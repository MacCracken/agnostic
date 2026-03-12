"""Tests for tenant data isolation — verifies tenants cannot access each other's data."""

import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


# ---------------------------------------------------------------------------
# Redis key isolation tests
# ---------------------------------------------------------------------------


class TestTenantKeyIsolation:
    """Verify tenant-scoped Redis keys prevent cross-tenant access."""

    def test_different_tenants_get_different_task_keys(self):
        """Two tenants storing the same task_id get different Redis keys."""
        from shared.database.tenants import TenantManager

        mgr = TenantManager()
        mgr.enabled = True

        key_a = mgr.task_key("tenant-a", "task-123")
        key_b = mgr.task_key("tenant-b", "task-123")

        assert key_a != key_b
        assert "tenant-a" in key_a
        assert "tenant-b" in key_b

    def test_different_tenants_get_different_session_keys(self):
        """Two tenants storing the same session_id get different Redis keys."""
        from shared.database.tenants import TenantManager

        mgr = TenantManager()
        mgr.enabled = True

        key_a = mgr.session_key("tenant-a", "sess-1")
        key_b = mgr.session_key("tenant-b", "sess-1")

        assert key_a != key_b

    def test_tenant_prefix_prevents_key_collision(self):
        """Tenant-scoped keys never collide with plain keys."""
        from shared.database.tenants import TenantManager

        mgr = TenantManager()
        mgr.enabled = True

        scoped = mgr.task_key("acme", "abc")
        mgr.enabled = False
        plain = mgr.task_key("acme", "abc")

        assert scoped != plain
        assert scoped.startswith("tenant:")
        assert plain.startswith("task:")

    def test_generic_redis_key_isolation(self):
        """get_redis_key produces unique keys per tenant."""
        from shared.database.tenants import TenantManager

        mgr = TenantManager()
        assert mgr.get_redis_key("a", "data") != mgr.get_redis_key("b", "data")

    def test_redis_prefix_unique_per_tenant(self):
        """get_redis_prefix is unique per tenant."""
        from shared.database.tenants import TenantManager

        mgr = TenantManager()
        assert mgr.get_redis_prefix("a") != mgr.get_redis_prefix("b")


# ---------------------------------------------------------------------------
# Helper to create an async-compatible mock redis backed by a dict store
# ---------------------------------------------------------------------------


def _make_async_redis_mock(store=None):
    """Create an AsyncMock redis that uses a dict as backing store."""
    if store is None:
        store = {}
    mock_redis = AsyncMock()

    async def async_setex(key, ttl, value):
        store[key] = value

    async def async_get(key):
        return store.get(key)

    async def async_incr(key):
        store[key] = store.get(key, 0) + 1
        return store[key]

    mock_redis.setex = AsyncMock(side_effect=async_setex)
    mock_redis.get = AsyncMock(side_effect=async_get)
    mock_redis.incr = AsyncMock(side_effect=async_incr)
    mock_redis.expire = AsyncMock()
    mock_redis.set = AsyncMock()
    return mock_redis, store


# ---------------------------------------------------------------------------
# Task submit/get isolation via API
# ---------------------------------------------------------------------------


class TestTaskEndpointIsolation:
    """Verify submit_task and get_task honour tenant boundaries."""

    @pytest.fixture
    def app(self):
        from fastapi import FastAPI

        from webgui.api import api_router

        app = FastAPI()
        app.include_router(api_router)
        return app

    def _make_client(self, app, tenant_id):
        """Create a TestClient authenticated as a specific tenant."""
        from fastapi.testclient import TestClient

        from webgui.api import get_current_user

        async def override():
            return {
                "user_id": f"user-{tenant_id}",
                "role": "admin",
                "tenant_id": tenant_id,
            }

        app.dependency_overrides[get_current_user] = override
        return TestClient(app)

    def _make_enabled_tenant_manager(self):
        """Create a TenantManager with multi-tenant enabled."""
        from shared.database.tenants import TenantManager

        mgr = TenantManager()
        mgr.enabled = True
        mgr.default_tenant_id = "default"
        return mgr

    def test_tenant_a_cannot_read_tenant_b_task(self, app):
        """A task created by tenant-a is not visible to tenant-b."""
        mock_redis, _store = _make_async_redis_mock()
        mgr = self._make_enabled_tenant_manager()

        with (
            patch("config.environment.config") as mock_config,
            patch("shared.database.tenants.tenant_manager", mgr),
        ):
            mock_config.get_async_redis_client.return_value = mock_redis

            # Tenant A submits a task
            client_a = self._make_client(app, "tenant-a")
            resp_a = client_a.post(
                "/api/v1/tasks",
                json={"title": "Test A", "description": "From tenant A"},
            )
            assert resp_a.status_code == 201
            task_id = resp_a.json()["task_id"]

            # Tenant A can read it
            resp_read_a = client_a.get(f"/api/v1/tasks/{task_id}")
            assert resp_read_a.status_code == 200

            # Tenant B cannot read it
            client_b = self._make_client(app, "tenant-b")
            resp_read_b = client_b.get(f"/api/v1/tasks/{task_id}")
            assert resp_read_b.status_code == 404

    def test_same_task_id_different_tenants_no_collision(self, app):
        """Two tenants can each store data under the same task_id without collision."""
        mock_redis, store = _make_async_redis_mock()
        mgr = self._make_enabled_tenant_manager()

        # Manually insert task records for same task_id but different tenants
        task_id = "shared-task-id"
        key_a = mgr.task_key("tenant-a", task_id)
        key_b = mgr.task_key("tenant-b", task_id)

        store[key_a] = json.dumps(
            {
                "task_id": task_id,
                "session_id": "sess-a",
                "status": "pending",
                "created_at": "2026-01-01T00:00:00",
                "updated_at": "2026-01-01T00:00:00",
                "result": None,
            }
        )
        store[key_b] = json.dumps(
            {
                "task_id": task_id,
                "session_id": "sess-b",
                "status": "completed",
                "created_at": "2026-01-01T00:00:00",
                "updated_at": "2026-01-01T00:00:00",
                "result": {"summary": "done"},
            }
        )

        with (
            patch("config.environment.config") as mock_config,
            patch("shared.database.tenants.tenant_manager", mgr),
        ):
            mock_config.get_async_redis_client.return_value = mock_redis

            # Tenant A sees pending
            client_a = self._make_client(app, "tenant-a")
            resp_a = client_a.get(f"/api/v1/tasks/{task_id}")
            assert resp_a.status_code == 200
            assert resp_a.json()["status"] == "pending"

            # Tenant B sees completed
            client_b = self._make_client(app, "tenant-b")
            resp_b = client_b.get(f"/api/v1/tasks/{task_id}")
            assert resp_b.status_code == 200
            assert resp_b.json()["status"] == "completed"


# ---------------------------------------------------------------------------
# Rate limit isolation tests
# ---------------------------------------------------------------------------


class TestRateLimitIsolation:
    """Verify rate limits are per-tenant, not global."""

    @pytest.mark.asyncio
    async def test_rate_limit_independent_per_tenant(self):
        """Exhausting tenant-a's rate limit does not affect tenant-b."""
        from shared.database.tenants import TenantManager

        mgr = TenantManager()
        mgr.enabled = True
        mgr.default_rate_limit = 2

        counters: dict[str, int] = {}

        mock_redis = AsyncMock()

        async def fake_incr(key):
            counters[key] = counters.get(key, 0) + 1
            return counters[key]

        mock_redis.incr = AsyncMock(side_effect=fake_incr)
        mock_redis.expire = AsyncMock()

        # Tenant A: 3 requests (exceeds limit of 2)
        assert await mgr.check_rate_limit(mock_redis, "tenant-a") is True  # 1
        assert await mgr.check_rate_limit(mock_redis, "tenant-a") is True  # 2
        assert (
            await mgr.check_rate_limit(mock_redis, "tenant-a") is False
        )  # 3 — blocked

        # Tenant B: still allowed
        assert await mgr.check_rate_limit(mock_redis, "tenant-b") is True

    def test_rate_limit_returns_429_on_task_submit(self):
        """POST /api/tasks returns 429 when tenant rate limit exceeded."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from webgui.api import api_router, get_current_user

        app = FastAPI()
        app.include_router(api_router)

        async def override():
            return {"user_id": "u1", "role": "admin", "tenant_id": "limited"}

        app.dependency_overrides[get_current_user] = override

        mock_redis = AsyncMock()
        mock_redis.incr.return_value = 1
        mock_redis.expire = AsyncMock()
        mock_redis.setex = AsyncMock()

        with (
            patch("config.environment.config") as mock_config,
            patch("shared.database.tenants.tenant_manager") as mock_mgr,
        ):
            mock_config.get_async_redis_client.return_value = mock_redis
            mock_mgr.enabled = True
            mock_mgr.default_tenant_id = "default"
            mock_mgr.task_key.return_value = "tenant:limited:task:xyz"
            mock_mgr.check_rate_limit = AsyncMock(return_value=False)

            client = TestClient(app)
            resp = client.post(
                "/api/v1/tasks",
                json={"title": "Test", "description": "Rate limited"},
            )
            assert resp.status_code == 429
            assert "Rate limit" in resp.json()["detail"]

        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# API key isolation tests
# ---------------------------------------------------------------------------


class TestAPIKeyIsolation:
    """Verify tenant API keys return correct tenant context."""

    @pytest.mark.asyncio
    async def test_api_key_returns_correct_tenant_id(self):
        """validate_tenant_api_key maps key to correct tenant."""
        import hashlib

        from shared.database.tenants import TenantManager

        mgr = TenantManager()

        key_a = "key-for-tenant-a"
        key_b = "key-for-tenant-b"
        hash_a = hashlib.sha256(key_a.encode()).hexdigest()
        hash_b = hashlib.sha256(key_b.encode()).hexdigest()

        store = {
            f"tenant_api_key:{hash_a}": json.dumps(
                {"tenant_id": "tenant-a", "role": "api_user"}
            ),
            f"tenant_api_key:{hash_b}": json.dumps(
                {"tenant_id": "tenant-b", "role": "api_user"}
            ),
        }

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(side_effect=lambda key: store.get(key))
        mock_redis.set = AsyncMock()

        result_a = await mgr.validate_tenant_api_key(mock_redis, key_a)
        result_b = await mgr.validate_tenant_api_key(mock_redis, key_b)

        assert result_a["tenant_id"] == "tenant-a"
        assert result_b["tenant_id"] == "tenant-b"

    @pytest.mark.asyncio
    async def test_api_key_for_one_tenant_does_not_auth_another(self):
        """A valid key for tenant-a does not grant access to tenant-b data."""
        import hashlib

        from shared.database.tenants import TenantManager

        mgr = TenantManager()
        mgr.enabled = True

        key = "only-for-tenant-a"
        key_hash = hashlib.sha256(key.encode()).hexdigest()

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(
            side_effect=lambda k: (
                json.dumps({"tenant_id": "tenant-a"})
                if k == f"tenant_api_key:{key_hash}"
                else None
            )
        )
        mock_redis.set = AsyncMock()

        result = await mgr.validate_tenant_api_key(mock_redis, key)
        assert result["tenant_id"] == "tenant-a"

        # The user dict has tenant-a, so task_key will scope to tenant-a
        task_key = mgr.task_key(result["tenant_id"], "task-1")
        assert "tenant-a" in task_key
        assert "tenant-b" not in task_key


# ---------------------------------------------------------------------------
# Quota isolation tests
# ---------------------------------------------------------------------------


class TestQuotaIsolation:
    """Verify quotas are evaluated per-tenant."""

    def test_quota_check_uses_tenant_limits(self):
        """Each tenant's own limits are used for quota checks."""
        from shared.database.tenants import TenantManager

        mgr = TenantManager()

        tenant_free = MagicMock()
        tenant_free.max_sessions = 5
        tenant_free.max_agents = 3
        tenant_free.max_storage_mb = 100

        tenant_pro = MagicMock()
        tenant_pro.max_sessions = 50
        tenant_pro.max_agents = 20
        tenant_pro.max_storage_mb = 10000

        # Free tenant at 5 sessions — blocked
        assert mgr.check_quota(tenant_free, "sessions", 5) is False

        # Pro tenant at 5 sessions — allowed
        assert mgr.check_quota(tenant_pro, "sessions", 5) is True
