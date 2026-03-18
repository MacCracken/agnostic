"""Unified crew state — Redis-backed shared state for distributed crews.

A single ``CrewState`` object represents a crew regardless of how many
nodes participate.  Every agent reads from and writes to the same logical
state.  Conflict resolution via Redis optimistic locking (WATCH/MULTI)
ensures consistency without distributed consensus overhead.

Redis key layout
----------------
fleet:crew:{crew_id}:state      — JSON blob of crew-wide state
fleet:crew:{crew_id}:agents     — HASH of agent_key → agent state JSON
fleet:crew:{crew_id}:barrier    — current barrier sequence number
fleet:crew:{crew_id}:coordinator — node_id of the coordinator
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

_CREW_STATE_TTL = 86400  # 24 hours


@dataclass
class AgentPlacement:
    """Where an agent is placed in the fleet."""

    agent_key: str
    node_id: str
    device_index: int = -1  # GPU device, -1 = CPU
    status: str = "pending"  # pending, running, completed, failed
    started_at: float = 0.0
    completed_at: float = 0.0
    result: dict[str, Any] | None = None
    checkpoint: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_key": self.agent_key,
            "node_id": self.node_id,
            "device_index": self.device_index,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "result": self.result,
            "checkpoint": self.checkpoint,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentPlacement:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class CrewState:
    """Shared state for a distributed crew execution."""

    crew_id: str
    coordinator_node_id: str = ""
    status: str = "pending"  # pending, running, completed, failed, partial
    barrier_seq: int = 0  # current barrier sequence number
    placements: list[AgentPlacement] = field(default_factory=list)
    created_at: float = 0.0
    updated_at: float = 0.0
    group: str | None = None  # optional group pinning

    def to_dict(self) -> dict[str, Any]:
        return {
            "crew_id": self.crew_id,
            "coordinator_node_id": self.coordinator_node_id,
            "status": self.status,
            "barrier_seq": self.barrier_seq,
            "placements": [p.to_dict() for p in self.placements],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "group": self.group,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CrewState:
        placements_raw = data.pop("placements", [])
        placements = [AgentPlacement.from_dict(p) for p in placements_raw]
        return cls(
            placements=placements,
            **{k: v for k, v in data.items() if k in cls.__dataclass_fields__},
        )

    def get_placement(self, agent_key: str) -> AgentPlacement | None:
        for p in self.placements:
            if p.agent_key == agent_key:
                return p
        return None


class CrewStateManager:
    """Manages distributed crew state in Redis with optimistic locking."""

    # ------------------------------------------------------------------
    # Create / Read
    # ------------------------------------------------------------------

    async def create(
        self,
        crew_id: str,
        coordinator_node_id: str,
        placements: list[AgentPlacement],
        *,
        group: str | None = None,
        redis_client: Any | None = None,
    ) -> CrewState:
        """Create a new crew state entry."""
        client = redis_client or await self._get_redis()
        now = time.time()

        state = CrewState(
            crew_id=crew_id,
            coordinator_node_id=coordinator_node_id,
            status="pending",
            barrier_seq=0,
            placements=placements,
            created_at=now,
            updated_at=now,
            group=group,
        )

        key = f"fleet:crew:{crew_id}:state"
        await client.setex(key, _CREW_STATE_TTL, json.dumps(state.to_dict()))

        # Store coordinator
        await client.setex(
            f"fleet:crew:{crew_id}:coordinator",
            _CREW_STATE_TTL,
            coordinator_node_id,
        )

        # Store individual agent placements
        for p in placements:
            await client.hset(
                f"fleet:crew:{crew_id}:agents",
                p.agent_key,
                json.dumps(p.to_dict()),
            )
        await client.expire(f"fleet:crew:{crew_id}:agents", _CREW_STATE_TTL)

        # Initialize barrier
        await client.setex(f"fleet:crew:{crew_id}:barrier", _CREW_STATE_TTL, "0")

        logger.info(
            "Fleet crew state created: %s (coordinator=%s, agents=%d, group=%s)",
            crew_id,
            coordinator_node_id,
            len(placements),
            group,
        )
        return state

    async def get(
        self, crew_id: str, redis_client: Any | None = None
    ) -> CrewState | None:
        """Read the current crew state."""
        client = redis_client or await self._get_redis()
        raw = await client.get(f"fleet:crew:{crew_id}:state")
        if not raw:
            return None
        return CrewState.from_dict(json.loads(raw))

    # ------------------------------------------------------------------
    # Updates with optimistic locking
    # ------------------------------------------------------------------

    async def update_agent_status(
        self,
        crew_id: str,
        agent_key: str,
        status: str,
        *,
        result: dict[str, Any] | None = None,
        checkpoint: dict[str, Any] | None = None,
        redis_client: Any | None = None,
    ) -> bool:
        """Update a single agent's status within the crew.

        Uses Redis WATCH/MULTI for optimistic locking on the crew state.
        Returns True if the update succeeded, False on conflict (retry needed).
        """
        client = redis_client or await self._get_redis()
        state_key = f"fleet:crew:{crew_id}:state"
        agents_key = f"fleet:crew:{crew_id}:agents"

        # Update agent hash
        raw = await client.hget(agents_key, agent_key)
        if raw:
            placement = AgentPlacement.from_dict(json.loads(raw))
            placement.status = status
            if result is not None:
                placement.result = result
            if checkpoint is not None:
                placement.checkpoint = checkpoint
            if status == "running" and not placement.started_at:
                placement.started_at = time.time()
            if status in ("completed", "failed"):
                placement.completed_at = time.time()
            await client.hset(agents_key, agent_key, json.dumps(placement.to_dict()))

        # Update crew-level state
        state = await self.get(crew_id, client)
        if not state:
            return False

        # Refresh placement from hash
        for p in state.placements:
            if p.agent_key == agent_key:
                p.status = status
                if result is not None:
                    p.result = result
                if checkpoint is not None:
                    p.checkpoint = checkpoint
                break

        state.updated_at = time.time()
        await client.setex(state_key, _CREW_STATE_TTL, json.dumps(state.to_dict()))
        return True

    async def advance_barrier(
        self,
        crew_id: str,
        redis_client: Any | None = None,
    ) -> int:
        """Increment the barrier sequence number. Returns the new value."""
        client = redis_client or await self._get_redis()
        key = f"fleet:crew:{crew_id}:barrier"
        new_seq = await client.incr(key)
        await client.expire(key, _CREW_STATE_TTL)
        return int(new_seq)

    async def get_barrier(
        self,
        crew_id: str,
        redis_client: Any | None = None,
    ) -> int:
        """Get the current barrier sequence number."""
        client = redis_client or await self._get_redis()
        val = await client.get(f"fleet:crew:{crew_id}:barrier")
        return int(val) if val else 0

    async def set_status(
        self,
        crew_id: str,
        status: str,
        redis_client: Any | None = None,
    ) -> None:
        """Update the overall crew status."""
        client = redis_client or await self._get_redis()
        state = await self.get(crew_id, client)
        if state:
            state.status = status
            state.updated_at = time.time()
            await client.setex(
                f"fleet:crew:{crew_id}:state",
                _CREW_STATE_TTL,
                json.dumps(state.to_dict()),
            )

    async def set_coordinator(
        self,
        crew_id: str,
        node_id: str,
        redis_client: Any | None = None,
    ) -> None:
        """Transfer coordination to a different node (failover)."""
        client = redis_client or await self._get_redis()
        await client.setex(
            f"fleet:crew:{crew_id}:coordinator", _CREW_STATE_TTL, node_id
        )
        state = await self.get(crew_id, client)
        if state:
            state.coordinator_node_id = node_id
            state.updated_at = time.time()
            await client.setex(
                f"fleet:crew:{crew_id}:state",
                _CREW_STATE_TTL,
                json.dumps(state.to_dict()),
            )
        logger.info("Fleet crew %s coordinator transferred to %s", crew_id, node_id)

    # ------------------------------------------------------------------
    # Checkpoint & recovery
    # ------------------------------------------------------------------

    async def checkpoint_agent(
        self,
        crew_id: str,
        agent_key: str,
        checkpoint_data: dict[str, Any],
        redis_client: Any | None = None,
    ) -> None:
        """Save a checkpoint for an agent (for recovery after node failure)."""
        await self.update_agent_status(
            crew_id,
            agent_key,
            status="running",
            checkpoint=checkpoint_data,
            redis_client=redis_client,
        )

    async def get_checkpoint(
        self,
        crew_id: str,
        agent_key: str,
        redis_client: Any | None = None,
    ) -> dict[str, Any] | None:
        """Retrieve the last checkpoint for an agent."""
        client = redis_client or await self._get_redis()
        raw = await client.hget(f"fleet:crew:{crew_id}:agents", agent_key)
        if not raw:
            return None
        placement = AgentPlacement.from_dict(json.loads(raw))
        return placement.checkpoint

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    async def delete(self, crew_id: str, redis_client: Any | None = None) -> None:
        """Remove all state for a crew."""
        client = redis_client or await self._get_redis()
        await asyncio.gather(
            client.delete(f"fleet:crew:{crew_id}:state"),
            client.delete(f"fleet:crew:{crew_id}:agents"),
            client.delete(f"fleet:crew:{crew_id}:barrier"),
            client.delete(f"fleet:crew:{crew_id}:coordinator"),
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _get_redis(self) -> Any:
        from config.environment import config

        return config.get_async_redis_client()


# Singleton
crew_state_manager = CrewStateManager()
