"""API key management — creation, listing, and revocation."""

import hashlib
import json
import secrets
from datetime import datetime
from typing import Any

from webgui.auth.models import Permission

# Default permissions granted to each role for API keys
_API_KEY_ROLE_PERMISSIONS: dict[str, list[str]] = {
    "api_user": [
        Permission.SESSIONS_READ.value,
        Permission.SESSIONS_WRITE.value,
        Permission.API_ACCESS.value,
    ],
    "qa_engineer": [
        Permission.SESSIONS_READ.value,
        Permission.SESSIONS_WRITE.value,
        Permission.AGENTS_CONTROL.value,
        Permission.REPORTS_GENERATE.value,
        Permission.API_ACCESS.value,
    ],
    "super_admin": [p.value for p in Permission],
}


def create_api_key(
    redis_client: Any,
    description: str,
    role: str,
    created_by: str,
) -> tuple[str, str, dict[str, Any]]:
    """Create a new API key and store its sha256 hash in Redis.

    Returns:
        (raw_key, key_id, key_metadata)
        raw_key  — the plaintext key shown once to the caller
        key_id   — first 8 chars of sha256(raw_key), used for management
        key_metadata — dict stored in Redis (never contains raw_key)
    """
    raw_key = secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    key_id = key_hash[:8]

    permissions = _API_KEY_ROLE_PERMISSIONS.get(
        role, _API_KEY_ROLE_PERMISSIONS["api_user"]
    )

    key_meta: dict[str, Any] = {
        "key_id": key_id,
        "description": description,
        "role": role,
        "created_by": created_by,
        "created_at": datetime.now().isoformat(),
        "user_id": f"api-key-{key_id}",
        "email": f"api-key-{key_id}@agnostic",
        "permissions": permissions,
    }

    # Store hash -> metadata (no TTL = permanent until revoked)
    redis_client.set(f"api_key:{key_hash}", json.dumps(key_meta))
    # Store key_id -> hash for management lookups
    redis_client.set(f"api_key_id:{key_id}", key_hash)
    # Add to index set
    redis_client.sadd("api_keys:index", key_id)

    return raw_key, key_id, key_meta


def list_api_keys(redis_client: Any) -> list[dict[str, Any]]:
    """Return metadata for all API keys (never raw keys or hashes)."""
    raw_ids = redis_client.smembers("api_keys:index")
    result: list[dict[str, Any]] = []

    for raw_id in raw_ids:
        key_id = raw_id.decode() if isinstance(raw_id, bytes) else raw_id
        key_hash_raw = redis_client.get(f"api_key_id:{key_id}")
        if not key_hash_raw:
            continue

        key_hash = (
            key_hash_raw.decode() if isinstance(key_hash_raw, bytes) else key_hash_raw
        )
        meta_data = redis_client.get(f"api_key:{key_hash}")
        if not meta_data:
            continue

        meta: dict[str, Any] = json.loads(meta_data)
        result.append(
            {
                "key_id": meta.get("key_id"),
                "description": meta.get("description"),
                "role": meta.get("role"),
                "created_by": meta.get("created_by"),
                "created_at": meta.get("created_at"),
            }
        )

    return result


def revoke_api_key(redis_client: Any, key_id: str) -> bool:
    """Revoke an API key by its key_id.  Returns True if found and deleted."""
    key_hash_raw = redis_client.get(f"api_key_id:{key_id}")
    if not key_hash_raw:
        return False

    key_hash = (
        key_hash_raw.decode() if isinstance(key_hash_raw, bytes) else key_hash_raw
    )
    redis_client.delete(f"api_key:{key_hash}")
    redis_client.delete(f"api_key_id:{key_id}")
    redis_client.srem("api_keys:index", key_id)
    return True
