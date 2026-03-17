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


class A2AReceiveResponse(BaseModel):
    """Generic A2A receive response — allows extra fields per message type."""

    model_config = {"extra": "allow"}

    accepted: bool
    message_id: str


class A2ACapabilitiesResponse(BaseModel):
    capabilities: list[dict[str, Any]]
    mcp: dict[str, Any]
    webhooks: dict[str, Any]
    auth_methods: list[str]


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
# Task submission endpoints
# ---------------------------------------------------------------------------


def _crew_to_task_response(crew_result) -> TaskStatusResponse:
    """Convert a CrewRunResponse to a TaskStatusResponse for backward compat."""
    return TaskStatusResponse(
        task_id=crew_result.task_id,
        session_id=crew_result.session_id,
        status=crew_result.status,
        created_at=crew_result.created_at,
        updated_at=crew_result.created_at,
        result=None,
    )


@router.post("/tasks", response_model=TaskStatusResponse, status_code=201)
async def submit_task(
    req: TaskSubmitRequest,
    user: dict = Depends(get_current_user),
):
    """Submit a quality task. Routes through the generic crew builder."""
    from config.environment import config
    from shared.database.tenants import tenant_manager
    from webgui.routes.crews import CrewRunRequest, run_crew

    # SSRF validation on callback URL
    if req.callback_url:
        try:
            _validate_callback_url(req.callback_url)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    # Tenant rate limit check
    tenant_id = user.get("tenant_id", tenant_manager.default_tenant_id)
    if tenant_manager.enabled:
        redis_client = config.get_async_redis_client()
        if not await tenant_manager.check_rate_limit(redis_client, tenant_id):
            audit_log(
                AuditAction.RATE_LIMIT_EXCEEDED,
                actor=user.get("user_id"),
                tenant_id=tenant_id,
            )
            raise HTTPException(status_code=429, detail="Rate limit exceeded")

    # Build description with standards/goals context
    desc_parts = [req.description]
    if req.standards:
        desc_parts.append(f"Standards: {', '.join(req.standards)}")
    if req.business_goals and req.business_goals != "Ensure quality and functionality":
        desc_parts.append(f"Business goals: {req.business_goals}")
    if req.constraints and req.constraints != "Standard testing environment":
        desc_parts.append(f"Constraints: {req.constraints}")

    crew_req = CrewRunRequest(
        preset="quality-standard",
        title=req.title,
        description="\n".join(desc_parts),
        target_url=req.target_url,
        priority=req.priority,
        callback_url=req.callback_url,
        callback_secret=req.callback_secret,
    )
    crew_result = await run_crew(crew_req, user)

    audit_log(
        AuditAction.TASK_SUBMITTED,
        actor=user.get("user_id"),
        resource_type="task",
        resource_id=crew_result.task_id,
    )

    return _crew_to_task_response(crew_result)


@router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_task(task_id: str, user: dict = Depends(get_current_user)):
    """Poll task status by task_id."""
    if not _TASK_ID_RE.match(task_id):
        raise HTTPException(status_code=400, detail="Invalid task ID format")

    from config.environment import config
    from shared.database.tenants import tenant_manager

    redis_client = config.get_async_redis_client()
    tenant_id = user.get("tenant_id", tenant_manager.default_tenant_id)
    task_redis_key = tenant_manager.task_key(tenant_id, task_id)
    data = await redis_client.get(task_redis_key)
    if not data:
        raise HTTPException(status_code=404, detail="Task not found")

    record = json.loads(data)
    return TaskStatusResponse(**record)


# ---------------------------------------------------------------------------
# Task cancellation and retry
# ---------------------------------------------------------------------------


class TaskCancelResponse(BaseModel):
    task_id: str
    status: str
    message: str


class TaskRetryResponse(BaseModel):
    original_task_id: str
    new_task_id: str
    session_id: str
    status: str


@router.delete("/tasks/{task_id}", response_model=TaskCancelResponse)
async def cancel_task(task_id: str, user: dict = Depends(get_current_user)):
    """Cancel a pending or running task."""
    if not _TASK_ID_RE.match(task_id):
        raise HTTPException(status_code=400, detail="Invalid task ID format")

    from config.environment import config
    from shared.database.tenants import tenant_manager

    redis_client = config.get_async_redis_client()
    tenant_id = user.get("tenant_id", tenant_manager.default_tenant_id)
    task_redis_key = tenant_manager.task_key(tenant_id, task_id)
    data = await redis_client.get(task_redis_key)
    if not data:
        raise HTTPException(status_code=404, detail="Task not found")

    record = json.loads(data)
    current_status = record.get("status")

    if current_status in ("completed", "failed", "cancelled"):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot cancel task in '{current_status}' state",
        )

    record["status"] = "cancelled"
    record["updated_at"] = datetime.now(UTC).isoformat()
    await redis_client.setex(task_redis_key, 86400, json.dumps(record))

    audit_log(
        AuditAction.TASK_CANCELLED,
        actor=user.get("user_id"),
        resource_type="task",
        resource_id=task_id,
    )

    return TaskCancelResponse(
        task_id=task_id,
        status="cancelled",
        message="Task cancelled successfully",
    )


@router.post(
    "/tasks/{task_id}/retry", response_model=TaskRetryResponse, status_code=201
)
async def retry_task(task_id: str, user: dict = Depends(get_current_user)):
    """Retry a failed or cancelled task by creating a new task with the same parameters."""
    if not _TASK_ID_RE.match(task_id):
        raise HTTPException(status_code=400, detail="Invalid task ID format")

    from config.environment import config
    from shared.database.tenants import tenant_manager

    redis_client = config.get_async_redis_client()
    tenant_id = user.get("tenant_id", tenant_manager.default_tenant_id)
    task_redis_key = tenant_manager.task_key(tenant_id, task_id)
    data = await redis_client.get(task_redis_key)
    if not data:
        raise HTTPException(status_code=404, detail="Task not found")

    record = json.loads(data)
    current_status = record.get("status")

    if current_status not in ("failed", "cancelled"):
        raise HTTPException(
            status_code=409,
            detail=f"Can only retry failed or cancelled tasks, current status: '{current_status}'",
        )

    # Look up original requirements from the session key
    original_session_id = record.get("session_id", "")
    req_key = tenant_manager.task_key(tenant_id, f"req:{task_id}")
    req_data = await redis_client.get(req_key)

    # Build new task from stored requirements or minimal fallback
    if req_data:
        requirements = json.loads(req_data)
        task_req = TaskSubmitRequest(
            title=requirements.get("title", f"Retry of {task_id}"),
            description=requirements.get("description", f"Retry of task {task_id}"),
            target_url=requirements.get("target_url"),
            priority=requirements.get("priority", "high"),
            agents=requirements.get("agents", []),
            standards=requirements.get("standards", []),
            business_goals=requirements.get(
                "business_goals", "Ensure quality and functionality"
            ),
            constraints=requirements.get("constraints", "Standard testing environment"),
        )
    else:
        task_req = TaskSubmitRequest(
            title=f"Retry of {task_id}",
            description=f"Automated retry of failed task {task_id} (session: {original_session_id})",
        )

    result = await submit_task(task_req, user)

    audit_log(
        AuditAction.TASK_SUBMITTED,
        actor=user.get("user_id"),
        resource_type="task",
        resource_id=result.task_id,
        detail={"retry_of": task_id},
    )

    return TaskRetryResponse(
        original_task_id=task_id,
        new_task_id=result.task_id,
        session_id=result.session_id,
        status="pending",
    )


# ---------------------------------------------------------------------------
# Agent-specific convenience endpoints
# ---------------------------------------------------------------------------


@router.post("/tasks/security", response_model=TaskStatusResponse)
async def submit_security_task(
    req: TaskSubmitRequest,
    user: dict = Depends(get_current_user),
):
    """Submit a security-focused task with a targeted security crew."""
    from webgui.routes.crews import CrewRunRequest, TeamSpec, run_crew

    standards = req.standards or ["OWASP", "GDPR", "PCI DSS"]
    crew_req = CrewRunRequest(
        team=TeamSpec(
            members=[
                {"role": "Security Lead", "context": f"Standards: {', '.join(standards)}", "lead": True},
                {"role": "Security & Compliance Specialist", "context": "Vulnerability scanning, penetration testing"},
                {"role": "QA Analyst", "context": "Security findings aggregation and risk scoring"},
            ],
            project_context=req.description,
        ),
        title=req.title,
        description=f"{req.description}\nStandards: {', '.join(standards)}",
        target_url=req.target_url,
        priority=req.priority,
    )
    result = await run_crew(crew_req, user)
    return _crew_to_task_response(result)


@router.post("/tasks/performance", response_model=TaskStatusResponse)
async def submit_performance_task(
    req: TaskSubmitRequest,
    user: dict = Depends(get_current_user),
):
    """Submit a performance-focused task with a targeted performance crew."""
    from webgui.routes.crews import CrewRunRequest, TeamSpec, run_crew

    crew_req = CrewRunRequest(
        team=TeamSpec(
            members=[
                {"role": "Performance & Resilience Specialist", "context": "Load testing, latency profiling, stress testing", "lead": True},
                {"role": "Infrastructure Monitor", "context": "System health, resource usage during tests"},
                {"role": "QA Analyst", "context": "Performance metrics aggregation and reporting"},
            ],
            project_context=req.description,
        ),
        title=req.title,
        description=f"{req.description}\nFocus: performance testing, load testing, latency profiling",
        target_url=req.target_url,
        priority=req.priority,
    )
    result = await run_crew(crew_req, user)
    return _crew_to_task_response(result)


@router.post("/tasks/regression", response_model=TaskStatusResponse)
async def submit_regression_task(
    req: TaskSubmitRequest,
    user: dict = Depends(get_current_user),
):
    """Submit a regression-focused task with a lean regression crew."""
    from webgui.routes.crews import CrewRunRequest, run_crew

    crew_req = CrewRunRequest(
        preset="quality-lean",
        title=req.title,
        description=f"{req.description}\nFocus: regression testing and test analysis",
        target_url=req.target_url,
        priority=req.priority,
    )
    result = await run_crew(crew_req, user)
    return _crew_to_task_response(result)


@router.post("/tasks/full", response_model=TaskStatusResponse)
async def submit_full_task(
    req: TaskSubmitRequest,
    user: dict = Depends(get_current_user),
):
    """Submit a comprehensive quality task with the large team."""
    from webgui.routes.crews import CrewRunRequest, run_crew

    crew_req = CrewRunRequest(
        preset="quality-large",
        title=req.title,
        description=req.description,
        target_url=req.target_url,
        priority=req.priority,
    )
    result = await run_crew(crew_req, user)
    return _crew_to_task_response(result)


# ---------------------------------------------------------------------------
# A2A (Agent-to-Agent) protocol endpoints
# ---------------------------------------------------------------------------

_A2A_RATE_LIMIT = int(os.getenv("A2A_RATE_LIMIT", "60"))  # requests per minute
_A2A_RATE_WINDOW = 60  # seconds


async def _check_a2a_rate_limit(peer_id: str) -> bool:
    """Return True if the peer is within the A2A rate limit."""
    try:
        from config.environment import config

        redis_client = config.get_async_redis_client()
        key = f"a2a_rate:{peer_id}"
        current = await redis_client.incr(key)
        if current == 1:
            await redis_client.expire(key, _A2A_RATE_WINDOW)
        return current <= _A2A_RATE_LIMIT
    except Exception:
        return True  # fail open


@router.post("/a2a/receive", response_model=A2AReceiveResponse)
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

    # Rate limit check
    try:
        if not await _check_a2a_rate_limit(msg.fromPeerId):
            raise HTTPException(status_code=429, detail="A2A rate limit exceeded")
    except HTTPException:
        raise
    except Exception:
        pass  # fail open if rate limit check fails

    if msg.type == "a2a:delegate":
        payload = msg.payload
        if not payload.get("description"):
            raise HTTPException(
                status_code=400, detail="Description is required for delegate tasks"
            )

        from webgui.routes.crews import CrewRunRequest, TeamSpec, run_crew

        # Resolve preset: explicit > domain+size > default quality-standard
        preset = payload.get("preset")
        if not preset and payload.get("domain") and not payload.get("team"):
            size = payload.get("size", "standard")
            preset = f"{payload['domain']}-{size}"
        if not preset and not payload.get("team") and not payload.get("agent_definitions"):
            preset = "quality-standard"

        crew_req = CrewRunRequest(
            preset=preset,
            agent_keys=payload.get("agent_keys", []),
            agent_definitions=payload.get("agent_definitions", []),
            team=TeamSpec.from_payload(payload.get("team")),
            title=payload.get("title", "A2A Crew Task"),
            description=payload.get("description", ""),
            target_url=payload.get("target_url"),
            priority=payload.get("priority", "high"),
        )
        crew_result = await run_crew(crew_req, user)
        audit_log(
            AuditAction.A2A_DELEGATE_RECEIVED,
            actor=msg.fromPeerId,
            resource_type="a2a",
            detail={
                "message_id": msg.id,
                "crew_id": crew_result.crew_id,
                "task_id": crew_result.task_id,
            },
        )
        return {
            "accepted": True,
            "crew_id": crew_result.crew_id,
            "task_id": crew_result.task_id,
            "message_id": msg.id,
        }

    if msg.type == "a2a:create_agent":
        # SY requesting dynamic agent creation
        payload = msg.payload
        required = {"agent_key", "name", "role", "goal", "backstory"}
        missing = required - set(payload.keys())
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"Missing required fields for agent creation: {missing}",
            )

        from webgui.routes.definitions import (
            AgentDefinitionRequest,
            create_definition,
        )

        defn_req = AgentDefinitionRequest(**{
            k: v for k, v in payload.items()
            if k in AgentDefinitionRequest.model_fields
        })
        # Use the authenticated user context
        await create_definition(defn_req, user)

        audit_log(
            AuditAction.A2A_DELEGATE_RECEIVED,
            actor=msg.fromPeerId,
            resource_type="a2a",
            detail={"message_id": msg.id, "agent_key": payload["agent_key"], "type": "create_agent"},
        )
        return {
            "accepted": True,
            "message_id": msg.id,
            "type": "agent_created",
            "agent_key": payload["agent_key"],
        }

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
        audit_log(
            AuditAction.A2A_RESULT_RECEIVED,
            actor=msg.fromPeerId,
            resource_type="a2a",
            detail={"message_id": msg.id},
        )
        return {"accepted": True, "message_id": msg.id, "type": "result_cached"}

    if msg.type == "a2a:status_query":
        # YEOMAN querying AGNOSTIC status
        audit_log(
            AuditAction.A2A_STATUS_QUERY,
            actor=msg.fromPeerId,
            resource_type="a2a",
            detail={"message_id": msg.id},
        )
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

    # Unknown message type — acknowledge receipt but take no action
    return {
        "accepted": True,
        "message_id": msg.id,
        "warning": f"Unhandled type: {msg.type}",
    }


@router.get("/a2a/capabilities", response_model=A2ACapabilitiesResponse)
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

    # Build dynamic capabilities from loaded presets
    capabilities: list[dict[str, Any]] = []
    try:
        from agents.factory import AgentFactory

        for preset in AgentFactory.list_presets():
            capabilities.append({
                "name": preset["name"],
                "description": preset.get("description", ""),
                "domain": preset.get("domain", "general"),
                "agent_count": preset.get("agent_count", 0),
                "version": "1.0",
            })
    except Exception:
        pass

    # Fallback: always advertise core quality preset if no presets loaded
    if not capabilities:
        capabilities = [
            {
                "name": "quality",
                "description": "Quality crew — security, performance, regression, compliance",
                "version": "1.0",
            },
        ]

    return {
        "capabilities": capabilities,
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
