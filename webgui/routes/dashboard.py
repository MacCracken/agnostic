"""Dashboard, alerts, and metrics endpoints."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from shared.version import VERSION
from webgui.routes.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class ItemListResponse(BaseModel):
    items: list[dict[str, Any]]
    total: int


class AlertListResponse(BaseModel):
    items: list[dict[str, Any]]
    total: int
    limit: int


class DashboardDataResponse(BaseModel):
    """Top-level dashboard export — allows extra fields."""

    model_config = {"extra": "allow"}


class MetricsDataResponse(BaseModel):
    """Resource metrics — allows extra fields from dataclass."""

    model_config = {"extra": "allow"}


class AgentMetricsDashboardResponse(BaseModel):
    agents: list[dict[str, Any]]


class LLMMetricsDashboardResponse(BaseModel):
    llm: dict[str, Any]


class GatewayHealthResponse(BaseModel):
    model_config = {"extra": "allow"}


class YeomanStatusResponse(BaseModel):
    enabled: bool = False
    cached_results: dict[str, Any] = {}
    peer_id: str | None = None


class UnifiedDashboardResponse(BaseModel):
    agnostic: dict[str, Any]
    yeoman: dict[str, Any]
    agnos_bridge: dict[str, Any]


class WidgetResponse(BaseModel):
    provider: str
    version: str
    agents: list[dict[str, Any]]
    sessions: dict[str, Any]
    quality: dict[str, Any]
    compliance: dict[str, Any]
    healthy: bool


class TokenBudgetResponse(BaseModel):
    enabled: bool = False
    pool: str | None = None
    pools: list[Any] = []
    agent_budgets: dict[str, Any] = {}
    error: str | None = None


class RecordingsResponse(BaseModel):
    enabled: bool = False
    recordings: list[Any] = []
    active_sessions: list[Any] = []


# ---------------------------------------------------------------------------
# Dashboard endpoints
# ---------------------------------------------------------------------------


@router.get("/dashboard", response_model=DashboardDataResponse)
async def get_dashboard(
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    from webgui.dashboard import dashboard_manager

    data: dict[str, Any] = await dashboard_manager.export_dashboard_data()
    return data


@router.get("/dashboard/sessions", response_model=ItemListResponse)
async def get_dashboard_sessions(
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    from webgui.dashboard import dashboard_manager

    sessions = await dashboard_manager.get_active_sessions()
    items = [asdict(s) for s in sessions]
    return {"items": items, "total": len(items)}


@router.get("/dashboard/agents", response_model=ItemListResponse)
async def get_dashboard_agents(
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    from webgui.dashboard import dashboard_manager

    agents = await dashboard_manager.get_agent_status()
    items = [asdict(a) for a in agents]
    return {"items": items, "total": len(items)}


@router.get("/dashboard/metrics", response_model=MetricsDataResponse)
async def get_dashboard_metrics(
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    from webgui.dashboard import dashboard_manager

    metrics = await dashboard_manager.get_resource_metrics()
    return asdict(metrics)


@router.get("/dashboard/agent-metrics", response_model=AgentMetricsDashboardResponse)
async def get_agent_dashboard(
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Per-agent metrics: task counts, success rates, LLM token usage."""
    from shared.agent_metrics import get_agent_metrics

    return {"agents": get_agent_metrics()}


@router.get("/dashboard/llm", response_model=LLMMetricsDashboardResponse)
async def get_llm_dashboard(
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Aggregated LLM usage metrics: call counts, error rates, by method."""
    from shared.agent_metrics import get_llm_metrics

    return {"llm": get_llm_metrics()}


@router.get("/dashboard/llm-gateway", response_model=GatewayHealthResponse)
async def get_llm_gateway_health(
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """AGNOS LLM Gateway health check and status."""
    from config.model_manager import model_manager

    result: dict[str, Any] = await model_manager.gateway_health()
    return result


@router.get("/dashboard/yeoman", response_model=YeomanStatusResponse)
async def get_yeoman_status(
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Get cached YEOMAN task results and status for unified dashboard view."""
    try:
        from shared.yeoman_a2a_client import yeoman_a2a_client

        return {
            "enabled": yeoman_a2a_client.enabled,
            "cached_results": yeoman_a2a_client.get_all_cached_results(),
            "peer_id": yeoman_a2a_client.yeoman_peer_id
            if yeoman_a2a_client.enabled
            else None,
        }
    except ImportError:
        return {"enabled": False, "cached_results": {}, "peer_id": None}


@router.get("/dashboard/unified", response_model=UnifiedDashboardResponse)
async def get_unified_dashboard(
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Get combined AGNOSTIC + YEOMAN status for unified AGNOS dashboard view."""
    from webgui.dashboard import dashboard_manager

    # AGNOSTIC dashboard data
    agnostic_data = await dashboard_manager.export_dashboard_data()

    # YEOMAN data (if available)
    yeoman_data: dict[str, Any] = {"enabled": False, "cached_results": {}}
    try:
        from shared.yeoman_a2a_client import yeoman_a2a_client

        if yeoman_a2a_client.enabled:
            yeoman_data = {
                "enabled": True,
                "cached_results": yeoman_a2a_client.get_all_cached_results(),
                "peer_id": yeoman_a2a_client.yeoman_peer_id,
            }
    except ImportError:
        pass

    # AGNOS bridge status
    bridge_status: dict[str, Any] = {"enabled": False}
    try:
        from shared.agnos_dashboard_bridge import agnos_dashboard_bridge

        bridge_status = {
            "enabled": agnos_dashboard_bridge.enabled,
            "pushing": agnos_dashboard_bridge._periodic_task is not None,
        }
    except ImportError:
        pass

    return {
        "agnostic": agnostic_data,
        "yeoman": yeoman_data,
        "agnos_bridge": bridge_status,
    }


# ---------------------------------------------------------------------------
# Embeddable metrics widget for SecureYeoman dashboard
# ---------------------------------------------------------------------------


@router.get("/dashboard/widget", response_model=WidgetResponse)
async def get_embeddable_widget(
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Compact JSON optimized for SecureYeoman dashboard embedding.

    Returns a minimal summary: agent status, active sessions, pass/fail rates,
    compliance scores, and recent task counts — all in a single request.
    """
    from webgui.dashboard import dashboard_manager

    # Core dashboard data
    dashboard_data: dict[str, Any] = {}
    try:
        dashboard_data = await dashboard_manager.export_dashboard_data()
    except Exception:
        pass

    # Agent status summary
    agents_summary = []
    try:
        agents = await dashboard_manager.get_agent_status()
        agents_summary = [
            {
                "name": a.agent_name,
                "status": a.status.value,
                "tasks_completed": getattr(a, "tasks_completed", 0),
            }
            for a in agents
        ]
    except Exception as e:
        logger.debug("Failed to get agent status for dashboard: %s", e)

    # Active session count
    try:
        sessions = await dashboard_manager.get_active_sessions()
        active_sessions = len(
            [s for s in sessions if s.status.value in ("running", "pending")]
        )
        total_sessions = len(sessions)
    except Exception:
        active_sessions = 0
        total_sessions = 0

    # Per-agent metrics
    agent_metrics: dict[str, Any] = {}
    try:
        from shared.agent_metrics import get_agent_metrics

        agent_metrics = get_agent_metrics()  # type: ignore[assignment]
    except Exception as e:
        logger.debug("Failed to get agent metrics for dashboard: %s", e)

    # Compute pass/fail rates from agent metrics
    total_passed = (
        sum(m.get("tasks_passed", 0) for m in agent_metrics.values())
        if isinstance(agent_metrics, dict)
        else 0
    )
    total_failed = (
        sum(m.get("tasks_failed", 0) for m in agent_metrics.values())
        if isinstance(agent_metrics, dict)
        else 0
    )
    total_tasks = total_passed + total_failed
    pass_rate = (total_passed / total_tasks * 100) if total_tasks > 0 else 0.0

    # Compliance scores (if available in dashboard data)
    compliance = dashboard_data.get("compliance_scores", {})

    return {
        "provider": "agnostic-qa",
        "version": os.getenv("AGNOSTIC_VERSION", VERSION),
        "agents": agents_summary,
        "sessions": {
            "active": active_sessions,
            "total": total_sessions,
        },
        "quality": {
            "pass_rate": round(pass_rate, 1),
            "total_tasks": total_tasks,
            "passed": total_passed,
            "failed": total_failed,
        },
        "compliance": compliance,
        "healthy": True,
    }


# ---------------------------------------------------------------------------
# Token budget pool dashboard
# ---------------------------------------------------------------------------


@router.get("/dashboard/token-budget", response_model=TokenBudgetResponse)
async def get_token_budget_pools(
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Display AGNOS token budget pool metrics."""
    try:
        from config.agnos_token_budget import agnos_token_budget

        if not agnos_token_budget or not agnos_token_budget.enabled:
            return {"enabled": False, "pools": []}

        client = agnos_token_budget._get_client()
        response = await client.get(
            f"{agnos_token_budget._pool_url('')}/../../../tokens/pools",
        )
        response.raise_for_status()
        data = response.json()

        # Also get per-agent remaining for our pool
        from config.agnos_agent_registration import AGNOSTIC_AGENTS

        agent_budgets: dict[str, Any] = {}
        for agent_key, agent_config in AGNOSTIC_AGENTS.items():
            agent_id: str = agent_config["agent_id"]  # type: ignore[assignment]
            remaining = await agnos_token_budget.get_remaining(agent_id)
            if remaining is not None:
                agent_budgets[agent_key] = remaining

        return {
            "enabled": True,
            "pool": agnos_token_budget.pool,
            "pools": data.get("pools", []),
            "agent_budgets": agent_budgets,
        }
    except Exception as exc:
        logger.debug("Token budget pool query failed: %s", exc)
        return {"enabled": False, "pools": [], "error": str(exc)}


# ---------------------------------------------------------------------------
# Video session streaming
# ---------------------------------------------------------------------------


@router.get("/dashboard/recordings", response_model=RecordingsResponse)
async def get_active_recordings(
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """List active screen recording sessions."""
    try:
        from shared.agnos_recording_client import agnos_recording

        if not agnos_recording.enabled:
            return {"enabled": False, "recordings": []}

        return {
            "enabled": True,
            "active_sessions": agnos_recording.get_active_sessions(),
        }
    except ImportError:
        return {"enabled": False, "recordings": []}


# ---------------------------------------------------------------------------
# Alert query endpoint
# ---------------------------------------------------------------------------


@router.get("/alerts", response_model=AlertListResponse)
async def list_alerts(
    limit: int = Query(50, ge=1, le=200),
    severity: str | None = Query(None),
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Query recent alerts from Redis stream."""
    try:
        from config.environment import config

        redis_client = config.get_async_redis_client()
        # Read from the alerts stream (most recent first)
        raw = await redis_client.xrevrange("stream:webgui:alerts", count=limit)
        alerts = []
        for stream_id, fields in raw:
            try:
                data = json.loads(fields.get("data", "{}"))
                if severity and data.get("severity") != severity:
                    continue
                data["stream_id"] = stream_id
                alerts.append(data)
            except (json.JSONDecodeError, AttributeError):
                continue
        return {"items": alerts, "total": len(alerts), "limit": limit}
    except Exception as exc:
        logger.warning("Failed to fetch alerts from Redis stream: %s", exc)
        return {"items": [], "total": 0, "limit": limit}


# ---------------------------------------------------------------------------
# Metrics endpoint — optionally secured via METRICS_AUTH_TOKEN
# ---------------------------------------------------------------------------

_METRICS_TOKEN = os.getenv("METRICS_AUTH_TOKEN", "")


@router.get("/metrics")
async def get_metrics(
    authorization: str | None = Header(default=None),
) -> JSONResponse:
    """Prometheus scrape endpoint. Set METRICS_AUTH_TOKEN to require a Bearer token."""
    if _METRICS_TOKEN and (
        not authorization
        or not authorization.removeprefix("Bearer ").strip() == _METRICS_TOKEN
    ):
        from fastapi import HTTPException

        raise HTTPException(status_code=401, detail="Invalid metrics token")

    from shared.metrics import get_content_type, get_metrics_text

    return JSONResponse(
        content=get_metrics_text(),
        media_type=get_content_type(),
    )
