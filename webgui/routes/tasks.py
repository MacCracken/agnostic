"""Task submission endpoints + webhook delivery + A2A protocol."""

import asyncio
import hashlib
import hmac
import json
import logging
import os
import random
import re
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from shared.audit import AuditAction, audit_log
from webgui.routes.dependencies import (
    YEOMAN_A2A_ENABLED,
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


class A2AStatusResponse(BaseModel):
    """Schema for ``a2a:status_query`` responses."""

    accepted: bool
    message_id: str
    type: Literal["status_response"]
    data: dict[str, Any]


# ---------------------------------------------------------------------------
# Webhook helpers
# ---------------------------------------------------------------------------

WEBHOOK_MAX_RETRIES = min(int(os.getenv("WEBHOOK_MAX_RETRIES", "3")), 10)

_webhook_http_client: Any = None
_webhook_client_lock = asyncio.Lock()

_TASK_ID_RE = re.compile(r"^[a-zA-Z0-9\-]{1,100}$")


async def _get_webhook_client() -> Any:
    """Return a shared httpx.AsyncClient for webhook delivery."""
    global _webhook_http_client
    async with _webhook_client_lock:
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
                delay = (2**attempt) * (0.8 + 0.4 * random.random())  # jittered backoff
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
    import asyncio as _asyncio

    from shared.database.tenants import tenant_manager

    task_redis_key = tenant_manager.task_key(tenant_id, task_id)
    loop = _asyncio.get_running_loop()

    def _update_task_sync(status: str, result: dict | None = None) -> dict[str, Any]:
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

    async def _update_task(status: str, result: dict | None = None) -> dict[str, Any]:
        return await loop.run_in_executor(None, _update_task_sync, status, result)

    final_record: dict[str, Any] = {}
    try:
        await _update_task("running")

        # Run agent import + execution in a thread so import-time failures
        # (crewai init, Redis/Celery singletons, missing deps) cannot corrupt
        # the main event loop.
        def _run_agent_sync() -> Any:
            """Import and execute the agent manager synchronously."""
            try:
                from agents.manager.qa_manager_optimized import OptimizedQAManager

                manager = OptimizedQAManager()
                return manager  # return manager for async orchestration
            except ImportError:
                from agents.manager.qa_manager import QAManagerAgent

                return QAManagerAgent()

        try:
            manager = await loop.run_in_executor(None, _run_agent_sync)
        except BaseException as import_err:
            logger.error(
                "Task %s: agent import failed: %s", task_id, import_err, exc_info=True
            )
            final_record = await _update_task(
                "failed", {"error": f"Agent runtime unavailable: {import_err}"}
            )
            if callback_url and final_record:
                await _fire_webhook(callback_url, callback_secret, final_record)
            return

        # Orchestrate — the manager is already instantiated safely
        if hasattr(manager, "orchestrate_qa_session"):
            result = await manager.orchestrate_qa_session(
                {"session_id": session_id, **requirements}
            )
        else:
            result = await manager.process_requirements(
                {"session_id": session_id, **requirements}
            )

        final_record = await _update_task("completed", result)

    except BaseException as e:
        logger.error("Task %s failed: %s", task_id, e, exc_info=True)
        try:
            final_record = await _update_task("failed", {"error": str(e)})
        except Exception:
            logger.exception("Task %s: failed to update status to 'failed'", task_id)

    # P3 — Webhook callback on completion
    if callback_url and final_record:
        await _fire_webhook(callback_url, callback_secret, final_record)


def _task_done_callback(task: asyncio.Task) -> None:  # type: ignore[type-arg]
    """Log unhandled exceptions from fire-and-forget task coroutines."""
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.error("Background task crashed: %s", exc, exc_info=exc)


# ---------------------------------------------------------------------------
# Task submission endpoints
# ---------------------------------------------------------------------------


@router.post("/tasks", response_model=TaskStatusResponse, status_code=201)
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

    # Fire-and-forget async execution with crash containment
    task = asyncio.create_task(
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
    task.add_done_callback(_task_done_callback)

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
    if not _TASK_ID_RE.match(task_id):
        raise HTTPException(status_code=400, detail="Invalid task ID format")

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
    if not YEOMAN_A2A_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="A2A protocol not enabled. Set YEOMAN_A2A_ENABLED=true",
        )
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

    if msg.type == "a2a:result":
        # YEOMAN sending task results back to AGNOSTIC
        try:
            from shared.yeoman_a2a_client import yeoman_a2a_client

            task_id = msg.payload.get("task_id", msg.id)
            yeoman_a2a_client.cache_result(task_id, msg.payload)
        except ImportError:
            logger.debug("yeoman_a2a_client not available — result not cached")
        return {"accepted": True, "message_id": msg.id, "type": "result_cached"}

    if msg.type == "a2a:status_query":
        # YEOMAN querying AGNOSTIC status
        status_data: dict = {"provider": "agnostic-qa", "agents": [], "sessions": []}
        try:
            from webgui.dashboard import dashboard_manager

            status_data = await dashboard_manager.export_dashboard_data()
        except Exception as exc:
            logger.warning("Failed to export dashboard data for status_query: %s", exc)
        return {
            "accepted": True,
            "message_id": msg.id,
            "type": "status_response",
            "data": status_data,
        }

    if msg.type == "a2a:provision_credentials":
        import time

        from config.credential_store import (
            CREDENTIAL_PROVISIONING_ENABLED,
            ProvisionedCredential,
            credential_store,
        )

        if not CREDENTIAL_PROVISIONING_ENABLED:
            raise HTTPException(
                status_code=503,
                detail="Credential provisioning not enabled",
            )
        # Only YEOMAN JWT or admin can provision
        auth_source = user.get("auth_source", "")
        role = user.get("role", "")
        if auth_source not in ("yeoman_jwt",) and role not in (
            "admin",
            "super_admin",
            "api_user",
        ):
            audit_log(
                AuditAction.PERMISSION_DENIED,
                actor=user.get("user_id", "unknown"),
                resource_type="credential",
                detail={"reason": "insufficient_privileges", "via": "a2a"},
            )
            raise HTTPException(
                status_code=403,
                detail="Credential provisioning requires YEOMAN JWT, admin, or API key",
            )

        expires_in = msg.payload.get("expires_in_seconds")
        credential_store.put(
            ProvisionedCredential(
                provider=msg.payload["provider"],
                api_key=msg.payload["api_key"],
                base_url=msg.payload.get("base_url"),
                model=msg.payload.get("model"),
                provisioned_by=user.get("user_id", msg.fromPeerId),
                provisioned_at=time.monotonic(),
                expires_at=time.monotonic() + expires_in if expires_in else None,
                metadata=msg.payload.get("metadata", {}),
            )
        )
        return {
            "accepted": True,
            "message_id": msg.id,
            "type": "credentials_provisioned",
        }

    if msg.type == "a2a:revoke_credentials":
        from config.credential_store import (
            CREDENTIAL_PROVISIONING_ENABLED,
            credential_store,
        )

        if not CREDENTIAL_PROVISIONING_ENABLED:
            raise HTTPException(
                status_code=503, detail="Credential provisioning not enabled"
            )

        auth_source = user.get("auth_source", "")
        role = user.get("role", "")
        if auth_source not in ("yeoman_jwt",) and role not in (
            "admin",
            "super_admin",
            "api_user",
        ):
            raise HTTPException(
                status_code=403,
                detail="Credential revocation requires YEOMAN JWT, admin, or API key",
            )

        provider = msg.payload.get("provider", "*")
        actor = user.get("user_id", msg.fromPeerId)
        if provider == "*":
            count = credential_store.revoke_all(actor)
            return {
                "accepted": True,
                "message_id": msg.id,
                "type": "credentials_revoked",
                "count": count,
            }
        else:
            credential_store.revoke(provider, actor)
            return {
                "accepted": True,
                "message_id": msg.id,
                "type": "credentials_revoked",
                "provider": provider,
            }

    # Unknown message type — acknowledge receipt but take no action
    return {
        "accepted": True,
        "message_id": msg.id,
        "warning": f"Unhandled type: {msg.type}",
    }


@router.get("/v1/a2a/capabilities")
async def a2a_capabilities():
    """Advertise what this Agnostic instance can do as an A2A peer.

    Includes MCP server info for auto-discovery by SecureYeoman.
    """
    if not YEOMAN_A2A_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="A2A protocol not enabled. Set YEOMAN_A2A_ENABLED=true",
        )

    # MCP tool count
    mcp_tool_count = 0
    try:
        from webgui.routes.mcp import MCP_ENABLED, MCP_TOOLS

        if MCP_ENABLED:
            mcp_tool_count = len(MCP_TOOLS)
    except ImportError:
        pass

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
        ],
        "mcp": {
            "enabled": mcp_tool_count > 0,
            "tool_count": mcp_tool_count,
            "endpoints": {
                "tools": "/api/v1/mcp/tools",
                "invoke": "/api/v1/mcp/invoke",
                "server_info": "/api/v1/mcp/server-info",
            },
        },
        "webhooks": {
            "endpoint": "/api/v1/yeoman/webhooks",
            "events_endpoint": "/api/v1/yeoman/events",
            "stream_endpoint": "/api/v1/yeoman/events/stream",
        },
        "auth_methods": ["api_key", "bearer_jwt", "yeoman_jwt"],
    }
