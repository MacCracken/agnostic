import json
import os
import sys
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

try:
    from webgui.auth import (
        AuthManager,
        AuthProvider,
        AuthToken,
        Permission,
        User,
        UserRole,
        create_api_key,
        list_api_keys,
        revoke_api_key,
    )
except ImportError:
    pytest.skip("webgui.auth module not available", allow_module_level=True)


@pytest.fixture()
def async_mock_redis():
    """Async mock Redis client for auth tests."""
    mock_client = AsyncMock()
    mock_client.get.return_value = None
    mock_client.set.return_value = True
    mock_client.exists.return_value = False
    mock_client.delete.return_value = True
    mock_client.setex.return_value = True
    return mock_client


@pytest.fixture()
def auth_mgr(async_mock_redis):
    """Create AuthManager with mocked async Redis."""
    with patch("webgui.auth.config") as mock_config:
        mock_config.get_async_redis_client.return_value = async_mock_redis
        mgr = AuthManager()
    return mgr


class TestAuthManagerInit:
    """Tests for AuthManager initialization"""

    def test_default_init(self, async_mock_redis):
        with patch("webgui.auth.config") as mock_config:
            mock_config.get_async_redis_client.return_value = async_mock_redis
            mgr = AuthManager()
        assert mgr.access_token_expire_minutes == 15
        assert mgr.refresh_token_expire_days == 7
        assert mgr.secret_key is not None

    def test_production_requires_secret_key(self, async_mock_redis):
        with (
            patch("webgui.auth.config") as mock_config,
            patch.dict(
                os.environ, {"ENVIRONMENT": "production", "WEBGUI_SECRET_KEY": ""}
            ),
        ):
            mock_config.get_async_redis_client.return_value = async_mock_redis
            os.environ.pop("WEBGUI_SECRET_KEY", None)
            with pytest.raises(ValueError, match="WEBGUI_SECRET_KEY must be set"):
                AuthManager()

    def test_production_with_secret_key(self, async_mock_redis):
        with (
            patch("webgui.auth.config") as mock_config,
            patch.dict(
                os.environ,
                {
                    "ENVIRONMENT": "production",
                    "WEBGUI_SECRET_KEY": "test-secret-key-abc",
                },
            ),
        ):
            mock_config.get_async_redis_client.return_value = async_mock_redis
            mgr = AuthManager()
        assert mgr.secret_key == "test-secret-key-abc"


class TestRolePermissions:
    """Tests for role-permission mapping"""

    def test_super_admin_has_all_permissions(self, auth_mgr):
        perms = auth_mgr.role_permissions[UserRole.SUPER_ADMIN]
        assert Permission.USERS_MANAGE in perms
        assert Permission.SYSTEM_CONFIGURE in perms
        assert Permission.SESSIONS_DELETE in perms

    def test_viewer_has_limited_permissions(self, auth_mgr):
        perms = auth_mgr.role_permissions[UserRole.VIEWER]
        assert Permission.SESSIONS_READ in perms
        assert Permission.USERS_MANAGE not in perms
        assert Permission.SESSIONS_WRITE not in perms

    def test_qa_engineer_permissions(self, auth_mgr):
        perms = auth_mgr.role_permissions[UserRole.QA_ENGINEER]
        assert Permission.SESSIONS_READ in perms
        assert Permission.SESSIONS_WRITE in perms
        assert Permission.AGENTS_CONTROL in perms
        assert Permission.SYSTEM_CONFIGURE not in perms


class TestTokens:
    """Tests for JWT token creation and verification"""

    @pytest.mark.asyncio
    async def test_create_tokens(self, auth_mgr):
        user = User(
            user_id="u1",
            email="test@example.com",
            name="Test User",
            role=UserRole.QA_ENGINEER,
            auth_provider=AuthProvider.LOCAL,
            organization_id=None,
            team_id=None,
            created_at=datetime.now(),
            last_login=None,
            is_active=True,
            permissions=auth_mgr.role_permissions[UserRole.QA_ENGINEER],
            metadata={},
        )
        tokens = await auth_mgr.create_tokens(user)
        assert isinstance(tokens, AuthToken)
        assert tokens.access_token
        assert tokens.refresh_token
        assert tokens.token_type == "bearer"

    @pytest.mark.asyncio
    async def test_verify_valid_token(self, auth_mgr, async_mock_redis):
        # Ensure token is not blacklisted
        async_mock_redis.exists.return_value = False
        user = User(
            user_id="u2",
            email="verify@example.com",
            name="Verify User",
            role=UserRole.VIEWER,
            auth_provider=AuthProvider.LOCAL,
            organization_id=None,
            team_id=None,
            created_at=datetime.now(),
            last_login=None,
            is_active=True,
            permissions=auth_mgr.role_permissions[UserRole.VIEWER],
            metadata={},
        )
        tokens = await auth_mgr.create_tokens(user)
        payload = await auth_mgr.verify_token(tokens.access_token)
        assert payload is not None
        assert payload["user_id"] == "u2"
        assert payload["email"] == "verify@example.com"

    @pytest.mark.asyncio
    async def test_verify_invalid_token(self, auth_mgr):
        payload = await auth_mgr.verify_token("invalid.token.here")
        assert payload is None

    @pytest.mark.asyncio
    async def test_verify_blacklisted_token(self, auth_mgr, async_mock_redis):
        user = User(
            user_id="u3",
            email="bl@example.com",
            name="BL User",
            role=UserRole.VIEWER,
            auth_provider=AuthProvider.LOCAL,
            organization_id=None,
            team_id=None,
            created_at=datetime.now(),
            last_login=None,
            is_active=True,
            permissions=set(),
            metadata={},
        )
        tokens = await auth_mgr.create_tokens(user)
        # Simulate blacklisted token
        async_mock_redis.exists.return_value = True
        payload = await auth_mgr.verify_token(tokens.access_token)
        assert payload is None


# ---------------------------------------------------------------------------
# P2 — API key authentication via X-API-Key header
# ---------------------------------------------------------------------------


class TestApiKeyAuth:
    """Tests for get_current_user with X-API-Key header."""

    def _make_app_with_authed_route(self):
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient

            from webgui.api import api_router
        except ImportError:
            return None, None

        test_app = FastAPI()
        test_app.include_router(api_router)

        @test_app.get("/api/v1/auth/me")
        async def me(user=None):
            return user or {}

        return test_app, TestClient(test_app)

    @patch.dict(os.environ, {"AGNOSTIC_API_KEY": "test-static-key-123"})
    def test_static_env_key_valid(self):
        """Valid AGNOSTIC_API_KEY in X-API-Key header -> 200."""
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient

            from webgui.api import api_router
        except ImportError:
            pytest.skip("webgui.api not available")

        test_app = FastAPI()
        test_app.include_router(api_router)
        client = TestClient(test_app)

        with patch("webgui.api.auth_manager"):
            resp = client.get(
                "/api/v1/auth/me",
                headers={"X-API-Key": "test-static-key-123"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("user_id") == "api-key-user"
        assert data.get("email") == "api@agnostic"

    @patch.dict(os.environ, {"AGNOSTIC_API_KEY": "test-static-key-123"})
    def test_static_env_key_invalid(self):
        """Wrong key in X-API-Key header -> 401."""
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient

            from webgui.api import api_router
        except ImportError:
            pytest.skip("webgui.api not available")

        test_app = FastAPI()
        test_app.include_router(api_router)
        client = TestClient(test_app)

        with patch("config.environment.config") as mock_config:
            mock_redis = AsyncMock()
            mock_redis.get.return_value = None
            mock_config.get_async_redis_client.return_value = mock_redis

            resp = client.get(
                "/api/v1/auth/me",
                headers={"X-API-Key": "wrong-key"},
            )
        assert resp.status_code == 401

    def test_no_auth_returns_401(self):
        """No X-API-Key and no Bearer -> 401."""
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient

            from webgui.api import api_router
        except ImportError:
            pytest.skip("webgui.api not available")

        test_app = FastAPI()
        test_app.include_router(api_router)
        client = TestClient(test_app)

        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# P2 — API key management (create / list / revoke)
# ---------------------------------------------------------------------------


class TestApiKeyManagement:
    """Tests for create_api_key, list_api_keys, revoke_api_key helpers."""

    def _make_mock_redis(self):
        """Create an async-compatible mock redis backed by dict stores."""
        store: dict = {}
        sets: dict = {}

        mock_redis = AsyncMock()

        async def fake_get(key):
            val = store.get(key)
            return val.encode() if isinstance(val, str) else val

        async def fake_set(key, value):
            store[key] = value if isinstance(value, str) else value.decode()

        async def fake_sadd(key, *members):
            sets.setdefault(key, set()).update(members)

        async def fake_smembers(key):
            return {
                m.encode() if isinstance(m, str) else m for m in sets.get(key, set())
            }

        async def fake_delete(*keys):
            for k in keys:
                store.pop(k, None)

        async def fake_srem(key, *members):
            if key in sets:
                sets[key].discard(members[0] if members else None)

        mock_redis.get = AsyncMock(side_effect=fake_get)
        mock_redis.set = AsyncMock(side_effect=fake_set)
        mock_redis.sadd = AsyncMock(side_effect=fake_sadd)
        mock_redis.smembers = AsyncMock(side_effect=fake_smembers)
        mock_redis.delete = AsyncMock(side_effect=fake_delete)
        mock_redis.srem = AsyncMock(side_effect=fake_srem)
        mock_redis._store = store
        mock_redis._sets = sets
        return mock_redis

    @pytest.mark.asyncio
    async def test_create_returns_raw_key_and_id(self):
        mock_redis = self._make_mock_redis()
        raw_key, key_id, meta = await create_api_key(
            redis_client=mock_redis,
            description="test key",
            role="api_user",
            created_by="admin",
        )
        assert len(raw_key) > 20
        assert len(key_id) == 8
        assert meta["role"] == "api_user"
        assert meta["description"] == "test key"
        assert meta["created_by"] == "admin"
        assert "permissions" in meta

    @pytest.mark.asyncio
    async def test_create_stores_hash_not_raw(self):
        """Raw key must not appear in Redis."""

        mock_redis = self._make_mock_redis()
        raw_key, _key_id, _meta = await create_api_key(
            redis_client=mock_redis,
            description="sensitive",
            role="api_user",
            created_by="admin",
        )
        all_values = json.dumps(list(mock_redis._store.values()))
        assert raw_key not in all_values

    @pytest.mark.asyncio
    async def test_list_returns_key_ids(self):
        mock_redis = self._make_mock_redis()
        _, key_id1, _ = await create_api_key(mock_redis, "key1", "api_user", "admin")
        _, key_id2, _ = await create_api_key(mock_redis, "key2", "qa_engineer", "admin")

        keys = await list_api_keys(mock_redis)
        ids = [k["key_id"] for k in keys]
        assert key_id1 in ids
        assert key_id2 in ids

    @pytest.mark.asyncio
    async def test_list_does_not_expose_hashes(self):
        mock_redis = self._make_mock_redis()
        await create_api_key(mock_redis, "k", "api_user", "admin")

        keys = await list_api_keys(mock_redis)
        for entry in keys:
            assert "hash" not in str(entry).lower()

    @pytest.mark.asyncio
    async def test_revoke_removes_key(self):
        mock_redis = self._make_mock_redis()
        _raw_key, key_id, _ = await create_api_key(mock_redis, "k", "api_user", "admin")

        assert await revoke_api_key(mock_redis, key_id) is True
        keys = await list_api_keys(mock_redis)
        ids = [k["key_id"] for k in keys]
        assert key_id not in ids

    @pytest.mark.asyncio
    async def test_revoke_nonexistent_returns_false(self):
        mock_redis = self._make_mock_redis()
        assert await revoke_api_key(mock_redis, "nonexistent") is False

    @pytest.mark.asyncio
    async def test_api_key_lookup_works_in_get_current_user(self):
        """End-to-end: created key is accepted by get_current_user."""
        import hashlib

        mock_redis = self._make_mock_redis()
        raw_key, key_id, _meta = await create_api_key(
            mock_redis, "e2e", "api_user", "admin"
        )

        # Simulate what get_current_user does
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        key_data = await mock_redis.get(f"api_key:{key_hash}")
        assert key_data is not None
        parsed = json.loads(key_data)
        assert parsed["key_id"] == key_id
        assert "permissions" in parsed
