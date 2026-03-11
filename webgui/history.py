"""
Session History Module
Provides historical session browsing, comparison, and trend analysis.
"""

import json
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

# Add config path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.environment import config

logger = logging.getLogger(__name__)


class TimeRange(Enum):
    LAST_24_HOURS = "24h"
    LAST_7_DAYS = "7d"
    LAST_30_DAYS = "30d"
    LAST_90_DAYS = "90d"
    ALL_TIME = "all"


class SortBy(Enum):
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"
    DURATION = "duration"
    OVERALL_SCORE = "overall_score"
    TEST_COVERAGE = "test_coverage"


class SortOrder(Enum):
    ASCENDING = "asc"
    DESCENDING = "desc"


@dataclass
class SessionSummary:
    session_id: str
    title: str
    status: str
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    duration_minutes: int
    user_id: str
    environment: str
    overall_score: float | None
    test_coverage: int
    agent_count: int
    scenarios_completed: int
    scenarios_total: int
    error_count: int
    warning_count: int


@dataclass
class SessionComparison:
    session1_id: str
    session2_id: str
    comparison_metrics: dict[str, Any]
    differences: list[dict[str, Any]]
    similarities: list[dict[str, Any]]
    trend_analysis: dict[str, Any]


@dataclass
class TrendData:
    metric: str
    time_range: TimeRange
    data_points: list[tuple[datetime, float]]
    trend_direction: str  # "improving", "declining", "stable"
    trend_percentage: float
    average_value: float
    best_value: float
    worst_value: float


class HistoryManager:
    """Manages historical session data and comparisons"""

    def __init__(self):
        self.redis_client = config.get_redis_client()
        self.session_cache = {}
        self.cache_timeout = 300  # 5 minutes

    async def get_session_history(
        self,
        user_id: str | None = None,
        time_range: TimeRange = TimeRange.LAST_30_DAYS,
        sort_by: SortBy = SortBy.UPDATED_AT,
        sort_order: SortOrder = SortOrder.DESCENDING,
        limit: int = 50,
        offset: int = 0,
        filters: dict[str, Any] | None = None,
    ) -> list[SessionSummary]:
        """Get historical sessions with filtering and sorting"""
        sessions = []

        try:
            # Get all session keys
            session_keys = list(
                self.redis_client.scan_iter("session:*:info", count=100)
            )

            for key in session_keys:
                parts = key.decode(errors="replace").split(":")
                if len(parts) < 2:
                    continue
                session_id = parts[1]
                session_data = self.redis_client.get(key)

                if session_data:
                    try:
                        data = json.loads(session_data)

                        # Parse dates
                        created_at = datetime.fromisoformat(
                            data.get("created_at", datetime.now().isoformat())
                        )
                        updated_at = datetime.fromisoformat(
                            data.get("updated_at", datetime.now().isoformat())
                        )
                        completed_at = None
                        if data.get("completed_at"):
                            completed_at = datetime.fromisoformat(data["completed_at"])

                        # Calculate duration
                        if completed_at:
                            duration = int(
                                (completed_at - created_at).total_seconds() / 60
                            )
                        else:
                            duration = int(
                                (datetime.now() - created_at).total_seconds() / 60
                            )

                        # Apply time range filter
                        if not self._is_in_time_range(created_at, time_range):
                            continue

                        # Apply user filter
                        if user_id and data.get("user_id") != user_id:
                            continue

                        # Apply custom filters
                        if filters and not self._passes_filters(data, filters):
                            continue

                        # Get metrics from Redis
                        metrics = await self._get_session_metrics(session_id)

                        sessions.append(
                            SessionSummary(
                                session_id=session_id,
                                title=data.get("title", f"Session {session_id}"),
                                status=data.get("status", "unknown"),
                                created_at=created_at,
                                updated_at=updated_at,
                                completed_at=completed_at,
                                duration_minutes=duration,
                                user_id=data.get("user_id", "unknown"),
                                environment=data.get("environment", "unknown"),
                                overall_score=metrics.get("overall_score"),
                                test_coverage=metrics.get("test_coverage", 0),
                                agent_count=metrics.get("agent_count", 0),
                                scenarios_completed=metrics.get(
                                    "scenarios_completed", 0
                                ),
                                scenarios_total=metrics.get("scenarios_total", 0),
                                error_count=metrics.get("error_count", 0),
                                warning_count=metrics.get("warning_count", 0),
                            )
                        )

                    except (json.JSONDecodeError, ValueError) as e:
                        logger.warning(f"Error parsing session {session_id}: {e}")
                        continue

            # Sort sessions
            sessions = self._sort_sessions(sessions, sort_by, sort_order)

            # Apply pagination
            total_sessions = len(sessions)
            sessions = sessions[offset : offset + limit]

            logger.info(f"Retrieved {len(sessions)} sessions (total: {total_sessions})")

        except Exception as e:
            logger.error(f"Error getting session history: {e}")

        return sessions

    async def get_session_details(self, session_id: str) -> dict[str, Any] | None:
        """Get detailed session data"""
        try:
            # Check cache first
            cache_key = f"session_details:{session_id}"
            cached = self.redis_client.get(cache_key)
            if cached:
                return json.loads(cached)

            # Collect session data
            from .exports import ReportGenerator

            report_gen = ReportGenerator()
            session_data = await report_gen._collect_session_data(session_id)

            # Cache the result
            self.redis_client.setex(
                cache_key, self.cache_timeout, json.dumps(session_data, default=str)
            )

            return session_data

        except Exception as e:
            logger.error(f"Error getting session details {session_id}: {e}")
            return None

    async def compare_sessions(
        self, session1_id: str, session2_id: str
    ) -> SessionComparison | None:
        """Compare two sessions"""
        try:
            # Get session details
            session1_data = await self.get_session_details(session1_id)
            session2_data = await self.get_session_details(session2_id)

            if not session1_data or not session2_data:
                return None

            # Extract metrics for comparison
            metrics1 = session1_data.get("metrics", {})
            metrics2 = session2_data.get("metrics", {})

            comparison_metrics = {
                "overall_scores": {
                    "session1": metrics1.get("overall_score"),
                    "session2": metrics2.get("overall_score"),
                    "difference": (
                        metrics2.get("overall_score", 0)
                        - metrics1.get("overall_score", 0)
                    ),
                },
                "test_coverage": {
                    "session1": metrics1.get("test_coverage"),
                    "session2": metrics2.get("test_coverage"),
                    "difference": (
                        metrics2.get("test_coverage", 0)
                        - metrics1.get("test_coverage", 0)
                    ),
                },
                "duration": {
                    "session1": metrics1.get("duration_minutes"),
                    "session2": metrics2.get("duration_minutes"),
                    "difference": (
                        metrics2.get("duration_minutes", 0)
                        - metrics1.get("duration_minutes", 0)
                    ),
                },
                "agent_count": {
                    "session1": metrics1.get("total_agents"),
                    "session2": metrics2.get("total_agents"),
                    "difference": (
                        metrics2.get("total_agents", 0)
                        - metrics1.get("total_agents", 0)
                    ),
                },
            }

            # Find differences
            differences = []
            if abs(comparison_metrics["overall_scores"]["difference"] or 0) > 5:
                differences.append(
                    {
                        "metric": "Overall Score",
                        "session1": comparison_metrics["overall_scores"]["session1"],
                        "session2": comparison_metrics["overall_scores"]["session2"],
                        "difference": comparison_metrics["overall_scores"][
                            "difference"
                        ],
                    }
                )

            if abs(comparison_metrics["test_coverage"]["difference"]) > 10:
                differences.append(
                    {
                        "metric": "Test Coverage",
                        "session1": comparison_metrics["test_coverage"]["session1"],
                        "session2": comparison_metrics["test_coverage"]["session2"],
                        "difference": comparison_metrics["test_coverage"]["difference"],
                    }
                )

            # Find similarities
            similarities = []
            if abs(comparison_metrics["agent_count"]["difference"]) == 0:
                similarities.append(
                    {
                        "metric": "Agent Count",
                        "value": comparison_metrics["agent_count"]["session1"],
                    }
                )

            # Trend analysis (would need more historical data)
            trend_analysis = {
                "score_trend": "stable",
                "coverage_trend": "stable",
                "efficiency_trend": "stable",
            }

            return SessionComparison(
                session1_id=session1_id,
                session2_id=session2_id,
                comparison_metrics=comparison_metrics,
                differences=differences,
                similarities=similarities,
                trend_analysis=trend_analysis,
            )

        except Exception as e:
            logger.error(
                f"Error comparing sessions {session1_id} and {session2_id}: {e}"
            )
            return None

    async def get_trend_data(
        self,
        metric: str,
        time_range: TimeRange = TimeRange.LAST_30_DAYS,
        user_id: str | None = None,
    ) -> TrendData | None:
        """Get trend data for a specific metric"""
        try:
            # Get sessions in time range
            sessions = await self.get_session_history(
                user_id=user_id,
                time_range=time_range,
                sort_by=SortBy.CREATED_AT,
                sort_order=SortOrder.ASCENDING,
                limit=1000,  # Get more for trend analysis
            )

            if not sessions:
                return None

            # Extract data points
            data_points = []
            for session in sessions:
                value = None

                if metric == "overall_score":
                    value = session.overall_score
                elif metric == "test_coverage":
                    value = session.test_coverage
                elif metric == "duration":
                    value = session.duration_minutes
                elif metric == "error_count":
                    value = session.error_count

                if value is not None:
                    data_points.append((session.created_at, float(value)))

            if len(data_points) < 2:
                return None

            # Calculate trend
            trend_direction, trend_percentage = self._calculate_trend(data_points)

            # Calculate statistics
            values = [point[1] for point in data_points]
            average_value = sum(values) / len(values)
            best_value = max(values)
            worst_value = min(values)

            return TrendData(
                metric=metric,
                time_range=time_range,
                data_points=data_points,
                trend_direction=trend_direction,
                trend_percentage=trend_percentage,
                average_value=average_value,
                best_value=best_value,
                worst_value=worst_value,
            )

        except Exception as e:
            logger.error(f"Error getting trend data for {metric}: {e}")
            return None

    async def search_sessions(
        self,
        query: str,
        user_id: str | None = None,
        time_range: TimeRange = TimeRange.LAST_30_DAYS,
        limit: int = 20,
    ) -> list[SessionSummary]:
        """Search sessions by title, description, or content"""
        matching_sessions = []

        try:
            # Get all sessions in range
            sessions = await self.get_session_history(
                user_id=user_id,
                time_range=time_range,
                sort_by=SortBy.UPDATED_AT,
                sort_order=SortOrder.DESCENDING,
                limit=1000,
            )

            query_lower = query.lower()

            for session in sessions:
                # Search in title
                if query_lower in session.title.lower():
                    matching_sessions.append(session)
                    continue

                # Get detailed session data for content search
                session_details = await self.get_session_details(session.session_id)
                if session_details:
                    # Search in test plan
                    test_plan = session_details.get("test_plan", {})
                    if query_lower in json.dumps(test_plan).lower():
                        matching_sessions.append(session)
                        continue

                    # Search in agent results
                    agent_results = session_details.get("agent_results", {})
                    if query_lower in json.dumps(agent_results).lower():
                        matching_sessions.append(session)
                        continue

            # Limit results
            matching_sessions = matching_sessions[:limit]

        except Exception as e:
            logger.error(f"Error searching sessions: {e}")

        return matching_sessions

    def _is_in_time_range(self, date: datetime, time_range: TimeRange) -> bool:
        """Check if date falls within time range"""
        now = datetime.now()

        if time_range == TimeRange.LAST_24_HOURS:
            return date >= now - timedelta(hours=24)
        elif time_range == TimeRange.LAST_7_DAYS:
            return date >= now - timedelta(days=7)
        elif time_range == TimeRange.LAST_30_DAYS:
            return date >= now - timedelta(days=30)
        elif time_range == TimeRange.LAST_90_DAYS:
            return date >= now - timedelta(days=90)
        elif time_range == TimeRange.ALL_TIME:
            return True

        return True

    def _passes_filters(
        self, session_data: dict[str, Any], filters: dict[str, Any]
    ) -> bool:
        """Check if session passes custom filters"""
        for key, value in filters.items():
            if key in session_data and session_data[key] != value:
                return False
        return True

    def _sort_sessions(
        self, sessions: list[SessionSummary], sort_by: SortBy, sort_order: SortOrder
    ) -> list[SessionSummary]:
        """Sort sessions by specified criteria"""
        reverse = sort_order == SortOrder.DESCENDING

        if sort_by == SortBy.CREATED_AT:
            sessions.sort(key=lambda x: x.created_at, reverse=reverse)
        elif sort_by == SortBy.UPDATED_AT:
            sessions.sort(key=lambda x: x.updated_at, reverse=reverse)
        elif sort_by == SortBy.DURATION:
            sessions.sort(key=lambda x: x.duration_minutes, reverse=reverse)
        elif sort_by == SortBy.OVERALL_SCORE:
            sessions.sort(key=lambda x: x.overall_score or 0, reverse=reverse)
        elif sort_by == SortBy.TEST_COVERAGE:
            sessions.sort(key=lambda x: x.test_coverage, reverse=reverse)

        return sessions

    async def _get_session_metrics(self, session_id: str) -> dict[str, Any]:
        """Get session metrics from Redis"""
        metrics = {
            "overall_score": None,
            "test_coverage": 0,
            "agent_count": 0,
            "scenarios_completed": 0,
            "scenarios_total": 0,
            "error_count": 0,
            "warning_count": 0,
            "duration_minutes": 0,
        }

        try:
            # Get verification data
            verify_key = f"manager:{session_id}:verification"
            verify_data = self.redis_client.get(verify_key)
            if verify_data:
                verify = json.loads(verify_data)
                metrics["overall_score"] = verify.get("overall_score")

            # Get test plan
            plan_key = f"manager:{session_id}:test_plan"
            plan_data = self.redis_client.get(plan_key)
            if plan_data:
                plan = json.loads(plan_data)
                scenarios = plan.get("scenarios", [])
                metrics["scenarios_total"] = len(scenarios)
                metrics["scenarios_completed"] = len(
                    [s for s in scenarios if s.get("completed", False)]
                )
                if metrics["scenarios_total"] > 0:
                    metrics["test_coverage"] = int(
                        (metrics["scenarios_completed"] / metrics["scenarios_total"])
                        * 100
                    )

            # Count agents with results
            agents = [
                "manager",
                "senior",
                "junior",
                "analyst",
                "security_compliance",
                "performance",
            ]
            for agent in agents:
                agent_key = f"{agent}:{session_id}:report"
                if agent == "manager":
                    agent_key = f"{agent}:{session_id}:report"
                elif agent == "analyst":
                    agent_key = f"{agent}:{session_id}:comprehensive_report"

                if self.redis_client.exists(agent_key):
                    metrics["agent_count"] += 1

                    # Count errors and warnings from agent results
                    result_data = self.redis_client.get(agent_key)
                    if result_data:
                        result = json.loads(result_data)
                        if "errors" in result:
                            metrics["error_count"] += len(result["errors"])
                        if "warnings" in result:
                            metrics["warning_count"] += len(result["warnings"])

        except Exception as e:
            logger.error(f"Error getting session metrics {session_id}: {e}")

        return metrics

    def _calculate_trend(
        self, data_points: list[tuple[datetime, float]]
    ) -> tuple[str, float]:
        """Calculate trend direction and percentage"""
        if len(data_points) < 2:
            return "stable", 0.0

        # Simple linear regression
        n = len(data_points)
        x_values = list(range(n))
        y_values = [point[1] for point in data_points]

        # Calculate slope
        x_mean = sum(x_values) / n
        y_mean = sum(y_values) / n

        numerator = sum(
            (x_values[i] - x_mean) * (y_values[i] - y_mean) for i in range(n)
        )
        denominator = sum((x_values[i] - x_mean) ** 2 for i in range(n))

        if denominator == 0:
            return "stable", 0.0

        slope = numerator / denominator

        # Determine trend
        if abs(slope) < 0.01:
            return "stable", 0.0
        elif slope > 0:
            return "improving", abs(slope) * 10  # Scale to percentage
        else:
            return "declining", abs(slope) * 10


# Singleton instance
history_manager = HistoryManager()
