"""Tests for shared/alerts.py — AlertManager, HealthMonitor."""

import json
import os
import sys
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from shared.alerts import (
    AlertManager,
    AlertSeverity,
    AlertType,
    HealthMonitor,
)


# ---------------------------------------------------------------------------
# AlertManager tests
# ---------------------------------------------------------------------------


class TestAlertManager:
    def test_alert_types_enum(self):
        assert AlertType.HEALTH_DEGRADED == "health.degraded"
        assert AlertType.CIRCUIT_BREAKER_OPEN == "circuit_breaker.open"

    def test_severity_enum(self):
        assert AlertSeverity.CRITICAL == "critical"
        assert AlertSeverity.WARNING == "warning"
        assert AlertSeverity.INFO == "info"

    @pytest.mark.asyncio
    async def test_fire_disabled(self):
        """Alerts suppressed when ALERTS_ENABLED is false."""
        mgr = AlertManager()
        with patch("shared.alerts.ALERTS_ENABLED", False):
            result = await mgr.fire(
                AlertType.HEALTH_DEGRADED,
                AlertSeverity.WARNING,
                "test",
                "test message",
            )
            assert result is None

    @pytest.mark.asyncio
    async def test_fire_enabled_no_channels(self):
        """Fire succeeds with empty results when no channels configured."""
        mgr = AlertManager()
        mgr.webhook_url = ""
        mgr.slack_webhook_url = ""
        mgr.email_recipients = []
        with patch("shared.alerts.ALERTS_ENABLED", True):
            result = await mgr.fire(
                AlertType.HEALTH_DEGRADED,
                AlertSeverity.WARNING,
                "test",
                "test message",
            )
            assert result == {}

    @pytest.mark.asyncio
    async def test_cooldown_suppresses_duplicate(self):
        """Second alert of same type within cooldown is suppressed."""
        mgr = AlertManager()
        mgr.cooldown_seconds = 600
        mgr.webhook_url = ""
        mgr.slack_webhook_url = ""
        mgr.email_recipients = []
        with patch("shared.alerts.ALERTS_ENABLED", True):
            r1 = await mgr.fire(
                AlertType.AGENT_OFFLINE,
                AlertSeverity.WARNING,
                "agent down",
                "test",
                context={"agent": "qa-manager"},
            )
            assert r1 is not None

            r2 = await mgr.fire(
                AlertType.AGENT_OFFLINE,
                AlertSeverity.WARNING,
                "agent down",
                "test",
                context={"agent": "qa-manager"},
            )
            assert r2 is None  # suppressed

    @pytest.mark.asyncio
    async def test_cooldown_allows_different_context(self):
        """Alerts with different context are not suppressed."""
        mgr = AlertManager()
        mgr.cooldown_seconds = 600
        mgr.webhook_url = ""
        mgr.slack_webhook_url = ""
        mgr.email_recipients = []
        with patch("shared.alerts.ALERTS_ENABLED", True):
            r1 = await mgr.fire(
                AlertType.AGENT_OFFLINE,
                AlertSeverity.WARNING,
                "agent down",
                "test",
                context={"agent": "qa-manager"},
            )
            r2 = await mgr.fire(
                AlertType.AGENT_OFFLINE,
                AlertSeverity.WARNING,
                "agent down",
                "test",
                context={"agent": "senior-qa"},
            )
            assert r1 is not None
            assert r2 is not None

    @pytest.mark.asyncio
    async def test_webhook_delivery(self):
        """Webhook delivery posts JSON with HMAC signature."""
        mgr = AlertManager()
        mgr.webhook_url = "https://example.com/hook"
        mgr.webhook_secret = "test-secret"
        mgr.slack_webhook_url = ""
        mgr.email_recipients = []

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.is_closed = False

        with patch("shared.alerts.ALERTS_ENABLED", True):
            mgr._http_client = mock_client
            result = await mgr.fire(
                AlertType.HEALTH_UNHEALTHY,
                AlertSeverity.CRITICAL,
                "System down",
                "Redis is unreachable",
            )
            assert result["webhook"] == "delivered"
            call_kwargs = mock_client.post.call_args
            assert "X-Signature" in call_kwargs.kwargs.get(
                "headers", call_kwargs[1].get("headers", {})
            )

    def test_has_channels(self):
        mgr = AlertManager()
        mgr.webhook_url = ""
        mgr.slack_webhook_url = ""
        mgr.email_recipients = []
        assert not mgr.has_channels

        mgr.webhook_url = "https://example.com"
        assert mgr.has_channels


# ---------------------------------------------------------------------------
# HealthMonitor tests
# ---------------------------------------------------------------------------


class TestHealthMonitor:
    @pytest.mark.asyncio
    async def test_start_disabled(self):
        """Monitor doesn't start when alerts disabled."""
        mgr = AlertManager()
        monitor = HealthMonitor(mgr)
        with patch("shared.alerts.ALERTS_ENABLED", False):
            await monitor.start()
            assert monitor._task is None

    @pytest.mark.asyncio
    async def test_health_transition_fires_alert(self):
        """Transition from healthy to degraded fires alert."""
        mgr = AlertManager()
        mgr.webhook_url = ""
        mgr.slack_webhook_url = ""
        mgr.email_recipients = []
        mgr.fire = AsyncMock(return_value={})

        monitor = HealthMonitor(mgr)
        monitor._previous_status = "healthy"
        monitor._previous_agents = {"qa-manager": "alive"}

        health_data = {
            "status": "degraded",
            "redis": "ok",
            "rabbitmq": "ok",
            "agents": {"qa-manager": "offline"},
        }
        mock_resp = MagicMock()
        mock_resp.json.return_value = health_data

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.is_closed = False
        mgr._http_client = mock_client

        with patch("shared.alerts.ALERTS_ENABLED", True):
            await monitor._check_health()

        # Should have fired for health.degraded and agent.offline
        assert mgr.fire.call_count >= 1
        alert_types = [call.args[0] for call in mgr.fire.call_args_list]
        assert AlertType.HEALTH_DEGRADED in alert_types

    @pytest.mark.asyncio
    async def test_no_alert_on_first_check(self):
        """First health check establishes baseline without firing."""
        mgr = AlertManager()
        mgr.fire = AsyncMock(return_value={})

        monitor = HealthMonitor(mgr)
        assert monitor._previous_status is None

        health_data = {
            "status": "healthy",
            "agents": {"qa-manager": "alive"},
        }
        mock_resp = MagicMock()
        mock_resp.json.return_value = health_data

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.is_closed = False
        mgr._http_client = mock_client

        with patch("shared.alerts.ALERTS_ENABLED", True):
            await monitor._check_health()

        mgr.fire.assert_not_called()
        assert monitor._previous_status == "healthy"


# ---------------------------------------------------------------------------
# CircuitBreaker callback integration
# ---------------------------------------------------------------------------


class TestCircuitBreakerCallback:
    def test_callback_on_open(self):
        """Circuit breaker fires on_state_change when tripping to OPEN."""
        from shared.resilience import CircuitBreaker

        callback = MagicMock()
        cb = CircuitBreaker(
            name="test", failure_threshold=2, on_state_change=callback
        )

        cb.record_failure()
        callback.assert_not_called()
        cb.record_failure()
        callback.assert_called_once_with("test", "closed", "open")

    def test_callback_on_recovery(self):
        """Circuit breaker fires on_state_change when recovering to CLOSED."""
        from shared.resilience import CircuitBreaker

        callback = MagicMock()
        cb = CircuitBreaker(
            name="test", failure_threshold=1, on_state_change=callback
        )

        cb.record_failure()  # trips to OPEN
        callback.reset_mock()

        cb._state = cb._state  # force to stay OPEN for test
        # Manually set to HALF_OPEN to test recovery path
        from shared.resilience import CircuitState

        cb._state = CircuitState.HALF_OPEN
        cb.record_success()
        callback.assert_called_once_with("test", "half_open", "closed")

    def test_no_callback_when_none(self):
        """No error when on_state_change is None."""
        from shared.resilience import CircuitBreaker

        cb = CircuitBreaker(name="test", failure_threshold=1)
        cb.record_failure()  # should not raise
        cb.record_success()  # should not raise
