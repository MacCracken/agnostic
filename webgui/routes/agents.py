"""Agent status, monitoring, and AGNOS registration endpoints."""

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Query

from webgui.routes.dependencies import get_current_user

router = APIRouter()


# ---------------------------------------------------------------------------
# Agent status endpoints
# ---------------------------------------------------------------------------


@router.get("/agents/registration-status")
async def get_agent_registration_status(
    user: dict = Depends(get_current_user),
):
    """Get agent registration status with agnosticos."""
    try:
        from config.agnos_agent_registration import agent_registry_client

        return agent_registry_client.get_registration_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/agents/register-agnostic")
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
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/agents/deregister-agnostic")
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
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/agents/queues")
async def get_agent_queues(user: dict = Depends(get_current_user)):
    from webgui.agent_monitor import agent_monitor

    return await agent_monitor.get_queue_depths()


@router.get("/agents/{agent_name}")
async def get_agent_detail(
    agent_name: str,
    user: dict = Depends(get_current_user),
):
    from webgui.agent_monitor import agent_monitor

    metrics = await agent_monitor.get_agent_metrics(agent_name)
    if metrics is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return asdict(metrics)


@router.get("/agents")
async def get_agents(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: dict = Depends(get_current_user),
):
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
