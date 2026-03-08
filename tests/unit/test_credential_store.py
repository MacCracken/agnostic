"""Tests for config.credential_store — runtime LLM credential provisioning."""

import time
from unittest.mock import patch

import pytest

from config.credential_store import (
    CredentialStore,
    ProvisionedCredential,
    VALID_PROVIDERS,
)


@pytest.fixture()
def store():
    """Fresh credential store with provisioning enabled."""
    s = CredentialStore()
    with patch("config.credential_store.CREDENTIAL_PROVISIONING_ENABLED", True):
        yield s


@pytest.fixture()
def disabled_store():
    """Credential store with provisioning disabled."""
    s = CredentialStore()
    with patch("config.credential_store.CREDENTIAL_PROVISIONING_ENABLED", False):
        yield s


def _make_cred(provider="openai", api_key="sk-test-123", **kwargs):
    return ProvisionedCredential(provider=provider, api_key=api_key, **kwargs)


class TestCredentialStoreBasic:
    def test_put_and_get(self, store):
        cred = _make_cred()
        store.put(cred)
        result = store.get("openai")
        assert result is not None
        assert result.api_key == "sk-test-123"
        assert result.provider == "openai"

    def test_get_returns_none_for_missing(self, store):
        assert store.get("anthropic") is None

    def test_get_returns_none_when_disabled(self, disabled_store):
        # Manually insert to bypass put's guard
        disabled_store._credentials["openai"] = _make_cred()
        assert disabled_store.get("openai") is None

    def test_put_is_noop_when_disabled(self, disabled_store):
        disabled_store.put(_make_cred())
        assert len(disabled_store._credentials) == 0

    def test_invalid_provider_raises(self, store):
        with pytest.raises(ValueError, match="Unknown provider"):
            store.put(_make_cred(provider="invalid_provider"))


class TestCredentialRotation:
    def test_second_put_replaces(self, store):
        store.put(_make_cred(api_key="key-1"))
        store.put(_make_cred(api_key="key-2"))
        result = store.get("openai")
        assert result is not None
        assert result.api_key == "key-2"

    @patch("config.credential_store.audit_log")
    def test_rotation_audit_action(self, mock_audit, store):
        from shared.audit import AuditAction

        store.put(_make_cred(api_key="key-1"))
        store.put(_make_cred(api_key="key-2"))
        # Second call should be CREDENTIAL_ROTATED
        actions = [call.args[0] for call in mock_audit.call_args_list]
        assert AuditAction.CREDENTIAL_PROVISIONED in actions
        assert AuditAction.CREDENTIAL_ROTATED in actions


class TestCredentialRevocation:
    def test_revoke_existing(self, store):
        store.put(_make_cred())
        assert store.revoke("openai", "admin") is True
        assert store.get("openai") is None

    def test_revoke_nonexistent(self, store):
        assert store.revoke("openai", "admin") is False

    def test_revoke_all(self, store):
        store.put(_make_cred(provider="openai"))
        store.put(_make_cred(provider="anthropic", api_key="sk-ant"))
        count = store.revoke_all("admin")
        assert count == 2
        assert store.list_providers() == []


class TestCredentialExpiry:
    def test_expired_credential_not_returned(self, store):
        cred = _make_cred(expires_at=time.monotonic() - 1)
        store._credentials["openai"] = cred
        assert store.get("openai") is None

    def test_valid_credential_returned(self, store):
        cred = _make_cred(expires_at=time.monotonic() + 3600)
        store.put(cred)
        assert store.get("openai") is not None


class TestCredentialListing:
    def test_list_providers(self, store):
        store.put(_make_cred(provider="openai"))
        store.put(_make_cred(provider="anthropic", api_key="sk-ant"))
        providers = store.list_providers()
        assert sorted(providers) == ["anthropic", "openai"]

    def test_is_provisioned(self, store):
        store.put(_make_cred())
        assert store.is_provisioned("openai") is True
        assert store.is_provisioned("anthropic") is False


class TestCredentialMetadata:
    def test_base_url_and_model(self, store):
        cred = _make_cred(
            base_url="https://proxy.example.com/v1",
            model="gpt-4o-mini",
        )
        store.put(cred)
        result = store.get("openai")
        assert result is not None
        assert result.base_url == "https://proxy.example.com/v1"
        assert result.model == "gpt-4o-mini"

    def test_provisioned_by_tracked(self, store):
        cred = _make_cred(provisioned_by="yeoman:agent-1")
        store.put(cred)
        result = store.get("openai")
        assert result is not None
        assert result.provisioned_by == "yeoman:agent-1"


class TestAllValidProviders:
    @pytest.mark.parametrize("provider", sorted(VALID_PROVIDERS))
    def test_can_provision_each_provider(self, store, provider):
        store.put(_make_cred(provider=provider, api_key=f"key-{provider}"))
        result = store.get(provider)
        assert result is not None
        assert result.api_key == f"key-{provider}"
