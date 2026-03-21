"""CrewAI backend — delegates to the existing Python execution path.

This wraps the existing _build_agents_sync / _try_fleet_execution /
_run_local / _aggregate_and_finalize pipeline so that the backend
abstraction can coexist without disrupting the proven code path.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncIterator

from agents.backend.base import BackendResult, CrewBackend

logger = logging.getLogger(__name__)


class CrewAIBackend(CrewBackend):
    """Execute crews using the local Python/CrewAI engine."""

    async def execute_crew(
        self,
        crew_config: dict[str, Any],
        session_id: str,
        crew_id: str,
        task_id: str,
    ) -> BackendResult:
        # Import inline to avoid circular deps at module load time.
        from webgui.routes.crews import (
            _build_agents_sync,
            _build_task_data,
            _run_local,
            _try_fleet_execution,
        )

        loop = asyncio.get_running_loop()
        agents = await loop.run_in_executor(None, _build_agents_sync, crew_config)

        if not agents:
            return BackendResult(status="failed", error="No agents could be created")

        task_data = _build_task_data(session_id, crew_id, crew_config)

        # Dummy status updater — the caller manages Redis status.
        async def _noop_status(status: str, result: dict | None = None) -> dict:
            return {}

        fleet_result = await _try_fleet_execution(
            crew_id, agents, task_data, crew_config, _noop_status
        )

        if fleet_result is not None:
            results, _ = fleet_result
        else:
            results, _ = await _run_local(
                crew_id, agents, task_data, crew_config, _noop_status
            )

        all_ok = all(r.get("status") == "completed" for r in results.values())
        return BackendResult(
            status="completed" if all_ok else "partial",
            agent_results=results,
        )

    async def get_crew_status(self, crew_id: str) -> dict[str, Any]:
        # Local CrewAI crews are tracked in Redis by the route handler.
        return {"error": "Use Redis directly for CrewAI crew status"}

    async def stream_crew(self, crew_id: str) -> AsyncIterator[dict[str, Any]]:
        # No SSE for CrewAI backend; the Chainlit websocket serves this role.
        yield {"event_type": "not_supported", "message": "SSE not available for crewai backend"}

    async def cancel_crew(self, crew_id: str) -> dict[str, Any]:
        return {"error": "Cancel not implemented for crewai backend"}
