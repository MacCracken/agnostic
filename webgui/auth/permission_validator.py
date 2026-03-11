"""Permission and resource access validation."""

import json
import logging
from typing import Any

from webgui.auth.models import Permission, User, UserRole

logger = logging.getLogger(__name__)


# Default role → permission mappings
ROLE_PERMISSIONS: dict[UserRole, set[Permission]] = {
    UserRole.SUPER_ADMIN: {
        Permission.SESSIONS_READ,
        Permission.SESSIONS_WRITE,
        Permission.SESSIONS_DELETE,
        Permission.AGENTS_CONTROL,
        Permission.REPORTS_GENERATE,
        Permission.REPORTS_EXPORT,
        Permission.USERS_MANAGE,
        Permission.SYSTEM_CONFIGURE,
        Permission.API_ACCESS,
    },
    UserRole.ORG_ADMIN: {
        Permission.SESSIONS_READ,
        Permission.SESSIONS_WRITE,
        Permission.SESSIONS_DELETE,
        Permission.AGENTS_CONTROL,
        Permission.REPORTS_GENERATE,
        Permission.REPORTS_EXPORT,
        Permission.USERS_MANAGE,
        Permission.API_ACCESS,
    },
    UserRole.TEAM_LEAD: {
        Permission.SESSIONS_READ,
        Permission.SESSIONS_WRITE,
        Permission.AGENTS_CONTROL,
        Permission.REPORTS_GENERATE,
        Permission.REPORTS_EXPORT,
    },
    UserRole.QA_ENGINEER: {
        Permission.SESSIONS_READ,
        Permission.SESSIONS_WRITE,
        Permission.AGENTS_CONTROL,
        Permission.REPORTS_GENERATE,
    },
    UserRole.VIEWER: {Permission.SESSIONS_READ, Permission.REPORTS_GENERATE},
    UserRole.API_USER: {
        Permission.SESSIONS_READ,
        Permission.SESSIONS_WRITE,
        Permission.API_ACCESS,
    },
}


class PermissionValidator:
    """Validates user permissions and resource-level access."""

    def __init__(self, redis_client: Any, role_permissions: dict | None = None):
        self.redis_client = redis_client
        self.role_permissions = role_permissions or ROLE_PERMISSIONS

    async def check_permission(self, user: User, permission: Permission) -> bool:
        """Check if user has specific permission."""
        return permission in user.permissions

    async def check_resource_access(
        self, user: User, resource_type: str, resource_id: str, action: str
    ) -> bool:
        """Check if user can access specific resource."""
        try:
            required_permission = f"{resource_type}:{action}"
            if not any(perm.value == required_permission for perm in user.permissions):
                return False

            if resource_type == "sessions":
                return await self._check_session_access(user, resource_id, action)
            elif resource_type == "reports":
                return await self._check_report_access(user, resource_id, action)
            elif resource_type == "users":
                return await self._check_user_access(user, resource_id, action)

            return True

        except Exception as e:
            logger.error(f"Error checking resource access: {e}")
            return False

    async def _check_session_access(
        self, user: User, session_id: str, action: str
    ) -> bool:
        """Check session-specific access."""
        try:
            session_key = f"session:{session_id}:info"
            session_data = await self.redis_client.get(session_key)

            if session_data:
                session_info = json.loads(session_data)

                if session_info.get("user_id") == user.user_id:
                    return True

                if user.role == UserRole.TEAM_LEAD:
                    if session_info.get("team_id") == user.team_id:
                        return True

                if user.role == UserRole.ORG_ADMIN:
                    if session_info.get("organization_id") == user.organization_id:
                        return True

                if user.role == UserRole.SUPER_ADMIN:
                    return True

            return False

        except Exception as e:
            logger.error(f"Error checking session access: {e}")
            return False

    async def _check_report_access(
        self, user: User, report_id: str, action: str
    ) -> bool:
        """Check report-specific access."""
        return True  # Simplified for now

    async def _check_user_access(
        self, user: User, target_user_id: str, action: str
    ) -> bool:
        """Check user management access."""
        if user.user_id == target_user_id:
            return True

        if user.role == UserRole.TEAM_LEAD and action in ["read"]:
            return True

        if user.role == UserRole.ORG_ADMIN:
            return True

        if user.role == UserRole.SUPER_ADMIN:
            return True

        return False
