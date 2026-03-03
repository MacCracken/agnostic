"""
Scheduled Report Generation Module

Provides APScheduler-based periodic report generation for:
- Daily executive summary
- Weekly compliance report
- Custom scheduled reports

Configured via environment variables:
- SCHEDULED_REPORTS_ENABLED: Enable/disable scheduled reports (default: false)
- SCHEDULED_REPORT_DAILY_TIME: Time for daily reports (default: "09:00")
- SCHEDULED_REPORT_WEEKLY_DAY: Day of week for weekly reports (default: "monday")
- SCHEDULED_REPORT_WEEKLY_TIME: Time for weekly reports (default: "09:00")
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any

from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.jobstores.redis import RedisJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from pytz import timezone as pytz_timezone

logger = logging.getLogger(__name__)


class ScheduledReportManager:
    """Manages scheduled report generation jobs."""

    def __init__(self):
        self.scheduler: AsyncIOScheduler | None = None
        self.enabled = os.getenv("SCHEDULED_REPORTS_ENABLED", "false").lower() == "true"
        self.daily_time = os.getenv("SCHEDULED_REPORT_DAILY_TIME", "09:00")
        self.weekly_day = os.getenv("SCHEDULED_REPORT_WEEKLY_DAY", "monday")
        self.weekly_time = os.getenv("SCHEDULED_REPORT_WEEKLY_TIME", "09:00")

    async def initialize(self) -> None:
        """Initialize the APScheduler."""
        if not self.enabled:
            logger.info("Scheduled reports are disabled")
            return

        try:
            jobstores = {
                "default": RedisJobStore(
                    host=os.getenv("REDIS_HOST", "localhost"),
                    port=int(os.getenv("REDIS_PORT", "6379")),
                    db=int(os.getenv("REDIS_SCHEDULER_DB", "1")),
                    prefix="scheduled_reports",
                )
            }

            executors = {
                "default": AsyncIOExecutor(),
            }

            job_defaults = {
                "coalesce": True,
                "max_instances": 1,
                "misfire_grace_time": 300,
            }

            self.scheduler = AsyncIOScheduler(
                jobstores=jobstores,
                executors=executors,
                job_defaults=job_defaults,
                timezone=pytz_timezone(os.getenv("TZ", "UTC")),
            )

            self._schedule_jobs()
            self.scheduler.start()
            logger.info(
                f"Scheduled reports initialized: daily at {self.daily_time}, "
                f"weekly on {self.weekly_day} at {self.weekly_time}"
            )

        except Exception as e:
            logger.error(f"Failed to initialize scheduled reports: {e}")
            self.enabled = False

    def _schedule_jobs(self) -> None:
        """Schedule the default report jobs."""
        if not self.scheduler:
            return

        hour, minute = map(int, self.daily_time.split(":"))

        self.scheduler.add_job(
            self._generate_daily_summary,
            CronTrigger(hour=hour, minute=minute),
            id="daily_executive_summary",
            name="Daily Executive Summary",
            replace_existing=True,
        )

        day_map = {
            "monday": 0,
            "tuesday": 1,
            "wednesday": 2,
            "thursday": 3,
            "friday": 4,
            "saturday": 5,
            "sunday": 6,
        }
        weekly_day = day_map.get(self.weekly_day.lower(), 0)
        hour, minute = map(int, self.weekly_time.split(":"))

        self.scheduler.add_job(
            self._generate_weekly_compliance,
            CronTrigger(day_of_week=weekly_day, hour=hour, minute=minute),
            id="weekly_compliance_report",
            name="Weekly Compliance Report",
            replace_existing=True,
        )

    async def _generate_daily_summary(self) -> dict[str, Any]:
        """Generate daily executive summary report."""
        logger.info("Generating daily executive summary report")
        try:
            from webgui.exports import (
                ReportFormat,
                ReportRequest,
                ReportType,
                report_generator,
            )

            report_req = ReportRequest(
                session_id="",
                report_type=ReportType.COMPREHENSIVE,
                format=ReportFormat.PDF,
            )

            metadata = await report_generator.generate_report(
                report_req, "scheduler:daily"
            )

            logger.info(
                f"Daily summary report generated: {metadata.report_id}"
            )
            return {"status": "success", "report_id": metadata.report_id}

        except Exception as e:
            logger.error(f"Failed to generate daily summary: {e}")
            return {"status": "error", "error": str(e)}

    async def _generate_weekly_compliance(self) -> dict[str, Any]:
        """Generate weekly compliance report."""
        logger.info("Generating weekly compliance report")
        try:
            from webgui.exports import (
                ReportFormat,
                ReportRequest,
                ReportType,
                report_generator,
            )

            report_req = ReportRequest(
                session_id="",
                report_type=ReportType.COMPLIANCE,
                format=ReportFormat.PDF,
            )

            metadata = await report_generator.generate_report(
                report_req, "scheduler:weekly"
            )

            logger.info(
                f"Weekly compliance report generated: {metadata.report_id}"
            )
            return {"status": "success", "report_id": metadata.report_id}

        except Exception as e:
            logger.error(f"Failed to generate weekly compliance: {e}")
            return {"status": "error", "error": str(e)}

    async def schedule_custom_report(
        self,
        report_type: str,
        format: str,
        schedule: dict[str, Any],
        report_name: str | None = None,
    ) -> str:
        """Schedule a custom report job.

        Args:
            report_type: Type of report (comprehensive, compliance, security, performance)
            format: Output format (pdf, json, csv)
            schedule: Schedule configuration with 'type' (cron, interval, date)
                      and parameters for the trigger
            report_name: Optional name for the job

        Returns:
            Job ID
        """
        if not self.scheduler:
            raise RuntimeError("Scheduler not initialized")

        job_id = f"custom_{report_type}_{datetime.now().timestamp()}"

        from webgui.exports import ReportFormat, ReportType

        try:
            report_type_enum = ReportType(report_type)
            format_enum = ReportFormat(format)
        except ValueError as e:
            raise ValueError(f"Invalid report type or format: {e}") from e

        async def generate_custom_report():
            from webgui.exports import (
                ReportRequest,
                report_generator,
            )

            report_req = ReportRequest(
                session_id="",
                report_type=report_type_enum,
                format=format_enum,
            )
            return await report_generator.generate_report(
                report_req, f"scheduler:{job_id}"
            )

        trigger = self._create_trigger(schedule)

        self.scheduler.add_job(
            generate_custom_report,
            trigger=trigger,
            id=job_id,
            name=report_name or f"Custom {report_type} report",
            replace_existing=True,
        )

        logger.info(f"Scheduled custom report: {job_id}")
        return job_id

    def _create_trigger(self, schedule: dict[str, Any]):
        """Create APScheduler trigger from schedule config."""
        schedule_type = schedule.get("type", "cron")

        if schedule_type == "cron":
            return CronTrigger(
                year=schedule.get("year"),
                month=schedule.get("month"),
                day=schedule.get("day"),
                hour=schedule.get("hour"),
                minute=schedule.get("minute"),
                day_of_week=schedule.get("day_of_week"),
            )
        elif schedule_type == "interval":
            return DateTrigger(
                run_date=datetime.fromisoformat(schedule["run_at"])
            )
        else:
            raise ValueError(f"Unknown schedule type: {schedule_type}")

    def get_jobs(self) -> list[dict[str, Any]]:
        """Get list of scheduled jobs."""
        if not self.scheduler:
            return []

        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append(
                {
                    "id": job.id,
                    "name": job.name,
                    "next_run": (
                        job.next_run_time.isoformat() if job.next_run_time else None
                    ),
                    "trigger": str(job.trigger),
                }
            )
        return jobs

    def remove_job(self, job_id: str) -> bool:
        """Remove a scheduled job."""
        if not self.scheduler:
            return False

        try:
            self.scheduler.remove_job(job_id)
            logger.info(f"Removed scheduled job: {job_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to remove job {job_id}: {e}")
            return False

    async def shutdown(self) -> None:
        """Shutdown the scheduler."""
        if self.scheduler:
            self.scheduler.shutdown()
            logger.info("Scheduled reports shutdown")


scheduled_report_manager = ScheduledReportManager()
