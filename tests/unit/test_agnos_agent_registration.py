"""Unit tests for AGNOS OS Agent HUD Registration."""

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


class TestAgnosticAgentsConfig:
    """Tests for the AGNOSTIC_AGENTS configuration dict."""

    def test_all_six_agents_defined(self):
        from config.agnos_agent_registration import AGNOSTIC_AGENTS

        expected = {
            "qa-manager",
            "senior-qa",
            "junior-qa",
            "qa-analyst",
            "security-compliance",
            "performance",
        }
        assert set(AGNOSTIC_AGENTS.keys()) == expected

    def test_agent_config_has_required_fields(self):
        from config.agnos_agent_registration import AGNOSTIC_AGENTS

        required_fields = {
            "agent_id",
            "agent_name",
            "agent_type",
            "description",
            "capabilities",
            "resource_limits",
        }
        for key, agent in AGNOSTIC_AGENTS.items():
            for field in required_fields:
                assert field in agent, f"Agent {key} missing field {field}"

    def test_agent_ids_are_unique(self):
        from config.agnos_agent_registration import AGNOSTIC_AGENTS

        ids = [a["agent_id"] for a in AGNOSTIC_AGENTS.values()]
        assert len(ids) == len(set(ids))

    def test_agent_ids_prefixed_with_agnostic(self):
        from config.agnos_agent_registration import AGNOSTIC_AGENTS

        for key, agent in AGNOSTIC_AGENTS.items():
            assert agent["agent_id"].startswith("agnostic-"), (
                f"Agent {key} id should start with 'agnostic-'"
            )

    def test_capabilities_are_lists(self):
        from config.agnos_agent_registration import AGNOSTIC_AGENTS

        for key, agent in AGNOSTIC_AGENTS.items():
            assert isinstance(agent["capabilities"], list), (
                f"Agent {key} capabilities should be a list"
            )
            assert len(agent["capabilities"]) > 0, (
                f"Agent {key} should have at least one capability"
            )

    def test_resource_limits_have_cpu_and_memory(self):
        from config.agnos_agent_registration import AGNOSTIC_AGENTS

        for key, agent in AGNOSTIC_AGENTS.items():
            limits = agent["resource_limits"]
            assert "cpu" in limits, f"Agent {key} missing cpu limit"
            assert "memory" in limits, f"Agent {key} missing memory limit"


class TestAgentRegistryClientInit:
    """Tests for AgentRegistryClient initialization."""

    def test_default_disabled(self):
        with patch.dict(os.environ, {}, clear=True):
            from config.agnos_agent_registration import AgentRegistryClient

            client = AgentRegistryClient()
            assert client.enabled is False

    def test_enabled_via_env(self):
        with patch.dict(
            os.environ, {"AGNOS_AGENT_REGISTRATION_ENABLED": "true"}, clear=False
        ):
            from config.agnos_agent_registration import AgentRegistryClient

            client = AgentRegistryClient()
            assert client.enabled is True

    def test_base_url_from_env(self):
        with patch.dict(
            os.environ,
            {"AGNOS_AGENT_REGISTRY_URL": "http://custom:9090"},
            clear=False,
        ):
            from config.agnos_agent_registration import AgentRegistryClient

            client = AgentRegistryClient()
            assert client.base_url == "http://custom:9090"

    def test_default_base_url(self):
        with patch.dict(os.environ, {}, clear=True):
            from config.agnos_agent_registration import AgentRegistryClient

            client = AgentRegistryClient()
            assert client.base_url == "http://localhost:8090"

    def test_session_lazy_created(self):
        from config.agnos_agent_registration import AgentRegistryClient

        client = AgentRegistryClient()
        assert client._session is None
        _ = client.session
        assert client._session is not None

    def test_session_sets_api_key_header(self):
        with patch.dict(os.environ, {"AGNOS_AGENT_API_KEY": "test-key"}, clear=False):
            from config.agnos_agent_registration import AgentRegistryClient

            client = AgentRegistryClient()
            session = client.session
            assert session.headers.get("X-API-Key") == "test-key"


class TestAgentRegistryClientRegister:
    """Tests for register/deregister operations."""

    @pytest.fixture
    def enabled_client(self):
        with patch.dict(
            os.environ,
            {
                "AGNOS_AGENT_REGISTRATION_ENABLED": "true",
                "AGNOS_AGENT_REGISTRY_URL": "http://test:8090",
                "AGNOS_AGENT_API_KEY": "test-key",
            },
            clear=False,
        ):
            from config.agnos_agent_registration import AgentRegistryClient

            client = AgentRegistryClient()
            yield client

    @pytest.fixture
    def disabled_client(self):
        with patch.dict(
            os.environ,
            {"AGNOS_AGENT_REGISTRATION_ENABLED": "false"},
            clear=False,
        ):
            from config.agnos_agent_registration import AgentRegistryClient

            client = AgentRegistryClient()
            yield client

    @pytest.mark.asyncio
    async def test_register_when_disabled(self, disabled_client):
        result = await disabled_client.register_agent("qa-manager")
        assert result["status"] == "disabled"

    @pytest.mark.asyncio
    async def test_register_unknown_agent(self, enabled_client):
        result = await enabled_client.register_agent("nonexistent-agent")
        assert result["status"] == "error"
        assert "Unknown agent" in result["message"]

    @pytest.mark.asyncio
    async def test_register_success(self, enabled_client):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_session = MagicMock()
        mock_session.post.return_value = mock_response
        mock_session.headers = MagicMock()
        enabled_client._session = mock_session

        result = await enabled_client.register_agent("qa-manager")

        assert result["status"] == "registered"
        assert result["agent_id"] == "agnostic-qa-manager"
        assert enabled_client._registered_agents["qa-manager"] is True

    @pytest.mark.asyncio
    async def test_register_http_error(self, enabled_client):
        import requests

        mock_session = MagicMock()
        mock_session.post.side_effect = requests.exceptions.ConnectionError("refused")
        mock_session.headers = MagicMock()
        enabled_client._session = mock_session

        result = await enabled_client.register_agent("qa-manager")

        assert result["status"] == "error"
        assert "refused" in result["message"]

    @pytest.mark.asyncio
    async def test_deregister_when_disabled(self, disabled_client):
        result = await disabled_client.deregister_agent("qa-manager")
        assert result["status"] == "disabled"

    @pytest.mark.asyncio
    async def test_deregister_unknown_agent(self, enabled_client):
        result = await enabled_client.deregister_agent("nonexistent")
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_deregister_success(self, enabled_client):
        enabled_client._registered_agents["qa-manager"] = True

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_session = MagicMock()
        mock_session.delete.return_value = mock_response
        mock_session.headers = MagicMock()
        enabled_client._session = mock_session

        result = await enabled_client.deregister_agent("qa-manager")

        assert result["status"] == "deregistered"
        assert result["agent_id"] == "agnostic-qa-manager"
        assert enabled_client._registered_agents["qa-manager"] is False

    @pytest.mark.asyncio
    async def test_deregister_http_error(self, enabled_client):
        import requests

        enabled_client._registered_agents["qa-manager"] = True

        mock_session = MagicMock()
        mock_session.delete.side_effect = requests.exceptions.Timeout("timeout")
        mock_session.headers = MagicMock()
        enabled_client._session = mock_session

        result = await enabled_client.deregister_agent("qa-manager")

        assert result["status"] == "error"


class TestAgentRegistryClientHeartbeat:
    """Tests for heartbeat functionality."""

    @pytest.fixture
    def client(self):
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
    async def test_heartbeat_skipped_when_not_registered(self, client):
        result = await client.send_heartbeat("qa-manager")
        assert result["status"] == "skipped"

    @pytest.mark.asyncio
    async def test_heartbeat_skipped_when_disabled(self):
        with patch.dict(
            os.environ,
            {"AGNOS_AGENT_REGISTRATION_ENABLED": "false"},
            clear=False,
        ):
            from config.agnos_agent_registration import AgentRegistryClient

            client = AgentRegistryClient()
            result = await client.send_heartbeat("qa-manager")
            assert result["status"] == "skipped"

    @pytest.mark.asyncio
    async def test_heartbeat_unknown_agent(self, client):
        client._registered_agents["nonexistent"] = True
        result = await client.send_heartbeat("nonexistent")
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_heartbeat_success(self, client):
        client._registered_agents["qa-manager"] = True

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_session = MagicMock()
        mock_session.post.return_value = mock_response
        mock_session.headers = MagicMock()
        client._session = mock_session

        result = await client.send_heartbeat("qa-manager", status="busy")

        assert result["status"] == "ok"
        call_args = mock_session.post.call_args
        payload = call_args[1]["json"]
        assert payload["agent_id"] == "agnostic-qa-manager"
        assert payload["status"] == "busy"
        assert "timestamp" in payload

    @pytest.mark.asyncio
    async def test_heartbeat_with_metadata(self, client):
        client._registered_agents["qa-manager"] = True

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_session = MagicMock()
        mock_session.post.return_value = mock_response
        mock_session.headers = MagicMock()
        client._session = mock_session

        result = await client.send_heartbeat(
            "qa-manager", metadata={"active_tasks": 3}
        )

        assert result["status"] == "ok"
        payload = mock_session.post.call_args[1]["json"]
        assert payload["metadata"]["active_tasks"] == 3


class TestAgentRegistryClientBulkOperations:
    """Tests for register_all_agents / deregister_all_agents."""

    @pytest.fixture
    def client(self):
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
    async def test_register_all_agents(self, client):
        from config.agnos_agent_registration import AGNOSTIC_AGENTS

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_session = MagicMock()
        mock_session.post.return_value = mock_response
        mock_session.headers = MagicMock()
        client._session = mock_session

        results = await client.register_all_agents()

        assert len(results) == len(AGNOSTIC_AGENTS)
        for key in AGNOSTIC_AGENTS:
            assert results[key]["status"] == "registered"

    @pytest.mark.asyncio
    async def test_deregister_all_agents(self, client):
        from config.agnos_agent_registration import AGNOSTIC_AGENTS

        # Mark all as registered
        for key in AGNOSTIC_AGENTS:
            client._registered_agents[key] = True

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_session = MagicMock()
        mock_session.delete.return_value = mock_response
        mock_session.headers = MagicMock()
        client._session = mock_session

        results = await client.deregister_all_agents()

        assert len(results) == len(AGNOSTIC_AGENTS)

    @pytest.mark.asyncio
    async def test_deregister_skips_unregistered(self, client):
        # Only mark one as registered
        client._registered_agents["qa-manager"] = True

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_session = MagicMock()
        mock_session.delete.return_value = mock_response
        mock_session.headers = MagicMock()
        client._session = mock_session

        results = await client.deregister_all_agents()

        assert len(results) == 1
        assert "qa-manager" in results


class TestGetRegistrationStatus:
    """Tests for get_registration_status."""

    def test_status_structure(self):
        with patch.dict(
            os.environ,
            {"AGNOS_AGENT_REGISTRATION_ENABLED": "true"},
            clear=False,
        ):
            from config.agnos_agent_registration import AgentRegistryClient

            client = AgentRegistryClient()
            status = client.get_registration_status()

            assert "enabled" in status
            assert "base_url" in status
            assert "registered_agents" in status
            assert "total_agents" in status
            assert status["enabled"] is True
            assert status["total_agents"] == 6

    def test_status_reflects_registrations(self):
        from config.agnos_agent_registration import AgentRegistryClient

        client = AgentRegistryClient()
        client._registered_agents["qa-manager"] = True
        client._registered_agents["senior-qa"] = True

        status = client.get_registration_status()
        assert status["registered_agents"]["qa-manager"] is True
        assert status["registered_agents"]["senior-qa"] is True
