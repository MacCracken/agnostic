"""
WebGUI REST API — FastAPI router wrapping existing manager singletons.

Provides HTTP endpoints for dashboard, sessions, reports, agents, auth,
and task submission.  All business logic lives in the existing manager
modules; this module only handles HTTP concerns (routing, serialization,
auth dependency).
"""

import asyncio
import hashlib
import hmac
import json
import logging
import os
import re
import sys
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

# Add config path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from webgui.auth import Permission, auth_manager

logger = logging.getLogger(__name__)

api_router = APIRouter(prefix="/api")


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------

async def get_current_user(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    """Extract and verify credentials from request headers.

    Checks X-API-Key first (env-var static key, then Redis-backed keys),
    then falls back to Bearer JWT.
    """
    # 1. Check X-API-Key header
    if x_api_key is not None:
        # Static env-var key (simple deployments) — constant-time compare prevents timing attacks
        static_key = os.getenv("AGNOSTIC_API_KEY")
        if static_key and hmac.compare_digest(x_api_key, static_key):
            return {
                "user_id": "api-key-user",
                "email": "api@agnostic",
                "role": "api_user",
                "permissions": [p.value for p in Permission],
            }

        # Redis-backed keys (multi-key deployments)
        try:
            from config.environment import config

            redis_client = config.get_redis_client()
            key_hash = hashlib.sha256(x_api_key.encode()).hexdigest()
            key_data = redis_client.get(f"api_key:{key_hash}")
            if key_data:
                return json.loads(key_data)
        except Exception as e:
            logger.warning(f"Redis API key lookup failed: {e}")

        raise HTTPException(status_code=401, detail="Invalid API key")

    # 2. Fall back to Bearer JWT
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401, detail="Missing or invalid authorization header"
        )

    token = authorization.removeprefix("Bearer ")
    payload = await auth_manager.verify_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return payload


def require_permission(permission: Permission):
    """Factory for permission-checking dependencies."""

    async def _check(user: dict = Depends(get_current_user)):
        user_permissions = user.get("permissions", [])
        if permission.value not in user_permissions:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user

    return _check


# ---------------------------------------------------------------------------
# Pydantic request/response models
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    access_token: str


class ReportGenerateRequest(BaseModel):
    session_id: str
    report_type: str = "executive_summary"
    format: str = "json"


class SessionCompareRequest(BaseModel):
    session1_id: str
    session2_id: str


_VALID_AGENTS = {
    "security-compliance", "performance", "junior-qa", "qa-analyst",
    "senior-qa", "qa-manager",
}


class TaskSubmitRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1, max_length=5000)
    target_url: str | None = None
    priority: Literal["critical", "high", "medium", "low"] = "high"
    standards: list[str] = Field(default_factory=list)   # ["OWASP", "GDPR", ...]
    agents: list[str] = Field(default_factory=list)      # [] = all; or subset of _VALID_AGENTS
    business_goals: str = Field(
        default="Ensure quality and functionality", max_length=500
    )
    constraints: str = Field(default="Standard testing environment", max_length=500)
    callback_url: str | None = None   # POST here on completion
    callback_secret: str | None = None  # HMAC-SHA256 signing secret


class TaskStatusResponse(BaseModel):
    task_id: str
    session_id: str
    status: str       # pending | running | completed | failed
    created_at: str
    updated_at: str
    result: dict | None = None


class ApiKeyCreateRequest(BaseModel):
    description: str = ""
    role: str = "api_user"


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------

@api_router.post("/auth/login")
async def login(req: LoginRequest):
    user = await auth_manager.authenticate_user(email=req.email, password=req.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    tokens = await auth_manager.create_tokens(user)
    return {
        "access_token": tokens.access_token,
        "refresh_token": tokens.refresh_token,
        "token_type": tokens.token_type,
        "expires_in": tokens.expires_in,
    }


@api_router.post("/auth/refresh")
async def refresh(req: RefreshRequest):
    tokens = await auth_manager.refresh_tokens(req.refresh_token)
    if tokens is None:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    return {
        "access_token": tokens.access_token,
        "refresh_token": tokens.refresh_token,
        "token_type": tokens.token_type,
        "expires_in": tokens.expires_in,
    }


@api_router.post("/auth/logout")
async def logout(req: LogoutRequest, user: dict = Depends(get_current_user)):
    success = await auth_manager.logout(user["user_id"], req.access_token)
    if not success:
        raise HTTPException(status_code=500, detail="Logout failed")
    return {"status": "logged_out"}


@api_router.get("/auth/me")
async def auth_me(user: dict = Depends(get_current_user)):
    return {
        "user_id": user.get("user_id"),
        "email": user.get("email"),
        "role": user.get("role"),
        "permissions": user.get("permissions", []),
    }


# ---------------------------------------------------------------------------
# API key management endpoints (require SYSTEM_CONFIGURE permission)
# ---------------------------------------------------------------------------

@api_router.post("/auth/api-keys")
async def create_api_key(
    req: ApiKeyCreateRequest,
    user: dict = Depends(require_permission(Permission.SYSTEM_CONFIGURE)),
):
    """Create a new API key. Returns the raw key once — store it safely."""
    from config.environment import config
    from webgui.auth import create_api_key as _create_api_key

    redis_client = config.get_redis_client()
    raw_key, key_id, key_meta = _create_api_key(
        redis_client=redis_client,
        description=req.description,
        role=req.role,
        created_by=user.get("user_id", "unknown"),
    )
    return {
        "key_id": key_id,
        "api_key": raw_key,
        "description": req.description,
        "role": req.role,
        "created_at": key_meta["created_at"],
        "note": "Store this key safely — it will not be shown again.",
    }


@api_router.get("/auth/api-keys")
async def list_api_keys(
    user: dict = Depends(require_permission(Permission.SYSTEM_CONFIGURE)),
):
    """List API key IDs and metadata (never raw keys)."""
    from config.environment import config
    from webgui.auth import list_api_keys as _list_api_keys

    redis_client = config.get_redis_client()
    keys = _list_api_keys(redis_client)
    return {"api_keys": keys}


@api_router.delete("/auth/api-keys/{key_id}")
async def delete_api_key(
    key_id: str,
    user: dict = Depends(require_permission(Permission.SYSTEM_CONFIGURE)),
):
    """Revoke an API key by its ID (first 8 chars of sha256 hash)."""
    from config.environment import config
    from webgui.auth import revoke_api_key as _revoke_api_key

    redis_client = config.get_redis_client()
    deleted = _revoke_api_key(redis_client, key_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="API key not found")
    return {"status": "revoked", "key_id": key_id}


# ---------------------------------------------------------------------------
# Task submission endpoints (P1)
# ---------------------------------------------------------------------------

@api_router.post("/tasks", response_model=TaskStatusResponse)
async def submit_task(
    req: TaskSubmitRequest,
    user: dict = Depends(get_current_user),
):
    """Submit a new QA task. Returns immediately with task_id for polling."""
    from config.environment import config

    task_id = str(uuid.uuid4())
    session_id = (
        f"session_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{task_id[:8]}"
    )
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
    redis_client.setex(f"task:{task_id}", 86400, json.dumps(task_record))

    # Fire-and-forget async execution
    asyncio.create_task(
        _run_task_async(
            task_id=task_id,
            session_id=session_id,
            requirements=requirements,
            redis_client=redis_client,
            callback_url=req.callback_url,
            callback_secret=req.callback_secret,
        )
    )

    return TaskStatusResponse(**task_record)


@api_router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_task(task_id: str, user: dict = Depends(get_current_user)):
    """Poll task status by task_id."""
    from config.environment import config

    redis_client = config.get_redis_client()
    data = redis_client.get(f"task:{task_id}")
    if not data:
        raise HTTPException(status_code=404, detail="Task not found")

    record = json.loads(data)
    return TaskStatusResponse(**record)


async def _run_task_async(
    task_id: str,
    session_id: str,
    requirements: dict[str, Any],
    redis_client: Any,
    callback_url: str | None,
    callback_secret: str | None,
) -> None:
    """Run a QA task asynchronously, updating Redis through status transitions."""

    def _update_task(status: str, result: dict | None = None) -> dict[str, Any]:
        raw = redis_client.get(f"task:{task_id}")
        record: dict[str, Any] = json.loads(raw) if raw else {
            "task_id": task_id,
            "session_id": session_id,
            "created_at": datetime.now(UTC).isoformat(),
        }
        record["status"] = status
        record["updated_at"] = datetime.now(UTC).isoformat()
        record["result"] = result
        redis_client.setex(f"task:{task_id}", 86400, json.dumps(record))
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


async def _fire_webhook(
    callback_url: str,
    callback_secret: str | None,
    payload: dict[str, Any],
) -> None:
    """POST task result to callback_url with optional HMAC-SHA256 signature."""
    try:
        import httpx

        body = json.dumps(payload)
        headers: dict[str, str] = {"Content-Type": "application/json"}

        if callback_secret:
            sig = hmac.new(
                callback_secret.encode(), body.encode(), hashlib.sha256
            ).hexdigest()
            headers["X-Signature"] = f"sha256={sig}"

        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(callback_url, content=body, headers=headers)

        logger.info(f"Webhook delivered to {callback_url}")

    except Exception as e:
        logger.warning(f"Webhook delivery to {callback_url} failed: {e}")


# ---------------------------------------------------------------------------
# Agent-specific convenience endpoints (P4)
# ---------------------------------------------------------------------------

@api_router.post("/tasks/security", response_model=TaskStatusResponse)
async def submit_security_task(
    req: TaskSubmitRequest,
    user: dict = Depends(get_current_user),
):
    """Submit a security-focused QA task (routes to security-compliance agent)."""
    req.agents = ["security-compliance"]
    return await submit_task(req, user)


@api_router.post("/tasks/performance", response_model=TaskStatusResponse)
async def submit_performance_task(
    req: TaskSubmitRequest,
    user: dict = Depends(get_current_user),
):
    """Submit a performance-focused QA task (routes to performance agent)."""
    req.agents = ["performance"]
    return await submit_task(req, user)


@api_router.post("/tasks/regression", response_model=TaskStatusResponse)
async def submit_regression_task(
    req: TaskSubmitRequest,
    user: dict = Depends(get_current_user),
):
    """Submit a regression QA task (routes to junior-qa + qa-analyst)."""
    req.agents = ["junior-qa", "qa-analyst"]
    return await submit_task(req, user)


@api_router.post("/tasks/full", response_model=TaskStatusResponse)
async def submit_full_task(
    req: TaskSubmitRequest,
    user: dict = Depends(get_current_user),
):
    """Submit a full QA task (uses all 6 agents)."""
    req.agents = []
    return await submit_task(req, user)


# ---------------------------------------------------------------------------
# P8 — A2A (Agent-to-Agent) protocol endpoints
# ---------------------------------------------------------------------------

class A2AMessage(BaseModel):
    id: str
    type: str           # "a2a:delegate", "a2a:heartbeat", etc.
    fromPeerId: str
    toPeerId: str
    payload: dict[str, Any] = {}
    timestamp: int      # Unix milliseconds


@api_router.post("/v1/a2a/receive")
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
    return {"accepted": True, "message_id": msg.id, "warning": f"Unhandled type: {msg.type}"}


@api_router.get("/v1/a2a/capabilities")
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


# ---------------------------------------------------------------------------
# Dashboard endpoints
# ---------------------------------------------------------------------------

@api_router.get("/dashboard")
async def get_dashboard(user: dict = Depends(get_current_user)):
    from webgui.dashboard import dashboard_manager

    data = await dashboard_manager.export_dashboard_data()
    return data


@api_router.get("/dashboard/sessions")
async def get_dashboard_sessions(user: dict = Depends(get_current_user)):
    from webgui.dashboard import dashboard_manager

    sessions = await dashboard_manager.get_active_sessions()
    return [asdict(s) for s in sessions]


@api_router.get("/dashboard/agents")
async def get_dashboard_agents(user: dict = Depends(get_current_user)):
    from webgui.dashboard import dashboard_manager

    agents = await dashboard_manager.get_agent_status()
    return [asdict(a) for a in agents]


@api_router.get("/dashboard/metrics")
async def get_dashboard_metrics(user: dict = Depends(get_current_user)):
    from webgui.dashboard import dashboard_manager

    metrics = await dashboard_manager.get_resource_metrics()
    return asdict(metrics)


# ---------------------------------------------------------------------------
# Session endpoints
# ---------------------------------------------------------------------------

@api_router.get("/sessions")
async def get_sessions(
    user_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: dict = Depends(get_current_user),
):
    from webgui.history import history_manager

    sessions = await history_manager.get_session_history(
        user_id=user_id, limit=limit, offset=offset,
    )
    return [asdict(s) for s in sessions]


@api_router.get("/sessions/search")
async def search_sessions(
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_user),
):
    from webgui.history import history_manager

    results = await history_manager.search_sessions(query=q, limit=limit)
    return [asdict(s) for s in results]


@api_router.get("/sessions/{session_id}")
async def get_session(session_id: str, user: dict = Depends(get_current_user)):
    from webgui.history import history_manager

    details = await history_manager.get_session_details(session_id)
    if details is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return details


@api_router.post("/sessions/compare")
async def compare_sessions(
    req: SessionCompareRequest,
    user: dict = Depends(get_current_user),
):
    from webgui.history import history_manager

    comparison = await history_manager.compare_sessions(
        req.session1_id, req.session2_id,
    )
    if comparison is None:
        raise HTTPException(status_code=404, detail="One or both sessions not found")
    return asdict(comparison)


# ---------------------------------------------------------------------------
# Report endpoints
# ---------------------------------------------------------------------------

@api_router.get("/reports")
async def list_reports(user: dict = Depends(get_current_user)):
    from config.environment import config

    redis_client = config.get_redis_client()
    user_id = user.get("user_id", "")
    keys = redis_client.keys(f"report:*:{user_id}:*")
    reports = []
    for key in keys:
        data = redis_client.get(key)
        if data:
            reports.append(json.loads(data))
    return reports


@api_router.post("/reports/generate")
async def generate_report(
    req: ReportGenerateRequest,
    user: dict = Depends(require_permission(Permission.REPORTS_GENERATE)),
):
    from webgui.exports import ReportFormat, ReportRequest, ReportType, report_generator

    try:
        report_type = ReportType(req.report_type)
        report_format = ReportFormat(req.format)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid report type or format: {e}") from e

    report_req = ReportRequest(
        session_id=req.session_id,
        report_type=report_type,
        format=report_format,
    )
    metadata = await report_generator.generate_report(report_req, user["user_id"])
    return {
        "report_id": metadata.report_id,
        "generated_at": metadata.generated_at.isoformat(),
        "session_id": metadata.session_id,
        "report_type": metadata.report_type.value,
        "format": metadata.format.value,
        "file_size": metadata.file_size,
    }


_REPORTS_DIR = Path("/app/reports").resolve()


@api_router.get("/reports/{report_id}/download")
async def download_report(
    report_id: str,
    user: dict = Depends(get_current_user),
):
    from config.environment import config

    redis_client = config.get_redis_client()
    meta_data = redis_client.get(f"report:{report_id}:meta")
    if not meta_data:
        raise HTTPException(status_code=404, detail="Report not found")

    meta = json.loads(meta_data)
    file_path = meta.get("file_path")
    if not file_path:
        raise HTTPException(status_code=404, detail="Report file not found")

    # Prevent path traversal: ensure file is inside the reports directory
    resolved = Path(file_path).resolve()
    if not resolved.is_relative_to(_REPORTS_DIR):
        logger.warning("Path traversal attempt blocked for report %s: %s", report_id, file_path)
        raise HTTPException(status_code=403, detail="Access denied")

    if not resolved.exists():
        raise HTTPException(status_code=404, detail="Report file not found on disk")

    return FileResponse(
        path=str(resolved),
        filename=resolved.name,
        media_type="application/octet-stream",
    )


# ---------------------------------------------------------------------------
# Agent endpoints
# ---------------------------------------------------------------------------

@api_router.get("/agents")
async def get_agents(user: dict = Depends(get_current_user)):
    from webgui.agent_monitor import agent_monitor

    statuses = await agent_monitor.get_all_agent_status()
    return [asdict(s) for s in statuses]


@api_router.get("/agents/queues")
async def get_agent_queues(user: dict = Depends(get_current_user)):
    from webgui.agent_monitor import agent_monitor

    return await agent_monitor.get_queue_depths()


@api_router.get("/agents/{agent_name}")
async def get_agent_detail(
    agent_name: str,
    user: dict = Depends(get_current_user),
):
    from webgui.agent_monitor import agent_monitor

    metrics = await agent_monitor.get_agent_metrics(agent_name)
    if metrics is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return asdict(metrics)


# ---------------------------------------------------------------------------
# Metrics endpoint (unauthenticated — for Prometheus scraping)
# ---------------------------------------------------------------------------

@api_router.get("/metrics")
async def get_metrics():
    from shared.metrics import get_content_type, get_metrics_text

    return JSONResponse(
        content=get_metrics_text(),
        media_type=get_content_type(),
    )
