"""Multi-tenant management endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from webgui.routes.dependencies import (
    _check_tenant_access,
    _require_tenant_enabled,
    get_current_user,
    get_tenant_repo,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class TenantCreate(BaseModel):
    tenant_id: str
    name: str
    slug: str
    owner_email: str
    plan: str = "free"


class TenantUpdate(BaseModel):
    name: str | None = None
    status: str | None = None
    plan: str | None = None
    max_sessions: int | None = None
    max_agents: int | None = None


class TenantUserInvite(BaseModel):
    email: str
    user_id: str
    role: str = "member"


# ---------------------------------------------------------------------------
# Tenant CRUD endpoints
# ---------------------------------------------------------------------------


@router.get("/tenants")
async def list_tenants(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: dict = Depends(get_current_user),
):
    """List tenants (admin only)."""
    _require_tenant_enabled()

    if user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    repo = await get_tenant_repo()
    if repo is None:
        raise HTTPException(status_code=503, detail="Tenant database unavailable")

    tenants = await repo.list_tenants()
    items = [
        {
            "tenant_id": t.tenant_id,
            "name": t.name,
            "slug": t.slug,
            "status": t.status,
            "plan": t.plan,
            "owner_email": t.owner_email,
            "is_active": t.is_active,
            "created_at": t.created_at.isoformat(),
        }
        for t in tenants
    ]
    total = len(items)
    return {
        "items": items[offset : offset + limit],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/tenants")
async def create_tenant(
    req: TenantCreate,
    user: dict = Depends(get_current_user),
):
    """Create a new tenant (admin only)."""
    _require_tenant_enabled()

    if user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    repo = await get_tenant_repo()
    if repo is None:
        raise HTTPException(status_code=503, detail="Tenant database unavailable")

    tenant = await repo.create_tenant(
        tenant_id=req.tenant_id,
        name=req.name,
        slug=req.slug,
        owner_email=req.owner_email,
        plan=req.plan,
    )
    return {
        "tenant_id": tenant.tenant_id,
        "name": tenant.name,
        "slug": tenant.slug,
        "status": tenant.status,
        "plan": tenant.plan,
    }


@router.get("/tenants/{tenant_id}")
async def get_tenant(
    tenant_id: str,
    user: dict = Depends(get_current_user),
):
    """Get tenant details."""
    _require_tenant_enabled()
    _check_tenant_access(user, tenant_id)

    repo = await get_tenant_repo()
    if repo is None:
        raise HTTPException(status_code=503, detail="Tenant database unavailable")

    tenant = await repo.get_tenant(tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    return {
        "tenant_id": tenant.tenant_id,
        "name": tenant.name,
        "slug": tenant.slug,
        "status": tenant.status,
        "plan": tenant.plan,
        "owner_email": tenant.owner_email,
        "max_sessions": tenant.max_sessions,
        "max_agents": tenant.max_agents,
        "is_active": tenant.is_active,
        "created_at": tenant.created_at.isoformat(),
    }


@router.put("/tenants/{tenant_id}")
async def update_tenant(
    tenant_id: str,
    req: TenantUpdate,
    user: dict = Depends(get_current_user),
):
    """Update tenant (admin only)."""
    _require_tenant_enabled()
    _check_tenant_access(user, tenant_id)

    if user.get("role") not in ("super_admin", "org_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    repo = await get_tenant_repo()
    if repo is None:
        raise HTTPException(status_code=503, detail="Tenant database unavailable")

    updates = req.model_dump(exclude_none=True)
    tenant = await repo.update_tenant(tenant_id, updates)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    return {
        "tenant_id": tenant.tenant_id,
        "name": tenant.name,
        "status": tenant.status,
        "plan": tenant.plan,
    }


@router.delete("/tenants/{tenant_id}")
async def delete_tenant(
    tenant_id: str,
    user: dict = Depends(get_current_user),
):
    """Delete tenant (admin only — super_admin only for delete)."""
    _require_tenant_enabled()

    if user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Super admin access required")

    repo = await get_tenant_repo()
    if repo is None:
        raise HTTPException(status_code=503, detail="Tenant database unavailable")

    deleted = await repo.delete_tenant(tenant_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Tenant not found")

    return {"tenant_id": tenant_id, "status": "deleted"}


# ---------------------------------------------------------------------------
# Tenant user management
# ---------------------------------------------------------------------------


@router.get("/tenants/{tenant_id}/users")
async def list_tenant_users(
    tenant_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: dict = Depends(get_current_user),
):
    """List users in a tenant."""
    _require_tenant_enabled()
    _check_tenant_access(user, tenant_id)

    repo = await get_tenant_repo()
    if repo is None:
        raise HTTPException(status_code=503, detail="Tenant database unavailable")

    users = await repo.list_users(tenant_id)
    items = [
        {
            "user_id": u.user_id,
            "email": u.email,
            "role": u.role,
            "is_owner": u.is_owner,
            "is_admin": u.is_admin,
            "created_at": u.created_at.isoformat(),
        }
        for u in users
    ]
    total = len(items)
    return {
        "items": items[offset : offset + limit],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/tenants/{tenant_id}/users")
async def invite_tenant_user(
    tenant_id: str,
    req: TenantUserInvite,
    user: dict = Depends(get_current_user),
):
    """Invite user to tenant."""
    _require_tenant_enabled()

    if user.get("role") not in ("super_admin", "org_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    repo = await get_tenant_repo()
    if repo is None:
        raise HTTPException(status_code=503, detail="Tenant database unavailable")

    tenant_user = await repo.add_user(
        tenant_id=tenant_id,
        user_id=req.user_id,
        email=req.email,
        role=req.role,
    )
    return {
        "user_id": tenant_user.user_id,
        "email": tenant_user.email,
        "role": tenant_user.role,
        "status": "invited",
    }


@router.delete("/tenants/{tenant_id}/users/{user_id}")
async def remove_tenant_user(
    tenant_id: str,
    user_id: str,
    user: dict = Depends(get_current_user),
):
    """Remove user from tenant."""
    _require_tenant_enabled()

    if user.get("role") not in ("super_admin", "org_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    repo = await get_tenant_repo()
    if repo is None:
        raise HTTPException(status_code=503, detail="Tenant database unavailable")

    removed = await repo.remove_user(tenant_id, user_id)
    if not removed:
        raise HTTPException(status_code=404, detail="User not found in tenant")

    return {"user_id": user_id, "status": "removed"}
