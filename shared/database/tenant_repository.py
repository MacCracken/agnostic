"""
Repository for multi-tenant database operations.
"""

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database.tenants import Tenant, TenantUser

logger = logging.getLogger(__name__)


class TenantRepository:
    """Repository for tenant CRUD operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_tenant(
        self,
        tenant_id: str,
        name: str,
        slug: str,
        owner_email: str,
        plan: str = "free",
    ) -> Tenant:
        """Create a new tenant."""
        tenant = Tenant(
            tenant_id=tenant_id,
            name=name,
            slug=slug,
            owner_email=owner_email,
            plan=plan,
        )
        self.session.add(tenant)
        await self.session.commit()
        await self.session.refresh(tenant)
        return tenant

    async def get_tenant(self, tenant_id: str) -> Tenant | None:
        """Get a tenant by ID."""
        result = await self.session.execute(
            select(Tenant).where(Tenant.tenant_id == tenant_id)
        )
        return result.scalar_one_or_none()

    async def list_tenants(self, limit: int = 50, offset: int = 0) -> list[Tenant]:
        """List all tenants."""
        result = await self.session.execute(
            select(Tenant)
            .order_by(Tenant.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def update_tenant(
        self, tenant_id: str, updates: dict[str, Any]
    ) -> Tenant | None:
        """Update tenant fields."""
        tenant = await self.get_tenant(tenant_id)
        if not tenant:
            return None

        allowed_fields = {
            "name",
            "status",
            "plan",
            "max_sessions",
            "max_agents",
            "max_storage_mb",
            "webhook_url",
            "custom_domain",
        }
        for key, value in updates.items():
            if key in allowed_fields and value is not None:
                setattr(tenant, key, value)

        await self.session.commit()
        await self.session.refresh(tenant)
        return tenant

    async def delete_tenant(self, tenant_id: str) -> bool:
        """Soft-delete a tenant by setting is_active=False."""
        tenant = await self.get_tenant(tenant_id)
        if not tenant:
            return False

        tenant.is_active = False
        tenant.status = "disabled"
        await self.session.commit()
        return True

    # --- Tenant Users ---

    async def list_users(self, tenant_id: str) -> list[TenantUser]:
        """List users in a tenant."""
        result = await self.session.execute(
            select(TenantUser).where(TenantUser.tenant_id == tenant_id)
        )
        return list(result.scalars().all())

    async def add_user(
        self,
        tenant_id: str,
        user_id: str,
        email: str,
        role: str = "member",
        is_owner: bool = False,
        is_admin: bool = False,
    ) -> TenantUser:
        """Add a user to a tenant."""
        user = TenantUser(
            tenant_id=tenant_id,
            user_id=user_id,
            email=email,
            role=role,
            is_owner=is_owner,
            is_admin=is_admin,
        )
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def remove_user(self, tenant_id: str, user_id: str) -> bool:
        """Remove a user from a tenant."""
        result = await self.session.execute(
            select(TenantUser).where(
                TenantUser.tenant_id == tenant_id,
                TenantUser.user_id == user_id,
            )
        )
        user = result.scalar_one_or_none()
        if not user:
            return False

        await self.session.delete(user)
        await self.session.commit()
        return True
