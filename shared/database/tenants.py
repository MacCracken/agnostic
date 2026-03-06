"""
Multi-tenant support for the Agentic QA System.

Provides tenant isolation using:
- Tenant-scoped Redis keyspaces (tenant_id prefix on all keys)
- Per-team RabbitMQ vhosts (optional)
- Tenant-aware session management
"""

import os
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from shared.database.models import Base


class TenantStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    TRIAL = "trial"
    DISABLED = "disabled"


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default=TenantStatus.TRIAL.value)

    owner_email: Mapped[str] = mapped_column(String(255))
    plan: Mapped[str] = mapped_column(String(50), default="free")

    max_sessions: Mapped[int] = mapped_column(Integer, default=10)
    max_agents: Mapped[int] = mapped_column(Integer, default=6)
    max_storage_mb: Mapped[int] = mapped_column(Integer, default=1000)

    redis_key_prefix: Mapped[str] = mapped_column(String(50), default="default")
    rabbitmq_vhost: Mapped[str | None] = mapped_column(String(100), nullable=True)

    custom_domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    webhook_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    settings: Mapped[dict[str, Any] | None] = mapped_column(Text, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_tenant_id"),
        UniqueConstraint("slug", name="uq_tenant_slug"),
    )


class TenantUser(Base):
    __tablename__ = "tenant_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(50), index=True)
    user_id: Mapped[str] = mapped_column(String(100), index=True)

    email: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(50), default="member")

    is_owner: Mapped[bool] = mapped_column(Boolean, default=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC)
    )

    __table_args__ = (UniqueConstraint("tenant_id", "user_id", name="uq_tenant_user"),)


class TenantAPIKey(Base):
    __tablename__ = "tenant_api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(50), index=True)
    key_id: Mapped[str] = mapped_column(String(50), unique=True)
    key_hash: Mapped[str] = mapped_column(String(255))

    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)

    rate_limit: Mapped[int] = mapped_column(Integer, default=100)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC)
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "key_id", name="uq_tenant_api_key"),
    )


class TenantManager:
    """Manager for multi-tenant operations."""

    def __init__(self):
        self.enabled = os.getenv("MULTI_TENANT_ENABLED", "false").lower() == "true"
        self.default_tenant_id = os.getenv("DEFAULT_TENANT_ID", "default")
        self.default_rate_limit = int(os.getenv("TENANT_DEFAULT_RATE_LIMIT", "100"))

    def get_tenant_id(self, request) -> str:
        """Extract tenant ID from request."""
        if not self.enabled:
            return self.default_tenant_id

        header_tenant = request.headers.get("X-Tenant-ID")
        if header_tenant:
            return header_tenant

        cookie_tenant = request.cookies.get("tenant_id")
        if cookie_tenant:
            return cookie_tenant

        return self.default_tenant_id

    def get_redis_key(self, tenant_id: str, key: str) -> str:
        """Generate tenant-scoped Redis key."""
        return f"tenant:{tenant_id}:{key}"

    def get_redis_prefix(self, tenant_id: str) -> str:
        """Get Redis key prefix for tenant."""
        return f"tenant:{tenant_id}"

    def task_key(self, tenant_id: str, task_id: str) -> str:
        """Redis key for a task, scoped to tenant when enabled."""
        if self.enabled:
            return f"tenant:{tenant_id}:task:{task_id}"
        return f"task:{task_id}"

    def session_key(self, tenant_id: str, session_id: str) -> str:
        """Redis key for session data, scoped to tenant when enabled."""
        if self.enabled:
            return f"tenant:{tenant_id}:session:{session_id}"
        return f"session:{session_id}"

    def check_quota(self, tenant: Tenant, resource: str, current: int) -> bool:
        """Check if tenant has quota for a resource."""
        quotas = {
            "sessions": tenant.max_sessions,
            "agents": tenant.max_agents,
            "storage_mb": tenant.max_storage_mb,
        }
        limit = quotas.get(resource, float("inf"))
        return current < limit

    def is_within_trial(self, tenant: Tenant) -> bool:
        """Check if tenant is within trial period."""
        if tenant.status == TenantStatus.TRIAL and tenant.trial_ends_at:
            return datetime.now(UTC) < tenant.trial_ends_at
        return False

    def check_rate_limit(
        self, redis_client, tenant_id: str, rate_limit: int | None = None
    ) -> bool:
        """Check and increment rate limit counter for a tenant.

        Uses a sliding window: one Redis key per minute, expires after 60s.
        Returns True if request is allowed, False if rate-limited.
        """
        limit = rate_limit or self.default_rate_limit
        now = datetime.now(UTC)
        window_key = f"tenant:{tenant_id}:rate:{now.strftime('%Y%m%d%H%M')}"

        current = redis_client.incr(window_key)
        if current == 1:
            redis_client.expire(window_key, 60)

        return current <= limit

    def validate_tenant_api_key(
        self, redis_client, api_key: str
    ) -> dict[str, Any] | None:
        """Validate a tenant-scoped API key.

        Looks up key hash in Redis under tenant_api_key:{hash}.
        Returns user dict with tenant_id if valid, None otherwise.
        """
        import hashlib

        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        key_data = redis_client.get(f"tenant_api_key:{key_hash}")
        if not key_data:
            return None

        import json

        data = json.loads(key_data)

        # Update last_used timestamp
        data["last_used_at"] = datetime.now(UTC).isoformat()
        redis_client.set(f"tenant_api_key:{key_hash}", json.dumps(data))

        return {
            "user_id": f"tenant-api-{data.get('tenant_id', 'unknown')}",
            "email": f"api@{data.get('tenant_id', 'unknown')}",
            "role": data.get("role", "api_user"),
            "tenant_id": data.get("tenant_id"),
            "permissions": data.get("permissions", []),
        }


tenant_manager = TenantManager()
