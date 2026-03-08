"""
AGNOS Audit Chain Forwarder.

Forwards AGNOSTIC audit events to the AGNOS cryptographic audit chain.
Events are batched and sent asynchronously to avoid blocking the local
audit_log() call. Falls back gracefully when AGNOS is unreachable.

Configure via:
- AGNOS_AUDIT_ENABLED: Enable forwarding (default: false)
- AGNOS_AUDIT_URL: AGNOS audit endpoint base URL
- AGNOS_AUDIT_API_KEY: API key for AGNOS audit chain
- AGNOS_AUDIT_BATCH_SIZE: Max events per batch (default: 50)
- AGNOS_AUDIT_FLUSH_INTERVAL: Seconds between flushes (default: 5)
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


class AgnosAuditForwarder:
    """Batched, async forwarder for AGNOS cryptographic audit chain."""

    _MAX_BUFFER_SIZE = 10_000  # Hard cap to prevent unbounded memory growth

    def __init__(self) -> None:
        self.enabled = (
            os.getenv("AGNOS_AUDIT_ENABLED", "false").lower() == "true"
            and _HTTPX_AVAILABLE
        )
        self.base_url = os.getenv("AGNOS_AUDIT_URL", "http://localhost:8090")
        self.api_key = os.getenv("AGNOS_AUDIT_API_KEY", "")
        self.batch_size = int(os.getenv("AGNOS_AUDIT_BATCH_SIZE", "50"))
        self.flush_interval = float(os.getenv("AGNOS_AUDIT_FLUSH_INTERVAL", "5"))

        self._buffer: list[dict[str, Any]] = []
        self._flush_task: asyncio.Task | None = None
        self._client: httpx.AsyncClient | None = None

        # Circuit breaker
        try:
            from shared.resilience import CircuitBreaker

            self._circuit = CircuitBreaker(
                name="agnos_audit", failure_threshold=5, recovery_timeout=60.0
            )
        except ImportError:
            self._circuit = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={"X-API-Key": self.api_key},
                timeout=5.0,
            )
        return self._client

    def queue_event(self, event: dict[str, Any]) -> None:
        """Queue an audit event for batched forwarding (fire-and-forget)."""
        if not self.enabled:
            return

        # Enforce hard cap on buffer size to prevent unbounded memory growth
        if len(self._buffer) >= self._MAX_BUFFER_SIZE:
            dropped = max(
                1, len(self._buffer) - self._MAX_BUFFER_SIZE + self.batch_size
            )
            self._buffer = self._buffer[dropped:]
            logger.warning(
                "AGNOS audit buffer exceeded %d entries, dropped %d oldest events",
                self._MAX_BUFFER_SIZE,
                dropped,
            )

        self._buffer.append(event)

        if len(self._buffer) >= self.batch_size:
            self._schedule_flush()
        elif self._flush_task is None or self._flush_task.done():
            self._schedule_flush()

    def _schedule_flush(self) -> None:
        """Schedule a flush on the running event loop (best-effort)."""
        try:
            loop = asyncio.get_running_loop()
            if self._flush_task is None or self._flush_task.done():
                self._flush_task = loop.create_task(self._delayed_flush())
        except RuntimeError:
            # No running loop — events will accumulate until an async
            # context calls flush() or queue_event() with a running loop.
            logger.debug(
                "AGNOS audit: no running event loop, deferring flush (buffer size: %d)",
                len(self._buffer),
            )

    async def _delayed_flush(self) -> None:
        """Wait up to flush_interval then send the batch."""
        await asyncio.sleep(self.flush_interval)
        await self.flush()

    async def flush(self) -> None:
        """Send all buffered events to AGNOS."""
        if not self._buffer:
            return

        batch = self._buffer[: self.batch_size]
        self._buffer = self._buffer[self.batch_size :]

        if self._circuit and not self._circuit.can_execute():
            logger.debug("AGNOS audit circuit open, dropping %d events", len(batch))
            return

        try:
            client = self._get_client()
            correlation_id = batch[0].get("correlation_id") if batch else None
            headers: dict[str, str] = {}
            if correlation_id:
                headers["X-Correlation-ID"] = correlation_id

            response = await client.post(
                f"{AGNOS_PATH_PREFIX}/audit/events/batch",
                json={"events": batch},
                headers=headers,
            )
            response.raise_for_status()
            if self._circuit:
                self._circuit.record_success()
            logger.debug("Forwarded %d audit events to AGNOS", len(batch))
        except Exception as exc:
            if self._circuit:
                self._circuit.record_failure()
            logger.debug("Failed to forward audit events to AGNOS: %s", exc)

    async def close(self) -> None:
        """Flush remaining events and close the HTTP client."""
        if self._buffer:
            await self.flush()
        if self._client and not self._client.is_closed:
            await self._client.aclose()


agnos_audit_forwarder = AgnosAuditForwarder()
