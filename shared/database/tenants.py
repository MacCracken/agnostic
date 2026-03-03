"""
Multi-tenant support for the Agentic QA System.

Provides tenant isolation using:
- Tenant-scoped Redis keyspaces (tenant_id prefix on all keys)
- Per-team RabbitMQ vhosts (optional)
- Tenant-aware session management
"""

import os
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from shared.database.models import Base


class TenantStatus(str, Enum):
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
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
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
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", name="uq_tenant_user"),
    )


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
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "key_id", name="uq_tenant_api_key"),
    )


class TenantManager:
    """Manager for multi-tenant operations."""

    def __init__(self):
        self.enabled = os.getenv("MULTI_TENANT_ENABLED", "false").lower() == "true"
        self.default_tenant_id = os.getenv("DEFAULT_TENANT_ID", "default")

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
            return datetime.now(timezone.utc) < tenant.trial_ends_at
        return False


tenant_manager = TenantManager()
