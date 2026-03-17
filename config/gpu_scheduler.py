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
) -> GPUPlacementPlan:
    """Create a GPU placement plan for a list of agent definitions.

    Args:
        agent_definitions: List of AgentDefinition objects or dicts.
        gpu_status: Pre-fetched GPU status. If None, will probe.

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

    for req in sorted_reqs:
        assignment = _assign_device(req, gpu_status, device_free, plan)
        plan.assignments.append(assignment)

    # Re-sort assignments back to original agent order
    key_order = {
        (d.get("agent_key") if isinstance(d, dict) else getattr(d, "agent_key", "")): i
        for i, d in enumerate(agent_definitions)
    }
    plan.assignments.sort(key=lambda a: key_order.get(a.agent_key, 999))

    if plan.gpu_agents:
        logger.info(
            "GPU scheduling: %d/%d agents assigned to GPU (%s)",
            len(plan.gpu_agents),
            len(plan.assignments),
            ", ".join(f"{a.agent_key}→GPU:{a.device_index}" for a in plan.gpu_agents),
        )

    return plan


def _assign_device(
    req: AgentGPURequirements,
    gpu_status: GPUStatus,
    device_free: dict[int, int],
    plan: GPUPlacementPlan,
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
