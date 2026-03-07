"""
YEOMAN A2A Client.

Bidirectional A2A communication with SecureYeoman. Allows AGNOSTIC to:
- Delegate tasks to YEOMAN
- Query YEOMAN task status and results
- Receive YEOMAN task completion notifications

Configure via:
- YEOMAN_A2A_ENABLED: Enable A2A client (default: false)
- YEOMAN_A2A_URL: YEOMAN's A2A endpoint (default: http://localhost:3001)
- YEOMAN_A2A_API_KEY: API key for YEOMAN
- YEOMAN_PEER_ID: YEOMAN's peer ID (default: secureyeoman)
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from collections import OrderedDict
from typing import Any

logger = logging.getLogger(__name__)

try:
    import httpx

    _HTTPX_AVAILABLE = True
except ImportError:  # pragma: no cover
    httpx = None  # type: ignore[assignment]
    _HTTPX_AVAILABLE = False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_AGNOSTIC_PEER_ID = "agnostic-qa"
_DEFAULT_YEOMAN_URL = "http://localhost:3001"
_DEFAULT_YEOMAN_PEER_ID = "secureyeoman"
_REQUEST_TIMEOUT = 15.0  # seconds
_RESULT_CACHE_MAX_SIZE = 500


class YeomanA2AClient:
    """Client for bidirectional A2A communication with SecureYeoman."""

    def __init__(self) -> None:
        self.enabled: bool = os.getenv("YEOMAN_A2A_ENABLED", "false").lower() in (
            "true",
            "1",
            "yes",
        )
        self.base_url: str = os.getenv("YEOMAN_A2A_URL", _DEFAULT_YEOMAN_URL).rstrip(
            "/"
        )
        self.api_key: str | None = os.getenv("YEOMAN_A2A_API_KEY")
        self.peer_id: str = _AGNOSTIC_PEER_ID
        self.yeoman_peer_id: str = os.getenv("YEOMAN_PEER_ID", _DEFAULT_YEOMAN_PEER_ID)

        # Circuit breaker to avoid hammering an unavailable YEOMAN instance.
        try:
            from shared.resilience import CircuitBreaker

            def _on_breaker_change(name: str, old: str, new: str) -> None:
                if new == "closed":
                    logger.info("YEOMAN A2A circuit breaker recovered (was %s)", old)
                elif new == "open":
                    logger.warning("YEOMAN A2A circuit breaker tripped OPEN")

            self._breaker: Any = CircuitBreaker(
                name="yeoman_a2a",
                failure_threshold=5,
                recovery_timeout=60.0,
                on_state_change=_on_breaker_change,
            )
        except ImportError:
            self._breaker = None

        # Bounded result cache for task results received via A2A (LRU eviction).
        self._results_cache: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._cache_max_size: int = _RESULT_CACHE_MAX_SIZE

        # Lazily-created httpx client.
        self._client: httpx.AsyncClient | None = None  # type: ignore[name-defined]

    # ------------------------------------------------------------------
    # httpx client lifecycle
    # ------------------------------------------------------------------

    def _get_client(self) -> httpx.AsyncClient:  # type: ignore[name-defined]
        """Return (and lazily create) the shared httpx client."""
        if not _HTTPX_AVAILABLE:
            raise RuntimeError(
                "httpx is not installed. Install it with: pip install httpx"
            )
        if self._client is None or self._client.is_closed:
            headers: dict[str, str] = {"Content-Type": "application/json"}
            if self.api_key:
                headers["X-API-Key"] = self.api_key
            self._client = httpx.AsyncClient(
                timeout=_REQUEST_TIMEOUT,
                headers=headers,
            )
        return self._client

    async def close(self) -> None:
        """Close the underlying httpx client."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    # Message building
    # ------------------------------------------------------------------

    def _build_message(self, msg_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Build an A2A-protocol envelope."""
        return {
            "id": uuid.uuid4().hex,
            "type": msg_type,
            "fromPeerId": self.peer_id,
            "toPeerId": self.yeoman_peer_id,
            "payload": payload,
            "timestamp": int(time.time() * 1000),
        }

    # ------------------------------------------------------------------
    # Low-level transport
    # ------------------------------------------------------------------

    async def send_message(
        self, msg_type: str, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        """POST an A2A message to YEOMAN's receive endpoint.

        Returns the parsed JSON response on success, or *None* on failure.
        """
        if not self.enabled:
            logger.debug("YEOMAN A2A client is disabled; skipping send_message")
            return None

        if self._breaker and not self._breaker.can_execute():
            logger.warning("YEOMAN A2A circuit breaker is OPEN; skipping request")
            return None

        message = self._build_message(msg_type, payload)
        url = f"{self.base_url}/api/v1/a2a/receive"

        try:
            client = self._get_client()
            response = await client.post(url, json=message)
            response.raise_for_status()
            if self._breaker:
                self._breaker.record_success()
            return response.json()  # type: ignore[no-any-return]
        except Exception as exc:
            if self._breaker:
                self._breaker.record_failure()
            logger.error(
                "Failed to send A2A message (type=%s) to %s: %s",
                msg_type,
                url,
                exc,
            )
            return None

    # ------------------------------------------------------------------
    # High-level operations
    # ------------------------------------------------------------------

    async def delegate_task(
        self,
        task_description: str,
        task_type: str = "qa",
        params: dict[str, Any] | None = None,
    ) -> str | None:
        """Delegate a task to YEOMAN via ``a2a:delegate``.

        Returns the YEOMAN-assigned *task_id* on success, or *None*.
        """
        payload: dict[str, Any] = {
            "description": task_description,
            "task_type": task_type,
        }
        if params:
            payload["params"] = params

        result = await self.send_message("a2a:delegate", payload)
        if result is None:
            return None
        return result.get("task_id")  # type: ignore[return-value]

    async def query_task_status(self, task_id: str) -> dict[str, Any] | None:
        """Query YEOMAN for the current status of *task_id*."""
        return await self.send_message("a2a:status_query", {"task_id": task_id})

    async def query_task_result(self, task_id: str) -> dict[str, Any] | None:
        """Query YEOMAN for the completed result of *task_id*."""
        result = await self.send_message("a2a:result_query", {"task_id": task_id})
        if result is not None:
            self.cache_result(task_id, result)
        return result

    async def query_capabilities(self) -> list[dict[str, Any]]:
        """GET YEOMAN's advertised A2A capabilities."""
        if not self.enabled:
            logger.debug("YEOMAN A2A client is disabled; skipping query_capabilities")
            return []

        if self._breaker and not self._breaker.can_execute():
            logger.warning("YEOMAN A2A circuit breaker is OPEN; skipping request")
            return []

        url = f"{self.base_url}/api/v1/a2a/capabilities"
        try:
            client = self._get_client()
            response = await client.get(url)
            response.raise_for_status()
            if self._breaker:
                self._breaker.record_success()
            data = response.json()
            return data.get("capabilities", [])  # type: ignore[no-any-return]
        except Exception as exc:
            if self._breaker:
                self._breaker.record_failure()
            logger.error("Failed to query YEOMAN capabilities at %s: %s", url, exc)
            return []

    async def send_heartbeat(self) -> bool:
        """Send an ``a2a:heartbeat`` to YEOMAN. Returns *True* on success."""
        result = await self.send_message("a2a:heartbeat", {"status": "healthy"})
        return result is not None

    async def delegate_batch(
        self,
        tasks: list[dict[str, Any]],
    ) -> list[str | None]:
        """Delegate multiple tasks in a single A2A message.

        Each entry in *tasks* should have ``description`` and optionally
        ``task_type`` and ``params``.  Returns a list of task IDs (or ``None``
        for any that failed).
        """
        result = await self.send_message("a2a:delegate_batch", {"tasks": tasks})
        if result is None:
            return [None] * len(tasks)
        return result.get("task_ids", [None] * len(tasks))  # type: ignore[return-value]

    async def query_batch_status(
        self, task_ids: list[str]
    ) -> dict[str, dict[str, Any] | None]:
        """Query status for multiple tasks in a single round-trip.

        Returns a mapping of ``task_id`` → status dict (or ``None`` if the
        task was not found on the YEOMAN side).
        """
        result = await self.send_message(
            "a2a:status_query_batch", {"task_ids": task_ids}
        )
        if result is None:
            return dict.fromkeys(task_ids)
        return result.get("statuses", {})  # type: ignore[return-value]

    async def send_result(self, task_id: str, result: dict[str, Any]) -> bool:
        """Send an ``a2a:result`` back to YEOMAN with completed QA results."""
        payload: dict[str, Any] = {
            "task_id": task_id,
            "result": result,
        }
        response = await self.send_message("a2a:result", payload)
        return response is not None

    # ------------------------------------------------------------------
    # Result cache
    # ------------------------------------------------------------------

    def cache_result(self, task_id: str, result: dict[str, Any]) -> None:
        """Store a YEOMAN task result in the bounded LRU cache."""
        # Move to end if already present (LRU touch)
        if task_id in self._results_cache:
            self._results_cache.move_to_end(task_id)
        self._results_cache[task_id] = result
        # Evict oldest entries when cache exceeds max size
        while len(self._results_cache) > self._cache_max_size:
            self._results_cache.popitem(last=False)

    def get_cached_result(self, task_id: str) -> dict[str, Any] | None:
        """Retrieve a cached result by *task_id*, or *None*."""
        result = self._results_cache.get(task_id)
        if result is not None:
            self._results_cache.move_to_end(task_id)  # LRU touch
        return result

    def get_all_cached_results(self) -> dict[str, dict[str, Any]]:
        """Return a shallow copy of all cached results."""
        return dict(self._results_cache)

    def clear_cache(self) -> None:
        """Clear the result cache."""
        self._results_cache.clear()


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

yeoman_a2a_client = YeomanA2AClient()
