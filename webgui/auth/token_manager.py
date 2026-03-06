"""Token management — JWT creation, verification, refresh, and logout."""

import hashlib
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from webgui.auth.models import AuthToken, User

logger = logging.getLogger(__name__)


class TokenManager:
    """Manages JWT access/refresh tokens and token blacklisting."""

    def __init__(self, redis_client: Any, secret_key: str):
        self.redis_client = redis_client
        self.secret_key = secret_key
        self.access_token_expire_minutes = 15
        self.refresh_token_expire_days = 7

    async def create_tokens(self, user: User) -> AuthToken:
        """Create JWT access and refresh tokens."""
        try:
            access_payload = {
                "user_id": user.user_id,
                "email": user.email,
                "role": user.role.value,
                "permissions": [p.value for p in user.permissions],
                "type": "access",
                "exp": datetime.now(UTC)
                + timedelta(minutes=self.access_token_expire_minutes),
                "iat": datetime.now(UTC),
            }

            refresh_payload = {
                "user_id": user.user_id,
                "type": "refresh",
                "exp": datetime.now(UTC)
                + timedelta(days=self.refresh_token_expire_days),
                "iat": datetime.now(UTC),
            }

            access_token = jwt.encode(
                access_payload, self.secret_key, algorithm="HS256"
            )
            refresh_token = jwt.encode(
                refresh_payload, self.secret_key, algorithm="HS256"
            )

            # Store refresh token in Redis
            refresh_key = f"refresh_token:{user.user_id}"
            self.redis_client.setex(
                refresh_key,
                timedelta(days=self.refresh_token_expire_days),
                refresh_token,
            )

            return AuthToken(
                access_token=access_token,
                refresh_token=refresh_token,
                expires_in=self.access_token_expire_minutes * 60,
            )

        except Exception as e:
            logger.error(f"Error creating tokens: {e}")
            raise

    async def verify_token(self, token: str) -> dict[str, Any] | None:
        """Verify JWT token."""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=["HS256"])

            if self._is_token_blacklisted(token):
                return None

            return payload

        except jwt.ExpiredSignatureError:
            logger.warning("Token expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {e}")
            return None

    async def refresh_tokens(
        self, refresh_token: str, get_user_fn: Any
    ) -> AuthToken | None:
        """Refresh access token using refresh token.

        Args:
            refresh_token: The refresh JWT to exchange.
            get_user_fn: Async callable(user_id) -> User | None.
        """
        try:
            payload = jwt.decode(
                refresh_token, self.secret_key, algorithms=["HS256"]
            )

            if payload.get("type") != "refresh":
                return None

            user_id = payload.get("user_id")

            refresh_key = f"refresh_token:{user_id}"
            stored_token = self.redis_client.get(refresh_key)

            if not stored_token or stored_token.decode() != refresh_token:
                return None

            user = await get_user_fn(user_id)
            if not user or not user.is_active:
                return None

            return await self.create_tokens(user)

        except Exception as e:
            logger.error(f"Error refreshing tokens: {e}")
            return None

    async def logout(self, user_id: str, access_token: str) -> bool:
        """Logout user and invalidate tokens."""
        try:
            blacklist_key = (
                f"blacklist_token:{hashlib.sha256(access_token.encode()).hexdigest()}"
            )
            self.redis_client.setex(blacklist_key, timedelta(hours=1), "1")

            refresh_key = f"refresh_token:{user_id}"
            self.redis_client.delete(refresh_key)

            return True

        except Exception as e:
            logger.error(f"Error during logout: {e}")
            return False

    def _is_token_blacklisted(self, token: str) -> bool:
        """Check if token is blacklisted."""
        try:
            blacklist_key = (
                f"blacklist_token:{hashlib.sha256(token.encode()).hexdigest()}"
            )
            return self.redis_client.exists(blacklist_key)
        except Exception as e:
            logger.error(f"Error checking token blacklist: {e}")
            return False

    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        """Verify password against bcrypt hash."""
        try:
            import bcrypt

            return bcrypt.checkpw(password.encode(), password_hash.encode())
        except ImportError as err:
            raise RuntimeError(
                "bcrypt is required for password verification. "
                "Install it with: pip install bcrypt"
            ) from err
        except Exception as e:
            logger.error(f"Error verifying password: {e}")
            return False

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash password with bcrypt."""
        try:
            import bcrypt

            return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        except ImportError as err:
            raise RuntimeError(
                "bcrypt is required for password hashing. "
                "Install it with: pip install bcrypt"
            ) from err
