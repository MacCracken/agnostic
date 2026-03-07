"""
YEOMAN Outbound Event Push Client.

Pushes QA events to SecureYeoman's webhook subscription endpoint so that
YEOMAN receives real-time notifications without polling.

This is the outbound side of the bidirectional event streaming.
The inbound side is the SSE endpoint in ``webgui/routes/yeoman_webhooks.py``.

Configure via:
- YEOMAN_EVENT_PUSH_ENABLED: Enable outbound event push (default: false)
- YEOMAN_EVENT_PUSH_URL: SecureYeoman webhook URL
- YEOMAN_EVENT_PUSH_SECRET: HMAC secret for signing outbound events
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

try:
    import httpx

    _HTTPX_AVAILABLE = True
except ImportError:  # pragma: no cover
    httpx = None  # type: ignore[assignment]
    _HTTPX_AVAILABLE = False

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_ENABLED = os.getenv("YEOMAN_EVENT_PUSH_ENABLED", "false").lower() in (
    "true",
    "1",
    "yes",
)
_PUSH_URL = os.getenv("YEOMAN_EVENT_PUSH_URL", "").rstrip("/")
_PUSH_SECRET = os.getenv("YEOMAN_EVENT_PUSH_SECRET", "")
_REQUEST_TIMEOUT = 10.0
_MAX_RETRIES = 3
_BATCH_SIZE = 20
_FLUSH_INTERVAL = 2.0  # seconds


class YeomanEventPushClient:
    """Batched, async event push to SecureYeoman."""

    def __init__(self) -> None:
        self.enabled = _ENABLED and bool(_PUSH_URL)
        self.push_url = _PUSH_URL
        self.secret = _PUSH_SECRET
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=5000)
        self._client: httpx.AsyncClient | None = None  # type: ignore[name-defined]
        self._flush_task: asyncio.Task[None] | None = None

    def _get_client(self) -> httpx.AsyncClient:  # type: ignore[name-defined]
        if not _HTTPX_AVAILABLE:
            raise RuntimeError("httpx is not installed")
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=_REQUEST_TIMEOUT)
        return self._client

    async def start(self) -> None:
        """Start the background flush loop."""
        if not self.enabled:
            logger.debug("YEOMAN event push disabled")
            return
        if self._flush_task is None:
            self._flush_task = asyncio.create_task(self._flush_loop())
            logger.info("YEOMAN event push client started (url=%s)", self.push_url)

    async def stop(self) -> None:
        """Stop the flush loop and drain remaining events."""
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
            self._flush_task = None
        # Final flush
        await self._flush_batch()
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    def push_event(
        self,
        event_type: str,
        data: dict[str, Any],
        task_id: str | None = None,
        session_id: str | None = None,
    ) -> None:
        """Queue an event for delivery to SecureYeoman.

        Non-blocking: drops events if the queue is full.
        """
        if not self.enabled:
            return

        event = {
            "event": event_type,
            "timestamp": int(time.time() * 1000),
            "data": data,
            "source": "agnostic-qa",
        }
        if task_id:
            event["task_id"] = task_id
        if session_id:
            event["session_id"] = session_id

        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning(
                "YEOMAN event push queue full; dropping event: %s", event_type
            )

    async def _flush_loop(self) -> None:
        """Background loop that flushes events in batches."""
        while True:
            try:
                await asyncio.sleep(_FLUSH_INTERVAL)
                await self._flush_batch()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("YEOMAN event push flush error: %s", exc)

    async def _flush_batch(self) -> None:
        """Send queued events to SecureYeoman."""
        if self._queue.empty():
            return

        batch: list[dict[str, Any]] = []
        while not self._queue.empty() and len(batch) < _BATCH_SIZE:
            try:
                batch.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break

        if not batch:
            return

        body = json.dumps({"events": batch})
        headers: dict[str, str] = {"Content-Type": "application/json"}

        if self.secret:
            sig = hmac.new(
                self.secret.encode(), body.encode(), hashlib.sha256
            ).hexdigest()
            headers["X-Webhook-Signature"] = f"sha256={sig}"

        for attempt in range(_MAX_RETRIES):
            try:
                client = self._get_client()
                resp = await client.post(self.push_url, content=body, headers=headers)
                resp.raise_for_status()
                logger.debug(
                    "Pushed %d events to YEOMAN (%s)", len(batch), self.push_url
                )
                return
            except Exception as exc:
                if attempt < _MAX_RETRIES - 1:
                    await asyncio.sleep(2**attempt)
                else:
                    logger.error(
                        "Failed to push %d events to YEOMAN after %d attempts: %s",
                        len(batch),
                        _MAX_RETRIES,
                        exc,
                    )


# Module-level singleton
yeoman_event_push = YeomanEventPushClient()
