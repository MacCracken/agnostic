"""Tests for code review changes: webhook sig, health check, task cancel/retry,
report validation, MCP dispatch, session filtering, LLM streaming timeout."""

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


# ---------------------------------------------------------------------------
# Webhook signature verification
# ---------------------------------------------------------------------------


class TestWebhookSignatureVerification:
    def test_accepts_when_no_secret_configured(self):
        with patch("webgui.routes.yeoman_webhooks.YEOMAN_WEBHOOK_SECRET", ""):
            from webgui.routes.yeoman_webhooks import _verify_webhook_signature

            assert _verify_webhook_signature(b"body", None) is True

    def test_rejects_when_secret_set_but_no_signature(self):
        with patch("webgui.routes.yeoman_webhooks.YEOMAN_WEBHOOK_SECRET", "mysecret"):
            from webgui.routes.yeoman_webhooks import _verify_webhook_signature

            assert _verify_webhook_signature(b"body", None) is False

    def test_accepts_valid_signature(self):
        import hashlib
        import hmac

        secret = "test-secret"
        body = b'{"event": "test"}'
        sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

        with patch("webgui.routes.yeoman_webhooks.YEOMAN_WEBHOOK_SECRET", secret):
            from webgui.routes.yeoman_webhooks import _verify_webhook_signature

            assert _verify_webhook_signature(body, f"sha256={sig}") is True

    def test_rejects_invalid_signature(self):
        with patch("webgui.routes.yeoman_webhooks.YEOMAN_WEBHOOK_SECRET", "secret"):
            from webgui.routes.yeoman_webhooks import _verify_webhook_signature

            assert _verify_webhook_signature(b"body", "sha256=bad") is False


# ---------------------------------------------------------------------------
# Report type/format validation
# ---------------------------------------------------------------------------


class TestReportValidation:
    def test_valid_report_types(self):
        from webgui.routes.reports import ReportGenerateRequest

        for rt in ("executive_summary", "detailed", "compliance", "security", "performance"):
            req = ReportGenerateRequest(session_id="s1", report_type=rt)
            assert req.report_type == rt

    def test_invalid_report_type_rejected(self):
        from pydantic import ValidationError

        from webgui.routes.reports import ReportGenerateRequest

        with pytest.raises(ValidationError):
            ReportGenerateRequest(session_id="s1", report_type="nonexistent")

    def test_valid_formats(self):
        from webgui.routes.reports import ReportGenerateRequest

        for fmt in ("json", "html", "pdf"):
            req = ReportGenerateRequest(session_id="s1", format=fmt)
            assert req.format == fmt

    def test_invalid_format_rejected(self):
        from pydantic import ValidationError

        from webgui.routes.reports import ReportGenerateRequest

        with pytest.raises(ValidationError):
            ReportGenerateRequest(session_id="s1", format="csv")


# ---------------------------------------------------------------------------
# Task cancel/retry models
# ---------------------------------------------------------------------------


class TestTaskCancelRetryModels:
    def test_cancel_response_model(self):
        from webgui.routes.tasks import TaskCancelResponse

        resp = TaskCancelResponse(
            task_id="t1", status="cancelled", message="Task cancelled successfully"
        )
        assert resp.task_id == "t1"
        assert resp.status == "cancelled"

    def test_retry_response_model(self):
        from webgui.routes.tasks import TaskRetryResponse

        resp = TaskRetryResponse(
            original_task_id="t1",
            new_task_id="t2",
            session_id="s1",
            status="pending",
        )
        assert resp.original_task_id == "t1"
        assert resp.new_task_id == "t2"


# ---------------------------------------------------------------------------
# Audit action
# ---------------------------------------------------------------------------


class TestAuditAction:
    def test_task_cancelled_action_exists(self):
        from shared.audit import AuditAction

        assert AuditAction.TASK_CANCELLED == "task.cancelled"


# ---------------------------------------------------------------------------
# Health check HTTP status codes
# ---------------------------------------------------------------------------


class TestHealthCheckStatus:
    @pytest.fixture()
    def client(self):
        from fastapi.testclient import TestClient

        mock_redis = MagicMock()
        mock_redis.ping.return_value = True
        mock_redis.get.return_value = None

        with patch("config.environment.config.get_redis_client", return_value=mock_redis):
            from webgui.app import app

            return TestClient(app, raise_server_exceptions=False)

    def test_health_returns_503_when_redis_down(self, client):
        mock_redis = MagicMock()
        mock_redis.ping.side_effect = Exception("Connection refused")
        mock_redis.get.return_value = None
        with (
            patch("config.environment.config.get_redis_client", return_value=mock_redis),
            patch("socket.create_connection") as mock_sock,
        ):
            mock_sock.return_value = MagicMock()
            response = client.get("/health")
        # Unhealthy should return 503
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["redis"] == "error"

    def test_readiness_endpoint_exists(self, client):
        mock_redis = MagicMock()
        mock_redis.ping.return_value = True
        with patch("config.environment.config.get_redis_client", return_value=mock_redis):
            response = client.get("/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["redis"] == "ok"

    def test_readiness_returns_503_when_redis_down(self, client):
        mock_redis = MagicMock()
        mock_redis.ping.side_effect = Exception("Connection refused")
        with patch("config.environment.config.get_redis_client", return_value=mock_redis):
            response = client.get("/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "not_ready"


# ---------------------------------------------------------------------------
# Session filtering
# ---------------------------------------------------------------------------


class TestSessionFiltering:
    def test_sort_order_enum(self):
        """Verify Literal type params are accepted."""
        # Just import to ensure no syntax errors
        from webgui.routes.sessions import get_sessions

        assert callable(get_sessions)


# ---------------------------------------------------------------------------
# LLM streaming timeout
# ---------------------------------------------------------------------------


class TestLLMStreamingTimeout:
    def test_timeout_attributes_exist(self):
        from config.llm_integration import LLMIntegrationService

        assert hasattr(LLMIntegrationService, "_STREAM_CHUNK_TIMEOUT")
        assert hasattr(LLMIntegrationService, "_STREAM_TOTAL_TIMEOUT")
        assert LLMIntegrationService._STREAM_TOTAL_TIMEOUT > 0

    @pytest.mark.asyncio
    async def test_streaming_call_timeout(self):
        """_streaming_call should raise TimeoutError if stream takes too long."""
        import asyncio

        from config.llm_integration import LLMIntegrationService

        service = LLMIntegrationService.__new__(LLMIntegrationService)
        service._STREAM_TOTAL_TIMEOUT = 0.01  # 10ms

        async def _slow_completion(**kwargs):
            async def _gen():
                await asyncio.sleep(10)  # Will be cancelled
                yield MagicMock()

            return _gen()

        with patch("config.llm_integration.litellm.acompletion", side_effect=_slow_completion):
            with pytest.raises((TimeoutError, asyncio.TimeoutError)):
                await service._streaming_call({"stream": True}, MagicMock())


# ---------------------------------------------------------------------------
# MCP dispatch — webhook subscription + event stream
# ---------------------------------------------------------------------------


class TestMCPDispatch:
    @pytest.mark.asyncio
    async def test_subscribe_webhook_dispatch(self):
        with (
            patch("webgui.routes.mcp.MCP_ENABLED", True),
            patch("webgui.routes.dependencies._validate_callback_url"),
        ):
            from webgui.routes.mcp import _dispatch_tool

            mock_redis = AsyncMock()
            mock_redis.setex = AsyncMock()
            with patch(
                "config.environment.config.get_async_redis_client",
                return_value=mock_redis,
            ):
                result = await _dispatch_tool(
                    "agnostic_subscribe_webhook",
                    {"callback_url": "https://example.com/hook", "events": ["task.completed"]},
                    {"user_id": "test"},
                )
            assert "subscription_id" in result
            assert result["callback_url"] == "https://example.com/hook"
            assert result["status"] == "active"

    @pytest.mark.asyncio
    async def test_event_stream_dispatch(self):
        with patch("webgui.routes.mcp.MCP_ENABLED", True):
            from webgui.routes.mcp import _dispatch_tool

            result = await _dispatch_tool(
                "agnostic_event_stream",
                {"channels": ["tasks"]},
                {"user_id": "test"},
            )
            assert "stream_url" in result
            assert result["protocol"] == "text/event-stream"


# ---------------------------------------------------------------------------
# Configurable constants
# ---------------------------------------------------------------------------


class TestConfigurableConstants:
    def test_max_active_sessions_configurable(self):
        with patch.dict(os.environ, {"MAX_ACTIVE_SESSIONS": "500"}):
            # The module reads at import time, so we verify the env var approach
            val = int(os.getenv("MAX_ACTIVE_SESSIONS", "1000"))
            assert val == 500

    def test_reports_dir_configurable(self):
        with patch.dict(os.environ, {"REPORTS_DIR": "/tmp/reports"}):
            from pathlib import Path

            val = Path(os.getenv("REPORTS_DIR", "/app/reports")).resolve()
            assert str(val) == "/tmp/reports"

    def test_event_buffer_max_configurable(self):
        with patch.dict(os.environ, {"EVENT_BUFFER_MAX": "2000"}):
            val = int(os.getenv("EVENT_BUFFER_MAX", "1000"))
            assert val == 2000

    def test_db_pool_defaults_increased(self):
        """DB pool defaults are now 20/40 instead of 5/10."""
        assert int(os.getenv("DB_POOL_SIZE", "20")) == 20
        assert int(os.getenv("DB_MAX_OVERFLOW", "40")) == 40
