"""Tests for webgui/agent_monitor.py — AgentMonitor, AgentStatus, TaskInfo.

All Redis calls are now async; the mock uses AsyncMock where needed.
"""

import json
import os
import sys
from datetime import datetime
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

_mock_redis = AsyncMock()


@pytest.fixture(autouse=True)
def _patch_redis(monkeypatch):
    monkeypatch.setattr(
        "config.environment.config.get_async_redis_client", lambda: _mock_redis
    )
    _mock_redis.reset_mock()
    _mock_redis.get = AsyncMock(return_value=None)
    _mock_redis.mget = AsyncMock(return_value=[])
    _mock_redis.setex = AsyncMock()
    _mock_redis.lrange = AsyncMock(return_value=[])

    # scan_iter needs to be an async generator
    async def _empty_scan(*args, **kwargs):
        return
        yield  # makes this an async generator

    _mock_redis.scan_iter = _empty_scan


def _make_monitor():
    from webgui.agent_monitor import AgentMonitor

    return AgentMonitor()


def _set_scan_iter(keys):
    """Helper: make scan_iter yield the given keys."""

    async def _scan(*args, **kwargs):
        for k in keys:
            yield k

    _mock_redis.scan_iter = _scan


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


class TestBoundedCache:
    def test_evicts_oldest(self):
        from webgui.agent_monitor import _BoundedCache

        cache = _BoundedCache(max_size=3)
        cache["a"] = 1
        cache["b"] = 2
        cache["c"] = 3
        cache["d"] = 4
        assert "a" not in cache
        assert "d" in cache
        assert len(cache) == 3


class TestGetAgentStatus:
    @pytest.mark.asyncio
    async def test_returns_offline_when_no_data(self):
        _mock_redis.get = AsyncMock(return_value=None)
        _set_scan_iter([])
        _mock_redis.mget = AsyncMock(return_value=[])
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
        # First call returns cached data from Redis
        _mock_redis.get = AsyncMock(return_value=json.dumps(cached))
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
        _mock_redis.get = AsyncMock(
            side_effect=[None, json.dumps(status_data)]
        )
        _set_scan_iter([])
        _mock_redis.mget = AsyncMock(return_value=[])
        _mock_redis.setex = AsyncMock()
        monitor = _make_monitor()
        status = await monitor._get_agent_status("qa-manager", AgentType.MANAGER)
        assert status.status == "idle"


class TestGetAllAgentStatus:
    @pytest.mark.asyncio
    async def test_returns_list_of_statuses(self):
        _mock_redis.get = AsyncMock(return_value=None)
        _set_scan_iter([])
        _mock_redis.mget = AsyncMock(return_value=[])
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
        _set_scan_iter([])
        _mock_redis.mget = AsyncMock(return_value=[])
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
        _set_scan_iter(["task:qa-manager:t1", "task:qa-manager:t2"])
        _mock_redis.mget = AsyncMock(
            return_value=[
                json.dumps(task_data),
                json.dumps(completed_task),
            ]
        )
        monitor = _make_monitor()
        tasks = await monitor.get_active_tasks()
        assert len(tasks) == 1
        assert tasks[0].task_id == "t1"


class TestGetQueueDepths:
    @pytest.mark.asyncio
    async def test_returns_depths(self):
        pending_task = {"status": "pending"}
        running_task = {"status": "in_progress"}
        _set_scan_iter(["task:qa-manager:1", "task:qa-manager:2"])
        _mock_redis.mget = AsyncMock(
            return_value=[
                json.dumps(pending_task),
                json.dumps(running_task),
            ]
        )
        monitor = _make_monitor()
        depths = await monitor.get_queue_depths()
        assert isinstance(depths, dict)


class TestCountTasksByStatus:
    @pytest.mark.asyncio
    async def test_counts_correctly(self):
        completed = {"status": "completed"}
        failed = {"status": "failed"}
        _set_scan_iter([
            "task:qa-manager:1",
            "task:qa-manager:2",
            "task:qa-manager:3",
            "task:qa-manager:4",
        ])
        _mock_redis.mget = AsyncMock(
            return_value=[
                json.dumps(completed),
                json.dumps(completed),
                json.dumps(completed),
                json.dumps(failed),
            ]
        )
        monitor = _make_monitor()
        counts = await monitor._count_tasks_by_status("qa-manager")
        assert counts["completed"] == 3
        assert counts["failed"] == 1

    @pytest.mark.asyncio
    async def test_error_rate_from_counts(self):
        """Error rate is calculated from single SCAN+MGET pass, not 3 separate scans."""
        completed = {"status": "completed"}
        failed = {"status": "failed"}
        _set_scan_iter([
            "task:qa-manager:1",
            "task:qa-manager:2",
            "task:qa-manager:3",
            "task:qa-manager:4",
        ])
        _mock_redis.mget = AsyncMock(
            return_value=[
                json.dumps(completed),
                json.dumps(completed),
                json.dumps(completed),
                json.dumps(failed),
            ]
        )
        monitor = _make_monitor()
        counts = await monitor._count_tasks_by_status("qa-manager")
        total = counts.get("completed", 0) + counts.get("failed", 0)
        error_rate = (counts.get("failed", 0) / total * 100) if total > 0 else 0.0
        assert error_rate == pytest.approx(25.0, abs=1.0)


class TestGetAgentMetrics:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_tasks(self):
        _set_scan_iter([])
        _mock_redis.mget = AsyncMock(return_value=[])
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
        # First scan_iter for tasks, second for perf data
        call_count = 0

        async def _alternating_scan(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                yield "task:qa-manager:1"
            # perf scan yields nothing

        _mock_redis.scan_iter = _alternating_scan
        _mock_redis.mget = AsyncMock(
            side_effect=[
                [json.dumps(task)],  # task data
                [],  # perf data
            ]
        )
        _mock_redis.get = AsyncMock(return_value=None)
        monitor = _make_monitor()
        metrics = await monitor.get_agent_metrics("qa-manager", "1h")
        assert metrics is not None
        assert metrics.total_tasks == 1
        assert metrics.completed_tasks == 1
