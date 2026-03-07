"""
Dashboard View Module
Real-time dashboard showing all active testing sessions with status indicators and resource utilization.
"""

import json
import logging
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from typing import Any

# Add config path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.environment import config

logger = logging.getLogger(__name__)


class SessionStatus(Enum):
    CREATED = "created"
    PLANNING = "planning"
    TESTING = "testing"
    ANALYSIS = "analysis"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentStatus(Enum):
    IDLE = "idle"
    BUSY = "busy"
    ERROR = "error"
    OFFLINE = "offline"


@dataclass
class SessionInfo:
    session_id: str
    title: str
    status: SessionStatus
    created_at: datetime
    updated_at: datetime
    progress: int
    agent_count: int
    scenarios_completed: int
    scenarios_total: int
    verification_score: float | None = None
    user_id: str | None = None
    environment: str | None = None


@dataclass
class AgentInfo:
    agent_name: str
    agent_type: str
    status: AgentStatus
    current_task: str | None
    tasks_completed: int
    last_heartbeat: datetime
    cpu_usage: float
    memory_usage: float


@dataclass
class ResourceMetrics:
    total_sessions: int
    active_sessions: int
    active_agents: int
    redis_memory_usage: int
    redis_connections: int
    system_load: float
    uptime_seconds: int


@dataclass
class ComplianceMetrics:
    gdpr_score: float
    pci_score: float
    soc2_score: float
    iso27001_score: float
    hipaa_score: float
    overall_score: float


@dataclass
class PredictiveMetrics:
    predicted_defects: int
    risk_score: float
    quality_trend: str
    release_readiness: float


@dataclass
class CrossPlatformMetrics:
    web_score: float
    mobile_score: float
    desktop_score: float
    overall_score: float


class DashboardManager:
    """Manages real-time dashboard data and metrics"""

    def __init__(self):
        self.redis_client = config.get_redis_client()
        self.sessions_cache = {}
        self.agents_cache = {}
        self.last_cache_update = None

    async def get_active_sessions(self) -> list[SessionInfo]:
        """Get all active testing sessions"""
        sessions = []

        try:
            # Get session keys from Redis (scan_iter avoids blocking the server)
            session_keys = list(
                self.redis_client.scan_iter("session:*:info", count=200)
            )

            for key in session_keys:
                session_id = key.decode().split(":")[1]
                session_data = self.redis_client.get(key)

                if session_data:
                    try:
                        data = json.loads(session_data)

                        # Parse status
                        status = SessionStatus.CREATED
                        if "status" in data:
                            try:
                                status = SessionStatus(data["status"])
                            except ValueError:
                                status = SessionStatus.CREATED

                        sessions.append(
                            SessionInfo(
                                session_id=session_id,
                                title=data.get("title", f"Session {session_id}"),
                                status=status,
                                created_at=datetime.fromisoformat(
                                    data.get("created_at", datetime.now().isoformat())
                                ),
                                updated_at=datetime.fromisoformat(
                                    data.get("updated_at", datetime.now().isoformat())
                                ),
                                progress=data.get("progress", 0),
                                agent_count=data.get("agent_count", 0),
                                scenarios_completed=data.get("scenarios_completed", 0),
                                scenarios_total=data.get("scenarios_total", 0),
                                verification_score=data.get("verification_score"),
                                user_id=data.get("user_id"),
                                environment=data.get("environment"),
                            )
                        )
                    except (json.JSONDecodeError, ValueError) as e:
                        logger.warning(f"Error parsing session {session_id}: {e}")
                        continue

            # Sort by updated_at (most recent first)
            sessions.sort(key=lambda x: x.updated_at, reverse=True)

        except Exception as e:
            logger.error(f"Error getting active sessions: {e}")

        return sessions

    async def get_agent_status(self) -> list[AgentInfo]:
        """Get status of all agents"""
        agents = []

        try:
            # Get agent status from Redis (scan_iter avoids blocking the server)
            agent_keys = list(self.redis_client.scan_iter("agent:*:status", count=200))

            for key in agent_keys:
                agent_name = key.decode().split(":")[1]
                status_data = self.redis_client.get(key)

                if status_data:
                    try:
                        data = json.loads(status_data)

                        # Parse status
                        status = AgentStatus.IDLE
                        if "status" in data:
                            try:
                                status = AgentStatus(data["status"])
                            except ValueError:
                                status = AgentStatus.IDLE

                        agents.append(
                            AgentInfo(
                                agent_name=agent_name,
                                agent_type=data.get("agent_type", "unknown"),
                                status=status,
                                current_task=data.get("current_task"),
                                tasks_completed=data.get("tasks_completed", 0),
                                last_heartbeat=datetime.fromisoformat(
                                    data.get(
                                        "last_heartbeat", datetime.now().isoformat()
                                    )
                                ),
                                cpu_usage=data.get("cpu_usage", 0.0),
                                memory_usage=data.get("memory_usage", 0.0),
                            )
                        )
                    except (json.JSONDecodeError, ValueError) as e:
                        logger.warning(f"Error parsing agent status {agent_name}: {e}")
                        continue

            # Sort by agent name
            agents.sort(key=lambda x: x.agent_name)

        except Exception as e:
            logger.error(f"Error getting agent status: {e}")

        return agents

    async def get_resource_metrics(self) -> ResourceMetrics:
        """Get system resource metrics"""
        try:
            # Get Redis info
            redis_info = self.redis_client.info()

            # Fetch once, derive both filtered and total counts
            all_sessions = await self.get_active_sessions()
            all_agents = await self.get_agent_status()
            active_sessions = len(
                [
                    s
                    for s in all_sessions
                    if s.status
                    in [
                        SessionStatus.PLANNING,
                        SessionStatus.TESTING,
                        SessionStatus.ANALYSIS,
                    ]
                ]
            )
            active_agents = len(
                [a for a in all_agents if a.status != AgentStatus.OFFLINE]
            )

            return ResourceMetrics(
                total_sessions=len(all_sessions),
                active_sessions=active_sessions,
                active_agents=active_agents,
                redis_memory_usage=redis_info.get("used_memory", 0),
                redis_connections=redis_info.get("connected_clients", 0),
                system_load=os.getloadavg()[0] if hasattr(os, "getloadavg") else 0.0,
                uptime_seconds=redis_info.get("uptime_in_seconds", 0),
            )

        except Exception as e:
            logger.error(f"Error getting resource metrics: {e}")
            return ResourceMetrics(
                total_sessions=0,
                active_sessions=0,
                active_agents=0,
                redis_memory_usage=0,
                redis_connections=0,
                system_load=0.0,
                uptime_seconds=0,
            )

    async def get_session_details(self, session_id: str) -> dict[str, Any] | None:
        """Get detailed information about a specific session"""
        try:
            # Get session info
            session_key = f"session:{session_id}:info"
            session_data = self.redis_client.get(session_key)

            if not session_data:
                return None

            session_info = json.loads(session_data)

            # Get test plan
            plan_key = f"manager:{session_id}:test_plan"
            plan_data = self.redis_client.get(plan_key)
            test_plan = json.loads(plan_data) if plan_data else {}

            # Get verification results
            verify_key = f"manager:{session_id}:verification"
            verify_data = self.redis_client.get(verify_key)
            verification = json.loads(verify_data) if verify_data else {}

            # Get agent tasks
            tasks = {}
            for agent_name in [
                "manager",
                "senior",
                "junior",
                "analyst",
                "security_compliance",
                "performance",
            ]:
                task_key = f"{agent_name}:{session_id}:tasks"
                task_data = self.redis_client.lrange(task_key, 0, -1)
                if task_data:
                    tasks[agent_name] = [json.loads(task) for task in task_data if task]

            return {
                "session_info": session_info,
                "test_plan": test_plan,
                "verification": verification,
                "agent_tasks": tasks,
                "timeline": await self._get_session_timeline(session_id),
            }

        except Exception as e:
            logger.error(f"Error getting session details {session_id}: {e}")
            return None

    async def _get_session_timeline(self, session_id: str) -> list[dict[str, Any]]:
        """Get timeline events for a session"""
        timeline = []

        try:
            # Get notifications from all agents
            for agent_name in [
                "manager",
                "senior",
                "junior",
                "analyst",
                "security_compliance",
                "performance",
            ]:
                notif_key = f"{agent_name}:{session_id}:notifications"
                notifications = self.redis_client.lrange(notif_key, 0, -1)

                for notif in notifications:
                    try:
                        data = json.loads(notif)
                        timeline.append(
                            {
                                "timestamp": data.get("timestamp"),
                                "agent": agent_name,
                                "type": data.get("type", "notification"),
                                "message": data.get("message", ""),
                                "data": data,
                            }
                        )
                    except json.JSONDecodeError:
                        continue

            # Sort by timestamp
            timeline.sort(key=lambda x: x.get("timestamp", ""))

        except Exception as e:
            logger.error(f"Error getting session timeline: {e}")

        return timeline

    def get_status_color(self, status: SessionStatus) -> str:
        """Get color code for session status"""
        colors = {
            SessionStatus.CREATED: "gray",
            SessionStatus.PLANNING: "blue",
            SessionStatus.TESTING: "yellow",
            SessionStatus.ANALYSIS: "orange",
            SessionStatus.COMPLETED: "green",
            SessionStatus.FAILED: "red",
            SessionStatus.CANCELLED: "gray",
        }
        return colors.get(status, "gray")

    def get_agent_status_color(self, status: AgentStatus) -> str:
        """Get color code for agent status"""
        colors = {
            AgentStatus.IDLE: "green",
            AgentStatus.BUSY: "yellow",
            AgentStatus.ERROR: "red",
            AgentStatus.OFFLINE: "gray",
        }
        return colors.get(status, "gray")

    async def export_dashboard_data(self) -> dict[str, Any]:
        """Export dashboard data for external consumption"""
        return {
            "timestamp": datetime.now().isoformat(),
            "sessions": [
                asdict(session) for session in await self.get_active_sessions()
            ],
            "agents": [asdict(agent) for agent in await self.get_agent_status()],
            "metrics": asdict(await self.get_resource_metrics()),
        }


# Singleton instance
dashboard_manager = DashboardManager()
