import os
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

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
            ReportRequest,
            ReportType,
        )
    except ImportError:
        pytest.skip("webgui.exports module not available", allow_module_level=True)


@pytest.fixture()
def report_gen(mock_redis, tmp_path):
    """Create ReportGenerator with mocked Redis and temp reports dir."""
    with (
        patch("webgui.exports.config") as mock_config,
        patch.object(Path, "mkdir", return_value=None),
    ):
        mock_config.get_redis_client.return_value = mock_redis
        gen = ReportGenerator()
        gen.reports_dir = tmp_path / "reports"
    gen.reports_dir.mkdir(exist_ok=True)
    return gen


class TestReportGeneratorInit:
    """Tests for ReportGenerator initialization"""

    def test_init(self, mock_redis):
        with (
            patch("webgui.exports.config") as mock_config,
            patch.object(Path, "mkdir", return_value=None),
        ):
            mock_config.get_redis_client.return_value = mock_redis
            gen = ReportGenerator()
        assert gen.redis_client is mock_redis

    def test_report_formats(self):
        assert ReportFormat.PDF.value == "pdf"
        assert ReportFormat.JSON.value == "json"
        assert ReportFormat.CSV.value == "csv"
        assert ReportFormat.HTML.value == "html"

    def test_report_types(self):
        assert ReportType.EXECUTIVE_SUMMARY.value == "executive_summary"
        assert ReportType.TECHNICAL_REPORT.value == "technical_report"
        assert ReportType.COMPLIANCE_REPORT.value == "compliance_report"


class TestReportRequest:
    """Tests for ReportRequest dataclass"""

    def test_creation(self):
        req = ReportRequest(
            session_id="session_123",
            report_type=ReportType.EXECUTIVE_SUMMARY,
            format=ReportFormat.JSON,
        )
        assert req.session_id == "session_123"
        assert req.include_charts is True  # default
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


class TestReportGeneration:
    """Tests for report generation methods"""

    @pytest.mark.asyncio
    async def test_collect_session_data(self, report_gen):
        data = await report_gen._collect_session_data("session_test")
        assert data["session_id"] == "session_test"
        assert "info" in data
        assert "test_plan" in data
        assert "metrics" in data

    @pytest.mark.asyncio
    async def test_collect_session_data_with_redis_data(self, report_gen, mock_redis):
        import json

        mock_redis.get.side_effect = lambda key: (
            json.dumps({"status": "completed"}) if "info" in key else None
        )
        data = await report_gen._collect_session_data("s1")
        assert data["session_id"] == "s1"


class TestGenerateFileSanitization:
    """Verify session_id sanitization prevents path traversal in generated filenames."""

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
        # File must stay within reports dir
        assert generated.resolve().is_relative_to(report_gen.reports_dir.resolve())
        # Path separators must not be present in the session_id portion
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
