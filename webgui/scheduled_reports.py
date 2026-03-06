"""
Scheduled Report Generation Module

Provides APScheduler-based periodic report generation for:
- Daily executive summary
- Weekly compliance report
- Custom scheduled reports

Report delivery channels:
- Webhook (HTTP POST with optional HMAC-SHA256 signature)
- Slack (incoming webhook URL)
- Email (SMTP with TLS support)

Configured via environment variables:
- SCHEDULED_REPORTS_ENABLED: Enable/disable scheduled reports (default: false)
- SCHEDULED_REPORT_DAILY_TIME: Time for daily reports (default: "09:00")
- SCHEDULED_REPORT_WEEKLY_DAY: Day of week for weekly reports (default: "monday")
- SCHEDULED_REPORT_WEEKLY_TIME: Time for weekly reports (default: "09:00")
- REPORT_WEBHOOK_URL: Webhook URL for report delivery notifications
- REPORT_WEBHOOK_SECRET: HMAC-SHA256 secret for webhook signatures
- REPORT_SLACK_WEBHOOK_URL: Slack incoming webhook URL for report notifications
- REPORT_EMAIL_ENABLED: Enable email delivery (default: false)
- SMTP_HOST: SMTP server hostname
- SMTP_PORT: SMTP server port (default: 587)
- SMTP_USERNAME: SMTP authentication username
- SMTP_PASSWORD: SMTP authentication password
- SMTP_USE_TLS: Use TLS for SMTP (default: true)
- SMTP_FROM: Sender email address
- REPORT_EMAIL_RECIPIENTS: Comma-separated list of recipient email addresses
"""

import asyncio
import hashlib
import hmac
import json
import logging
import os
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import aiosmtplib
import httpx
from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.jobstores.redis import RedisJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from pytz import timezone as pytz_timezone

logger = logging.getLogger(__name__)


class ReportDeliveryService:
    """Delivers report notifications via webhook, Slack, and email."""

    def __init__(self):
        self.webhook_url = os.getenv("REPORT_WEBHOOK_URL")
        self.webhook_secret = os.getenv("REPORT_WEBHOOK_SECRET")
        self.slack_webhook_url = os.getenv("REPORT_SLACK_WEBHOOK_URL")
        self.max_retries = int(os.getenv("REPORT_DELIVERY_MAX_RETRIES", "3"))
        self.email_enabled = os.getenv("REPORT_EMAIL_ENABLED", "false").lower() == "true"
        self.smtp_host = os.getenv("SMTP_HOST", "")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_username = os.getenv("SMTP_USERNAME", "")
        self.smtp_password = os.getenv("SMTP_PASSWORD", "")
        self.smtp_use_tls = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
        self.smtp_from = os.getenv("SMTP_FROM", "")
        self.email_recipients = [r.strip() for r in os.getenv("REPORT_EMAIL_RECIPIENTS", "").split(",") if r.strip()]

    @property
    def has_delivery_channels(self) -> bool:
        return bool(self.webhook_url or self.slack_webhook_url or (self.email_enabled and self.email_recipients))

    async def deliver(self, report_result: dict[str, Any], job_name: str) -> dict[str, Any]:
        """Deliver report notification to all configured channels.

        Returns dict with delivery status per channel.
        """
        results: dict[str, Any] = {}

        if self.webhook_url:
            results["webhook"] = await self._deliver_webhook(report_result, job_name)

        if self.slack_webhook_url:
            results["slack"] = await self._deliver_slack(report_result, job_name)

        if self.email_enabled and self.email_recipients:
            results["email"] = await self._deliver_email(report_result, job_name)

        return results

    async def _deliver_webhook(self, report_result: dict[str, Any], job_name: str) -> str:
        """POST report notification to webhook URL with optional HMAC signature."""
        payload = {
            "event": "report.generated",
            "job_name": job_name,
            "report_id": report_result.get("report_id"),
            "status": report_result.get("status"),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        body = json.dumps(payload)
        headers = {"Content-Type": "application/json"}

        if self.webhook_secret:
            signature = hmac.new(
                self.webhook_secret.encode(), body.encode(), hashlib.sha256
            ).hexdigest()
            headers["X-Signature"] = signature

        last_error = None
        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.post(self.webhook_url, content=body, headers=headers)
                    resp.raise_for_status()
                logger.info(f"Report webhook delivered for {job_name}")
                return "delivered"
            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2**attempt)

        logger.error(f"Report webhook failed after {self.max_retries} attempts: {last_error}")
        return f"failed: {last_error}"

    async def _deliver_slack(self, report_result: dict[str, Any], job_name: str) -> str:
        """POST report notification to Slack incoming webhook."""
        report_id = report_result.get("report_id", "unknown")
        status = report_result.get("status", "unknown")
        status_emoji = ":white_check_mark:" if status == "success" else ":x:"

        payload = {
            "text": f"{status_emoji} *Scheduled Report: {job_name}*\n"
                    f"Status: {status}\n"
                    f"Report ID: `{report_id}`\n"
                    f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        }

        last_error = None
        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.post(
                        self.slack_webhook_url,
                        content=json.dumps(payload),
                        headers={"Content-Type": "application/json"},
                    )
                    resp.raise_for_status()
                logger.info(f"Slack notification delivered for {job_name}")
                return "delivered"
            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2**attempt)

        logger.error(f"Slack delivery failed after {self.max_retries} attempts: {last_error}")
        return f"failed: {last_error}"

    async def _deliver_email(self, report_result: dict[str, Any], job_name: str) -> str:
        """Send report notification via SMTP email."""
        report_id = report_result.get("report_id", "unknown")
        status = report_result.get("status", "unknown")
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"Scheduled Report: {job_name} - {status}"
        msg["From"] = self.smtp_from
        msg["To"] = ", ".join(self.email_recipients)

        html_body = (
            "<html><body>"
            f"<h2>Scheduled Report: {job_name}</h2>"
            f"<p><strong>Status:</strong> {status}</p>"
            f"<p><strong>Report ID:</strong> {report_id}</p>"
            f"<p><strong>Generated:</strong> {timestamp}</p>"
            "</body></html>"
        )
        msg.attach(MIMEText(html_body, "html"))

        last_error = None
        for attempt in range(self.max_retries):
            try:
                smtp = aiosmtplib.SMTP(
                    hostname=self.smtp_host,
                    port=self.smtp_port,
                    use_tls=self.smtp_use_tls,
                )
                await smtp.connect()
                if self.smtp_username and self.smtp_password:
                    await smtp.login(self.smtp_username, self.smtp_password)
                await smtp.send_message(msg)
                await smtp.quit()
                logger.info(f"Email notification delivered for {job_name}")
                return "delivered"
            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2**attempt)

        logger.error(f"Email delivery failed after {self.max_retries} attempts: {last_error}")
        return f"failed: {last_error}"


class ScheduledReportManager:
    """Manages scheduled report generation jobs."""

    def __init__(self):
        self.scheduler: AsyncIOScheduler | None = None
        self.enabled = os.getenv("SCHEDULED_REPORTS_ENABLED", "false").lower() == "true"
        self.daily_time = os.getenv("SCHEDULED_REPORT_DAILY_TIME", "09:00")
        self.weekly_day = os.getenv("SCHEDULED_REPORT_WEEKLY_DAY", "monday")
        self.weekly_time = os.getenv("SCHEDULED_REPORT_WEEKLY_TIME", "09:00")
        self.delivery = ReportDeliveryService()

    def _create_jobstore(self) -> dict:
        """Create job store -- database-backed if configured, Redis otherwise."""
        store_type = os.getenv("SCHEDULER_JOBSTORE", "redis")
        db_enabled = os.getenv("DATABASE_ENABLED", "false").lower() == "true"

        if store_type == "database" and db_enabled:
            from shared.database.models import get_database_url

            # APScheduler's SQLAlchemyJobStore needs a sync URL
            sync_url = get_database_url().replace(
                "postgresql+asyncpg://", "postgresql+psycopg2://"
            )
            from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

            logger.info("Using database-backed job store")
            return {
                "default": SQLAlchemyJobStore(
                    url=sync_url,
                    tablename="apscheduler_jobs",
                )
            }

        logger.info("Using Redis job store")
        return {
            "default": RedisJobStore(
                host=os.getenv("REDIS_HOST", "localhost"),
                port=int(os.getenv("REDIS_PORT", "6379")),
                db=int(os.getenv("REDIS_SCHEDULER_DB", "1")),
                prefix="scheduled_reports",
            )
        }

    async def initialize(self) -> None:
        """Initialize the APScheduler."""
        if not self.enabled:
            logger.info("Scheduled reports are disabled")
            return

        try:
            jobstores = self._create_jobstore()

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
            if self.delivery.has_delivery_channels:
                logger.info("Report delivery channels configured")

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

    async def _generate_and_deliver(
        self, report_type_name: str, report_type_val: str, format_val: str, job_name: str
    ) -> dict[str, Any]:
        """Generate a report and deliver via configured channels."""
        logger.info(f"Generating {report_type_name}")
        try:
            from webgui.exports import (
                ReportFormat,
                ReportRequest,
                ReportType,
                report_generator,
            )

            report_req = ReportRequest(
                session_id="",
                report_type=ReportType(report_type_val),
                format=ReportFormat(format_val),
            )

            metadata = await report_generator.generate_report(report_req, f"scheduler:{job_name}")

            result = {"status": "success", "report_id": metadata.report_id}
            logger.info(f"{report_type_name} generated: {metadata.report_id}")

            # Deliver to configured channels
            if self.delivery.has_delivery_channels:
                delivery_results = await self.delivery.deliver(result, report_type_name)
                result["delivery"] = delivery_results

            return result

        except Exception as e:
            logger.error(f"Failed to generate {report_type_name}: {e}")
            result = {"status": "error", "error": str(e)}

            # Notify delivery channels about failure too
            if self.delivery.has_delivery_channels:
                try:
                    delivery_results = await self.delivery.deliver(result, report_type_name)
                    result["delivery"] = delivery_results
                except Exception as de:
                    logger.error(f"Delivery notification also failed: {de}")

            return result

    async def _generate_daily_summary(self) -> dict[str, Any]:
        """Generate daily executive summary report."""
        return await self._generate_and_deliver(
            "Daily Executive Summary", "comprehensive", "pdf", "daily"
        )

    async def _generate_weekly_compliance(self) -> dict[str, Any]:
        """Generate weekly compliance report."""
        return await self._generate_and_deliver(
            "Weekly Compliance Report", "compliance", "pdf", "weekly"
        )

    async def schedule_custom_report(
        self,
        report_type: str,
        format: str,
        schedule: dict[str, Any],
        report_name: str | None = None,
        tenant_id: str | None = None,
    ) -> str:
        """Schedule a custom report job.

        Args:
            report_type: Type of report (comprehensive, compliance, security, performance)
            format: Output format (pdf, json, csv)
            schedule: Schedule configuration with 'type' (cron, interval, date)
                      and parameters for the trigger
            report_name: Optional name for the job
            tenant_id: Optional tenant ID for tenant-scoped reports

        Returns:
            Job ID
        """
        if not self.scheduler:
            raise RuntimeError("Scheduler not initialized")

        prefix = f"tenant_{tenant_id}_" if tenant_id else ""
        job_id = f"custom_{prefix}{report_type}_{datetime.now().timestamp()}"

        from webgui.exports import ReportFormat, ReportType

        try:
            report_type_enum = ReportType(report_type)
            format_enum = ReportFormat(format)
        except ValueError as e:
            raise ValueError(f"Invalid report type or format: {e}") from e

        display_name = report_name or f"Custom {report_type} report"
        delivery = self.delivery

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
            try:
                metadata = await report_generator.generate_report(
                    report_req, f"scheduler:{job_id}"
                )
                result = {"status": "success", "report_id": metadata.report_id}
            except Exception as e:
                result = {"status": "error", "error": str(e)}

            if delivery.has_delivery_channels:
                await delivery.deliver(result, display_name)

            return result

        trigger = self._create_trigger(schedule)

        self.scheduler.add_job(
            generate_custom_report,
            trigger=trigger,
            id=job_id,
            name=display_name,
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
