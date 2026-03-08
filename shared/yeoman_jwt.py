"""
SecureYeoman JWT Validation.

Validates JWTs issued by SecureYeoman alongside existing AGNOSTIC auth.
Supports RS256/ES256 (public key), HS256 (shared secret), and OIDC discovery.

Configure via:
- YEOMAN_JWT_ENABLED: Enable YEOMAN JWT validation (default: false)
- YEOMAN_JWT_ISSUER: Expected JWT issuer claim (default: secureyeoman)
- YEOMAN_JWT_PUBLIC_KEY: Path to PEM public key file, or inline PEM string
- YEOMAN_JWT_SECRET: Shared HMAC secret (fallback if no public key)
- YEOMAN_JWT_AUDIENCE: Expected audience claim (default: agnostic-qa)
- YEOMAN_OIDC_DISCOVERY_URL: OIDC discovery endpoint (e.g. https://idp/.well-known/openid-configuration)
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

try:
    import jwt as pyjwt

    _JWT_AVAILABLE = True
except ImportError:  # pragma: no cover
    pyjwt = None  # type: ignore[assignment]
    _JWT_AVAILABLE = False

try:
    import httpx as _httpx

    _HTTPX_AVAILABLE = True
except ImportError:  # pragma: no cover
    _httpx = None  # type: ignore[assignment]
    _HTTPX_AVAILABLE = False

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_ENABLED = os.getenv("YEOMAN_JWT_ENABLED", "false").lower() in ("true", "1", "yes")
_ISSUER = os.getenv("YEOMAN_JWT_ISSUER", "secureyeoman")
_AUDIENCE = os.getenv("YEOMAN_JWT_AUDIENCE", "agnostic-qa")
_PUBLIC_KEY_PATH = os.getenv("YEOMAN_JWT_PUBLIC_KEY", "")
_SHARED_SECRET = os.getenv("YEOMAN_JWT_SECRET", "")
_OIDC_DISCOVERY_URL = os.getenv("YEOMAN_OIDC_DISCOVERY_URL", "")

# Cache the loaded public key
_cached_public_key: str | None = None

# OIDC JWKS cache
_oidc_jwks: dict[str, Any] | None = None
_oidc_jwks_fetched_at: float = 0
_oidc_issuer: str | None = None
_oidc_lock = threading.Lock()
_OIDC_CACHE_TTL = 3600  # Re-fetch JWKS every hour


def _load_public_key() -> str | None:
    """Load the YEOMAN JWT public key from file or env var."""
    global _cached_public_key
    if _cached_public_key is not None:
        return _cached_public_key

    raw = _PUBLIC_KEY_PATH.strip()
    if not raw:
        return None

    # If it looks like inline PEM, use directly
    if raw.startswith("-----BEGIN"):
        _cached_public_key = raw
        return _cached_public_key

    # Otherwise treat as file path
    try:
        with open(raw) as f:
            _cached_public_key = f.read().strip()
        logger.info("Loaded YEOMAN JWT public key from %s", raw)
        return _cached_public_key
    except OSError as exc:
        logger.error("Failed to load YEOMAN JWT public key from %s: %s", raw, exc)
        return None


def _fetch_oidc_config() -> dict[str, Any] | None:
    """Fetch OIDC discovery document and JWKS."""
    global _oidc_jwks, _oidc_jwks_fetched_at, _oidc_issuer

    if not _OIDC_DISCOVERY_URL or not _HTTPX_AVAILABLE:
        return None

    now = time.monotonic()
    with _oidc_lock:
        if _oidc_jwks is not None and (now - _oidc_jwks_fetched_at) < _OIDC_CACHE_TTL:
            return _oidc_jwks

        # Hold lock during entire fetch to prevent duplicate concurrent fetches
        try:
            with _httpx.Client(timeout=10.0) as client:
                # Fetch discovery document
                disco_resp = client.get(_OIDC_DISCOVERY_URL)
                disco_resp.raise_for_status()
                disco = disco_resp.json()

                jwks_uri = disco.get("jwks_uri")
                if not jwks_uri:
                    logger.warning("OIDC discovery missing jwks_uri")
                    return None

                # Fetch JWKS
                jwks_resp = client.get(jwks_uri)
                jwks_resp.raise_for_status()
                jwks = jwks_resp.json()

            _oidc_jwks = jwks
            _oidc_jwks_fetched_at = time.monotonic()
            _oidc_issuer = disco.get("issuer")

            logger.info(
                "Fetched OIDC JWKS from %s (%d keys)",
                jwks_uri,
                len(jwks.get("keys", [])),
            )
            return jwks

        except Exception as exc:
            logger.warning(
                "Failed to fetch OIDC configuration from %s: %s",
                _OIDC_DISCOVERY_URL,
                exc,
            )
            return None


def _validate_with_oidc(token: str) -> dict[str, Any] | None:
    """Validate a JWT using OIDC-discovered JWKS."""
    if not _JWT_AVAILABLE:
        return None

    jwks = _fetch_oidc_config()
    if not jwks:
        return None

    try:
        # PyJWT >= 2.x supports JWK sets
        from jwt import PyJWKClient

        # Build a JWK client from the cached JWKS data
        # We use the JWKS URI approach but with our cached data
        jwks_uri = ""
        if _OIDC_DISCOVERY_URL and _HTTPX_AVAILABLE:
            try:
                with _httpx.Client(timeout=5.0) as client:
                    disco = client.get(_OIDC_DISCOVERY_URL).json()
                    jwks_uri = disco.get("jwks_uri", "")
            except Exception:
                logger.debug("OIDC discovery fetch failed for %s", _OIDC_DISCOVERY_URL)

        if not jwks_uri:
            return None

        jwks_client = PyJWKClient(jwks_uri, cache_keys=True, lifespan=_OIDC_CACHE_TTL)
        signing_key = jwks_client.get_signing_key_from_jwt(token)

        issuer = _oidc_issuer or _ISSUER
        payload = pyjwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            audience=_AUDIENCE,
            issuer=issuer,
            options={
                "require": ["exp", "iss", "sub"],
                "verify_exp": True,
                "verify_iss": True,
            },
        )
        return payload

    except ImportError:
        logger.debug("PyJWKClient not available; OIDC validation requires PyJWT >= 2.x")
        return None
    except pyjwt.ExpiredSignatureError:
        logger.debug("OIDC JWT expired")
        return None
    except pyjwt.InvalidTokenError as exc:
        logger.debug("OIDC JWT validation failed: %s", exc)
        return None
    except Exception as exc:
        logger.debug("OIDC validation error: %s", exc)
        return None


def is_enabled() -> bool:
    """Check if YEOMAN JWT validation is configured and available."""
    if not _ENABLED or not _JWT_AVAILABLE:
        return False
    return bool(_load_public_key() or _SHARED_SECRET or _OIDC_DISCOVERY_URL)


def validate_yeoman_jwt(token: str) -> dict[str, Any] | None:
    """Validate a SecureYeoman-issued JWT.

    Returns the decoded payload dict on success, or None on failure.
    The returned dict is normalized to match AGNOSTIC's user format:
    - user_id, email, role, permissions
    """
    if not _JWT_AVAILABLE:
        logger.debug("PyJWT not installed; cannot validate YEOMAN JWT")
        return None

    if not _ENABLED:
        return None

    public_key = _load_public_key()

    # Determine algorithm and key
    payload: dict[str, Any] | None = None
    if public_key:
        key: str = public_key
        algorithms = ["RS256", "ES256"]
    elif _SHARED_SECRET:
        key = _SHARED_SECRET
        algorithms = ["HS256"]
    elif _OIDC_DISCOVERY_URL:
        # No static key — try OIDC discovery
        payload = _validate_with_oidc(token)
        if payload is None:
            return None
    else:
        logger.debug("No YEOMAN JWT key configured")
        return None

    if payload is None:
        try:
            payload = pyjwt.decode(
                token,
                key,
                algorithms=algorithms,
                issuer=_ISSUER,
                audience=_AUDIENCE,
                options={
                    "require": ["exp", "iss", "sub"],
                    "verify_exp": True,
                    "verify_iss": True,
                },
            )
        except pyjwt.ExpiredSignatureError:
            logger.debug("YEOMAN JWT expired")
            return None
        except pyjwt.InvalidTokenError as exc:
            logger.debug("YEOMAN JWT validation failed: %s", exc)
            return None

    # Map YEOMAN JWT claims to AGNOSTIC user format
    yeoman_role = payload.get("role", "operator")
    role_mapping = {
        "role_admin": "super_admin",
        "role_operator": "api_user",
        "role_auditor": "analyst",
        "role_viewer": "viewer",
        "role_security_auditor": "analyst",
        "admin": "super_admin",
        "operator": "api_user",
        "auditor": "analyst",
        "viewer": "viewer",
    }
    agnostic_role = role_mapping.get(yeoman_role, "api_user")

    # Map permissions based on role
    from webgui.auth.models import Permission

    role_permissions = {
        "super_admin": [p.value for p in Permission],
        "api_user": [p.value for p in Permission if p != Permission.SYSTEM_CONFIGURE],
        "analyst": [
            Permission.SESSIONS_READ.value,
            Permission.REPORTS_GENERATE.value,
            Permission.REPORTS_EXPORT.value,
            Permission.API_ACCESS.value,
        ],
        "viewer": [
            Permission.SESSIONS_READ.value,
            Permission.REPORTS_EXPORT.value,
            Permission.API_ACCESS.value,
        ],
    }
    permissions = role_permissions.get(
        agnostic_role,
        [p.value for p in Permission if p != Permission.SYSTEM_CONFIGURE],
    )

    return {
        "user_id": f"yeoman:{payload.get('sub', payload.get('userId', 'unknown'))}",
        "email": payload.get("email", f"{payload.get('sub', 'unknown')}@secureyeoman"),
        "role": agnostic_role,
        "permissions": permissions,
        "auth_source": "yeoman_jwt",
        "yeoman_user_id": payload.get("userId") or payload.get("sub"),
        "yeoman_role": yeoman_role,
    }
