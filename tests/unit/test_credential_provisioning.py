"""Tests for credential provisioning via MCP tools and A2A protocol."""

import time
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from config.credential_store import CredentialStore, ProvisionedCredential


def _patch_store(store):
    """Patch the singleton credential_store at its source module."""
    return patch("config.credential_store.credential_store", store)


def _patch_enabled(enabled=True):
    return patch("config.credential_store.CREDENTIAL_PROVISIONING_ENABLED", enabled)


# ---------------------------------------------------------------------------
# MCP dispatch tests
# ---------------------------------------------------------------------------


class TestMCPProvisionCredentials:
    """Test agnostic_provision_credentials MCP tool dispatch."""

    def _dispatch_provision(self, arguments, user):
        from webgui.routes.mcp import _dispatch_provision_credentials

        return _dispatch_provision_credentials(arguments, user)

    def test_provision_success_admin(self):
        store = CredentialStore()
        with _patch_enabled(True), _patch_store(store):
            result = self._dispatch_provision(
                {"provider": "openai", "api_key": "sk-test-123"},
                {"user_id": "admin-1", "role": "admin", "auth_source": "local"},
            )
        assert result["status"] == "provisioned"
        assert result["provider"] == "openai"

    def test_provision_success_yeoman_jwt(self):
        store = CredentialStore()
        with _patch_enabled(True), _patch_store(store):
            result = self._dispatch_provision(
                {"provider": "anthropic", "api_key": "sk-ant-test"},
                {"user_id": "yeoman:agent", "role": "api_user", "auth_source": "yeoman_jwt"},
            )
        assert result["status"] == "provisioned"
        assert result["provider"] == "anthropic"

    def test_provision_unauthorized(self):
        with _patch_enabled(True):
            with pytest.raises(HTTPException) as exc_info:
                self._dispatch_provision(
                    {"provider": "openai", "api_key": "sk-test"},
                    {"user_id": "viewer-1", "role": "viewer", "auth_source": "local"},
                )
            assert exc_info.value.status_code == 403

    def test_provision_disabled(self):
        with _patch_enabled(False):
            with pytest.raises(HTTPException) as exc_info:
                self._dispatch_provision(
                    {"provider": "openai", "api_key": "sk-test"},
                    {"user_id": "admin-1", "role": "admin"},
                )
            assert exc_info.value.status_code == 503

    def test_provision_with_expiry(self):
        store = CredentialStore()
        with _patch_enabled(True), _patch_store(store):
            result = self._dispatch_provision(
                {"provider": "openai", "api_key": "sk-test", "expires_in_seconds": 3600},
                {"user_id": "admin-1", "role": "admin"},
            )
        assert result["has_expiry"] is True

    def test_provision_with_base_url_and_model(self):
        store = CredentialStore()
        with _patch_enabled(True), _patch_store(store):
            self._dispatch_provision(
                {
                    "provider": "openai",
                    "api_key": "sk-proxy",
                    "base_url": "https://proxy.example.com/v1",
                    "model": "gpt-4o-mini",
                },
                {"user_id": "admin-1", "role": "admin"},
            )
            cred = store.get("openai")
            assert cred is not None
            assert cred.base_url == "https://proxy.example.com/v1"
            assert cred.model == "gpt-4o-mini"


class TestMCPRevokeCredentials:
    """Test agnostic_revoke_credentials MCP tool dispatch."""

    def _dispatch_revoke(self, arguments, user):
        from webgui.routes.mcp import _dispatch_revoke_credentials

        return _dispatch_revoke_credentials(arguments, user)

    def test_revoke_existing(self):
        store = CredentialStore()
        store._credentials["openai"] = ProvisionedCredential(
            provider="openai", api_key="sk-old"
        )
        with _patch_enabled(True), _patch_store(store):
            result = self._dispatch_revoke(
                {"provider": "openai"},
                {"user_id": "admin-1", "role": "admin"},
            )
        assert result["status"] == "revoked"

    def test_revoke_nonexistent(self):
        store = CredentialStore()
        with _patch_enabled(True), _patch_store(store):
            result = self._dispatch_revoke(
                {"provider": "openai"},
                {"user_id": "admin-1", "role": "admin"},
            )
        assert result["status"] == "not_found"

    def test_revoke_all(self):
        store = CredentialStore()
        store._credentials["openai"] = ProvisionedCredential(
            provider="openai", api_key="sk-1"
        )
        store._credentials["anthropic"] = ProvisionedCredential(
            provider="anthropic", api_key="sk-2"
        )
        with _patch_enabled(True), _patch_store(store):
            result = self._dispatch_revoke(
                {"provider": "*"},
                {"user_id": "admin-1", "role": "admin"},
            )
        assert result["status"] == "revoked_all"
        assert result["count"] == 2

    def test_revoke_unauthorized(self):
        with _patch_enabled(True):
            with pytest.raises(HTTPException) as exc_info:
                self._dispatch_revoke(
                    {"provider": "openai"},
                    {"user_id": "viewer-1", "role": "viewer", "auth_source": "local"},
                )
            assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# A2A protocol tests
# ---------------------------------------------------------------------------


class TestA2AProvisionCredentials:
    """Test a2a:provision_credentials message handling."""

    @pytest.mark.asyncio
    async def test_a2a_provision_success(self):
        from webgui.routes.tasks import A2AMessage, receive_a2a_message

        store = CredentialStore()
        with _patch_enabled(True), _patch_store(store), \
             patch("webgui.routes.tasks.YEOMAN_A2A_ENABLED", True):
            msg = A2AMessage(
                id="msg-001",
                type="a2a:provision_credentials",
                fromPeerId="secureyeoman",
                toPeerId="agnostic-qa",
                payload={"provider": "openai", "api_key": "sk-from-yeoman"},
                timestamp=1708516800000,
            )
            result = await receive_a2a_message(
                msg, {"user_id": "yeoman:core", "role": "api_user", "auth_source": "yeoman_jwt"}
            )
        assert result["accepted"] is True
        assert result["type"] == "credentials_provisioned"

    @pytest.mark.asyncio
    async def test_a2a_provision_unauthorized(self):
        from webgui.routes.tasks import A2AMessage, receive_a2a_message

        with _patch_enabled(True), \
             patch("webgui.routes.tasks.YEOMAN_A2A_ENABLED", True):
            msg = A2AMessage(
                id="msg-002",
                type="a2a:provision_credentials",
                fromPeerId="unknown",
                toPeerId="agnostic-qa",
                payload={"provider": "openai", "api_key": "sk-bad"},
                timestamp=1708516800000,
            )
            with pytest.raises(HTTPException) as exc_info:
                await receive_a2a_message(
                    msg, {"user_id": "viewer", "role": "viewer", "auth_source": "local"}
                )
            assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_a2a_revoke_success(self):
        from webgui.routes.tasks import A2AMessage, receive_a2a_message

        store = CredentialStore()
        store._credentials["openai"] = ProvisionedCredential(
            provider="openai", api_key="sk-old"
        )
        with _patch_enabled(True), _patch_store(store), \
             patch("webgui.routes.tasks.YEOMAN_A2A_ENABLED", True):
            msg = A2AMessage(
                id="msg-003",
                type="a2a:revoke_credentials",
                fromPeerId="secureyeoman",
                toPeerId="agnostic-qa",
                payload={"provider": "openai"},
                timestamp=1708516800000,
            )
            result = await receive_a2a_message(
                msg, {"user_id": "yeoman:core", "role": "admin", "auth_source": "yeoman_jwt"}
            )
        assert result["accepted"] is True
        assert result["type"] == "credentials_revoked"

    @pytest.mark.asyncio
    async def test_a2a_provision_disabled(self):
        from webgui.routes.tasks import A2AMessage, receive_a2a_message

        with _patch_enabled(False), \
             patch("webgui.routes.tasks.YEOMAN_A2A_ENABLED", True):
            msg = A2AMessage(
                id="msg-004",
                type="a2a:provision_credentials",
                fromPeerId="secureyeoman",
                toPeerId="agnostic-qa",
                payload={"provider": "openai", "api_key": "sk-test"},
                timestamp=1708516800000,
            )
            with pytest.raises(HTTPException) as exc_info:
                await receive_a2a_message(
                    msg, {"user_id": "yeoman:core", "role": "admin", "auth_source": "yeoman_jwt"}
                )
            assert exc_info.value.status_code == 503


# ---------------------------------------------------------------------------
# LLM integration wiring tests
# ---------------------------------------------------------------------------


class TestLLMIntegrationCredentialResolution:
    """Verify LLMIntegrationService uses provisioned credentials."""

    def test_resolve_falls_back_to_env_key(self):
        from config.llm_integration import LLMIntegrationService

        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-env-key"}):
            svc = LLMIntegrationService()
            with _patch_enabled(False):
                assert svc._resolve_api_key() == "sk-env-key"

    def test_resolve_prefers_provisioned(self):
        from config.llm_integration import LLMIntegrationService

        store = CredentialStore()
        store._credentials["openai"] = ProvisionedCredential(
            provider="openai", api_key="sk-provisioned"
        )
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-env-key"}), \
             _patch_enabled(True), _patch_store(store):
            svc = LLMIntegrationService()
            assert svc._resolve_api_key() == "sk-provisioned"

    def test_resolve_no_key_at_all(self):
        from config.llm_integration import LLMIntegrationService

        with patch.dict("os.environ", {}, clear=True), \
             _patch_enabled(False):
            # Remove OPENAI_API_KEY if present
            import os
            os.environ.pop("OPENAI_API_KEY", None)
            svc = LLMIntegrationService()
            assert svc._resolve_api_key() is None

    def test_detect_provider_openai(self):
        from config.llm_integration import LLMIntegrationService

        assert LLMIntegrationService._detect_provider("gpt-4o") == "openai"
        assert LLMIntegrationService._detect_provider("gpt-3.5-turbo") == "openai"

    def test_detect_provider_anthropic(self):
        from config.llm_integration import LLMIntegrationService

        assert LLMIntegrationService._detect_provider("anthropic/claude-3-sonnet") == "anthropic"
        assert LLMIntegrationService._detect_provider("claude-opus-4-5") == "anthropic"

    def test_detect_provider_google(self):
        from config.llm_integration import LLMIntegrationService

        assert LLMIntegrationService._detect_provider("gemini/gemini-2.0-flash") == "google"

    def test_detect_provider_ollama(self):
        from config.llm_integration import LLMIntegrationService

        assert LLMIntegrationService._detect_provider("ollama/llama3.3") == "ollama"


class TestModelManagerCredentialResolution:
    """Verify BaseModelProvider uses provisioned credentials."""

    def test_resolve_falls_back_to_config_key(self):
        from config.model_manager import OpenAIProvider

        provider = OpenAIProvider({"api_key": "sk-config", "type": "openai"})
        with _patch_enabled(False):
            assert provider._resolve_api_key() == "sk-config"

    def test_resolve_prefers_provisioned(self):
        from config.model_manager import OpenAIProvider

        store = CredentialStore()
        store._credentials["openai"] = ProvisionedCredential(
            provider="openai", api_key="sk-provisioned"
        )
        provider = OpenAIProvider({"api_key": "sk-config", "type": "openai"})
        with _patch_enabled(True), _patch_store(store):
            assert provider._resolve_api_key() == "sk-provisioned"

    def test_anthropic_resolve_prefers_provisioned(self):
        from config.model_manager import AnthropicProvider

        store = CredentialStore()
        store._credentials["anthropic"] = ProvisionedCredential(
            provider="anthropic", api_key="sk-ant-provisioned"
        )
        provider = AnthropicProvider({"api_key": "sk-ant-config", "type": "anthropic"})
        with _patch_enabled(True), _patch_store(store):
            assert provider._resolve_api_key() == "sk-ant-provisioned"
