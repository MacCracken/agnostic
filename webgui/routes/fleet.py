"""Fleet management API endpoints."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from webgui.routes.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()


def _check_fleet_enabled() -> None:
    from config.fleet.node import FLEET_ENABLED

    if not FLEET_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="Fleet mode not enabled. Set AGNOS_FLEET_ENABLED=true",
        )


@router.get("/fleet/nodes")
async def list_fleet_nodes(
    alive_only: bool = True,
    group: str | None = None,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """List all fleet nodes with optional group and liveness filters."""
    _check_fleet_enabled()
    from config.fleet.registry import fleet_registry

    if group:
        nodes = await fleet_registry.get_group_nodes(group)
    elif alive_only:
        nodes = await fleet_registry.get_alive_nodes()
    else:
        nodes = await fleet_registry.get_all_nodes()

    return {
        "nodes": [n.to_dict() for n in nodes],
        "total": len(nodes),
    }


@router.get("/fleet/nodes/{node_id}")
async def get_fleet_node(
    node_id: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Get details for a specific fleet node."""
    _check_fleet_enabled()
    from config.fleet.registry import fleet_registry

    node = await fleet_registry.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found")
    return node.to_dict()


@router.get("/fleet/groups")
async def list_fleet_groups(
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """List all fleet groups with node counts and GPU summary."""
    _check_fleet_enabled()
    from config.fleet.registry import fleet_registry

    groups = await fleet_registry.list_groups()
    return {"groups": groups}


@router.get("/fleet/status")
async def fleet_status(
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Fleet-wide status summary."""
    _check_fleet_enabled()
    from config.fleet.registry import fleet_registry

    all_nodes = await fleet_registry.get_all_nodes()
    alive = [n for n in all_nodes if n.is_alive]

    return {
        "enabled": True,
        "local_node": fleet_registry.local_node.to_dict()
        if fleet_registry.local_node
        else None,
        "total_nodes": len(all_nodes),
        "alive_nodes": len(alive),
        "dead_nodes": len(all_nodes) - len(alive),
        "total_gpus": sum(n.capabilities.gpu_count for n in alive),
        "total_vram_mb": sum(n.capabilities.gpu_vram_total_mb for n in alive),
        "free_vram_mb": sum(n.capabilities.gpu_vram_free_mb for n in alive),
        "total_cpu_cores": sum(n.capabilities.cpu_cores for n in alive),
        "active_crews": sum(n.active_crews for n in alive),
        "active_agents": sum(n.active_agents for n in alive),
    }


@router.get("/fleet/gpu")
async def fleet_gpu_status(
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Aggregated GPU utilization across all fleet nodes."""
    _check_fleet_enabled()
    from config.fleet.registry import fleet_registry

    alive = await fleet_registry.get_alive_nodes()

    per_node = []
    for node in alive:
        if node.capabilities.gpu_count > 0:
            per_node.append(
                {
                    "node_id": node.node_id,
                    "group": node.group,
                    "gpu_count": node.capabilities.gpu_count,
                    "gpu_names": node.capabilities.gpu_names,
                    "vram_total_mb": node.capabilities.gpu_vram_total_mb,
                    "vram_free_mb": node.capabilities.gpu_vram_free_mb,
                }
            )

    return {
        "gpu_nodes": len(per_node),
        "total_gpus": sum(n["gpu_count"] for n in per_node),
        "total_vram_mb": sum(n["vram_total_mb"] for n in per_node),
        "free_vram_mb": sum(n["vram_free_mb"] for n in per_node),
        "nodes": per_node,
    }


@router.post("/fleet/evict")
async def evict_dead_nodes(
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Remove dead nodes from the fleet registry."""
    _check_fleet_enabled()
    if user.get("role") not in ("super_admin", "org_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    from config.fleet.registry import fleet_registry

    evicted = await fleet_registry.evict_dead_nodes()
    return {"evicted": evicted, "count": len(evicted)}
