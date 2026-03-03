"""
Unit tests for config/model_manager.py

Covers:
- models.json structure and schema validation
- agnos_gateway provider entry (AGNOS OS integration)
- ModelManager config loading and provider creation
- OpenAIProvider, AnthropicProvider, LocalLLMProvider, GoogleProvider construction
- env-var overrides for AGNOS_LLM_GATEWAY_* variables
"""

import json
import os
import sys
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

try:
    from config.model_manager import (
        ModelManager,
        OpenAIProvider,
        AnthropicProvider,
        LocalLLMProvider,
        GoogleProvider,
        BaseModelProvider,
    )
except ImportError:
    pytest.skip("model_manager module not available", allow_module_level=True)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MODELS_JSON_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "config", "models.json"
)


def load_models_json() -> dict:
    with open(MODELS_JSON_PATH) as f:
        return json.load(f)


def make_minimal_config(
    provider_type: str = "openai",
    base_url: str = "http://localhost:8088/v1",
    api_key: str = "test-key",
    model: str = "test-model",
    enabled: bool = True,
) -> dict:
    return {
        "type": provider_type,
        "name": "Test Provider",
        "base_url": base_url,
        "api_key": api_key,
        "model": model,
        "temperature": 0.1,
        "max_tokens": 1000,
        "enabled": enabled,
    }


# ---------------------------------------------------------------------------
# models.json schema tests
# ---------------------------------------------------------------------------


class TestModelsJsonSchema:
    """Validates the static models.json config file structure."""

    def test_file_exists(self):
        assert os.path.exists(MODELS_JSON_PATH), "config/models.json must exist"

    def test_valid_json(self):
        config = load_models_json()
        assert isinstance(config, dict)

    def test_top_level_keys(self):
        config = load_models_json()
        assert "providers" in config
        assert "primary_provider" in config
        assert "fallback_providers" in config

    def test_providers_is_dict(self):
        config = load_models_json()
        assert isinstance(config["providers"], dict)
        assert len(config["providers"]) > 0

    def test_all_providers_have_required_fields(self):
        config = load_models_json()
        required = {"type", "name", "base_url", "model", "enabled"}
        for name, provider in config["providers"].items():
            missing = required - set(provider.keys())
            assert not missing, f"Provider '{name}' missing fields: {missing}"

    def test_primary_provider_is_string(self):
        config = load_models_json()
        assert isinstance(config["primary_provider"], str)
        assert len(config["primary_provider"]) > 0

    def test_fallback_providers_is_list(self):
        config = load_models_json()
        assert isinstance(config["fallback_providers"], list)

    def test_standard_providers_present(self):
        config = load_models_json()
        providers = config["providers"]
        for expected in ("openai", "ollama", "custom_local"):
            assert expected in providers, f"Expected provider '{expected}' not found"

    def test_routing_config_present(self):
        config = load_models_json()
        assert "routing" in config
        routing = config["routing"]
        assert "strategy" in routing
        assert "retry_attempts" in routing
        assert "timeout_seconds" in routing


# ---------------------------------------------------------------------------
# agnos_gateway provider tests
# ---------------------------------------------------------------------------


class TestAgnosGatewayProvider:
    """Tests specific to the agnos_gateway provider entry (AGNOS OS integration)."""

    def setup_method(self):
        self.config = load_models_json()
        self.providers = self.config["providers"]

    def test_agnos_gateway_present(self):
        assert "agnos_gateway" in self.providers, (
            "agnos_gateway provider must be present in models.json"
        )

    def test_agnos_gateway_disabled_by_default(self):
        gw = self.providers["agnos_gateway"]
        assert gw.get("enabled") is False, (
            "agnos_gateway must be disabled by default to avoid breaking "
            "deployments that are not running on AGNOS OS"
        )

    def test_agnos_gateway_type_is_openai(self):
        """Must use type=openai so ModelManager creates an OpenAIProvider,
        which speaks the OpenAI-compatible API the AGNOS LLM Gateway exposes."""
        gw = self.providers["agnos_gateway"]
        assert gw["type"] == "openai"

    def test_agnos_gateway_default_url_contains_port_8088(self):
        """Default base_url should target localhost:8088 (agnosticos LLM Gateway)."""
        gw = self.providers["agnos_gateway"]
        assert "8088" in gw["base_url"]

    def test_agnos_gateway_url_uses_env_var(self):
        """base_url must reference AGNOS_LLM_GATEWAY_URL env var."""
        gw = self.providers["agnos_gateway"]
        assert "AGNOS_LLM_GATEWAY_URL" in gw["base_url"]

    def test_agnos_gateway_api_key_uses_env_var(self):
        gw = self.providers["agnos_gateway"]
        assert "AGNOS_LLM_GATEWAY_API_KEY" in gw.get("api_key", "")

    def test_agnos_gateway_model_uses_env_var(self):
        gw = self.providers["agnos_gateway"]
        assert "AGNOS_LLM_GATEWAY_MODEL" in gw["model"]

    def test_agnos_gateway_has_comment_field(self):
        """Provider entry should carry a _comment explaining its purpose."""
        gw = self.providers["agnos_gateway"]
        assert "_comment" in gw
        assert "AGNOS" in gw["_comment"]

    def test_agnos_gateway_not_in_fallback_providers_by_default(self):
        """agnos_gateway should not be a default fallback to preserve existing behaviour."""
        fallbacks = self.config.get("fallback_providers", [])
        assert "agnos_gateway" not in fallbacks


# ---------------------------------------------------------------------------
# ModelManager provider creation tests
# ---------------------------------------------------------------------------


class TestModelManagerProviderCreation:
    """Tests that ModelManager._create_provider builds the right type for each config."""

    def _make_manager_no_file(self) -> ModelManager:
        """Return a ModelManager that won't try to open a real config file."""
        with patch.object(ModelManager, "load_config", return_value={}):
            mgr = ModelManager.__new__(ModelManager)
            mgr.config_file = "config/models.json"
            mgr.providers = {}
            mgr.primary_provider = None
            mgr.fallback_providers = []
        return mgr

    def test_create_openai_provider(self):
        mgr = self._make_manager_no_file()
        cfg = make_minimal_config(provider_type="openai")
        provider = mgr._create_provider(cfg)
        assert isinstance(provider, OpenAIProvider)

    def test_create_anthropic_provider(self):
        mgr = self._make_manager_no_file()
        cfg = make_minimal_config(provider_type="anthropic")
        provider = mgr._create_provider(cfg)
        assert isinstance(provider, AnthropicProvider)

    def test_create_local_provider(self):
        mgr = self._make_manager_no_file()
        cfg = make_minimal_config(provider_type="local")
        provider = mgr._create_provider(cfg)
        assert isinstance(provider, LocalLLMProvider)

    def test_create_google_provider(self):
        mgr = self._make_manager_no_file()
        cfg = make_minimal_config(provider_type="google")
        provider = mgr._create_provider(cfg)
        assert isinstance(provider, GoogleProvider)

    def test_create_unknown_provider_returns_none(self):
        mgr = self._make_manager_no_file()
        cfg = make_minimal_config(provider_type="nonexistent_provider_xyz")
        provider = mgr._create_provider(cfg)
        assert provider is None

    def test_agnos_gateway_creates_openai_provider(self):
        """agnos_gateway uses type=openai, so it must produce an OpenAIProvider
        that targets the AGNOS LLM Gateway base_url."""
        mgr = self._make_manager_no_file()
        gw_config = load_models_json()["providers"]["agnos_gateway"].copy()
        # Resolve the env-var template for the test
        gw_config["base_url"] = "http://localhost:8088/v1"
        gw_config["api_key"] = "agnos-local"
        gw_config["model"] = "default"
        provider = mgr._create_provider(gw_config)
        assert isinstance(provider, OpenAIProvider)

    def test_agnos_gateway_provider_base_url(self):
        mgr = self._make_manager_no_file()
        gw_config = {
            "type": "openai",
            "name": "AGNOS LLM Gateway",
            "base_url": "http://localhost:8088/v1",
            "api_key": "agnos-local",
            "model": "default",
            "temperature": 0.1,
            "max_tokens": 4000,
        }
        provider = mgr._create_provider(gw_config)
        assert provider is not None
        assert provider.base_url == "http://localhost:8088/v1"

    def test_disabled_provider_not_loaded(self):
        """ModelManager.load_config skips providers where enabled=False."""
        disabled_config = {
            "providers": {
                "agnos_gateway": make_minimal_config(enabled=False),
            },
            "primary_provider": "agnos_gateway",
            "fallback_providers": [],
        }
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(disabled_config, f)
            tmp_path = f.name

        try:
            with patch("os.getcwd", return_value=os.path.dirname(tmp_path)):
                mgr = ModelManager(
                    config_file=os.path.basename(tmp_path)
                )
            assert "agnos_gateway" not in mgr.providers
        finally:
            os.unlink(tmp_path)

    def test_enabled_provider_is_loaded(self):
        enabled_config = {
            "providers": {
                "agnos_gateway": make_minimal_config(enabled=True),
            },
            "primary_provider": "agnos_gateway",
            "fallback_providers": [],
        }
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(enabled_config, f)
            tmp_path = f.name

        try:
            with patch("os.getcwd", return_value=os.path.dirname(tmp_path)):
                mgr = ModelManager(
                    config_file=os.path.basename(tmp_path)
                )
            assert "agnos_gateway" in mgr.providers
        finally:
            os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# AGNOS env-var integration tests
# ---------------------------------------------------------------------------


class TestAgnosEnvVars:
    """Validates that AGNOS_LLM_GATEWAY_* env vars are correctly applied
    when the agnos_gateway provider is enabled in a config file."""

    def _config_with_gateway_enabled(self, base_url_tpl: str) -> dict:
        return {
            "providers": {
                "agnos_gateway": {
                    "type": "openai",
                    "name": "AGNOS LLM Gateway",
                    "base_url": base_url_tpl,
                    "api_key": "agnos-local",
                    "model": "default",
                    "temperature": 0.1,
                    "max_tokens": 4000,
                    "enabled": True,
                }
            },
            "primary_provider": "agnos_gateway",
            "fallback_providers": [],
        }

    def test_provider_info_reflects_base_url(self):
        """ModelManager.get_provider_info returns the configured base_url."""
        cfg = self._config_with_gateway_enabled("http://localhost:8088/v1")
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(cfg, f)
            tmp_path = f.name

        try:
            with patch("os.getcwd", return_value=os.path.dirname(tmp_path)):
                mgr = ModelManager(config_file=os.path.basename(tmp_path))
            info = mgr.get_provider_info("agnos_gateway")
            assert info is not None
            assert info["base_url"] == "http://localhost:8088/v1"
        finally:
            os.unlink(tmp_path)

    def test_custom_gateway_url(self):
        """A non-default gateway URL (e.g. remote agnosticos host) is accepted."""
        cfg = self._config_with_gateway_enabled("http://192.168.1.50:8088/v1")
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(cfg, f)
            tmp_path = f.name

        try:
            with patch("os.getcwd", return_value=os.path.dirname(tmp_path)):
                mgr = ModelManager(config_file=os.path.basename(tmp_path))
            info = mgr.get_provider_info("agnos_gateway")
            assert info is not None
            assert "192.168.1.50" in info["base_url"]
        finally:
            os.unlink(tmp_path)

    def test_get_available_providers_includes_gateway_when_enabled(self):
        cfg = self._config_with_gateway_enabled("http://localhost:8088/v1")
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(cfg, f)
            tmp_path = f.name

        try:
            with patch("os.getcwd", return_value=os.path.dirname(tmp_path)):
                mgr = ModelManager(config_file=os.path.basename(tmp_path))
            assert "agnos_gateway" in mgr.get_available_providers()
        finally:
            os.unlink(tmp_path)

    def test_missing_provider_info_returns_none(self):
        cfg = self._config_with_gateway_enabled("http://localhost:8088/v1")
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(cfg, f)
            tmp_path = f.name

        try:
            with patch("os.getcwd", return_value=os.path.dirname(tmp_path)):
                mgr = ModelManager(config_file=os.path.basename(tmp_path))
            result = mgr.get_provider_info("nonexistent_provider")
            assert result is None
        finally:
            os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# OpenAIProvider unit tests (used by agnos_gateway)
# ---------------------------------------------------------------------------


class TestOpenAIProvider:
    """Unit tests for OpenAIProvider, which is the implementation class
    used for the agnos_gateway entry."""

    def test_init_stores_config(self):
        cfg = make_minimal_config(
            provider_type="openai",
            base_url="http://localhost:8088/v1",
            api_key="test-key",
            model="gpt-4",
        )
        provider = OpenAIProvider(cfg)
        assert provider.base_url == "http://localhost:8088/v1"
        assert provider.model == "gpt-4"
        assert provider.name == "Test Provider"
        assert provider.temperature == 0.1
        assert provider.max_tokens == 1000

    def test_init_sets_auth_header(self):
        cfg = make_minimal_config(api_key="my-secret-key")
        provider = OpenAIProvider(cfg)
        assert "Authorization" in provider.headers
        assert "my-secret-key" in provider.headers["Authorization"]

    def test_init_with_agnos_gateway_url(self):
        """OpenAIProvider created with agnos_gateway base_url should store it correctly."""
        cfg = make_minimal_config(base_url="http://localhost:8088/v1")
        provider = OpenAIProvider(cfg)
        assert provider.base_url == "http://localhost:8088/v1"

    def test_is_base_model_provider(self):
        cfg = make_minimal_config()
        provider = OpenAIProvider(cfg)
        assert isinstance(provider, BaseModelProvider)

    @pytest.mark.asyncio
    async def test_chat_completion_returns_error_on_connection_failure(self):
        """When the gateway is unreachable, chat_completion returns a failure dict."""
        cfg = make_minimal_config(
            base_url="http://localhost:19999/v1",  # nothing listening here
        )
        provider = OpenAIProvider(cfg)
        messages = [{"role": "user", "content": "hello"}]
        result = await provider.chat_completion(messages)
        assert isinstance(result, dict)
        assert result.get("success") is False

    @pytest.mark.asyncio
    async def test_test_connection_returns_false_on_failure(self):
        cfg = make_minimal_config(base_url="http://localhost:19999/v1")
        provider = OpenAIProvider(cfg)
        result = await provider.test_connection()
        assert result is False


# ---------------------------------------------------------------------------
# ModelManager.chat_completion routing tests
# ---------------------------------------------------------------------------


class TestModelManagerChatCompletion:
    """Tests ModelManager routing when agnos_gateway is the primary provider."""

    def _make_manager_with_mock_provider(
        self, provider_name: str = "agnos_gateway"
    ) -> tuple[ModelManager, MagicMock]:
        mock_provider = MagicMock()
        mock_provider.chat_completion = AsyncMock(
            return_value={"success": True, "content": "mock response"}
        )

        with patch.object(ModelManager, "load_config", return_value={}):
            mgr = ModelManager.__new__(ModelManager)
            mgr.config_file = "config/models.json"
            mgr.providers = {provider_name: mock_provider}
            mgr.primary_provider = provider_name
            mgr.fallback_providers = []
            mgr._raw_config = {}

        return mgr, mock_provider

    @pytest.mark.asyncio
    async def test_routes_to_primary_provider(self):
        mgr, mock_provider = self._make_manager_with_mock_provider("agnos_gateway")
        messages = [{"role": "user", "content": "test"}]
        result = await mgr.chat_completion(messages)
        assert result.get("success") is True
        mock_provider.chat_completion.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_routes_to_specified_provider(self):
        mgr, mock_provider = self._make_manager_with_mock_provider("agnos_gateway")
        messages = [{"role": "user", "content": "test"}]
        result = await mgr.chat_completion(messages, provider="agnos_gateway")
        assert result.get("success") is True

    @pytest.mark.asyncio
    async def test_returns_error_for_unknown_provider(self):
        mgr, _ = self._make_manager_with_mock_provider("agnos_gateway")
        messages = [{"role": "user", "content": "test"}]
        result = await mgr.chat_completion(messages, provider="nonexistent")
        assert result.get("success") is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_returns_error_when_no_providers(self):
        with patch.object(ModelManager, "load_config", return_value={}):
            mgr = ModelManager.__new__(ModelManager)
            mgr.config_file = "config/models.json"
            mgr.providers = {}
            mgr.primary_provider = "agnos_gateway"
            mgr.fallback_providers = []

        messages = [{"role": "user", "content": "test"}]
        result = await mgr.chat_completion(messages)
        assert result.get("success") is False
