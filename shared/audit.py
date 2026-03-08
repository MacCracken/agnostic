"""
Structured audit logging for security-relevant events.

Emits JSON audit events to a dedicated logger. Events include auth, task,
tenant, and report operations with actor, action, resource, and outcome fields.

Configure via:
- AUDIT_LOG_ENABLED: Enable audit logging (default: true)
- AUDIT_LOG_LEVEL: Log level for audit events (default: INFO)
"""

import json
import logging
import os
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

AUDIT_ENABLED = os.getenv("AUDIT_LOG_ENABLED", "true").lower() == "true"
AUDIT_LOG_LEVEL = getattr(
    logging, os.getenv("AUDIT_LOG_LEVEL", "INFO").upper(), logging.INFO
)

# Dedicated audit logger — separate from application logs
_audit_logger = logging.getLogger("audit")


class AuditAction(StrEnum):
    """Auditable actions."""

    # Auth
    AUTH_LOGIN_SUCCESS = "auth.login.success"
    AUTH_LOGIN_FAILURE = "auth.login.failure"
    AUTH_LOGOUT = "auth.logout"
    AUTH_TOKEN_REFRESH = "auth.token.refresh"  # nosec B105
    AUTH_API_KEY_CREATED = "auth.apikey.created"
    AUTH_API_KEY_DELETED = "auth.apikey.deleted"
    AUTH_API_KEY_USED = "auth.apikey.used"

    # Tasks
    TASK_SUBMITTED = "task.submitted"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"

    # Reports
    REPORT_GENERATED = "report.generated"
    REPORT_DOWNLOADED = "report.downloaded"
    REPORT_SCHEDULED = "report.scheduled"
    REPORT_SCHEDULE_REMOVED = "report.schedule.removed"

    # Tenant
    TENANT_CREATED = "tenant.created"
    TENANT_UPDATED = "tenant.updated"
    TENANT_DELETED = "tenant.deleted"
    TENANT_USER_ADDED = "tenant.user.added"
    TENANT_USER_REMOVED = "tenant.user.removed"

    # Integration
    TOOL_INVOKED = "integration.tool_invoked"
    WEBHOOK_RECEIVED = "integration.webhook_received"

    # Credentials
    CREDENTIAL_PROVISIONED = "credential.provisioned"
    CREDENTIAL_ROTATED = "credential.rotated"
    CREDENTIAL_REVOKED = "credential.revoked"
    CREDENTIAL_EXPIRED = "credential.expired"

    # System
    RATE_LIMIT_EXCEEDED = "system.rate_limit"
    PERMISSION_DENIED = "system.permission_denied"
    PATH_TRAVERSAL_BLOCKED = "system.path_traversal"


def audit_log(
    action: AuditAction,
    actor: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    outcome: str = "success",
    detail: dict[str, Any] | None = None,
    tenant_id: str | None = None,
) -> None:
    """Emit a structured audit event.

    Args:
        action: The auditable action (from AuditAction enum)
        actor: User ID, API key ID, or "system"
        resource_type: Type of resource (task, report, tenant, session)
        resource_id: ID of the affected resource
        outcome: "success" or "failure"
        detail: Additional context (reason for failure, etc.)
        tenant_id: Tenant scope (if multi-tenant)
    """
    if not AUDIT_ENABLED:
        return

    event: dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "event": "audit",
        "action": action.value if isinstance(action, AuditAction) else action,
        "actor": actor or "anonymous",
        "outcome": outcome,
    }

    # Attach correlation ID if present
    try:
        from webgui.app import correlation_id_ctx

        cid = correlation_id_ctx.get()
        if cid:
            event["correlation_id"] = cid
    except (ImportError, LookupError):
        pass

    if resource_type:
        event["resource_type"] = resource_type
    if resource_id:
        event["resource_id"] = resource_id
    if tenant_id:
        event["tenant_id"] = tenant_id
    if detail:
        event["detail"] = detail

    _audit_logger.log(AUDIT_LOG_LEVEL, json.dumps(event, default=str))

    # Forward to AGNOS cryptographic audit chain (fire-and-forget)
    try:
        from shared.agnos_audit import agnos_audit_forwarder

        agnos_audit_forwarder.queue_event(event)
    except Exception:
        _audit_logger.debug(
            "AGNOS audit forwarding unavailable"
        )  # Never block local audit logging


def configure_audit_logging() -> None:
    """Set up the dedicated audit logger with a stream handler.

    Call this once during application startup (e.g. from app factory).
    The handler emits only the raw message since ``audit_log`` already
    produces fully-formed JSON.
    """
    _audit_logger.setLevel(AUDIT_LOG_LEVEL)

    # Avoid duplicate handlers on repeated calls
    if not _audit_logger.handlers:
        handler = logging.StreamHandler()
        handler.setLevel(AUDIT_LOG_LEVEL)
        # Message-only format — the JSON payload is self-describing
        handler.setFormatter(logging.Formatter("%(message)s"))
        _audit_logger.addHandler(handler)

    # Prevent propagation to root logger (avoids double-printing)
    _audit_logger.propagate = False
