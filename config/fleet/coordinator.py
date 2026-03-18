"""Fleet crew coordinator — manages distributed crew lifecycle.

The coordinator is the node that received the crew request. It:
1. Runs the placement engine to assign agents to nodes
2. Publishes task handoffs via the relay
3. Collects results and aggregates them
4. Monitors node health and re-places agents on failure
5. Can be transferred to another node if the coordinator fails

Coordinator election is simple: the node that receives the `POST /crews`
request becomes the coordinator for that crew. If it fails, any node can
promote itself by checking the checkpointed state and calling
``set_coordinator()``.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from config.fleet.node import FLEET_NODE_ID, FleetNode
from config.fleet.placement import PlacementPlan, place_agents
from config.fleet.relay import RelayMessage, task_relay
from config.fleet.state import crew_state_manager

logger = logging.getLogger(__name__)


class FleetCoordinator:
    """Coordinates a single distributed crew execution."""

    def __init__(
        self,
        crew_id: str,
        *,
        node_id: str | None = None,
    ) -> None:
        self.crew_id = crew_id
        self.node_id = node_id or FLEET_NODE_ID
        self._results: dict[str, dict[str, Any]] = {}
        self._result_event = asyncio.Event()
        self._subscription: asyncio.Task | None = None  # type: ignore[type-arg]
        self._expected_agents: set[str] = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def plan_and_distribute(
        self,
        agent_definitions: list[Any],
        nodes: list[FleetNode],
        task_data: dict[str, Any],
        *,
        policy: str = "gpu-affinity",
        group: str | None = None,
        redis_client: Any | None = None,
    ) -> PlacementPlan:
        """Place agents across nodes and create distributed crew state.

        Returns the placement plan. After this, call ``execute_and_collect``
        to run the crew.
        """
        # Run placement
        plan = place_agents(agent_definitions, nodes, policy=policy, group=group)
        if plan.has_errors:
            return plan

        # Create crew state in Redis
        await crew_state_manager.create(
            self.crew_id,
            self.node_id,
            plan.placements,
            group=group,
            redis_client=redis_client,
        )

        # Track expected agents
        self._expected_agents = {p.agent_key for p in plan.placements}

        # Subscribe to relay messages for this crew
        self._subscription = await task_relay.subscribe(
            self.crew_id, self._handle_relay_message, redis_client
        )

        # Publish task handoffs to each remote node
        local_agents = []
        for placement in plan.placements:
            if placement.node_id == self.node_id:
                local_agents.append(placement.agent_key)
            else:
                await task_relay.publish_task_handoff(
                    crew_id=self.crew_id,
                    agent_key=placement.agent_key,
                    source_node=self.node_id,
                    target_node=placement.node_id,
                    task_data={
                        **task_data,
                        "_fleet_placement": placement.to_dict(),
                    },
                    redis_client=redis_client,
                )

        await crew_state_manager.set_status(
            self.crew_id, "running", redis_client=redis_client
        )

        logger.info(
            "Fleet coordinator %s: crew %s distributed — %d local, %d remote agents",
            self.node_id,
            self.crew_id,
            len(local_agents),
            len(plan.placements) - len(local_agents),
        )

        return plan

    async def collect_results(
        self,
        timeout: float = 600.0,
        redis_client: Any | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Wait for all agent results to arrive.

        Local agents should call ``submit_result()`` directly.
        Remote agents publish results via the relay.
        """
        deadline = time.time() + timeout

        while len(self._results) < len(self._expected_agents):
            remaining = deadline - time.time()
            if remaining <= 0:
                missing = self._expected_agents - set(self._results.keys())
                logger.warning(
                    "Fleet crew %s timed out waiting for agents: %s",
                    self.crew_id,
                    missing,
                )
                for agent_key in missing:
                    self._results[agent_key] = {
                        "status": "failed",
                        "error": "Timed out waiting for result",
                    }
                break

            self._result_event.clear()
            try:
                await asyncio.wait_for(
                    self._result_event.wait(), timeout=min(remaining, 5.0)
                )
            except TimeoutError:
                # Check for dead nodes
                await self._check_node_health(redis_client)

        # Finalize
        all_ok = all(r.get("status") == "completed" for r in self._results.values())
        final_status = "completed" if all_ok else "partial"
        await crew_state_manager.set_status(
            self.crew_id, final_status, redis_client=redis_client
        )

        return self._results

    def submit_result(self, agent_key: str, result: dict[str, Any]) -> None:
        """Submit a result from a locally-executed agent."""
        self._results[agent_key] = result
        self._result_event.set()

    async def cleanup(self, redis_client: Any | None = None) -> None:
        """Clean up coordinator resources."""
        if self._subscription:
            self._subscription.cancel()
            self._subscription = None
        task_relay.cleanup(self.crew_id)

    # ------------------------------------------------------------------
    # Relay message handling
    # ------------------------------------------------------------------

    async def _handle_relay_message(self, msg: RelayMessage) -> None:
        """Process an incoming relay message."""
        if msg.msg_type == "agent_result":
            self._results[msg.agent_key] = msg.payload
            self._result_event.set()

            # Update crew state
            status = msg.payload.get("status", "completed")
            await crew_state_manager.update_agent_status(
                self.crew_id, msg.agent_key, status, result=msg.payload
            )

    # ------------------------------------------------------------------
    # Health monitoring
    # ------------------------------------------------------------------

    async def _check_node_health(self, redis_client: Any | None = None) -> None:
        """Check if any nodes hosting agents have gone offline."""
        from config.fleet.registry import fleet_registry

        state = await crew_state_manager.get(self.crew_id, redis_client)
        if not state:
            return

        for placement in state.placements:
            if placement.agent_key in self._results:
                continue  # already have result

            node = await fleet_registry.get_node(placement.node_id, redis_client)
            if node and node.is_alive:
                continue

            logger.warning(
                "Fleet crew %s: node %s is dead, agent %s needs re-placement",
                self.crew_id,
                placement.node_id,
                placement.agent_key,
            )

            # Mark agent as failed — the fleet-aware crew builder can
            # attempt re-placement from the checkpoint
            self._results[placement.agent_key] = {
                "status": "failed",
                "error": f"Node {placement.node_id} went offline",
                "_needs_replace": True,
            }
            self._result_event.set()


async def promote_coordinator(
    crew_id: str,
    new_node_id: str | None = None,
    redis_client: Any | None = None,
) -> FleetCoordinator:
    """Promote this node to coordinator for a crew (failover).

    Reads the existing crew state and creates a new coordinator that
    can continue collecting results.
    """
    node_id = new_node_id or FLEET_NODE_ID

    await crew_state_manager.set_coordinator(
        crew_id, node_id, redis_client=redis_client
    )

    coordinator = FleetCoordinator(crew_id, node_id=node_id)

    # Load existing state to know which agents to expect
    state = await crew_state_manager.get(crew_id, redis_client)
    if state:
        coordinator._expected_agents = {p.agent_key for p in state.placements}
        # Pre-populate with any already-completed agents
        for p in state.placements:
            if p.status in ("completed", "failed") and p.result:
                coordinator._results[p.agent_key] = p.result

    # Subscribe to relay
    coordinator._subscription = await task_relay.subscribe(
        crew_id, coordinator._handle_relay_message, redis_client
    )

    logger.info("Fleet coordinator promoted: %s for crew %s", node_id, crew_id)
    return coordinator
