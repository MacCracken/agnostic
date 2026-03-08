"""
Real-time alert system for the Agentic QA platform.

Fires alerts on agent failures, circuit breaker trips, and degraded health.
Delivers via webhook, Slack, and email (reuses delivery config from
scheduled reports).  A background monitor polls health state periodically.

Configure via environment variables:
- ALERTS_ENABLED: Enable alert system (default: false)
- ALERT_POLL_INTERVAL_SECONDS: Health poll interval (default: 30)
- ALERT_COOLDOWN_SECONDS: Min seconds between repeated alerts of same type (default: 300)
- ALERT_WEBHOOK_URL: Webhook URL (falls back to REPORT_WEBHOOK_URL)
- ALERT_SLACK_WEBHOOK_URL: Slack URL (falls back to REPORT_SLACK_WEBHOOK_URL)
- ALERT_EMAIL_RECIPIENTS: Comma-separated (falls back to REPORT_EMAIL_RECIPIENTS)
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac as hmac_mod
import json
import logging
import os
import time
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Alert types & severity
# ---------------------------------------------------------------------------


class AlertSeverity(StrEnum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class AlertType(StrEnum):
    HEALTH_DEGRADED = "health.degraded"
    HEALTH_UNHEALTHY = "health.unhealthy"
    HEALTH_RECOVERED = "health.recovered"
    AGENT_OFFLINE = "agent.offline"
    AGENT_STALE = "agent.stale"
    CIRCUIT_BREAKER_OPEN = "circuit_breaker.open"
    CIRCUIT_BREAKER_RECOVERED = "circuit_breaker.recovered"
    TASK_FAILED = "task.failed"


# ---------------------------------------------------------------------------
# Alert manager
# ---------------------------------------------------------------------------

ALERTS_ENABLED = os.getenv("ALERTS_ENABLED", "false").lower() == "true"

_COOLDOWN_MAX_ENTRIES = 5_000
_COOLDOWN_EVICT_AGE = 7200  # Remove entries older than 2 hours


class AlertManager:
    """Manages alert delivery with cooldown throttling."""

    def __init__(self, *, enabled: bool | None = None) -> None:
        self.enabled = enabled if enabled is not None else ALERTS_ENABLED
        self.webhook_url = os.getenv(
            "ALERT_WEBHOOK_URL", os.getenv("REPORT_WEBHOOK_URL", "")
        )
        self.webhook_secret = os.getenv(
            "ALERT_WEBHOOK_SECRET", os.getenv("REPORT_WEBHOOK_SECRET", "")
        )
        self.slack_webhook_url = os.getenv(
            "ALERT_SLACK_WEBHOOK_URL", os.getenv("REPORT_SLACK_WEBHOOK_URL", "")
        )
        self.email_recipients = [
            r.strip()
            for r in os.getenv(
                "ALERT_EMAIL_RECIPIENTS",
                os.getenv("REPORT_EMAIL_RECIPIENTS", ""),
            ).split(",")
            if r.strip()
        ]
        self.cooldown_seconds = int(os.getenv("ALERT_COOLDOWN_SECONDS", "300"))
        self.max_retries = int(os.getenv("ALERT_DELIVERY_MAX_RETRIES", "3"))

        # Tracks last alert time per (alert_type, context_key) to avoid storms
        self._last_fired: dict[str, float] = {}

        # Shared httpx client (created lazily)
        self._http_client: Any = None

    async def _get_http_client(self) -> Any:
        """Return a shared httpx.AsyncClient, created on first use."""
        if self._http_client is None or self._http_client.is_closed:
            import httpx

            self._http_client = httpx.AsyncClient(timeout=10)
        return self._http_client

    async def close(self) -> None:
        """Close the shared HTTP client."""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
            self._http_client = None

    @property
    def has_channels(self) -> bool:
        return bool(self.webhook_url or self.slack_webhook_url or self.email_recipients)

    def _evict_stale_cooldowns(self) -> None:
        """Remove old cooldown entries to prevent unbounded growth."""
        now = time.monotonic()
        cutoff = now - _COOLDOWN_EVICT_AGE
        stale = [k for k, v in self._last_fired.items() if v < cutoff]
        for k in stale:
            del self._last_fired[k]

    async def fire(
        self,
        alert_type: AlertType,
        severity: AlertSeverity,
        title: str,
        message: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Send an alert if not in cooldown.

        Returns delivery results dict, or None if suppressed by cooldown.
        """
        if not self.enabled:
            return None

        # Cooldown check
        cooldown_key = f"{alert_type}:{json.dumps(context or {}, sort_keys=True)}"
        now = time.monotonic()
        last = self._last_fired.get(cooldown_key, 0.0)
        if now - last < self.cooldown_seconds:
            logger.debug("Alert suppressed (cooldown): %s", alert_type)
            return None

        self._last_fired[cooldown_key] = now

        # Proactive eviction: run every 100 entries or when exceeding hard cap
        if (
            len(self._last_fired) % 100 == 0
            or len(self._last_fired) > _COOLDOWN_MAX_ENTRIES
        ):
            self._evict_stale_cooldowns()
            # Hard-cap: if still too large after eviction, drop oldest entries
            if len(self._last_fired) > _COOLDOWN_MAX_ENTRIES:
                sorted_keys = sorted(self._last_fired, key=self._last_fired.get)
                for k in sorted_keys[: len(self._last_fired) - _COOLDOWN_MAX_ENTRIES]:
                    del self._last_fired[k]

        payload = {
            "event": "alert",
            "alert_type": str(alert_type),
            "severity": str(severity),
            "title": title,
            "message": message,
            "timestamp": datetime.now(UTC).isoformat(),
            "context": context or {},
        }

        # Attach correlation ID if available
        try:
            from webgui.app import correlation_id_ctx

            cid = correlation_id_ctx.get()
            if cid:
                payload["correlation_id"] = cid
        except (ImportError, LookupError):
            pass

        results: dict[str, Any] = {}
        if self.webhook_url:
            results["webhook"] = await self._deliver_webhook(payload)
        if self.slack_webhook_url:
            results["slack"] = await self._deliver_slack(payload)
        if self.email_recipients:
            results["email"] = await self._deliver_email(payload)

        # Publish to Redis pub/sub for WebSocket clients + persist to stream
        try:
            from config.environment import config

            redis_client = config.get_redis_client()
            redis_client.publish("webgui:alerts", json.dumps(payload))
            # Persist to stream for query endpoint (capped at 1000 entries)
            redis_client.xadd(
                "stream:webgui:alerts",
                {"data": json.dumps(payload)},
                maxlen=1000,
            )
        except Exception:
            logger.debug("Failed to publish alert to Redis")

        logger.info("Alert fired: [%s] %s - %s", severity, alert_type, title)
        return results

    async def _deliver_webhook(self, payload: dict[str, Any]) -> str:
        client = await self._get_http_client()
        body = json.dumps(payload)
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.webhook_secret:
            sig = hmac_mod.new(
                self.webhook_secret.encode(), body.encode(), hashlib.sha256
            ).hexdigest()
            headers["X-Signature"] = sig

        last_error = None
        for attempt in range(self.max_retries):
            try:
                resp = await client.post(
                    self.webhook_url, content=body, headers=headers
                )
                resp.raise_for_status()
                return "delivered"
            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2**attempt)
        return f"failed: {last_error}"

    async def _deliver_slack(self, payload: dict[str, Any]) -> str:
        client = await self._get_http_client()
        severity = payload.get("severity", "info")
        emoji = {
            "critical": ":rotating_light:",
            "warning": ":warning:",
            "info": ":information_source:",
        }.get(severity, ":bell:")

        slack_payload = {
            "text": (
                f"{emoji} *[{severity.upper()}] {payload['title']}*\n"
                f"{payload['message']}\n"
                f"Type: `{payload['alert_type']}`  |  {payload['timestamp']}"
            ),
        }

        last_error = None
        for attempt in range(self.max_retries):
            try:
                resp = await client.post(
                    self.slack_webhook_url,
                    content=json.dumps(slack_payload),
                    headers={"Content-Type": "application/json"},
                )
                resp.raise_for_status()
                return "delivered"
            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2**attempt)
        return f"failed: {last_error}"

    async def _deliver_email(self, payload: dict[str, Any]) -> str:
        try:
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText

            import aiosmtplib
        except ImportError:
            return "skipped: aiosmtplib not installed"

        smtp_host = os.getenv("SMTP_HOST", "")
        if not smtp_host:
            return "skipped: SMTP_HOST not configured"

        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        smtp_user = os.getenv("SMTP_USERNAME", "")
        smtp_pass = os.getenv("SMTP_PASSWORD", "")
        smtp_tls = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
        smtp_from = os.getenv("SMTP_FROM", "")

        severity = payload.get("severity", "info")
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"[{severity.upper()}] {payload['title']}"
        msg["From"] = smtp_from
        msg["To"] = ", ".join(self.email_recipients)

        html = (
            "<html><body>"
            f"<h2>{payload['title']}</h2>"
            f"<p>{payload['message']}</p>"
            f"<p><strong>Severity:</strong> {severity}</p>"
            f"<p><strong>Type:</strong> {payload['alert_type']}</p>"
            f"<p><strong>Time:</strong> {payload['timestamp']}</p>"
            "</body></html>"
        )
        msg.attach(MIMEText(html, "html"))

        last_error = None
        for attempt in range(self.max_retries):
            try:
                smtp = aiosmtplib.SMTP(
                    hostname=smtp_host, port=smtp_port, use_tls=smtp_tls
                )
                await smtp.connect()
                if smtp_user and smtp_pass:
                    await smtp.login(smtp_user, smtp_pass)
                await smtp.send_message(msg)
                await smtp.quit()
                return "delivered"
            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2**attempt)
        return f"failed: {last_error}"


# Singleton
alert_manager = AlertManager()


# ---------------------------------------------------------------------------
# Health monitor - background task that polls health and fires alerts
# ---------------------------------------------------------------------------


class HealthMonitor:
    """Background task that periodically checks system health and fires alerts."""

    def __init__(self, manager: AlertManager) -> None:
        self.manager = manager
        self.poll_interval = int(os.getenv("ALERT_POLL_INTERVAL_SECONDS", "30"))
        self._previous_status: str | None = None
        self._previous_agents: dict[str, str] = {}
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if not ALERTS_ENABLED:
            logger.info("Alerts disabled, health monitor not started")
            return
        self._task = asyncio.create_task(self._poll_loop())
        logger.info(
            "Health monitor started (interval=%ds, cooldown=%ds)",
            self.poll_interval,
            self.manager.cooldown_seconds,
        )

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self.manager.close()
        logger.info("Health monitor stopped")

    async def _poll_loop(self) -> None:
        # Brief startup delay to let services come up
        await asyncio.sleep(5)
        while True:
            try:
                await self._check_health()
            except Exception as e:
                logger.debug("Health monitor poll error: %s", e)
            await asyncio.sleep(self.poll_interval)

    async def _check_health(self) -> None:
        """Fetch health status and fire alerts on transitions."""
        try:
            client = await self.manager._get_http_client()
            resp = await client.get("http://127.0.0.1:8000/health")
            data = resp.json()
        except Exception:
            # Can't reach self - likely starting up
            return

        current_status = data.get("status", "unknown")
        agents = data.get("agents", {})

        # Overall health transitions
        if (
            self._previous_status is not None
            and current_status != self._previous_status
        ):
            if current_status == "unhealthy":
                await self.manager.fire(
                    AlertType.HEALTH_UNHEALTHY,
                    AlertSeverity.CRITICAL,
                    "System unhealthy",
                    f"Health status changed: {self._previous_status} -> unhealthy. "
                    f"Redis: {data.get('redis')}, RabbitMQ: {data.get('rabbitmq')}",
                    context={
                        "redis": data.get("redis"),
                        "rabbitmq": data.get("rabbitmq"),
                    },
                )
            elif current_status == "degraded":
                await self.manager.fire(
                    AlertType.HEALTH_DEGRADED,
                    AlertSeverity.WARNING,
                    "System degraded",
                    f"Health status changed: {self._previous_status} -> degraded. "
                    "No agents responding.",
                    context={"agents": agents},
                )
            elif current_status == "healthy" and self._previous_status in (
                "degraded",
                "unhealthy",
            ):
                await self.manager.fire(
                    AlertType.HEALTH_RECOVERED,
                    AlertSeverity.INFO,
                    "System recovered",
                    f"Health status recovered: {self._previous_status} -> healthy",
                )

        # Per-agent transitions
        for agent_name, agent_status in agents.items():
            prev = self._previous_agents.get(agent_name)
            if prev is None:
                continue  # First check, no transition

            if agent_status == "offline" and prev != "offline":
                await self.manager.fire(
                    AlertType.AGENT_OFFLINE,
                    AlertSeverity.WARNING,
                    f"Agent offline: {agent_name}",
                    f"Agent '{agent_name}' went offline (was: {prev})",
                    context={"agent": agent_name, "previous": prev},
                )
            elif agent_status == "stale" and prev == "alive":
                await self.manager.fire(
                    AlertType.AGENT_STALE,
                    AlertSeverity.WARNING,
                    f"Agent stale: {agent_name}",
                    f"Agent '{agent_name}' heartbeat is stale (was: alive)",
                    context={"agent": agent_name},
                )

        self._previous_status = current_status
        self._previous_agents = dict(agents)


# Singleton
health_monitor = HealthMonitor(alert_manager)
