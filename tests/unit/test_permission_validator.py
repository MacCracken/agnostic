"""Tests for webgui/auth/permission_validator.py — PermissionValidator, RBAC."""

import json
import os
import sys
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from webgui.auth.models import AuthProvider, Permission, User, UserRole
from webgui.auth.permission_validator import ROLE_PERMISSIONS, PermissionValidator


def _make_user(**overrides):
    defaults = {
        "user_id": "u1",
        "email": "test@example.com",
        "name": "Test User",
        "role": UserRole.QA_ENGINEER,
        "auth_provider": AuthProvider.LOCAL,
        "organization_id": "org1",
        "team_id": "team1",
        "created_at": datetime.now(UTC),
        "last_login": None,
        "is_active": True,
        "permissions": ROLE_PERMISSIONS[UserRole.QA_ENGINEER],
        "metadata": {},
    }
    defaults.update(overrides)
    return User(**defaults)


def _make_validator(redis=None):
    return PermissionValidator(redis_client=redis or MagicMock())


class TestRolePermissions:
    def test_super_admin_has_all(self):
        perms = ROLE_PERMISSIONS[UserRole.SUPER_ADMIN]
        assert Permission.SYSTEM_CONFIGURE in perms
        assert Permission.USERS_MANAGE in perms
        assert Permission.SESSIONS_DELETE in perms

    def test_viewer_is_minimal(self):
        perms = ROLE_PERMISSIONS[UserRole.VIEWER]
        assert perms == {Permission.SESSIONS_READ, Permission.REPORTS_GENERATE}

    def test_api_user_has_api_access(self):
        perms = ROLE_PERMISSIONS[UserRole.API_USER]
        assert Permission.API_ACCESS in perms
        assert Permission.SYSTEM_CONFIGURE not in perms

    def test_org_admin_no_system_configure(self):
        perms = ROLE_PERMISSIONS[UserRole.ORG_ADMIN]
        assert Permission.SYSTEM_CONFIGURE not in perms
        assert Permission.USERS_MANAGE in perms


class TestCheckPermission:
    @pytest.mark.asyncio
    async def test_user_has_permission(self):
        user = _make_user()
        v = _make_validator()
        assert await v.check_permission(user, Permission.SESSIONS_READ) is True

    @pytest.mark.asyncio
    async def test_user_lacks_permission(self):
        user = _make_user()
        v = _make_validator()
        assert await v.check_permission(user, Permission.SYSTEM_CONFIGURE) is False


class TestCheckResourceAccess:
    @pytest.mark.asyncio
    async def test_session_owner_access(self):
        redis = AsyncMock()
        session_info = {"user_id": "u1", "team_id": "team1"}
        redis.get.return_value = json.dumps(session_info).encode()
        user = _make_user()
        v = _make_validator(redis)
        result = await v.check_resource_access(user, "sessions", "s1", "read")
        assert result is True

    @pytest.mark.asyncio
    async def test_session_non_owner_denied(self):
        redis = AsyncMock()
        session_info = {"user_id": "other-user", "team_id": "other-team"}
        redis.get.return_value = json.dumps(session_info).encode()
        user = _make_user()
        v = _make_validator(redis)
        result = await v.check_resource_access(user, "sessions", "s1", "read")
        assert result is False

    @pytest.mark.asyncio
    async def test_team_lead_same_team_access(self):
        redis = AsyncMock()
        session_info = {"user_id": "other-user", "team_id": "team1"}
        redis.get.return_value = json.dumps(session_info).encode()
        user = _make_user(
            role=UserRole.TEAM_LEAD,
            permissions=ROLE_PERMISSIONS[UserRole.TEAM_LEAD],
        )
        result = await _make_validator(redis).check_resource_access(
            user, "sessions", "s1", "read"
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_org_admin_same_org_access(self):
        redis = AsyncMock()
        session_info = {
            "user_id": "other",
            "team_id": "other-team",
            "organization_id": "org1",
        }
        redis.get.return_value = json.dumps(session_info).encode()
        user = _make_user(
            role=UserRole.ORG_ADMIN,
            permissions=ROLE_PERMISSIONS[UserRole.ORG_ADMIN],
        )
        result = await _make_validator(redis).check_resource_access(
            user, "sessions", "s1", "read"
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_super_admin_always_access(self):
        redis = AsyncMock()
        session_info = {
            "user_id": "other",
            "team_id": "other",
            "organization_id": "other",
        }
        redis.get.return_value = json.dumps(session_info).encode()
        user = _make_user(
            role=UserRole.SUPER_ADMIN,
            permissions=ROLE_PERMISSIONS[UserRole.SUPER_ADMIN],
        )
        result = await _make_validator(redis).check_resource_access(
            user, "sessions", "s1", "read"
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_missing_permission_denied(self):
        """User without sessions:read can't access sessions."""
        user = _make_user(permissions=set())
        v = _make_validator()
        result = await v.check_resource_access(user, "sessions", "s1", "read")
        assert result is False

    @pytest.mark.asyncio
    async def test_report_access_always_true(self):
        user = _make_user(
            role=UserRole.TEAM_LEAD,
            permissions=ROLE_PERMISSIONS[UserRole.TEAM_LEAD],
        )
        v = _make_validator()
        result = await v.check_resource_access(user, "reports", "r1", "generate")
        assert result is True


class TestCheckUserAccess:
    @pytest.mark.asyncio
    async def test_self_access(self):
        user = _make_user(permissions=ROLE_PERMISSIONS[UserRole.ORG_ADMIN])
        v = _make_validator()
        result = await v.check_resource_access(user, "users", "u1", "manage")
        assert result is True

    @pytest.mark.asyncio
    async def test_team_lead_no_manage(self):
        """Team lead lacks USERS_MANAGE so can't manage other users."""
        user = _make_user(
            role=UserRole.TEAM_LEAD,
            permissions=ROLE_PERMISSIONS[UserRole.TEAM_LEAD],
        )
        v = _make_validator()
        result = await v.check_resource_access(user, "users", "other-user", "manage")
        assert result is False

    @pytest.mark.asyncio
    async def test_org_admin_manages_users(self):
        user = _make_user(
            role=UserRole.ORG_ADMIN,
            permissions=ROLE_PERMISSIONS[UserRole.ORG_ADMIN],
        )
        v = _make_validator()
        result = await v.check_resource_access(user, "users", "other-user", "manage")
        assert result is True

    @pytest.mark.asyncio
    async def test_viewer_cannot_manage(self):
        user = _make_user(
            role=UserRole.VIEWER,
            permissions=ROLE_PERMISSIONS[UserRole.VIEWER],
        )
        v = _make_validator()
        result = await v.check_resource_access(user, "users", "other-user", "manage")
        assert result is False

    @pytest.mark.asyncio
    async def test_qa_engineer_cannot_manage_others(self):
        """QA engineer doesn't have users:manage."""
        user = _make_user()
        v = _make_validator()
        result = await v.check_resource_access(user, "users", "other-user", "manage")
        assert result is False
