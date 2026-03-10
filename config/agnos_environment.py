"""
AGNOS Environment Profile Sync.

Reads AGNOS EnvironmentProfile and auto-configures AGNOSTIC settings.
A single AGNOS_PROFILE env var (dev/staging/prod) replaces 10+ individual settings.
Explicit env vars always take precedence over profile defaults.

Configure via:
- AGNOS_PROFILE: Profile name (dev, staging, prod) or empty to disable
- AGNOS_PROFILE_URL: AGNOS API for profile overrides (optional)
- AGNOS_PROFILE_API_KEY: API key for profile fetch (optional)
"""

import logging
import os

logger = logging.getLogger(__name__)

AGNOS_PATH_PREFIX = os.getenv("AGNOS_PATH_PREFIX", "/v1")

PROFILES: dict[str, dict[str, str]] = {
    "dev": {
        "LOG_LEVEL": "DEBUG",
        "ENVIRONMENT": "development",
        "AUDIT_LOG_ENABLED": "true",
        "AUDIT_LOG_LEVEL": "DEBUG",
        "WEBSOCKET_ENABLED": "true",
        "CORS_ALLOWED_ORIGINS": "*",
        "AUTH_REQUIRED": "false",
        "DEBUG_ENDPOINTS": "true",
    },
    "staging": {
        "LOG_LEVEL": "INFO",
        "ENVIRONMENT": "staging",
        "AUDIT_LOG_ENABLED": "true",
        "AUDIT_LOG_LEVEL": "INFO",
        "WEBSOCKET_ENABLED": "true",
        "CORS_ALLOWED_ORIGINS": "",
        "AUTH_REQUIRED": "true",
        "DEBUG_ENDPOINTS": "false",
    },
    "prod": {
        "LOG_LEVEL": "WARNING",
        "ENVIRONMENT": "production",
        "AUDIT_LOG_ENABLED": "true",
        "AUDIT_LOG_LEVEL": "INFO",
        "WEBSOCKET_ENABLED": "true",
        "CORS_ALLOWED_ORIGINS": "",
        "AUTH_REQUIRED": "true",
        "DEBUG_ENDPOINTS": "false",
    },
}


def _fetch_remote_overrides(profile_name: str) -> dict[str, str]:
    """Optionally fetch profile overrides from AGNOS API (sync)."""
    url = os.getenv("AGNOS_PROFILE_URL", "")
    api_key = os.getenv("AGNOS_PROFILE_API_KEY", "")
    if not url:
        return {}

    try:
        import httpx

        with httpx.Client(timeout=5.0) as client:
            response = client.get(
                f"{url}{AGNOS_PATH_PREFIX}/profiles/{profile_name}",
                headers={"X-API-Key": api_key} if api_key else {},
            )
            response.raise_for_status()
            overrides = response.json().get("settings", {})
            if isinstance(overrides, dict):
                return {k: str(v) for k, v in overrides.items()}
    except ImportError:
        logger.debug("httpx not available, skipping remote profile fetch")
    except Exception as exc:
        logger.warning("Failed to fetch AGNOS profile overrides: %s", exc)
    return {}


def apply_agnos_profile() -> str | None:
    """Apply AGNOS environment profile defaults.

    Call this early in app startup, before other config is read.
    Explicit env vars take precedence (uses os.environ.setdefault).

    Returns the profile name that was applied, or None.
    """
    profile_name = os.getenv("AGNOS_PROFILE", "").strip().lower()
    if not profile_name:
        return None

    if profile_name not in PROFILES:
        logger.warning(
            "Unknown AGNOS_PROFILE '%s' (valid: %s)",
            profile_name,
            ", ".join(PROFILES.keys()),
        )
        return None

    # Start with hardcoded defaults
    settings = PROFILES[profile_name].copy()

    # Merge remote overrides (if AGNOS API is configured)
    remote = _fetch_remote_overrides(profile_name)
    settings.update(remote)

    # Apply via setdefault — explicit env vars win
    applied = []
    for key, value in settings.items():
        if key not in os.environ:
            os.environ.setdefault(key, value)
            applied.append(key)

    logger.info(
        "Applied AGNOS profile '%s': set %d defaults (%s)",
        profile_name,
        len(applied),
        ", ".join(applied) if applied else "none — all already set",
    )
    return profile_name


def get_active_profile() -> str | None:
    """Return the current AGNOS profile name, or None if not set."""
    profile = os.getenv("AGNOS_PROFILE", "").strip().lower()
    return profile if profile in PROFILES else None
