import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

try:
    from fastapi.testclient import TestClient
except ImportError:
    pytest.skip("fastapi not available", allow_module_level=True)

try:
    from webgui.api import api_router, get_current_user
except ImportError:
    pytest.skip("webgui.api module not available", allow_module_level=True)

from fastapi import FastAPI


@pytest.fixture()
def app():
    """Create a test FastAPI app with the API router mounted."""
    test_app = FastAPI()
    test_app.include_router(api_router)

    @test_app.get("/health")
    async def health():
        return {"status": "healthy"}

    return test_app


@pytest.fixture()
def client(app):
    return TestClient(app)


@pytest.fixture()
def auth_user():
    """Return a mock authenticated user payload."""
    return {
        "user_id": "test-user-1",
        "email": "test@example.com",
        "role": "qa_engineer",
        "permissions": [
            "sessions:read",
            "sessions:write",
            "agents:control",
            "reports:generate",
        ],
    }


@pytest.fixture()
def authed_client(app, auth_user):
    """Create a TestClient with auth dependency overridden."""

    async def override_get_current_user():
        return auth_user

    app.dependency_overrides[get_current_user] = override_get_current_user
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


class TestHealthEndpoint:
    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"


class TestAuthEndpoints:
    def test_login_missing_credentials(self, client):
        resp = client.post("/api/auth/login", json={})
        assert resp.status_code == 422  # validation error

    @patch("webgui.api.auth_manager")
    def test_login_invalid_credentials(self, mock_auth, client):
        mock_auth.authenticate_user = AsyncMock(return_value=None)
        resp = client.post(
            "/api/auth/login",
            json={"email": "bad@example.com", "password": "wrong"},
        )
        assert resp.status_code == 401

    def test_me_unauthenticated(self, client):
        resp = client.get("/api/auth/me")
        assert resp.status_code == 401

    def test_me_authenticated(self, authed_client, auth_user):
        resp = authed_client.get("/api/auth/me")
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == auth_user["user_id"]
        assert data["email"] == auth_user["email"]


class TestDashboardEndpoints:
    def test_dashboard_unauthenticated(self, client):
        resp = client.get("/api/dashboard")
        assert resp.status_code == 401

    @patch("webgui.api.auth_manager")
    def test_dashboard_authenticated(self, mock_auth, authed_client):
        with patch("webgui.dashboard.dashboard_manager") as mock_dm:
            mock_dm.export_dashboard_data = AsyncMock(return_value={
                "sessions": [],
                "agents": [],
                "metrics": {},
            })
            resp = authed_client.get("/api/dashboard")
            assert resp.status_code == 200


class TestAgentEndpoints:
    @patch("webgui.agent_monitor.agent_monitor")
    def test_agents_list(self, mock_monitor, authed_client):
        mock_monitor.get_all_agent_status = AsyncMock(return_value=[])
        resp = authed_client.get("/api/agents")
        assert resp.status_code == 200

    @patch("webgui.agent_monitor.agent_monitor")
    def test_agent_queues(self, mock_monitor, authed_client):
        mock_monitor.get_queue_depths = AsyncMock(return_value={"qa_manager": 0})
        resp = authed_client.get("/api/agents/queues")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# P6 — Enhanced health endpoint
# ---------------------------------------------------------------------------

class TestHealthCheckEndpoint:
    """Tests for the enhanced /health endpoint in webgui/app.py."""

    def _make_health_app(self):
        """Import the real app's health endpoint for testing."""
        try:
            from webgui.app import app as real_app
            return real_app
        except ImportError:
            return None

    def test_health_redis_ok_rabbitmq_ok_agents_offline(self):
        """Infrastructure ok but all agents offline → degraded."""
        try:
            from webgui.app import app as real_app
        except ImportError:
            pytest.skip("webgui.app not importable")

        mock_redis = Mock()
        mock_redis.ping.return_value = True
        mock_redis.get.return_value = None  # no heartbeats

        with patch("webgui.app.config") as mock_config, \
             patch("webgui.app.socket") as mock_socket, \
             patch("webgui.app._agent_registry") as mock_registry:

            mock_config.get_redis_client.return_value = mock_redis

            # RabbitMQ connect succeeds
            mock_sock_instance = Mock()
            mock_socket.create_connection.return_value = mock_sock_instance

            # Registry returns empty list (no agents)
            mock_registry.get_agents_for_team.return_value = []

            client = TestClient(real_app)
            resp = client.get("/health")

        assert resp.status_code == 200
        data = resp.json()
        assert data["redis"] == "ok"
        assert data["rabbitmq"] == "ok"
        assert data["status"] in ("healthy", "degraded")
        assert "timestamp" in data

    def test_health_redis_error(self):
        """Redis failure → unhealthy."""
        try:
            from webgui.app import app as real_app
        except ImportError:
            pytest.skip("webgui.app not importable")

        mock_redis = Mock()
        mock_redis.ping.side_effect = ConnectionError("redis down")

        with patch("webgui.app.config") as mock_config, \
             patch("webgui.app.socket") as mock_socket, \
             patch("webgui.app._agent_registry") as mock_registry:

            mock_config.get_redis_client.return_value = mock_redis
            mock_socket.create_connection.return_value = Mock()
            mock_registry.get_agents_for_team.return_value = []

            client = TestClient(real_app)
            resp = client.get("/health")

        assert resp.status_code == 200
        data = resp.json()
        assert data["redis"] == "error"
        assert data["status"] == "unhealthy"

    def test_health_rabbitmq_error(self):
        """RabbitMQ failure → unhealthy."""
        try:
            from webgui.app import app as real_app
        except ImportError:
            pytest.skip("webgui.app not importable")

        mock_redis = Mock()
        mock_redis.ping.return_value = True
        mock_redis.get.return_value = None

        with patch("webgui.app.config") as mock_config, \
             patch("webgui.app.socket") as mock_socket, \
             patch("webgui.app._agent_registry") as mock_registry:

            mock_config.get_redis_client.return_value = mock_redis
            mock_socket.create_connection.side_effect = ConnectionRefusedError("rmq down")
            mock_registry.get_agents_for_team.return_value = []

            client = TestClient(real_app)
            resp = client.get("/health")

        assert resp.status_code == 200
        data = resp.json()
        assert data["rabbitmq"] == "error"
        assert data["status"] == "unhealthy"

    def test_health_alive_agent(self):
        """At least one alive agent + infra ok → healthy."""
        try:
            from webgui.app import app as real_app
        except ImportError:
            pytest.skip("webgui.app not importable")

        now_iso = datetime.now(timezone.utc).isoformat()
        heartbeat_data = json.dumps({"last_heartbeat": now_iso}).encode()

        mock_redis = Mock()
        mock_redis.ping.return_value = True
        mock_redis.get.return_value = heartbeat_data

        mock_agent = Mock()
        mock_agent.name = "QA Manager"

        with patch("webgui.app.config") as mock_config, \
             patch("webgui.app.socket") as mock_socket, \
             patch("webgui.app._agent_registry") as mock_registry:

            mock_config.get_redis_client.return_value = mock_redis
            mock_socket.create_connection.return_value = Mock()
            mock_registry.get_agents_for_team.return_value = [mock_agent]

            client = TestClient(real_app)
            resp = client.get("/health")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"

    def test_health_stale_agent(self):
        """Agent heartbeat older than threshold → stale."""
        try:
            from webgui.app import app as real_app
        except ImportError:
            pytest.skip("webgui.app not importable")

        old_ts = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        heartbeat_data = json.dumps({"last_heartbeat": old_ts}).encode()

        mock_redis = Mock()
        mock_redis.ping.return_value = True
        mock_redis.get.return_value = heartbeat_data

        mock_agent = Mock()
        mock_agent.name = "QA Manager"

        with patch("webgui.app.config") as mock_config, \
             patch("webgui.app.socket") as mock_socket, \
             patch("webgui.app._agent_registry") as mock_registry, \
             patch.dict(os.environ, {"AGENT_STALE_THRESHOLD_SECONDS": "60"}):

            mock_config.get_redis_client.return_value = mock_redis
            mock_socket.create_connection.return_value = Mock()
            mock_registry.get_agents_for_team.return_value = [mock_agent]

            client = TestClient(real_app)
            resp = client.get("/health")

        assert resp.status_code == 200
        data = resp.json()
        # stale agent, infra ok → degraded
        agent_statuses = list(data["agents"].values())
        assert "stale" in agent_statuses


# ---------------------------------------------------------------------------
# Security: path traversal in report download
# ---------------------------------------------------------------------------

class TestReportDownloadSecurity:
    """Verify path traversal is blocked in GET /api/reports/{id}/download."""

    def _make_redis_with_meta(self, file_path: str):
        mock_redis = Mock()
        mock_redis.get.return_value = json.dumps({"file_path": file_path}).encode()
        return mock_redis

    def test_path_within_reports_dir_ok(self, authed_client, tmp_path):
        """A file inside /app/reports should be served."""
        import webgui.api as api_mod

        report_file = tmp_path / "report.json"
        report_file.write_text("{}")

        original_dir = api_mod._REPORTS_DIR
        api_mod._REPORTS_DIR = tmp_path.resolve()
        try:
            with patch("config.environment.config") as mock_cfg:
                mock_cfg.get_redis_client.return_value = self._make_redis_with_meta(
                    str(report_file)
                )
                resp = authed_client.get("/api/reports/report-abc/download")
            assert resp.status_code == 200
        finally:
            api_mod._REPORTS_DIR = original_dir

    def test_path_traversal_blocked(self, authed_client, tmp_path):
        """A file outside /app/reports must return 403."""
        import webgui.api as api_mod

        # Reports dir is tmp_path; file is one level above (outside)
        malicious_path = str(tmp_path.parent / "etc" / "passwd")

        original_dir = api_mod._REPORTS_DIR
        api_mod._REPORTS_DIR = tmp_path.resolve()
        try:
            with patch("config.environment.config") as mock_cfg:
                mock_cfg.get_redis_client.return_value = self._make_redis_with_meta(
                    malicious_path
                )
                resp = authed_client.get("/api/reports/evil-id/download")
            assert resp.status_code == 403
        finally:
            api_mod._REPORTS_DIR = original_dir

    def test_dotdot_traversal_blocked(self, authed_client, tmp_path):
        """../../etc/passwd style path must be blocked."""
        import webgui.api as api_mod

        traversal = str(tmp_path / ".." / ".." / "etc" / "passwd")

        original_dir = api_mod._REPORTS_DIR
        api_mod._REPORTS_DIR = tmp_path.resolve()
        try:
            with patch("config.environment.config") as mock_cfg:
                mock_cfg.get_redis_client.return_value = self._make_redis_with_meta(
                    traversal
                )
                resp = authed_client.get("/api/reports/dotdot/download")
            assert resp.status_code == 403
        finally:
            api_mod._REPORTS_DIR = original_dir

    def test_missing_file_returns_404(self, authed_client, tmp_path):
        """Non-existent file within reports dir returns 404, not 500."""
        import webgui.api as api_mod

        nonexistent = str(tmp_path / "missing_report.json")
        original_dir = api_mod._REPORTS_DIR
        api_mod._REPORTS_DIR = tmp_path.resolve()
        try:
            with patch("config.environment.config") as mock_cfg:
                mock_cfg.get_redis_client.return_value = self._make_redis_with_meta(
                    nonexistent
                )
                resp = authed_client.get("/api/reports/gone/download")
            assert resp.status_code == 404
        finally:
            api_mod._REPORTS_DIR = original_dir


# ---------------------------------------------------------------------------
# Security: security headers middleware
# ---------------------------------------------------------------------------

class TestSecurityHeaders:
    """Verify OWASP security headers are present on API responses."""

    def test_security_headers_on_health(self):
        try:
            from webgui.app import app as real_app
        except ImportError:
            pytest.skip("webgui.app not importable")

        with patch("webgui.app.config") as mock_cfg, \
             patch("webgui.app.socket") as mock_sock, \
             patch("webgui.app._agent_registry") as mock_reg:
            mock_cfg.get_redis_client.return_value = Mock(ping=Mock(return_value=True))
            mock_sock.create_connection.return_value = Mock()
            mock_reg.get_agents_for_team.return_value = []

            client = TestClient(real_app)
            resp = client.get("/health")

        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-Frame-Options") == "DENY"
        assert resp.headers.get("X-XSS-Protection") == "1; mode=block"
        assert resp.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
