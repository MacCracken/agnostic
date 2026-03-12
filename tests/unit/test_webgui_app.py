"""Tests for webgui/app.py — AgenticQAGUI, health check, app factory."""

import json
import os
import sys
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

_mock_redis = MagicMock()


@pytest.fixture(autouse=True)
def _patch_redis(monkeypatch):
    monkeypatch.setattr(
        "config.environment.config.get_redis_client", lambda: _mock_redis
    )
    _mock_redis.reset_mock()
    _mock_redis.get.reset_mock()
    _mock_redis.ping.reset_mock()
    _mock_redis.get.return_value = None
    _mock_redis.get.side_effect = None
    _mock_redis.ping.return_value = True
    _mock_redis.ping.side_effect = None


class TestAgenticQAGUI:
    @pytest.mark.asyncio
    async def test_start_new_session(self):
        from webgui.app import AgenticQAGUI

        gui = AgenticQAGUI()
        session_id = await gui.start_new_session()
        assert session_id.startswith("session_")
        assert session_id in gui.active_sessions
        assert gui.active_sessions[session_id]["status"] == "created"

    @pytest.mark.asyncio
    async def test_get_session_status_active(self):
        from webgui.app import AgenticQAGUI

        gui = AgenticQAGUI()
        sid = await gui.start_new_session()
        status = await gui.get_session_status(sid)
        assert status["status"] == "created"

    @pytest.mark.asyncio
    async def test_get_reasoning_trace_empty(self):
        from webgui.app import AgenticQAGUI

        gui = AgenticQAGUI()
        _mock_redis.lrange.return_value = []
        trace = await gui.get_reasoning_trace("sess1")
        assert trace == []

    @pytest.mark.asyncio
    async def test_get_reasoning_trace_parses_notifications(self):
        from webgui.app import AgenticQAGUI

        gui = AgenticQAGUI()
        notif = {
            "timestamp": "2026-01-01T00:00:00",
            "agent": "manager",
            "scenario_id": "sc1",
        }
        _mock_redis.lrange.return_value = [json.dumps(notif).encode()]
        trace = await gui.get_reasoning_trace("sess1")
        assert len(trace) == 1
        assert trace[0]["agent"] == "manager"

    @pytest.mark.asyncio
    async def test_get_reasoning_trace_skips_bad_json(self):
        from webgui.app import AgenticQAGUI

        gui = AgenticQAGUI()
        _mock_redis.lrange.return_value = [
            b"not json",
            json.dumps({"timestamp": "t", "agent": "a", "scenario_id": "s"}).encode(),
        ]
        trace = await gui.get_reasoning_trace("sess1")
        assert len(trace) == 1

    @pytest.mark.asyncio
    async def test_submit_requirements_error(self):
        from webgui.app import AgenticQAGUI

        gui = AgenticQAGUI()
        sid = await gui.start_new_session()
        # Without a real QAManagerAgent, this will fail
        result = await gui.submit_requirements(sid, {"title": "test"})
        assert "error" in result


class TestHealthCheck:
    """Test the health check endpoint via TestClient."""

    @pytest.fixture()
    def client(self):
        from fastapi.testclient import TestClient

        from webgui.app import app

        return TestClient(app, raise_server_exceptions=False)

    def test_health_degraded_no_agents(self, client):
        """No agents alive → degraded (503)."""
        _mock_redis.ping.side_effect = None
        _mock_redis.ping.return_value = True
        _mock_redis.get.return_value = None
        with patch("socket.create_connection") as mock_sock:
            mock_sock.return_value = MagicMock()
            response = client.get("/health")
        # Degraded returns 503 for monitoring systems
        assert response.status_code == 503
        data = response.json()
        assert "status" in data
        assert "redis" in data
        assert "agents" in data
        assert data["status"] in ("degraded", "healthy")

    def test_health_redis_error(self, client):
        """Redis down → unhealthy (503)."""
        _mock_redis.ping.side_effect = Exception("Connection refused")
        _mock_redis.ping.return_value = None
        _mock_redis.get.return_value = None
        with patch("socket.create_connection") as mock_sock:
            mock_sock.return_value = MagicMock()
            response = client.get("/health")
        assert response.status_code == 503
        data = response.json()
        assert data["redis"] == "error"

    def test_health_rabbitmq_error(self, client):
        _mock_redis.ping.side_effect = None
        _mock_redis.ping.return_value = True
        _mock_redis.get.return_value = None
        with (
            patch.dict(os.environ, {"RABBITMQ_HOST": "rabbitmq"}),
            patch("socket.create_connection", side_effect=Exception("refused")),
        ):
            response = client.get("/health")
        data = response.json()
        assert data["rabbitmq"] == "error"

    def test_health_healthy_with_alive_agent(self, client):
        """All systems up + agent alive → healthy (200)."""
        _mock_redis.ping.side_effect = None
        _mock_redis.ping.return_value = True
        agent_status = {
            "last_heartbeat": datetime.now().isoformat(),
            "status": "idle",
        }
        _mock_redis.get.return_value = json.dumps(agent_status).encode()
        with (
            patch.dict(os.environ, {"RABBITMQ_HOST": "rabbitmq"}),
            patch("socket.create_connection") as mock_sock,
        ):
            mock_sock.return_value = MagicMock()
            response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
