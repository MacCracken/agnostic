"""
Agent Monitor Module
Real-time agent activity visualization and performance monitoring.

Uses async Redis throughout to avoid blocking the event loop.
Batches key lookups with MGET to eliminate N+1 query patterns.
"""

import json
import logging
import os
import sys
from collections import OrderedDict
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

# Add config path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.environment import config

logger = logging.getLogger(__name__)

# LRU-style cache: max entries before eviction
_CACHE_MAX_ENTRIES = int(os.getenv("AGENT_MONITOR_CACHE_MAX_ENTRIES", "200"))


class AgentType(Enum):
    MANAGER = "manager"
    SENIOR = "senior"
    JUNIOR = "junior"
    ANALYST = "analyst"
    SECURITY_COMPLIANCE = "security_compliance"
    PERFORMANCE = "performance"


class TaskStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class AgentStatus:
    agent_name: str
    agent_type: AgentType
    status: str
    current_task: str | None
    current_session: str | None
    tasks_completed: int
    tasks_failed: int
    last_heartbeat: datetime
    cpu_usage: float
    memory_usage: float
    response_time_ms: float
    uptime_seconds: int
    error_rate: float


@dataclass
class TaskInfo:
    task_id: str
    agent_name: str
    session_id: str
    task_type: str
    status: TaskStatus
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    duration_seconds: int
    result: dict[str, Any] | None
    error_message: str | None


@dataclass
class AgentMetrics:
    agent_name: str
    time_range: str
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    success_rate: float
    average_duration_seconds: float
    average_response_time_ms: float
    cpu_usage_average: float
    memory_usage_average: float
    error_rate: float
    last_updated: datetime


class _BoundedCache(OrderedDict[str, Any]):
    """OrderedDict with a max-size eviction policy (LRU)."""

    def __init__(self, max_size: int = _CACHE_MAX_ENTRIES) -> None:
        super().__init__()
        self._max_size = max_size

    def __setitem__(self, key: str, value: Any) -> None:
        if key in self:
            self.move_to_end(key)
        super().__setitem__(key, value)
        while len(self) > self._max_size:
            self.popitem(last=False)


class AgentMonitor:
    """Monitors agent activity and performance using async Redis."""

    def __init__(self) -> None:
        self._redis = config.get_async_redis_client()
        self._status_cache = _BoundedCache(_CACHE_MAX_ENTRIES)
        self.cache_timeout = 60  # 1 minute

        # Agent configuration
        self.agents = {
            AgentType.MANAGER: {
                "name": "qa-manager",
                "description": "QA Manager Orchestrator",
            },
            AgentType.SENIOR: {
                "name": "senior-qa",
                "description": "Senior QA Engineer",
            },
            AgentType.JUNIOR: {"name": "junior-qa", "description": "Junior QA Worker"},
            AgentType.ANALYST: {"name": "qa-analyst", "description": "QA Analyst"},
            AgentType.SECURITY_COMPLIANCE: {
                "name": "security-compliance-agent",
                "description": "Security & Compliance Agent",
            },
            AgentType.PERFORMANCE: {
                "name": "performance-agent",
                "description": "Performance & Resilience Agent",
            },
        }

    # ------------------------------------------------------------------
    # Internal helpers — async Redis with MGET batching
    # ------------------------------------------------------------------

    async def _scan_keys(self, pattern: str, count: int = 100) -> list[str]:
        """Async SCAN for keys matching pattern."""
        keys: list[str] = []
        async for key in self._redis.scan_iter(pattern, count=count):
            keys.append(key)
        return keys

    async def _mget_parsed(self, keys: list[str]) -> list[dict[str, Any] | None]:
        """MGET + JSON parse in one shot. Returns None for missing/bad entries."""
        if not keys:
            return []
        values = await self._redis.mget(keys)
        results: list[dict[str, Any] | None] = []
        for v in values:
            if v is None:
                results.append(None)
                continue
            try:
                results.append(json.loads(v))
            except (json.JSONDecodeError, TypeError):
                results.append(None)
        return results

    async def _get_task_data_for_agent(self, agent_name: str) -> list[dict[str, Any]]:
        """Fetch all task data for an agent using SCAN + MGET (not N+1)."""
        keys = await self._scan_keys(f"task:{agent_name}:*")
        parsed = await self._mget_parsed(keys)
        return [d for d in parsed if d is not None]

    async def _count_tasks_by_status(self, agent_name: str) -> dict[str, int]:
        """Count tasks grouped by status in a single SCAN + MGET pass."""
        tasks = await self._get_task_data_for_agent(agent_name)
        counts: dict[str, int] = {}
        for t in tasks:
            status = t.get("status", "unknown")
            counts[status] = counts.get(status, 0) + 1
        return counts

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_all_agent_status(self) -> list[AgentStatus]:
        """Get status of all agents"""
        agent_statuses = []

        try:
            for agent_type, cfg in self.agents.items():
                agent_name = cfg["name"]
                status = await self._get_agent_status(agent_name, agent_type)
                if status:
                    agent_statuses.append(status)

            # Sort by agent name
            agent_statuses.sort(key=lambda x: x.agent_name)

        except Exception as e:
            logger.error(f"Error getting all agent status: {e}")

        return agent_statuses

    async def get_agent_status(self, agent_name: str) -> AgentStatus | None:
        """Get status of specific agent"""
        try:
            # Find agent type
            agent_type = None
            for atype, cfg in self.agents.items():
                if cfg["name"] == agent_name:
                    agent_type = atype
                    break

            if not agent_type:
                return None

            return await self._get_agent_status(agent_name, agent_type)

        except Exception as e:
            logger.error(f"Error getting agent status {agent_name}: {e}")
            return None

    async def _get_agent_status(
        self, agent_name: str, agent_type: AgentType
    ) -> AgentStatus | None:
        """Get detailed status for an agent (async Redis)."""
        try:
            # Check cache first
            cache_key = f"agent_status:{agent_name}"
            cached = await self._redis.get(cache_key)

            if cached:
                data = json.loads(cached)
                # Parse dates
                data["last_heartbeat"] = datetime.fromisoformat(
                    data.get("last_heartbeat", datetime.now().isoformat())
                )
                return AgentStatus(**data)

            # Get status from Redis (async)
            status_key = f"agent:{agent_name}:status"
            status_data = await self._redis.get(status_key)

            if not status_data:
                # Agent not found, return offline status
                return AgentStatus(
                    agent_name=agent_name,
                    agent_type=agent_type,
                    status="offline",
                    current_task=None,
                    current_session=None,
                    tasks_completed=0,
                    tasks_failed=0,
                    last_heartbeat=datetime.now() - timedelta(hours=1),
                    cpu_usage=0.0,
                    memory_usage=0.0,
                    response_time_ms=0.0,
                    uptime_seconds=0,
                    error_rate=0.0,
                )

            data = json.loads(status_data)

            # Get task counts in a single SCAN + MGET pass (not 3 separate scans)
            counts = await self._count_tasks_by_status(agent_name)
            tasks_completed = counts.get("completed", 0)
            tasks_failed = counts.get("failed", 0)
            total = tasks_completed + tasks_failed
            error_rate = (tasks_failed / total * 100) if total > 0 else 0.0

            status = AgentStatus(
                agent_name=agent_name,
                agent_type=agent_type,
                status=data.get("status", "unknown"),
                current_task=data.get("current_task"),
                current_session=data.get("current_session"),
                tasks_completed=tasks_completed,
                tasks_failed=tasks_failed,
                last_heartbeat=datetime.fromisoformat(
                    data.get("last_heartbeat", datetime.now().isoformat())
                ),
                cpu_usage=data.get("cpu_usage", 0.0),
                memory_usage=data.get("memory_usage", 0.0),
                response_time_ms=data.get("response_time_ms", 0.0),
                uptime_seconds=data.get("uptime_seconds", 0),
                error_rate=error_rate,
            )

            # Cache the result (async)
            await self._redis.setex(
                cache_key, self.cache_timeout, json.dumps(asdict(status), default=str)
            )

            return status

        except Exception as e:
            logger.error(f"Error getting agent status {agent_name}: {e}")
            return None

    async def get_active_tasks(self, agent_name: str | None = None) -> list[TaskInfo]:
        """Get currently active tasks using SCAN + MGET."""
        active_tasks = []

        try:
            pattern = f"task:{agent_name}:*" if agent_name else "task:*"
            keys = await self._scan_keys(pattern)
            parsed = await self._mget_parsed(keys)

            for data in parsed:
                if data is None:
                    continue
                try:
                    if data.get("status") in ["pending", "in_progress"]:
                        created_at = datetime.fromisoformat(
                            data.get("created_at", datetime.now().isoformat())
                        )
                        started_at = None
                        if data.get("started_at"):
                            started_at = datetime.fromisoformat(data["started_at"])
                        completed_at = None
                        if data.get("completed_at"):
                            completed_at = datetime.fromisoformat(data["completed_at"])

                        task = TaskInfo(
                            task_id=data.get("task_id", ""),
                            agent_name=data.get("agent_name", ""),
                            session_id=data.get("session_id", ""),
                            task_type=data.get("task_type", ""),
                            status=TaskStatus(data.get("status", "pending")),
                            created_at=created_at,
                            started_at=started_at,
                            completed_at=completed_at,
                            duration_seconds=data.get("duration_seconds", 0),
                            result=data.get("result"),
                            error_message=data.get("error_message"),
                        )

                        active_tasks.append(task)

                except (ValueError, KeyError) as e:
                    logger.warning(f"Error parsing task data: {e}")
                    continue

            # Sort by created_at
            active_tasks.sort(key=lambda x: x.created_at, reverse=True)

        except Exception as e:
            logger.error(f"Error getting active tasks: {e}")

        return active_tasks

    async def get_agent_metrics(
        self, agent_name: str, time_range: str = "24h"
    ) -> AgentMetrics | None:
        """Get performance metrics for an agent"""
        try:
            # Calculate time range
            now = datetime.now()
            if time_range == "1h":
                start_time = now - timedelta(hours=1)
            elif time_range == "24h":
                start_time = now - timedelta(hours=24)
            elif time_range == "7d":
                start_time = now - timedelta(days=7)
            elif time_range == "30d":
                start_time = now - timedelta(days=30)
            else:
                start_time = now - timedelta(hours=24)

            # Get tasks in time range (single SCAN + MGET)
            tasks = await self._get_tasks_in_range(agent_name, start_time, now)

            if not tasks:
                return None

            # Calculate metrics
            total_tasks = len(tasks)
            completed_tasks = len([t for t in tasks if t.get("status") == "completed"])
            failed_tasks = len([t for t in tasks if t.get("status") == "failed"])
            success_rate = (
                (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
            )

            # Calculate durations
            durations = [
                t.get("duration_seconds", 0) for t in tasks if t.get("duration_seconds")
            ]
            avg_duration = sum(durations) / len(durations) if durations else 0

            # Get performance data (single SCAN + MGET)
            perf_data = await self._get_performance_data(agent_name, start_time, now)

            # Error rate from same data (no extra scan)
            total_terminal = completed_tasks + failed_tasks
            error_rate = (
                (failed_tasks / total_terminal * 100) if total_terminal > 0 else 0.0
            )

            metrics = AgentMetrics(
                agent_name=agent_name,
                time_range=time_range,
                total_tasks=total_tasks,
                completed_tasks=completed_tasks,
                failed_tasks=failed_tasks,
                success_rate=success_rate,
                average_duration_seconds=avg_duration,
                average_response_time_ms=perf_data.get("avg_response_time_ms", 0),
                cpu_usage_average=perf_data.get("avg_cpu_usage", 0),
                memory_usage_average=perf_data.get("avg_memory_usage", 0),
                error_rate=error_rate,
                last_updated=datetime.now(),
            )

            return metrics

        except Exception as e:
            logger.error(f"Error getting agent metrics {agent_name}: {e}")
            return None

    async def get_agent_communication_graph(self) -> dict[str, Any]:
        """Get agent communication flow visualization data"""
        graph_data: dict[str, Any] = {
            "nodes": [],
            "edges": [],
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "time_range": "24h",
            },
        }

        try:
            # Add nodes for each agent
            for agent_type, cfg in self.agents.items():
                agent_name = cfg["name"]
                status = await self._get_agent_status(agent_name, agent_type)

                if status:
                    node = {
                        "id": agent_name,
                        "label": cfg["description"],
                        "type": agent_type.value,
                        "status": status.status,
                        "tasks_completed": status.tasks_completed,
                        "current_task": status.current_task,
                    }
                    graph_data["nodes"].append(node)

            # Get communication edges from recent notifications
            time_threshold = datetime.now() - timedelta(hours=24)

            for agent_type, cfg in self.agents.items():
                agent_name = cfg["name"]

                # Get recent notifications (async SCAN + MGET)
                notif_pattern = f"{agent_name}:*:notifications"
                notif_keys = await self._scan_keys(notif_pattern)

                for key in notif_keys:
                    notifications = await self._redis.lrange(key, 0, -1)  # type: ignore[misc]
                    for notif in notifications:
                        try:
                            data = json.loads(notif)
                            notif_time = datetime.fromisoformat(
                                data.get("timestamp", "")
                            )

                            if notif_time >= time_threshold:
                                target_agent = data.get("target_agent")
                                if target_agent and target_agent != agent_name:
                                    edge = {
                                        "source": agent_name,
                                        "target": target_agent,
                                        "type": data.get("type", "notification"),
                                        "timestamp": data.get("timestamp"),
                                        "message": data.get("message", "")[:50] + "...",
                                    }
                                    graph_data["edges"].append(edge)

                        except (json.JSONDecodeError, ValueError):
                            continue

        except Exception as e:
            logger.error(f"Error getting communication graph: {e}")

        return graph_data

    async def get_queue_depths(self) -> dict[str, int]:
        """Get current queue depths for each agent using SCAN + MGET."""
        queue_depths = {}

        try:
            for cfg in self.agents.values():
                agent_name = cfg["name"]
                tasks = await self._get_task_data_for_agent(agent_name)
                pending = sum(1 for t in tasks if t.get("status") == "pending")
                queue_depths[agent_name] = pending

        except Exception as e:
            logger.error(f"Error getting queue depths: {e}")

        return queue_depths

    # ------------------------------------------------------------------
    # Private helpers (all async, using batched MGET)
    # ------------------------------------------------------------------

    async def _get_tasks_in_range(
        self, agent_name: str, start_time: datetime, end_time: datetime
    ) -> list[dict[str, Any]]:
        """Get tasks for agent within time range (single SCAN + MGET)."""
        tasks = []
        all_tasks = await self._get_task_data_for_agent(agent_name)

        for data in all_tasks:
            try:
                created_at = datetime.fromisoformat(data.get("created_at", ""))
                if start_time <= created_at <= end_time:
                    tasks.append(data)
            except (ValueError, TypeError):
                continue

        return tasks

    async def _get_performance_data(
        self, agent_name: str, start_time: datetime, end_time: datetime
    ) -> dict[str, float]:
        """Get performance metrics for agent in time range (single SCAN + MGET)."""
        perf_data = {
            "avg_response_time_ms": 0.0,
            "avg_cpu_usage": 0.0,
            "avg_memory_usage": 0.0,
        }

        try:
            keys = await self._scan_keys(f"perf:{agent_name}:*")
            parsed = await self._mget_parsed(keys)

            response_times = []
            cpu_usages = []
            memory_usages = []

            for data in parsed:
                if data is None:
                    continue
                try:
                    timestamp = datetime.fromisoformat(data.get("timestamp", ""))
                    if start_time <= timestamp <= end_time:
                        if "response_time_ms" in data:
                            response_times.append(data["response_time_ms"])
                        if "cpu_usage" in data:
                            cpu_usages.append(data["cpu_usage"])
                        if "memory_usage" in data:
                            memory_usages.append(data["memory_usage"])
                except (ValueError, TypeError):
                    continue

            if response_times:
                perf_data["avg_response_time_ms"] = sum(response_times) / len(
                    response_times
                )
            if cpu_usages:
                perf_data["avg_cpu_usage"] = sum(cpu_usages) / len(cpu_usages)
            if memory_usages:
                perf_data["avg_memory_usage"] = sum(memory_usages) / len(memory_usages)

        except Exception as e:
            logger.error(f"Error getting performance data for {agent_name}: {e}")

        return perf_data


# Singleton instance
agent_monitor = AgentMonitor()
