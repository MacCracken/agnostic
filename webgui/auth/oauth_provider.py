"""OAuth provider authentication — Google, GitHub, Azure AD, and local."""

import json
import logging
import os
import uuid
from datetime import datetime
from typing import Any

import httpx
import jwt
from jwt import PyJWKClient

from webgui.auth.models import AuthProvider, Permission, User, UserRole

logger = logging.getLogger(__name__)


class OAuthProviderFactory:
    """Handles authentication for all supported OAuth2/local providers."""

    def __init__(
        self,
        redis_client: Any,
        role_permissions: dict[UserRole, set[Permission]],
        verify_password_fn: Any,
    ):
        self.redis_client = redis_client
        self.role_permissions = role_permissions
        self._verify_password = verify_password_fn

    async def authenticate(
        self,
        provider: AuthProvider,
        email: str,
        password: str | None = None,
        auth_code: str | None = None,
        id_token: str | None = None,
    ) -> User | None:
        """Dispatch to the appropriate provider."""
        if provider == AuthProvider.LOCAL:
            return await self._authenticate_local(email, password or "")
        elif provider == AuthProvider.GOOGLE:
            return await self._authenticate_google(auth_code, id_token)
        elif provider == AuthProvider.GITHUB:
            return await self._authenticate_github(auth_code)
        elif provider == AuthProvider.AZURE_AD:
            return await self._authenticate_azure_ad(auth_code, id_token)
        elif provider == AuthProvider.SAML:
            logger.warning("SAML authentication is not yet implemented")
            return None
        # Fallback for any future providers not yet handled
        logger.error(f"Unsupported auth provider: {provider}")  # type: ignore[unreachable]
        return None

    async def _authenticate_local(self, email: str, password: str) -> User | None:
        """Local authentication with password."""
        try:
            user_key = f"user:email:{email}"
            user_data = await self.redis_client.get(user_key)

            if not user_data:
                return None

            user_dict = json.loads(user_data)

            password_hash = user_dict.get("password_hash")
            if not password_hash or not self._verify_password(password, password_hash):
                return None

            user = User(
                user_id=user_dict["user_id"],
                email=user_dict["email"],
                name=user_dict["name"],
                role=UserRole(user_dict["role"]),
                auth_provider=AuthProvider.LOCAL,
                organization_id=user_dict.get("organization_id"),
                team_id=user_dict.get("team_id"),
                created_at=datetime.fromisoformat(user_dict["created_at"]),
                last_login=datetime.fromisoformat(user_dict["last_login"])
                if user_dict.get("last_login")
                else None,
                is_active=user_dict.get("is_active", True),
                permissions=self.role_permissions.get(
                    UserRole(user_dict["role"]), set()
                ),
                metadata=user_dict.get("metadata", {}),
            )

            await self._update_last_login(user.user_id)

            return user

        except Exception as e:
            logger.error(f"Local authentication error: {e}")
            return None

    async def _authenticate_google(
        self, auth_code: str | None, id_token: str | None
    ) -> User | None:
        """Google OAuth2 authentication with JWKS signature verification."""
        try:
            if not id_token:
                return None

            google_client_id = os.getenv("OAUTH2_GOOGLE_CLIENT_ID")
            if not google_client_id:
                logger.error("OAUTH2_GOOGLE_CLIENT_ID not configured")
                return None

            jwks_client = PyJWKClient("https://www.googleapis.com/oauth2/v3/certs")
            signing_key = jwks_client.get_signing_key_from_jwt(id_token)

            payload = jwt.decode(
                id_token,
                signing_key.key,
                algorithms=["RS256"],
                audience=google_client_id,
                issuer=["https://accounts.google.com", "accounts.google.com"],
            )

            email = payload.get("email")
            if not email:
                logger.error("Google ID token missing email claim")
                return None

            name = payload.get("name", email)

            return await self._get_or_create_oauth_user(
                email=email,
                name=name,
                provider=AuthProvider.GOOGLE,
                provider_id=str(payload.get("sub", "")),
            )

        except jwt.ExpiredSignatureError:
            logger.warning("Google ID token expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.error(f"Google ID token validation failed: {e}")
            return None
        except Exception as e:
            logger.error(f"Google authentication error: {e}")
            return None

    async def _authenticate_github(self, auth_code: str | None) -> User | None:
        """GitHub OAuth2 authentication via code->token exchange."""
        try:
            if not auth_code:
                return None

            client_id = os.getenv("OAUTH2_GITHUB_CLIENT_ID")
            client_secret = os.getenv("OAUTH2_GITHUB_CLIENT_SECRET")
            if not client_id or not client_secret:
                logger.error("OAUTH2_GITHUB_CLIENT_ID/SECRET not configured")
                return None

            async with httpx.AsyncClient(timeout=10) as client:
                token_resp = await client.post(
                    "https://github.com/login/oauth/access_token",
                    json={
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "code": auth_code,
                    },
                    headers={"Accept": "application/json"},
                )
                token_resp.raise_for_status()
                token_data = token_resp.json()

                access_token = token_data.get("access_token")
                if not access_token:
                    logger.error(
                        f"GitHub token exchange failed: {token_data.get('error_description', 'unknown error')}"
                    )
                    return None

                user_resp = await client.get(
                    "https://api.github.com/user",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Accept": "application/vnd.github+json",
                    },
                )
                user_resp.raise_for_status()
                github_user = user_resp.json()

                email = github_user.get("email")
                if not email:
                    emails_resp = await client.get(
                        "https://api.github.com/user/emails",
                        headers={
                            "Authorization": f"Bearer {access_token}",
                            "Accept": "application/vnd.github+json",
                        },
                    )
                    emails_resp.raise_for_status()
                    for email_obj in emails_resp.json():
                        if email_obj.get("primary") and email_obj.get("verified"):
                            email = email_obj["email"]
                            break

            if not email:
                logger.error("Could not retrieve verified email from GitHub")
                return None

            name = github_user.get("name") or github_user.get("login", email)

            return await self._get_or_create_oauth_user(
                email=email,
                name=name,
                provider=AuthProvider.GITHUB,
                provider_id=str(github_user["id"]),
            )

        except httpx.HTTPError as e:
            logger.error(f"GitHub API request failed: {e}")
            return None
        except Exception as e:
            logger.error(f"GitHub authentication error: {e}")
            return None

    async def _authenticate_azure_ad(
        self, auth_code: str | None, id_token: str | None
    ) -> User | None:
        """Azure AD authentication with JWKS signature verification."""
        try:
            if not id_token:
                return None

            azure_client_id = os.getenv("OAUTH2_AZURE_CLIENT_ID")
            azure_tenant_id = os.getenv("OAUTH2_AZURE_TENANT_ID", "common")
            if not azure_client_id:
                logger.error("OAUTH2_AZURE_CLIENT_ID not configured")
                return None

            jwks_client = PyJWKClient(
                f"https://login.microsoftonline.com/{azure_tenant_id}/discovery/v2.0/keys"
            )
            signing_key = jwks_client.get_signing_key_from_jwt(id_token)

            # Build issuer allowlist for the configured tenant
            azure_issuers = [
                f"https://login.microsoftonline.com/{azure_tenant_id}/v2.0",
                f"https://sts.windows.net/{azure_tenant_id}/",
            ]

            payload = jwt.decode(
                id_token,
                signing_key.key,
                algorithms=["RS256"],
                audience=azure_client_id,
                issuer=azure_issuers,
            )

            email = payload.get("preferred_username") or payload.get("email")
            if not email:
                logger.error("Azure AD ID token missing email claim")
                return None

            name = payload.get("name", email)

            return await self._get_or_create_oauth_user(
                email=email,
                name=name,
                provider=AuthProvider.AZURE_AD,
                provider_id=str(payload.get("oid") or payload.get("sub", "")),
            )

        except jwt.ExpiredSignatureError:
            logger.warning("Azure AD ID token expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.error(f"Azure AD ID token validation failed: {e}")
            return None
        except Exception as e:
            logger.error(f"Azure AD authentication error: {e}")
            return None

    async def _get_or_create_oauth_user(
        self, email: str, name: str, provider: AuthProvider, provider_id: str
    ) -> User | None:
        """Get existing OAuth user or create new one."""
        try:
            user_key = f"user:email:{email}"
            user_data = await self.redis_client.get(user_key)

            if user_data:
                user_dict = json.loads(user_data)
                await self._update_last_login(user_dict["user_id"])

                return User(
                    user_id=user_dict["user_id"],
                    email=user_dict["email"],
                    name=user_dict["name"],
                    role=UserRole(user_dict["role"]),
                    auth_provider=AuthProvider(user_dict["auth_provider"]),
                    organization_id=user_dict.get("organization_id"),
                    team_id=user_dict.get("team_id"),
                    created_at=datetime.fromisoformat(user_dict["created_at"]),
                    last_login=datetime.fromisoformat(user_dict["last_login"])
                    if user_dict.get("last_login")
                    else None,
                    is_active=user_dict.get("is_active", True),
                    permissions=self.role_permissions.get(
                        UserRole(user_dict["role"]), set()
                    ),
                    metadata=user_dict.get("metadata", {}),
                )

            # Create new user
            user_id = f"user_{uuid.uuid4().hex}"

            default_role = UserRole.VIEWER

            new_user = User(
                user_id=user_id,
                email=email,
                name=name,
                role=default_role,
                auth_provider=provider,
                organization_id=None,
                team_id=None,
                created_at=datetime.now(),
                last_login=datetime.now(),
                is_active=True,
                permissions=self.role_permissions.get(default_role, set()),
                metadata={"provider_id": provider_id},
            )

            await self._save_user(new_user)

            return new_user

        except Exception as e:
            logger.error(f"Error getting/creating OAuth user: {e}")
            return None

    async def _save_user(self, user: User) -> None:
        """Save user to Redis."""
        from dataclasses import asdict

        try:
            user_dict = asdict(user)
            user_dict["role"] = user.role.value
            user_dict["auth_provider"] = user.auth_provider.value
            user_dict["created_at"] = user.created_at.isoformat()
            if user.last_login:
                user_dict["last_login"] = user.last_login.isoformat()

            user_key = f"user:{user.user_id}"
            await self.redis_client.set(user_key, json.dumps(user_dict))

            email_key = f"user:email:{user.email}"
            email_data = {
                "user_id": user.user_id,
                "email": user.email,
                "name": user.name,
                "role": user.role.value,
                "auth_provider": user.auth_provider.value,
                "organization_id": user.organization_id,
                "team_id": user.team_id,
                "created_at": user.created_at.isoformat(),
                "last_login": user.last_login.isoformat() if user.last_login else None,
                "is_active": user.is_active,
                "metadata": user.metadata,
            }

            if (
                user.auth_provider == AuthProvider.LOCAL
                and "password_hash" in user_dict
            ):
                email_data["password_hash"] = user_dict["password_hash"]

            await self.redis_client.set(email_key, json.dumps(email_data))

        except Exception as e:
            logger.error(f"Error saving user: {e}")
            raise

    async def _update_last_login(self, user_id: str) -> None:
        """Update user's last login time."""
        try:
            user_key = f"user:{user_id}"
            user_data = await self.redis_client.get(user_key)

            if user_data:
                user_dict = json.loads(user_data)
                user_dict["last_login"] = datetime.now().isoformat()
                await self.redis_client.set(user_key, json.dumps(user_dict))

                email = user_dict.get("email")
                if email:
                    email_key = f"user:email:{email}"
                    email_data = await self.redis_client.get(email_key)
                    if email_data:
                        email_dict = json.loads(email_data)
                        email_dict["last_login"] = datetime.now().isoformat()
                        await self.redis_client.set(email_key, json.dumps(email_dict))

        except Exception as e:
            logger.error(f"Error updating last login: {e}")
