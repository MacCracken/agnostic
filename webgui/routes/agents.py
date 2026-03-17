"""Agent status, monitoring, and AGNOS registration endpoints."""

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from webgui.routes.dependencies import PaginatedResponse, get_current_user

router = APIRouter()


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class AgentRegistrationStatusResponse(BaseModel):
    agents: list[dict[str, Any]] = []
    registered: int = 0
    total: int = 0


class AgentRegistrationResultResponse(BaseModel):
    results: list[dict[str, Any]]


class AgentMetricsResponse(BaseModel):
    """Agent metrics — allows extra fields from dataclass conversion."""

    model_config = {"extra": "allow"}

    agent_name: str
    total_tasks: int = 0
    success_rate: float = 0.0


# ---------------------------------------------------------------------------
# Agent status endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/agents/registration-status", response_model=AgentRegistrationStatusResponse
)
async def get_agent_registration_status(
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Get agent registration status with agnosticos."""
    try:
        from config.agnos_agent_registration import agent_registry_client

        return agent_registry_client.get_registration_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post(
    "/agents/register-agnostic", response_model=AgentRegistrationResultResponse
)
async def register_agnostic_agents(
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Register all Agnostic agents with agnosticos."""
    if user.get("role") not in ("super_admin", "org_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        from config.agnos_agent_registration import agent_registry_client

        results = await agent_registry_client.register_all_agents()
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post(
    "/agents/deregister-agnostic", response_model=AgentRegistrationResultResponse
)
async def deregister_agnostic_agents(
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Deregister all Agnostic agents from agnosticos."""
    if user.get("role") not in ("super_admin", "org_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        from config.agnos_agent_registration import agent_registry_client

        results = await agent_registry_client.deregister_all_agents()
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/agents/queues", response_model=dict[str, int])
async def get_agent_queues(
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, int]:
    from webgui.agent_monitor import agent_monitor

    return await agent_monitor.get_queue_depths()


@router.get("/agents/{agent_name}", response_model=AgentMetricsResponse)
async def get_agent_detail(
    agent_name: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    from webgui.agent_monitor import agent_monitor

    metrics = await agent_monitor.get_agent_metrics(agent_name)
    if metrics is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return asdict(metrics)


@router.get("/agents", response_model=PaginatedResponse)
async def get_agents(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    from webgui.agent_monitor import agent_monitor

    statuses = await agent_monitor.get_all_agent_status()
    items = [asdict(s) for s in statuses]
    total = len(items)
    return {
        "items": items[offset : offset + limit],
        "total": total,
        "limit": limit,
        "offset": offset,
    }
