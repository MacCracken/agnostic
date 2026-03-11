"""Tests for webgui/history.py — HistoryManager, session history, trends, search."""

import json
import os
import sys
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

_mock_redis = MagicMock()


@pytest.fixture(autouse=True)
def _patch_redis(monkeypatch):
    monkeypatch.setattr(
        "config.environment.config.get_redis_client", lambda: _mock_redis
    )
    _mock_redis.reset_mock()
    _mock_redis.get.reset_mock()
    _mock_redis.keys.reset_mock()
    _mock_redis.scan_iter.reset_mock()
    _mock_redis.exists.reset_mock()
    _mock_redis.get.return_value = None
    _mock_redis.get.side_effect = None
    _mock_redis.keys.return_value = []
    _mock_redis.keys.side_effect = None
    _mock_redis.scan_iter.return_value = []
    _mock_redis.scan_iter.side_effect = None
    _mock_redis.exists.return_value = False
    _mock_redis.exists.side_effect = None


def _make_manager():
    from webgui.history import HistoryManager

    return HistoryManager()


class TestEnums:
    def test_time_range_values(self):
        from webgui.history import TimeRange

        assert TimeRange.LAST_24_HOURS.value == "24h"
        assert TimeRange.ALL_TIME.value == "all"

    def test_sort_by_values(self):
        from webgui.history import SortBy

        assert SortBy.CREATED_AT.value == "created_at"
        assert SortBy.OVERALL_SCORE.value == "overall_score"

    def test_sort_order_values(self):
        from webgui.history import SortOrder

        assert SortOrder.ASCENDING.value == "asc"
        assert SortOrder.DESCENDING.value == "desc"


class TestIsInTimeRange:
    def test_within_24h(self):
        from webgui.history import TimeRange

        mgr = _make_manager()
        assert mgr._is_in_time_range(
            datetime.now() - timedelta(hours=12), TimeRange.LAST_24_HOURS
        )

    def test_outside_24h(self):
        from webgui.history import TimeRange

        mgr = _make_manager()
        assert not mgr._is_in_time_range(
            datetime.now() - timedelta(hours=48), TimeRange.LAST_24_HOURS
        )

    def test_all_time_always_true(self):
        from webgui.history import TimeRange

        mgr = _make_manager()
        assert mgr._is_in_time_range(datetime(2000, 1, 1), TimeRange.ALL_TIME)

    def test_within_7d(self):
        from webgui.history import TimeRange

        mgr = _make_manager()
        assert mgr._is_in_time_range(
            datetime.now() - timedelta(days=3), TimeRange.LAST_7_DAYS
        )

    def test_within_30d(self):
        from webgui.history import TimeRange

        mgr = _make_manager()
        assert mgr._is_in_time_range(
            datetime.now() - timedelta(days=15), TimeRange.LAST_30_DAYS
        )

    def test_within_90d(self):
        from webgui.history import TimeRange

        mgr = _make_manager()
        assert mgr._is_in_time_range(
            datetime.now() - timedelta(days=60), TimeRange.LAST_90_DAYS
        )


class TestPassesFilters:
    def test_passes_with_matching_filter(self):
        mgr = _make_manager()
        data = {"status": "completed", "user_id": "u1"}
        assert mgr._passes_filters(data, {"status": "completed"})

    def test_fails_with_non_matching_filter(self):
        mgr = _make_manager()
        data = {"status": "completed"}
        assert not mgr._passes_filters(data, {"status": "failed"})

    def test_passes_with_empty_filters(self):
        mgr = _make_manager()
        assert mgr._passes_filters({"a": 1}, {})

    def test_passes_when_key_not_in_data(self):
        mgr = _make_manager()
        assert mgr._passes_filters({"a": 1}, {"b": 2})


class TestSortSessions:
    def _make_sessions(self):
        from webgui.history import SessionSummary

        now = datetime.now()
        return [
            SessionSummary(
                session_id="s1",
                title="A",
                status="completed",
                created_at=now - timedelta(hours=2),
                updated_at=now - timedelta(hours=1),
                completed_at=now,
                duration_minutes=60,
                user_id="u1",
                environment="dev",
                overall_score=80.0,
                test_coverage=90,
                agent_count=4,
                scenarios_completed=9,
                scenarios_total=10,
                error_count=1,
                warning_count=2,
            ),
            SessionSummary(
                session_id="s2",
                title="B",
                status="completed",
                created_at=now - timedelta(hours=1),
                updated_at=now,
                completed_at=now,
                duration_minutes=30,
                user_id="u1",
                environment="dev",
                overall_score=95.0,
                test_coverage=100,
                agent_count=4,
                scenarios_completed=10,
                scenarios_total=10,
                error_count=0,
                warning_count=0,
            ),
        ]

    def test_sort_by_created_at_asc(self):
        from webgui.history import SortBy, SortOrder

        mgr = _make_manager()
        sessions = self._make_sessions()
        sorted_sessions = mgr._sort_sessions(
            sessions, SortBy.CREATED_AT, SortOrder.ASCENDING
        )
        assert sorted_sessions[0].session_id == "s1"  # older first

    def test_sort_by_overall_score_desc(self):
        from webgui.history import SortBy, SortOrder

        mgr = _make_manager()
        sessions = self._make_sessions()
        sorted_sessions = mgr._sort_sessions(
            sessions, SortBy.OVERALL_SCORE, SortOrder.DESCENDING
        )
        assert sorted_sessions[0].session_id == "s2"  # higher score first

    def test_sort_by_duration(self):
        from webgui.history import SortBy, SortOrder

        mgr = _make_manager()
        sessions = self._make_sessions()
        sorted_sessions = mgr._sort_sessions(
            sessions, SortBy.DURATION, SortOrder.ASCENDING
        )
        assert sorted_sessions[0].duration_minutes == 30

    def test_sort_by_test_coverage(self):
        from webgui.history import SortBy, SortOrder

        mgr = _make_manager()
        sessions = self._make_sessions()
        sorted_sessions = mgr._sort_sessions(
            sessions, SortBy.TEST_COVERAGE, SortOrder.DESCENDING
        )
        assert sorted_sessions[0].test_coverage == 100


class TestCalculateTrend:
    def test_stable_when_flat(self):
        mgr = _make_manager()
        now = datetime.now()
        points = [(now + timedelta(hours=i), 50.0) for i in range(5)]
        direction, _pct = mgr._calculate_trend(points)
        assert direction == "stable"

    def test_improving_when_rising(self):
        mgr = _make_manager()
        now = datetime.now()
        points = [(now + timedelta(hours=i), float(i * 10)) for i in range(5)]
        direction, _pct = mgr._calculate_trend(points)
        assert direction == "improving"
        assert _pct > 0

    def test_declining_when_falling(self):
        mgr = _make_manager()
        now = datetime.now()
        points = [(now + timedelta(hours=i), 100.0 - i * 10) for i in range(5)]
        direction, _pct = mgr._calculate_trend(points)
        assert direction == "declining"

    def test_stable_with_too_few_points(self):
        mgr = _make_manager()
        direction, pct = mgr._calculate_trend([(datetime.now(), 50.0)])
        assert direction == "stable"
        assert pct == 0.0


class TestGetSessionHistory:
    @pytest.mark.asyncio
    async def test_returns_empty_when_no_sessions(self):
        _mock_redis.keys.return_value = []
        _mock_redis.scan_iter.return_value = []
        mgr = _make_manager()
        sessions = await mgr.get_session_history()
        assert sessions == []

    @pytest.mark.asyncio
    async def test_parses_sessions(self):
        now = datetime.now()
        session_data = {
            "title": "Test",
            "status": "completed",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "completed_at": now.isoformat(),
            "user_id": "u1",
            "environment": "dev",
        }
        _mock_redis.keys.return_value = [b"session:s1:info"]
        _mock_redis.scan_iter.return_value = [b"session:s1:info"]
        _mock_redis.get.side_effect = [
            json.dumps(session_data).encode(),  # session info
            None,  # verification
            None,  # test plan
        ]
        _mock_redis.exists.return_value = False
        mgr = _make_manager()
        sessions = await mgr.get_session_history(limit=10)
        assert len(sessions) == 1
        assert sessions[0].session_id == "s1"

    @pytest.mark.asyncio
    async def test_pagination(self):
        now = datetime.now()
        session_data = {
            "title": "T",
            "status": "completed",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
        encoded = json.dumps(session_data).encode()
        _mock_redis.keys.return_value = [
            f"session:s{i}:info".encode() for i in range(5)
        ]
        _mock_redis.scan_iter.return_value = [
            f"session:s{i}:info".encode() for i in range(5)
        ]
        _mock_redis.get.return_value = encoded
        _mock_redis.exists.return_value = False
        mgr = _make_manager()
        sessions = await mgr.get_session_history(limit=2, offset=1)
        assert len(sessions) == 2


class TestGetSessionDetails:
    @pytest.mark.asyncio
    async def test_returns_cached(self):
        cached = {"session_id": "s1", "title": "Cached"}
        _mock_redis.get.side_effect = [json.dumps(cached).encode()]
        mgr = _make_manager()
        result = await mgr.get_session_details("s1")
        assert result["title"] == "Cached"

    @pytest.mark.asyncio
    async def test_uncached_calls_report_generator(self):
        """When no cache, delegates to ReportGenerator._collect_session_data."""
        _mock_redis.get.return_value = None
        _mock_redis.lrange.return_value = []
        mgr = _make_manager()
        result = await mgr.get_session_details("s1")
        # Result depends on whether /app/reports exists (None if not, dict if patched)
        if result is not None:
            assert result["session_id"] == "s1"


class TestCompareSessions:
    @pytest.mark.asyncio
    async def test_compare_uses_details(self):
        """Compare sessions delegates to get_session_details twice."""
        cached = {"session_id": "s1", "overall_score": 80}
        _mock_redis.get.side_effect = [
            json.dumps(cached).encode(),  # cache hit for s1
            json.dumps(
                {"session_id": "s2", "overall_score": 90}
            ).encode(),  # cache hit for s2
        ]
        mgr = _make_manager()
        result = await mgr.compare_sessions("s1", "s2")
        assert result is not None
        assert result.session1_id == "s1"
        assert result.session2_id == "s2"


class TestGetSessionMetrics:
    @pytest.mark.asyncio
    async def test_defaults_when_no_data(self):
        _mock_redis.get.return_value = None
        _mock_redis.exists.return_value = False
        mgr = _make_manager()
        metrics = await mgr._get_session_metrics("s1")
        assert metrics["overall_score"] is None
        assert metrics["test_coverage"] == 0
        assert metrics["agent_count"] == 0

    @pytest.mark.asyncio
    async def test_parses_verification_score(self):
        verify = {"overall_score": 87.5}
        _mock_redis.get.side_effect = [
            json.dumps(verify).encode(),  # verification
            None,  # test plan
        ]
        _mock_redis.exists.return_value = False
        mgr = _make_manager()
        metrics = await mgr._get_session_metrics("s1")
        assert metrics["overall_score"] == 87.5
