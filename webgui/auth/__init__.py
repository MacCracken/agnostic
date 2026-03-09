"""Authentication and Authorization Package.

Composed AuthManager delegates to TokenManager, OAuthProviderFactory,
and PermissionValidator.  Provides backward-compatible singleton
``auth_manager`` and re-exports all public symbols.
"""

import json
import logging
import os
import secrets
import sys
from dataclasses import asdict
from datetime import datetime as _dt
from typing import Any

# Add config path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.environment import config
from shared.audit import AuditAction, audit_log
from webgui.auth.api_keys import create_api_key, list_api_keys, revoke_api_key
from webgui.auth.models import AuthProvider, AuthToken, Permission, User, UserRole
from webgui.auth.oauth_provider import OAuthProviderFactory
from webgui.auth.permission_validator import ROLE_PERMISSIONS, PermissionValidator
from webgui.auth.token_manager import TokenManager

logger = logging.getLogger(__name__)

__all__ = [
    "AuthManager",
    "AuthProvider",
    "AuthToken",
    "OAuthProviderFactory",
    "Permission",
    "PermissionValidator",
    "TokenManager",
    "User",
    "UserRole",
    "auth_manager",
    "create_api_key",
    "list_api_keys",
    "revoke_api_key",
]


class AuthManager:
    """Composed authentication manager delegating to specialized sub-managers.

    Public API is identical to the original monolithic AuthManager so all
    existing callers continue to work without changes.
    """

    def __init__(self):
        self.redis_client = config.get_redis_client()

        environment = os.getenv("ENVIRONMENT", "development")
        secret_key = os.getenv("WEBGUI_SECRET_KEY")
        if environment == "production" and not secret_key:
            raise ValueError(
                "WEBGUI_SECRET_KEY must be set in production. "
                'Generate one with: python -c "import secrets; print(secrets.token_urlsafe(32))"'
            )
        if not secret_key:
            # In development, persist the auto-generated key so tokens
            # survive app restarts within the same environment.
            _dev_key_path = os.path.join(
                os.getenv("HOME", "/tmp"),  # nosec B108
                ".agnostic_dev_secret_key",
            )
            try:
                with open(_dev_key_path) as f:
                    secret_key = f.read().strip()
                if not secret_key:
                    raise ValueError("empty key file")
            except (FileNotFoundError, ValueError, PermissionError):
                secret_key = secrets.token_urlsafe(32)
                try:
                    with open(_dev_key_path, "w") as f:
                        f.write(secret_key)
                    os.chmod(_dev_key_path, 0o600)
                    logger.info(
                        "Generated and persisted dev secret key to %s",
                        _dev_key_path,
                    )
                except OSError:
                    logger.warning(
                        "Could not persist dev secret key — tokens will "
                        "be invalidated on restart"
                    )
        self.secret_key = secret_key

        # Role permissions mapping (shared across sub-managers)
        self.role_permissions = dict(ROLE_PERMISSIONS)

        # Sub-managers
        self.token_manager = TokenManager(self.redis_client, self.secret_key)
        self.oauth_provider = OAuthProviderFactory(
            self.redis_client,
            self.role_permissions,
            self.token_manager.verify_password,
        )
        self.permission_validator = PermissionValidator(
            self.redis_client, self.role_permissions
        )

        # Expose token TTL config for backward compat
        self.access_token_expire_minutes = (
            self.token_manager.access_token_expire_minutes
        )
        self.refresh_token_expire_days = self.token_manager.refresh_token_expire_days

    # --- Token operations (delegated to TokenManager) ---

    async def create_tokens(self, user: User) -> AuthToken:
        return await self.token_manager.create_tokens(user)

    async def verify_token(self, token: str) -> dict[str, Any] | None:
        return await self.token_manager.verify_token(token)

    async def refresh_tokens(self, refresh_token: str) -> AuthToken | None:
        return await self.token_manager.refresh_tokens(refresh_token, self.get_user)

    async def logout(self, user_id: str, access_token: str) -> bool:
        return await self.token_manager.logout(user_id, access_token)

    # --- Authentication (delegated to OAuthProviderFactory) ---

    async def authenticate_user(
        self,
        email: str,
        password: str | None = None,
        provider: AuthProvider = AuthProvider.LOCAL,
        auth_code: str | None = None,
        id_token: str | None = None,
    ) -> User | None:
        """Authenticate user with various providers."""
        try:
            user = await self.oauth_provider.authenticate(
                provider=provider,
                email=email,
                password=password,
                auth_code=auth_code,
                id_token=id_token,
            )

            if user:
                audit_log(
                    AuditAction.AUTH_LOGIN_SUCCESS,
                    actor=user.user_id,
                    resource_type="auth",
                    detail={"provider": provider.value},
                )
            else:
                audit_log(
                    AuditAction.AUTH_LOGIN_FAILURE,
                    actor=email,
                    outcome="failure",
                    resource_type="auth",
                    detail={"provider": provider.value},
                )
            return user

        except Exception as e:
            logger.error(f"Authentication error for {email}: {e}")
            audit_log(
                AuditAction.AUTH_LOGIN_FAILURE,
                actor=email,
                outcome="failure",
                resource_type="auth",
                detail={"provider": provider.value, "error": str(e)},
            )
            return None

    # --- Permission checks (delegated to PermissionValidator) ---

    async def check_permission(self, user: User, permission: Permission) -> bool:
        return await self.permission_validator.check_permission(user, permission)

    async def check_resource_access(
        self, user: User, resource_type: str, resource_id: str, action: str
    ) -> bool:
        return await self.permission_validator.check_resource_access(
            user, resource_type, resource_id, action
        )

    # --- User management (kept in AuthManager for orchestration) ---

    async def get_user(self, user_id: str) -> User | None:
        """Get user by ID."""
        try:
            user_key = f"user:{user_id}"
            user_data = self.redis_client.get(user_key)

            if not user_data:
                return None

            user_dict = json.loads(user_data)

            # Validate required fields to avoid KeyError on corrupt data
            for field in ("user_id", "email", "name", "role", "auth_provider"):
                if field not in user_dict:
                    logger.warning("Corrupt user data in Redis: missing '%s'", field)
                    return None

            return User(
                user_id=user_dict["user_id"],
                email=user_dict["email"],
                name=user_dict["name"],
                role=UserRole(user_dict["role"]),
                auth_provider=AuthProvider(user_dict["auth_provider"]),
                organization_id=user_dict.get("organization_id"),
                team_id=user_dict.get("team_id"),
                created_at=_dt.fromisoformat(user_dict["created_at"]),
                last_login=_dt.fromisoformat(user_dict["last_login"])
                if user_dict.get("last_login")
                else None,
                is_active=user_dict.get("is_active", True),
                permissions=self.role_permissions.get(
                    UserRole(user_dict["role"]), set()
                ),
                metadata=user_dict.get("metadata", {}),
            )

        except Exception as e:
            logger.error(f"Error getting user {user_id}: {e}")
            return None

    async def _save_user(self, user: User):
        """Save user to Redis."""
        await self.oauth_provider._save_user(user)

    async def _update_last_login(self, user_id: str):
        """Update user's last login time."""
        await self.oauth_provider._update_last_login(user_id)

    # Backward compat: expose password helpers
    def _verify_password(self, password: str, password_hash: str) -> bool:
        return self.token_manager.verify_password(password, password_hash)

    def _hash_password(self, password: str) -> str:
        return self.token_manager.hash_password(password)

    def _is_token_blacklisted(self, token: str) -> bool:
        return self.token_manager._is_token_blacklisted(token)


# Singleton instance
auth_manager = AuthManager()
