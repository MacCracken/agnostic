"""
Repository for test result persistence operations.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database.models import TestMetrics, TestReport, TestResult, TestSession

logger = logging.getLogger(__name__)


class TestResultRepository:
    """Repository for test result database operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_session(
        self,
        session_id: str,
        title: str,
        description: str | None = None,
        priority: str | None = None,
        created_by: str | None = None,
    ) -> TestSession:
        """Create a new test session."""
        session = TestSession(
            session_id=session_id,
            title=title,
            description=description,
            priority=priority,
            status="pending",
            created_by=created_by,
        )
        self.session.add(session)
        await self.session.commit()
        await self.session.refresh(session)
        return session

    async def update_session_status(
        self, session_id: str, status: str
    ) -> TestSession | None:
        """Update test session status."""
        result = await self.session.execute(
            select(TestSession).where(TestSession.session_id == session_id)
        )
        session = result.scalar_one_or_none()
        if session:
            session.status = status
            if status in ("completed", "failed", "cancelled"):
                session.completed_at = datetime.now(timezone.utc)
            await self.session.commit()
            await self.session.refresh(session)
        return session

    async def add_test_result(self, result_data: dict[str, Any]) -> TestResult:
        """Add a test result."""
        result = TestResult(
            session_id=result_data.get("session_id", ""),
            test_id=result_data.get("test_id", ""),
            test_name=result_data.get("test_name", ""),
            test_description=result_data.get("description"),
            status=result_data.get("status", "passed"),
            severity=result_data.get("severity"),
            category=result_data.get("category"),
            component=result_data.get("component"),
            agent_name=result_data.get("agent_name"),
            error_message=result_data.get("error_message"),
            stack_trace=result_data.get("stack_trace"),
            execution_time_ms=result_data.get("execution_time_ms"),
            retry_count=result_data.get("retry_count", 0),
            test_data=result_data.get("test_data"),
            expected_result=result_data.get("expected_result"),
            actual_result=result_data.get("actual_result"),
            extra_metadata=result_data.get("metadata"),
        )
        self.session.add(result)
        await self.session.commit()
        await self.session.refresh(result)
        return result

    async def get_test_results(
        self,
        session_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[TestResult]:
        """Get test results with optional filters."""
        query = select(TestResult)
        if session_id:
            query = query.where(TestResult.session_id == session_id)
        if status:
            query = query.where(TestResult.status == status)
        query = query.order_by(TestResult.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_session_results_summary(self, session_id: str) -> dict[str, Any]:
        """Get summary of test results for a session."""
        result = await self.session.execute(
            select(
                TestResult.status,
                func.count(TestResult.id).label("count"),
            ).where(TestResult.session_id == session_id).group_by(TestResult.status)
        )
        summary = {row.status: row.count for row in result.all()}

        total = sum(summary.values())
        passed = summary.get("passed", 0)
        pass_rate = (passed / total * 100) if total > 0 else 0.0

        return {
            "session_id": session_id,
            "total": total,
            "passed": summary.get("passed", 0),
            "failed": summary.get("failed", 0),
            "skipped": summary.get("skipped", 0),
            "error": summary.get("error", 0),
            "pass_rate": round(pass_rate, 2),
        }

    async def get_sessions(
        self,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[TestSession]:
        """Get test sessions with optional filters."""
        query = select(TestSession)
        if status:
            query = query.where(TestSession.status == status)
        query = query.order_by(TestSession.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def add_metric(
        self,
        session_id: str,
        metric_name: str,
        metric_value: float,
        metric_unit: str | None = None,
    ) -> TestMetrics:
        """Add a test metric."""
        metric = TestMetrics(
            session_id=session_id,
            metric_name=metric_name,
            metric_value=metric_value,
            metric_unit=metric_unit,
        )
        self.session.add(metric)
        await self.session.commit()
        await self.session.refresh(metric)
        return metric

    async def get_metrics(
        self,
        session_id: str | None = None,
        metric_name: str | None = None,
        since: datetime | None = None,
    ) -> list[TestMetrics]:
        """Get metrics with optional filters."""
        query = select(TestMetrics)
        if session_id:
            query = query.where(TestMetrics.session_id == session_id)
        if metric_name:
            query = query.where(TestMetrics.metric_name == metric_name)
        if since:
            query = query.where(TestMetrics.recorded_at >= since)
        query = query.order_by(TestMetrics.recorded_at.desc()).limit(1000)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def create_report(
        self,
        session_id: str,
        report_type: str,
        summary: dict[str, Any],
        generated_by: str,
        details: dict[str, Any] | None = None,
    ) -> TestReport:
        """Create a test report."""
        report = TestReport(
            session_id=session_id,
            report_type=report_type,
            summary=summary,
            details=details,
            pass_count=summary.get("passed", 0),
            fail_count=summary.get("failed", 0),
            skip_count=summary.get("skipped", 0),
            total_count=summary.get("total", 0),
            pass_rate=summary.get("pass_rate", 0.0),
            generated_by=generated_by,
        )
        self.session.add(report)
        await self.session.commit()
        await self.session.refresh(report)
        return report

    async def get_reports(
        self,
        session_id: str | None = None,
        report_type: str | None = None,
        limit: int = 50,
    ) -> list[TestReport]:
        """Get test reports."""
        query = select(TestReport)
        if session_id:
            query = query.where(TestReport.session_id == session_id)
        if report_type:
            query = query.where(TestReport.report_type == report_type)
        query = query.order_by(TestReport.created_at.desc()).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_quality_trends(
        self, days: int = 30
    ) -> list[dict[str, Any]]:
        """Get quality trends over time."""
        since = datetime.now(timezone.utc) - timedelta(days=days)

        result = await self.session.execute(
            select(
                func.date(TestResult.created_at).label("date"),
                TestResult.status,
                func.count(TestResult.id).label("count"),
            )
            .where(TestResult.created_at >= since)
            .group_by(func.date(TestResult.created_at), TestResult.status)
            .order_by(func.date(TestResult.created_at))
        )

        trends = {}
        for row in result.all():
            date_str = str(row.date)
            if date_str not in trends:
                trends[date_str] = {"date": date_str, "total": 0}
            trends[date_str][row.status] = row.count
            trends[date_str]["total"] += row.count

        return list(trends.values())
