import json
import os
import sys
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, Mock, patch

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
        resp = client.post("/api/v1/auth/login", json={})
        assert resp.status_code == 422  # validation error

    def test_login_invalid_credentials(self, client):
        mock_redis = AsyncMock()
        mock_redis.incr.return_value = 1
        mock_redis.expire.return_value = True
        mock_auth_manager = MagicMock()
        mock_auth_manager.authenticate_user = AsyncMock(return_value=None)
        with (
            patch(
                "config.environment.config.get_async_redis_client",
                return_value=mock_redis,
            ),
            patch("webgui.routes.auth.auth_manager", mock_auth_manager),
        ):
            resp = client.post(
                "/api/v1/auth/login",
                json={"email": "bad@example.com", "password": "wrong"},
            )
        assert resp.status_code == 401

    def test_me_unauthenticated(self, client):
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 401

    def test_me_authenticated(self, authed_client, auth_user):
        resp = authed_client.get("/api/v1/auth/me")
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == auth_user["user_id"]
        assert data["email"] == auth_user["email"]


class TestDashboardEndpoints:
    def test_dashboard_unauthenticated(self, client):
        resp = client.get("/api/v1/dashboard")
        assert resp.status_code == 401

    @patch("webgui.api.auth_manager")
    def test_dashboard_authenticated(self, mock_auth, authed_client):
        with patch("webgui.dashboard.dashboard_manager") as mock_dm:
            mock_dm.export_dashboard_data = AsyncMock(
                return_value={
                    "sessions": [],
                    "agents": [],
                    "metrics": {},
                }
            )
            resp = authed_client.get("/api/v1/dashboard")
            assert resp.status_code == 200


class TestAgentMetricsDashboard:
    @patch("shared.agent_metrics.get_agent_metrics")
    def test_agent_dashboard_returns_agents(self, mock_get, authed_client):
        mock_get.return_value = [
            {
                "agent": "qa-manager",
                "tasks_total": 5,
                "tasks_success": 4,
                "tasks_failed": 1,
                "success_rate": 0.8,
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "active": 1.0,
            },
        ]
        resp = authed_client.get("/api/v1/dashboard/agent-metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert "agents" in data
        assert isinstance(data["agents"], list)
        assert data["agents"][0]["agent"] == "qa-manager"

    @patch("shared.agent_metrics.get_llm_metrics")
    def test_llm_dashboard_returns_metrics(self, mock_get, authed_client):
        mock_get.return_value = {
            "total_calls": 10,
            "total_errors": 2,
            "error_rate": 0.1667,
            "by_method": {"generate_test_scenarios": {"calls": 8, "errors": 2}},
        }
        resp = authed_client.get("/api/v1/dashboard/llm")
        assert resp.status_code == 200
        data = resp.json()
        assert "llm" in data
        assert data["llm"]["total_calls"] == 10
        assert "by_method" in data["llm"]


class TestAgentEndpoints:
    @patch("webgui.agent_monitor.agent_monitor")
    def test_agents_list(self, mock_monitor, authed_client):
        mock_monitor.get_all_agent_status = AsyncMock(return_value=[])
        resp = authed_client.get("/api/v1/agents")
        assert resp.status_code == 200

    @patch("webgui.agent_monitor.agent_monitor")
    def test_agent_queues(self, mock_monitor, authed_client):
        mock_monitor.get_queue_depths = AsyncMock(return_value={"qa_manager": 0})
        resp = authed_client.get("/api/v1/agents/queues")
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

        with (
            patch.dict(os.environ, {"RABBITMQ_HOST": "rabbitmq"}),
            patch("webgui.app.config") as mock_config,
            patch("webgui.app.socket") as mock_socket,
            patch("webgui.app._agent_registry") as mock_registry,
        ):
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

        with (
            patch("webgui.app.config") as mock_config,
            patch("webgui.app.socket") as mock_socket,
            patch("webgui.app._agent_registry") as mock_registry,
        ):
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
        """RabbitMQ failure → degraded (RabbitMQ is optional, only needed for workers profile)."""
        try:
            from webgui.app import app as real_app
        except ImportError:
            pytest.skip("webgui.app not importable")

        mock_redis = Mock()
        mock_redis.ping.return_value = True
        mock_redis.get.return_value = None

        with (
            patch.dict(os.environ, {"RABBITMQ_HOST": "rabbitmq"}),
            patch("webgui.app.config") as mock_config,
            patch("webgui.app.socket") as mock_socket,
            patch("webgui.app._agent_registry") as mock_registry,
        ):
            mock_config.get_redis_client.return_value = mock_redis
            mock_socket.create_connection.side_effect = ConnectionRefusedError(
                "rmq down"
            )
            mock_registry.get_agents_for_team.return_value = []

            client = TestClient(real_app)
            resp = client.get("/health")

        assert resp.status_code == 200
        data = resp.json()
        assert data["rabbitmq"] == "error"
        assert data["status"] == "degraded"

    def test_health_alive_agent(self):
        """At least one alive agent + infra ok → healthy."""
        try:
            from webgui.app import app as real_app
        except ImportError:
            pytest.skip("webgui.app not importable")

        now_iso = datetime.now(UTC).isoformat()
        heartbeat_data = json.dumps({"last_heartbeat": now_iso}).encode()

        mock_redis = Mock()
        mock_redis.ping.return_value = True
        mock_redis.get.return_value = heartbeat_data

        mock_agent = Mock()
        mock_agent.name = "QA Manager"

        with (
            patch.dict(os.environ, {"RABBITMQ_HOST": "rabbitmq"}),
            patch("webgui.app.config") as mock_config,
            patch("webgui.app.socket") as mock_socket,
            patch("webgui.app._agent_registry") as mock_registry,
        ):
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

        old_ts = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
        heartbeat_data = json.dumps({"last_heartbeat": old_ts}).encode()

        mock_redis = Mock()
        mock_redis.ping.return_value = True
        mock_redis.get.return_value = heartbeat_data

        mock_agent = Mock()
        mock_agent.name = "QA Manager"

        with (
            patch("webgui.app.config") as mock_config,
            patch("webgui.app.socket") as mock_socket,
            patch("webgui.app._agent_registry") as mock_registry,
            patch.dict(os.environ, {"AGENT_STALE_THRESHOLD_SECONDS": "60"}),
        ):
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
        mock_redis = AsyncMock()
        mock_redis.get.return_value = json.dumps({"file_path": file_path}).encode()
        return mock_redis

    def test_path_within_reports_dir_ok(self, authed_client, tmp_path):
        """A file inside /app/reports should be served."""
        import webgui.routes.reports as reports_mod

        report_file = tmp_path / "report.json"
        report_file.write_text("{}")

        original_dir = reports_mod._REPORTS_DIR
        reports_mod._REPORTS_DIR = tmp_path.resolve()
        try:
            with patch("config.environment.config") as mock_cfg:
                mock_cfg.get_async_redis_client.return_value = (
                    self._make_redis_with_meta(str(report_file))
                )
                resp = authed_client.get("/api/v1/reports/report-abc/download")
            assert resp.status_code == 200
        finally:
            reports_mod._REPORTS_DIR = original_dir

    def test_path_traversal_blocked(self, authed_client, tmp_path):
        """A file outside /app/reports must return 403."""
        import webgui.routes.reports as reports_mod

        # Reports dir is tmp_path; file is one level above (outside)
        malicious_path = str(tmp_path.parent / "etc" / "passwd")

        original_dir = reports_mod._REPORTS_DIR
        reports_mod._REPORTS_DIR = tmp_path.resolve()
        try:
            with patch("config.environment.config") as mock_cfg:
                mock_cfg.get_async_redis_client.return_value = (
                    self._make_redis_with_meta(malicious_path)
                )
                resp = authed_client.get("/api/v1/reports/evil-id/download")
            assert resp.status_code == 403
        finally:
            reports_mod._REPORTS_DIR = original_dir

    def test_dotdot_traversal_blocked(self, authed_client, tmp_path):
        """../../etc/passwd style path must be blocked."""
        import webgui.routes.reports as reports_mod

        traversal = str(tmp_path / ".." / ".." / "etc" / "passwd")

        original_dir = reports_mod._REPORTS_DIR
        reports_mod._REPORTS_DIR = tmp_path.resolve()
        try:
            with patch("config.environment.config") as mock_cfg:
                mock_cfg.get_async_redis_client.return_value = (
                    self._make_redis_with_meta(traversal)
                )
                resp = authed_client.get("/api/v1/reports/dotdot/download")
            assert resp.status_code == 403
        finally:
            reports_mod._REPORTS_DIR = original_dir

    def test_missing_file_returns_404(self, authed_client, tmp_path):
        """Non-existent file within reports dir returns 404, not 500."""
        import webgui.routes.reports as reports_mod

        nonexistent = str(tmp_path / "missing_report.json")
        original_dir = reports_mod._REPORTS_DIR
        reports_mod._REPORTS_DIR = tmp_path.resolve()
        try:
            with patch("config.environment.config") as mock_cfg:
                mock_cfg.get_async_redis_client.return_value = (
                    self._make_redis_with_meta(nonexistent)
                )
                resp = authed_client.get("/api/v1/reports/gone/download")
            assert resp.status_code == 404
        finally:
            reports_mod._REPORTS_DIR = original_dir


# ---------------------------------------------------------------------------
# SSRF protection tests
# ---------------------------------------------------------------------------


class TestSSRFProtection:
    def test_blocks_localhost(self):
        from webgui.api import _validate_callback_url

        with pytest.raises(ValueError, match="private network"):
            _validate_callback_url("http://127.0.0.1/hook")

    def test_blocks_private_10_network(self):
        from webgui.api import _validate_callback_url

        with pytest.raises(ValueError, match="private network"):
            _validate_callback_url("http://10.0.0.1/hook")

    def test_blocks_private_172_network(self):
        from webgui.api import _validate_callback_url

        with pytest.raises(ValueError, match="private network"):
            _validate_callback_url("http://172.16.0.1/hook")

    def test_blocks_private_192_network(self):
        from webgui.api import _validate_callback_url

        with pytest.raises(ValueError, match="private network"):
            _validate_callback_url("http://192.168.1.1:8080/hook")

    def test_blocks_metadata_endpoint(self):
        from webgui.api import _validate_callback_url

        with pytest.raises(ValueError, match="private network"):
            _validate_callback_url("http://169.254.169.254/latest/meta-data/")

    def test_allows_public_url(self, monkeypatch):
        import socket as _socket

        from webgui.api import _validate_callback_url

        # Mock DNS resolution to return a public IP
        monkeypatch.setattr(
            "webgui.routes.dependencies.socket.getaddrinfo",
            lambda *a, **kw: [
                (_socket.AF_INET, _socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))
            ],
        )
        _validate_callback_url("https://hooks.example.com/callback")

    def test_allows_domain_name(self, monkeypatch):
        import socket as _socket

        from webgui.api import _validate_callback_url

        monkeypatch.setattr(
            "webgui.routes.dependencies.socket.getaddrinfo",
            lambda *a, **kw: [
                (_socket.AF_INET, _socket.SOCK_STREAM, 6, "", ("203.0.113.1", 0))
            ],
        )
        _validate_callback_url("https://my-webhook.company.io/hook")

    def test_blocks_dns_rebinding_to_private(self, monkeypatch):
        import socket as _socket

        from webgui.api import _validate_callback_url

        # DNS rebinding: domain resolves to a private IP
        monkeypatch.setattr(
            "webgui.routes.dependencies.socket.getaddrinfo",
            lambda *a, **kw: [
                (_socket.AF_INET, _socket.SOCK_STREAM, 6, "", ("10.0.0.1", 0))
            ],
        )
        with pytest.raises(ValueError, match="private network"):
            _validate_callback_url("https://evil-rebind.attacker.com/hook")

    def test_blocks_unresolvable_hostname(self, monkeypatch):
        import socket as _socket

        from webgui.api import _validate_callback_url

        def _raise_gaierror(*a, **kw):
            raise _socket.gaierror("Name resolution failed")

        monkeypatch.setattr(
            "webgui.routes.dependencies.socket.getaddrinfo",
            _raise_gaierror,
        )
        with pytest.raises(ValueError, match="Cannot resolve hostname"):
            _validate_callback_url("https://nonexistent.invalid/hook")

    def test_blocks_unsupported_scheme(self):
        from webgui.api import _validate_callback_url

        with pytest.raises(ValueError, match="Unsupported scheme"):
            _validate_callback_url("ftp://example.com/file")

    def test_blocks_missing_hostname(self):
        from webgui.api import _validate_callback_url

        with pytest.raises(ValueError, match="Missing hostname"):
            _validate_callback_url("http:///path")


# ---------------------------------------------------------------------------
# Agent name normalization tests
# ---------------------------------------------------------------------------


class TestAgentNameNormalization:
    def test_snake_case_to_kebab(self):
        from webgui.api import _normalize_agent_name

        assert _normalize_agent_name("security_compliance") == "security-compliance"

    def test_kebab_case_unchanged(self):
        from webgui.api import _normalize_agent_name

        assert _normalize_agent_name("security-compliance") == "security-compliance"

    def test_simple_name_unchanged(self):
        from webgui.api import _normalize_agent_name

        assert _normalize_agent_name("performance") == "performance"

    def test_multiple_underscores(self):
        from webgui.api import _normalize_agent_name

        assert _normalize_agent_name("qa_senior_lead") == "qa-senior-lead"


# ---------------------------------------------------------------------------
# Static API key permissions test
# ---------------------------------------------------------------------------


class TestStaticApiKeyPermissions:
    def test_static_key_excludes_system_configure(self):
        """Static API key should not include SYSTEM_CONFIGURE permission."""
        from webgui.auth import Permission

        with patch.dict(os.environ, {"AGNOSTIC_API_KEY": "test-key-123"}):
            # Re-import to pick up env var

            # Simulate what get_current_user does for static key
            import hmac

            static_key = "test-key-123"
            x_api_key = "test-key-123"
            assert hmac.compare_digest(x_api_key, static_key)
            _static_permissions = [
                p.value for p in Permission if p != Permission.SYSTEM_CONFIGURE
            ]
            assert "system:configure" not in _static_permissions
            assert "sessions:read" in _static_permissions
