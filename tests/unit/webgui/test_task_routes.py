"""Unit tests for P1-P4: task submission endpoints and related helpers."""

import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from pydantic import ValidationError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

try:
    from fastapi.testclient import TestClient
except ImportError:
    pytest.skip("fastapi not available", allow_module_level=True)

try:
    from webgui.api import (
        TaskStatusResponse,
        TaskSubmitRequest,
        _fire_webhook,
        api_router,
        get_current_user,
    )
except ImportError:
    pytest.skip("webgui.api module not available", allow_module_level=True)

from fastapi import FastAPI

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def app():
    """Test FastAPI app with API router."""
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
            "api:access",
            "system:configure",
        ],
    }


@pytest.fixture()
def authed_client(app, auth_user):
    async def override_get_current_user():
        return auth_user

    app.dependency_overrides[get_current_user] = override_get_current_user
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Model validation tests
# ---------------------------------------------------------------------------


class TestTaskSubmitRequest:
    def test_required_fields(self):
        req = TaskSubmitRequest(title="My Task", description="Test everything")
        assert req.title == "My Task"
        assert req.description == "Test everything"

    def test_defaults(self):
        req = TaskSubmitRequest(title="T", description="D")
        assert req.priority == "high"
        assert req.agents == []
        assert req.standards == []
        assert req.target_url is None
        assert req.callback_url is None
        assert req.callback_secret is None
        assert req.business_goals == "Ensure quality and functionality"
        assert req.constraints == "Standard testing environment"

    def test_all_fields(self):
        req = TaskSubmitRequest(
            title="Security Scan",
            description="Run OWASP checks",
            target_url="https://example.com",
            priority="critical",
            standards=["OWASP", "GDPR"],
            agents=["security-compliance"],
            business_goals="Zero vulnerabilities",
            constraints="Prod-like env",
            callback_url="https://hook.example.com/cb",
            callback_secret="mysecret",
        )
        assert req.priority == "critical"
        assert "OWASP" in req.standards
        assert req.agents == ["security-compliance"]

    def test_missing_required_fields(self):
        with pytest.raises(ValidationError):
            TaskSubmitRequest(title="Only title")

    # --- Input validation (added with security hardening) ---

    def test_title_empty_rejected(self):
        with pytest.raises(ValidationError):
            TaskSubmitRequest(title="", description="D")

    def test_title_too_long_rejected(self):
        with pytest.raises(ValidationError):
            TaskSubmitRequest(title="x" * 201, description="D")

    def test_description_too_long_rejected(self):
        with pytest.raises(ValidationError):
            TaskSubmitRequest(title="T", description="d" * 5001)

    def test_priority_invalid_rejected(self):
        with pytest.raises(ValidationError):
            TaskSubmitRequest(title="T", description="D", priority="urgent")

    def test_priority_valid_values(self):
        for p in ("critical", "high", "medium", "low"):
            req = TaskSubmitRequest(title="T", description="D", priority=p)
            assert req.priority == p

    def test_business_goals_too_long_rejected(self):
        with pytest.raises(ValidationError):
            TaskSubmitRequest(title="T", description="D", business_goals="x" * 501)

    def test_constraints_too_long_rejected(self):
        with pytest.raises(ValidationError):
            TaskSubmitRequest(title="T", description="D", constraints="x" * 501)


class TestTaskStatusResponse:
    def test_serialization(self):
        resp = TaskStatusResponse(
            task_id="abc-123",
            session_id="session_x",
            status="pending",
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
            result=None,
        )
        data = resp.model_dump()
        assert data["task_id"] == "abc-123"
        assert data["status"] == "pending"
        assert data["result"] is None

    def test_with_result(self):
        resp = TaskStatusResponse(
            task_id="abc-123",
            session_id="session_x",
            status="completed",
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:01:00Z",
            result={"pass_rate": 98.5},
        )
        assert resp.result["pass_rate"] == 98.5


# ---------------------------------------------------------------------------
# POST /api/tasks — submit_task
# ---------------------------------------------------------------------------


class TestSubmitTask:
    @patch("config.environment.config")
    @patch("webgui.api.asyncio")
    def test_submit_returns_pending(self, mock_asyncio, mock_config, authed_client):
        mock_redis = Mock()
        mock_redis.setex.return_value = True
        mock_config.get_redis_client.return_value = mock_redis
        mock_asyncio.create_task = Mock()

        resp = authed_client.post(
            "/api/v1/tasks",
            json={"title": "My Test", "description": "Run all checks"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "pending"
        assert "task_id" in data
        assert "session_id" in data
        assert data["result"] is None

    @patch("config.environment.config")
    @patch("webgui.api.asyncio")
    def test_submit_stores_in_redis(self, mock_asyncio, mock_config, authed_client):
        mock_redis = Mock()
        mock_redis.setex.return_value = True
        mock_config.get_redis_client.return_value = mock_redis
        mock_asyncio.create_task = Mock()

        authed_client.post(
            "/api/v1/tasks",
            json={"title": "T", "description": "D"},
        )

        assert mock_redis.setex.called
        call_args = mock_redis.setex.call_args
        # key should start with "task:"
        assert call_args[0][0].startswith("task:")
        # TTL should be 24h = 86400 seconds
        assert call_args[0][1] == 86400

    @patch("config.environment.config")
    @patch("webgui.api.asyncio")
    def test_submit_fires_async_task(self, mock_asyncio, mock_config, authed_client):
        mock_redis = Mock()
        mock_redis.setex.return_value = True
        mock_config.get_redis_client.return_value = mock_redis
        mock_asyncio.create_task = Mock()

        authed_client.post(
            "/api/v1/tasks",
            json={"title": "T", "description": "D"},
        )

        assert mock_asyncio.create_task.called

    def test_submit_unauthenticated(self, app):
        client = TestClient(app)
        resp = client.post(
            "/api/v1/tasks",
            json={"title": "T", "description": "D"},
        )
        assert resp.status_code == 401

    def test_submit_missing_fields(self, authed_client):
        resp = authed_client.post("/api/v1/tasks", json={"title": "T"})
        assert resp.status_code == 422

    def test_submit_invalid_priority_rejected(self, authed_client):
        resp = authed_client.post(
            "/api/v1/tasks",
            json={"title": "T", "description": "D", "priority": "urgent"},
        )
        assert resp.status_code == 422

    def test_submit_title_too_long_rejected(self, authed_client):
        resp = authed_client.post(
            "/api/v1/tasks",
            json={"title": "x" * 201, "description": "D"},
        )
        assert resp.status_code == 422

    def test_submit_description_too_long_rejected(self, authed_client):
        resp = authed_client.post(
            "/api/v1/tasks",
            json={"title": "T", "description": "d" * 5001},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/tasks/{task_id} — get_task
# ---------------------------------------------------------------------------


class TestGetTask:
    @patch("config.environment.config")
    def test_returns_404_when_missing(self, mock_config, authed_client):
        mock_redis = Mock()
        mock_redis.get.return_value = None
        mock_config.get_redis_client.return_value = mock_redis

        resp = authed_client.get("/api/v1/tasks/nonexistent-id")
        assert resp.status_code == 404

    @patch("config.environment.config")
    def test_returns_task_record(self, mock_config, authed_client):
        record = {
            "task_id": "task-abc",
            "session_id": "session_20260101",
            "status": "running",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:05+00:00",
            "result": None,
        }
        mock_redis = Mock()
        mock_redis.get.return_value = json.dumps(record).encode()
        mock_config.get_redis_client.return_value = mock_redis

        resp = authed_client.get("/api/v1/tasks/task-abc")
        assert resp.status_code == 200
        data = resp.json()
        assert data["task_id"] == "task-abc"
        assert data["status"] == "running"


# ---------------------------------------------------------------------------
# _fire_webhook — HMAC signing
# ---------------------------------------------------------------------------


class TestFireWebhook:
    @pytest.mark.asyncio
    async def test_sends_post_with_signature(self):
        import hashlib
        import hmac

        payload = {"task_id": "t1", "status": "completed"}
        secret = "mysecret"

        captured_requests = []

        class FakeResponse:
            status_code = 200

            def raise_for_status(self):
                pass

        class FakeClient:
            is_closed = False

            async def post(self, url, content, headers):
                captured_requests.append(
                    {"url": url, "content": content, "headers": headers}
                )
                return FakeResponse()

        with patch(
            "webgui.api._get_webhook_client",
            new_callable=AsyncMock,
            return_value=FakeClient(),
        ):
            await _fire_webhook(
                "https://hook.example.com/cb",
                secret,
                payload,
            )

        assert len(captured_requests) == 1
        req = captured_requests[0]
        assert req["url"] == "https://hook.example.com/cb"
        sig_header = req["headers"].get("X-Signature", "")
        assert sig_header.startswith("sha256=")

        import json as _json

        body = _json.dumps(payload)
        expected_sig = hmac.new(
            secret.encode(), body.encode(), hashlib.sha256
        ).hexdigest()
        assert sig_header == f"sha256={expected_sig}"

    @pytest.mark.asyncio
    async def test_no_signature_without_secret(self):
        payload = {"task_id": "t1"}
        captured_requests = []

        class FakeResponse:
            status_code = 200

            def raise_for_status(self):
                pass

        class FakeClient:
            is_closed = False

            async def post(self, url, content, headers):
                captured_requests.append(headers)
                return FakeResponse()

        with patch(
            "webgui.api._get_webhook_client",
            new_callable=AsyncMock,
            return_value=FakeClient(),
        ):
            await _fire_webhook("https://hook.example.com/cb", None, payload)

        assert "X-Signature" not in captured_requests[0]

    @pytest.mark.asyncio
    async def test_webhook_failure_does_not_raise(self):
        """Webhook errors should be caught and logged, not propagated."""

        class BrokenClient:
            is_closed = False

            async def post(self, *args, **kwargs):
                raise ConnectionError("unreachable")

        with (
            patch(
                "webgui.api._get_webhook_client",
                new_callable=AsyncMock,
                return_value=BrokenClient(),
            ),
            patch("webgui.api.WEBHOOK_MAX_RETRIES", 1),
        ):
            # Should not raise
            await _fire_webhook("https://bad.example.com", "secret", {"x": 1})

    @pytest.mark.asyncio
    async def test_webhook_retries_on_failure(self):
        """Webhook retries with exponential backoff on failure."""
        attempts = []

        class FailThenSucceedClient:
            is_closed = False

            async def post(self, *args, **kwargs):
                attempts.append(1)
                if len(attempts) < 3:
                    raise ConnectionError("unreachable")
                resp = MagicMock()
                resp.raise_for_status = MagicMock()
                return resp

        with (
            patch(
                "webgui.api._get_webhook_client",
                new_callable=AsyncMock,
                return_value=FailThenSucceedClient(),
            ),
            patch("webgui.api.WEBHOOK_MAX_RETRIES", 3),
            patch("webgui.api.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            await _fire_webhook("https://hook.example.com/cb", None, {"x": 1})

        assert len(attempts) == 3  # 2 failures + 1 success
        assert mock_sleep.call_count == 2  # sleep between retries
        # Verify exponential backoff: 2^0=1, 2^1=2
        assert mock_sleep.call_args_list[0][0][0] == 1
        assert mock_sleep.call_args_list[1][0][0] == 2

    @pytest.mark.asyncio
    async def test_webhook_exhausts_retries(self):
        """Webhook logs error after exhausting all retries."""
        attempts = []

        class AlwaysFailClient:
            is_closed = False

            async def post(self, *args, **kwargs):
                attempts.append(1)
                raise ConnectionError("unreachable")

        with (
            patch(
                "webgui.api._get_webhook_client",
                new_callable=AsyncMock,
                return_value=AlwaysFailClient(),
            ),
            patch("webgui.api.WEBHOOK_MAX_RETRIES", 3),
            patch("webgui.api.asyncio.sleep", new_callable=AsyncMock),
        ):
            await _fire_webhook("https://bad.example.com", None, {"x": 1})

        assert len(attempts) == 3  # tried all 3 times


# ---------------------------------------------------------------------------
# Agent-specific convenience endpoints (P4)
# ---------------------------------------------------------------------------


class TestAgentSpecificEndpoints:
    @patch("config.environment.config")
    @patch("webgui.api.asyncio")
    def test_security_endpoint_sets_agents(
        self, mock_asyncio, mock_config, authed_client
    ):
        mock_redis = Mock()
        mock_redis.setex.return_value = True
        mock_config.get_redis_client.return_value = mock_redis
        mock_asyncio.create_task = Mock()

        resp = authed_client.post(
            "/api/v1/tasks/security",
            json={"title": "T", "description": "D"},
        )
        assert resp.status_code == 201

    @patch("config.environment.config")
    @patch("webgui.api.asyncio")
    def test_performance_endpoint(self, mock_asyncio, mock_config, authed_client):
        mock_redis = Mock()
        mock_redis.setex.return_value = True
        mock_config.get_redis_client.return_value = mock_redis
        mock_asyncio.create_task = Mock()

        resp = authed_client.post(
            "/api/v1/tasks/performance",
            json={"title": "T", "description": "D"},
        )
        assert resp.status_code == 201

    @patch("config.environment.config")
    @patch("webgui.api.asyncio")
    def test_regression_endpoint(self, mock_asyncio, mock_config, authed_client):
        mock_redis = Mock()
        mock_redis.setex.return_value = True
        mock_config.get_redis_client.return_value = mock_redis
        mock_asyncio.create_task = Mock()

        resp = authed_client.post(
            "/api/v1/tasks/regression",
            json={"title": "T", "description": "D"},
        )
        assert resp.status_code == 201

    @patch("config.environment.config")
    @patch("webgui.api.asyncio")
    def test_full_endpoint(self, mock_asyncio, mock_config, authed_client):
        mock_redis = Mock()
        mock_redis.setex.return_value = True
        mock_config.get_redis_client.return_value = mock_redis
        mock_asyncio.create_task = Mock()

        resp = authed_client.post(
            "/api/v1/tasks/full",
            json={"title": "T", "description": "D"},
        )
        assert resp.status_code == 201


# ---------------------------------------------------------------------------
# A2A protocol endpoints (P8)
# ---------------------------------------------------------------------------


@patch("webgui.routes.tasks.YEOMAN_A2A_ENABLED", True)
class TestA2AEndpoints:
    """Tests for POST /api/v1/a2a/receive and GET /api/v1/a2a/capabilities."""

    def test_capabilities_unauthenticated(self, app):
        """GET /api/v1/a2a/capabilities should not require auth."""
        client = TestClient(app)
        resp = client.get("/api/v1/a2a/capabilities")
        assert resp.status_code == 200
        data = resp.json()
        assert "capabilities" in data
        assert isinstance(data["capabilities"], list)
        assert len(data["capabilities"]) > 0
        names = [c["name"] for c in data["capabilities"]]
        assert "qa" in names
        assert "security-audit" in names
        assert "performance-test" in names

    def test_capabilities_shape(self, app):
        """Each capability must have name, description, and version."""
        client = TestClient(app)
        resp = client.get("/api/v1/a2a/capabilities")
        for cap in resp.json()["capabilities"]:
            assert "name" in cap
            assert "description" in cap
            assert "version" in cap

    @patch("config.environment.config")
    @patch("webgui.api.asyncio")
    def test_delegate_message_spawns_task(
        self, mock_asyncio, mock_config, authed_client
    ):
        """a2a:delegate should create a QA task and return task_id."""
        mock_redis = Mock()
        mock_redis.setex.return_value = True
        mock_config.get_redis_client.return_value = mock_redis
        mock_asyncio.create_task = Mock()

        resp = authed_client.post(
            "/api/v1/a2a/receive",
            json={
                "id": "msg-001",
                "type": "a2a:delegate",
                "fromPeerId": "yeoman-agent",
                "toPeerId": "agnostic",
                "payload": {
                    "title": "Security scan via A2A",
                    "description": "Run OWASP checks on staging",
                    "priority": "high",
                    "agents": ["security-compliance"],
                    "standards": ["OWASP"],
                },
                "timestamp": 1708516800000,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["accepted"] is True
        assert "task_id" in data
        assert data["message_id"] == "msg-001"

    @patch("config.environment.config")
    @patch("webgui.api.asyncio")
    def test_delegate_minimal_payload(self, mock_asyncio, mock_config, authed_client):
        """Delegate with only title + description in payload."""
        mock_redis = Mock()
        mock_redis.setex.return_value = True
        mock_config.get_redis_client.return_value = mock_redis
        mock_asyncio.create_task = Mock()

        resp = authed_client.post(
            "/api/v1/a2a/receive",
            json={
                "id": "msg-002",
                "type": "a2a:delegate",
                "fromPeerId": "yeoman",
                "toPeerId": "agnostic",
                "payload": {"title": "Quick QA", "description": "Full pipeline"},
                "timestamp": 1708516800000,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["accepted"] is True

    def test_heartbeat_message(self, authed_client):
        """a2a:heartbeat should be acknowledged immediately."""
        resp = authed_client.post(
            "/api/v1/a2a/receive",
            json={
                "id": "hb-001",
                "type": "a2a:heartbeat",
                "fromPeerId": "yeoman",
                "toPeerId": "agnostic",
                "payload": {},
                "timestamp": 1708516800000,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["accepted"] is True
        assert data["message_id"] == "hb-001"
        assert data["timestamp"] == 1708516800000

    def test_unknown_message_type_returns_warning(self, authed_client):
        """Unknown message types should be acknowledged with a warning."""
        resp = authed_client.post(
            "/api/v1/a2a/receive",
            json={
                "id": "unk-001",
                "type": "a2a:unknown_future_type",
                "fromPeerId": "yeoman",
                "toPeerId": "agnostic",
                "payload": {},
                "timestamp": 1708516800000,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["accepted"] is True
        assert "warning" in data
        assert "a2a:unknown_future_type" in data["warning"]

    def test_receive_requires_auth(self, app):
        """POST /api/v1/a2a/receive must reject unauthenticated requests."""
        client = TestClient(app)
        resp = client.post(
            "/api/v1/a2a/receive",
            json={
                "id": "x",
                "type": "a2a:heartbeat",
                "fromPeerId": "y",
                "toPeerId": "z",
                "payload": {},
                "timestamp": 0,
            },
        )
        assert resp.status_code == 401

    def test_receive_invalid_body(self, authed_client):
        """Missing required fields should return 422."""
        resp = authed_client.post(
            "/api/v1/a2a/receive",
            json={"type": "a2a:heartbeat"},  # missing id, fromPeerId, etc.
        )
        assert resp.status_code == 422
