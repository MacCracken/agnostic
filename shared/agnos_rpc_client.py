"""
AGNOS Daimon RPC Client.

Registers agent methods with daimon's RPC registry and provides a client
for invoking remote methods on other agents via daimon routing.

Configure via:
- AGNOS_RPC_ENABLED: Enable RPC registration and invocation (default: false)
- AGNOS_AGENT_REGISTRY_URL: Daimon base URL (shared with agent registration)
- AGNOS_AGENT_API_KEY: API key for daimon (shared with agent registration)
"""

import asyncio
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

AGNOS_PATH_PREFIX = os.getenv("AGNOS_PATH_PREFIX", "/v1")

try:
    import httpx

    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False


# ---------------------------------------------------------------------------
# RPC method definitions — maps capability names to daimon RPC method names.
# Each agent registers its methods at startup so external agents (e.g.
# SecureYeoman) can discover and invoke QA services via daimon RPC.
# ---------------------------------------------------------------------------

# Map: agent_key → list of RPC method names (namespaced "agnostic.<capability>")
AGENT_RPC_METHODS: dict[str, list[str]] = {
    "qa-manager": [
        "agnostic.test_planning",
        "agnostic.fuzzy_verification",
    ],
    "senior-qa": [
        "agnostic.test_planning",
        "agnostic.edge_case_analysis",
        "agnostic.risk_assessment",
    ],
    "junior-qa": [
        "agnostic.test_execution",
        "agnostic.regression_testing",
        "agnostic.test_data_generation",
    ],
    "qa-analyst": [
        "agnostic.quality_analysis",
        "agnostic.reporting",
    ],
    "security-compliance": [
        "agnostic.security_audit",
        "agnostic.compliance_check",
        "agnostic.vulnerability_scanning",
    ],
    "performance": [
        "agnostic.load_testing",
        "agnostic.performance_profiling",
        "agnostic.chaos_testing",
    ],
}


class AgnosRpcClient:
    """Client for AGNOS daimon RPC registration and invocation."""

    def __init__(self) -> None:
        self.enabled = (
            os.getenv("AGNOS_RPC_ENABLED", "false").lower() == "true"
            and _HTTPX_AVAILABLE
        )
        self.base_url = os.getenv(
            "AGNOS_AGENT_REGISTRY_URL", "http://localhost:8090"
        )
        self.api_key = os.getenv("AGNOS_AGENT_API_KEY", "")
        self._client: httpx.AsyncClient | None = None
        self._client_lock = asyncio.Lock()
        self._registered_methods: dict[str, list[str]] = {}

        try:
            from shared.resilience import CircuitBreaker

            self._circuit = CircuitBreaker(
                name="agnos_rpc", failure_threshold=5, recovery_timeout=60.0
            )
        except ImportError:
            self._circuit = None

    async def _get_client(self) -> "httpx.AsyncClient":
        async with self._client_lock:
            if self._client is None or self._client.is_closed:
                self._client = httpx.AsyncClient(
                    base_url=self.base_url,
                    headers={"X-API-Key": self.api_key} if self.api_key else {},
                    timeout=10.0,
                )
        return self._client

    def _can_execute(self) -> bool:
        if not self.enabled:
            return False
        if self._circuit and not self._circuit.can_execute():
            return False
        return True

    def _record_success(self) -> None:
        if self._circuit:
            self._circuit.record_success()

    def _record_failure(self) -> None:
        if self._circuit:
            self._circuit.record_failure()

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    async def register_methods(
        self, agent_daimon_id: str, methods: list[str]
    ) -> dict[str, Any]:
        """Register RPC methods for an agent with daimon.

        Args:
            agent_daimon_id: The daimon UUID for the agent (from registration).
            methods: List of method names to register (e.g. "agnostic.security_audit").

        Returns:
            Result dict with status and registered method count.
        """
        if not self._can_execute():
            return {"status": "disabled"}

        try:
            client = await self._get_client()
            response = await client.post(
                f"{AGNOS_PATH_PREFIX}/rpc/register",
                json={"agent_id": agent_daimon_id, "methods": methods},
            )
            response.raise_for_status()
            self._record_success()
            self._registered_methods[agent_daimon_id] = methods
            logger.info(
                "Registered %d RPC methods for agent %s: %s",
                len(methods),
                agent_daimon_id,
                methods,
            )
            return {
                "status": "registered",
                "agent_id": agent_daimon_id,
                "methods": methods,
                "count": len(methods),
            }
        except Exception as exc:
            self._record_failure()
            logger.warning(
                "Failed to register RPC methods for %s: %s",
                agent_daimon_id,
                exc,
            )
            return {"status": "error", "message": str(exc)}

    async def register_all_agent_methods(
        self, registered_agents: dict[str, Any]
    ) -> dict[str, Any]:
        """Register RPC methods for all agents that have daimon IDs.

        Args:
            registered_agents: Dict of agent_key → daimon_id from
                AgentRegistryClient._registered_agents.

        Returns:
            Result dict keyed by agent_key with registration results.
        """
        if not self._can_execute():
            return {"status": "disabled"}

        import asyncio

        eligible = [
            (agent_key, daimon_id)
            for agent_key, daimon_id in registered_agents.items()
            if daimon_id and AGENT_RPC_METHODS.get(agent_key)
        ]
        if not eligible:
            return {}
        keys, ids = zip(*eligible, strict=False)
        method_lists = [AGENT_RPC_METHODS[k] for k in keys]
        gathered = await asyncio.gather(
            *[self.register_methods(did, methods) for did, methods in zip(ids, method_lists, strict=False)]
        )
        results: dict[str, Any] = dict(zip(keys, gathered, strict=False))

        total = sum(
            r.get("count", 0) for r in results.values() if r.get("status") == "registered"
        )
        logger.info("Registered %d total RPC methods across %d agents", total, len(results))
        return results

    async def deregister_all_methods(self) -> None:
        """Clear local tracking of registered methods.

        Daimon automatically deregisters methods when an agent is
        deregistered, so this only clears local state.
        """
        self._registered_methods.clear()
        logger.info("Cleared local RPC method registrations")

    # ------------------------------------------------------------------
    # Invocation — call remote methods via daimon routing
    # ------------------------------------------------------------------

    async def call(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        timeout_ms: int = 30000,
        sender_id: str | None = None,
    ) -> dict[str, Any]:
        """Invoke an RPC method on a remote agent via daimon routing.

        Args:
            method: Fully qualified method name (e.g. "secureyeoman.scan").
            params: Parameters to pass to the remote method.
            timeout_ms: Timeout in milliseconds (default 30s for QA tasks).
            sender_id: Optional sender agent identifier for tracking.

        Returns:
            Response dict from daimon with routing result or error.
        """
        if not self._can_execute():
            return {"status": "disabled"}

        payload: dict[str, Any] = {
            "method": method,
            "params": params or {},
            "timeout_ms": timeout_ms,
        }
        if sender_id:
            payload["sender_id"] = sender_id

        try:
            client = await self._get_client()
            response = await client.post(
                f"{AGNOS_PATH_PREFIX}/rpc/call",
                json=payload,
            )
            response.raise_for_status()
            self._record_success()
            result = response.json()
            logger.debug("RPC call %s returned: %s", method, result.get("status"))
            return result
        except Exception as exc:
            self._record_failure()
            logger.warning("RPC call to %s failed: %s", method, exc)
            return {"status": "error", "message": str(exc)}

    # ------------------------------------------------------------------
    # Discovery — list available remote methods
    # ------------------------------------------------------------------

    async def list_methods(
        self, agent_id: str | None = None
    ) -> list[str]:
        """List RPC methods registered with daimon.

        Args:
            agent_id: Optional daimon agent UUID to filter by. If None,
                returns all methods across all agents.

        Returns:
            List of method names, or empty list on failure.
        """
        if not self._can_execute():
            return []

        try:
            client = await self._get_client()
            path = f"{AGNOS_PATH_PREFIX}/rpc/methods"
            if agent_id:
                path = f"{path}/{agent_id}"
            response = await client.get(path)
            response.raise_for_status()
            self._record_success()
            data = response.json()
            return data.get("methods", [])
        except Exception as exc:
            self._record_failure()
            logger.debug("Failed to list RPC methods: %s", exc)
            return []

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()


agnos_rpc = AgnosRpcClient()
