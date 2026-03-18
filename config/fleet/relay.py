"""Inter-node task relay — Redis pub/sub message passing between fleet nodes.

Agents on different nodes communicate via Redis pub/sub channels. Each
message carries a sequence number for ordering guarantees and exactly-once
delivery tracking.

Channels
--------
fleet:relay:{crew_id}           — task handoff messages for a crew
fleet:relay:{crew_id}:ack       — acknowledgments from receiving nodes
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class RelayMessage:
    """A message sent between nodes in a fleet crew."""

    crew_id: str
    agent_key: str
    source_node: str
    target_node: str
    seq: int
    msg_type: str  # task_handoff, agent_result, barrier_advance, checkpoint
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = time.time()

    def to_json(self) -> str:
        return json.dumps(
            {
                "crew_id": self.crew_id,
                "agent_key": self.agent_key,
                "source_node": self.source_node,
                "target_node": self.target_node,
                "seq": self.seq,
                "msg_type": self.msg_type,
                "payload": self.payload,
                "timestamp": self.timestamp,
            }
        )

    @classmethod
    def from_json(cls, data: str) -> RelayMessage:
        d = json.loads(data)
        return cls(**d)


class TaskRelay:
    """Publish and subscribe to inter-node task messages."""

    def __init__(self) -> None:
        self._seen_seqs: dict[str, set[int]] = {}  # crew_id → set of seen seq numbers
        self._seq_counter: dict[str, int] = {}  # crew_id → next seq

    def _next_seq(self, crew_id: str) -> int:
        seq = self._seq_counter.get(crew_id, 0) + 1
        self._seq_counter[crew_id] = seq
        return seq

    def _is_duplicate(self, crew_id: str, seq: int) -> bool:
        seen = self._seen_seqs.setdefault(crew_id, set())
        if seq in seen:
            return True
        seen.add(seq)
        # Cap the seen set to prevent unbounded growth
        if len(seen) > 10000:
            # Keep only recent sequences
            min_keep = max(seen) - 5000
            seen -= {s for s in seen if s < min_keep}
        return False

    async def publish(
        self,
        msg: RelayMessage,
        redis_client: Any | None = None,
    ) -> None:
        """Publish a relay message to the crew's channel."""
        client = redis_client or await self._get_redis()
        if msg.seq == 0:
            msg.seq = self._next_seq(msg.crew_id)

        channel = f"fleet:relay:{msg.crew_id}"
        await client.publish(channel, msg.to_json())

        logger.debug(
            "Relay published: crew=%s seq=%d type=%s %s→%s",
            msg.crew_id,
            msg.seq,
            msg.msg_type,
            msg.source_node,
            msg.target_node,
        )

    async def publish_task_handoff(
        self,
        crew_id: str,
        agent_key: str,
        source_node: str,
        target_node: str,
        task_data: dict[str, Any],
        redis_client: Any | None = None,
    ) -> int:
        """Publish a task handoff message. Returns the sequence number."""
        msg = RelayMessage(
            crew_id=crew_id,
            agent_key=agent_key,
            source_node=source_node,
            target_node=target_node,
            seq=self._next_seq(crew_id),
            msg_type="task_handoff",
            payload=task_data,
        )
        await self.publish(msg, redis_client)
        return msg.seq

    async def publish_result(
        self,
        crew_id: str,
        agent_key: str,
        source_node: str,
        target_node: str,
        result: dict[str, Any],
        redis_client: Any | None = None,
    ) -> None:
        """Publish an agent result back to the coordinator."""
        msg = RelayMessage(
            crew_id=crew_id,
            agent_key=agent_key,
            source_node=source_node,
            target_node=target_node,
            seq=self._next_seq(crew_id),
            msg_type="agent_result",
            payload=result,
        )
        await self.publish(msg, redis_client)

    async def subscribe(
        self,
        crew_id: str,
        handler: Any,
        redis_client: Any | None = None,
    ) -> asyncio.Task:  # type: ignore[type-arg]
        """Subscribe to relay messages for a crew.

        The handler is called with each RelayMessage (deduplicated).
        Returns the subscription task (cancel to unsubscribe).
        """
        client = redis_client or await self._get_redis()
        channel = f"fleet:relay:{crew_id}"

        pubsub = client.pubsub()
        await pubsub.subscribe(channel)

        async def _listen() -> None:
            try:
                async for message in pubsub.listen():
                    if message["type"] != "message":
                        continue
                    try:
                        relay_msg = RelayMessage.from_json(message["data"])
                        if self._is_duplicate(crew_id, relay_msg.seq):
                            continue
                        await handler(relay_msg)
                    except Exception as exc:
                        logger.warning("Relay message handling failed: %s", exc)
            except asyncio.CancelledError:
                await pubsub.unsubscribe(channel)
            except Exception as exc:
                logger.error("Relay subscription error: %s", exc)

        task = asyncio.create_task(_listen())
        return task

    def cleanup(self, crew_id: str) -> None:
        """Remove tracking state for a completed crew."""
        self._seen_seqs.pop(crew_id, None)
        self._seq_counter.pop(crew_id, None)

    async def _get_redis(self) -> Any:
        from config.environment import config

        return config.get_async_redis_client()


# Singleton
task_relay = TaskRelay()
