"""AgnosAI backend — delegates crew execution to the Rust server via HTTP."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import AsyncIterator
from typing import Any

import httpx

from agents.backend.base import BackendResult, CrewBackend

logger = logging.getLogger(__name__)

# Default timeout for crew execution (10 min).
_EXECUTE_TIMEOUT = float(os.getenv("AGNOSAI_EXECUTE_TIMEOUT", "600"))


def _translate_crew_config(crew_config: dict[str, Any]) -> dict[str, Any]:
    """Translate an Agnostic crew_config dict into an AgnosAI CrewRunRequest."""
    agents = []
    raw_agents = crew_config.get("agents") or crew_config.get("agent_definitions") or []
    for member in raw_agents:
        agent: dict[str, Any] = {
            "agent_key": member.get("agent_key", member.get("role", "agent")),
            "name": member.get("name", member.get("role", "Agent")),
            "role": member.get("role", ""),
            "goal": member.get("goal", ""),
        }
        # Optional scalar/string fields — only include if present.
        for key in ("backstory", "domain", "tools", "complexity", "llm_model"):
            if member.get(key):
                agent[key] = member[key]
        # Modern hardware requirements — prefer over legacy fields.
        if member.get("hardware"):
            agent["hardware"] = member["hardware"]
        else:
            for key in ("gpu_required", "gpu_preferred"):
                if member.get(key):
                    agent[key] = member[key]
            if member.get("gpu_memory_min_mb"):
                agent["gpu_memory_min_mb"] = member["gpu_memory_min_mb"]
        # Personality profile (bhava).
        if member.get("personality"):
            agent["personality"] = member["personality"]
        agents.append(agent)

    # Build tasks from the crew_config description.
    tasks = []
    if crew_config.get("tasks"):
        for t in crew_config["tasks"]:
            task: dict[str, Any] = {"description": t.get("description", "")}
            if t.get("expected_output"):
                task["expected_output"] = t["expected_output"]
            if t.get("dependencies"):
                task["dependencies"] = t["dependencies"]
            if t.get("priority"):
                task["priority"] = t["priority"]
            tasks.append(task)
    else:
        # Single-task fallback from title/description.
        tasks.append(
            {
                "description": crew_config.get(
                    "description", crew_config.get("title", "Execute crew")
                ),
            }
        )

    process = crew_config.get("process", "sequential")

    return {
        "name": crew_config.get("title", crew_config.get("name", "crew")),
        "agents": agents,
        "tasks": tasks,
        "process": process,
    }


class AgnosAIBackend(CrewBackend):
    """Execute crews on the AgnosAI Rust server."""

    def __init__(self, base_url: str, api_key: str = "") -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    async def execute_crew(
        self,
        crew_config: dict[str, Any],
        session_id: str,
        crew_id: str,
        task_id: str,
    ) -> BackendResult:
        payload = _translate_crew_config(crew_config)

        async with httpx.AsyncClient(timeout=_EXECUTE_TIMEOUT) as client:
            try:
                resp = await client.post(
                    f"{self.base_url}/api/v1/crews",
                    json=payload,
                    headers=self._headers(),
                )
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                body = exc.response.text
                logger.error(
                    "AgnosAI crew creation failed (%s): %s",
                    exc.response.status_code,
                    body,
                )
                return BackendResult(
                    status="failed",
                    error=f"AgnosAI HTTP {exc.response.status_code}: {body}",
                )
            except httpx.RequestError as exc:
                logger.error("AgnosAI unreachable: %s", exc)
                return BackendResult(
                    status="failed", error=f"AgnosAI unreachable: {exc}"
                )

        data = resp.json()

        # Translate AgnosAI response to BackendResult.
        agent_results: dict[str, dict[str, Any]] = {}
        for result in data.get("results", []):
            key = result.get("task_id", "unknown")
            agent_results[key] = {
                "status": result.get("status", "unknown"),
                "output": result.get("output", ""),
            }

        # Extract execution profile (0.21.3+).
        profile: CrewProfile | None = None
        raw_profile = data.get("profile")
        if raw_profile and isinstance(raw_profile, dict):
            profile = CrewProfile(
                wall_ms=raw_profile.get("wall_ms", 0),
                task_ms=raw_profile.get("task_ms", {}),
                task_count=raw_profile.get("task_count", 0),
                cost_usd=raw_profile.get("cost_usd", 0.0),
            )

        return BackendResult(
            status=data.get("status", "unknown"),
            agent_results=agent_results,
            profile=profile,
        )

    async def get_crew_status(self, crew_id: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self.base_url}/api/v1/crews/{crew_id}",
                headers=self._headers(),
            )
            return resp.json()

    async def stream_crew(self, crew_id: str) -> AsyncIterator[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "GET",
                f"{self.base_url}/api/v1/crews/{crew_id}/stream",
                headers=self._headers(),
            ) as resp:
                event_type = ""
                async for line in resp.aiter_lines():
                    if line.startswith("event: "):
                        event_type = line[7:].strip()
                    elif line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])
                        except json.JSONDecodeError:
                            continue
                        # Inject the SSE event type for downstream consumers.
                        if event_type:
                            data["_sse_event"] = event_type
                        # Skip control events, forward crew events.
                        if event_type == "error":
                            logger.warning(
                                "AgnosAI SSE error for crew %s: %s",
                                crew_id,
                                data.get("data", {}).get("message", data),
                            )
                        elif event_type != "connected":
                            yield data
                        event_type = ""

    async def cancel_crew(self, crew_id: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30) as client:
            try:
                resp = await client.post(
                    f"{self.base_url}/api/v1/crews/{crew_id}/cancel",
                    headers=self._headers(),
                )
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as exc:
                return {
                    "error": f"AgnosAI cancel failed: HTTP {exc.response.status_code}"
                }
            except httpx.RequestError as exc:
                return {"error": f"AgnosAI unreachable: {exc}"}

    # ------------------------------------------------------------------
    # Sync helpers — query AgnosAI's definition/preset/tool registries
    # ------------------------------------------------------------------

    async def list_definitions(self) -> list[dict[str, Any]]:
        """Fetch agent definitions from AgnosAI."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self.base_url}/api/v1/agents/definitions",
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    async def push_definition(self, definition: dict[str, Any]) -> dict[str, Any]:
        """Create an agent definition on AgnosAI."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.base_url}/api/v1/agents/definitions",
                json=definition,
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    async def list_presets(self) -> list[dict[str, Any]]:
        """Fetch built-in presets from AgnosAI."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self.base_url}/api/v1/presets",
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    async def list_tools(self) -> list[dict[str, Any]]:
        """Fetch registered tools from AgnosAI."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self.base_url}/api/v1/tools",
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()
