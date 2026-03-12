"""Auth endpoints — login, logout, token refresh, API key management."""

import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from webgui.auth import Permission, auth_manager
from webgui.routes.dependencies import (
    PaginatedResponse,
    get_current_user,
    require_permission,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Login rate limiting — max attempts per email per window
_LOGIN_MAX_ATTEMPTS = int(os.getenv("LOGIN_RATE_LIMIT_MAX", "10"))
_LOGIN_WINDOW_SECONDS = int(os.getenv("LOGIN_RATE_LIMIT_WINDOW", "300"))


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class ApiKeyCreateRequest(BaseModel):
    description: str = ""
    role: str = "api_user"


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int | None = None


class StatusResponse(BaseModel):
    status: str


class UserMeResponse(BaseModel):
    user_id: str | None = None
    email: str | None = None
    role: str | None = None
    permissions: list[str] = []


class ApiKeyCreateResponse(BaseModel):
    key_id: str
    api_key: str
    description: str = ""
    role: str = "api_user"
    created_at: str
    note: str = ""


class ApiKeyDeleteResponse(BaseModel):
    status: str
    key_id: str


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------


@router.post("/auth/login", response_model=TokenResponse)
async def login(req: LoginRequest):
    # Rate limit login attempts per email
    try:
        from config.environment import config

        redis_client = config.get_async_redis_client()
        rate_key = f"login_attempts:{req.email}"
        attempts = await redis_client.incr(rate_key)
        if attempts == 1:
            await redis_client.expire(rate_key, _LOGIN_WINDOW_SECONDS)
        if attempts > _LOGIN_MAX_ATTEMPTS:
            logger.warning("Login rate limit exceeded for %s", req.email)
            raise HTTPException(
                status_code=429,
                detail="Too many login attempts. Try again later.",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Login rate limiting unavailable (Redis): %s", e)
        raise HTTPException(
            status_code=503,
            detail="Service temporarily unavailable. Try again later.",
        ) from e

    user = await auth_manager.authenticate_user(email=req.email, password=req.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    tokens = await auth_manager.create_tokens(user)
    return {
        "access_token": tokens.access_token,
        "refresh_token": tokens.refresh_token,
        "token_type": tokens.token_type,
        "expires_in": tokens.expires_in,
    }


@router.post("/auth/refresh", response_model=TokenResponse)
async def refresh(req: RefreshRequest):
    tokens = await auth_manager.refresh_tokens(req.refresh_token)
    if tokens is None:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    return {
        "access_token": tokens.access_token,
        "refresh_token": tokens.refresh_token,
        "token_type": tokens.token_type,
        "expires_in": tokens.expires_in,
    }


@router.post("/auth/logout", response_model=StatusResponse)
async def logout(request: Request, user: dict = Depends(get_current_user)):
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        access_token = auth_header[len("Bearer ") :]
    else:
        raise HTTPException(
            status_code=400, detail="Missing Bearer token in Authorization header"
        )
    success = await auth_manager.logout(user["user_id"], access_token)
    if not success:
        raise HTTPException(status_code=500, detail="Logout failed")
    return {"status": "logged_out"}


@router.get("/auth/me", response_model=UserMeResponse)
async def auth_me(user: dict = Depends(get_current_user)):
    return {
        "user_id": user.get("user_id"),
        "email": user.get("email"),
        "role": user.get("role"),
        "permissions": user.get("permissions", []),
    }


# ---------------------------------------------------------------------------
# API key management endpoints (require SYSTEM_CONFIGURE permission)
# ---------------------------------------------------------------------------


@router.post("/auth/api-keys", status_code=201, response_model=ApiKeyCreateResponse)
async def create_api_key(
    req: ApiKeyCreateRequest,
    user: dict = Depends(require_permission(Permission.SYSTEM_CONFIGURE)),
):
    """Create a new API key. Returns the raw key once — store it safely."""
    from config.environment import config
    from webgui.auth import create_api_key as _create_api_key

    redis_client = config.get_async_redis_client()
    raw_key, key_id, key_meta = await _create_api_key(
        redis_client=redis_client,
        description=req.description,
        role=req.role,
        created_by=user.get("user_id", "unknown"),
    )
    return {
        "key_id": key_id,
        "api_key": raw_key,
        "description": req.description,
        "role": req.role,
        "created_at": key_meta["created_at"],
        "note": "Store this key safely — it will not be shown again.",
    }


@router.get("/auth/api-keys", response_model=PaginatedResponse)
async def list_api_keys(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: dict = Depends(require_permission(Permission.SYSTEM_CONFIGURE)),
):
    """List API key IDs and metadata (never raw keys)."""
    from config.environment import config
    from webgui.auth import list_api_keys as _list_api_keys

    redis_client = config.get_async_redis_client()
    keys = await _list_api_keys(redis_client)
    total = len(keys)
    return {
        "items": keys[offset : offset + limit],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.delete("/auth/api-keys/{key_id}", response_model=ApiKeyDeleteResponse)
async def delete_api_key(
    key_id: str,
    user: dict = Depends(require_permission(Permission.SYSTEM_CONFIGURE)),
):
    """Revoke an API key by its ID (first 8 chars of sha256 hash)."""
    from config.environment import config
    from webgui.auth import revoke_api_key as _revoke_api_key

    redis_client = config.get_async_redis_client()
    deleted = await _revoke_api_key(redis_client, key_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="API key not found")
    return {"status": "revoked", "key_id": key_id}
