"""Fleet placement engine — assigns agents to fleet nodes.

Given a list of agent definitions and the current fleet inventory, the
placement engine decides which node runs each agent.  Pluggable scheduling
policies control the strategy.

Policies
--------
- ``gpu-affinity`` (default) — prefer GPU nodes for GPU-requiring agents
- ``data-locality`` — place agents near data (stub, needs context)
- ``balanced`` — spread load evenly across nodes
- ``cost-aware`` — prefer cheaper/lower-power nodes first
- ``lockstep-strict`` — co-locate on fewest nodes possible
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from config.fleet.node import FleetNode
from config.fleet.state import AgentPlacement

logger = logging.getLogger(__name__)

SCHEDULING_POLICIES = (
    "gpu-affinity",
    "data-locality",
    "balanced",
    "cost-aware",
    "lockstep-strict",
)


@dataclass
class PlacementPlan:
    """Result of the placement engine."""

    placements: list[AgentPlacement] = field(default_factory=list)
    policy: str = "gpu-affinity"
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "placements": [p.to_dict() for p in self.placements],
            "policy": self.policy,
            "warnings": self.warnings,
            "errors": self.errors,
        }


def place_agents(
    agent_definitions: list[Any],
    nodes: list[FleetNode],
    *,
    policy: str = "gpu-affinity",
    group: str | None = None,
) -> PlacementPlan:
    """Assign agents to fleet nodes based on the scheduling policy.

    Args:
        agent_definitions: Agent definitions (dicts or AgentDefinition objects).
        nodes: Available fleet nodes (should be alive only).
        policy: Scheduling policy name.
        group: If set, only place on nodes in this group.

    Returns:
        A PlacementPlan with one AgentPlacement per agent.
    """
    plan = PlacementPlan(policy=policy)

    if not nodes:
        plan.errors.append("No fleet nodes available for placement")
        return plan

    # Filter by group if specified
    if group:
        nodes = [n for n in nodes if n.group == group]
        if not nodes:
            plan.errors.append(f"No nodes in group '{group}'")
            return plan

    # Filter out draining/offline nodes
    available = [n for n in nodes if n.status == "online" and n.is_alive]
    if not available:
        plan.errors.append("No online nodes available")
        return plan

    if policy == "lockstep-strict":
        _place_lockstep_strict(agent_definitions, available, plan)
    elif policy == "balanced":
        _place_balanced(agent_definitions, available, plan)
    elif policy == "cost-aware":
        _place_cost_aware(agent_definitions, available, plan)
    else:
        # gpu-affinity is the default, data-locality falls through here too
        _place_gpu_affinity(agent_definitions, available, plan)

    if plan.placements:
        node_counts: dict[str, int] = {}
        for p in plan.placements:
            node_counts[p.node_id] = node_counts.get(p.node_id, 0) + 1
        logger.info(
            "Fleet placement (%s): %d agents across %d nodes — %s",
            policy,
            len(plan.placements),
            len(node_counts),
            ", ".join(f"{nid}={cnt}" for nid, cnt in node_counts.items()),
        )

    return plan


# ---------------------------------------------------------------------------
# Policy implementations
# ---------------------------------------------------------------------------


def _get_gpu_req(defn: Any) -> tuple[bool, int]:
    """Extract GPU requirements from a definition."""
    if isinstance(defn, dict):
        meta = defn.get("metadata", {})
        gpu = defn.get("gpu_required", meta.get("gpu_required", False))
        mem = defn.get("gpu_memory_min_mb", meta.get("gpu_memory_min_mb", 0))
        return bool(gpu), int(mem)
    gpu = getattr(defn, "gpu_required", False)
    mem = getattr(defn, "gpu_memory_min_mb", 0)
    return bool(gpu), int(mem)


def _agent_key(defn: Any) -> str:
    if isinstance(defn, dict):
        return defn.get("agent_key", "unknown")
    return getattr(defn, "agent_key", "unknown")


def _node_score_gpu(node: FleetNode) -> float:
    """Score a node for GPU workloads (higher = better)."""
    score = float(node.capabilities.gpu_vram_free_mb)
    # Penalize busy nodes
    score -= node.active_agents * 100
    return score


def _node_score_balanced(node: FleetNode) -> float:
    """Score a node for balanced placement (fewer agents = higher score)."""
    return float(node.capabilities.cpu_cores * 100 - node.active_agents * 200)


def _place_gpu_affinity(
    definitions: list[Any],
    nodes: list[FleetNode],
    plan: PlacementPlan,
) -> None:
    """GPU-requiring agents go to GPU nodes; others spread across all."""
    gpu_nodes = [n for n in nodes if n.has_gpu]
    # Track allocations per node for spreading
    alloc_count: dict[str, int] = {n.node_id: 0 for n in nodes}

    for defn in definitions:
        key = _agent_key(defn)
        needs_gpu, gpu_mem = _get_gpu_req(defn)

        if needs_gpu:
            if not gpu_nodes:
                plan.warnings.append(
                    f"Agent '{key}' needs GPU but no GPU nodes available — placing on CPU"
                )
                best = _pick_least_loaded(nodes, alloc_count)
                plan.placements.append(
                    AgentPlacement(agent_key=key, node_id=best.node_id)
                )
            else:
                # Pick GPU node with most free VRAM
                candidates = sorted(gpu_nodes, key=_node_score_gpu, reverse=True)
                best = candidates[0]
                plan.placements.append(
                    AgentPlacement(
                        agent_key=key,
                        node_id=best.node_id,
                        device_index=0,
                    )
                )
        else:
            best = _pick_least_loaded(nodes, alloc_count)
            plan.placements.append(AgentPlacement(agent_key=key, node_id=best.node_id))

        alloc_count[plan.placements[-1].node_id] += 1


def _place_balanced(
    definitions: list[Any],
    nodes: list[FleetNode],
    plan: PlacementPlan,
) -> None:
    """Spread agents evenly across all nodes (round-robin)."""
    alloc_count: dict[str, int] = {n.node_id: 0 for n in nodes}

    for defn in definitions:
        key = _agent_key(defn)
        best = _pick_least_loaded(nodes, alloc_count)
        plan.placements.append(AgentPlacement(agent_key=key, node_id=best.node_id))
        alloc_count[best.node_id] += 1


def _place_cost_aware(
    definitions: list[Any],
    nodes: list[FleetNode],
    plan: PlacementPlan,
) -> None:
    """Prefer nodes without GPU (cheaper), escalate to GPU only when needed."""
    cpu_nodes = [n for n in nodes if not n.has_gpu]
    gpu_nodes = [n for n in nodes if n.has_gpu]
    alloc_count: dict[str, int] = {n.node_id: 0 for n in nodes}

    for defn in definitions:
        key = _agent_key(defn)
        needs_gpu, _ = _get_gpu_req(defn)

        if needs_gpu and gpu_nodes:
            best = _pick_least_loaded(gpu_nodes, alloc_count)
            plan.placements.append(
                AgentPlacement(agent_key=key, node_id=best.node_id, device_index=0)
            )
        elif cpu_nodes:
            best = _pick_least_loaded(cpu_nodes, alloc_count)
            plan.placements.append(AgentPlacement(agent_key=key, node_id=best.node_id))
        else:
            best = _pick_least_loaded(nodes, alloc_count)
            plan.placements.append(AgentPlacement(agent_key=key, node_id=best.node_id))

        alloc_count[plan.placements[-1].node_id] += 1


def _place_lockstep_strict(
    definitions: list[Any],
    nodes: list[FleetNode],
    plan: PlacementPlan,
) -> None:
    """Co-locate all agents on the fewest nodes possible.

    Prioritizes nodes with more resources. GPU agents go to GPU nodes.
    """
    # Sort nodes by capacity (most capable first)
    sorted_nodes = sorted(
        nodes,
        key=lambda n: (n.capabilities.gpu_count, n.capabilities.cpu_cores),
        reverse=True,
    )

    gpu_agents = [d for d in definitions if _get_gpu_req(d)[0]]
    cpu_agents = [d for d in definitions if not _get_gpu_req(d)[0]]

    # Place GPU agents on first GPU node
    gpu_node = next((n for n in sorted_nodes if n.has_gpu), None)
    for defn in gpu_agents:
        key = _agent_key(defn)
        if gpu_node:
            plan.placements.append(
                AgentPlacement(agent_key=key, node_id=gpu_node.node_id, device_index=0)
            )
        else:
            plan.warnings.append(
                f"Agent '{key}' needs GPU, none available — using first node"
            )
            plan.placements.append(
                AgentPlacement(agent_key=key, node_id=sorted_nodes[0].node_id)
            )

    # Place CPU agents on first available node (co-locate)
    target = sorted_nodes[0]
    for defn in cpu_agents:
        key = _agent_key(defn)
        plan.placements.append(AgentPlacement(agent_key=key, node_id=target.node_id))


def _pick_least_loaded(
    nodes: list[FleetNode],
    alloc_count: dict[str, int],
) -> FleetNode:
    """Pick the node with the fewest allocated agents."""
    return min(nodes, key=lambda n: alloc_count.get(n.node_id, 0) + n.active_agents)
