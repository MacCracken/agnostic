"""Test result persistence (PostgreSQL) endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from webgui.auth import Permission
from webgui.routes.dependencies import get_current_user, get_db_repo, require_permission

router = APIRouter()


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class TestSessionCreate(BaseModel):
    session_id: str
    title: str
    description: str | None = None
    priority: str | None = None


class TestResultCreate(BaseModel):
    session_id: str
    test_id: str
    test_name: str
    description: str | None = None
    status: str
    severity: str | None = None
    category: str | None = None
    component: str | None = None
    agent_name: str | None = None
    error_message: str | None = None
    stack_trace: str | None = None
    execution_time_ms: int | None = None
    test_data: dict | None = None
    expected_result: dict | None = None
    actual_result: dict | None = None
    metadata: dict | None = None


class TestResultFilter(BaseModel):
    session_id: str | None = None
    status: str | None = None
    limit: int = 100
    offset: int = 0


class TestMetricsQuery(BaseModel):
    session_id: str | None = None
    metric_name: str | None = None
    days: int = 30


# ---------------------------------------------------------------------------
# Test session endpoints
# ---------------------------------------------------------------------------


@router.get("/test-sessions")
async def get_test_sessions(
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    user: dict = Depends(get_current_user),
):
    """Get test sessions."""
    repo = await get_db_repo()
    if repo is None:
        raise HTTPException(
            status_code=503, detail="Database not enabled. Set DATABASE_ENABLED=true"
        )
    sessions = await repo.get_sessions(status=status, limit=limit, offset=offset)
    return [
        {
            "id": s.id,
            "session_id": s.session_id,
            "title": s.title,
            "description": s.description,
            "status": s.status,
            "priority": s.priority,
            "created_by": s.created_by,
            "created_at": s.created_at.isoformat(),
            "completed_at": s.completed_at.isoformat() if s.completed_at else None,
        }
        for s in sessions
    ]


@router.post("/test-sessions", status_code=201)
async def create_test_session(
    req: TestSessionCreate,
    user: dict = Depends(require_permission(Permission.SESSIONS_WRITE)),
):
    """Create a new test session."""
    repo = await get_db_repo()
    if repo is None:
        raise HTTPException(
            status_code=503, detail="Database not enabled. Set DATABASE_ENABLED=true"
        )
    session = await repo.create_session(
        session_id=req.session_id,
        title=req.title,
        description=req.description,
        priority=req.priority,
        created_by=user.get("user_id"),
    )
    return {
        "id": session.id,
        "session_id": session.session_id,
        "status": session.status,
    }


@router.put("/test-sessions/{session_id}/status")
async def update_test_session_status(
    session_id: str,
    status: str,
    user: dict = Depends(require_permission(Permission.SESSIONS_WRITE)),
):
    """Update test session status."""
    repo = await get_db_repo()
    if repo is None:
        raise HTTPException(
            status_code=503, detail="Database not enabled. Set DATABASE_ENABLED=true"
        )
    session = await repo.update_session_status(session_id, status)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session_id": session.session_id, "status": session.status}


# ---------------------------------------------------------------------------
# Test result endpoints
# ---------------------------------------------------------------------------


@router.get("/test-results")
async def get_test_results(
    session_id: str | None = None,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
    user: dict = Depends(get_current_user),
):
    """Get test results."""
    repo = await get_db_repo()
    if repo is None:
        raise HTTPException(
            status_code=503, detail="Database not enabled. Set DATABASE_ENABLED=true"
        )
    results = await repo.get_test_results(
        session_id=session_id, status=status, limit=limit, offset=offset
    )
    return [
        {
            "id": r.id,
            "session_id": r.session_id,
            "test_id": r.test_id,
            "test_name": r.test_name,
            "status": r.status,
            "severity": r.severity,
            "category": r.category,
            "component": r.component,
            "agent_name": r.agent_name,
            "error_message": r.error_message,
            "execution_time_ms": r.execution_time_ms,
            "created_at": r.created_at.isoformat(),
        }
        for r in results
    ]


@router.post("/test-results", status_code=201)
async def add_test_result(
    req: TestResultCreate,
    user: dict = Depends(require_permission(Permission.SESSIONS_WRITE)),
):
    """Add a test result."""
    repo = await get_db_repo()
    if repo is None:
        raise HTTPException(
            status_code=503, detail="Database not enabled. Set DATABASE_ENABLED=true"
        )
    result = await repo.add_test_result(req.model_dump())
    return {"id": result.id, "test_id": result.test_id, "status": result.status}


@router.get("/test-results/{session_id}/summary")
async def get_test_results_summary(
    session_id: str,
    user: dict = Depends(get_current_user),
):
    """Get summary of test results for a session."""
    repo = await get_db_repo()
    if repo is None:
        raise HTTPException(
            status_code=503, detail="Database not enabled. Set DATABASE_ENABLED=true"
        )
    summary = await repo.get_session_results_summary(session_id)
    return summary


# ---------------------------------------------------------------------------
# Quality trends & session diff
# ---------------------------------------------------------------------------


@router.get("/test-metrics/trends")
async def get_quality_trends(
    days: int = 30,
    user: dict = Depends(get_current_user),
):
    """Get quality trends over time."""
    repo = await get_db_repo()
    if repo is None:
        raise HTTPException(
            status_code=503, detail="Database not enabled. Set DATABASE_ENABLED=true"
        )
    trends = await repo.get_quality_trends(days=days)
    return trends


@router.get("/test-sessions/diff")
async def diff_test_sessions(
    base: str = Query(..., description="Base session ID (the 'before')"),
    compare: str = Query(..., description="Compare session ID (the 'after')"),
    user: dict = Depends(get_current_user),
):
    """Compare test results between two sessions to detect regressions.

    Returns regressions (was passing, now failing), fixes, new tests,
    removed tests, and aggregate pass-rate / timing deltas.
    Requires DATABASE_ENABLED=true.
    """
    repo = await get_db_repo()
    if repo is None:
        raise HTTPException(
            status_code=503, detail="Database not enabled. Set DATABASE_ENABLED=true"
        )
    return await repo.diff_sessions(base, compare)
