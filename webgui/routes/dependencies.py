"""Shared dependencies, helpers, and request models used across route modules."""

import hashlib
import hmac
import ipaddress
import json
import logging
import os
import socket
from typing import Any
from urllib.parse import urlparse

from fastapi import Depends, Header, HTTPException
from pydantic import BaseModel

from shared.audit import AuditAction, audit_log
from webgui.auth import Permission, auth_manager

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Standard response models
# ---------------------------------------------------------------------------


class PaginatedResponse(BaseModel):
    """Standard pagination envelope for list endpoints."""

    items: list[dict[str, Any]]
    total: int
    limit: int
    offset: int = 0


class ErrorDetail(BaseModel):
    """Standard error response body."""

    detail: str
    code: str | None = None


# ---------------------------------------------------------------------------
# SSRF protection — block callbacks to private/internal networks
# ---------------------------------------------------------------------------

_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def _validate_callback_url(url: str) -> None:
    """Raise ValueError if url points to a private/internal network.

    Resolves domain names to IP addresses to prevent DNS rebinding attacks.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Unsupported scheme: {parsed.scheme}")
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("Missing hostname")

    def _check_ip(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> None:
        for net in _BLOCKED_NETWORKS:
            if addr in net:
                raise ValueError(f"Callback to private network blocked: {addr}")

    try:
        addr = ipaddress.ip_address(hostname)
        _check_ip(addr)
    except ValueError as e:
        if (
            "private network" in str(e)
            or "Unsupported" in str(e)
            or "Missing" in str(e)
        ):
            raise
        # hostname is a domain name — resolve and validate all addresses
        try:
            addrinfos = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
            for _family, _type, _proto, _canonname, sockaddr in addrinfos:
                resolved_ip = ipaddress.ip_address(sockaddr[0])
                _check_ip(resolved_ip)
        except socket.gaierror:
            raise ValueError(f"Cannot resolve hostname: {hostname}")  # noqa: B904


# ---------------------------------------------------------------------------
# Agent name normalization
# ---------------------------------------------------------------------------


def _normalize_agent_name(name: str) -> str:
    """Normalize agent name: convert underscores to hyphens."""
    return name.replace("_", "-")


_VALID_AGENTS = {
    "security-compliance",
    "performance",
    "junior-qa",
    "qa-analyst",
    "senior-qa",
    "qa-manager",
}


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------


async def get_current_user(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    """Extract and verify credentials from request headers.

    Checks X-API-Key first (env-var static key, then Redis-backed keys),
    then falls back to Bearer JWT.
    """
    # 1. Check X-API-Key header
    if x_api_key is not None:
        # Static env-var key (simple deployments) — constant-time compare prevents timing attacks
        static_key = os.getenv("AGNOSTIC_API_KEY")
        if static_key and hmac.compare_digest(x_api_key, static_key):
            audit_log(
                AuditAction.AUTH_API_KEY_USED,
                actor="api-key-user",
                resource_type="auth",
                detail={"method": "static"},
            )
            # Static key gets operational permissions only (not SYSTEM_CONFIGURE)
            _static_permissions = [
                p.value for p in Permission if p != Permission.SYSTEM_CONFIGURE
            ]
            return {
                "user_id": "api-key-user",
                "email": "api@agnostic",
                "role": "api_user",
                "permissions": _static_permissions,
            }

        # Redis-backed keys (multi-key deployments)
        try:
            from config.environment import config

            redis_client = config.get_async_redis_client()
            key_hash = hashlib.sha256(x_api_key.encode()).hexdigest()
            key_data = await redis_client.get(f"api_key:{key_hash}")
            if key_data:
                parsed = json.loads(key_data)
                audit_log(
                    AuditAction.AUTH_API_KEY_USED,
                    actor=parsed.get("key_id", key_hash[:8]),
                    resource_type="auth",
                    detail={"method": "redis"},
                )
                return parsed

            # Tenant-scoped API keys
            from shared.database.tenants import tenant_manager

            if tenant_manager.enabled:
                tenant_user = await tenant_manager.validate_tenant_api_key(
                    redis_client, x_api_key
                )
                if tenant_user:
                    return tenant_user

        except Exception as e:
            logger.warning(f"Redis API key lookup failed: {e}")

        raise HTTPException(status_code=401, detail="Invalid API key")

    # 2. Fall back to Bearer JWT
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401, detail="Missing or invalid authorization header"
        )

    token = authorization.removeprefix("Bearer ")

    # 2a. Try SecureYeoman JWT first (if configured)
    try:
        from shared.yeoman_jwt import is_enabled as yeoman_jwt_enabled
        from shared.yeoman_jwt import validate_yeoman_jwt

        if yeoman_jwt_enabled():
            yeoman_user = validate_yeoman_jwt(token)
            if yeoman_user is not None:
                audit_log(
                    AuditAction.AUTH_LOGIN_SUCCESS,
                    actor=yeoman_user["user_id"],
                    resource_type="auth",
                    detail={"method": "yeoman_jwt"},
                )
                return yeoman_user
    except ImportError:
        pass

    # 2b. AGNOSTIC's own JWT
    payload = await auth_manager.verify_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return payload


def require_permission(permission: Permission):
    """Factory for permission-checking dependencies."""

    async def _check(user: dict = Depends(get_current_user)):
        user_permissions = user.get("permissions", [])
        if permission.value not in user_permissions:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user

    return _check


# ---------------------------------------------------------------------------
# Feature flags
# ---------------------------------------------------------------------------

DATABASE_ENABLED = os.getenv("DATABASE_ENABLED", "false").lower() == "true"
MULTI_TENANT_ENABLED = os.getenv("MULTI_TENANT_ENABLED", "false").lower() == "true"
YEOMAN_A2A_ENABLED = os.getenv("YEOMAN_A2A_ENABLED", "false").lower() == "true"


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


def _get_db_repo():
    """Get database repository if enabled."""
    if not DATABASE_ENABLED:
        return None
    try:
        from shared.database.repository import TestResultRepository

        return TestResultRepository
    except Exception:
        return None


async def get_db_repo():
    """Get database repository instance."""
    repo_class = _get_db_repo()
    if repo_class is None:
        return None
    from shared.database.models import get_session

    session = await get_session()
    return repo_class(session)


async def get_tenant_repo():
    """Get tenant repository instance."""
    if not MULTI_TENANT_ENABLED or not DATABASE_ENABLED:
        return None
    try:
        from shared.database.models import get_session
        from shared.database.tenant_repository import TenantRepository

        session = await get_session()
        return TenantRepository(session)
    except Exception:
        return None


def _require_tenant_enabled():
    """Raise 503 if multi-tenancy is not enabled."""
    if not MULTI_TENANT_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="Multi-tenancy not enabled. Set MULTI_TENANT_ENABLED=true",
        )
    if not DATABASE_ENABLED:
        raise HTTPException(
            status_code=503, detail="Database not enabled. Set DATABASE_ENABLED=true"
        )


def _check_tenant_access(user: dict[str, Any], tenant_id: str) -> None:
    """Ensure user has access to the specified tenant."""
    if user.get("role") == "super_admin":
        return  # Super admins can access all tenants
    user_tenant = user.get("tenant_id")
    if user_tenant and user_tenant != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied to this tenant")
