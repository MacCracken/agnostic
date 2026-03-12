"""MCP (Model Context Protocol) server auto-registration endpoints.

Exposes AGNOSTIC's QA tools as an MCP HTTP server that SecureYeoman
auto-discovers via ``/api/v1/a2a/capabilities``.  The tool manifest is
served at ``/api/v1/mcp/tools`` and individual tool invocations are
handled at ``/api/v1/mcp/invoke``.
"""

import logging
import os
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from webgui.routes.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()

MCP_ENABLED = os.getenv("MCP_SERVER_ENABLED", "true").lower() == "true"

# ---------------------------------------------------------------------------
# MCP tool definitions — the full set AGNOSTIC advertises
# ---------------------------------------------------------------------------

MCP_TOOLS: list[dict[str, Any]] = [
    # --- Core QA tools ---
    {
        "name": "agnostic_submit_task",
        "description": "Submit a QA task to the 6-agent pipeline",
        "category": "qa",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "description": {"type": "string"},
                "target_url": {"type": "string"},
                "priority": {
                    "type": "string",
                    "enum": ["critical", "high", "medium", "low"],
                },
                "agents": {"type": "array", "items": {"type": "string"}},
                "standards": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["title", "description"],
        },
    },
    {
        "name": "agnostic_task_status",
        "description": "Get the status of a QA task by ID",
        "category": "qa",
        "inputSchema": {
            "type": "object",
            "properties": {"task_id": {"type": "string"}},
            "required": ["task_id"],
        },
    },
    {
        "name": "agnostic_list_sessions",
        "description": "List active QA sessions",
        "category": "qa",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "agnostic_agent_status",
        "description": "Get status of all 6 QA agents",
        "category": "qa",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "agnostic_dashboard",
        "description": "Full dashboard snapshot: agents, sessions, metrics",
        "category": "qa",
        "inputSchema": {"type": "object", "properties": {}},
    },
    # --- Security tools ---
    {
        "name": "agnostic_security_scan",
        "description": "Run OWASP/GDPR/PCI DSS/SOC 2 compliance scan",
        "category": "security",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target_url": {"type": "string"},
                "standards": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": ["target_url"],
        },
    },
    {
        "name": "agnostic_security_findings",
        "description": "Retrieve security findings for a session",
        "category": "security",
        "inputSchema": {
            "type": "object",
            "properties": {"session_id": {"type": "string"}},
            "required": ["session_id"],
        },
    },
    # --- Performance tools ---
    {
        "name": "agnostic_performance_test",
        "description": "Run load testing and P95/P99 latency profiling",
        "category": "performance",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target_url": {"type": "string"},
                "duration_seconds": {"type": "integer", "default": 60},
                "concurrency": {"type": "integer", "default": 10},
            },
            "required": ["target_url"],
        },
    },
    {
        "name": "agnostic_performance_results",
        "description": "Retrieve performance test results for a session",
        "category": "performance",
        "inputSchema": {
            "type": "object",
            "properties": {"session_id": {"type": "string"}},
            "required": ["session_id"],
        },
    },
    # --- Structured results ---
    {
        "name": "agnostic_structured_results",
        "description": "Get typed results (security, perf, tests) for YEOMAN actions",
        "category": "qa",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "result_type": {
                    "type": "string",
                    "enum": ["security", "performance", "test_execution"],
                },
            },
            "required": ["session_id"],
        },
    },
    {
        "name": "agnostic_session_diff",
        "description": "Compare two QA sessions for regression analysis",
        "category": "qa",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_a": {"type": "string"},
                "session_b": {"type": "string"},
            },
            "required": ["session_a", "session_b"],
        },
    },
    {
        "name": "agnostic_quality_trends",
        "description": "Quality metrics over time: pass rates, regression frequency",
        "category": "qa",
        "inputSchema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "default": 30},
            },
        },
    },
    {
        "name": "agnostic_quality_dashboard",
        "description": "Embeddable quality summary: pass/fail, compliance, coverage",
        "category": "qa",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "agnostic_qa_orchestrate",
        "description": "Orchestrate a full QA run: plan, execute, analyse, report",
        "category": "qa",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target_url": {"type": "string"},
                "scope": {
                    "type": "string",
                    "enum": ["quick", "standard", "comprehensive"],
                    "default": "standard",
                },
            },
            "required": ["target_url"],
        },
    },
    # --- Reports ---
    {
        "name": "agnostic_generate_report",
        "description": "Generate a QA report for a session",
        "category": "reports",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "format": {
                    "type": "string",
                    "enum": ["json", "html", "pdf"],
                    "default": "json",
                },
            },
            "required": ["session_id"],
        },
    },
    {
        "name": "agnostic_list_reports",
        "description": "List available QA reports",
        "category": "reports",
        "inputSchema": {"type": "object", "properties": {}},
    },
    # --- REST proxy tools ---
    {
        "name": "agnostic_health",
        "description": "Health check: Redis, RabbitMQ, agent liveness",
        "category": "system",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "agnostic_metrics",
        "description": "Prometheus-compatible metrics",
        "category": "system",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "agnostic_agent_metrics",
        "description": "Per-agent task counts, success rates, LLM token usage",
        "category": "system",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "agnostic_llm_usage",
        "description": "Aggregated LLM usage: call counts, error rates, by method",
        "category": "system",
        "inputSchema": {"type": "object", "properties": {}},
    },
    # --- A2A ---
    {
        "name": "agnostic_a2a_delegate",
        "description": "Delegate a QA task via A2A protocol",
        "category": "a2a",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "description": {"type": "string"},
                "target_url": {"type": "string"},
                "priority": {"type": "string"},
            },
            "required": ["title", "description"],
        },
    },
    {
        "name": "agnostic_a2a_status",
        "description": "Query task status via A2A protocol",
        "category": "a2a",
        "inputSchema": {
            "type": "object",
            "properties": {"task_id": {"type": "string"}},
            "required": ["task_id"],
        },
    },
    {
        "name": "agnostic_a2a_heartbeat",
        "description": "Send A2A heartbeat",
        "category": "a2a",
        "inputSchema": {"type": "object", "properties": {}},
    },
    # --- Webhook management ---
    {
        "name": "agnostic_subscribe_webhook",
        "description": "Subscribe to task completion webhooks",
        "category": "webhooks",
        "inputSchema": {
            "type": "object",
            "properties": {
                "callback_url": {"type": "string"},
                "events": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": ["task.completed"],
                },
                "secret": {"type": "string"},
            },
            "required": ["callback_url"],
        },
    },
    {
        "name": "agnostic_event_stream",
        "description": "Subscribe to SSE event stream for real-time QA updates",
        "category": "streaming",
        "inputSchema": {
            "type": "object",
            "properties": {
                "channels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": ["all"],
                },
            },
        },
    },
]

# ---------------------------------------------------------------------------
# MCP endpoint — route to internal API based on tool name
# ---------------------------------------------------------------------------

# Map tool name -> (HTTP method, internal API path)
_TOOL_ROUTES: dict[str, tuple[str, str]] = {
    "agnostic_submit_task": ("POST", "/api/v1/tasks"),
    "agnostic_task_status": ("GET", "/api/v1/tasks/{task_id}"),
    "agnostic_list_sessions": ("GET", "/api/v1/dashboard/sessions"),
    "agnostic_agent_status": ("GET", "/api/v1/dashboard/agents"),
    "agnostic_dashboard": ("GET", "/api/v1/dashboard"),
    "agnostic_security_scan": ("POST", "/api/v1/tasks"),
    "agnostic_security_findings": ("GET", "/api/v1/results/structured/{session_id}"),
    "agnostic_performance_test": ("POST", "/api/v1/tasks"),
    "agnostic_performance_results": ("GET", "/api/v1/results/structured/{session_id}"),
    "agnostic_structured_results": ("GET", "/api/v1/results/structured/{session_id}"),
    "agnostic_session_diff": ("GET", "/api/v1/sessions/compare"),
    "agnostic_quality_trends": ("GET", "/api/v1/dashboard/metrics"),
    "agnostic_quality_dashboard": ("GET", "/api/v1/dashboard/widget"),
    "agnostic_qa_orchestrate": ("POST", "/api/v1/tasks"),
    "agnostic_generate_report": ("POST", "/api/v1/reports/generate"),
    "agnostic_list_reports": ("GET", "/api/v1/reports"),
    "agnostic_health": ("GET", "/health"),
    "agnostic_metrics": ("GET", "/api/v1/metrics"),
    "agnostic_agent_metrics": ("GET", "/api/v1/dashboard/agent-metrics"),
    "agnostic_llm_usage": ("GET", "/api/v1/dashboard/llm"),
    "agnostic_a2a_delegate": ("POST", "/api/v1/a2a/receive"),
    "agnostic_a2a_status": ("POST", "/api/v1/a2a/receive"),
    "agnostic_a2a_heartbeat": ("POST", "/api/v1/a2a/receive"),
    "agnostic_subscribe_webhook": ("POST", "/api/v1/tasks"),
    "agnostic_event_stream": ("GET", "/api/v1/yeoman/events/stream"),
}


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class MCPInvokeRequest(BaseModel):
    tool: str = Field(..., min_length=1, max_length=100)
    arguments: dict[str, Any] = Field(default_factory=dict)
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))


class MCPInvokeResponse(BaseModel):
    request_id: str
    tool: str
    result: Any = None
    error: str | None = None
    timestamp: str


class MCPToolsResponse(BaseModel):
    tools: list[dict[str, Any]]
    total: int
    server: dict[str, Any]


class MCPServerInfoResponse(BaseModel):
    name: str
    version: str
    protocol_version: str
    capabilities: dict[str, Any]
    tool_count: int
    categories: list[str]
    health_endpoint: str
    auth_methods: list[str]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


def _require_mcp_enabled() -> None:
    if not MCP_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="MCP server not enabled. Set MCP_SERVER_ENABLED=true",
        )


@router.get("/mcp/tools", response_model=MCPToolsResponse)
async def list_mcp_tools(
    category: str | None = None,
    _user: dict = Depends(get_current_user),
):
    """List all MCP tools AGNOSTIC exposes.

    SecureYeoman auto-discovers these via Connections > MCP tab.
    """
    _require_mcp_enabled()
    tools = MCP_TOOLS
    if category:
        tools = [t for t in tools if t.get("category") == category]
    return {
        "tools": tools,
        "total": len(tools),
        "server": {
            "name": "agnostic-qa",
            "version": "1.0",
            "protocol": "mcp-http",
        },
    }


@router.get("/mcp/server-info", response_model=MCPServerInfoResponse)
async def mcp_server_info(_user: dict = Depends(get_current_user)):
    """MCP server metadata for auto-registration handshake."""
    _require_mcp_enabled()
    return {
        "name": "agnostic-qa",
        "version": "1.0",
        "protocol_version": "2024-11-05",
        "capabilities": {
            "tools": {"listChanged": False},
        },
        "tool_count": len(MCP_TOOLS),
        "categories": sorted({t["category"] for t in MCP_TOOLS}),
        "health_endpoint": "/health",
        "auth_methods": ["api_key", "bearer_jwt"],
    }


@router.post("/mcp/invoke", response_model=MCPInvokeResponse)
async def invoke_mcp_tool(
    req: MCPInvokeRequest,
    user: dict = Depends(get_current_user),
):
    """Invoke an MCP tool by name.

    This is the server-side execution entry-point that SecureYeoman calls
    after discovering tools via ``/v1/mcp/tools``.
    """
    _require_mcp_enabled()

    route = _TOOL_ROUTES.get(req.tool)
    if not route:
        raise HTTPException(status_code=404, detail=f"Unknown MCP tool: {req.tool}")

    from shared.audit import AuditAction, audit_log

    audit_log(
        AuditAction.TOOL_INVOKED,
        actor=user.get("user_id", "unknown"),
        resource_type="mcp_tool",
        detail={"tool": req.tool, "request_id": req.request_id},
    )

    try:
        result = await _dispatch_tool(req.tool, req.arguments, user)
        return MCPInvokeResponse(
            request_id=req.request_id,
            tool=req.tool,
            result=result,
            timestamp=datetime.now(UTC).isoformat(),
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("MCP tool %s failed: %s", req.tool, exc)
        return MCPInvokeResponse(
            request_id=req.request_id,
            tool=req.tool,
            error=str(exc),
            timestamp=datetime.now(UTC).isoformat(),
        )


async def _dispatch_tool(tool_name: str, arguments: dict[str, Any], user: dict) -> Any:
    """Route MCP tool invocations to internal API handlers."""
    # Task submission tools
    if tool_name in (
        "agnostic_submit_task",
        "agnostic_security_scan",
        "agnostic_performance_test",
        "agnostic_qa_orchestrate",
    ):
        from webgui.routes.tasks import TaskSubmitRequest, submit_task

        # Map tool-specific args to TaskSubmitRequest
        agents: list[str] = arguments.get("agents", [])
        if tool_name == "agnostic_security_scan":
            agents = agents or ["security-compliance"]
        elif tool_name == "agnostic_performance_test":
            agents = agents or ["performance"]

        task_req = TaskSubmitRequest(
            title=arguments.get("title", f"MCP: {tool_name}"),
            description=arguments.get(
                "description", f"Invoked via MCP tool {tool_name}"
            ),
            target_url=arguments.get("target_url"),
            priority=arguments.get("priority", "high"),
            agents=agents,
            standards=arguments.get("standards", []),
        )
        result = await submit_task(task_req, user)
        return {
            "task_id": result.task_id,
            "session_id": result.session_id,
            "status": result.status,
        }

    # Task status
    if tool_name == "agnostic_task_status":
        from webgui.routes.tasks import get_task

        return await get_task(arguments["task_id"], user)

    # Dashboard tools
    if tool_name == "agnostic_dashboard":
        from webgui.routes.dashboard import get_dashboard

        return await get_dashboard(user)

    if tool_name == "agnostic_list_sessions":
        from webgui.routes.dashboard import get_dashboard_sessions

        return await get_dashboard_sessions(user)

    if tool_name == "agnostic_agent_status":
        from webgui.routes.dashboard import get_dashboard_agents

        return await get_dashboard_agents(user)

    if tool_name == "agnostic_agent_metrics":
        from webgui.routes.dashboard import get_agent_dashboard

        return await get_agent_dashboard(user)

    if tool_name == "agnostic_llm_usage":
        from webgui.routes.dashboard import get_llm_dashboard

        return await get_llm_dashboard(user)

    if tool_name == "agnostic_quality_dashboard":
        from webgui.routes.dashboard import get_embeddable_widget

        return await get_embeddable_widget(user)

    # Structured results
    if tool_name in (
        "agnostic_structured_results",
        "agnostic_security_findings",
        "agnostic_performance_results",
    ):
        from webgui.routes.integration import get_structured_results

        result_type = arguments.get("result_type")
        if tool_name == "agnostic_security_findings":
            result_type = "security"
        elif tool_name == "agnostic_performance_results":
            result_type = "performance"
        return await get_structured_results(arguments["session_id"], result_type, user)

    # Session diff
    if tool_name == "agnostic_session_diff":
        from webgui.routes.sessions import compare_sessions

        return await compare_sessions(
            arguments["session_a"], arguments["session_b"], user
        )

    # Quality trends
    if tool_name == "agnostic_quality_trends":
        from webgui.routes.dashboard import get_dashboard_metrics

        return await get_dashboard_metrics(user)

    # Reports
    if tool_name == "agnostic_generate_report":
        from webgui.routes.reports import generate_report

        return await generate_report(
            arguments["session_id"], arguments.get("format", "json"), user
        )

    if tool_name == "agnostic_list_reports":
        from webgui.routes.reports import list_reports

        return await list_reports(user)

    # A2A delegation
    if tool_name == "agnostic_a2a_delegate":
        from webgui.routes.tasks import A2AMessage, receive_a2a_message

        msg = A2AMessage(
            id=str(uuid.uuid4()),
            type="a2a:delegate",
            fromPeerId="secureyeoman",
            toPeerId="agnostic-qa",
            payload=arguments,
            timestamp=int(datetime.now(UTC).timestamp() * 1000),
        )
        return await receive_a2a_message(msg, user)

    if tool_name == "agnostic_a2a_status":
        from webgui.routes.tasks import A2AMessage, receive_a2a_message

        msg = A2AMessage(
            id=str(uuid.uuid4()),
            type="a2a:status_query",
            fromPeerId="secureyeoman",
            toPeerId="agnostic-qa",
            payload=arguments,
            timestamp=int(datetime.now(UTC).timestamp() * 1000),
        )
        return await receive_a2a_message(msg, user)

    if tool_name == "agnostic_a2a_heartbeat":
        from webgui.routes.tasks import A2AMessage, receive_a2a_message

        msg = A2AMessage(
            id=str(uuid.uuid4()),
            type="a2a:heartbeat",
            fromPeerId="secureyeoman",
            toPeerId="agnostic-qa",
            payload={},
            timestamp=int(datetime.now(UTC).timestamp() * 1000),
        )
        return await receive_a2a_message(msg, user)

    # Webhook subscription
    if tool_name == "agnostic_subscribe_webhook":
        callback_url = arguments.get("callback_url")
        if not callback_url:
            raise HTTPException(status_code=400, detail="callback_url is required")
        # Validate callback URL against SSRF
        from webgui.routes.dependencies import _validate_callback_url

        try:
            _validate_callback_url(callback_url)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

        events = arguments.get("events", ["task.completed"])
        secret = arguments.get("secret")
        sub_id = str(uuid.uuid4())

        # Store subscription in Redis for webhook delivery
        from config.environment import config as app_config

        redis_client = app_config.get_async_redis_client()
        sub_data = {
            "id": sub_id,
            "callback_url": callback_url,
            "events": events,
            "has_secret": bool(secret),
            "created_by": user.get("user_id", "unknown"),
            "created_at": datetime.now(UTC).isoformat(),
        }
        import json as _json

        await redis_client.setex(
            f"webhook_sub:{sub_id}", 86400 * 30, _json.dumps(sub_data)
        )
        return {
            "subscription_id": sub_id,
            "callback_url": callback_url,
            "events": events,
            "status": "active",
        }

    # Event stream info (SSE is not invocable via MCP — return connection info)
    if tool_name == "agnostic_event_stream":
        channels = arguments.get("channels", ["all"])
        return {
            "stream_url": "/api/v1/yeoman/events/stream",
            "protocol": "text/event-stream",
            "channels": channels,
            "note": "Connect via SSE client to the stream_url with Bearer auth. "
            "This tool returns connection info — real-time streaming requires "
            "a persistent SSE connection.",
        }

    # Health
    if tool_name == "agnostic_health":
        # Import the app-level health check
        return {"status": "ok", "note": "Use GET /health for full details"}

    if tool_name == "agnostic_metrics":
        from shared.metrics import get_metrics_text

        return {"metrics": get_metrics_text()}

    raise HTTPException(
        status_code=404, detail=f"Tool dispatch not implemented: {tool_name}"
    )
