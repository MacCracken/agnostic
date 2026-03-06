"""
AGNOS Dashboard Bridge.

Periodically pushes AGNOSTIC agent status, session info, and QA metrics
to the AGNOS unified dashboard API. Enables YEOMAN and other AGNOS agents
to see AGNOSTIC's QA team status without polling AGNOSTIC directly.

Configure via:
- AGNOS_DASHBOARD_BRIDGE_ENABLED: Enable bridge (default: false)
- AGNOS_DASHBOARD_URL: AGNOS dashboard API (default: http://localhost:8090)
- AGNOS_DASHBOARD_API_KEY: API key for dashboard push
- AGNOS_DASHBOARD_PUSH_INTERVAL: Seconds between pushes (default: 30)
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

# Optional httpx import — the bridge degrades gracefully without it.
try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None  # type: ignore[assignment]

# Context-var used by the correlation-ID middleware elsewhere in the app.
_correlation_id_var: ContextVar[str | None] = ContextVar(
    "correlation_id", default=None
)

PROVIDER_ID = "agnostic-qa"


class AgnosDashboardBridge:
    """Pushes AGNOSTIC dashboard snapshots to the AGNOS unified dashboard."""

    def __init__(self) -> None:
        self.enabled = (
            os.getenv("AGNOS_DASHBOARD_BRIDGE_ENABLED", "false").lower() == "true"
        )
        self.base_url = os.getenv(
            "AGNOS_DASHBOARD_URL",
            os.getenv("AGNOS_AGENT_REGISTRY_URL", "http://localhost:8090"),
        )
        self.api_key = os.getenv("AGNOS_DASHBOARD_API_KEY", "")
        self.push_interval = float(
            os.getenv("AGNOS_DASHBOARD_PUSH_INTERVAL", "30")
        )

        self._client: httpx.AsyncClient | None = None
        self._periodic_task: asyncio.Task[None] | None = None

        try:
            from shared.resilience import CircuitBreaker

            self._circuit_breaker: Any = CircuitBreaker(
                name="agnos-dashboard-bridge",
                failure_threshold=5,
                recovery_timeout=60.0,
            )
        except ImportError:
            self._circuit_breaker = None

    # ------------------------------------------------------------------
    # HTTP client (lazy)
    # ------------------------------------------------------------------

    def _get_client(self) -> httpx.AsyncClient:
        """Return (and lazily create) the async HTTP client."""
        if httpx is None:
            raise RuntimeError(
                "httpx is not installed — cannot use AgnosDashboardBridge"
            )
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(10.0),
            )
        return self._client

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        """Build common request headers."""
        headers: dict[str, str] = {}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        cid = _correlation_id_var.get(None)
        if cid:
            headers["X-Correlation-ID"] = cid
        else:
            headers["X-Correlation-ID"] = str(uuid.uuid4())
        return headers

    async def _post(self, path: str, payload: dict[str, Any]) -> bool:
        """POST *payload* to *path* with circuit-breaker protection.

        Returns ``True`` on success, ``False`` on any failure.
        """
        if not self.enabled:
            return False

        if self._circuit_breaker and not self._circuit_breaker.can_execute():
            logger.debug(
                "Dashboard bridge circuit open — skipping push to %s", path
            )
            return False

        try:
            client = self._get_client()
            response = await client.post(
                path,
                json=payload,
                headers=self._headers(),
            )
            response.raise_for_status()
            if self._circuit_breaker:
                self._circuit_breaker.record_success()
            return True
        except Exception:
            if self._circuit_breaker:
                self._circuit_breaker.record_failure()
            logger.warning(
                "Dashboard bridge push failed for %s",
                path,
                exc_info=True,
            )
            return False

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(UTC).isoformat()

    # ------------------------------------------------------------------
    # Public push methods
    # ------------------------------------------------------------------

    async def push_agent_status(self, agents: list[dict[str, Any]]) -> bool:
        """Push all agent statuses in a single batch.

        Args:
            agents: List of agent-info dicts (from DashboardManager or
                AgentMonitor).

        Returns:
            ``True`` if the push succeeded.
        """
        payload: dict[str, Any] = {
            "provider": PROVIDER_ID,
            "timestamp": self._now_iso(),
            "agents": agents,
        }
        return await self._post(
            "/api/v1/dashboard/providers/agnostic-qa/agents",
            payload,
        )

    async def push_session_status(self, sessions: list[dict[str, Any]]) -> bool:
        """Push active session information.

        Args:
            sessions: List of session-info dicts.

        Returns:
            ``True`` if the push succeeded.
        """
        payload: dict[str, Any] = {
            "provider": PROVIDER_ID,
            "timestamp": self._now_iso(),
            "sessions": sessions,
        }
        return await self._post(
            "/api/v1/dashboard/providers/agnostic-qa/sessions",
            payload,
        )

    async def push_metrics(self, metrics: dict[str, Any]) -> bool:
        """Push resource / LLM usage metrics.

        Args:
            metrics: Metrics dict (from DashboardManager.export_dashboard_data).

        Returns:
            ``True`` if the push succeeded.
        """
        payload: dict[str, Any] = {
            "provider": PROVIDER_ID,
            "timestamp": self._now_iso(),
            "metrics": metrics,
        }
        return await self._post(
            "/api/v1/dashboard/providers/agnostic-qa/metrics",
            payload,
        )

    async def push_full_snapshot(self, dashboard_data: dict[str, Any]) -> bool:
        """Convenience method that pushes agents, sessions, and metrics.

        Expects *dashboard_data* in the shape returned by
        ``DashboardManager.export_dashboard_data()``.

        Returns:
            ``True`` if **all three** pushes succeeded.
        """
        agents_ok = await self.push_agent_status(
            dashboard_data.get("agents", [])
        )
        sessions_ok = await self.push_session_status(
            dashboard_data.get("sessions", [])
        )
        metrics_ok = await self.push_metrics(
            dashboard_data.get("metrics", {})
        )
        return agents_ok and sessions_ok and metrics_ok

    # ------------------------------------------------------------------
    # Periodic background push
    # ------------------------------------------------------------------

    async def start_periodic_push(
        self,
        get_dashboard_data: Callable[..., Any],
    ) -> None:
        """Start a background task that pushes dashboard data periodically.

        Args:
            get_dashboard_data: An async (or sync) callable that returns a
                dashboard-data dict compatible with ``push_full_snapshot``.
        """
        if not self.enabled:
            logger.debug("Dashboard bridge disabled — periodic push not started")
            return

        if httpx is None:
            logger.warning(
                "httpx not installed — dashboard bridge periodic push disabled"
            )
            return

        if self._periodic_task is not None and not self._periodic_task.done():
            logger.warning("Periodic push already running — ignoring duplicate start")
            return

        async def _loop() -> None:
            logger.info(
                "AGNOS dashboard bridge started (interval=%ss, url=%s)",
                self.push_interval,
                self.base_url,
            )
            while True:
                try:
                    await asyncio.sleep(self.push_interval)
                    data = get_dashboard_data()
                    if asyncio.iscoroutine(data) or asyncio.isfuture(data):
                        data = await data
                    await self.push_full_snapshot(data)
                except asyncio.CancelledError:
                    logger.info("AGNOS dashboard bridge periodic push cancelled")
                    raise
                except Exception:
                    # Never crash the host application.
                    logger.warning(
                        "Dashboard bridge periodic push error",
                        exc_info=True,
                    )

        self._periodic_task = asyncio.create_task(_loop(), name="agnos-dashboard-bridge")

    async def stop(self) -> None:
        """Cancel the periodic task and close the HTTP client."""
        if self._periodic_task is not None and not self._periodic_task.done():
            self._periodic_task.cancel()
            try:
                await self._periodic_task
            except asyncio.CancelledError:
                pass
            self._periodic_task = None

        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

        logger.info("AGNOS dashboard bridge stopped")


# ------------------------------------------------------------------
# Module-level singleton
# ------------------------------------------------------------------
agnos_dashboard_bridge = AgnosDashboardBridge()
