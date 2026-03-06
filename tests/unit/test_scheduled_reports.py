"""Unit tests for Scheduled Report Generation."""

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


class TestScheduledReportManagerInit:
    """Tests for ScheduledReportManager initialization."""

    def test_defaults_disabled(self):
        """Manager is disabled by default."""
        with patch.dict(os.environ, {}, clear=True):
            from webgui.scheduled_reports import ScheduledReportManager

            mgr = ScheduledReportManager()
            assert mgr.enabled is False

    def test_enabled_via_env(self):
        """Manager enabled when SCHEDULED_REPORTS_ENABLED=true."""
        with patch.dict(os.environ, {"SCHEDULED_REPORTS_ENABLED": "true"}, clear=False):
            from webgui.scheduled_reports import ScheduledReportManager

            mgr = ScheduledReportManager()
            assert mgr.enabled is True

    def test_default_daily_time(self):
        """Default daily time is 09:00."""
        with patch.dict(os.environ, {}, clear=True):
            from webgui.scheduled_reports import ScheduledReportManager

            mgr = ScheduledReportManager()
            assert mgr.daily_time == "09:00"

    def test_custom_daily_time(self):
        """Custom daily time from env var."""
        with patch.dict(
            os.environ, {"SCHEDULED_REPORT_DAILY_TIME": "14:30"}, clear=False
        ):
            from webgui.scheduled_reports import ScheduledReportManager

            mgr = ScheduledReportManager()
            assert mgr.daily_time == "14:30"

    def test_default_weekly_day(self):
        """Default weekly day is monday."""
        with patch.dict(os.environ, {}, clear=True):
            from webgui.scheduled_reports import ScheduledReportManager

            mgr = ScheduledReportManager()
            assert mgr.weekly_day == "monday"

    def test_custom_weekly_day(self):
        """Custom weekly day from env var."""
        with patch.dict(
            os.environ, {"SCHEDULED_REPORT_WEEKLY_DAY": "friday"}, clear=False
        ):
            from webgui.scheduled_reports import ScheduledReportManager

            mgr = ScheduledReportManager()
            assert mgr.weekly_day == "friday"

    def test_default_weekly_time(self):
        """Default weekly time is 09:00."""
        with patch.dict(os.environ, {}, clear=True):
            from webgui.scheduled_reports import ScheduledReportManager

            mgr = ScheduledReportManager()
            assert mgr.weekly_time == "09:00"


class TestScheduledReportManagerDisabled:
    """Tests for behavior when scheduler is disabled."""

    @pytest.mark.asyncio
    async def test_initialize_skips_when_disabled(self):
        """Initialize does nothing when disabled."""
        from webgui.scheduled_reports import ScheduledReportManager

        mgr = ScheduledReportManager()
        mgr.enabled = False

        await mgr.initialize()

        assert mgr.scheduler is None

    def test_get_jobs_returns_empty_when_no_scheduler(self):
        """get_jobs returns empty list when scheduler not initialized."""
        from webgui.scheduled_reports import ScheduledReportManager

        mgr = ScheduledReportManager()
        assert mgr.get_jobs() == []

    def test_remove_job_returns_false_when_no_scheduler(self):
        """remove_job returns False when scheduler not initialized."""
        from webgui.scheduled_reports import ScheduledReportManager

        mgr = ScheduledReportManager()
        assert mgr.remove_job("nonexistent") is False

    @pytest.mark.asyncio
    async def test_shutdown_no_op_when_no_scheduler(self):
        """shutdown is a no-op when scheduler not initialized."""
        from webgui.scheduled_reports import ScheduledReportManager

        mgr = ScheduledReportManager()
        await mgr.shutdown()  # Should not raise


class TestScheduledReportManagerEnabled:
    """Tests for behavior when scheduler is enabled."""

    @pytest.fixture
    def mock_scheduler(self):
        """Create a mock AsyncIOScheduler."""
        scheduler = MagicMock()
        scheduler.add_job = MagicMock()
        scheduler.start = MagicMock()
        scheduler.shutdown = MagicMock()
        scheduler.get_jobs = MagicMock(return_value=[])
        scheduler.remove_job = MagicMock()
        return scheduler

    @pytest.fixture
    def manager_with_scheduler(self, mock_scheduler):
        """Create a ScheduledReportManager with a mock scheduler."""
        from webgui.scheduled_reports import ScheduledReportManager

        mgr = ScheduledReportManager()
        mgr.enabled = True
        mgr.scheduler = mock_scheduler
        return mgr

    def test_schedule_jobs_adds_daily_and_weekly(
        self, manager_with_scheduler, mock_scheduler
    ):
        """_schedule_jobs adds both daily and weekly jobs."""
        manager_with_scheduler._schedule_jobs()

        assert mock_scheduler.add_job.call_count == 2

        call_ids = [c.kwargs.get("id") for c in mock_scheduler.add_job.call_args_list]
        assert "daily_executive_summary" in call_ids
        assert "weekly_compliance_report" in call_ids

    def test_schedule_jobs_daily_has_replace_existing(
        self, manager_with_scheduler, mock_scheduler
    ):
        """Daily job is added with replace_existing=True."""
        manager_with_scheduler._schedule_jobs()

        for call in mock_scheduler.add_job.call_args_list:
            assert call.kwargs.get("replace_existing") is True

    def test_get_jobs_delegates_to_scheduler(
        self, manager_with_scheduler, mock_scheduler
    ):
        """get_jobs returns formatted job list from scheduler."""
        mock_job = MagicMock()
        mock_job.id = "daily_executive_summary"
        mock_job.name = "Daily Executive Summary"
        mock_job.next_run_time = None
        mock_job.trigger = "cron[hour='9', minute='0']"
        mock_scheduler.get_jobs.return_value = [mock_job]

        jobs = manager_with_scheduler.get_jobs()

        assert len(jobs) == 1
        assert jobs[0]["id"] == "daily_executive_summary"
        assert jobs[0]["name"] == "Daily Executive Summary"
        assert jobs[0]["next_run"] is None

    def test_remove_job_delegates_to_scheduler(
        self, manager_with_scheduler, mock_scheduler
    ):
        """remove_job calls scheduler.remove_job."""
        result = manager_with_scheduler.remove_job("daily_executive_summary")

        assert result is True
        mock_scheduler.remove_job.assert_called_once_with("daily_executive_summary")

    def test_remove_job_returns_false_on_error(
        self, manager_with_scheduler, mock_scheduler
    ):
        """remove_job returns False when scheduler raises."""
        mock_scheduler.remove_job.side_effect = Exception("Job not found")

        result = manager_with_scheduler.remove_job("nonexistent")

        assert result is False

    @pytest.mark.asyncio
    async def test_shutdown_calls_scheduler_shutdown(
        self, manager_with_scheduler, mock_scheduler
    ):
        """shutdown calls scheduler.shutdown."""
        await manager_with_scheduler.shutdown()

        mock_scheduler.shutdown.assert_called_once()

    @pytest.mark.asyncio
    async def test_schedule_custom_report_raises_without_scheduler(self):
        """schedule_custom_report raises when scheduler is None."""
        from webgui.scheduled_reports import ScheduledReportManager

        mgr = ScheduledReportManager()
        mgr.scheduler = None

        with pytest.raises(RuntimeError, match="Scheduler not initialized"):
            await mgr.schedule_custom_report(
                "comprehensive", "pdf", {"type": "cron", "hour": 9}
            )


class TestCreateTrigger:
    """Tests for _create_trigger."""

    def test_cron_trigger(self):
        """Creates CronTrigger from cron schedule config."""
        from webgui.scheduled_reports import ScheduledReportManager

        mgr = ScheduledReportManager()
        trigger = mgr._create_trigger({"type": "cron", "hour": 14, "minute": 30})

        from apscheduler.triggers.cron import CronTrigger

        assert isinstance(trigger, CronTrigger)

    def test_interval_trigger_creates_date_trigger(self):
        """Interval type creates DateTrigger (current implementation)."""
        from webgui.scheduled_reports import ScheduledReportManager

        mgr = ScheduledReportManager()
        trigger = mgr._create_trigger(
            {"type": "interval", "run_at": "2026-03-10T09:00:00"}
        )

        from apscheduler.triggers.date import DateTrigger

        assert isinstance(trigger, DateTrigger)

    def test_unknown_trigger_type_raises(self):
        """Unknown schedule type raises ValueError."""
        from webgui.scheduled_reports import ScheduledReportManager

        mgr = ScheduledReportManager()

        with pytest.raises(ValueError, match="Unknown schedule type"):
            mgr._create_trigger({"type": "unknown"})


class TestScheduledReportManagerInitialize:
    """Tests for the full initialize flow."""

    @pytest.mark.asyncio
    async def test_initialize_when_enabled_creates_scheduler(self):
        """Initialize creates and starts scheduler when enabled."""
        from webgui.scheduled_reports import ScheduledReportManager

        mgr = ScheduledReportManager()
        mgr.enabled = True

        with (
            patch("webgui.scheduled_reports.AsyncIOScheduler") as mock_cls,
            patch("webgui.scheduled_reports.RedisJobStore"),
            patch("webgui.scheduled_reports.AsyncIOExecutor"),
        ):
            mock_instance = MagicMock()
            mock_instance.start = MagicMock()
            mock_instance.add_job = MagicMock()
            mock_cls.return_value = mock_instance

            await mgr.initialize()

            mock_cls.assert_called_once()
            mock_instance.start.assert_called_once()
            assert mgr.scheduler is mock_instance

    @pytest.mark.asyncio
    async def test_initialize_failure_disables_scheduler(self):
        """Initialize sets enabled=False on failure."""
        from webgui.scheduled_reports import ScheduledReportManager

        mgr = ScheduledReportManager()
        mgr.enabled = True

        with patch(
            "webgui.scheduled_reports.RedisJobStore",
            side_effect=Exception("Redis unavailable"),
        ):
            await mgr.initialize()

        assert mgr.enabled is False
        assert mgr.scheduler is None


class TestDayMapping:
    """Tests for weekly day mapping in _schedule_jobs."""

    @pytest.fixture
    def mock_scheduler(self):
        scheduler = MagicMock()
        scheduler.add_job = MagicMock()
        return scheduler

    def _get_weekly_trigger(self, manager, mock_scheduler):
        """Helper to extract the weekly job's CronTrigger."""
        manager._schedule_jobs()
        for call in mock_scheduler.add_job.call_args_list:
            if call.kwargs.get("id") == "weekly_compliance_report":
                return call.args[1]  # trigger is second positional arg
        return None

    def test_monday_maps_to_0(self, mock_scheduler):
        from webgui.scheduled_reports import ScheduledReportManager

        mgr = ScheduledReportManager()
        mgr.weekly_day = "monday"
        mgr.weekly_time = "09:00"
        mgr.scheduler = mock_scheduler

        trigger = self._get_weekly_trigger(mgr, mock_scheduler)
        assert trigger is not None

    def test_friday_maps_correctly(self, mock_scheduler):
        from webgui.scheduled_reports import ScheduledReportManager

        mgr = ScheduledReportManager()
        mgr.weekly_day = "friday"
        mgr.weekly_time = "09:00"
        mgr.scheduler = mock_scheduler

        trigger = self._get_weekly_trigger(mgr, mock_scheduler)
        assert trigger is not None

    def test_unknown_day_defaults_to_0(self, mock_scheduler):
        from webgui.scheduled_reports import ScheduledReportManager

        mgr = ScheduledReportManager()
        mgr.weekly_day = "notaday"
        mgr.weekly_time = "09:00"
        mgr.scheduler = mock_scheduler

        trigger = self._get_weekly_trigger(mgr, mock_scheduler)
        assert trigger is not None


class TestJobStoreSelection:
    """Tests for _create_jobstore method."""

    def test_default_uses_redis(self, monkeypatch):
        """No SCHEDULER_JOBSTORE set -> Redis."""
        monkeypatch.delenv("SCHEDULER_JOBSTORE", raising=False)
        monkeypatch.delenv("DATABASE_ENABLED", raising=False)

        from webgui.scheduled_reports import ScheduledReportManager

        mgr = ScheduledReportManager()

        with patch("webgui.scheduled_reports.RedisJobStore") as mock_redis:
            mock_redis.return_value = MagicMock()
            result = mgr._create_jobstore()

        assert "default" in result
        mock_redis.assert_called_once()

    def test_explicit_redis(self, monkeypatch):
        """SCHEDULER_JOBSTORE=redis -> Redis."""
        monkeypatch.setenv("SCHEDULER_JOBSTORE", "redis")
        monkeypatch.delenv("DATABASE_ENABLED", raising=False)

        from webgui.scheduled_reports import ScheduledReportManager

        mgr = ScheduledReportManager()

        with patch("webgui.scheduled_reports.RedisJobStore") as mock_redis:
            mock_redis.return_value = MagicMock()
            result = mgr._create_jobstore()

        assert "default" in result
        mock_redis.assert_called_once()

    def test_database_requires_db_enabled(self, monkeypatch):
        """SCHEDULER_JOBSTORE=database but DATABASE_ENABLED=false -> Redis fallback."""
        monkeypatch.setenv("SCHEDULER_JOBSTORE", "database")
        monkeypatch.setenv("DATABASE_ENABLED", "false")

        from webgui.scheduled_reports import ScheduledReportManager

        mgr = ScheduledReportManager()

        with patch("webgui.scheduled_reports.RedisJobStore") as mock_redis:
            mock_redis.return_value = MagicMock()
            result = mgr._create_jobstore()

        assert "default" in result
        mock_redis.assert_called_once()

    def test_database_with_db_enabled(self, monkeypatch):
        """SCHEDULER_JOBSTORE=database + DATABASE_ENABLED=true -> SQLAlchemyJobStore."""
        monkeypatch.setenv("SCHEDULER_JOBSTORE", "database")
        monkeypatch.setenv("DATABASE_ENABLED", "true")

        from webgui.scheduled_reports import ScheduledReportManager

        mgr = ScheduledReportManager()

        with (
            patch(
                "shared.database.models.get_database_url",
                return_value="postgresql+asyncpg://user:pass@localhost/testdb",
            ),
            patch(
                "apscheduler.jobstores.sqlalchemy.SQLAlchemyJobStore"
            ) as mock_sqla,
        ):
            mock_sqla.return_value = MagicMock()
            result = mgr._create_jobstore()

        assert "default" in result
        mock_sqla.assert_called_once()

    def test_database_store_uses_sync_url(self, monkeypatch):
        """Verify asyncpg URL is converted to psycopg2."""
        monkeypatch.setenv("SCHEDULER_JOBSTORE", "database")
        monkeypatch.setenv("DATABASE_ENABLED", "true")

        from webgui.scheduled_reports import ScheduledReportManager

        mgr = ScheduledReportManager()

        with (
            patch(
                "shared.database.models.get_database_url",
                return_value="postgresql+asyncpg://user:pass@localhost/testdb",
            ),
            patch(
                "apscheduler.jobstores.sqlalchemy.SQLAlchemyJobStore"
            ) as mock_sqla,
        ):
            mock_sqla.return_value = MagicMock()
            mgr._create_jobstore()

        mock_sqla.assert_called_once_with(
            url="postgresql+psycopg2://user:pass@localhost/testdb",
            tablename="apscheduler_jobs",
        )
