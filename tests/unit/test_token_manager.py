"""Tests for webgui/auth/token_manager.py — JWT create, verify, refresh, logout."""

import hashlib
import os
import sys
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import jwt
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from webgui.auth.models import AuthProvider, AuthToken, Permission, User, UserRole

SECRET = "test-secret-key-minimum-32-bytes!"


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
        "permissions": {Permission.SESSIONS_READ, Permission.SESSIONS_WRITE},
        "metadata": {},
    }
    defaults.update(overrides)
    return User(**defaults)


def _make_manager(redis=None):
    from webgui.auth.token_manager import TokenManager

    return TokenManager(redis_client=redis or MagicMock(), secret_key=SECRET)


class TestCreateTokens:
    @pytest.mark.asyncio
    async def test_returns_auth_token(self):
        redis = MagicMock()
        mgr = _make_manager(redis)
        user = _make_user()
        token = await mgr.create_tokens(user)
        assert isinstance(token, AuthToken)
        assert token.token_type == "bearer"
        assert token.expires_in == 15 * 60

    @pytest.mark.asyncio
    async def test_access_token_decodable(self):
        mgr = _make_manager()
        user = _make_user()
        token = await mgr.create_tokens(user)
        payload = jwt.decode(token.access_token, SECRET, algorithms=["HS256"])
        assert payload["user_id"] == "u1"
        assert payload["email"] == "test@example.com"
        assert payload["type"] == "access"

    @pytest.mark.asyncio
    async def test_refresh_token_decodable(self):
        mgr = _make_manager()
        user = _make_user()
        token = await mgr.create_tokens(user)
        payload = jwt.decode(token.refresh_token, SECRET, algorithms=["HS256"])
        assert payload["user_id"] == "u1"
        assert payload["type"] == "refresh"

    @pytest.mark.asyncio
    async def test_stores_refresh_in_redis(self):
        redis = MagicMock()
        mgr = _make_manager(redis)
        user = _make_user()
        token = await mgr.create_tokens(user)
        redis.setex.assert_called_once()
        args = redis.setex.call_args
        assert args[0][0] == "refresh_token:u1"
        assert args[0][2] == token.refresh_token

    @pytest.mark.asyncio
    async def test_permissions_in_token(self):
        mgr = _make_manager()
        user = _make_user()
        token = await mgr.create_tokens(user)
        payload = jwt.decode(token.access_token, SECRET, algorithms=["HS256"])
        assert "sessions:read" in payload["permissions"]
        assert "sessions:write" in payload["permissions"]


class TestVerifyToken:
    @pytest.mark.asyncio
    async def test_valid_token(self):
        redis = MagicMock()
        redis.exists.return_value = False
        mgr = _make_manager(redis)
        user = _make_user()
        token = await mgr.create_tokens(user)
        payload = await mgr.verify_token(token.access_token)
        assert payload is not None
        assert payload["user_id"] == "u1"

    @pytest.mark.asyncio
    async def test_expired_token(self):
        mgr = _make_manager()
        expired = jwt.encode(
            {"user_id": "u1", "type": "access", "exp": datetime.now(UTC) - timedelta(hours=1)},
            SECRET,
            algorithm="HS256",
        )
        result = await mgr.verify_token(expired)
        assert result is None

    @pytest.mark.asyncio
    async def test_invalid_token(self):
        mgr = _make_manager()
        result = await mgr.verify_token("not.a.valid.token")
        assert result is None

    @pytest.mark.asyncio
    async def test_blacklisted_token(self):
        redis = MagicMock()
        redis.exists.return_value = True  # token is blacklisted
        mgr = _make_manager(redis)
        user = _make_user()
        token = await mgr.create_tokens(user)
        result = await mgr.verify_token(token.access_token)
        assert result is None


class TestRefreshTokens:
    @pytest.mark.asyncio
    async def test_successful_refresh(self):
        redis = MagicMock()
        redis.exists.return_value = False
        mgr = _make_manager(redis)
        user = _make_user()
        original = await mgr.create_tokens(user)

        # Mock stored token
        redis.get.return_value = original.refresh_token.encode()
        get_user = AsyncMock(return_value=user)

        new_token = await mgr.refresh_tokens(original.refresh_token, get_user)
        assert new_token is not None
        assert isinstance(new_token, AuthToken)
        get_user.assert_awaited_once_with("u1")

    @pytest.mark.asyncio
    async def test_wrong_token_type(self):
        mgr = _make_manager()
        # Create an access token (type != "refresh")
        access = jwt.encode(
            {"user_id": "u1", "type": "access", "exp": datetime.now(UTC) + timedelta(hours=1)},
            SECRET,
            algorithm="HS256",
        )
        result = await mgr.refresh_tokens(access, AsyncMock())
        assert result is None

    @pytest.mark.asyncio
    async def test_mismatched_stored_token(self):
        redis = MagicMock()
        redis.get.return_value = b"different-token"
        mgr = _make_manager(redis)
        refresh = jwt.encode(
            {"user_id": "u1", "type": "refresh", "exp": datetime.now(UTC) + timedelta(days=1)},
            SECRET,
            algorithm="HS256",
        )
        result = await mgr.refresh_tokens(refresh, AsyncMock())
        assert result is None

    @pytest.mark.asyncio
    async def test_inactive_user(self):
        redis = MagicMock()
        mgr = _make_manager(redis)
        user = _make_user(is_active=False)
        token = await mgr.create_tokens(user)
        redis.get.return_value = token.refresh_token.encode()

        get_user = AsyncMock(return_value=user)
        result = await mgr.refresh_tokens(token.refresh_token, get_user)
        assert result is None

    @pytest.mark.asyncio
    async def test_user_not_found(self):
        redis = MagicMock()
        mgr = _make_manager(redis)
        user = _make_user()
        token = await mgr.create_tokens(user)
        redis.get.return_value = token.refresh_token.encode()

        get_user = AsyncMock(return_value=None)
        result = await mgr.refresh_tokens(token.refresh_token, get_user)
        assert result is None


class TestLogout:
    @pytest.mark.asyncio
    async def test_blacklists_and_deletes(self):
        redis = MagicMock()
        mgr = _make_manager(redis)
        result = await mgr.logout("u1", "some-access-token")
        assert result is True
        redis.setex.assert_called_once()
        redis.delete.assert_called_once_with("refresh_token:u1")

    @pytest.mark.asyncio
    async def test_blacklist_key_uses_hash(self):
        redis = MagicMock()
        mgr = _make_manager(redis)
        token = "my-token"
        await mgr.logout("u1", token)
        expected_key = f"blacklist_token:{hashlib.sha256(token.encode()).hexdigest()}"
        assert redis.setex.call_args[0][0] == expected_key

    @pytest.mark.asyncio
    async def test_returns_false_on_error(self):
        redis = MagicMock()
        redis.setex.side_effect = Exception("Redis down")
        mgr = _make_manager(redis)
        result = await mgr.logout("u1", "token")
        assert result is False


class TestPasswordHashing:
    def test_hash_and_verify(self):
        from webgui.auth.token_manager import TokenManager

        pw = "my-secret-password"
        hashed = TokenManager.hash_password(pw)
        assert hashed != pw
        assert TokenManager.verify_password(pw, hashed) is True

    def test_wrong_password(self):
        from webgui.auth.token_manager import TokenManager

        hashed = TokenManager.hash_password("correct")
        assert TokenManager.verify_password("wrong", hashed) is False
