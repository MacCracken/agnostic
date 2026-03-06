"""Task submission endpoints + webhook delivery + A2A protocol."""

import asyncio
import hashlib
import hmac
import json
import logging
import os
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from shared.audit import AuditAction, audit_log
from webgui.routes.dependencies import (
    _normalize_agent_name,
    _validate_callback_url,
    get_current_user,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Request/response models
# ---------------------------------------------------------------------------


class TaskSubmitRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1, max_length=5000)
    target_url: str | None = None
    priority: Literal["critical", "high", "medium", "low"] = "high"
    standards: list[str] = Field(default_factory=list)
    agents: list[str] = Field(default_factory=list)
    business_goals: str = Field(
        default="Ensure quality and functionality", max_length=500
    )
    constraints: str = Field(default="Standard testing environment", max_length=500)
    callback_url: str | None = None
    callback_secret: str | None = None


class TaskStatusResponse(BaseModel):
    task_id: str
    session_id: str
    status: str  # pending | running | completed | failed
    created_at: str
    updated_at: str
    result: dict | None = None


class A2AMessage(BaseModel):
    id: str
    type: str  # "a2a:delegate", "a2a:heartbeat", etc.
    fromPeerId: str
    toPeerId: str
    payload: dict[str, Any] = {}
    timestamp: int  # Unix milliseconds


# ---------------------------------------------------------------------------
# Webhook helpers
# ---------------------------------------------------------------------------

WEBHOOK_MAX_RETRIES = int(os.getenv("WEBHOOK_MAX_RETRIES", "3"))

_webhook_http_client: Any = None


async def _get_webhook_client() -> Any:
    """Return a shared httpx.AsyncClient for webhook delivery."""
    global _webhook_http_client
    if _webhook_http_client is None or _webhook_http_client.is_closed:
        import httpx

        _webhook_http_client = httpx.AsyncClient(timeout=10)
    return _webhook_http_client


async def _fire_webhook(
    callback_url: str,
    callback_secret: str | None,
    payload: dict[str, Any],
) -> None:
    """POST task result to callback_url with optional HMAC-SHA256 signature.

    Retries up to WEBHOOK_MAX_RETRIES times with exponential backoff (1s, 2s, 4s, ...).
    """
    body = json.dumps(payload)
    headers: dict[str, str] = {"Content-Type": "application/json"}

    if callback_secret:
        sig = hmac.new(
            callback_secret.encode(), body.encode(), hashlib.sha256
        ).hexdigest()
        headers["X-Signature"] = f"sha256={sig}"

    client = await _get_webhook_client()
    last_error: Exception | None = None
    for attempt in range(WEBHOOK_MAX_RETRIES):
        try:
            resp = await client.post(callback_url, content=body, headers=headers)
            resp.raise_for_status()

            logger.info(f"Webhook delivered to {callback_url}")
            return

        except Exception as e:
            last_error = e
            if attempt < WEBHOOK_MAX_RETRIES - 1:
                delay = 2**attempt  # 1s, 2s, 4s, ...
                logger.warning(
                    f"Webhook delivery to {callback_url} failed (attempt {attempt + 1}/{WEBHOOK_MAX_RETRIES}): {e}. "
                    f"Retrying in {delay}s"
                )
                await asyncio.sleep(delay)

    logger.error(
        f"Webhook delivery to {callback_url} failed after {WEBHOOK_MAX_RETRIES} attempts: {last_error}"
    )


# ---------------------------------------------------------------------------
# Async task runner
# ---------------------------------------------------------------------------


async def _run_task_async(
    task_id: str,
    session_id: str,
    requirements: dict[str, Any],
    redis_client: Any,
    callback_url: str | None,
    callback_secret: str | None,
    tenant_id: str = "default",
) -> None:
    """Run a QA task asynchronously, updating Redis through status transitions."""
    from shared.database.tenants import tenant_manager

    task_redis_key = tenant_manager.task_key(tenant_id, task_id)

    def _update_task(status: str, result: dict | None = None) -> dict[str, Any]:
        raw = redis_client.get(task_redis_key)
        record: dict[str, Any] = (
            json.loads(raw)
            if raw
            else {
                "task_id": task_id,
                "session_id": session_id,
                "created_at": datetime.now(UTC).isoformat(),
            }
        )
        record["status"] = status
        record["updated_at"] = datetime.now(UTC).isoformat()
        record["result"] = result
        redis_client.setex(task_redis_key, 86400, json.dumps(record))

        # Publish task update to WebSocket subscribers
        redis_client.publish(
            f"task:{task_id}",
            json.dumps(
                {
                    "type": "task_status_changed",
                    "task_id": task_id,
                    "status": status,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "result": result,
                }
            ),
        )

        return record

    final_record: dict[str, Any] = {}
    try:
        _update_task("running")

        # Lazy-import to avoid startup overhead
        try:
            from agents.manager.qa_manager_optimized import OptimizedQAManager

            manager = OptimizedQAManager()
            result = await manager.orchestrate_qa_session(
                {"session_id": session_id, **requirements}
            )
        except ImportError:
            from agents.manager.qa_manager import QAManagerAgent

            manager = QAManagerAgent()
            result = await manager.process_requirements(
                {"session_id": session_id, **requirements}
            )

        final_record = _update_task("completed", result)

    except Exception as e:
        logger.error(f"Task {task_id} failed: {e}")
        final_record = _update_task("failed", {"error": str(e)})

    # P3 — Webhook callback on completion
    if callback_url and final_record:
        await _fire_webhook(callback_url, callback_secret, final_record)


# ---------------------------------------------------------------------------
# Task submission endpoints
# ---------------------------------------------------------------------------


@router.post("/tasks", response_model=TaskStatusResponse)
async def submit_task(
    req: TaskSubmitRequest,
    user: dict = Depends(get_current_user),
):
    """Submit a new QA task. Returns immediately with task_id for polling."""
    # Validate callback URL against SSRF
    if req.callback_url:
        try:
            _validate_callback_url(req.callback_url)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    # Normalize agent names (accept both snake_case and kebab-case)
    if req.agents:
        req.agents = [_normalize_agent_name(a) for a in req.agents]

    from config.environment import config

    task_id = str(uuid.uuid4())
    session_id = f"session_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{task_id[:8]}"
    now = datetime.now(UTC).isoformat()

    requirements = {
        "title": req.title,
        "description": req.description,
        "priority": req.priority,
        "standards": req.standards,
        "agents": req.agents,
        "business_goals": req.business_goals,
        "constraints": req.constraints,
        "target_url": req.target_url,
        "submitted_by": user.get("user_id", "api-user"),
        "submitted_at": now,
    }

    task_record: dict[str, Any] = {
        "task_id": task_id,
        "session_id": session_id,
        "status": "pending",
        "created_at": now,
        "updated_at": now,
        "result": None,
    }

    redis_client = config.get_redis_client()

    # Tenant-scoped Redis key when multi-tenant is enabled
    from shared.database.tenants import tenant_manager

    tenant_id = user.get("tenant_id", tenant_manager.default_tenant_id)
    task_redis_key = tenant_manager.task_key(tenant_id, task_id)

    # Rate limit check for tenant
    if tenant_manager.enabled and not tenant_manager.check_rate_limit(
        redis_client, tenant_id
    ):
        audit_log(
            AuditAction.RATE_LIMIT_EXCEEDED,
            actor=user.get("user_id"),
            tenant_id=tenant_id,
        )
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    redis_client.setex(task_redis_key, 86400, json.dumps(task_record))

    # Fire-and-forget async execution
    asyncio.create_task(
        _run_task_async(
            task_id=task_id,
            session_id=session_id,
            requirements=requirements,
            redis_client=redis_client,
            callback_url=req.callback_url,
            callback_secret=req.callback_secret,
            tenant_id=tenant_id,
        )
    )

    audit_log(
        AuditAction.TASK_SUBMITTED,
        actor=user.get("user_id"),
        resource_type="task",
        resource_id=task_id,
    )

    return TaskStatusResponse(**task_record)


@router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_task(task_id: str, user: dict = Depends(get_current_user)):
    """Poll task status by task_id."""
    from config.environment import config
    from shared.database.tenants import tenant_manager

    redis_client = config.get_redis_client()
    tenant_id = user.get("tenant_id", tenant_manager.default_tenant_id)
    task_redis_key = tenant_manager.task_key(tenant_id, task_id)
    data = redis_client.get(task_redis_key)
    if not data:
        raise HTTPException(status_code=404, detail="Task not found")

    record = json.loads(data)
    return TaskStatusResponse(**record)


# ---------------------------------------------------------------------------
# Agent-specific convenience endpoints
# ---------------------------------------------------------------------------


@router.post("/tasks/security", response_model=TaskStatusResponse)
async def submit_security_task(
    req: TaskSubmitRequest,
    user: dict = Depends(get_current_user),
):
    """Submit a security-focused QA task (routes to security-compliance agent)."""
    req.agents = ["security-compliance"]
    return await submit_task(req, user)


@router.post("/tasks/performance", response_model=TaskStatusResponse)
async def submit_performance_task(
    req: TaskSubmitRequest,
    user: dict = Depends(get_current_user),
):
    """Submit a performance-focused QA task (routes to performance agent)."""
    req.agents = ["performance"]
    return await submit_task(req, user)


@router.post("/tasks/regression", response_model=TaskStatusResponse)
async def submit_regression_task(
    req: TaskSubmitRequest,
    user: dict = Depends(get_current_user),
):
    """Submit a regression QA task (routes to junior-qa + qa-analyst)."""
    req.agents = ["junior-qa", "qa-analyst"]
    return await submit_task(req, user)


@router.post("/tasks/full", response_model=TaskStatusResponse)
async def submit_full_task(
    req: TaskSubmitRequest,
    user: dict = Depends(get_current_user),
):
    """Submit a full QA task (uses all 6 agents)."""
    req.agents = []
    return await submit_task(req, user)


# ---------------------------------------------------------------------------
# A2A (Agent-to-Agent) protocol endpoints
# ---------------------------------------------------------------------------


@router.post("/v1/a2a/receive")
async def receive_a2a_message(
    msg: A2AMessage,
    user: dict = Depends(get_current_user),
):
    """Receive an A2A protocol message from a YEOMAN peer."""
    if msg.type == "a2a:delegate":
        payload = msg.payload
        task_req = TaskSubmitRequest(
            title=payload.get("title", "A2A QA Task"),
            description=payload.get("description", ""),
            target_url=payload.get("target_url"),
            priority=payload.get("priority", "high"),
            agents=payload.get("agents", []),
            standards=payload.get("standards", []),
        )
        result = await submit_task(task_req, user)
        return {"accepted": True, "task_id": result.task_id, "message_id": msg.id}

    if msg.type == "a2a:heartbeat":
        return {"accepted": True, "message_id": msg.id, "timestamp": msg.timestamp}

    # Unknown message type — acknowledge receipt but take no action
    return {
        "accepted": True,
        "message_id": msg.id,
        "warning": f"Unhandled type: {msg.type}",
    }


@router.get("/v1/a2a/capabilities")
async def a2a_capabilities():
    """Advertise what this Agnostic instance can do as an A2A peer."""
    return {
        "capabilities": [
            {
                "name": "qa",
                "description": "6-agent QA pipeline (security, performance, regression, compliance)",
                "version": "1.0",
            },
            {
                "name": "security-audit",
                "description": "OWASP, GDPR, PCI DSS, SOC 2 compliance scanning",
                "version": "1.0",
            },
            {
                "name": "performance-test",
                "description": "Load testing and P95/P99 latency profiling",
                "version": "1.0",
            },
        ]
    }
