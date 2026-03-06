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

        # Publish task update to WebSocket subscribers
        redis_client.publish(f"task:{task_id}", json.dumps({
            "type": "task_status_changed",
            "task_id": task_id,
            "status": status,
            "timestamp": datetime.now(UTC).isoformat(),
            "result": result,
        }))

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


WEBHOOK_MAX_RETRIES = int(os.getenv("WEBHOOK_MAX_RETRIES", "3"))


async def _fire_webhook(
    callback_url: str,
    callback_secret: str | None,
    payload: dict[str, Any],
) -> None:
    """POST task result to callback_url with optional HMAC-SHA256 signature.

    Retries up to WEBHOOK_MAX_RETRIES times with exponential backoff (1s, 2s, 4s, ...).
    """
    import httpx

    body = json.dumps(payload)
    headers: dict[str, str] = {"Content-Type": "application/json"}

    if callback_secret:
        sig = hmac.new(
            callback_secret.encode(), body.encode(), hashlib.sha256
        ).hexdigest()
        headers["X-Signature"] = f"sha256={sig}"

    last_error: Exception | None = None
    for attempt in range(WEBHOOK_MAX_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=10) as client:
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
# Scheduled Report endpoints
# ---------------------------------------------------------------------------

from pydantic import BaseModel


class ScheduleReportRequest(BaseModel):
    report_type: str
    format: str
    schedule: dict


class ScheduleReportResponse(BaseModel):
    job_id: str
    name: str
    next_run: str | None


@api_router.get("/reports/scheduled")
async def get_scheduled_reports(
    user: dict = Depends(get_current_user),
):
    from webgui.scheduled_reports import scheduled_report_manager

    jobs = scheduled_report_manager.get_jobs()
    return jobs


@api_router.post("/reports/scheduled")
async def schedule_report(
    req: ScheduleReportRequest,
    user: dict = Depends(require_permission(Permission.REPORTS_GENERATE)),
):
    from webgui.scheduled_reports import scheduled_report_manager

    try:
        job_id = await scheduled_report_manager.schedule_custom_report(
            report_type=req.report_type,
            format=req.format,
            schedule=req.schedule,
            report_name=f"{req.report_type} by {user['user_id']}",
        )

        jobs = scheduled_report_manager.get_jobs()
        job = next((j for j in jobs if j["id"] == job_id), None)

        return {
            "job_id": job_id,
            "name": job["name"] if job else req.report_type,
            "next_run": job["next_run"] if job else None,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to schedule report: {e}")
        raise HTTPException(status_code=500, detail="Failed to schedule report")


@api_router.delete("/reports/scheduled/{job_id}")
async def delete_scheduled_report(
    job_id: str,
    user: dict = Depends(require_permission(Permission.REPORTS_GENERATE)),
):
    from webgui.scheduled_reports import scheduled_report_manager

    if scheduled_report_manager.remove_job(job_id):
        return {"status": "deleted", "job_id": job_id}
    raise HTTPException(status_code=404, detail="Job not found")


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


# ---------------------------------------------------------------------------
# Structured Result Schemas for YEOMAN
# ---------------------------------------------------------------------------

@api_router.get("/results/structured/{session_id}")
async def get_structured_results(
    session_id: str,
    result_type: str | None = None,
    user: dict = Depends(get_current_user),
):
    """Get structured results for YEOMAN integration.

    Returns typed results that YEOMAN can parse to take programmatic actions:
    - Auto-create issues for critical security findings
    - Block PRs on regression failures
    - Alert on flaky tests
    """
    try:
        from shared.yeoman_schemas import (
            PerformanceResult,
            QAReport,
            SecurityResult,
            TestExecutionResult,
        )

        redis_client = config.get_redis_client()

        results = {}

        if result_type in (None, "security"):
            security_data = redis_client.get(f"security_compliance:{session_id}:audit")
            if security_data:
                sec = json.loads(security_data)
                findings = []
                for v in sec.get("vulnerabilities", []):
                    from shared.yeoman_schemas import Finding, FindingCategory, FindingSeverity
                    findings.append(Finding(
                        finding_id=v.get("id", f"sec-{len(findings)}"),
                        title=v.get("description", "Unknown vulnerability"),
                        description=v.get("description", ""),
                        severity=FindingSeverity(v.get("severity", "medium")),
                        category=FindingCategory.SECURITY,
                        component=v.get("component", "unknown"),
                        cwe_id=v.get("cwe_id"),
                        cvss_score=v.get("cvss_score"),
                    ))
                results["security"] = SecurityResult(
                    scan_id=f"scan-{session_id}",
                    session_id=session_id,
                    scan_type="comprehensive",
                    timestamp=datetime.now(UTC).isoformat(),
                    overall_score=sec.get("security_score", 0),
                    risk_level=sec.get("risk_level", "unknown"),
                    findings=findings,
                    compliance_scores=sec.get("compliance_scores", {}),
                )

        if result_type in (None, "performance"):
            perf_data = redis_client.get(f"analyst:{session_id}:performance")
            if perf_data:
                perf = json.loads(perf_data)
                results["performance"] = PerformanceResult(
                    test_id=f"perf-{session_id}",
                    session_id=session_id,
                    test_type=perf.get("test_type", "load"),
                    timestamp=datetime.now(UTC).isoformat(),
                    duration_seconds=perf.get("duration", 0),
                    response_times=perf.get("response_times", {}),
                    throughput=perf.get("throughput", {}).get("rps", 0),
                    error_rate=perf.get("error_rate", 0),
                    regression_detected=perf.get("regression_detected", False),
                )

        if result_type in (None, "test_execution"):
            test_data = redis_client.get(f"junior:{session_id}:test_results")
            if test_data:
                test = json.loads(test_data)
                results["test_execution"] = TestExecutionResult(
                    execution_id=f"exec-{session_id}",
                    session_id=session_id,
                    test_type="automated",
                    timestamp=datetime.now(UTC).isoformat(),
                    status="passed" if test.get("passed", 0) > test.get("failed", 0) else "failed",
                    total_tests=test.get("total", 0),
                    passed=test.get("passed", 0),
                    failed=test.get("failed", 0),
                    skipped=test.get("skipped", 0),
                    coverage_percentage=test.get("coverage", 0),
                )

        if not results:
            return {"session_id": session_id, "message": "No results found"}

        report = QAReport(
            report_id=f"report-{session_id}",
            session_id=session_id,
            report_type=result_type or "comprehensive",
            generated_at=datetime.now(UTC).isoformat(),
            summary="Structured results for YEOMAN integration",
            security=results.get("security"),
            performance=results.get("performance"),
            test_execution=results.get("test_execution"),
        )

        return report.to_yeoman_action()

    except Exception as e:
        logger.error(f"Error generating structured results: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Test Result Persistence (PostgreSQL) endpoints
# ---------------------------------------------------------------------------

from pydantic import BaseModel


class TestSessionCreate(BaseModel):
    session_id: str
    title: str
    description: str | None = None
    priority: str | None = None


class TestResultCreate(BaseModel):
    session_id: str
    test_id: str
    test_name: str
    description: str | None = None
    status: str
    severity: str | None = None
    category: str | None = None
    component: str | None = None
    agent_name: str | None = None
    error_message: str | None = None
    stack_trace: str | None = None
    execution_time_ms: int | None = None
    test_data: dict | None = None
    expected_result: dict | None = None
    actual_result: dict | None = None
    metadata: dict | None = None


class TestResultFilter(BaseModel):
    session_id: str | None = None
    status: str | None = None
    limit: int = 100
    offset: int = 0


class TestMetricsQuery(BaseModel):
    session_id: str | None = None
    metric_name: str | None = None
    days: int = 30


DATABASE_ENABLED = os.getenv("DATABASE_ENABLED", "false").lower() == "true"


def _get_db_repo():
    """Get database repository if enabled."""
    if not DATABASE_ENABLED:
        return None
    try:
        from shared.database.repository import TestResultRepository
        from shared.database.models import get_session

        return TestResultRepository
    except Exception:
        return None


async def get_db_repo():
    """Get database repository instance."""
    repo_class = _get_db_repo()
    if repo_class is None:
        return None
    session = await get_session()
    return repo_class(session)


@api_router.get("/test-sessions")
async def get_test_sessions(
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    user: dict = Depends(get_current_user),
):
    """Get test sessions."""
    repo = await get_db_repo()
    if repo is None:
        raise HTTPException(
            status_code=503, detail="Database not enabled. Set DATABASE_ENABLED=true"
        )
    sessions = await repo.get_sessions(status=status, limit=limit, offset=offset)
    return [
        {
            "id": s.id,
            "session_id": s.session_id,
            "title": s.title,
            "description": s.description,
            "status": s.status,
            "priority": s.priority,
            "created_by": s.created_by,
            "created_at": s.created_at.isoformat(),
            "completed_at": s.completed_at.isoformat() if s.completed_at else None,
        }
        for s in sessions
    ]


@api_router.post("/test-sessions")
async def create_test_session(
    req: TestSessionCreate,
    user: dict = Depends(require_permission(Permission.SESSIONS_WRITE)),
):
    """Create a new test session."""
    repo = await get_db_repo()
    if repo is None:
        raise HTTPException(
            status_code=503, detail="Database not enabled. Set DATABASE_ENABLED=true"
        )
    session = await repo.create_session(
        session_id=req.session_id,
        title=req.title,
        description=req.description,
        priority=req.priority,
        created_by=user.get("user_id"),
    )
    return {
        "id": session.id,
        "session_id": session.session_id,
        "status": session.status,
    }


@api_router.put("/test-sessions/{session_id}/status")
async def update_test_session_status(
    session_id: str,
    status: str,
    user: dict = Depends(require_permission(Permission.SESSIONS_WRITE)),
):
    """Update test session status."""
    repo = await get_db_repo()
    if repo is None:
        raise HTTPException(
            status_code=503, detail="Database not enabled. Set DATABASE_ENABLED=true"
        )
    session = await repo.update_session_status(session_id, status)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session_id": session.session_id, "status": session.status}


@api_router.get("/test-results")
async def get_test_results(
    session_id: str | None = None,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
    user: dict = Depends(get_current_user),
):
    """Get test results."""
    repo = await get_db_repo()
    if repo is None:
        raise HTTPException(
            status_code=503, detail="Database not enabled. Set DATABASE_ENABLED=true"
        )
    results = await repo.get_test_results(
        session_id=session_id, status=status, limit=limit, offset=offset
    )
    return [
        {
            "id": r.id,
            "session_id": r.session_id,
            "test_id": r.test_id,
            "test_name": r.test_name,
            "status": r.status,
            "severity": r.severity,
            "category": r.category,
            "component": r.component,
            "agent_name": r.agent_name,
            "error_message": r.error_message,
            "execution_time_ms": r.execution_time_ms,
            "created_at": r.created_at.isoformat(),
        }
        for r in results
    ]


@api_router.post("/test-results")
async def add_test_result(
    req: TestResultCreate,
    user: dict = Depends(require_permission(Permission.SESSIONS_WRITE)),
):
    """Add a test result."""
    repo = await get_db_repo()
    if repo is None:
        raise HTTPException(
            status_code=503, detail="Database not enabled. Set DATABASE_ENABLED=true"
        )
    result = await repo.add_test_result(req.model_dump())
    return {"id": result.id, "test_id": result.test_id, "status": result.status}


@api_router.get("/test-results/{session_id}/summary")
async def get_test_results_summary(
    session_id: str,
    user: dict = Depends(get_current_user),
):
    """Get summary of test results for a session."""
    repo = await get_db_repo()
    if repo is None:
        raise HTTPException(
            status_code=503, detail="Database not enabled. Set DATABASE_ENABLED=true"
        )
    summary = await repo.get_session_results_summary(session_id)
    return summary


@api_router.get("/test-metrics/trends")
async def get_quality_trends(
    days: int = 30,
    user: dict = Depends(get_current_user),
):
    """Get quality trends over time."""
    repo = await get_db_repo()
    if repo is None:
        raise HTTPException(
            status_code=503, detail="Database not enabled. Set DATABASE_ENABLED=true"
        )
    trends = await repo.get_quality_trends(days=days)
    return trends


# ---------------------------------------------------------------------------
# Multi-Tenant endpoints
# ---------------------------------------------------------------------------

MULTI_TENANT_ENABLED = os.getenv("MULTI_TENANT_ENABLED", "false").lower() == "true"


class TenantCreate(BaseModel):
    tenant_id: str
    name: str
    slug: str
    owner_email: str
    plan: str = "free"


class TenantUpdate(BaseModel):
    name: str | None = None
    status: str | None = None
    plan: str | None = None
    max_sessions: int | None = None
    max_agents: int | None = None


class TenantUserInvite(BaseModel):
    email: str
    user_id: str
    role: str = "member"


async def get_tenant_repo():
    """Get tenant repository instance."""
    if not MULTI_TENANT_ENABLED or not DATABASE_ENABLED:
        return None
    try:
        from shared.database.tenant_repository import TenantRepository
        from shared.database.models import get_session

        session = await get_session()
        return TenantRepository(session)
    except Exception:
        return None


def _require_tenant_enabled():
    """Raise 503 if multi-tenancy is not enabled."""
    if not MULTI_TENANT_ENABLED:
        raise HTTPException(
            status_code=503, detail="Multi-tenancy not enabled. Set MULTI_TENANT_ENABLED=true"
        )
    if not DATABASE_ENABLED:
        raise HTTPException(
            status_code=503, detail="Database not enabled. Set DATABASE_ENABLED=true"
        )


@api_router.get("/tenants")
async def list_tenants(
    user: dict = Depends(get_current_user),
):
    """List tenants (admin only)."""
    _require_tenant_enabled()

    if user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    repo = await get_tenant_repo()
    if repo is None:
        raise HTTPException(status_code=503, detail="Tenant database unavailable")

    tenants = await repo.list_tenants()
    return {
        "tenants": [
            {
                "tenant_id": t.tenant_id,
                "name": t.name,
                "slug": t.slug,
                "status": t.status,
                "plan": t.plan,
                "owner_email": t.owner_email,
                "is_active": t.is_active,
                "created_at": t.created_at.isoformat(),
            }
            for t in tenants
        ]
    }


@api_router.post("/tenants")
async def create_tenant(
    req: TenantCreate,
    user: dict = Depends(get_current_user),
):
    """Create a new tenant (admin only)."""
    _require_tenant_enabled()

    if user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    repo = await get_tenant_repo()
    if repo is None:
        raise HTTPException(status_code=503, detail="Tenant database unavailable")

    tenant = await repo.create_tenant(
        tenant_id=req.tenant_id,
        name=req.name,
        slug=req.slug,
        owner_email=req.owner_email,
        plan=req.plan,
    )
    return {
        "tenant_id": tenant.tenant_id,
        "name": tenant.name,
        "slug": tenant.slug,
        "status": tenant.status,
        "plan": tenant.plan,
    }


@api_router.get("/tenants/{tenant_id}")
async def get_tenant(
    tenant_id: str,
    user: dict = Depends(get_current_user),
):
    """Get tenant details."""
    _require_tenant_enabled()

    repo = await get_tenant_repo()
    if repo is None:
        raise HTTPException(status_code=503, detail="Tenant database unavailable")

    tenant = await repo.get_tenant(tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    return {
        "tenant_id": tenant.tenant_id,
        "name": tenant.name,
        "slug": tenant.slug,
        "status": tenant.status,
        "plan": tenant.plan,
        "owner_email": tenant.owner_email,
        "max_sessions": tenant.max_sessions,
        "max_agents": tenant.max_agents,
        "is_active": tenant.is_active,
        "created_at": tenant.created_at.isoformat(),
    }


@api_router.put("/tenants/{tenant_id}")
async def update_tenant(
    tenant_id: str,
    req: TenantUpdate,
    user: dict = Depends(get_current_user),
):
    """Update tenant (admin only)."""
    _require_tenant_enabled()

    if user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    repo = await get_tenant_repo()
    if repo is None:
        raise HTTPException(status_code=503, detail="Tenant database unavailable")

    updates = req.model_dump(exclude_none=True)
    tenant = await repo.update_tenant(tenant_id, updates)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    return {
        "tenant_id": tenant.tenant_id,
        "name": tenant.name,
        "status": tenant.status,
        "plan": tenant.plan,
    }


@api_router.delete("/tenants/{tenant_id}")
async def delete_tenant(
    tenant_id: str,
    user: dict = Depends(get_current_user),
):
    """Delete tenant (admin only)."""
    _require_tenant_enabled()

    if user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    repo = await get_tenant_repo()
    if repo is None:
        raise HTTPException(status_code=503, detail="Tenant database unavailable")

    deleted = await repo.delete_tenant(tenant_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Tenant not found")

    return {"tenant_id": tenant_id, "status": "deleted"}


@api_router.get("/tenants/{tenant_id}/users")
async def list_tenant_users(
    tenant_id: str,
    user: dict = Depends(get_current_user),
):
    """List users in a tenant."""
    _require_tenant_enabled()

    repo = await get_tenant_repo()
    if repo is None:
        raise HTTPException(status_code=503, detail="Tenant database unavailable")

    users = await repo.list_users(tenant_id)
    return {
        "users": [
            {
                "user_id": u.user_id,
                "email": u.email,
                "role": u.role,
                "is_owner": u.is_owner,
                "is_admin": u.is_admin,
                "created_at": u.created_at.isoformat(),
            }
            for u in users
        ]
    }


@api_router.post("/tenants/{tenant_id}/users")
async def invite_tenant_user(
    tenant_id: str,
    req: TenantUserInvite,
    user: dict = Depends(get_current_user),
):
    """Invite user to tenant."""
    _require_tenant_enabled()

    if user.get("role") not in ("super_admin", "org_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    repo = await get_tenant_repo()
    if repo is None:
        raise HTTPException(status_code=503, detail="Tenant database unavailable")

    tenant_user = await repo.add_user(
        tenant_id=tenant_id,
        user_id=req.user_id,
        email=req.email,
        role=req.role,
    )
    return {
        "user_id": tenant_user.user_id,
        "email": tenant_user.email,
        "role": tenant_user.role,
        "status": "invited",
    }


@api_router.delete("/tenants/{tenant_id}/users/{user_id}")
async def remove_tenant_user(
    tenant_id: str,
    user_id: str,
    user: dict = Depends(get_current_user),
):
    """Remove user from tenant."""
    _require_tenant_enabled()

    if user.get("role") not in ("super_admin", "org_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    repo = await get_tenant_repo()
    if repo is None:
        raise HTTPException(status_code=503, detail="Tenant database unavailable")

    removed = await repo.remove_user(tenant_id, user_id)
    if not removed:
        raise HTTPException(status_code=404, detail="User not found in tenant")

    return {"user_id": user_id, "status": "removed"}


# ---------------------------------------------------------------------------
# AGNOS OS Agent Registration endpoints
# ---------------------------------------------------------------------------

@api_router.get("/agents/registration-status")
async def get_agent_registration_status(
    user: dict = Depends(get_current_user),
):
    """Get agent registration status with agnosticos."""
    try:
        from config.agnos_agent_registration import agent_registry_client

        return agent_registry_client.get_registration_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/agents/register-agnostic")
async def register_agnostic_agents(
    user: dict = Depends(get_current_user),
):
    """Register all Agnostic agents with agnosticos."""
    if user.get("role") not in ("super_admin", "org_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        from config.agnos_agent_registration import agent_registry_client

        results = await agent_registry_client.register_all_agents()
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/agents/deregister-agnostic")
async def deregister_agnostic_agents(
    user: dict = Depends(get_current_user),
):
    """Deregister all Agnostic agents from agnosticos."""
    if user.get("role") not in ("super_admin", "org_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        from config.agnos_agent_registration import agent_registry_client

        results = await agent_registry_client.deregister_all_agents()
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
