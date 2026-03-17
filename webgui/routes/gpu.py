"""GPU status and management endpoints."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from webgui.routes.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/gpu/status")
async def gpu_status(
    force: bool = False,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Return current GPU status for this host.

    Set ``force=true`` to bypass the probe cache and re-detect hardware.
    """
    from config.gpu import detect_gpus

    status = detect_gpus(force=force)
    return status.to_dict()


@router.get("/gpu/devices/{device_index}")
async def gpu_device_detail(
    device_index: int,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Return detailed info for a specific GPU device."""
    from config.gpu import detect_gpus

    status = detect_gpus(force=True)
    for dev in status.devices:
        if dev.index == device_index:
            return dev.to_dict()
    raise HTTPException(status_code=404, detail=f"GPU device {device_index} not found")


@router.get("/gpu/memory")
async def gpu_memory_summary(
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Return aggregated GPU memory usage across all devices."""
    from config.gpu import detect_gpus

    status = detect_gpus(force=True)
    per_device = []
    for dev in status.devices:
        pct = (
            round(dev.memory_used_mb / dev.memory_total_mb * 100, 1)
            if dev.memory_total_mb > 0
            else 0
        )
        per_device.append(
            {
                "index": dev.index,
                "name": dev.name,
                "total_mb": dev.memory_total_mb,
                "used_mb": dev.memory_used_mb,
                "free_mb": dev.memory_free_mb,
                "utilization_pct": pct,
            }
        )

    return {
        "available": status.available,
        "device_count": status.device_count,
        "total_mb": status.total_memory_mb,
        "used_mb": sum(d.memory_used_mb for d in status.devices),
        "free_mb": status.free_memory_mb,
        "devices": per_device,
    }


@router.get("/gpu/slots")
async def gpu_slots(
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Return cross-crew GPU slot reservations.

    Shows which crews currently hold GPU memory reservations and how much.
    """
    from config.gpu import detect_gpus
    from config.gpu_scheduler import gpu_slot_tracker

    status = detect_gpus()
    adjusted = gpu_slot_tracker.adjusted_free(status) if status.available else {}

    return {
        "tracker": gpu_slot_tracker.to_dict(),
        "adjusted_free_mb": adjusted,
    }


@router.get("/gpu/inference")
async def local_inference_status(
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Return local inference offload configuration and available models."""
    from config.local_inference import get_local_models, is_enabled

    return {
        "enabled": is_enabled(),
        "models": get_local_models(),
    }
