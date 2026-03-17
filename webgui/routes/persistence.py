"""Test result persistence (PostgreSQL) endpoints."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from webgui.auth import Permission
from webgui.routes.dependencies import (
    PaginatedResponse,
    _db_repo_dependency,
    get_current_user,
    require_permission,
)

# Type alias for the repository injected by Depends(_db_repo_dependency)
_RepoType = Any

router = APIRouter()


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class TestSessionCreate(BaseModel):
    session_id: str = Field(..., max_length=200)
    title: str = Field(..., max_length=500)
    description: str | None = Field(default=None, max_length=5000)
    priority: str | None = Field(default=None, max_length=50)


class TestResultCreate(BaseModel):
    session_id: str = Field(..., max_length=200)
    test_id: str = Field(..., max_length=200)
    test_name: str = Field(..., max_length=500)
    description: str | None = Field(default=None, max_length=5000)
    status: str = Field(..., max_length=50)
    severity: str | None = Field(default=None, max_length=50)
    category: str | None = Field(default=None, max_length=200)
    component: str | None = Field(default=None, max_length=200)
    agent_name: str | None = Field(default=None, max_length=200)
    error_message: str | None = Field(default=None, max_length=5000)
    stack_trace: str | None = Field(default=None, max_length=50000)
    execution_time_ms: int | None = None
    test_data: dict[str, Any] | None = None
    expected_result: dict[str, Any] | None = None
    actual_result: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


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
# Response models
# ---------------------------------------------------------------------------


class TestSessionResponse(BaseModel):
    id: int
    session_id: str
    status: str


class TestResultResponse(BaseModel):
    id: int
    test_id: str
    status: str


class StatusUpdateResponse(BaseModel):
    session_id: str
    status: str


class DeleteResponse(BaseModel):
    status: str
    job_id: str | None = None


class TestResultsSummaryResponse(BaseModel):
    """Session results summary — allows extra fields from repository."""

    model_config = {"extra": "allow"}

    session_id: str | None = None
    total: int = 0


class QualityTrendsResponse(BaseModel):
    """Quality trends — allows extra fields from repository."""

    model_config = {"extra": "allow"}


class SessionDiffResponse(BaseModel):
    """Session diff — allows extra fields from repository."""

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# Test session endpoints
# ---------------------------------------------------------------------------


@router.get("/test-sessions", response_model=PaginatedResponse)
async def get_test_sessions(
    status: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=10000),
    user: dict[str, Any] = Depends(get_current_user),
    repo: _RepoType = Depends(_db_repo_dependency),
) -> dict[str, Any]:
    """Get test sessions."""
    if repo is None:
        raise HTTPException(
            status_code=503, detail="Database not enabled. Set DATABASE_ENABLED=true"
        )
    sessions = await repo.get_sessions(status=status, limit=limit, offset=offset)
    items = [
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
    return {"items": items, "total": len(items), "limit": limit, "offset": offset}


@router.post("/test-sessions", status_code=201, response_model=TestSessionResponse)
async def create_test_session(
    req: TestSessionCreate,
    user: dict[str, Any] = Depends(require_permission(Permission.SESSIONS_WRITE)),
    repo: _RepoType = Depends(_db_repo_dependency),
) -> dict[str, Any]:
    """Create a new test session."""
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


@router.put("/test-sessions/{session_id}/status", response_model=StatusUpdateResponse)
async def update_test_session_status(
    session_id: str,
    status: str,
    user: dict[str, Any] = Depends(require_permission(Permission.SESSIONS_WRITE)),
    repo: _RepoType = Depends(_db_repo_dependency),
) -> dict[str, Any]:
    """Update test session status."""
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


@router.get("/test-results", response_model=PaginatedResponse)
async def get_test_results(
    session_id: str | None = None,
    status: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=10000),
    user: dict[str, Any] = Depends(get_current_user),
    repo: _RepoType = Depends(_db_repo_dependency),
) -> dict[str, Any]:
    """Get test results."""
    if repo is None:
        raise HTTPException(
            status_code=503, detail="Database not enabled. Set DATABASE_ENABLED=true"
        )
    results = await repo.get_test_results(
        session_id=session_id, status=status, limit=limit, offset=offset
    )
    items = [
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
    return {"items": items, "total": len(items), "limit": limit, "offset": offset}


@router.post("/test-results", status_code=201, response_model=TestResultResponse)
async def add_test_result(
    req: TestResultCreate,
    user: dict[str, Any] = Depends(require_permission(Permission.SESSIONS_WRITE)),
    repo: _RepoType = Depends(_db_repo_dependency),
) -> dict[str, Any]:
    """Add a test result."""
    if repo is None:
        raise HTTPException(
            status_code=503, detail="Database not enabled. Set DATABASE_ENABLED=true"
        )
    result = await repo.add_test_result(req.model_dump())
    return {"id": result.id, "test_id": result.test_id, "status": result.status}


@router.get(
    "/test-results/{session_id}/summary", response_model=TestResultsSummaryResponse
)
async def get_test_results_summary(
    session_id: str,
    user: dict[str, Any] = Depends(get_current_user),
    repo: _RepoType = Depends(_db_repo_dependency),
) -> Any:
    """Get summary of test results for a session."""
    if repo is None:
        raise HTTPException(
            status_code=503, detail="Database not enabled. Set DATABASE_ENABLED=true"
        )
    summary = await repo.get_session_results_summary(session_id)
    return summary


# ---------------------------------------------------------------------------
# Quality trends & session diff
# ---------------------------------------------------------------------------


@router.get("/test-metrics/trends", response_model=QualityTrendsResponse)
async def get_quality_trends(
    days: int = 30,
    user: dict[str, Any] = Depends(get_current_user),
    repo: _RepoType = Depends(_db_repo_dependency),
) -> Any:
    """Get quality trends over time."""
    if repo is None:
        raise HTTPException(
            status_code=503, detail="Database not enabled. Set DATABASE_ENABLED=true"
        )
    trends = await repo.get_quality_trends(days=days)
    return trends


@router.get("/test-sessions/diff", response_model=SessionDiffResponse)
async def diff_test_sessions(
    base: str = Query(
        ..., max_length=200, description="Base session ID (the 'before')"
    ),
    compare: str = Query(
        ..., max_length=200, description="Compare session ID (the 'after')"
    ),
    user: dict[str, Any] = Depends(get_current_user),
    repo: _RepoType = Depends(_db_repo_dependency),
) -> Any:
    """Compare test results between two sessions to detect regressions.

    Returns regressions (was passing, now failing), fixes, new tests,
    removed tests, and aggregate pass-rate / timing deltas.
    Requires DATABASE_ENABLED=true.

    For Redis-backed session comparison, use POST /sessions/compare instead.
    """
    if repo is None:
        raise HTTPException(
            status_code=503, detail="Database not enabled. Set DATABASE_ENABLED=true"
        )
    return await repo.diff_sessions(base, compare)
