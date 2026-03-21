"""Fleet shim — delegates fleet operations to the AgnosAI Rust server.

When ``AGNOSTIC_BACKEND=agnosai``, fleet coordination (node registry,
placement, relay, state) is handled by AgnosAI's fleet module.  This
shim translates the Python-side fleet interfaces into HTTP calls.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx

from config.fleet.node import FleetNode, NodeCapabilities

logger = logging.getLogger(__name__)

_AGNOSAI_URL = os.getenv("AGNOSAI_URL", "http://localhost:8080")
_AGNOSAI_API_KEY = os.getenv("AGNOSAI_API_KEY", "")
_TIMEOUT = 30.0


def _headers() -> dict[str, str]:
    h: dict[str, str] = {"Content-Type": "application/json"}
    if _AGNOSAI_API_KEY:
        h["Authorization"] = f"Bearer {_AGNOSAI_API_KEY}"
    return h


class FleetShim:
    """Thin HTTP client that delegates fleet operations to AgnosAI."""

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or _AGNOSAI_URL).rstrip("/")

    async def get_alive_nodes(self) -> list[FleetNode]:
        """Fetch alive nodes from AgnosAI fleet registry."""
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            try:
                resp = await client.get(
                    f"{self.base_url}/api/v1/fleet/nodes",
                    headers=_headers(),
                )
                resp.raise_for_status()
                data = resp.json()
                return [FleetNode.from_dict(n) for n in data]
            except Exception as exc:
                logger.warning("Fleet shim: failed to fetch nodes: %s", exc)
                return []

    async def plan_and_distribute(
        self,
        agent_definitions: list[dict[str, Any]],
        task_data: dict[str, Any],
        *,
        policy: str = "gpu-affinity",
        group: str | None = None,
    ) -> dict[str, Any]:
        """Request placement from AgnosAI fleet coordinator."""
        payload = {
            "agents": agent_definitions,
            "task_data": task_data,
            "policy": policy,
            "group": group,
        }
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            try:
                resp = await client.post(
                    f"{self.base_url}/api/v1/fleet/place",
                    json=payload,
                    headers=_headers(),
                )
                resp.raise_for_status()
                return resp.json()
            except Exception as exc:
                logger.error("Fleet shim: placement failed: %s", exc)
                return {"has_errors": True, "errors": [str(exc)]}

    async def collect_results(
        self,
        crew_id: str,
        timeout: float = 600.0,
    ) -> dict[str, dict[str, Any]]:
        """Poll AgnosAI for crew results."""
        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                resp = await client.get(
                    f"{self.base_url}/api/v1/crews/{crew_id}",
                    headers=_headers(),
                )
                resp.raise_for_status()
                data = resp.json()
                results: dict[str, dict[str, Any]] = {}
                for r in data.get("results", []):
                    results[r.get("task_id", "unknown")] = {
                        "status": r.get("status", "unknown"),
                        "output": r.get("output", ""),
                    }
                return results
            except Exception as exc:
                logger.error("Fleet shim: collect_results failed: %s", exc)
                return {}

    async def submit_result(
        self,
        crew_id: str,
        agent_key: str,
        result: dict[str, Any],
    ) -> None:
        """Submit a local agent result to AgnosAI relay."""
        payload = {
            "crew_id": crew_id,
            "agent_key": agent_key,
            "result": result,
        }
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            try:
                resp = await client.post(
                    f"{self.base_url}/api/v1/fleet/results",
                    json=payload,
                    headers=_headers(),
                )
                resp.raise_for_status()
            except Exception as exc:
                logger.error("Fleet shim: submit_result failed: %s", exc)


# Module-level singleton.
fleet_shim = FleetShim()
