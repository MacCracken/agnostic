"""GPU-aware crew scheduling.

Assigns agents to GPU devices based on their hardware requirements and
current GPU availability.  The scheduler produces a *placement plan* that
the crew runner applies before executing each agent (setting
``CUDA_VISIBLE_DEVICES`` and recording the allocation in the crew record).

Design goals
------------
- **Transparent fallback**: agents without ``gpu_required`` always run on CPU.
  If no GPU is available, GPU-preferring agents log a warning and proceed on
  CPU.  Only agents with ``gpu_required=True`` and ``gpu_strict=True`` block.
- **Memory-aware**: agents can declare ``gpu_memory_min_mb``. The scheduler
  skips GPUs without enough free VRAM.
- **Multi-GPU**: on multi-GPU hosts, agents are spread across devices to avoid
  contention.  Each agent gets a single device via ``CUDA_VISIBLE_DEVICES``.
- **Minimal invasiveness**: the scheduler is a pure function that reads GPU
  state and agent definitions and returns a plan dict. No global side effects.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from config.gpu import GPUStatus, detect_gpus

logger = logging.getLogger(__name__)


@dataclass
class AgentGPURequirements:
    """GPU requirements extracted from an agent definition."""

    agent_key: str
    gpu_required: bool = False
    gpu_strict: bool = False  # fail if no GPU available (vs. fallback to CPU)
    gpu_memory_min_mb: int = 0  # minimum VRAM needed
    gpu_preferred: bool = False  # prefers GPU but works without

    @classmethod
    def from_definition(cls, defn: Any) -> AgentGPURequirements:
        """Extract GPU requirements from an AgentDefinition or dict."""
        if isinstance(defn, dict):
            meta = defn.get("metadata", {})
            return cls(
                agent_key=defn.get("agent_key", "unknown"),
                gpu_required=defn.get("gpu_required", meta.get("gpu_required", False)),
                gpu_strict=defn.get("gpu_strict", meta.get("gpu_strict", False)),
                gpu_memory_min_mb=defn.get(
                    "gpu_memory_min_mb", meta.get("gpu_memory_min_mb", 0)
                ),
                gpu_preferred=defn.get(
                    "gpu_preferred", meta.get("gpu_preferred", False)
                ),
            )

        # AgentDefinition object (agents.base.AgentDefinition)
        meta = getattr(defn, "metadata", {}) or {}
        return cls(
            agent_key=getattr(defn, "agent_key", "unknown"),
            gpu_required=getattr(defn, "gpu_required", meta.get("gpu_required", False)),
            gpu_strict=getattr(defn, "gpu_strict", meta.get("gpu_strict", False)),
            gpu_memory_min_mb=getattr(
                defn, "gpu_memory_min_mb", meta.get("gpu_memory_min_mb", 0)
            ),
            gpu_preferred=getattr(
                defn, "gpu_preferred", meta.get("gpu_preferred", False)
            ),
        )


@dataclass
class GPUAssignment:
    """A single agent → GPU device assignment."""

    agent_key: str
    device_index: int  # -1 = CPU only
    device_name: str = ""
    memory_reserved_mb: int = 0
    cuda_visible_devices: str = ""  # the env var value to set

    @property
    def is_gpu(self) -> bool:
        return self.device_index >= 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_key": self.agent_key,
            "device_index": self.device_index,
            "device_name": self.device_name,
            "memory_reserved_mb": self.memory_reserved_mb,
            "cuda_visible_devices": self.cuda_visible_devices,
            "is_gpu": self.is_gpu,
        }


@dataclass
class GPUPlacementPlan:
    """Complete placement plan for a crew."""

    assignments: list[GPUAssignment] = field(default_factory=list)
    gpu_status: GPUStatus | None = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0

    @property
    def gpu_agents(self) -> list[GPUAssignment]:
        return [a for a in self.assignments if a.is_gpu]

    @property
    def cpu_agents(self) -> list[GPUAssignment]:
        return [a for a in self.assignments if not a.is_gpu]

    def get_assignment(self, agent_key: str) -> GPUAssignment | None:
        for a in self.assignments:
            if a.agent_key == agent_key:
                return a
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "assignments": [a.to_dict() for a in self.assignments],
            "gpu_available": self.gpu_status.available if self.gpu_status else False,
            "gpu_device_count": self.gpu_status.device_count if self.gpu_status else 0,
            "gpu_agents_count": len(self.gpu_agents),
            "cpu_agents_count": len(self.cpu_agents),
            "warnings": self.warnings,
            "errors": self.errors,
        }


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------


def schedule_crew_gpus(
    agent_definitions: list[Any],
    gpu_status: GPUStatus | None = None,
    memory_budget_mb: int | None = None,
) -> GPUPlacementPlan:
    """Create a GPU placement plan for a list of agent definitions.

    Args:
        agent_definitions: List of AgentDefinition objects or dicts.
        gpu_status: Pre-fetched GPU status. If None, will probe.
        memory_budget_mb: Optional crew-wide GPU memory budget in MB.
            If set, the total reserved GPU memory across all agents must
            not exceed this limit.

    Returns:
        A GPUPlacementPlan with assignments for each agent.
    """
    if gpu_status is None:
        gpu_status = detect_gpus()

    plan = GPUPlacementPlan(gpu_status=gpu_status)

    # Extract requirements for each agent
    requirements = [AgentGPURequirements.from_definition(d) for d in agent_definitions]

    # Track available memory per device (mutable copy)
    device_free: dict[int, int] = {}
    if gpu_status.available:
        for dev in gpu_status.devices:
            device_free[dev.index] = dev.memory_free_mb

    # Budget enforcement: pre-check total declared minimums
    if memory_budget_mb is not None and memory_budget_mb > 0:
        total_declared = sum(
            r.gpu_memory_min_mb
            for r in requirements
            if r.gpu_required or r.gpu_preferred
        )
        if total_declared > memory_budget_mb:
            plan.errors.append(
                f"Crew GPU memory budget exceeded: agents declare {total_declared} MB "
                f"but budget is {memory_budget_mb} MB"
            )
            # Still assign CPU for all agents so the plan is complete
            for req in requirements:
                plan.assignments.append(
                    GPUAssignment(agent_key=req.agent_key, device_index=-1)
                )
            return plan

    # Sort: strict GPU-required first, then preferred, then others
    # This ensures critical agents get GPU slots before optional ones
    def _priority(req: AgentGPURequirements) -> int:
        if req.gpu_required and req.gpu_strict:
            return 0
        if req.gpu_required:
            return 1
        if req.gpu_preferred:
            return 2
        return 3

    sorted_reqs = sorted(requirements, key=_priority)

    budget_remaining = (
        memory_budget_mb if memory_budget_mb and memory_budget_mb > 0 else None
    )

    for req in sorted_reqs:
        assignment = _assign_device(
            req, gpu_status, device_free, plan, budget_remaining
        )
        plan.assignments.append(assignment)
        if budget_remaining is not None and assignment.is_gpu:
            budget_remaining -= assignment.memory_reserved_mb

    # Re-sort assignments back to original agent order
    key_order = {
        (d.get("agent_key") if isinstance(d, dict) else getattr(d, "agent_key", "")): i
        for i, d in enumerate(agent_definitions)
    }
    plan.assignments.sort(key=lambda a: key_order.get(a.agent_key, 999))

    if plan.gpu_agents:
        total_reserved = sum(a.memory_reserved_mb for a in plan.gpu_agents)
        logger.info(
            "GPU scheduling: %d/%d agents on GPU, %d MB reserved%s (%s)",
            len(plan.gpu_agents),
            len(plan.assignments),
            total_reserved,
            f" (budget: {memory_budget_mb} MB)" if memory_budget_mb else "",
            ", ".join(f"{a.agent_key}→GPU:{a.device_index}" for a in plan.gpu_agents),
        )

    return plan


def _assign_device(
    req: AgentGPURequirements,
    gpu_status: GPUStatus,
    device_free: dict[int, int],
    plan: GPUPlacementPlan,
    budget_remaining: int | None = None,
) -> GPUAssignment:
    """Assign a single agent to a GPU device or CPU."""

    # Agent doesn't want GPU
    if not req.gpu_required and not req.gpu_preferred:
        return GPUAssignment(agent_key=req.agent_key, device_index=-1)

    # No GPUs available at all
    if not gpu_status.available or not device_free:
        if req.gpu_required and req.gpu_strict:
            plan.errors.append(
                f"Agent '{req.agent_key}' requires GPU (strict) but no GPU is available"
            )
        elif req.gpu_required:
            plan.warnings.append(
                f"Agent '{req.agent_key}' requires GPU but none available — falling back to CPU"
            )
        elif req.gpu_preferred:
            plan.warnings.append(
                f"Agent '{req.agent_key}' prefers GPU but none available — using CPU"
            )
        return GPUAssignment(agent_key=req.agent_key, device_index=-1)

    # Find best device: most free memory, meeting minimum requirement
    min_mem = req.gpu_memory_min_mb
    candidates = [(idx, free) for idx, free in device_free.items() if free >= min_mem]

    if not candidates:
        msg = (
            f"Agent '{req.agent_key}' needs {min_mem} MB GPU memory "
            f"but no device has enough free"
        )
        if req.gpu_required and req.gpu_strict:
            plan.errors.append(msg)
        else:
            plan.warnings.append(f"{msg} — falling back to CPU")
        return GPUAssignment(agent_key=req.agent_key, device_index=-1)

    # Budget check — if this agent's memory would exceed remaining budget, skip
    agent_mem = min_mem if min_mem > 0 else 1
    if budget_remaining is not None and agent_mem > budget_remaining:
        msg = (
            f"Agent '{req.agent_key}' needs {agent_mem} MB but crew budget "
            f"has only {budget_remaining} MB remaining"
        )
        if req.gpu_required and req.gpu_strict:
            plan.errors.append(msg)
        else:
            plan.warnings.append(f"{msg} — falling back to CPU")
        return GPUAssignment(agent_key=req.agent_key, device_index=-1)

    # Pick the device with the most free memory (spread load)
    best_idx, best_free = max(candidates, key=lambda c: c[1])

    # Reserve memory — use declared minimum, or a nominal 1 MB to track
    # that this device has an agent assigned (spreads load on ties)
    reserved = min_mem if min_mem > 0 else 1
    device_free[best_idx] -= reserved

    # Find device name
    device_name = ""
    for dev in gpu_status.devices:
        if dev.index == best_idx:
            device_name = dev.name
            break

    return GPUAssignment(
        agent_key=req.agent_key,
        device_index=best_idx,
        device_name=device_name,
        memory_reserved_mb=reserved,
        cuda_visible_devices=str(best_idx),
    )


def apply_gpu_assignment(assignment: GPUAssignment) -> dict[str, str]:
    """Return environment variables to set for an agent's GPU assignment.

    The caller should set these in ``os.environ`` before the agent runs
    (and restore them after).
    """
    env: dict[str, str] = {}
    if assignment.is_gpu:
        env["CUDA_VISIBLE_DEVICES"] = assignment.cuda_visible_devices
    else:
        # Explicitly hide GPUs from CPU-only agents to prevent accidental use
        env["CUDA_VISIBLE_DEVICES"] = ""
    return env


# ---------------------------------------------------------------------------
# Multi-crew GPU slot tracker
# ---------------------------------------------------------------------------


class GPUSlotTracker:
    """Track GPU reservations across concurrent crews.

    When multiple crews run simultaneously on a multi-GPU host, each crew's
    scheduler sees the *hardware* free memory but not what other crews have
    reserved.  This tracker provides a process-wide view of reservations so
    the scheduler can account for other active crews.

    Usage::

        tracker = GPUSlotTracker()
        tracker.reserve("crew-123", 0, 4000)   # crew-123 reserves 4 GB on GPU 0
        tracker.reserve("crew-123", 1, 8000)   # crew-123 reserves 8 GB on GPU 1
        adjusted = tracker.adjusted_free(gpu_status)  # {0: hw_free - 4000, 1: hw_free - 8000}
        tracker.release("crew-123")             # crew done, free all its slots
    """

    def __init__(self) -> None:
        # crew_id → list of (device_index, reserved_mb)
        self._reservations: dict[str, list[tuple[int, int]]] = {}

    def reserve(self, crew_id: str, device_index: int, memory_mb: int) -> None:
        """Record a GPU memory reservation for a crew."""
        if crew_id not in self._reservations:
            self._reservations[crew_id] = []
        self._reservations[crew_id].append((device_index, memory_mb))

    def release(self, crew_id: str) -> None:
        """Release all GPU reservations for a crew."""
        self._reservations.pop(crew_id, None)

    def total_reserved(self, device_index: int) -> int:
        """Total memory reserved on a device across all crews."""
        total = 0
        for reservations in self._reservations.values():
            for idx, mem in reservations:
                if idx == device_index:
                    total += mem
        return total

    def adjusted_free(self, gpu_status: GPUStatus) -> dict[int, int]:
        """Return per-device free memory adjusted for cross-crew reservations."""
        result: dict[int, int] = {}
        for dev in gpu_status.devices:
            reserved = self.total_reserved(dev.index)
            result[dev.index] = max(0, dev.memory_free_mb - reserved)
        return result

    def active_crews(self) -> list[str]:
        """Return IDs of crews with active GPU reservations."""
        return list(self._reservations.keys())

    def to_dict(self) -> dict[str, Any]:
        return {
            "active_crews": len(self._reservations),
            "reservations": {
                crew_id: [{"device": idx, "memory_mb": mem} for idx, mem in slots]
                for crew_id, slots in self._reservations.items()
            },
        }


# Process-wide singleton
gpu_slot_tracker = GPUSlotTracker()
