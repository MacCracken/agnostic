"""Audit forwarding to SecureYeoman's cryptographic audit trail.

Forwards crew action logs (creation, completion, failure, cancellation,
GPU allocation, agent execution) to SecureYeoman's audit endpoint so that
all Agnostic actions are included in SY's tamper-evident audit chain.

Environment variables
---------------------
YEOMAN_AUDIT_ENABLED
    Enable audit forwarding. Default ``false``.
YEOMAN_AUDIT_URL
    SecureYeoman audit endpoint. Default ``http://localhost:18789/api/v1/audit/ingest``.
YEOMAN_AUDIT_API_KEY
    API key for the audit endpoint.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

_AUDIT_ENABLED = os.getenv("YEOMAN_AUDIT_ENABLED", "false").lower() in (
    "true",
    "1",
    "yes",
)
_AUDIT_URL = os.getenv("YEOMAN_AUDIT_URL", "http://localhost:18789/api/v1/audit/ingest")
_AUDIT_API_KEY = os.getenv("YEOMAN_AUDIT_API_KEY", "")

# Buffer audit entries and flush in batches
_buffer: list[dict[str, Any]] = []
_BUFFER_MAX = 50


async def forward_crew_event(
    event_type: str,
    crew_id: str,
    *,
    actor: str | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    """Forward a crew lifecycle event to SY's audit trail.

    Event types: ``crew_created``, ``crew_completed``, ``crew_failed``,
    ``crew_cancelled``, ``agent_executed``, ``gpu_allocated``,
    ``gpu_released``, ``definition_changed``, ``tool_uploaded``.
    """
    if not _AUDIT_ENABLED:
        return

    entry = {
        "source": "agnostic",
        "event_type": event_type,
        "resource_type": "crew",
        "resource_id": crew_id,
        "actor": actor or "system",
        "timestamp": datetime.now(UTC).isoformat(),
        "detail": detail or {},
    }

    _buffer.append(entry)

    if len(_buffer) >= _BUFFER_MAX:
        await flush()


async def flush() -> None:
    """Flush buffered audit entries to SecureYeoman."""
    if not _buffer:
        return

    entries = list(_buffer)
    _buffer.clear()

    try:
        import httpx
    except ImportError:
        logger.debug("httpx not available — audit flush skipped")
        return

    headers: dict[str, str] = {"Content-Type": "application/json"}
    if _AUDIT_API_KEY:
        headers["X-API-Key"] = _AUDIT_API_KEY

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                _AUDIT_URL,
                json={"entries": entries},
                headers=headers,
            )

        if resp.status_code != 200:
            logger.warning(
                "Audit forward returned %d — %d entries may be lost",
                resp.status_code,
                len(entries),
            )
        else:
            logger.debug("Forwarded %d audit entries to SecureYeoman", len(entries))

    except Exception as exc:
        logger.warning("Audit forward failed: %s — %d entries lost", exc, len(entries))


def is_enabled() -> bool:
    """Whether audit forwarding is enabled."""
    return _AUDIT_ENABLED
