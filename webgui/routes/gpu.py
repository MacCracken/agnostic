"""GPU status and management endpoints."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends

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
