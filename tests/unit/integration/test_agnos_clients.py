"""Tests for AGNOS platform service clients.

Covers: RAG client, screen capture client, recording client,
daimon MCP registration, token budget dashboard, LLM streaming,
marketplace package validation, and persistent memory client.
"""

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))


# ---------------------------------------------------------------------------
# RAG Client
# ---------------------------------------------------------------------------


class TestAgnosRagClient:
    @pytest.fixture
    def client(self):
        with patch.dict(
            os.environ,
            {
                "AGNOS_RAG_ENABLED": "true",
                "AGNOS_AGENT_REGISTRY_URL": "http://test:8090",
            },
            clear=False,
        ):
            from shared.agnos_rag_client import AgnosRagClient

            c = AgnosRagClient()
            yield c

    def test_disabled_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            from shared.agnos_rag_client import AgnosRagClient

            c = AgnosRagClient()
            assert c.enabled is False

    @pytest.mark.asyncio
    async def test_ingest_disabled(self):
        with patch.dict(os.environ, {"AGNOS_RAG_ENABLED": "false"}, clear=False):
            from shared.agnos_rag_client import AgnosRagClient

            c = AgnosRagClient()
            result = await c.ingest("test document")
            assert result["status"] == "disabled"

    @pytest.mark.asyncio
    async def test_ingest_success(self, client):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"status": "ingested", "chunks": 5}

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        mock_http.is_closed = False
        client._client = mock_http

        result = await client.ingest(
            "OWASP Top 10 guide", metadata={"framework": "owasp"}
        )
        assert result["status"] == "ingested"
        assert result["chunks"] == 5

    @pytest.mark.asyncio
    async def test_query_returns_chunks(self, client):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "chunks": [
                {"content": "SQL injection prevention", "score": 0.95, "metadata": {}},
                {"content": "XSS mitigation", "score": 0.88, "metadata": {}},
            ]
        }

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        mock_http.is_closed = False
        client._client = mock_http

        chunks = await client.query("SQL injection", top_k=5)
        assert len(chunks) == 2
        assert chunks[0].content == "SQL injection prevention"
        assert chunks[0].score == 0.95

    @pytest.mark.asyncio
    async def test_query_returns_empty_on_error(self, client):
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(side_effect=Exception("down"))
        mock_http.is_closed = False
        client._client = mock_http

        chunks = await client.query("test")
        assert chunks == []

    @pytest.mark.asyncio
    async def test_query_formatted(self, client):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "formatted_context": "Relevant context: ...",
            "chunks": [],
        }

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        mock_http.is_closed = False
        client._client = mock_http

        context = await client.query_formatted("GDPR compliance")
        assert context == "Relevant context: ..."

    @pytest.mark.asyncio
    async def test_ingest_batch(self, client):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"status": "ingested", "chunks": 3}

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        mock_http.is_closed = False
        client._client = mock_http

        results = await client.ingest_batch(
            [
                {"text": "doc 1", "metadata": {"type": "compliance"}},
                {"text": "doc 2"},
            ]
        )
        assert len(results) == 2
        assert all(r["status"] == "ingested" for r in results)


# ---------------------------------------------------------------------------
# Screen Capture Client
# ---------------------------------------------------------------------------


class TestAgnosScreenClient:
    @pytest.fixture
    def client(self):
        with patch.dict(
            os.environ,
            {
                "AGNOS_SCREEN_ENABLED": "true",
                "AGNOS_AGENT_REGISTRY_URL": "http://test:8090",
            },
            clear=False,
        ):
            from shared.agnos_screen_client import AgnosScreenClient

            c = AgnosScreenClient()
            yield c

    def test_disabled_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            from shared.agnos_screen_client import AgnosScreenClient

            c = AgnosScreenClient()
            assert c.enabled is False

    @pytest.mark.asyncio
    async def test_capture_success(self, client):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "id": "cap-123",
            "width": 1920,
            "height": 1080,
            "format": "png",
            "data_base64": "iVBOR...",
        }

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        mock_http.is_closed = False
        client._client = mock_http

        result = await client.capture(agent_id="agent-1")
        assert result["id"] == "cap-123"
        assert result["width"] == 1920

    @pytest.mark.asyncio
    async def test_start_stop_recording(self, client):
        start_resp = MagicMock()
        start_resp.raise_for_status = MagicMock()
        start_resp.json.return_value = {"status": "recording", "recording_id": "rec-1"}

        stop_resp = MagicMock()
        stop_resp.raise_for_status = MagicMock()
        stop_resp.json.return_value = {"status": "stopped"}

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(side_effect=[start_resp, stop_resp])
        mock_http.is_closed = False
        client._client = mock_http

        start = await client.start_recording(agent_id="agent-1")
        assert start["recording_id"] == "rec-1"

        stop = await client.stop_recording("rec-1")
        assert stop["status"] == "stopped"

    @pytest.mark.asyncio
    async def test_list_recordings(self, client):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"recordings": [{"id": "rec-1"}]}

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)
        mock_http.is_closed = False
        client._client = mock_http

        recordings = await client.list_recordings()
        assert len(recordings) == 1


# ---------------------------------------------------------------------------
# Recording Client (Video Streaming)
# ---------------------------------------------------------------------------


class TestAgnosRecordingClient:
    @pytest.fixture
    def client(self):
        with patch.dict(
            os.environ,
            {
                "AGNOS_SCREEN_ENABLED": "true",
                "AGNOS_AGENT_REGISTRY_URL": "http://test:8090",
            },
            clear=False,
        ):
            from shared.agnos_recording_client import AgnosRecordingClient

            c = AgnosRecordingClient()
            yield c

    @pytest.mark.asyncio
    async def test_start_session_recording(self, client):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "status": "recording",
            "recording_id": "rec-abc",
        }

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        mock_http.is_closed = False
        client._client = mock_http

        result = await client.start_session_recording("session-1", agent_id="agent-1")
        assert result["recording_id"] == "rec-abc"
        assert client._active_recordings["session-1"] == "rec-abc"

    @pytest.mark.asyncio
    async def test_stop_session_recording(self, client):
        client._active_recordings["session-1"] = "rec-abc"

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"status": "stopped"}

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        mock_http.is_closed = False
        client._client = mock_http

        result = await client.stop_session_recording("session-1")
        assert result["status"] == "stopped"
        assert "session-1" not in client._active_recordings

    @pytest.mark.asyncio
    async def test_stop_nonexistent_session(self, client):
        result = await client.stop_session_recording("no-such-session")
        assert result["status"] == "not_found"

    def test_get_active_sessions(self, client):
        client._active_recordings = {"s1": "r1", "s2": "r2"}
        active = client.get_active_sessions()
        assert active == {"s1": "r1", "s2": "r2"}


# ---------------------------------------------------------------------------
# Daimon MCP Registration
# ---------------------------------------------------------------------------


class TestDaimonMcpRegistration:
    def test_disabled_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            from shared.yeoman_mcp_server import DaimonMcpRegistration

            reg = DaimonMcpRegistration()
            assert reg.enabled is False

    def test_enabled_via_env(self):
        with patch.dict(os.environ, {"DAIMON_MCP_AUTO_REGISTER": "true"}, clear=False):
            from shared.yeoman_mcp_server import DaimonMcpRegistration

            reg = DaimonMcpRegistration()
            assert reg.enabled is True

    @pytest.mark.asyncio
    async def test_register_disabled(self):
        with patch.dict(os.environ, {"DAIMON_MCP_AUTO_REGISTER": "false"}, clear=False):
            from shared.yeoman_mcp_server import DaimonMcpRegistration

            reg = DaimonMcpRegistration()
            result = await reg.register()
            assert result is False

    @pytest.mark.asyncio
    async def test_register_success(self):
        with patch.dict(
            os.environ,
            {
                "DAIMON_MCP_AUTO_REGISTER": "true",
                "AGNOS_AGENT_REGISTRY_URL": "http://test:8090",
            },
            clear=False,
        ):
            from shared.yeoman_mcp_server import DaimonMcpRegistration

            reg = DaimonMcpRegistration()

            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = {"id": "daimon-server-1"}

            mock_http = AsyncMock()
            mock_http.post = AsyncMock(return_value=mock_response)
            mock_http.is_closed = False
            reg._client = mock_http

            result = await reg.register()
            assert result is True
            assert reg._server_id == "daimon-server-1"

    @pytest.mark.asyncio
    async def test_deregister_success(self):
        with patch.dict(
            os.environ,
            {"DAIMON_MCP_AUTO_REGISTER": "true"},
            clear=False,
        ):
            from shared.yeoman_mcp_server import DaimonMcpRegistration

            reg = DaimonMcpRegistration()
            reg._server_id = "daimon-server-1"

            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()

            mock_http = AsyncMock()
            mock_http.delete = AsyncMock(return_value=mock_response)
            mock_http.is_closed = False
            reg._client = mock_http

            result = await reg.deregister()
            assert result is True
            assert reg._server_id is None


# ---------------------------------------------------------------------------
# Token Budget Pool Dashboard
# ---------------------------------------------------------------------------


class TestTokenBudgetDashboard:
    @pytest.fixture
    def dashboard_client(self):
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except ImportError:
            pytest.skip("fastapi not available")

        from webgui.routes.dashboard import router
        from webgui.routes.dependencies import get_current_user

        app = FastAPI()
        app.dependency_overrides[get_current_user] = lambda: {
            "user_id": "test",
            "role": "admin",
        }
        app.include_router(router, prefix="/api")

        return TestClient(app)

    def test_token_budget_disabled(self, dashboard_client):
        with patch("config.agnos_token_budget.agnos_token_budget") as mock_budget:
            mock_budget.enabled = False
            resp = dashboard_client.get("/api/dashboard/token-budget")
            data = resp.json()
            assert data["enabled"] is False


# ---------------------------------------------------------------------------
# LLM Streaming Support
# ---------------------------------------------------------------------------


class TestLLMStreamingCall:
    def test_streaming_call_method_exists(self):
        pytest.importorskip("litellm")
        from config.llm_integration import LLMIntegrationService

        assert hasattr(LLMIntegrationService, "_streaming_call")

    def test_llm_call_accepts_stream_param(self):
        """Verify _llm_call signature includes stream parameter."""
        pytest.importorskip("litellm")
        import inspect

        from config.llm_integration import LLMIntegrationService

        sig = inspect.signature(LLMIntegrationService._llm_call)
        assert "stream" in sig.parameters


# ---------------------------------------------------------------------------
# Marketplace Package
# ---------------------------------------------------------------------------


class TestMarketplacePackage:
    def test_agpkg_toml_exists(self):
        import tomllib
        from pathlib import Path

        toml_path = Path(__file__).parent.parent.parent.parent / "agnostic.agpkg.toml"
        assert toml_path.exists()

        with open(toml_path, "rb") as f:
            data = tomllib.load(f)

        assert data["package"]["name"] == "agnostic"
        assert "qa" in data["marketplace"]["tags"]
        assert data["marketplace"]["sandbox"]["network_access"] is True
        assert 8000 in data["marketplace"]["services"]["ports"]
        assert data["marketplace"]["agents"]["count"] == 6


# ---------------------------------------------------------------------------
# Persistent Memory Migration
# ---------------------------------------------------------------------------


class TestPersistentMemoryMigration:
    @pytest.fixture
    def client(self):
        with patch.dict(
            os.environ,
            {"AGNOS_MEMORY_ENABLED": "true", "AGNOS_MEMORY_URL": "http://test:8090"},
            clear=False,
        ):
            from shared.agnos_memory import AgnosMemoryClient

            c = AgnosMemoryClient()
            yield c

    @pytest.mark.asyncio
    async def test_store_session(self, client):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        mock_http = AsyncMock()
        mock_http.put = AsyncMock(return_value=mock_response)
        mock_http.is_closed = False
        client._client = mock_http

        result = await client.store_session(
            "agnostic-qa-manager", "sess-1", {"status": "active", "progress": 0.5}
        )
        assert result is True

        call_args = mock_http.put.call_args
        assert "sessions" in call_args[0][0]
        assert "session:sess-1" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_retrieve_session(self, client):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "value": {"status": "active", "progress": 0.5}
        }

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)
        mock_http.is_closed = False
        client._client = mock_http

        session = await client.retrieve_session("agnostic-qa-manager", "sess-1")
        assert session["status"] == "active"

    @pytest.mark.asyncio
    async def test_list_sessions(self, client):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"keys": ["session:s1", "session:s2"]}

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)
        mock_http.is_closed = False
        client._client = mock_http

        sessions = await client.list_sessions("agnostic-qa-manager")
        assert sessions == ["s1", "s2"]

    @pytest.mark.asyncio
    async def test_store_agent_state(self, client):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        mock_http = AsyncMock()
        mock_http.put = AsyncMock(return_value=mock_response)
        mock_http.is_closed = False
        client._client = mock_http

        result = await client.store_agent_state(
            "agnostic-qa-manager", {"tasks_completed": 42}
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_retrieve_agent_state(self, client):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"value": {"tasks_completed": 42}}

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)
        mock_http.is_closed = False
        client._client = mock_http

        state = await client.retrieve_agent_state("agnostic-qa-manager")
        assert state["tasks_completed"] == 42
