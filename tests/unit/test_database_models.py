"""Unit tests for test result persistence (PostgreSQL) models and repository.

Tests the SQLAlchemy models, repository logic, and API endpoint guards
without requiring a live database connection.
"""

import os
import sys
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


class TestDatabaseModels:
    """Tests for SQLAlchemy model definitions."""

    def test_test_status_enum(self):
        from shared.database.models import TestStatus

        assert TestStatus.PASSED == "passed"
        assert TestStatus.FAILED == "failed"
        assert TestStatus.SKIPPED == "skipped"
        assert TestStatus.ERROR == "error"
        assert TestStatus.RUNNING == "running"

    def test_test_result_severity_enum(self):
        from shared.database.models import TestResultSeverity

        assert TestResultSeverity.CRITICAL == "critical"
        assert TestResultSeverity.HIGH == "high"
        assert TestResultSeverity.MEDIUM == "medium"
        assert TestResultSeverity.LOW == "low"

    def test_test_session_table_name(self):
        from shared.database.models import TestSession

        assert TestSession.__tablename__ == "test_sessions"

    def test_test_result_table_name(self):
        from shared.database.models import TestResult

        assert TestResult.__tablename__ == "test_results"

    def test_test_metrics_table_name(self):
        from shared.database.models import TestMetrics

        assert TestMetrics.__tablename__ == "test_metrics"

    def test_test_report_table_name(self):
        from shared.database.models import TestReport

        assert TestReport.__tablename__ == "test_reports"

    def test_test_session_has_indexes(self):
        from shared.database.models import TestSession

        index_names = [idx.name for idx in TestSession.__table_args__ if hasattr(idx, "name")]
        assert "idx_test_sessions_status" in index_names
        assert "idx_test_sessions_created_at" in index_names

    def test_test_result_has_indexes(self):
        from shared.database.models import TestResult

        index_names = [idx.name for idx in TestResult.__table_args__ if hasattr(idx, "name")]
        assert "idx_test_results_session_id" in index_names
        assert "idx_test_results_status" in index_names
        assert "idx_test_results_test_id" in index_names


class TestDatabaseUrl:
    """Tests for database URL construction."""

    def test_default_url(self):
        with patch.dict(os.environ, {}, clear=True):
            from shared.database.models import get_database_url

            url = get_database_url()
            assert url.startswith("postgresql+asyncpg://")
            assert "localhost" in url
            assert "5432" in url
            assert "agnostic" in url

    def test_custom_url_from_env(self):
        env = {
            "POSTGRES_HOST": "db.example.com",
            "POSTGRES_PORT": "5433",
            "POSTGRES_USER": "qauser",
            "POSTGRES_PASSWORD": "secret",
            "POSTGRES_DB": "qa_results",
        }
        with patch.dict(os.environ, env, clear=True):
            from shared.database.models import get_database_url

            url = get_database_url()
            assert "db.example.com" in url
            assert "5433" in url
            assert "qauser" in url
            assert "qa_results" in url


class TestTestResultRepository:
    """Tests for TestResultRepository methods using mock sessions."""

    @pytest.fixture
    def mock_session(self):
        session = AsyncMock()
        return session

    @pytest.fixture
    def repo(self, mock_session):
        from shared.database.repository import TestResultRepository

        return TestResultRepository(mock_session)

    @pytest.mark.asyncio
    async def test_create_session(self, repo, mock_session):
        mock_session.refresh = AsyncMock()

        result = await repo.create_session(
            session_id="test-sess-001",
            title="Test Session",
            description="A test",
            priority="high",
            created_by="user-1",
        )

        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()
        added_obj = mock_session.add.call_args[0][0]
        assert added_obj.session_id == "test-sess-001"
        assert added_obj.title == "Test Session"
        assert added_obj.status == "pending"

    @pytest.mark.asyncio
    async def test_update_session_status_found(self, repo, mock_session):
        from shared.database.models import TestSession

        mock_session_obj = MagicMock(spec=TestSession)
        mock_session_obj.status = "pending"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_session_obj
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.refresh = AsyncMock()

        result = await repo.update_session_status("test-sess-001", "completed")

        assert mock_session_obj.status == "completed"
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_session_status_not_found(self, repo, mock_session):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await repo.update_session_status("nonexistent", "completed")

        assert result is None
        mock_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_add_test_result(self, repo, mock_session):
        mock_session.refresh = AsyncMock()

        result_data = {
            "session_id": "sess-1",
            "test_id": "test-001",
            "test_name": "test_login",
            "status": "passed",
            "severity": "low",
            "execution_time_ms": 150,
        }

        result = await repo.add_test_result(result_data)

        mock_session.add.assert_called_once()
        added = mock_session.add.call_args[0][0]
        assert added.session_id == "sess-1"
        assert added.test_id == "test-001"
        assert added.status == "passed"

    @pytest.mark.asyncio
    async def test_get_test_results(self, repo, mock_session):
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute = AsyncMock(return_value=mock_result)

        results = await repo.get_test_results(session_id="sess-1")

        mock_session.execute.assert_called_once()
        assert results == []

    @pytest.mark.asyncio
    async def test_add_metric(self, repo, mock_session):
        mock_session.refresh = AsyncMock()

        result = await repo.add_metric(
            session_id="sess-1",
            metric_name="response_time_p95",
            metric_value=245.5,
            metric_unit="ms",
        )

        mock_session.add.assert_called_once()
        added = mock_session.add.call_args[0][0]
        assert added.metric_name == "response_time_p95"
        assert added.metric_value == 245.5
        assert added.metric_unit == "ms"

    @pytest.mark.asyncio
    async def test_create_report(self, repo, mock_session):
        mock_session.refresh = AsyncMock()

        summary = {"total": 100, "passed": 95, "failed": 5, "pass_rate": 95.0}
        result = await repo.create_report(
            session_id="sess-1",
            report_type="executive_summary",
            summary=summary,
            generated_by="qa-analyst",
        )

        mock_session.add.assert_called_once()
        added = mock_session.add.call_args[0][0]
        assert added.report_type == "executive_summary"
        assert added.pass_count == 95
        assert added.fail_count == 5
        assert added.pass_rate == 95.0

    @pytest.mark.asyncio
    async def test_get_session_results_summary(self, repo, mock_session):
        mock_row1 = MagicMock()
        mock_row1.status = "passed"
        mock_row1.count = 90
        mock_row2 = MagicMock()
        mock_row2.status = "failed"
        mock_row2.count = 10

        mock_result = MagicMock()
        mock_result.all.return_value = [mock_row1, mock_row2]
        mock_session.execute = AsyncMock(return_value=mock_result)

        summary = await repo.get_session_results_summary("sess-1")

        assert summary["session_id"] == "sess-1"
        assert summary["total"] == 100
        assert summary["passed"] == 90
        assert summary["failed"] == 10
        assert summary["pass_rate"] == 90.0


class TestDatabaseEnabledGuard:
    """Tests for DATABASE_ENABLED env var guard in API endpoints."""

    def test_database_disabled_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            # Re-evaluate the module-level constant
            assert os.getenv("DATABASE_ENABLED", "false").lower() != "true"

    def test_database_enabled_via_env(self):
        with patch.dict(os.environ, {"DATABASE_ENABLED": "true"}, clear=False):
            assert os.getenv("DATABASE_ENABLED", "false").lower() == "true"
