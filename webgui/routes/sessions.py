"""Session history endpoints."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from webgui.routes.dependencies import PaginatedResponse, get_current_user

router = APIRouter()


class SessionCompareRequest(BaseModel):
    session1_id: str
    session2_id: str


class SessionDetailResponse(BaseModel):
    """Session details — allows extra fields from history manager."""

    model_config = {"extra": "allow"}

    session_id: str | None = None


class SessionCompareResponse(BaseModel):
    """Session comparison — allows extra fields from dataclass."""

    model_config = {"extra": "allow"}


@router.get("/sessions", response_model=PaginatedResponse)
async def get_sessions(
    user_id: str | None = Query(None),
    status: str | None = Query(
        None, description="Filter by status: pending, running, completed, failed"
    ),
    created_after: str | None = Query(None, description="ISO 8601 date (inclusive)"),
    created_before: str | None = Query(None, description="ISO 8601 date (inclusive)"),
    sort_by: Literal["created_at", "updated_at", "status"] = Query("created_at"),
    sort_order: Literal["asc", "desc"] = Query("desc"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=10000),
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    if (
        user_id is not None
        and user_id != user["user_id"]
        and user.get("role") != "admin"
    ):
        raise HTTPException(status_code=403, detail="Forbidden")

    from webgui.history import history_manager

    sessions = await history_manager.get_session_history(
        user_id=user_id,
        limit=limit + offset,  # Fetch enough for offset slicing
        offset=0,
    )
    items = [asdict(s) for s in sessions]

    # Apply filters
    if status:
        items = [i for i in items if i.get("status") == status]
    if created_after:
        items = [i for i in items if i.get("created_at", "") >= created_after]
    if created_before:
        items = [i for i in items if i.get("created_at", "") <= created_before]

    # Sort
    reverse = sort_order == "desc"
    items.sort(key=lambda x: x.get(sort_by, ""), reverse=reverse)

    total = len(items)
    items = items[offset : offset + limit]

    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/sessions/search", response_model=PaginatedResponse)
async def search_sessions(
    q: str = Query(..., min_length=1, max_length=500),
    limit: int = Query(20, ge=1, le=100),
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    from webgui.history import history_manager

    results = await history_manager.search_sessions(query=q, limit=limit)
    items = [asdict(s) for s in results]
    return {"items": items, "total": len(items), "limit": limit, "offset": 0}


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
async def get_session(
    session_id: str, user: dict[str, Any] = Depends(get_current_user)
) -> Any:
    from webgui.history import history_manager

    details = await history_manager.get_session_details(session_id)
    if details is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return details


@router.post("/sessions/compare", response_model=SessionCompareResponse)
async def compare_sessions(
    req: SessionCompareRequest,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Compare two sessions from Redis history (real-time data).

    For database-backed session diff, use GET /test-sessions/diff instead.
    """
    from webgui.history import history_manager

    comparison = await history_manager.compare_sessions(
        req.session1_id,
        req.session2_id,
    )
    if comparison is None:
        raise HTTPException(status_code=404, detail="One or both sessions not found")
    return asdict(comparison)
