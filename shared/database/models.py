"""
Database models for test result persistence.
Uses SQLAlchemy with async support for PostgreSQL.
"""

import asyncio
import os
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class TestStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"
    RUNNING = "running"


class TestResultSeverity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Base(DeclarativeBase):
    pass


class TestSession(Base):
    __tablename__ = "test_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    priority: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    test_results: Mapped[list["TestResult"]] = []

    __table_args__ = (
        Index("idx_test_sessions_status", "status"),
        Index("idx_test_sessions_created_at", "created_at"),
    )


class TestResult(Base):
    __tablename__ = "test_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(String(100), index=True)
    test_id: Mapped[str] = mapped_column(String(100), index=True)
    test_name: Mapped[str] = mapped_column(String(500))
    test_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20))
    severity: Mapped[str | None] = mapped_column(String(20), nullable=True)
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    component: Mapped[str | None] = mapped_column(String(100), nullable=True)
    agent_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    stack_trace: Mapped[str | None] = mapped_column(Text, nullable=True)
    execution_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    test_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    expected_result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    actual_result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    extra_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSON, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC)
    )

    __table_args__ = (
        Index("idx_test_results_session_id", "session_id"),
        Index("idx_test_results_status", "status"),
        Index("idx_test_results_created_at", "created_at"),
        Index("idx_test_results_test_id", "test_id"),
    )


class TestMetrics(Base):
    __tablename__ = "test_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(String(100), index=True)
    metric_name: Mapped[str] = mapped_column(String(100))
    metric_value: Mapped[float] = mapped_column(Float)
    metric_unit: Mapped[str | None] = mapped_column(String(20), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC)
    )

    __table_args__ = (
        Index("idx_test_metrics_session_id", "session_id"),
        Index("idx_test_metrics_recorded_at", "recorded_at"),
    )


class TestReport(Base):
    __tablename__ = "test_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(String(100), index=True)
    report_type: Mapped[str] = mapped_column(String(50))
    summary: Mapped[dict[str, Any]] = mapped_column(JSON)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    pass_count: Mapped[int] = mapped_column(Integer, default=0)
    fail_count: Mapped[int] = mapped_column(Integer, default=0)
    skip_count: Mapped[int] = mapped_column(Integer, default=0)
    total_count: Mapped[int] = mapped_column(Integer, default=0)
    pass_rate: Mapped[float] = mapped_column(default=0.0)
    generated_by: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC)
    )

    __table_args__ = (
        Index("idx_test_reports_session_id", "session_id"),
        Index("idx_test_reports_created_at", "created_at"),
    )


_engine = None
_session_factory = None
_init_lock = asyncio.Lock()


def get_database_url() -> str:
    """Get database URL from environment or use default."""
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "")
    database = os.getenv("POSTGRES_DB", "agnostic")

    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{database}"


async def init_db():
    """Initialize database connection and create tables."""
    global _engine, _session_factory

    async with _init_lock:
        if _session_factory is not None:
            return  # Already initialized by another coroutine

        database_url = get_database_url()
        _engine = create_async_engine(
            database_url,
            echo=False,
            pool_pre_ping=True,
            pool_size=int(os.getenv("DB_POOL_SIZE", "5")),
            max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "10")),
            pool_recycle=int(os.getenv("DB_POOL_RECYCLE", "3600")),
        )

        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        from sqlalchemy.orm import sessionmaker

        _session_factory = sessionmaker(
            _engine, class_=AsyncSession, expire_on_commit=False
        )


async def get_session() -> AsyncSession:
    """Get a database session."""
    if _session_factory is None:
        await init_db()
    return _session_factory()


async def close_db():
    """Close database connection."""
    global _engine
    if _engine:
        await _engine.dispose()
