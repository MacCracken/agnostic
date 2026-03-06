"""Tests for shared.audit — structured audit logging."""

import json
import logging
from unittest.mock import patch

import pytest

import shared.audit as audit_module
from shared.audit import AuditAction, audit_log


class TestAuditLog:
    """Tests for the audit_log function."""

    def test_audit_log_emits_json(self, caplog):
        """audit_log writes valid JSON to the audit logger."""
        with caplog.at_level(logging.INFO, logger="audit"):
            audit_log(
                AuditAction.TASK_SUBMITTED,
                actor="user-1",
                resource_type="task",
                resource_id="t-123",
            )

        assert len(caplog.records) == 1
        event = json.loads(caplog.records[0].message)
        assert event["action"] == "task.submitted"
        assert event["actor"] == "user-1"
        assert event["resource_type"] == "task"
        assert event["resource_id"] == "t-123"
        assert event["outcome"] == "success"
        assert "timestamp" in event

    def test_audit_log_disabled(self, caplog):
        """No output when AUDIT_ENABLED is False."""
        with patch.object(audit_module, "AUDIT_ENABLED", False):
            with caplog.at_level(logging.INFO, logger="audit"):
                audit_log(AuditAction.TASK_SUBMITTED, actor="user-1")

        assert len(caplog.records) == 0

    def test_audit_log_minimal(self, caplog):
        """Only action required — defaults applied for actor and outcome."""
        with caplog.at_level(logging.INFO, logger="audit"):
            audit_log(AuditAction.AUTH_LOGOUT)

        event = json.loads(caplog.records[0].message)
        assert event["actor"] == "anonymous"
        assert event["outcome"] == "success"
        assert "resource_type" not in event
        assert "resource_id" not in event

    def test_audit_log_with_all_fields(self, caplog):
        """All optional fields appear in output."""
        with caplog.at_level(logging.INFO, logger="audit"):
            audit_log(
                AuditAction.TENANT_CREATED,
                actor="admin-1",
                resource_type="tenant",
                resource_id="tn-456",
                outcome="success",
                detail={"plan": "enterprise"},
                tenant_id="tn-456",
            )

        event = json.loads(caplog.records[0].message)
        assert event["resource_type"] == "tenant"
        assert event["resource_id"] == "tn-456"
        assert event["tenant_id"] == "tn-456"
        assert event["detail"] == {"plan": "enterprise"}

    def test_audit_log_with_detail(self, caplog):
        """Detail dict is serialized in the JSON."""
        with caplog.at_level(logging.INFO, logger="audit"):
            audit_log(
                AuditAction.AUTH_LOGIN_FAILURE,
                actor="user@example.com",
                outcome="failure",
                detail={"provider": "google", "reason": "expired"},
            )

        event = json.loads(caplog.records[0].message)
        assert event["detail"]["provider"] == "google"
        assert event["detail"]["reason"] == "expired"

    def test_audit_log_failure_outcome(self, caplog):
        """Failure outcome is recorded."""
        with caplog.at_level(logging.INFO, logger="audit"):
            audit_log(
                AuditAction.PERMISSION_DENIED,
                actor="user-2",
                outcome="failure",
            )

        event = json.loads(caplog.records[0].message)
        assert event["outcome"] == "failure"


class TestAuditActionEnum:
    """Tests for AuditAction enum values."""

    def test_all_values_are_dotted_strings(self):
        """Every enum value follows the dotted string pattern."""
        for action in AuditAction:
            assert "." in action.value, f"{action.name} value {action.value!r} is not dotted"

    def test_expected_actions_exist(self):
        """Key actions are defined."""
        expected = [
            "auth.login.success",
            "auth.login.failure",
            "task.submitted",
            "task.completed",
            "report.generated",
            "tenant.created",
            "system.rate_limit",
            "system.permission_denied",
        ]
        values = {a.value for a in AuditAction}
        for exp in expected:
            assert exp in values, f"Missing audit action: {exp}"


class TestConfigureAuditLogging:
    """Tests for configure_audit_logging."""

    def test_configure_sets_up_handler(self):
        """configure_audit_logging adds a StreamHandler."""
        from shared.audit import _audit_logger, configure_audit_logging

        _audit_logger.handlers.clear()
        configure_audit_logging()

        assert len(_audit_logger.handlers) == 1
        assert isinstance(_audit_logger.handlers[0], logging.StreamHandler)
        assert _audit_logger.propagate is False

    def test_configure_idempotent(self):
        """Repeated calls don't add duplicate handlers."""
        from shared.audit import _audit_logger, configure_audit_logging

        _audit_logger.handlers.clear()
        configure_audit_logging()
        configure_audit_logging()

        assert len(_audit_logger.handlers) == 1
