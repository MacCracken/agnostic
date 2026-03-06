"""Tests for test result diffing — TestResultRepository.diff_sessions."""

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from shared.database.repository import TestResultRepository


def _make_result(test_id, test_name, status, execution_time_ms=None, error_message=None, component=None):
    """Create a mock TestResult row."""
    r = MagicMock()
    r.test_id = test_id
    r.test_name = test_name
    r.status = status
    r.execution_time_ms = execution_time_ms
    r.error_message = error_message
    r.component = component
    return r


@pytest.fixture()
def repo():
    session = AsyncMock()
    return TestResultRepository(session)


class TestDiffSessions:
    @pytest.mark.asyncio
    async def test_identical_sessions(self, repo):
        """Two identical sessions show no regressions or fixes."""
        base = [
            _make_result("t1", "Login test", "passed", 100),
            _make_result("t2", "Logout test", "passed", 50),
        ]
        compare = [
            _make_result("t1", "Login test", "passed", 95),
            _make_result("t2", "Logout test", "passed", 55),
        ]

        mock_base = MagicMock()
        mock_base.scalars.return_value.all.return_value = base
        mock_compare = MagicMock()
        mock_compare.scalars.return_value.all.return_value = compare
        repo.session.execute = AsyncMock(side_effect=[mock_base, mock_compare])

        diff = await repo.diff_sessions("s1", "s2")

        assert diff["has_regressions"] is False
        assert diff["summary"]["regressions"] == 0
        assert diff["summary"]["fixes"] == 0
        assert diff["summary"]["stable"] == 2
        assert diff["summary"]["base_pass_rate"] == 100.0
        assert diff["summary"]["compare_pass_rate"] == 100.0
        assert diff["summary"]["pass_rate_delta"] == 0.0

    @pytest.mark.asyncio
    async def test_regression_detected(self, repo):
        """Test that went from passed to failed is flagged as regression."""
        base = [_make_result("t1", "Login test", "passed", 100)]
        compare = [_make_result("t1", "Login test", "failed", 200, error_message="timeout")]

        mock_base = MagicMock()
        mock_base.scalars.return_value.all.return_value = base
        mock_compare = MagicMock()
        mock_compare.scalars.return_value.all.return_value = compare
        repo.session.execute = AsyncMock(side_effect=[mock_base, mock_compare])

        diff = await repo.diff_sessions("s1", "s2")

        assert diff["has_regressions"] is True
        assert diff["summary"]["regressions"] == 1
        assert diff["regressions"][0]["test_id"] == "t1"
        assert diff["regressions"][0]["base_status"] == "passed"
        assert diff["regressions"][0]["compare_status"] == "failed"
        assert diff["regressions"][0]["error_message"] == "timeout"

    @pytest.mark.asyncio
    async def test_fix_detected(self, repo):
        """Test that went from failed to passed is flagged as fix."""
        base = [_make_result("t1", "Login test", "failed")]
        compare = [_make_result("t1", "Login test", "passed")]

        mock_base = MagicMock()
        mock_base.scalars.return_value.all.return_value = base
        mock_compare = MagicMock()
        mock_compare.scalars.return_value.all.return_value = compare
        repo.session.execute = AsyncMock(side_effect=[mock_base, mock_compare])

        diff = await repo.diff_sessions("s1", "s2")

        assert diff["summary"]["fixes"] == 1
        assert diff["fixes"][0]["test_id"] == "t1"
        assert diff["fixes"][0]["base_status"] == "failed"
        assert diff["fixes"][0]["compare_status"] == "passed"

    @pytest.mark.asyncio
    async def test_new_tests(self, repo):
        """Tests in compare but not base are flagged as new."""
        base = [_make_result("t1", "Login test", "passed")]
        compare = [
            _make_result("t1", "Login test", "passed"),
            _make_result("t2", "Signup test", "passed"),
        ]

        mock_base = MagicMock()
        mock_base.scalars.return_value.all.return_value = base
        mock_compare = MagicMock()
        mock_compare.scalars.return_value.all.return_value = compare
        repo.session.execute = AsyncMock(side_effect=[mock_base, mock_compare])

        diff = await repo.diff_sessions("s1", "s2")

        assert diff["summary"]["new_tests"] == 1
        assert diff["new_tests"][0]["test_id"] == "t2"
        assert diff["new_tests"][0]["test_name"] == "Signup test"

    @pytest.mark.asyncio
    async def test_removed_tests(self, repo):
        """Tests in base but not compare are flagged as removed."""
        base = [
            _make_result("t1", "Login test", "passed"),
            _make_result("t2", "Signup test", "passed"),
        ]
        compare = [_make_result("t1", "Login test", "passed")]

        mock_base = MagicMock()
        mock_base.scalars.return_value.all.return_value = base
        mock_compare = MagicMock()
        mock_compare.scalars.return_value.all.return_value = compare
        repo.session.execute = AsyncMock(side_effect=[mock_base, mock_compare])

        diff = await repo.diff_sessions("s1", "s2")

        assert diff["summary"]["removed_tests"] == 1
        assert "t2" in diff["removed_tests"]

    @pytest.mark.asyncio
    async def test_pass_rate_delta(self, repo):
        """Pass rate delta reflects regression impact."""
        base = [
            _make_result("t1", "Test 1", "passed"),
            _make_result("t2", "Test 2", "passed"),
            _make_result("t3", "Test 3", "passed"),
            _make_result("t4", "Test 4", "passed"),
        ]
        compare = [
            _make_result("t1", "Test 1", "passed"),
            _make_result("t2", "Test 2", "failed"),
            _make_result("t3", "Test 3", "passed"),
            _make_result("t4", "Test 4", "failed"),
        ]

        mock_base = MagicMock()
        mock_base.scalars.return_value.all.return_value = base
        mock_compare = MagicMock()
        mock_compare.scalars.return_value.all.return_value = compare
        repo.session.execute = AsyncMock(side_effect=[mock_base, mock_compare])

        diff = await repo.diff_sessions("s1", "s2")

        assert diff["summary"]["base_pass_rate"] == 100.0
        assert diff["summary"]["compare_pass_rate"] == 50.0
        assert diff["summary"]["pass_rate_delta"] == -50.0

    @pytest.mark.asyncio
    async def test_empty_sessions(self, repo):
        """Diffing two empty sessions returns zeroes."""
        mock_base = MagicMock()
        mock_base.scalars.return_value.all.return_value = []
        mock_compare = MagicMock()
        mock_compare.scalars.return_value.all.return_value = []
        repo.session.execute = AsyncMock(side_effect=[mock_base, mock_compare])

        diff = await repo.diff_sessions("s1", "s2")

        assert diff["summary"]["base_total"] == 0
        assert diff["summary"]["compare_total"] == 0
        assert diff["has_regressions"] is False

    @pytest.mark.asyncio
    async def test_avg_time_included(self, repo):
        """Average execution time is included in summary."""
        base = [
            _make_result("t1", "Test 1", "passed", 100),
            _make_result("t2", "Test 2", "passed", 200),
        ]
        compare = [
            _make_result("t1", "Test 1", "passed", 300),
            _make_result("t2", "Test 2", "passed", 400),
        ]

        mock_base = MagicMock()
        mock_base.scalars.return_value.all.return_value = base
        mock_compare = MagicMock()
        mock_compare.scalars.return_value.all.return_value = compare
        repo.session.execute = AsyncMock(side_effect=[mock_base, mock_compare])

        diff = await repo.diff_sessions("s1", "s2")

        assert diff["summary"]["base_avg_time_ms"] == 150.0
        assert diff["summary"]["compare_avg_time_ms"] == 350.0

    @pytest.mark.asyncio
    async def test_session_ids_in_response(self, repo):
        """Response includes both session IDs."""
        mock_base = MagicMock()
        mock_base.scalars.return_value.all.return_value = []
        mock_compare = MagicMock()
        mock_compare.scalars.return_value.all.return_value = []
        repo.session.execute = AsyncMock(side_effect=[mock_base, mock_compare])

        diff = await repo.diff_sessions("base-123", "compare-456")

        assert diff["base_session_id"] == "base-123"
        assert diff["compare_session_id"] == "compare-456"
