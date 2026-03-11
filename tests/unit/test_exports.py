"""Tests for webgui/exports.py — ReportGenerator, enums, dataclasses."""

import json
import os
import sys
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

_mock_redis = MagicMock()

# Patch os.mkdir before webgui.exports is imported (module-level singleton).
# Use a targeted patch so we don't break pytest's tmp_path fixture.
_original_mkdir = os.mkdir


def _safe_mkdir(path, mode=0o777):
    """Allow all mkdirs except /app/reports."""
    if str(path).startswith("/app/"):
        return
    return _original_mkdir(path, mode)


_mkdir_patcher = patch("os.mkdir", side_effect=_safe_mkdir)
_mkdir_patcher.start()


@pytest.fixture(autouse=True)
def _patch_redis(monkeypatch):
    monkeypatch.setattr(
        "config.environment.config.get_redis_client", lambda: _mock_redis
    )
    _mock_redis.reset_mock()
    _mock_redis.get.reset_mock()
    _mock_redis.lrange.reset_mock()
    _mock_redis.get.return_value = None
    _mock_redis.get.side_effect = None
    _mock_redis.lrange.return_value = []


class TestEnums:
    def test_report_format_values(self):
        from webgui.exports import ReportFormat

        assert ReportFormat.PDF.value == "pdf"
        assert ReportFormat.JSON.value == "json"
        assert ReportFormat.CSV.value == "csv"
        assert ReportFormat.HTML.value == "html"

    def test_report_type_values(self):
        from webgui.exports import ReportType

        assert ReportType.EXECUTIVE_SUMMARY.value == "executive_summary"
        assert ReportType.TECHNICAL_REPORT.value == "technical_report"
        assert ReportType.COMPLIANCE_REPORT.value == "compliance_report"


class TestReportRequest:
    def test_creation(self):
        from webgui.exports import ReportFormat, ReportRequest, ReportType

        req = ReportRequest(
            session_id="s1",
            report_type=ReportType.EXECUTIVE_SUMMARY,
            format=ReportFormat.JSON,
        )
        assert req.session_id == "s1"
        assert req.include_charts is True
        assert req.template is None


class TestReportMetadata:
    def test_creation(self):
        from webgui.exports import ReportFormat, ReportMetadata, ReportType

        meta = ReportMetadata(
            report_id="r1",
            generated_at=datetime.now(),
            generated_by="user1",
            session_id="s1",
            report_type=ReportType.TECHNICAL_REPORT,
            format=ReportFormat.PDF,
            file_size=1024,
            page_count=5,
        )
        assert meta.report_id == "r1"
        assert meta.page_count == 5


def _make_generator():
    from webgui.exports import ReportGenerator

    with patch("pathlib.Path.mkdir"):
        gen = ReportGenerator()
    gen.redis_client = _mock_redis
    return gen


class TestCollectSessionData:
    @pytest.mark.asyncio
    async def test_empty_session(self):
        gen = _make_generator()
        data = await gen._collect_session_data("missing")
        assert data["session_id"] == "missing"
        assert data["info"] == {}
        assert data["test_plan"] == {}
        assert data["agent_results"] == {}
        assert data["timeline"] == []

    @pytest.mark.asyncio
    async def test_collects_info(self):
        session_info = {"title": "Test", "status": "completed"}
        _mock_redis.get.side_effect = lambda key: (
            json.dumps(session_info).encode() if key == "session:s1:info" else None
        )
        gen = _make_generator()
        data = await gen._collect_session_data("s1")
        assert data["info"]["title"] == "Test"

    @pytest.mark.asyncio
    async def test_collects_test_plan(self):
        plan = {"scenarios": [{"name": "login"}, {"name": "checkout"}]}

        def get_side_effect(key):
            if key == "manager:s1:test_plan":
                return json.dumps(plan).encode()
            return None

        _mock_redis.get.side_effect = get_side_effect
        gen = _make_generator()
        data = await gen._collect_session_data("s1")
        assert len(data["test_plan"]["scenarios"]) == 2

    @pytest.mark.asyncio
    async def test_collects_verification(self):
        verify = {"overall_score": 85.0}

        def get_side_effect(key):
            if key == "manager:s1:verification":
                return json.dumps(verify).encode()
            return None

        _mock_redis.get.side_effect = get_side_effect
        gen = _make_generator()
        data = await gen._collect_session_data("s1")
        assert data["verification"]["overall_score"] == 85.0

    @pytest.mark.asyncio
    async def test_collects_agent_results(self):
        report = {"score": 90, "findings": []}

        def get_side_effect(key):
            if key == "manager:s1:report":
                return json.dumps(report).encode()
            return None

        _mock_redis.get.side_effect = get_side_effect
        gen = _make_generator()
        data = await gen._collect_session_data("s1")
        assert "manager" in data["agent_results"]
        assert data["agent_results"]["manager"]["score"] == 90

    @pytest.mark.asyncio
    async def test_collects_timeline(self):
        notif = json.dumps(
            {"timestamp": "2026-01-01T00:00:00", "event": "started"}
        ).encode()
        _mock_redis.lrange.return_value = [notif]

        gen = _make_generator()
        data = await gen._collect_session_data("s1")
        assert len(data["timeline"]) >= 1

    @pytest.mark.asyncio
    async def test_timeline_sorted(self):
        notif1 = json.dumps({"timestamp": "2026-01-01T02:00:00", "event": "b"}).encode()
        notif2 = json.dumps({"timestamp": "2026-01-01T01:00:00", "event": "a"}).encode()
        _mock_redis.lrange.return_value = [notif1, notif2]

        gen = _make_generator()
        data = await gen._collect_session_data("s1")
        timestamps = [e["timestamp"] for e in data["timeline"] if "timestamp" in e]
        assert timestamps == sorted(timestamps)

    @pytest.mark.asyncio
    async def test_skips_bad_notification_json(self):
        _mock_redis.lrange.return_value = [
            b"not json",
            json.dumps({"timestamp": "t"}).encode(),
        ]
        gen = _make_generator()
        data = await gen._collect_session_data("s1")
        valid = [e for e in data["timeline"] if "timestamp" in e]
        # 6 agents each get the same lrange mock, so 6 valid notifications
        assert len(valid) == 6
        # Bad JSON entries are skipped (would be 12 total otherwise)
        assert len(data["timeline"]) == 6


class TestCalculateSessionMetrics:
    def test_empty_data(self):
        gen = _make_generator()
        data = {
            "info": {},
            "verification": {},
            "agent_results": {},
            "timeline": [],
            "test_plan": {},
        }
        metrics = gen._calculate_session_metrics(data)
        assert metrics["total_agents"] == 0
        assert metrics["timeline_events"] == 0
        assert metrics["overall_score"] is None

    def test_with_verification_score(self):
        gen = _make_generator()
        data = {
            "info": {},
            "verification": {"overall_score": 92.5},
            "agent_results": {"manager": {"score": 90}},
            "timeline": [{"event": "a"}],
            "test_plan": {},
        }
        metrics = gen._calculate_session_metrics(data)
        assert metrics["overall_score"] == 92.5
        assert metrics["total_agents"] == 1
        assert metrics["timeline_events"] == 1

    def test_duration_calculation(self):
        gen = _make_generator()
        data = {
            "info": {
                "created_at": "2026-01-01T10:00:00",
                "completed_at": "2026-01-01T11:30:00",
            },
            "verification": {},
            "agent_results": {},
            "timeline": [],
            "test_plan": {},
        }
        metrics = gen._calculate_session_metrics(data)
        assert metrics["duration_minutes"] == 90

    def test_agent_scores(self):
        gen = _make_generator()
        data = {
            "info": {},
            "verification": {},
            "agent_results": {
                "manager": {"score": 85},
                "senior": {"score": 90},
                "junior": {},  # no score
            },
            "timeline": [],
            "test_plan": {},
        }
        metrics = gen._calculate_session_metrics(data)
        assert metrics["agent_scores"]["manager"] == 85
        assert metrics["agent_scores"]["senior"] == 90
        assert "junior" not in metrics["agent_scores"]
