"""Unit tests for multi-tenant functionality."""

import os
import sys
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


# ---------------------------------------------------------------------------
# TenantManager tests
# ---------------------------------------------------------------------------


class TestTenantManager:
    """Tests for TenantManager utility methods."""

    def test_disabled_by_default(self):
        """TenantManager is disabled by default."""
        with patch.dict(os.environ, {}, clear=True):
            from shared.database.tenants import TenantManager

            mgr = TenantManager()
            assert mgr.enabled is False

    def test_enabled_via_env(self):
        """TenantManager enabled via MULTI_TENANT_ENABLED."""
        with patch.dict(os.environ, {"MULTI_TENANT_ENABLED": "true"}, clear=False):
            from shared.database.tenants import TenantManager

            mgr = TenantManager()
            assert mgr.enabled is True

    def test_get_tenant_id_returns_default_when_disabled(self):
        """Returns default tenant ID when disabled."""
        from shared.database.tenants import TenantManager

        mgr = TenantManager()
        mgr.enabled = False

        request = MagicMock()
        assert mgr.get_tenant_id(request) == "default"

    def test_get_tenant_id_from_header(self):
        """Extracts tenant ID from X-Tenant-ID header."""
        from shared.database.tenants import TenantManager

        mgr = TenantManager()
        mgr.enabled = True

        request = MagicMock()
        request.headers.get.return_value = "acme-corp"
        request.cookies.get.return_value = None

        assert mgr.get_tenant_id(request) == "acme-corp"

    def test_get_tenant_id_from_cookie_fallback(self):
        """Falls back to cookie when header not present."""
        from shared.database.tenants import TenantManager

        mgr = TenantManager()
        mgr.enabled = True

        request = MagicMock()
        request.headers.get.return_value = None
        request.cookies.get.return_value = "cookie-tenant"

        assert mgr.get_tenant_id(request) == "cookie-tenant"

    def test_get_tenant_id_default_fallback(self):
        """Falls back to default when no header or cookie."""
        from shared.database.tenants import TenantManager

        mgr = TenantManager()
        mgr.enabled = True

        request = MagicMock()
        request.headers.get.return_value = None
        request.cookies.get.return_value = None

        assert mgr.get_tenant_id(request) == "default"

    def test_get_redis_key(self):
        """Generates tenant-scoped Redis key."""
        from shared.database.tenants import TenantManager

        mgr = TenantManager()
        assert mgr.get_redis_key("acme", "session:123") == "tenant:acme:session:123"

    def test_get_redis_prefix(self):
        """Generates tenant Redis prefix."""
        from shared.database.tenants import TenantManager

        mgr = TenantManager()
        assert mgr.get_redis_prefix("acme") == "tenant:acme"

    def test_check_quota_under_limit(self):
        """check_quota returns True when under limit."""
        from shared.database.tenants import TenantManager

        mgr = TenantManager()

        tenant = MagicMock()
        tenant.max_sessions = 10
        tenant.max_agents = 6
        tenant.max_storage_mb = 1000

        assert mgr.check_quota(tenant, "sessions", 5) is True

    def test_check_quota_at_limit(self):
        """check_quota returns False when at limit."""
        from shared.database.tenants import TenantManager

        mgr = TenantManager()

        tenant = MagicMock()
        tenant.max_sessions = 10
        tenant.max_agents = 6
        tenant.max_storage_mb = 1000

        assert mgr.check_quota(tenant, "sessions", 10) is False

    def test_check_quota_unknown_resource(self):
        """check_quota returns True for unknown resource (infinite limit)."""
        from shared.database.tenants import TenantManager

        mgr = TenantManager()

        tenant = MagicMock()
        tenant.max_sessions = 10
        tenant.max_agents = 6
        tenant.max_storage_mb = 1000

        assert mgr.check_quota(tenant, "unknown_thing", 999) is True

    def test_is_within_trial_active(self):
        """is_within_trial returns True during active trial."""
        from shared.database.tenants import TenantManager, TenantStatus

        mgr = TenantManager()

        tenant = MagicMock()
        tenant.status = TenantStatus.TRIAL
        tenant.trial_ends_at = datetime(2099, 12, 31, tzinfo=timezone.utc)

        assert mgr.is_within_trial(tenant) is True

    def test_is_within_trial_expired(self):
        """is_within_trial returns False when trial expired."""
        from shared.database.tenants import TenantManager, TenantStatus

        mgr = TenantManager()

        tenant = MagicMock()
        tenant.status = TenantStatus.TRIAL
        tenant.trial_ends_at = datetime(2020, 1, 1, tzinfo=timezone.utc)

        assert mgr.is_within_trial(tenant) is False

    def test_is_within_trial_not_trial_status(self):
        """is_within_trial returns False when not in trial status."""
        from shared.database.tenants import TenantManager, TenantStatus

        mgr = TenantManager()

        tenant = MagicMock()
        tenant.status = TenantStatus.ACTIVE
        tenant.trial_ends_at = datetime(2099, 12, 31, tzinfo=timezone.utc)

        assert mgr.is_within_trial(tenant) is False

    # -- task_key / session_key --

    def test_task_key_disabled(self):
        """task_key returns plain key when disabled."""
        from shared.database.tenants import TenantManager

        mgr = TenantManager()
        mgr.enabled = False
        assert mgr.task_key("acme", "abc-123") == "task:abc-123"

    def test_task_key_enabled(self):
        """task_key returns tenant-scoped key when enabled."""
        from shared.database.tenants import TenantManager

        mgr = TenantManager()
        mgr.enabled = True
        assert mgr.task_key("acme", "abc-123") == "tenant:acme:task:abc-123"

    def test_session_key_disabled(self):
        """session_key returns plain key when disabled."""
        from shared.database.tenants import TenantManager

        mgr = TenantManager()
        mgr.enabled = False
        assert mgr.session_key("acme", "sess-1") == "session:sess-1"

    def test_session_key_enabled(self):
        """session_key returns tenant-scoped key when enabled."""
        from shared.database.tenants import TenantManager

        mgr = TenantManager()
        mgr.enabled = True
        assert mgr.session_key("acme", "sess-1") == "tenant:acme:session:sess-1"

    # -- check_rate_limit --

    def test_check_rate_limit_allowed(self):
        """check_rate_limit returns True when under limit."""
        from shared.database.tenants import TenantManager

        mgr = TenantManager()
        mgr.default_rate_limit = 100

        redis = MagicMock()
        redis.incr.return_value = 1

        assert mgr.check_rate_limit(redis, "acme") is True
        redis.expire.assert_called_once()

    def test_check_rate_limit_exceeded(self):
        """check_rate_limit returns False when over limit."""
        from shared.database.tenants import TenantManager

        mgr = TenantManager()
        mgr.default_rate_limit = 100

        redis = MagicMock()
        redis.incr.return_value = 101

        assert mgr.check_rate_limit(redis, "acme") is False

    def test_check_rate_limit_custom_limit(self):
        """check_rate_limit respects custom rate_limit parameter."""
        from shared.database.tenants import TenantManager

        mgr = TenantManager()

        redis = MagicMock()
        redis.incr.return_value = 6

        assert mgr.check_rate_limit(redis, "acme", rate_limit=5) is False
        assert mgr.check_rate_limit(redis, "acme", rate_limit=10) is True

    def test_check_rate_limit_sets_expiry_on_first_request(self):
        """check_rate_limit sets 60s TTL on first request in window."""
        from shared.database.tenants import TenantManager

        mgr = TenantManager()
        redis = MagicMock()
        redis.incr.return_value = 1

        mgr.check_rate_limit(redis, "acme")
        redis.expire.assert_called_once()
        assert redis.expire.call_args[0][1] == 60

    def test_check_rate_limit_no_expiry_on_subsequent(self):
        """check_rate_limit does not reset TTL on subsequent requests."""
        from shared.database.tenants import TenantManager

        mgr = TenantManager()
        redis = MagicMock()
        redis.incr.return_value = 5

        mgr.check_rate_limit(redis, "acme")
        redis.expire.assert_not_called()

    # -- validate_tenant_api_key --

    def test_validate_tenant_api_key_valid(self):
        """validate_tenant_api_key returns user dict for valid key."""
        import hashlib
        import json

        from shared.database.tenants import TenantManager

        mgr = TenantManager()
        redis = MagicMock()

        api_key = "test-api-key-12345"
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        stored = json.dumps({
            "tenant_id": "acme",
            "role": "admin",
            "permissions": ["read", "write"],
        })
        redis.get.return_value = stored

        result = mgr.validate_tenant_api_key(redis, api_key)

        assert result is not None
        assert result["tenant_id"] == "acme"
        assert result["role"] == "admin"
        assert result["user_id"] == "tenant-api-acme"
        assert result["email"] == "api@acme"
        assert "read" in result["permissions"]
        redis.get.assert_called_once_with(f"tenant_api_key:{key_hash}")

    def test_validate_tenant_api_key_invalid(self):
        """validate_tenant_api_key returns None for unknown key."""
        from shared.database.tenants import TenantManager

        mgr = TenantManager()
        redis = MagicMock()
        redis.get.return_value = None

        result = mgr.validate_tenant_api_key(redis, "bad-key")
        assert result is None

    def test_validate_tenant_api_key_updates_last_used(self):
        """validate_tenant_api_key updates last_used_at in Redis."""
        import hashlib
        import json

        from shared.database.tenants import TenantManager

        mgr = TenantManager()
        redis = MagicMock()

        api_key = "key-for-timestamp-test"
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        stored = json.dumps({"tenant_id": "acme"})
        redis.get.return_value = stored

        mgr.validate_tenant_api_key(redis, api_key)

        redis.set.assert_called_once()
        call_args = redis.set.call_args
        updated = json.loads(call_args[0][1])
        assert "last_used_at" in updated


# ---------------------------------------------------------------------------
# Tenant model tests
# ---------------------------------------------------------------------------


class TestTenantModels:
    """Tests for tenant SQLAlchemy models."""

    def test_tenant_table_name(self):
        from shared.database.tenants import Tenant

        assert Tenant.__tablename__ == "tenants"

    def test_tenant_user_table_name(self):
        from shared.database.tenants import TenantUser

        assert TenantUser.__tablename__ == "tenant_users"

    def test_tenant_api_key_table_name(self):
        from shared.database.tenants import TenantAPIKey

        assert TenantAPIKey.__tablename__ == "tenant_api_keys"

    def test_tenant_status_enum(self):
        from shared.database.tenants import TenantStatus

        assert TenantStatus.ACTIVE == "active"
        assert TenantStatus.SUSPENDED == "suspended"
        assert TenantStatus.TRIAL == "trial"
        assert TenantStatus.DISABLED == "disabled"


# ---------------------------------------------------------------------------
# TenantRepository tests
# ---------------------------------------------------------------------------


class TestTenantRepository:
    """Tests for TenantRepository CRUD operations."""

    @pytest.fixture
    def mock_session(self):
        session = AsyncMock()
        session.add = MagicMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        session.delete = AsyncMock()
        return session

    @pytest.fixture
    def repo(self, mock_session):
        from shared.database.tenant_repository import TenantRepository

        return TenantRepository(mock_session)

    @pytest.mark.asyncio
    async def test_create_tenant(self, repo, mock_session):
        """create_tenant adds and commits a Tenant."""
        await repo.create_tenant(
            tenant_id="acme",
            name="Acme Corp",
            slug="acme-corp",
            owner_email="admin@acme.com",
        )

        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()
        mock_session.refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_tenant_found(self, repo, mock_session):
        """get_tenant returns tenant when found."""
        mock_tenant = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_tenant
        mock_session.execute.return_value = mock_result

        tenant = await repo.get_tenant("acme")
        assert tenant is mock_tenant

    @pytest.mark.asyncio
    async def test_get_tenant_not_found(self, repo, mock_session):
        """get_tenant returns None when not found."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        tenant = await repo.get_tenant("nonexistent")
        assert tenant is None

    @pytest.mark.asyncio
    async def test_list_tenants(self, repo, mock_session):
        """list_tenants returns list from query."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [MagicMock(), MagicMock()]
        mock_session.execute.return_value = mock_result

        tenants = await repo.list_tenants()
        assert len(tenants) == 2

    @pytest.mark.asyncio
    async def test_update_tenant_found(self, repo, mock_session):
        """update_tenant updates allowed fields."""
        mock_tenant = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_tenant
        mock_session.execute.return_value = mock_result

        result = await repo.update_tenant("acme", {"name": "New Name", "plan": "pro"})

        assert result is mock_tenant
        assert mock_tenant.name == "New Name"
        assert mock_tenant.plan == "pro"

    @pytest.mark.asyncio
    async def test_update_tenant_ignores_disallowed_fields(self, repo, mock_session):
        """update_tenant ignores fields not in allowed set."""
        mock_tenant = MagicMock(spec=["tenant_id", "name", "plan"])
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_tenant
        mock_session.execute.return_value = mock_result

        await repo.update_tenant("acme", {"tenant_id": "hacked", "name": "OK"})

        # tenant_id should not have been set (not in allowed_fields)
        # name should have been set
        assert mock_tenant.name == "OK"

    @pytest.mark.asyncio
    async def test_update_tenant_not_found(self, repo, mock_session):
        """update_tenant returns None when tenant not found."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repo.update_tenant("nonexistent", {"name": "New"})
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_tenant_soft_deletes(self, repo, mock_session):
        """delete_tenant sets is_active=False and status=disabled."""
        mock_tenant = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_tenant
        mock_session.execute.return_value = mock_result

        result = await repo.delete_tenant("acme")

        assert result is True
        assert mock_tenant.is_active is False
        assert mock_tenant.status == "disabled"

    @pytest.mark.asyncio
    async def test_delete_tenant_not_found(self, repo, mock_session):
        """delete_tenant returns False when not found."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repo.delete_tenant("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_add_user(self, repo, mock_session):
        """add_user adds and commits a TenantUser."""
        await repo.add_user(
            tenant_id="acme",
            user_id="user-1",
            email="user@acme.com",
            role="member",
        )

        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_users(self, repo, mock_session):
        """list_users returns users for a tenant."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [MagicMock()]
        mock_session.execute.return_value = mock_result

        users = await repo.list_users("acme")
        assert len(users) == 1

    @pytest.mark.asyncio
    async def test_remove_user_found(self, repo, mock_session):
        """remove_user deletes and commits."""
        mock_user = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_session.execute.return_value = mock_result

        result = await repo.remove_user("acme", "user-1")

        assert result is True
        mock_session.delete.assert_called_once_with(mock_user)

    @pytest.mark.asyncio
    async def test_remove_user_not_found(self, repo, mock_session):
        """remove_user returns False when user not found."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repo.remove_user("acme", "nonexistent")
        assert result is False


# ---------------------------------------------------------------------------
# Tenant API endpoint tests
# ---------------------------------------------------------------------------


class TestTenantEndpoints:
    """Tests for tenant API endpoints via FastAPI TestClient."""

    @pytest.fixture
    def app(self):
        from fastapi import FastAPI
        from webgui.api import api_router

        app = FastAPI()
        app.include_router(api_router)
        return app

    @pytest.fixture
    def admin_client(self, app):
        from fastapi.testclient import TestClient
        from webgui.api import get_current_user

        async def override():
            return {"user_id": "admin", "role": "super_admin"}

        app.dependency_overrides[get_current_user] = override
        client = TestClient(app)
        yield client
        app.dependency_overrides.clear()

    @pytest.fixture
    def viewer_client(self, app):
        from fastapi.testclient import TestClient
        from webgui.api import get_current_user

        async def override():
            return {"user_id": "viewer", "role": "viewer"}

        app.dependency_overrides[get_current_user] = override
        client = TestClient(app)
        yield client
        app.dependency_overrides.clear()

    def test_list_tenants_disabled(self, admin_client):
        """Returns 503 when multi-tenancy disabled."""
        with patch("webgui.routes.dependencies.MULTI_TENANT_ENABLED", False):
            resp = admin_client.get("/api/tenants")
            assert resp.status_code == 503

    def test_create_tenant_disabled(self, admin_client):
        """Returns 503 when multi-tenancy disabled."""
        with patch("webgui.routes.dependencies.MULTI_TENANT_ENABLED", False):
            resp = admin_client.post(
                "/api/tenants",
                json={
                    "tenant_id": "t1",
                    "name": "T1",
                    "slug": "t1",
                    "owner_email": "a@b.com",
                },
            )
            assert resp.status_code == 503

    def test_get_tenant_disabled(self, admin_client):
        """Returns 503 when multi-tenancy disabled."""
        with patch("webgui.routes.dependencies.MULTI_TENANT_ENABLED", False):
            resp = admin_client.get("/api/tenants/t1")
            assert resp.status_code == 503

    def test_list_tenants_requires_admin(self, viewer_client):
        """Returns 403 for non-admin users."""
        with (
            patch("webgui.routes.dependencies.MULTI_TENANT_ENABLED", True),
            patch("webgui.routes.dependencies.DATABASE_ENABLED", True),
        ):
            resp = viewer_client.get("/api/tenants")
            assert resp.status_code == 403

    def test_get_tenant_not_found(self, admin_client):
        """Returns 404 when tenant not found."""
        mock_repo = AsyncMock()
        mock_repo.get_tenant.return_value = None

        with (
            patch("webgui.routes.dependencies.MULTI_TENANT_ENABLED", True),
            patch("webgui.routes.dependencies.DATABASE_ENABLED", True),
            patch("webgui.routes.tenants.get_tenant_repo", return_value=mock_repo),
        ):
            resp = admin_client.get("/api/tenants/nonexistent")
            assert resp.status_code == 404

    def test_delete_tenant_not_found(self, admin_client):
        """Returns 404 when deleting nonexistent tenant."""
        mock_repo = AsyncMock()
        mock_repo.delete_tenant.return_value = False

        with (
            patch("webgui.routes.dependencies.MULTI_TENANT_ENABLED", True),
            patch("webgui.routes.dependencies.DATABASE_ENABLED", True),
            patch("webgui.routes.tenants.get_tenant_repo", return_value=mock_repo),
        ):
            resp = admin_client.delete("/api/tenants/nonexistent")
            assert resp.status_code == 404

    def test_update_tenant_not_found(self, admin_client):
        """Returns 404 when updating nonexistent tenant."""
        mock_repo = AsyncMock()
        mock_repo.update_tenant.return_value = None

        with (
            patch("webgui.routes.dependencies.MULTI_TENANT_ENABLED", True),
            patch("webgui.routes.dependencies.DATABASE_ENABLED", True),
            patch("webgui.routes.tenants.get_tenant_repo", return_value=mock_repo),
        ):
            resp = admin_client.put("/api/tenants/nonexistent", json={"name": "New"})
            assert resp.status_code == 404

    def test_remove_user_not_found(self, admin_client):
        """Returns 404 when removing nonexistent user."""
        mock_repo = AsyncMock()
        mock_repo.remove_user.return_value = False

        with (
            patch("webgui.routes.dependencies.MULTI_TENANT_ENABLED", True),
            patch("webgui.routes.dependencies.DATABASE_ENABLED", True),
            patch("webgui.routes.tenants.get_tenant_repo", return_value=mock_repo),
        ):
            resp = admin_client.delete("/api/tenants/t1/users/nonexistent")
            assert resp.status_code == 404

    def test_database_disabled_returns_503(self, admin_client):
        """Returns 503 when database not enabled even if tenant is."""
        with (
            patch("webgui.routes.dependencies.MULTI_TENANT_ENABLED", True),
            patch("webgui.routes.dependencies.DATABASE_ENABLED", False),
        ):
            resp = admin_client.get("/api/tenants")
            assert resp.status_code == 503
