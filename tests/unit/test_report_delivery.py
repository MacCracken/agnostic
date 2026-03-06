"""Tests for scheduled report delivery channels (webhook + Slack + email)."""

import hashlib
import hmac
import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


class TestReportDeliveryService:
    """Tests for ReportDeliveryService."""

    def test_no_channels_by_default(self):
        """No delivery channels configured by default."""
        with patch.dict(os.environ, {}, clear=True):
            from webgui.scheduled_reports import ReportDeliveryService

            svc = ReportDeliveryService()
            assert svc.has_delivery_channels is False

    def test_webhook_channel_detected(self):
        """has_delivery_channels True when webhook URL set."""
        from webgui.scheduled_reports import ReportDeliveryService

        svc = ReportDeliveryService()
        svc.webhook_url = "https://example.com/hook"
        assert svc.has_delivery_channels is True

    def test_slack_channel_detected(self):
        """has_delivery_channels True when Slack URL set."""
        from webgui.scheduled_reports import ReportDeliveryService

        svc = ReportDeliveryService()
        svc.slack_webhook_url = "https://hooks.slack.com/test"
        assert svc.has_delivery_channels is True

    @pytest.mark.asyncio
    async def test_webhook_delivery_success(self):
        """Webhook delivers successfully on first attempt."""
        from webgui.scheduled_reports import ReportDeliveryService

        svc = ReportDeliveryService()
        svc.webhook_url = "https://example.com/hook"
        svc.webhook_secret = None
        svc.max_retries = 1

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        with patch("webgui.scheduled_reports.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await svc._deliver_webhook(
                {"status": "success", "report_id": "rpt-1"}, "Daily Report"
            )
            assert result == "delivered"
            mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_webhook_includes_hmac_signature(self):
        """Webhook includes X-Signature when secret is set."""
        from webgui.scheduled_reports import ReportDeliveryService

        svc = ReportDeliveryService()
        svc.webhook_url = "https://example.com/hook"
        svc.webhook_secret = "test-secret"
        svc.max_retries = 1

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        with patch("webgui.scheduled_reports.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await svc._deliver_webhook(
                {"status": "success", "report_id": "rpt-1"}, "Test"
            )

            call_kwargs = mock_client.post.call_args
            headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers")
            assert "X-Signature" in headers

            # Verify signature is valid
            body = call_kwargs.kwargs.get("content") or call_kwargs[1].get("content")
            expected_sig = hmac.new(
                b"test-secret", body.encode(), hashlib.sha256
            ).hexdigest()
            assert headers["X-Signature"] == expected_sig

    @pytest.mark.asyncio
    async def test_webhook_retries_on_failure(self):
        """Webhook retries with exponential backoff."""
        from webgui.scheduled_reports import ReportDeliveryService

        svc = ReportDeliveryService()
        svc.webhook_url = "https://example.com/hook"
        svc.webhook_secret = None
        svc.max_retries = 3

        with patch("webgui.scheduled_reports.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=Exception("connection refused"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with patch("webgui.scheduled_reports.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                result = await svc._deliver_webhook(
                    {"status": "success", "report_id": "rpt-1"}, "Test"
                )

                assert "failed" in result
                assert mock_client.post.call_count == 3
                # Exponential backoff: sleep(1), sleep(2)
                assert mock_sleep.call_count == 2

    @pytest.mark.asyncio
    async def test_slack_delivery_success(self):
        """Slack notification delivers successfully."""
        from webgui.scheduled_reports import ReportDeliveryService

        svc = ReportDeliveryService()
        svc.slack_webhook_url = "https://hooks.slack.com/test"
        svc.max_retries = 1

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        with patch("webgui.scheduled_reports.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await svc._deliver_slack(
                {"status": "success", "report_id": "rpt-1"}, "Weekly Report"
            )
            assert result == "delivered"

            # Verify Slack message format
            call_kwargs = mock_client.post.call_args
            body = json.loads(call_kwargs.kwargs.get("content") or call_kwargs[1].get("content"))
            assert "Weekly Report" in body["text"]
            assert "rpt-1" in body["text"]
            assert ":white_check_mark:" in body["text"]

    @pytest.mark.asyncio
    async def test_slack_error_report_uses_x_emoji(self):
        """Slack uses :x: emoji for failed reports."""
        from webgui.scheduled_reports import ReportDeliveryService

        svc = ReportDeliveryService()
        svc.slack_webhook_url = "https://hooks.slack.com/test"
        svc.max_retries = 1

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        with patch("webgui.scheduled_reports.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await svc._deliver_slack(
                {"status": "error", "error": "boom"}, "Failed Report"
            )

            call_kwargs = mock_client.post.call_args
            body = json.loads(call_kwargs.kwargs.get("content") or call_kwargs[1].get("content"))
            assert ":x:" in body["text"]

    @pytest.mark.asyncio
    async def test_deliver_calls_all_channels(self):
        """deliver() sends to both webhook and slack when configured."""
        from webgui.scheduled_reports import ReportDeliveryService

        svc = ReportDeliveryService()
        svc.webhook_url = "https://example.com/hook"
        svc.slack_webhook_url = "https://hooks.slack.com/test"
        svc._deliver_webhook = AsyncMock(return_value="delivered")
        svc._deliver_slack = AsyncMock(return_value="delivered")

        results = await svc.deliver(
            {"status": "success", "report_id": "rpt-1"}, "Test"
        )

        assert results["webhook"] == "delivered"
        assert results["slack"] == "delivered"
        svc._deliver_webhook.assert_called_once()
        svc._deliver_slack.assert_called_once()


class TestScheduledReportDeliveryIntegration:
    """Tests for delivery integration in ScheduledReportManager."""

    def test_manager_has_delivery_service(self):
        """ScheduledReportManager has a delivery attribute."""
        from webgui.scheduled_reports import ScheduledReportManager

        mgr = ScheduledReportManager()
        assert hasattr(mgr, "delivery")
        assert hasattr(mgr.delivery, "deliver")

    @pytest.mark.asyncio
    async def test_generate_and_deliver_calls_delivery(self):
        """_generate_and_deliver sends to delivery channels."""
        from webgui.scheduled_reports import ScheduledReportManager

        mgr = ScheduledReportManager()
        mgr.delivery = MagicMock()
        mgr.delivery.has_delivery_channels = True
        mgr.delivery.deliver = AsyncMock(return_value={"webhook": "delivered"})

        mock_metadata = MagicMock()
        mock_metadata.report_id = "rpt-test"

        mock_exports = MagicMock()
        mock_exports.ReportFormat.return_value = "pdf"
        mock_exports.ReportType.return_value = "comprehensive"
        mock_exports.ReportRequest = MagicMock
        mock_exports.report_generator.generate_report = AsyncMock(return_value=mock_metadata)

        with patch.dict("sys.modules", {"webgui.exports": mock_exports}):
            result = await mgr._generate_and_deliver(
                "Test Report", "comprehensive", "pdf", "test"
            )

        assert result["status"] == "success"
        mgr.delivery.deliver.assert_called_once()

    @pytest.mark.asyncio
    async def test_schedule_custom_report_accepts_tenant_id(self):
        """schedule_custom_report includes tenant_id in job_id."""
        from webgui.scheduled_reports import ScheduledReportManager

        mgr = ScheduledReportManager()
        mgr.scheduler = MagicMock()

        mock_exports = MagicMock()
        with patch.dict("sys.modules", {"webgui.exports": mock_exports}):
            job_id = await mgr.schedule_custom_report(
                report_type="comprehensive",
                format="pdf",
                schedule={"type": "cron", "hour": 9},
                tenant_id="acme",
            )

        assert "tenant_acme" in job_id
        mgr.scheduler.add_job.assert_called_once()

    @pytest.mark.asyncio
    async def test_schedule_custom_report_without_tenant(self):
        """schedule_custom_report works without tenant_id."""
        from webgui.scheduled_reports import ScheduledReportManager

        mgr = ScheduledReportManager()
        mgr.scheduler = MagicMock()

        mock_exports = MagicMock()
        with patch.dict("sys.modules", {"webgui.exports": mock_exports}):
            job_id = await mgr.schedule_custom_report(
                report_type="comprehensive",
                format="pdf",
                schedule={"type": "cron", "hour": 9},
            )

        assert "tenant_" not in job_id


class TestEmailDelivery:
    """Tests for email delivery channel."""

    def test_email_not_enabled_by_default(self):
        """Email delivery is disabled by default."""
        with patch.dict(os.environ, {}, clear=True):
            from webgui.scheduled_reports import ReportDeliveryService

            svc = ReportDeliveryService()
            assert svc.email_enabled is False
            assert svc.has_delivery_channels is False

    def test_email_enabled_with_recipients(self):
        """has_delivery_channels True when email enabled with recipients."""
        from webgui.scheduled_reports import ReportDeliveryService

        svc = ReportDeliveryService()
        svc.email_enabled = True
        svc.email_recipients = ["test@example.com"]
        svc.webhook_url = None
        svc.slack_webhook_url = None
        assert svc.has_delivery_channels is True

    @pytest.mark.asyncio
    async def test_deliver_email_success(self):
        """Email delivers successfully on first attempt."""
        from webgui.scheduled_reports import ReportDeliveryService

        svc = ReportDeliveryService()
        svc.email_enabled = True
        svc.smtp_host = "smtp.example.com"
        svc.smtp_port = 587
        svc.smtp_from = "reports@example.com"
        svc.email_recipients = ["user@example.com", "admin@example.com"]
        svc.smtp_username = "user"
        svc.smtp_password = "pass"
        svc.smtp_use_tls = True
        svc.max_retries = 1

        with patch("webgui.scheduled_reports.aiosmtplib.SMTP") as mock_smtp_cls:
            mock_smtp = AsyncMock()
            mock_smtp_cls.return_value = mock_smtp

            result = await svc._deliver_email(
                {"status": "success", "report_id": "rpt-1"}, "Daily Report"
            )

            assert result == "delivered"
            mock_smtp.connect.assert_called_once()
            mock_smtp.login.assert_called_once_with("user", "pass")
            mock_smtp.send_message.assert_called_once()
            mock_smtp.quit.assert_called_once()

            # Verify from/to/subject
            sent_msg = mock_smtp.send_message.call_args[0][0]
            assert sent_msg["From"] == "reports@example.com"
            assert "user@example.com" in sent_msg["To"]
            assert "admin@example.com" in sent_msg["To"]
            assert "Daily Report" in sent_msg["Subject"]
            assert "success" in sent_msg["Subject"]

    @pytest.mark.asyncio
    async def test_deliver_email_retry_on_failure(self):
        """Email retries with exponential backoff then succeeds."""
        from webgui.scheduled_reports import ReportDeliveryService

        svc = ReportDeliveryService()
        svc.email_enabled = True
        svc.smtp_host = "smtp.example.com"
        svc.smtp_port = 587
        svc.smtp_from = "reports@example.com"
        svc.email_recipients = ["user@example.com"]
        svc.smtp_username = ""
        svc.smtp_password = ""
        svc.smtp_use_tls = True
        svc.max_retries = 3

        with patch("webgui.scheduled_reports.aiosmtplib.SMTP") as mock_smtp_cls:
            mock_smtp_fail = AsyncMock()
            mock_smtp_fail.connect = AsyncMock(side_effect=Exception("connection refused"))

            mock_smtp_ok = AsyncMock()
            mock_smtp_ok.connect = AsyncMock()
            mock_smtp_ok.send_message = AsyncMock()
            mock_smtp_ok.quit = AsyncMock()

            mock_smtp_cls.side_effect = [mock_smtp_fail, mock_smtp_ok]

            with patch("webgui.scheduled_reports.asyncio.sleep", new_callable=AsyncMock):
                result = await svc._deliver_email(
                    {"status": "success", "report_id": "rpt-1"}, "Test"
                )

            assert result == "delivered"

    @pytest.mark.asyncio
    async def test_deliver_email_all_retries_exhausted(self):
        """Email returns failed after all retries exhausted."""
        from webgui.scheduled_reports import ReportDeliveryService

        svc = ReportDeliveryService()
        svc.email_enabled = True
        svc.smtp_host = "smtp.example.com"
        svc.smtp_port = 587
        svc.smtp_from = "reports@example.com"
        svc.email_recipients = ["user@example.com"]
        svc.smtp_username = ""
        svc.smtp_password = ""
        svc.smtp_use_tls = True
        svc.max_retries = 2

        with patch("webgui.scheduled_reports.aiosmtplib.SMTP") as mock_smtp_cls:
            mock_smtp = AsyncMock()
            mock_smtp.connect = AsyncMock(side_effect=Exception("connection refused"))
            mock_smtp_cls.return_value = mock_smtp

            with patch("webgui.scheduled_reports.asyncio.sleep", new_callable=AsyncMock):
                result = await svc._deliver_email(
                    {"status": "success", "report_id": "rpt-1"}, "Test"
                )

            assert result.startswith("failed:")

    @pytest.mark.asyncio
    async def test_deliver_email_html_body_contains_report_info(self):
        """Email HTML body includes job_name, report_id, and status."""
        from webgui.scheduled_reports import ReportDeliveryService

        svc = ReportDeliveryService()
        svc.email_enabled = True
        svc.smtp_host = "smtp.example.com"
        svc.smtp_port = 587
        svc.smtp_from = "reports@example.com"
        svc.email_recipients = ["user@example.com"]
        svc.smtp_username = ""
        svc.smtp_password = ""
        svc.smtp_use_tls = True
        svc.max_retries = 1

        with patch("webgui.scheduled_reports.aiosmtplib.SMTP") as mock_smtp_cls:
            mock_smtp = AsyncMock()
            mock_smtp_cls.return_value = mock_smtp

            await svc._deliver_email(
                {"status": "success", "report_id": "rpt-42"}, "Weekly Compliance"
            )

            sent_msg = mock_smtp.send_message.call_args[0][0]
            # Extract HTML payload from the MIMEMultipart message
            html_part = sent_msg.get_payload()[0].get_payload()
            assert "Weekly Compliance" in html_part
            assert "rpt-42" in html_part
            assert "success" in html_part

    @pytest.mark.asyncio
    async def test_deliver_includes_email_channel(self):
        """deliver() sends to all three channels when all configured."""
        from webgui.scheduled_reports import ReportDeliveryService

        svc = ReportDeliveryService()
        svc.webhook_url = "https://example.com/hook"
        svc.slack_webhook_url = "https://hooks.slack.com/test"
        svc.email_enabled = True
        svc.email_recipients = ["user@example.com"]
        svc._deliver_webhook = AsyncMock(return_value="delivered")
        svc._deliver_slack = AsyncMock(return_value="delivered")
        svc._deliver_email = AsyncMock(return_value="delivered")

        results = await svc.deliver(
            {"status": "success", "report_id": "rpt-1"}, "Test"
        )

        assert results["webhook"] == "delivered"
        assert results["slack"] == "delivered"
        assert results["email"] == "delivered"
        svc._deliver_webhook.assert_called_once()
        svc._deliver_slack.assert_called_once()
        svc._deliver_email.assert_called_once()
