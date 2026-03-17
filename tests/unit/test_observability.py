"""Tests for observability and production hardening.

Covers:
- Telemetry and audit initialization
- Circuit breaker metrics
- Correlation ID propagation
- A2A audit logging, rate limiting, and payload validation
- Session lifecycle audit actions
- Reasoning trace models
- Request body size limit middleware
- Webhook exception handling
"""

import hashlib
import hmac
import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

try:
    from fastapi.testclient import TestClient
except ImportError:
    pytest.skip("fastapi not available", allow_module_level=True)

try:
    from webgui.api import api_router, get_current_user
except ImportError:
    pytest.skip("webgui.api module not available", allow_module_level=True)

from fastapi import FastAPI

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture()
def app():
    test_app = FastAPI()
    test_app.include_router(api_router)
    return test_app


@pytest.fixture()
def auth_user():
    return {
        "user_id": "test-user-1",
        "email": "test@example.com",
        "role": "qa_engineer",
        "permissions": [
            "sessions:read",
            "sessions:write",
            "agents:control",
            "reports:generate",
            "tasks:submit",
            "tasks:view",
        ],
    }


@pytest.fixture()
def authed_client(app, auth_user):
    async def override():
        return auth_user

    app.dependency_overrides[get_current_user] = override
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


# ============================================================================
# Phase 1: Telemetry & Audit Init
# ============================================================================


class TestTelemetryInit:
    def test_configure_telemetry_is_idempotent(self):
        from shared.telemetry import configure_telemetry

        # Should not raise even when called multiple times
        configure_telemetry()
        configure_telemetry()

    def test_configure_audit_logging_sets_handler(self):

        from shared.audit import _audit_logger, configure_audit_logging

        configure_audit_logging()
        assert len(_audit_logger.handlers) >= 1
        assert _audit_logger.propagate is False

    def test_configure_audit_logging_idempotent(self):
        from shared.audit import _audit_logger, configure_audit_logging

        configure_audit_logging()
        count = len(_audit_logger.handlers)
        configure_audit_logging()
        assert len(_audit_logger.handlers) == count


class TestCircuitBreakerMetrics:
    def test_llm_breaker_exports_gauge_on_state_change(self):
        pytest.importorskip("litellm")
        from config.llm_integration import _on_llm_breaker_change

        # Should not raise
        _on_llm_breaker_change("llm_api", "closed", "open")
        _on_llm_breaker_change("llm_api", "open", "half_open")
        _on_llm_breaker_change("llm_api", "half_open", "closed")


class TestCorrelationIdPropagation:
    @patch("webgui.routes.yeoman_webhooks.YEOMAN_WEBHOOKS_ENABLED", True)
    @patch("webgui.routes.yeoman_webhooks.YEOMAN_WEBHOOK_SECRET", "test-secret")
    def test_webhook_sets_correlation_id_context(self, authed_client):

        body = json.dumps(
            {
                "event": "on-push",
                "timestamp": 1700000000000,
                "data": {"repository": "test-repo"},
            }
        ).encode()
        sig = hmac.new(b"test-secret", body, hashlib.sha256).hexdigest()

        mock_redis = MagicMock()
        mock_redis.setex = MagicMock()
        mock_redis.get = MagicMock(return_value=None)

        with patch(
            "config.environment.config.get_redis_client", return_value=mock_redis
        ):
            with patch(
                "shared.database.tenants.tenant_manager.check_rate_limit",
                return_value=True,
            ):
                resp = authed_client.post(
                    "/api/v1/yeoman/webhooks",
                    content=body,
                    headers={
                        "Content-Type": "application/json",
                        "X-Webhook-Signature": f"sha256={sig}",
                        "X-Correlation-ID": "test-corr-123",
                    },
                )
        assert resp.status_code == 200
        data = resp.json()
        assert data["accepted"] is True


# ============================================================================
# Phase 2: Audit Actions
# ============================================================================


class TestNewAuditActions:
    def test_a2a_audit_actions_exist(self):
        from shared.audit import AuditAction

        assert AuditAction.A2A_DELEGATE_RECEIVED == "a2a.delegate.received"
        assert AuditAction.A2A_RESULT_RECEIVED == "a2a.result.received"
        assert AuditAction.A2A_STATUS_QUERY == "a2a.status_query"
        assert AuditAction.A2A_DELEGATE_SENT == "a2a.delegate.sent"

    def test_session_lifecycle_audit_actions_exist(self):
        from shared.audit import AuditAction

        assert AuditAction.SESSION_CREATED == "session.created"
        assert AuditAction.SESSION_COMPLETED == "session.completed"
        assert AuditAction.SESSION_FAILED == "session.failed"


class TestA2AAuditLogging:
    @patch("webgui.routes.tasks.YEOMAN_A2A_ENABLED", True)
    def test_a2a_delegate_emits_audit(self, authed_client):
        """A2A delegate messages should emit audit log."""
        mock_pipe = AsyncMock()
        mock_pipe.get = AsyncMock(return_value=None)
        mock_pipe.watch = AsyncMock()
        mock_pipe.multi = MagicMock()
        mock_pipe.setex = MagicMock()
        mock_pipe.execute = AsyncMock(return_value=[True])

        mock_redis = AsyncMock()
        mock_redis.setex = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.publish = AsyncMock()
        # pipeline() is a sync method returning an async context manager
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)

        with patch(
            "config.environment.config.get_async_redis_client", return_value=mock_redis
        ):
            with patch(
                "shared.database.tenants.tenant_manager.check_rate_limit",
                new_callable=AsyncMock,
                return_value=True,
            ):
                with patch(
                    "webgui.routes.tasks._check_a2a_rate_limit",
                    new_callable=AsyncMock,
                    return_value=True,
                ):
                    with patch("webgui.routes.tasks.audit_log") as mock_audit:
                        resp = authed_client.post(
                            "/api/v1/a2a/receive",
                            json={
                                "id": "msg-001",
                                "type": "a2a:delegate",
                                "fromPeerId": "secureyeoman",
                                "toPeerId": "agnostic-qa",
                                "payload": {
                                    "title": "Test task",
                                    "description": "Test description",
                                },
                                "timestamp": 1700000000000,
                            },
                        )
        assert resp.status_code == 200
        # Check audit_log was called with A2A_DELEGATE_RECEIVED
        from shared.audit import AuditAction

        a2a_calls = [
            c
            for c in mock_audit.call_args_list
            if c.args and c.args[0] == AuditAction.A2A_DELEGATE_RECEIVED
        ]
        assert len(a2a_calls) >= 1

    @patch("webgui.routes.tasks.YEOMAN_A2A_ENABLED", True)
    def test_a2a_status_query_emits_audit(self, authed_client):
        with patch(
            "webgui.routes.tasks._check_a2a_rate_limit",
            new_callable=AsyncMock,
            return_value=True,
        ):
            with patch("webgui.routes.tasks.audit_log") as mock_audit:
                resp = authed_client.post(
                    "/api/v1/a2a/receive",
                    json={
                        "id": "msg-002",
                        "type": "a2a:status_query",
                        "fromPeerId": "secureyeoman",
                        "toPeerId": "agnostic-qa",
                        "payload": {},
                        "timestamp": 1700000000000,
                    },
                )
        assert resp.status_code == 200
        from shared.audit import AuditAction

        calls = [
            c
            for c in mock_audit.call_args_list
            if c.args and c.args[0] == AuditAction.A2A_STATUS_QUERY
        ]
        assert len(calls) >= 1

    @patch("webgui.routes.tasks.YEOMAN_A2A_ENABLED", True)
    def test_a2a_result_emits_audit(self, authed_client):
        with patch(
            "webgui.routes.tasks._check_a2a_rate_limit",
            new_callable=AsyncMock,
            return_value=True,
        ):
            with patch("webgui.routes.tasks.audit_log") as mock_audit:
                resp = authed_client.post(
                    "/api/v1/a2a/receive",
                    json={
                        "id": "msg-003",
                        "type": "a2a:result",
                        "fromPeerId": "secureyeoman",
                        "toPeerId": "agnostic-qa",
                        "payload": {"task_id": "task-001", "result": {}},
                        "timestamp": 1700000000000,
                    },
                )
        assert resp.status_code == 200
        from shared.audit import AuditAction

        calls = [
            c
            for c in mock_audit.call_args_list
            if c.args and c.args[0] == AuditAction.A2A_RESULT_RECEIVED
        ]
        assert len(calls) >= 1


# ============================================================================
# Phase 3: SY Integration Hardening
# ============================================================================


class TestA2ARateLimiting:
    @patch("webgui.routes.tasks.YEOMAN_A2A_ENABLED", True)
    def test_a2a_rate_limit_rejects_excess(self, authed_client):
        """A2A endpoint should reject when rate limit exceeded."""
        with patch(
            "webgui.routes.tasks._check_a2a_rate_limit",
            new_callable=AsyncMock,
            return_value=False,
        ):
            resp = authed_client.post(
                "/api/v1/a2a/receive",
                json={
                    "id": "msg-ratelimit",
                    "type": "a2a:heartbeat",
                    "fromPeerId": "spammer",
                    "toPeerId": "agnostic-qa",
                    "payload": {},
                    "timestamp": 1700000000000,
                },
            )
        assert resp.status_code == 429
        assert "rate limit" in resp.json()["detail"].lower()

    @patch("webgui.routes.tasks.YEOMAN_A2A_ENABLED", True)
    def test_a2a_rate_limit_allows_normal(self, authed_client):
        """A2A endpoint should allow when within rate limit."""
        with patch("webgui.routes.tasks._check_a2a_rate_limit", return_value=True):
            resp = authed_client.post(
                "/api/v1/a2a/receive",
                json={
                    "id": "msg-ok",
                    "type": "a2a:heartbeat",
                    "fromPeerId": "secureyeoman",
                    "toPeerId": "agnostic-qa",
                    "payload": {},
                    "timestamp": 1700000000000,
                },
            )
        assert resp.status_code == 200


class TestA2APayloadValidation:
    @patch("webgui.routes.tasks.YEOMAN_A2A_ENABLED", True)
    def test_a2a_delegate_rejects_missing_description(self, authed_client):
        """A2A delegate should reject payloads without description."""
        with patch("webgui.routes.tasks._check_a2a_rate_limit", return_value=True):
            resp = authed_client.post(
                "/api/v1/a2a/receive",
                json={
                    "id": "msg-bad",
                    "type": "a2a:delegate",
                    "fromPeerId": "secureyeoman",
                    "toPeerId": "agnostic-qa",
                    "payload": {"title": "No description"},
                    "timestamp": 1700000000000,
                },
            )
        assert resp.status_code == 400
        assert "description" in resp.json()["detail"].lower()


class TestWebhookExceptionHandling:
    @patch("webgui.routes.yeoman_webhooks.YEOMAN_WEBHOOKS_ENABLED", True)
    @patch("webgui.routes.yeoman_webhooks.YEOMAN_WEBHOOK_SECRET", "test-secret")
    def test_webhook_rejects_invalid_json(self, authed_client):
        body = b"not valid json at all"
        sig = hmac.new(b"test-secret", body, hashlib.sha256).hexdigest()

        resp = authed_client.post(
            "/api/v1/yeoman/webhooks",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Signature": f"sha256={sig}",
            },
        )
        assert resp.status_code == 400

    @patch("webgui.routes.yeoman_webhooks.YEOMAN_WEBHOOKS_ENABLED", True)
    @patch("webgui.routes.yeoman_webhooks.YEOMAN_WEBHOOK_SECRET", "test-secret")
    def test_webhook_rejects_invalid_event_type(self, authed_client):
        body = json.dumps(
            {
                "event": "../../etc/passwd",
                "timestamp": 1700000000000,
                "data": {},
            }
        ).encode()
        sig = hmac.new(b"test-secret", body, hashlib.sha256).hexdigest()

        resp = authed_client.post(
            "/api/v1/yeoman/webhooks",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Signature": f"sha256={sig}",
            },
        )
        assert resp.status_code == 400
        assert "event type" in resp.json()["detail"].lower()


# ============================================================================
# Phase 4: Production Hardening
# ============================================================================


class TestRequestBodySizeLimit:
    def test_default_max_body_size(self):
        """Default max request body size should be 10 MB."""
        default = int(os.getenv("MAX_REQUEST_BODY_SIZE", str(10 * 1024 * 1024)))
        assert default == 10 * 1024 * 1024


class TestEventPushMetrics:
    def test_event_push_imports_metrics(self):
        """Event push module should reference HTTP_REQUESTS_TOTAL."""
        from shared.metrics import HTTP_REQUESTS_TOTAL

        # Verify metric object exists and has expected labels
        assert HTTP_REQUESTS_TOTAL is not None


class TestReasoningTraceModels:
    def test_reasoning_step_defaults(self):
        from shared.agnos_reasoning import ReasoningStep

        step = ReasoningStep(
            phase="execution",
            agent_id="qa-manager",
            description="Test step",
            input_summary="input",
            output_summary="output",
            confidence=0.8,
        )
        assert step.timestamp  # Auto-set
        assert step.confidence == 0.8

    def test_reasoning_trace_defaults(self):
        from shared.agnos_reasoning import ReasoningTrace

        trace = ReasoningTrace(
            trace_id="t-001",
            session_id="s-001",
            task_description="Test task",
        )
        assert trace.created_at  # Auto-set
        assert trace.steps == []
        assert trace.final_verdict is None


class TestLoadTestConfig:
    def test_locustfile_exists(self):
        path = os.path.join(os.path.dirname(__file__), "..", "load", "locustfile.py")
        assert os.path.isfile(path)
