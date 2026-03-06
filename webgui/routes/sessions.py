"""Session history endpoints."""

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from webgui.routes.dependencies import get_current_user

router = APIRouter()


class SessionCompareRequest(BaseModel):
    session1_id: str
    session2_id: str


@router.get("/sessions")
async def get_sessions(
    user_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: dict = Depends(get_current_user),
):
    from webgui.history import history_manager

    sessions = await history_manager.get_session_history(
        user_id=user_id,
        limit=limit,
        offset=offset,
    )
    return [asdict(s) for s in sessions]


@router.get("/sessions/search")
async def search_sessions(
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_user),
):
    from webgui.history import history_manager

    results = await history_manager.search_sessions(query=q, limit=limit)
    return [asdict(s) for s in results]


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, user: dict = Depends(get_current_user)):
    from webgui.history import history_manager

    details = await history_manager.get_session_details(session_id)
    if details is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return details


@router.post("/sessions/compare")
async def compare_sessions(
    req: SessionCompareRequest,
    user: dict = Depends(get_current_user),
):
    from webgui.history import history_manager

    comparison = await history_manager.compare_sessions(
        req.session1_id,
        req.session2_id,
    )
    if comparison is None:
        raise HTTPException(
            status_code=404, detail="One or both sessions not found"
        )
    return asdict(comparison)
