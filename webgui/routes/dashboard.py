"""Dashboard, alerts, and metrics endpoints."""

import json
import logging
from dataclasses import asdict

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from webgui.routes.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Dashboard endpoints
# ---------------------------------------------------------------------------


@router.get("/dashboard")
async def get_dashboard(user: dict = Depends(get_current_user)):
    from webgui.dashboard import dashboard_manager

    data = await dashboard_manager.export_dashboard_data()
    return data


@router.get("/dashboard/sessions")
async def get_dashboard_sessions(user: dict = Depends(get_current_user)):
    from webgui.dashboard import dashboard_manager

    sessions = await dashboard_manager.get_active_sessions()
    return [asdict(s) for s in sessions]


@router.get("/dashboard/agents")
async def get_dashboard_agents(user: dict = Depends(get_current_user)):
    from webgui.dashboard import dashboard_manager

    agents = await dashboard_manager.get_agent_status()
    return [asdict(a) for a in agents]


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


# ---------------------------------------------------------------------------
# Alert query endpoint
# ---------------------------------------------------------------------------


@router.get("/alerts")
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
    except Exception:
        return {"items": [], "total": 0, "limit": limit}


# ---------------------------------------------------------------------------
# Metrics endpoint (unauthenticated — for Prometheus scraping)
# ---------------------------------------------------------------------------


@router.get("/metrics")
async def get_metrics():
    from shared.metrics import get_content_type, get_metrics_text

    return JSONResponse(
        content=get_metrics_text(),
        media_type=get_content_type(),
    )
