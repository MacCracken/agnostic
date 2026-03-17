"""
RPC handler route — receives inbound RPC calls from daimon.

When an external agent invokes an ``agnostic.*`` method via daimon's
``POST /v1/rpc/call``, daimon routes the call here. This module dispatches
to the appropriate agent capability handler.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from webgui.routes.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rpc", tags=["rpc"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class RpcCallRequest(BaseModel):
    method: str = Field(..., description="Fully qualified RPC method name")
    params: dict[str, Any] = Field(
        default_factory=dict, description="Method parameters"
    )
    timeout_ms: int = Field(default=30000, description="Timeout in milliseconds")
    sender_id: str | None = Field(default=None, description="Calling agent identifier")


class RpcCallResponse(BaseModel):
    status: str
    method: str
    result: dict[str, Any] | None = None
    error: str | None = None


class RpcMethodsResponse(BaseModel):
    methods: list[str]
    count: int


# ---------------------------------------------------------------------------
# Capability → handler dispatch
# ---------------------------------------------------------------------------

# Maps RPC method names to the capability name used by
# handle_capability_request in agnos_agent_registration.
_METHOD_TO_CAPABILITY: dict[str, str] = {
    "agnostic.security_audit": "security_audit",
    "agnostic.load_testing": "load_testing",
    "agnostic.compliance_check": "compliance_check",
    "agnostic.test_planning": "test_planning",
    "agnostic.test_execution": "test_execution",
    "agnostic.quality_analysis": "quality_analysis",
    "agnostic.regression_testing": "regression_testing",
    "agnostic.fuzzy_verification": "fuzzy_verification",
}


@router.post("/handle", response_model=RpcCallResponse)
async def handle_rpc_call(
    request: RpcCallRequest,
    _user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Handle an inbound RPC call routed by daimon.

    Daimon forwards ``POST /v1/rpc/call`` requests to this endpoint when the
    target method is registered by an Agnostic agent. The handler maps the
    method to a capability and dispatches via the existing capability request
    handler.
    """
    method = request.method
    capability_name = _METHOD_TO_CAPABILITY.get(method)

    if capability_name is None:
        # Check if it's an agnostic.* method we don't recognize
        if method.startswith("agnostic."):
            logger.warning("Unknown agnostic RPC method: %s", method)
            raise HTTPException(
                status_code=404,
                detail=f"Unknown RPC method: {method}",
            )
        # Not our method — shouldn't have been routed here
        raise HTTPException(
            status_code=400,
            detail=f"Method {method} is not an Agnostic RPC method",
        )

    # Dispatch to capability handler
    from config.agnos_agent_registration import agent_registry_client

    result = await agent_registry_client.handle_capability_request(
        capability_name, request.params
    )

    if result.get("status") == "error":
        return {
            "status": "error",
            "method": method,
            "error": result.get("message", "Unknown error"),
        }

    logger.info(
        "RPC call %s from %s → capability %s (task_id=%s)",
        method,
        request.sender_id or "unknown",
        capability_name,
        result.get("task_id"),
    )

    return {
        "status": "accepted",
        "method": method,
        "result": result,
    }


@router.get("/methods", response_model=RpcMethodsResponse)
async def list_local_methods(
    _user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """List RPC methods this Agnostic instance can handle."""
    return {
        "methods": list(_METHOD_TO_CAPABILITY.keys()),
        "count": len(_METHOD_TO_CAPABILITY),
    }
