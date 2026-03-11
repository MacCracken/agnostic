"""Unit tests for AGNOS daimon RPC client and handler."""

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


# ---------------------------------------------------------------------------
# RPC method definitions
# ---------------------------------------------------------------------------


class TestAgentRpcMethods:
    """Tests for the AGENT_RPC_METHODS configuration."""

    def test_all_six_agents_have_methods(self):
        from shared.agnos_rpc_client import AGENT_RPC_METHODS

        expected_agents = {
            "qa-manager",
            "senior-qa",
            "junior-qa",
            "qa-analyst",
            "security-compliance",
            "performance",
        }
        assert set(AGENT_RPC_METHODS.keys()) == expected_agents

    def test_all_methods_namespaced(self):
        from shared.agnos_rpc_client import AGENT_RPC_METHODS

        for agent_key, methods in AGENT_RPC_METHODS.items():
            for method in methods:
                assert method.startswith("agnostic."), (
                    f"Method {method} for {agent_key} must be namespaced with 'agnostic.'"
                )

    def test_each_agent_has_at_least_one_method(self):
        from shared.agnos_rpc_client import AGENT_RPC_METHODS

        for agent_key, methods in AGENT_RPC_METHODS.items():
            assert len(methods) > 0, (
                f"Agent {agent_key} should have at least one method"
            )

    def test_capability_methods_covered(self):
        """All CAPABILITY_DEFINITIONS should have corresponding RPC methods."""
        from config.agnos_agent_registration import CAPABILITY_DEFINITIONS
        from shared.agnos_rpc_client import AGENT_RPC_METHODS

        all_methods = set()
        for methods in AGENT_RPC_METHODS.values():
            all_methods.update(methods)

        for cap_name in CAPABILITY_DEFINITIONS:
            assert f"agnostic.{cap_name}" in all_methods, (
                f"Capability {cap_name} should have an RPC method"
            )


# ---------------------------------------------------------------------------
# RPC client initialization
# ---------------------------------------------------------------------------


class TestAgnosRpcClientInit:
    def test_default_disabled(self):
        with patch.dict(os.environ, {}, clear=True):
            from shared.agnos_rpc_client import AgnosRpcClient

            client = AgnosRpcClient()
            assert client.enabled is False

    def test_enabled_via_env(self):
        with patch.dict(os.environ, {"AGNOS_RPC_ENABLED": "true"}, clear=False):
            from shared.agnos_rpc_client import AgnosRpcClient

            client = AgnosRpcClient()
            assert client.enabled is True

    def test_uses_registry_url(self):
        with patch.dict(
            os.environ,
            {"AGNOS_AGENT_REGISTRY_URL": "http://custom:9090"},
            clear=False,
        ):
            from shared.agnos_rpc_client import AgnosRpcClient

            client = AgnosRpcClient()
            assert client.base_url == "http://custom:9090"


# ---------------------------------------------------------------------------
# RPC client — register methods
# ---------------------------------------------------------------------------


class TestAgnosRpcClientRegister:
    @pytest.fixture
    def client(self):
        with patch.dict(
            os.environ,
            {
                "AGNOS_RPC_ENABLED": "true",
                "AGNOS_AGENT_REGISTRY_URL": "http://test:8090",
                "AGNOS_AGENT_API_KEY": "test-key",
            },
            clear=False,
        ):
            from shared.agnos_rpc_client import AgnosRpcClient

            c = AgnosRpcClient()
            yield c

    @pytest.mark.asyncio
    async def test_register_methods_when_disabled(self):
        with patch.dict(os.environ, {"AGNOS_RPC_ENABLED": "false"}, clear=False):
            from shared.agnos_rpc_client import AgnosRpcClient

            client = AgnosRpcClient()
            result = await client.register_methods("uuid-1", ["agnostic.test_planning"])
            assert result["status"] == "disabled"

    @pytest.mark.asyncio
    async def test_register_methods_success(self, client):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"status": "ok"}

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        mock_http.is_closed = False
        client._client = mock_http

        result = await client.register_methods(
            "uuid-1234", ["agnostic.test_planning", "agnostic.fuzzy_verification"]
        )

        assert result["status"] == "registered"
        assert result["count"] == 2
        assert client._registered_methods["uuid-1234"] == [
            "agnostic.test_planning",
            "agnostic.fuzzy_verification",
        ]

    @pytest.mark.asyncio
    async def test_register_methods_http_error(self, client):
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(side_effect=Exception("connection refused"))
        mock_http.is_closed = False
        client._client = mock_http

        result = await client.register_methods("uuid-1234", ["agnostic.test_planning"])

        assert result["status"] == "error"
        assert "connection refused" in result["message"]

    @pytest.mark.asyncio
    async def test_register_all_agent_methods(self, client):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"status": "ok"}

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        mock_http.is_closed = False
        client._client = mock_http

        registered_agents = {
            "qa-manager": "uuid-1",
            "senior-qa": "uuid-2",
            "junior-qa": None,  # not registered — should be skipped
        }

        results = await client.register_all_agent_methods(registered_agents)

        assert "qa-manager" in results
        assert "senior-qa" in results
        assert "junior-qa" not in results  # skipped (no daimon ID)

    @pytest.mark.asyncio
    async def test_deregister_all_methods(self, client):
        client._registered_methods = {"uuid-1": ["agnostic.test_planning"]}
        await client.deregister_all_methods()
        assert client._registered_methods == {}


# ---------------------------------------------------------------------------
# RPC client — call remote methods
# ---------------------------------------------------------------------------


class TestAgnosRpcClientCall:
    @pytest.fixture
    def client(self):
        with patch.dict(
            os.environ,
            {
                "AGNOS_RPC_ENABLED": "true",
                "AGNOS_AGENT_REGISTRY_URL": "http://test:8090",
            },
            clear=False,
        ):
            from shared.agnos_rpc_client import AgnosRpcClient

            c = AgnosRpcClient()
            yield c

    @pytest.mark.asyncio
    async def test_call_when_disabled(self):
        with patch.dict(os.environ, {"AGNOS_RPC_ENABLED": "false"}, clear=False):
            from shared.agnos_rpc_client import AgnosRpcClient

            client = AgnosRpcClient()
            result = await client.call("secureyeoman.scan", {"target": "example.com"})
            assert result["status"] == "disabled"

    @pytest.mark.asyncio
    async def test_call_success(self, client):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "status": "routed",
            "handler_agent_id": "sy-scanner",
        }

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        mock_http.is_closed = False
        client._client = mock_http

        result = await client.call(
            "secureyeoman.scan",
            params={"target": "example.com"},
            sender_id="agnostic-security-compliance",
        )

        assert result["status"] == "routed"
        call_args = mock_http.post.call_args
        payload = call_args[1]["json"]
        assert payload["method"] == "secureyeoman.scan"
        assert payload["sender_id"] == "agnostic-security-compliance"

    @pytest.mark.asyncio
    async def test_call_http_error(self, client):
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(side_effect=Exception("timeout"))
        mock_http.is_closed = False
        client._client = mock_http

        result = await client.call("secureyeoman.scan")
        assert result["status"] == "error"


# ---------------------------------------------------------------------------
# RPC client — list methods
# ---------------------------------------------------------------------------


class TestAgnosRpcClientListMethods:
    @pytest.fixture
    def client(self):
        with patch.dict(
            os.environ,
            {
                "AGNOS_RPC_ENABLED": "true",
                "AGNOS_AGENT_REGISTRY_URL": "http://test:8090",
            },
            clear=False,
        ):
            from shared.agnos_rpc_client import AgnosRpcClient

            c = AgnosRpcClient()
            yield c

    @pytest.mark.asyncio
    async def test_list_all_methods(self, client):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "methods": ["agnostic.test_planning", "secureyeoman.scan"]
        }

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)
        mock_http.is_closed = False
        client._client = mock_http

        methods = await client.list_methods()
        assert len(methods) == 2
        assert "agnostic.test_planning" in methods

    @pytest.mark.asyncio
    async def test_list_methods_for_agent(self, client):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"methods": ["agnostic.test_planning"]}

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)
        mock_http.is_closed = False
        client._client = mock_http

        methods = await client.list_methods(agent_id="uuid-1234")
        assert methods == ["agnostic.test_planning"]

        # Verify URL includes agent_id
        call_args = mock_http.get.call_args
        assert "uuid-1234" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_list_methods_returns_empty_on_error(self, client):
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(side_effect=Exception("down"))
        mock_http.is_closed = False
        client._client = mock_http

        methods = await client.list_methods()
        assert methods == []


# ---------------------------------------------------------------------------
# RPC handler route
# ---------------------------------------------------------------------------


class TestRpcHandlerRoute:
    @pytest.fixture
    def rpc_client(self):
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except ImportError:
            pytest.skip("fastapi not available")

        from webgui.routes.dependencies import get_current_user
        from webgui.routes.rpc import router

        app = FastAPI()
        app.include_router(router, prefix="/api")

        async def override_auth():
            return {"user_id": "test-user", "role": "admin", "permissions": []}

        app.dependency_overrides[get_current_user] = override_auth

        return TestClient(app)

    def test_handle_known_method(self, rpc_client):
        with patch(
            "config.agnos_agent_registration.agent_registry_client"
        ) as mock_registry:
            mock_registry.handle_capability_request = AsyncMock(
                return_value={
                    "status": "accepted",
                    "task_id": "agnostic-security_audit-20260309",
                    "capability": "security_audit",
                    "assigned_agents": ["agnostic-security-compliance"],
                    "estimated_duration_seconds": 300,
                    "params": {"target": "example.com"},
                }
            )

            resp = rpc_client.post(
                "/api/v1/rpc/handle",
                json={
                    "method": "agnostic.security_audit",
                    "params": {"target": "example.com"},
                    "sender_id": "sy-orchestrator",
                },
            )

            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "accepted"
            assert data["method"] == "agnostic.security_audit"
            assert data["result"]["task_id"] == "agnostic-security_audit-20260309"

    def test_handle_unknown_agnostic_method(self, rpc_client):
        resp = rpc_client.post(
            "/api/v1/rpc/handle",
            json={"method": "agnostic.nonexistent", "params": {}},
        )
        assert resp.status_code == 404

    def test_handle_non_agnostic_method(self, rpc_client):
        resp = rpc_client.post(
            "/api/v1/rpc/handle",
            json={"method": "other.method", "params": {}},
        )
        assert resp.status_code == 400

    def test_list_local_methods(self, rpc_client):
        resp = rpc_client.get("/api/v1/rpc/methods")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 8
        assert "agnostic.security_audit" in data["methods"]
        assert "agnostic.fuzzy_verification" in data["methods"]

    def test_handle_capability_error(self, rpc_client):
        with patch(
            "config.agnos_agent_registration.agent_registry_client"
        ) as mock_registry:
            mock_registry.handle_capability_request = AsyncMock(
                return_value={
                    "status": "error",
                    "message": "Unknown capability: bad",
                }
            )

            resp = rpc_client.post(
                "/api/v1/rpc/handle",
                json={"method": "agnostic.security_audit", "params": {}},
            )

            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "error"
            assert data["error"] is not None


# ---------------------------------------------------------------------------
# Integration with AgentRegistryClient
# ---------------------------------------------------------------------------


class TestAgentRegistryRpcIntegration:
    """Test that register_all_agents wires up RPC registration."""

    @pytest.fixture
    def registry_client(self):
        with patch.dict(
            os.environ,
            {
                "AGNOS_AGENT_REGISTRATION_ENABLED": "true",
                "AGNOS_AGENT_REGISTRY_URL": "http://test:8090",
            },
            clear=False,
        ):
            from config.agnos_agent_registration import AgentRegistryClient

            client = AgentRegistryClient()
            yield client

    @pytest.mark.asyncio
    async def test_register_all_includes_rpc(self, registry_client):
        """register_all_agents should call RPC method registration."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"id": "uuid-test"}
        mock_session = MagicMock()
        mock_session.post.return_value = mock_response
        mock_session.headers = MagicMock()
        registry_client._session = mock_session

        with patch("shared.agnos_rpc_client.agnos_rpc") as mock_rpc:
            mock_rpc.register_all_agent_methods = AsyncMock(
                return_value={"qa-manager": {"status": "registered", "count": 2}}
            )

            results = await registry_client.register_all_agents()

            assert "rpc_methods" in results
            mock_rpc.register_all_agent_methods.assert_called_once()

    @pytest.mark.asyncio
    async def test_deregister_all_clears_rpc(self, registry_client):
        """deregister_all_agents should clear RPC registrations."""
        registry_client._registered_agents["qa-manager"] = "uuid-1"

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_session = MagicMock()
        mock_session.delete.return_value = mock_response
        mock_session.headers = MagicMock()
        registry_client._session = mock_session

        with patch("shared.agnos_rpc_client.agnos_rpc") as mock_rpc:
            mock_rpc.deregister_all_methods = AsyncMock()

            await registry_client.deregister_all_agents()

            mock_rpc.deregister_all_methods.assert_called_once()

    @pytest.mark.asyncio
    async def test_registration_status_includes_rpc(self, registry_client):
        """get_registration_status should include rpc_methods_registered."""
        status = registry_client.get_registration_status()
        assert "rpc_methods_registered" in status
