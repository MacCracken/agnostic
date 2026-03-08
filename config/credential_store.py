"""In-memory credential store for runtime LLM key provisioning.

Supports two modes:
  1. **Standalone** — credentials come from environment variables (default).
     The store is inactive; ``get()`` always returns ``None``.
  2. **Orchestrated** — SecureYeoman or AGNOS provisions credentials at
     runtime via MCP tool or A2A message.  The store holds them in memory
     and LLM consumers check the store before falling back to env vars.

Credentials are *never* persisted to disk, Redis, or the database.
On process restart the orchestrator must re-provision.

Enable with ``CREDENTIAL_PROVISIONING_ENABLED=true``.
"""

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from shared.audit import AuditAction, audit_log

logger = logging.getLogger(__name__)

CREDENTIAL_PROVISIONING_ENABLED = (
    os.getenv("CREDENTIAL_PROVISIONING_ENABLED", "false").lower() == "true"
)

# Providers that can be provisioned
VALID_PROVIDERS = frozenset(
    {"openai", "anthropic", "google", "ollama", "lm_studio", "custom_local", "agnos_gateway"}
)


@dataclass
class ProvisionedCredential:
    """A runtime-provisioned LLM credential."""

    provider: str
    api_key: str
    base_url: str | None = None
    model: str | None = None
    provisioned_by: str = "unknown"
    provisioned_at: float = field(default_factory=time.monotonic)
    expires_at: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        return self.expires_at is not None and time.monotonic() > self.expires_at


class CredentialStore:
    """Thread-safe in-memory credential store.

    The singleton ``credential_store`` is used by ``LLMIntegrationService``
    and ``BaseModelProvider`` to resolve API keys at call time.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._credentials: dict[str, ProvisionedCredential] = {}

    @property
    def enabled(self) -> bool:
        return CREDENTIAL_PROVISIONING_ENABLED

    def get(self, provider: str) -> ProvisionedCredential | None:
        """Return the provisioned credential for *provider*, or ``None``.

        Returns ``None`` when provisioning is disabled, the provider has
        no credential, or the credential has expired.
        """
        if not CREDENTIAL_PROVISIONING_ENABLED:
            return None
        with self._lock:
            cred = self._credentials.get(provider)
            if cred is None:
                return None
            if cred.is_expired:
                del self._credentials[provider]
                logger.info("Credential for provider=%s expired — removed", provider)
                audit_log(
                    AuditAction.CREDENTIAL_EXPIRED,
                    actor="system",
                    resource_type="credential",
                    resource_id=provider,
                )
                return None
            return cred

    def put(self, credential: ProvisionedCredential) -> None:
        """Store or replace a credential.  No-op when provisioning is disabled."""
        if not CREDENTIAL_PROVISIONING_ENABLED:
            logger.debug(
                "Credential provisioning disabled — ignoring put for %s",
                credential.provider,
            )
            return
        if credential.provider not in VALID_PROVIDERS:
            raise ValueError(
                f"Unknown provider {credential.provider!r}. "
                f"Valid: {sorted(VALID_PROVIDERS)}"
            )

        is_rotation = False
        with self._lock:
            is_rotation = credential.provider in self._credentials
            self._credentials[credential.provider] = credential

        action = AuditAction.CREDENTIAL_ROTATED if is_rotation else AuditAction.CREDENTIAL_PROVISIONED
        audit_log(
            action,
            actor=credential.provisioned_by,
            resource_type="credential",
            resource_id=credential.provider,
            detail={
                "has_base_url": credential.base_url is not None,
                "has_model": credential.model is not None,
                "has_expiry": credential.expires_at is not None,
            },
        )
        logger.info(
            "Credential %s for provider=%s by=%s",
            "rotated" if is_rotation else "provisioned",
            credential.provider,
            credential.provisioned_by,
        )

    def revoke(self, provider: str, actor: str) -> bool:
        """Remove a provisioned credential.  Returns ``True`` if it existed."""
        with self._lock:
            removed = self._credentials.pop(provider, None) is not None
        if removed:
            audit_log(
                AuditAction.CREDENTIAL_REVOKED,
                actor=actor,
                resource_type="credential",
                resource_id=provider,
            )
            logger.info("Credential revoked for provider=%s by=%s", provider, actor)
        return removed

    def revoke_all(self, actor: str) -> int:
        """Remove all provisioned credentials.  Returns count removed."""
        with self._lock:
            count = len(self._credentials)
            self._credentials.clear()
        if count:
            audit_log(
                AuditAction.CREDENTIAL_REVOKED,
                actor=actor,
                resource_type="credential",
                resource_id="*",
                detail={"count": count},
            )
            logger.info("All %d credentials revoked by=%s", count, actor)
        return count

    def list_providers(self) -> list[str]:
        """Return provider names that have provisioned credentials (no secrets)."""
        with self._lock:
            return [
                p for p, c in self._credentials.items() if not c.is_expired
            ]

    def is_provisioned(self, provider: str) -> bool:
        """Check whether a provider has a valid credential without returning it."""
        return self.get(provider) is not None


# Module-level singleton
credential_store = CredentialStore()
