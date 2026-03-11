"""Tests for webgui/agent_monitor.py — AgentMonitor, AgentStatus, TaskInfo."""

import json
import os
import sys
from datetime import datetime
from unittest.mock import MagicMock

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
    _mock_redis.keys.reset_mock()
    _mock_redis.scan_iter.reset_mock()
    _mock_redis.get.return_value = None
    _mock_redis.get.side_effect = None
    _mock_redis.keys.return_value = []
    _mock_redis.keys.side_effect = None
    _mock_redis.scan_iter.return_value = []
    _mock_redis.scan_iter.side_effect = None


def _make_monitor():
    from webgui.agent_monitor import AgentMonitor

    return AgentMonitor()


class TestEnums:
    def test_agent_type_values(self):
        from webgui.agent_monitor import AgentType

        assert AgentType.MANAGER.value == "manager"
        assert AgentType.SECURITY_COMPLIANCE.value == "security_compliance"

    def test_task_status_values(self):
        from webgui.agent_monitor import TaskStatus

        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.FAILED.value == "failed"


class TestAgentMonitorInit:
    def test_has_six_agents(self):
        monitor = _make_monitor()
        assert len(monitor.agents) == 6

    def test_agent_names(self):
        monitor = _make_monitor()
        names = {c["name"] for c in monitor.agents.values()}
        assert "qa-manager" in names
        assert "senior-qa" in names
        assert "security-compliance-agent" in names


class TestGetAgentStatus:
    @pytest.mark.asyncio
    async def test_returns_offline_when_no_data(self):
        _mock_redis.get.return_value = None
        _mock_redis.keys.return_value = []
        _mock_redis.scan_iter.return_value = []
        monitor = _make_monitor()
        status = await monitor.get_agent_status("qa-manager")
        assert status is not None
        assert status.status == "offline"
        assert status.tasks_completed == 0

    @pytest.mark.asyncio
    async def test_returns_none_for_unknown_agent(self):
        monitor = _make_monitor()
        status = await monitor.get_agent_status("nonexistent-agent")
        assert status is None

    @pytest.mark.asyncio
    async def test_returns_cached_status(self):
        from webgui.agent_monitor import AgentType

        cached = {
            "agent_name": "qa-manager",
            "agent_type": "manager",
            "status": "busy",
            "current_task": "task-1",
            "current_session": "sess-1",
            "tasks_completed": 5,
            "tasks_failed": 1,
            "last_heartbeat": datetime.now().isoformat(),
            "cpu_usage": 45.0,
            "memory_usage": 60.0,
            "response_time_ms": 120.0,
            "uptime_seconds": 3600,
            "error_rate": 16.67,
        }
        # First call returns cached data
        _mock_redis.get.side_effect = [json.dumps(cached).encode()]
        monitor = _make_monitor()
        status = await monitor._get_agent_status("qa-manager", AgentType.MANAGER)
        assert status.status == "busy"
        assert status.tasks_completed == 5

    @pytest.mark.asyncio
    async def test_returns_status_from_redis(self):
        from webgui.agent_monitor import AgentType

        status_data = {
            "status": "idle",
            "current_task": None,
            "current_session": None,
            "last_heartbeat": datetime.now().isoformat(),
            "cpu_usage": 10.0,
            "memory_usage": 30.0,
            "response_time_ms": 50.0,
            "uptime_seconds": 7200,
        }
        # get(cache_key) = None, get(status_key) = data
        _mock_redis.get.side_effect = [None, json.dumps(status_data).encode()]
        _mock_redis.keys.return_value = []
        _mock_redis.scan_iter.return_value = []
        _mock_redis.setex = MagicMock()
        monitor = _make_monitor()
        status = await monitor._get_agent_status("qa-manager", AgentType.MANAGER)
        assert status.status == "idle"


class TestGetAllAgentStatus:
    @pytest.mark.asyncio
    async def test_returns_list_of_statuses(self):
        _mock_redis.get.return_value = None
        _mock_redis.keys.return_value = []
        _mock_redis.scan_iter.return_value = []
        monitor = _make_monitor()
        statuses = await monitor.get_all_agent_status()
        assert isinstance(statuses, list)
        assert len(statuses) == 6
        # Should be sorted by name
        names = [s.agent_name for s in statuses]
        assert names == sorted(names)


class TestGetActiveTasks:
    @pytest.mark.asyncio
    async def test_returns_empty_when_no_tasks(self):
        _mock_redis.keys.return_value = []
        _mock_redis.scan_iter.return_value = []
        monitor = _make_monitor()
        tasks = await monitor.get_active_tasks()
        assert tasks == []

    @pytest.mark.asyncio
    async def test_filters_active_tasks(self):
        task_data = {
            "task_id": "t1",
            "agent_name": "qa-manager",
            "session_id": "s1",
            "task_type": "qa",
            "status": "in_progress",
            "created_at": datetime.now().isoformat(),
            "started_at": datetime.now().isoformat(),
            "completed_at": None,
            "duration_seconds": 0,
            "result": None,
            "error_message": None,
        }
        completed_task = {**task_data, "task_id": "t2", "status": "completed"}
        _mock_redis.keys.return_value = [b"task:qa-manager:t1", b"task:qa-manager:t2"]
        _mock_redis.scan_iter.return_value = [
            b"task:qa-manager:t1",
            b"task:qa-manager:t2",
        ]
        _mock_redis.get.side_effect = [
            json.dumps(task_data).encode(),
            json.dumps(completed_task).encode(),
        ]
        monitor = _make_monitor()
        tasks = await monitor.get_active_tasks()
        assert len(tasks) == 1
        assert tasks[0].task_id == "t1"


class TestGetQueueDepths:
    @pytest.mark.asyncio
    async def test_returns_depths(self):
        pending_task = {"status": "pending"}
        running_task = {"status": "in_progress"}
        _mock_redis.keys.return_value = [b"task:qa-manager:1", b"task:qa-manager:2"]
        _mock_redis.scan_iter.return_value = [
            b"task:qa-manager:1",
            b"task:qa-manager:2",
        ]
        _mock_redis.get.side_effect = [
            json.dumps(pending_task).encode(),
            json.dumps(running_task).encode(),
        ] * 6  # 6 agents
        monitor = _make_monitor()
        depths = await monitor.get_queue_depths()
        assert isinstance(depths, dict)


class TestCalculateErrorRate:
    def test_zero_when_no_tasks(self):
        _mock_redis.keys.return_value = []
        _mock_redis.scan_iter.return_value = []
        monitor = _make_monitor()
        assert monitor._calculate_error_rate("qa-manager") == 0.0

    def test_calculates_rate(self):
        completed = {"status": "completed"}
        failed = {"status": "failed"}
        # 3 completed + 1 failed = 25% error rate
        keys = [
            b"task:qa-manager:1",
            b"task:qa-manager:2",
            b"task:qa-manager:3",
            b"task:qa-manager:4",
        ]
        # _calculate_error_rate calls _get_agent_task_count 3 times:
        #   completed (scan_iter + 4 gets), failed (scan_iter + 4 gets), failed again (scan_iter + 4 gets)
        _mock_redis.keys.side_effect = [keys, keys, keys]
        _mock_redis.scan_iter.side_effect = [keys, keys, keys]
        get_responses = [
            json.dumps(completed).encode(),
            json.dumps(completed).encode(),
            json.dumps(completed).encode(),
            json.dumps(failed).encode(),
        ]
        _mock_redis.get.side_effect = get_responses * 3
        monitor = _make_monitor()
        rate = monitor._calculate_error_rate("qa-manager")
        assert rate == pytest.approx(25.0, abs=1.0)


class TestGetAgentMetrics:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_tasks(self):
        _mock_redis.keys.return_value = []
        _mock_redis.scan_iter.return_value = []
        monitor = _make_monitor()
        metrics = await monitor.get_agent_metrics("qa-manager", "24h")
        assert metrics is None

    @pytest.mark.asyncio
    async def test_time_range_parsing(self):
        now = datetime.now()
        task = {
            "status": "completed",
            "created_at": now.isoformat(),
            "duration_seconds": 30,
        }
        _mock_redis.keys.side_effect = [
            [b"task:qa-manager:1"],  # _get_agent_tasks_in_range
            [],  # _get_agent_performance_data
            [],  # _calculate_error_rate (completed)
            [],  # _calculate_error_rate (failed)
        ]
        _mock_redis.scan_iter.side_effect = [
            [b"task:qa-manager:1"],  # _get_agent_tasks_in_range
            [],  # _get_agent_performance_data
            [],  # _calculate_error_rate (completed)
            [],  # _calculate_error_rate (failed)
        ]
        _mock_redis.get.side_effect = [json.dumps(task).encode()]
        monitor = _make_monitor()
        metrics = await monitor.get_agent_metrics("qa-manager", "1h")
        assert metrics is not None
        assert metrics.total_tasks == 1
        assert metrics.completed_tasks == 1
