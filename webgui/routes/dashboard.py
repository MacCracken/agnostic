"""Dashboard, alerts, and metrics endpoints."""

import json
import logging
import os
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

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


# ---------------------------------------------------------------------------
# Dashboard endpoints
# ---------------------------------------------------------------------------


@router.get("/dashboard")
async def get_dashboard(user: dict = Depends(get_current_user)):
    from webgui.dashboard import dashboard_manager

    data = await dashboard_manager.export_dashboard_data()
    return data


@router.get("/dashboard/sessions", response_model=ItemListResponse)
async def get_dashboard_sessions(user: dict = Depends(get_current_user)):
    from webgui.dashboard import dashboard_manager

    sessions = await dashboard_manager.get_active_sessions()
    items = [asdict(s) for s in sessions]
    return {"items": items, "total": len(items)}


@router.get("/dashboard/agents", response_model=ItemListResponse)
async def get_dashboard_agents(user: dict = Depends(get_current_user)):
    from webgui.dashboard import dashboard_manager

    agents = await dashboard_manager.get_agent_status()
    items = [asdict(a) for a in agents]
    return {"items": items, "total": len(items)}


@router.get("/dashboard/metrics")
async def get_dashboard_metrics(user: dict = Depends(get_current_user)):
    from webgui.dashboard import dashboard_manager

    metrics = await dashboard_manager.get_resource_metrics()
    return asdict(metrics)


@router.get("/dashboard/agent-metrics")
async def get_agent_dashboard(user: dict = Depends(get_current_user)):
    """Per-agent metrics: task counts, success rates, LLM token usage."""
    from shared.agent_metrics import get_agent_metrics

    return {"agents": get_agent_metrics()}


@router.get("/dashboard/llm")
async def get_llm_dashboard(user: dict = Depends(get_current_user)):
    """Aggregated LLM usage metrics: call counts, error rates, by method."""
    from shared.agent_metrics import get_llm_metrics

    return {"llm": get_llm_metrics()}


@router.get("/dashboard/llm-gateway")
async def get_llm_gateway_health(user: dict = Depends(get_current_user)):
    """AGNOS LLM Gateway health check and status."""
    from config.model_manager import model_manager

    return await model_manager.gateway_health()


@router.get("/dashboard/yeoman")
async def get_yeoman_status(user: dict = Depends(get_current_user)):
    """Get cached YEOMAN task results and status for unified dashboard view."""
    try:
        from shared.yeoman_a2a_client import yeoman_a2a_client

        return {
            "enabled": yeoman_a2a_client.enabled,
            "cached_results": yeoman_a2a_client.get_all_cached_results(),
            "peer_id": yeoman_a2a_client.yeoman_peer_id if yeoman_a2a_client.enabled else None,
        }
    except ImportError:
        return {"enabled": False, "cached_results": {}, "peer_id": None}


@router.get("/dashboard/unified")
async def get_unified_dashboard(user: dict = Depends(get_current_user)):
    """Get combined AGNOSTIC + YEOMAN status for unified AGNOS dashboard view."""
    from webgui.dashboard import dashboard_manager

    # AGNOSTIC dashboard data
    agnostic_data = await dashboard_manager.export_dashboard_data()

    # YEOMAN data (if available)
    yeoman_data: dict = {"enabled": False, "cached_results": {}}
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
    bridge_status: dict = {"enabled": False}
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


@router.get("/dashboard/widget")
async def get_embeddable_widget(user: dict = Depends(get_current_user)):
    """Compact JSON optimized for SecureYeoman dashboard embedding.

    Returns a minimal summary: agent status, active sessions, pass/fail rates,
    compliance scores, and recent task counts — all in a single request.
    """
    from webgui.dashboard import dashboard_manager

    # Core dashboard data
    try:
        dashboard_data = await dashboard_manager.export_dashboard_data()
    except Exception:
        dashboard_data = {}

    # Agent status summary
    agents_summary = []
    try:
        agents = await dashboard_manager.get_agent_status()
        agents_summary = [
            {"name": a.name, "status": a.status, "tasks_completed": getattr(a, "tasks_completed", 0)}
            for a in agents
        ]
    except Exception:
        pass

    # Active session count
    try:
        sessions = await dashboard_manager.get_active_sessions()
        active_sessions = len([s for s in sessions if s.status in ("running", "pending")])
        total_sessions = len(sessions)
    except Exception:
        active_sessions = 0
        total_sessions = 0

    # Per-agent metrics
    agent_metrics = {}
    try:
        from shared.agent_metrics import get_agent_metrics

        agent_metrics = get_agent_metrics()
    except Exception:
        pass

    # Compute pass/fail rates from agent metrics
    total_passed = sum(m.get("tasks_passed", 0) for m in agent_metrics.values()) if isinstance(agent_metrics, dict) else 0
    total_failed = sum(m.get("tasks_failed", 0) for m in agent_metrics.values()) if isinstance(agent_metrics, dict) else 0
    total_tasks = total_passed + total_failed
    pass_rate = (total_passed / total_tasks * 100) if total_tasks > 0 else 0.0

    # Compliance scores (if available in dashboard data)
    compliance = dashboard_data.get("compliance_scores", {})

    return {
        "provider": "agnostic-qa",
        "version": os.getenv("AGNOSTIC_VERSION", "2026.3.5"),
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
# Alert query endpoint
# ---------------------------------------------------------------------------


@router.get("/alerts", response_model=AlertListResponse)
async def list_alerts(
    limit: int = Query(50, ge=1, le=200),
    severity: str | None = Query(None),
    user: dict = Depends(get_current_user),
):
    """Query recent alerts from Redis stream."""
    try:
        from config.environment import config

        redis_client = config.get_redis_client()
        # Read from the alerts stream (most recent first)
        raw = redis_client.xrevrange("stream:webgui:alerts", count=limit)
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
):
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
