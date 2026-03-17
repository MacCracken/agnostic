"""Tests for webgui/exports.py — ReportGenerator, enums, dataclasses, and
path traversal sanitization in generated filenames."""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

# Patch Path.mkdir before importing (singleton creates /app/reports at import time)
with (
    patch.object(Path, "mkdir", return_value=None),
    patch("config.environment.config") as _mock_cfg,
):
    _mock_cfg.get_redis_client.return_value = Mock()
    try:
        from webgui.exports import (
            ReportFormat,
            ReportGenerator,
            ReportMetadata,
            ReportRequest,
            ReportType,
        )
    except ImportError:
        pytest.skip("webgui.exports module not available", allow_module_level=True)


_mock_redis = Mock()


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


def _make_generator():
    with patch.object(Path, "mkdir", return_value=None):
        gen = ReportGenerator()
    gen.redis_client = _mock_redis
    return gen


@pytest.fixture()
def report_gen(tmp_path):
    """Create ReportGenerator with mocked Redis and temp reports dir."""
    with (
        patch("webgui.exports.config") as mock_config,
        patch.object(Path, "mkdir", return_value=None),
    ):
        mock_config.get_redis_client.return_value = _mock_redis
        gen = ReportGenerator()
        gen.reports_dir = tmp_path / "reports"
    gen.reports_dir.mkdir(exist_ok=True)
    return gen


# ---------------------------------------------------------------------------
# Enums and models
# ---------------------------------------------------------------------------


class TestEnums:
    def test_report_format_values(self):
        assert ReportFormat.PDF.value == "pdf"
        assert ReportFormat.JSON.value == "json"
        assert ReportFormat.CSV.value == "csv"
        assert ReportFormat.HTML.value == "html"

    def test_report_type_values(self):
        assert ReportType.EXECUTIVE_SUMMARY.value == "executive_summary"
        assert ReportType.TECHNICAL_REPORT.value == "technical_report"
        assert ReportType.COMPLIANCE_REPORT.value == "compliance_report"


class TestReportRequest:
    def test_creation(self):
        req = ReportRequest(
            session_id="s1",
            report_type=ReportType.EXECUTIVE_SUMMARY,
            format=ReportFormat.JSON,
        )
        assert req.session_id == "s1"
        assert req.include_charts is True
        assert req.template is None

    def test_creation_with_all_fields(self):
        req = ReportRequest(
            session_id="s1",
            report_type=ReportType.COMPLIANCE_REPORT,
            format=ReportFormat.PDF,
            template="custom",
            custom_filters={"severity": "high"},
            include_charts=False,
            branding={"logo": "logo.png"},
        )
        assert req.include_charts is False
        assert req.branding == {"logo": "logo.png"}


class TestReportMetadata:
    def test_creation(self):
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


# ---------------------------------------------------------------------------
# ReportGenerator initialization
# ---------------------------------------------------------------------------


class TestReportGeneratorInit:
    def test_init(self):
        with (
            patch("webgui.exports.config") as mock_config,
            patch.object(Path, "mkdir", return_value=None),
        ):
            mock_config.get_redis_client.return_value = _mock_redis
            gen = ReportGenerator()
        assert gen.redis_client is _mock_redis


# ---------------------------------------------------------------------------
# Session data collection
# ---------------------------------------------------------------------------


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

    @pytest.mark.asyncio
    async def test_collect_with_redis_data(self, report_gen):
        _mock_redis.get.side_effect = lambda key: (
            json.dumps({"status": "completed"}) if "info" in key else None
        )
        data = await report_gen._collect_session_data("s1")
        assert data["session_id"] == "s1"


# ---------------------------------------------------------------------------
# Session metrics calculation
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Path traversal sanitization in generated filenames
# ---------------------------------------------------------------------------


class TestGenerateFileSanitization:
    @pytest.mark.asyncio
    async def test_path_traversal_in_session_id_is_neutralized(self, report_gen):
        """../../etc/passwd as session_id must not escape reports_dir."""
        content = {"summary": "safe"}
        req = ReportRequest(
            session_id="../../etc/passwd",
            report_type=ReportType.EXECUTIVE_SUMMARY,
            format=ReportFormat.JSON,
        )
        file_path_str, _ = await report_gen._generate_file(
            content, ReportFormat.JSON, req
        )
        generated = Path(file_path_str)
        assert generated.resolve().is_relative_to(report_gen.reports_dir.resolve())
        assert ".." not in generated.name
        assert "/" not in generated.name

    @pytest.mark.asyncio
    async def test_normal_session_id_preserved(self, report_gen):
        """Normal session IDs like session_20260101_abc should be untouched."""
        content = {"summary": "ok"}
        req = ReportRequest(
            session_id="session_20260101_abc123",
            report_type=ReportType.EXECUTIVE_SUMMARY,
            format=ReportFormat.JSON,
        )
        file_path_str, _ = await report_gen._generate_file(
            content, ReportFormat.JSON, req
        )
        generated = Path(file_path_str)
        assert "session_20260101_abc123" in generated.name
