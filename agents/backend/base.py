"""Abstract crew execution backend."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CrewProfile:
    """Execution profile returned by the backend (optional)."""

    wall_ms: int = 0
    task_ms: dict[str, int] = field(default_factory=dict)
    task_count: int = 0
    cost_usd: float = 0.0


@dataclass
class BackendResult:
    """Normalised result from any backend."""

    status: str  # "completed", "partial", "failed"
    agent_results: dict[str, dict[str, Any]] = field(default_factory=dict)
    error: str | None = None
    profile: CrewProfile | None = None


class CrewBackend(ABC):
    """Interface every execution backend must implement."""

    @abstractmethod
    async def execute_crew(
        self,
        crew_config: dict[str, Any],
        session_id: str,
        crew_id: str,
        task_id: str,
    ) -> BackendResult:
        """Run a crew and return aggregated results."""

    @abstractmethod
    async def get_crew_status(self, crew_id: str) -> dict[str, Any]:
        """Retrieve current status of a running crew."""

    @abstractmethod
    async def stream_crew(self, crew_id: str) -> AsyncIterator[dict[str, Any]]:
        """Yield SSE-style events for a running crew."""

    @abstractmethod
    async def cancel_crew(self, crew_id: str) -> dict[str, Any]:
        """Cancel a running crew."""
