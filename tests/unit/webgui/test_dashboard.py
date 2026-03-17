"""Tests for webgui/dashboard.py — DashboardManager, SessionInfo, AgentInfo, ResourceMetrics."""

import json
import os
import sys
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

_mock_redis = AsyncMock()


async def _async_iter(items):
    """Helper to create an async iterator from a list."""
    for item in items:
        yield item


@pytest.fixture(autouse=True)
def _patch_redis(monkeypatch):
    monkeypatch.setattr(
        "config.environment.config.get_async_redis_client", lambda: _mock_redis
    )
    _mock_redis.reset_mock()
    _mock_redis.get.reset_mock()
    _mock_redis.get.return_value = None
    _mock_redis.get.side_effect = None
    # scan_iter must be a regular method returning an async iterator (not a coroutine)
    _mock_redis.scan_iter = MagicMock(return_value=_async_iter([]))
    _mock_redis.info.reset_mock()
    _mock_redis.info.side_effect = None
    _mock_redis.lrange.reset_mock()
    _mock_redis.lrange.return_value = []
    _mock_redis.lrange.side_effect = None


def _make_manager():
    from webgui.dashboard import DashboardManager

    return DashboardManager()


class TestEnums:
    def test_session_status_values(self):
        from webgui.dashboard import SessionStatus

        assert SessionStatus.CREATED.value == "created"
        assert SessionStatus.TESTING.value == "testing"
        assert SessionStatus.COMPLETED.value == "completed"

    def test_agent_status_values(self):
        from webgui.dashboard import AgentStatus

        assert AgentStatus.IDLE.value == "idle"
        assert AgentStatus.BUSY.value == "busy"
        assert AgentStatus.OFFLINE.value == "offline"


class TestGetActiveSessions:
    @pytest.mark.asyncio
    async def test_returns_empty_when_no_sessions(self):
        _mock_redis.scan_iter = MagicMock(return_value=_async_iter([]))
        mgr = _make_manager()
        sessions = await mgr.get_active_sessions()
        assert sessions == []

    @pytest.mark.asyncio
    async def test_parses_session_data(self):
        now = datetime.now().isoformat()
        session_data = {
            "title": "Test Session",
            "status": "testing",
            "created_at": now,
            "updated_at": now,
            "progress": 50,
            "agent_count": 4,
            "scenarios_completed": 5,
            "scenarios_total": 10,
        }
        _mock_redis.scan_iter = MagicMock(
            return_value=_async_iter([b"session:abc:info"])
        )
        _mock_redis.get.return_value = json.dumps(session_data).encode()
        mgr = _make_manager()
        sessions = await mgr.get_active_sessions()
        assert len(sessions) == 1
        assert sessions[0].session_id == "abc"
        assert sessions[0].title == "Test Session"
        assert sessions[0].progress == 50

    @pytest.mark.asyncio
    async def test_handles_invalid_status(self):
        now = datetime.now().isoformat()
        session_data = {
            "status": "invalid_status",
            "created_at": now,
            "updated_at": now,
        }
        _mock_redis.scan_iter = MagicMock(return_value=_async_iter([b"session:x:info"]))
        _mock_redis.get.return_value = json.dumps(session_data).encode()
        mgr = _make_manager()
        sessions = await mgr.get_active_sessions()
        assert len(sessions) == 1
        from webgui.dashboard import SessionStatus

        assert sessions[0].status == SessionStatus.CREATED  # fallback

    @pytest.mark.asyncio
    async def test_skips_invalid_json(self):
        _mock_redis.scan_iter = MagicMock(
            return_value=_async_iter([b"session:bad:info"])
        )
        _mock_redis.get.return_value = b"not json"
        mgr = _make_manager()
        sessions = await mgr.get_active_sessions()
        assert sessions == []


class TestGetAgentStatus:
    @pytest.mark.asyncio
    async def test_returns_empty_when_no_agents(self):
        _mock_redis.scan_iter = MagicMock(return_value=_async_iter([]))
        mgr = _make_manager()
        agents = await mgr.get_agent_status()
        assert agents == []

    @pytest.mark.asyncio
    async def test_parses_agent_data(self):
        agent_data = {
            "agent_type": "manager",
            "status": "busy",
            "current_task": "task-1",
            "tasks_completed": 10,
            "last_heartbeat": datetime.now().isoformat(),
            "cpu_usage": 45.0,
            "memory_usage": 60.0,
        }
        _mock_redis.scan_iter = MagicMock(
            return_value=_async_iter([b"agent:qa-manager:status"])
        )
        _mock_redis.get.return_value = json.dumps(agent_data).encode()
        mgr = _make_manager()
        agents = await mgr.get_agent_status()
        assert len(agents) == 1
        assert agents[0].agent_name == "qa-manager"
        from webgui.dashboard import AgentStatus

        assert agents[0].status == AgentStatus.BUSY

    @pytest.mark.asyncio
    async def test_sorted_by_name(self):
        agents_data = [
            (
                "agent:zeta:status",
                {"status": "idle", "last_heartbeat": datetime.now().isoformat()},
            ),
            (
                "agent:alpha:status",
                {"status": "busy", "last_heartbeat": datetime.now().isoformat()},
            ),
        ]
        _mock_redis.scan_iter = MagicMock(
            return_value=_async_iter([a[0].encode() for a in agents_data])
        )
        _mock_redis.get.side_effect = [json.dumps(a[1]).encode() for a in agents_data]
        mgr = _make_manager()
        agents = await mgr.get_agent_status()
        names = [a.agent_name for a in agents]
        assert names == sorted(names)


class TestGetResourceMetrics:
    @pytest.mark.asyncio
    async def test_returns_metrics(self):
        _mock_redis.info.return_value = {
            "used_memory": 1024000,
            "connected_clients": 5,
            "uptime_in_seconds": 3600,
        }
        _mock_redis.scan_iter = MagicMock(return_value=_async_iter([]))
        mgr = _make_manager()
        metrics = await mgr.get_resource_metrics()
        assert metrics.redis_memory_usage == 1024000
        assert metrics.redis_connections == 5

    @pytest.mark.asyncio
    async def test_returns_defaults_on_error(self):
        _mock_redis.info.side_effect = Exception("Redis down")
        mgr = _make_manager()
        metrics = await mgr.get_resource_metrics()
        assert metrics.total_sessions == 0
        assert metrics.redis_memory_usage == 0


class TestGetSessionDetails:
    @pytest.mark.asyncio
    async def test_returns_none_for_missing_session(self):
        _mock_redis.get.return_value = None
        mgr = _make_manager()
        result = await mgr.get_session_details("missing")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_details_structure(self):
        session_info = {"title": "Test", "status": "completed"}
        _mock_redis.get.side_effect = [
            json.dumps(session_info).encode(),  # session info
            None,  # test plan
            None,  # verification
        ]
        _mock_redis.lrange.return_value = []  # agent tasks
        _mock_redis.scan_iter = MagicMock(return_value=_async_iter([]))
        mgr = _make_manager()
        result = await mgr.get_session_details("sess1")
        assert result is not None
        assert "session_info" in result
        assert "test_plan" in result
        assert "agent_tasks" in result


class TestStatusColors:
    def test_session_status_colors(self):
        from webgui.dashboard import SessionStatus

        mgr = _make_manager()
        assert mgr.get_status_color(SessionStatus.COMPLETED) == "green"
        assert mgr.get_status_color(SessionStatus.FAILED) == "red"
        assert mgr.get_status_color(SessionStatus.TESTING) == "yellow"

    def test_agent_status_colors(self):
        from webgui.dashboard import AgentStatus

        mgr = _make_manager()
        assert mgr.get_agent_status_color(AgentStatus.IDLE) == "green"
        assert mgr.get_agent_status_color(AgentStatus.ERROR) == "red"
        assert mgr.get_agent_status_color(AgentStatus.OFFLINE) == "gray"


class TestExportDashboardData:
    @pytest.mark.asyncio
    async def test_returns_full_export(self):
        _mock_redis.scan_iter = MagicMock(return_value=_async_iter([]))
        _mock_redis.info.return_value = {
            "used_memory": 0,
            "connected_clients": 0,
            "uptime_in_seconds": 0,
        }
        mgr = _make_manager()
        data = await mgr.export_dashboard_data()
        assert "timestamp" in data
        assert "sessions" in data
        assert "agents" in data
        assert "metrics" in data
