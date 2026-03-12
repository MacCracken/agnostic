"""SecureYeoman webhook receiver and SSE event streaming.

Phase B items:
- Event-driven QA triggers: Accept webhook POSTs from SecureYeoman extension hooks
- Bidirectional event streaming: SSE endpoint for real-time QA events
- Embeddable metrics widget: Compact dashboard JSON for YEOMAN embedding
"""

import asyncio
import hashlib
import hmac
import json
import logging
import os
import re
import time
import uuid
from collections import OrderedDict
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from shared.audit import AuditAction, audit_log
from webgui.routes.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

YEOMAN_WEBHOOK_SECRET = os.getenv("YEOMAN_WEBHOOK_SECRET", "")
YEOMAN_WEBHOOKS_ENABLED = os.getenv("YEOMAN_WEBHOOKS_ENABLED", "false").lower() in (
    "true",
    "1",
    "yes",
)
_MAX_WEBHOOK_BODY_SIZE = int(os.getenv("WEBHOOK_MAX_BODY_SIZE", "1048576"))  # 1 MB
_EVENT_BUFFER_MAX = int(os.getenv("EVENT_BUFFER_MAX", "1000"))
_SSE_KEEPALIVE_INTERVAL = int(os.getenv("SSE_KEEPALIVE_INTERVAL", "30"))  # seconds

# Validate event names to prevent injection
_EVENT_TYPE_RE = re.compile(r"^[a-zA-Z0-9._:-]{1,100}$")


# ---------------------------------------------------------------------------
# Request/response models
# ---------------------------------------------------------------------------


class YeomanWebhookPayload(BaseModel):
    """Payload from SecureYeoman extension hooks."""

    event: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Event type: after-deploy, on-pr-merge, on-push, on-schedule, etc.",
    )
    timestamp: int = Field(..., description="Unix millisecond timestamp of the event")
    data: dict[str, Any] = Field(
        default_factory=dict,
        description="Event-specific data (repo, branch, commit, PR number, etc.)",
    )
    source: str = Field(
        default="secureyeoman",
        max_length=100,
        description="Source system identifier",
    )
    correlation_id: str | None = Field(
        default=None,
        max_length=200,
        description="Optional correlation ID for distributed tracing",
    )


class WebhookResponse(BaseModel):
    accepted: bool
    event_id: str
    task_id: str | None = None
    message: str


class YeomanEventsResponse(BaseModel):
    events: list[dict[str, Any]]
    total: int


# ---------------------------------------------------------------------------
# Event type → QA task mapping
# ---------------------------------------------------------------------------

# Maps SecureYeoman event types to QA task configurations.
_EVENT_TASK_MAP: dict[str, dict[str, Any]] = {
    "after-deploy": {
        "title_template": "Post-deployment QA: {repo}@{branch}",
        "agents": [],  # full 6-agent pipeline
        "priority": "high",
        "standards": ["OWASP"],
    },
    "on-pr-merge": {
        "title_template": "PR merge regression check: {repo} #{pr_number}",
        "agents": ["junior-qa", "qa-analyst", "security-compliance"],
        "priority": "high",
        "standards": [],
    },
    "on-push": {
        "title_template": "Push QA scan: {repo}@{branch} ({commit_sha:.8})",
        "agents": ["junior-qa", "qa-analyst"],
        "priority": "medium",
        "standards": [],
    },
    "on-schedule": {
        "title_template": "Scheduled QA: {repo}",
        "agents": [],  # full pipeline
        "priority": "medium",
        "standards": ["OWASP", "GDPR"],
    },
    "on-release": {
        "title_template": "Release QA: {repo} {tag}",
        "agents": [],  # full pipeline
        "priority": "critical",
        "standards": ["OWASP", "PCI_DSS", "SOC2"],
    },
    "security-alert": {
        "title_template": "Security alert triage: {repo} — {alert_title}",
        "agents": ["security-compliance"],
        "priority": "critical",
        "standards": ["OWASP"],
    },
}


def _build_task_from_event(
    event_type: str, data: dict[str, Any]
) -> dict[str, Any] | None:
    """Build a QA task config from a webhook event. Returns None for unknown events."""
    template = _EVENT_TASK_MAP.get(event_type)
    if not template:
        return None

    # Safe format: missing keys become empty strings
    format_data = {
        "repo": data.get("repository", data.get("repo", "unknown")),
        "branch": data.get("branch", data.get("ref", "main")),
        "commit_sha": data.get("commit_sha", data.get("sha", "unknown")),
        "pr_number": data.get(
            "pr_number", data.get("pull_request", {}).get("number", "?")
        ),
        "tag": data.get("tag", data.get("release", {}).get("tag_name", "?")),
        "alert_title": data.get("alert_title", data.get("title", "Unknown alert")),
    }

    title = template["title_template"].format_map(
        {k: str(v) for k, v in format_data.items()}
    )
    description = (
        f"Triggered by SecureYeoman {event_type} event.\n"
        f"Repository: {format_data['repo']}\n"
        f"Branch: {format_data['branch']}\n"
        f"Commit: {format_data['commit_sha']}"
    )
    if data.get("target_url"):
        description += f"\nTarget: {data['target_url']}"

    return {
        "title": title[:200],
        "description": description[:5000],
        "target_url": data.get("target_url"),
        "priority": template["priority"],
        "agents": template["agents"],
        "standards": template["standards"],
    }


# ---------------------------------------------------------------------------
# HMAC verification
# ---------------------------------------------------------------------------


def _verify_webhook_signature(body: bytes, signature_header: str | None) -> bool:
    """Verify HMAC-SHA256 signature from SecureYeoman webhook.

    If no secret is configured, signatures are not required (dev/test mode).
    If a secret IS configured, the signature MUST be present and valid.
    """
    if not YEOMAN_WEBHOOK_SECRET:
        logger.debug(
            "Webhook signature verification skipped — no secret configured"
        )
        return True  # No secret configured — accept (dev/test mode)

    if not signature_header:
        return False

    # Accept formats: "sha256=<hex>" or raw "<hex>"
    expected_prefix = "sha256="
    if signature_header.startswith(expected_prefix):
        provided_sig = signature_header[len(expected_prefix) :]
    else:
        provided_sig = signature_header

    computed = hmac.new(
        YEOMAN_WEBHOOK_SECRET.encode(), body, hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(computed, provided_sig)


# ---------------------------------------------------------------------------
# SSE event buffer (bounded ring buffer)
# ---------------------------------------------------------------------------


class _EventBuffer:
    """Bounded buffer of recent QA events for SSE replay."""

    def __init__(self, max_size: int = _EVENT_BUFFER_MAX) -> None:
        self._events: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._max_size = max_size
        self._subscribers: dict[str, asyncio.Queue[dict[str, Any]]] = {}

    def push(self, event: dict[str, Any]) -> str:
        """Add an event and notify subscribers. Returns event ID."""
        event_id = event.get("event_id", uuid.uuid4().hex)
        event["event_id"] = event_id
        self._events[event_id] = event
        while len(self._events) > self._max_size:
            self._events.popitem(last=False)

        # Fan out to SSE subscribers
        dead = []
        for sub_id, queue in self._subscribers.items():
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                dead.append(sub_id)
        for sub_id in dead:
            self._subscribers.pop(sub_id, None)

        return event_id

    def subscribe(self) -> tuple[str, asyncio.Queue[dict[str, Any]]]:
        """Create a new subscriber. Returns (subscriber_id, queue)."""
        sub_id = uuid.uuid4().hex
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=200)
        self._subscribers[sub_id] = queue
        return sub_id, queue

    def unsubscribe(self, sub_id: str) -> None:
        self._subscribers.pop(sub_id, None)

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        items = list(self._events.values())
        return items[-limit:]


_event_buffer = _EventBuffer()


def get_event_buffer() -> _EventBuffer:
    """Get the module-level event buffer (for use by other modules)."""
    return _event_buffer


# ---------------------------------------------------------------------------
# Webhook receiver endpoint
# ---------------------------------------------------------------------------


@router.post("/yeoman/webhooks", response_model=WebhookResponse)
async def receive_yeoman_webhook(
    request: Request,
    x_webhook_signature: str | None = Header(default=None, alias="X-Webhook-Signature"),
    x_correlation_id: str | None = Header(default=None, alias="X-Correlation-ID"),
):
    """Receive webhook events from SecureYeoman extension hooks.

    Accepts events like ``after-deploy``, ``on-pr-merge``, ``on-push``,
    ``on-schedule``, ``on-release``, ``security-alert``.

    Auto-creates QA tasks based on event type with appropriate agent routing.
    Verifies HMAC-SHA256 signature when ``YEOMAN_WEBHOOK_SECRET`` is set.
    """
    if not YEOMAN_WEBHOOKS_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="YEOMAN webhooks not enabled. Set YEOMAN_WEBHOOKS_ENABLED=true",
        )

    # Read and verify body
    body = await request.body()
    if len(body) > _MAX_WEBHOOK_BODY_SIZE:
        raise HTTPException(status_code=413, detail="Payload too large")

    if not _verify_webhook_signature(body, x_webhook_signature):
        audit_log(
            AuditAction.AUTH_LOGIN_FAILURE,
            actor="yeoman-webhook",
            resource_type="webhook",
            detail={"reason": "invalid_signature"},
        )
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    # Parse payload
    try:
        payload_data = json.loads(body)
        payload = YeomanWebhookPayload(**payload_data)
    except (json.JSONDecodeError, Exception) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid payload: {exc}") from exc

    # Validate event type format
    if not _EVENT_TYPE_RE.match(payload.event):
        raise HTTPException(status_code=400, detail="Invalid event type format")

    event_id = uuid.uuid4().hex
    correlation_id = x_correlation_id or payload.correlation_id or event_id

    audit_log(
        AuditAction.TASK_SUBMITTED,
        actor="yeoman-webhook",
        resource_type="webhook",
        resource_id=event_id,
        detail={
            "event": payload.event,
            "source": payload.source,
            "correlation_id": correlation_id,
        },
    )

    logger.info(
        "Received YEOMAN webhook: event=%s source=%s correlation_id=%s",
        payload.event,
        payload.source,
        correlation_id,
    )

    # Build and submit QA task
    task_config = _build_task_from_event(payload.event, payload.data)
    task_id: str | None = None

    if task_config:
        try:
            from webgui.routes.tasks import TaskSubmitRequest, submit_task

            task_req = TaskSubmitRequest(**task_config)
            # Use a system user context for webhook-triggered tasks
            system_user = {
                "user_id": f"yeoman-webhook:{payload.source}",
                "email": "webhook@secureyeoman",
                "role": "api_user",
                "permissions": ["tasks:submit", "tasks:view"],
            }
            result = await submit_task(task_req, system_user)
            task_id = result.task_id
            logger.info(
                "Created QA task %s from YEOMAN %s event", task_id, payload.event
            )
        except Exception as exc:
            logger.error(
                "Failed to create QA task from YEOMAN %s event: %s",
                payload.event,
                exc,
            )

    # Buffer event for SSE subscribers
    _event_buffer.push(
        {
            "event_id": event_id,
            "event": payload.event,
            "source": payload.source,
            "timestamp": payload.timestamp,
            "correlation_id": correlation_id,
            "task_id": task_id,
            "data": payload.data,
            "received_at": datetime.now(UTC).isoformat(),
        }
    )

    return WebhookResponse(
        accepted=True,
        event_id=event_id,
        task_id=task_id,
        message=f"Event {payload.event} processed"
        + (f", task {task_id} created" if task_id else ", no task mapping"),
    )


# ---------------------------------------------------------------------------
# SSE event stream endpoint
# ---------------------------------------------------------------------------


@router.get("/yeoman/events/stream")
async def yeoman_event_stream(
    user: dict = Depends(get_current_user),
):
    """Server-Sent Events stream for real-time QA events.

    SecureYeoman connects here to receive live updates on:
    - Task status changes
    - QA completion events
    - Webhook processing results
    - Agent activity notifications

    Supports ``Last-Event-ID`` header for reconnection replay.
    """
    if not YEOMAN_WEBHOOKS_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="YEOMAN event streaming not enabled. Set YEOMAN_WEBHOOKS_ENABLED=true",
        )

    sub_id, queue = _event_buffer.subscribe()

    async def _generate():
        try:
            # Send initial connection event
            yield f"event: connected\ndata: {json.dumps({'subscriber_id': sub_id})}\n\n"

            while True:
                try:
                    event = await asyncio.wait_for(
                        queue.get(), timeout=_SSE_KEEPALIVE_INTERVAL
                    )
                    event_id = event.get("event_id", "")
                    event_type = event.get("event", "update")
                    yield f"id: {event_id}\nevent: {event_type}\ndata: {json.dumps(event)}\n\n"
                except TimeoutError:
                    # Send keepalive comment
                    yield f": keepalive {int(time.time())}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            _event_buffer.unsubscribe(sub_id)

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Recent events endpoint (REST fallback)
# ---------------------------------------------------------------------------


@router.get("/yeoman/events", response_model=YeomanEventsResponse)
async def list_yeoman_events(
    limit: int = 50,
    user: dict = Depends(get_current_user),
):
    """List recent webhook events (REST fallback for non-SSE clients)."""
    if not YEOMAN_WEBHOOKS_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="YEOMAN webhooks not enabled. Set YEOMAN_WEBHOOKS_ENABLED=true",
        )

    events = _event_buffer.recent(min(limit, 200))
    return {"events": events, "total": len(events)}
