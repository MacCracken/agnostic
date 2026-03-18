"""Fleet node model — describes a single Agnostic instance in the fleet.

Each node self-describes its hardware capabilities, current load, group
membership, and liveness via periodic heartbeats stored in Redis.

Environment variables
---------------------
AGNOS_FLEET_ENABLED
    Master switch.  Default ``false``.
AGNOS_FLEET_NODE_ID
    Unique node identifier.  Defaults to hostname.
AGNOS_FLEET_GROUP
    Logical group this node belongs to (e.g. ``gpu-rack-1``).
AGNOS_FLEET_EXTERNAL_URL
    How other nodes reach this instance (e.g. ``http://node-2:8000``).
AGNOS_FLEET_HEARTBEAT_INTERVAL
    Seconds between heartbeat writes.  Default ``10``.
AGNOS_FLEET_HEARTBEAT_TTL
    Seconds before a node is considered dead.  Default ``30``.
"""

from __future__ import annotations

import os
import platform
import time
from dataclasses import dataclass, field
from typing import Any

FLEET_ENABLED = os.getenv("AGNOS_FLEET_ENABLED", "false").lower() in (
    "true",
    "1",
    "yes",
)
FLEET_NODE_ID = os.getenv("AGNOS_FLEET_NODE_ID", platform.node() or "agnostic-0")
FLEET_GROUP = os.getenv("AGNOS_FLEET_GROUP", "default")
FLEET_EXTERNAL_URL = os.getenv("AGNOS_FLEET_EXTERNAL_URL", "http://localhost:8000")
HEARTBEAT_INTERVAL = int(os.getenv("AGNOS_FLEET_HEARTBEAT_INTERVAL", "10"))
HEARTBEAT_TTL = int(os.getenv("AGNOS_FLEET_HEARTBEAT_TTL", "30"))


@dataclass
class NodeCapabilities:
    """Hardware and software capabilities of a fleet node."""

    cpu_cores: int = 0
    ram_total_mb: int = 0
    ram_free_mb: int = 0
    gpu_count: int = 0
    gpu_names: list[str] = field(default_factory=list)
    gpu_vram_total_mb: int = 0
    gpu_vram_free_mb: int = 0
    tools: list[str] = field(default_factory=list)
    python_version: str = ""
    crewai_version: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "cpu_cores": self.cpu_cores,
            "ram_total_mb": self.ram_total_mb,
            "ram_free_mb": self.ram_free_mb,
            "gpu_count": self.gpu_count,
            "gpu_names": self.gpu_names,
            "gpu_vram_total_mb": self.gpu_vram_total_mb,
            "gpu_vram_free_mb": self.gpu_vram_free_mb,
            "tools": self.tools,
            "python_version": self.python_version,
            "crewai_version": self.crewai_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NodeCapabilities:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    @classmethod
    def probe_local(cls) -> NodeCapabilities:
        """Probe the local host for capabilities."""
        import multiprocessing

        caps = cls(
            cpu_cores=multiprocessing.cpu_count(),
            python_version=platform.python_version(),
        )

        # RAM
        try:
            import psutil

            mem = psutil.virtual_memory()
            caps.ram_total_mb = int(mem.total / (1024 * 1024))
            caps.ram_free_mb = int(mem.available / (1024 * 1024))
        except ImportError:
            pass

        # GPU
        try:
            from config.gpu import detect_gpus

            gpu_status = detect_gpus()
            if gpu_status.available:
                caps.gpu_count = gpu_status.device_count
                caps.gpu_names = [d.name for d in gpu_status.devices]
                caps.gpu_vram_total_mb = gpu_status.total_memory_mb
                caps.gpu_vram_free_mb = gpu_status.free_memory_mb
        except ImportError:
            pass

        # Tools
        try:
            from agents.tool_registry import tool_registry

            caps.tools = list(tool_registry.keys())
        except ImportError:
            pass

        # CrewAI version
        try:
            import crewai

            caps.crewai_version = getattr(crewai, "__version__", "unknown")
        except ImportError:
            pass

        return caps


@dataclass
class FleetNode:
    """A single node in the fleet."""

    node_id: str
    group: str = "default"
    external_url: str = "http://localhost:8000"
    capabilities: NodeCapabilities = field(default_factory=NodeCapabilities)
    status: str = "online"  # online, draining, offline
    active_crews: int = 0
    active_agents: int = 0
    last_heartbeat: float = 0.0
    registered_at: float = 0.0

    @property
    def is_alive(self) -> bool:
        return (time.time() - self.last_heartbeat) < HEARTBEAT_TTL

    @property
    def has_gpu(self) -> bool:
        return self.capabilities.gpu_count > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "group": self.group,
            "external_url": self.external_url,
            "capabilities": self.capabilities.to_dict(),
            "status": self.status,
            "active_crews": self.active_crews,
            "active_agents": self.active_agents,
            "last_heartbeat": self.last_heartbeat,
            "registered_at": self.registered_at,
            "is_alive": self.is_alive,
            "has_gpu": self.has_gpu,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FleetNode:
        caps_data = data.pop("capabilities", {})
        # Remove computed properties
        data.pop("is_alive", None)
        data.pop("has_gpu", None)
        return cls(
            capabilities=NodeCapabilities.from_dict(caps_data),
            **{k: v for k, v in data.items() if k in cls.__dataclass_fields__},
        )

    @classmethod
    def local(cls) -> FleetNode:
        """Create a FleetNode representing this instance."""
        return cls(
            node_id=FLEET_NODE_ID,
            group=FLEET_GROUP,
            external_url=FLEET_EXTERNAL_URL,
            capabilities=NodeCapabilities.probe_local(),
            status="online",
            last_heartbeat=time.time(),
            registered_at=time.time(),
        )
