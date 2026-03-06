import json
import logging
import os
from abc import ABC, abstractmethod
from typing import Any

import aiohttp

# Add config path for imports

logger = logging.getLogger(__name__)


class BaseModelProvider(ABC):
    """Abstract base class for model providers"""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.name = config.get("name", "unknown")
        self.base_url = config.get("base_url", "")
        self.api_key = config.get("api_key", "")
        self.model = config.get("model", "")
        self.temperature = config.get("temperature", 0.1)
        self.max_tokens = config.get("max_tokens", 4000)
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create a shared aiohttp session for connection pooling."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        """Close the shared aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    @abstractmethod
    async def chat_completion(
        self, messages: list[dict[str, str]], **kwargs: Any
    ) -> dict[str, Any]:
        """Perform chat completion"""
        pass

    @abstractmethod
    async def test_connection(self) -> bool:
        """Test connection to the model provider"""
        pass


class OpenAIProvider(BaseModelProvider):
    """OpenAI API provider"""

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self.base_url = config.get("base_url", "https://api.openai.com/v1")
        self.is_gateway = config.get("provider_type") == "agnos_gateway"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def chat_completion(
        self, messages: list[dict[str, str]], **kwargs: Any
    ) -> dict[str, Any]:
        """OpenAI chat completion"""
        url = f"{self.base_url}/chat/completions"

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": kwargs.get("temperature", self.temperature),
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
        }

        # Propagate agent-id header for AGNOS gateway per-agent token accounting
        headers = dict(self.headers)
        agent_role = kwargs.get("agent_role")
        if self.is_gateway and agent_role:
            headers["x-agent-id"] = agent_role

        try:
            session = await self._get_session()
            async with session.post(
                url, headers=headers, json=payload
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    return {
                        "success": True,
                        "content": result["choices"][0]["message"]["content"],
                        "usage": result.get("usage", {}),
                        "model": result["model"],
                    }
                else:
                    error_text = await response.text()
                    logger.error(f"OpenAI API error: {response.status} - {error_text}")
                    return {
                        "success": False,
                        "error": f"OpenAI API error: {response.status}",
                        "details": error_text,
                    }
        except Exception as e:
            logger.error(f"OpenAI connection error: {e}")
            return {"success": False, "error": "Connection error", "details": str(e)}

    async def test_connection(self) -> bool:
        """Test OpenAI connection"""
        try:
            test_messages = [{"role": "user", "content": "Hello, test connection"}]
            result = await self.chat_completion(test_messages, max_tokens=10)
            return result.get("success", False)
        except Exception as e:
            logger.error(f"OpenAI connection test failed: {e}")
            return False


class AnthropicProvider(BaseModelProvider):
    """Anthropic Claude API provider"""

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self.base_url = config.get("base_url", "https://api.anthropic.com/v1")
        self.headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

    async def chat_completion(
        self, messages: list[dict[str, str]], **kwargs
    ) -> dict[str, Any]:
        """Anthropic chat completion"""
        url = f"{self.base_url}/messages"

        # Convert messages to Anthropic format
        system_message = ""
        user_messages = []

        for msg in messages:
            if msg["role"] == "system":
                system_message = msg["content"]
            else:
                user_messages.append({"role": msg["role"], "content": msg["content"]})

        payload = {
            "model": self.model,
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
            "temperature": kwargs.get("temperature", self.temperature),
            "messages": user_messages,
        }

        if system_message:
            payload["system"] = system_message

        try:
            session = await self._get_session()
            async with session.post(
                url, headers=self.headers, json=payload
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    return {
                        "success": True,
                        "content": result["content"][0]["text"],
                        "usage": result.get("usage", {}),
                        "model": result["model"],
                    }
                else:
                    error_text = await response.text()
                    logger.error(
                        f"Anthropic API error: {response.status} - {error_text}"
                    )
                    return {
                        "success": False,
                        "error": f"Anthropic API error: {response.status}",
                        "details": error_text,
                    }
        except Exception as e:
            logger.error(f"Anthropic connection error: {e}")
            return {"success": False, "error": "Connection error", "details": str(e)}

    async def test_connection(self) -> bool:
        """Test Anthropic connection"""
        try:
            test_messages = [{"role": "user", "content": "Hello, test connection"}]
            result = await self.chat_completion(test_messages, max_tokens=10)
            return result.get("success", False)
        except Exception as e:
            logger.error(f"Anthropic connection test failed: {e}")
            return False


class LocalLLMProvider(BaseModelProvider):
    """Local LLM provider (Ollama, LM Studio, etc.)"""

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self.provider_type = config.get(
            "provider_type", "ollama"
        )  # ollama, lm_studio, custom
        self.stream = config.get("stream", False)

        # Set default headers based on provider type
        if self.provider_type == "ollama":
            self.headers = {"Content-Type": "application/json"}
        elif self.provider_type == "lm_studio":
            self.headers = {"Content-Type": "application/json"}
        else:
            self.headers = config.get("headers", {"Content-Type": "application/json"})

    async def chat_completion(
        self, messages: list[dict[str, str]], **kwargs
    ) -> dict[str, Any]:
        """Local LLM chat completion"""
        if self.provider_type == "ollama":
            return await self._ollama_completion(messages, **kwargs)
        elif self.provider_type == "lm_studio":
            return await self._lm_studio_completion(messages, **kwargs)
        else:
            return await self._custom_completion(messages, **kwargs)

    async def _ollama_completion(
        self, messages: list[dict[str, str]], **kwargs
    ) -> dict[str, Any]:
        """Ollama API completion"""
        url = f"{self.base_url}/api/chat"

        # Convert messages to Ollama format
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": self.stream,
            "options": {
                "temperature": kwargs.get("temperature", self.temperature),
                "num_predict": kwargs.get("max_tokens", self.max_tokens),
            },
        }

        try:
            session = await self._get_session()
            async with session.post(
                url, headers=self.headers, json=payload
            ) as response:
                if response.status == 200:
                    return await self._parse_streaming_response(
                        response, format="ollama"
                    )
                else:
                    error_text = await response.text()
                    logger.error(f"Ollama API error: {response.status} - {error_text}")
                    return {
                        "success": False,
                        "error": f"Ollama API error: {response.status}",
                        "details": error_text,
                    }
        except Exception as e:
            logger.error(f"Ollama connection error: {e}")
            return {"success": False, "error": "Connection error", "details": str(e)}

    async def _lm_studio_completion(
        self, messages: list[dict[str, str]], **kwargs
    ) -> dict[str, Any]:
        """LM Studio API completion (OpenAI-compatible)"""
        url = f"{self.base_url}/v1/chat/completions"

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": kwargs.get("temperature", self.temperature),
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
            "stream": self.stream,
        }

        try:
            session = await self._get_session()
            async with session.post(
                url, headers=self.headers, json=payload
            ) as response:
                if response.status == 200:
                    return await self._parse_streaming_response(
                        response, format="openai"
                    )
                else:
                    error_text = await response.text()
                    logger.error(
                        f"LM Studio API error: {response.status} - {error_text}"
                    )
                    return {
                        "success": False,
                        "error": f"LM Studio API error: {response.status}",
                        "details": error_text,
                    }
        except Exception as e:
            logger.error(f"LM Studio connection error: {e}")
            return {"success": False, "error": "Connection error", "details": str(e)}

    async def _custom_completion(
        self, messages: list[dict[str, str]], **kwargs
    ) -> dict[str, Any]:
        """Custom local LLM completion"""
        # Default to OpenAI-compatible format
        url = f"{self.base_url}/v1/chat/completions"

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": kwargs.get("temperature", self.temperature),
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
        }

        try:
            session = await self._get_session()
            async with session.post(
                url, headers=self.headers, json=payload
            ) as response:
                if response.status == 200:
                    return await self._parse_streaming_response(
                        response, format="custom"
                    )
                else:
                    error_text = await response.text()
                    logger.error(
                        f"Custom LLM API error: {response.status} - {error_text}"
                    )
                    return {
                        "success": False,
                        "error": f"Custom LLM API error: {response.status}",
                        "details": error_text,
                    }
        except Exception as e:
            logger.error(f"Custom LLM connection error: {e}")
            return {"success": False, "error": "Connection error", "details": str(e)}

    async def _parse_streaming_response(
        self, response: aiohttp.ClientResponse, format: str = "openai"
    ) -> dict[str, Any]:
        """Parse a streaming or non-streaming response in ollama, openai, or custom format."""
        if self.stream:
            content = ""
            async for line in response.content:
                if not line:
                    continue
                if format == "ollama":
                    try:
                        data = json.loads(line.decode().strip())
                        if "message" in data and "content" in data["message"]:
                            content += data["message"]["content"]
                    except json.JSONDecodeError:
                        continue
                else:
                    # openai-compatible SSE format (LM Studio, custom)
                    line_str = line.decode().strip()
                    if line_str.startswith("data: ") and not line_str.endswith(
                        "[DONE]"
                    ):
                        try:
                            data = json.loads(line_str[6:])
                            if "choices" in data and len(data["choices"]) > 0:
                                delta = data["choices"][0].get("delta", {})
                                if "content" in delta:
                                    content += delta["content"]
                        except json.JSONDecodeError:
                            continue
            return {
                "success": True,
                "content": content,
                "usage": {},
                "model": self.model,
            }

        # Non-streaming response
        result = await response.json()
        if format == "ollama":
            return {
                "success": True,
                "content": result["message"]["content"],
                "usage": result.get("usage", {}),
                "model": self.model,
            }
        elif format == "custom":
            # Try common response formats
            if "choices" in result and len(result["choices"]) > 0:
                content = result["choices"][0]["message"]["content"]
            elif "content" in result:
                content = result["content"]
            else:
                content = str(result)
            return {
                "success": True,
                "content": content,
                "usage": result.get("usage", {}),
                "model": self.model,
            }
        else:
            # openai-compatible
            return {
                "success": True,
                "content": result["choices"][0]["message"]["content"],
                "usage": result.get("usage", {}),
                "model": result.get("model", self.model),
            }

    async def test_connection(self) -> bool:
        """Test local LLM connection"""
        try:
            test_messages = [{"role": "user", "content": "Hello, test connection"}]
            result = await self.chat_completion(test_messages, max_tokens=10)
            return result.get("success", False)
        except Exception as e:
            logger.error(f"Local LLM connection test failed: {e}")
            return False


class GoogleProvider(BaseModelProvider):
    """Google Gemini API provider"""

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self.base_url = config.get(
            "base_url", "https://generativelanguage.googleapis.com/v1"
        )
        self.api_key = config.get("api_key", "")
        self.headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key,
        }

    async def chat_completion(
        self, messages: list[dict[str, str]], **kwargs
    ) -> dict[str, Any]:
        """Google Gemini chat completion"""
        url = f"{self.base_url}/models/{self.model}:generateContent"

        # Convert messages to Gemini format
        contents = []
        for msg in messages:
            if msg["role"] != "system":  # Gemini doesn't use system role in messages
                role = "user" if msg["role"] == "user" else "model"
                contents.append({"role": role, "parts": [{"text": msg["content"]}]})

        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": kwargs.get("temperature", self.temperature),
                "maxOutputTokens": kwargs.get("max_tokens", self.max_tokens),
            },
        }

        try:
            session = await self._get_session()
            async with session.post(
                url, headers=self.headers, json=payload
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    if "candidates" in result and len(result["candidates"]) > 0:
                        content = result["candidates"][0]["content"]["parts"][0]["text"]
                        return {
                            "success": True,
                            "content": content,
                            "usage": result.get("usageMetadata", {}),
                            "model": self.model,
                        }
                    else:
                        return {
                            "success": False,
                            "error": "No content in response",
                            "details": str(result),
                        }
                else:
                    error_text = await response.text()
                    logger.error(f"Google API error: {response.status} - {error_text}")
                    return {
                        "success": False,
                        "error": f"Google API error: {response.status}",
                        "details": error_text,
                    }
        except Exception as e:
            logger.error(f"Google connection error: {e}")
            return {"success": False, "error": "Connection error", "details": str(e)}

    async def test_connection(self) -> bool:
        """Test Google connection"""
        try:
            test_messages = [{"role": "user", "content": "Hello, test connection"}]
            result = await self.chat_completion(test_messages, max_tokens=10)
            return result.get("success", False)
        except Exception as e:
            logger.error(f"Google connection test failed: {e}")
            return False


class ModelManager:
    """Manages multiple model providers and routing"""

    def __init__(self, config_file: str = "config/models.json") -> None:
        self.config_file = config_file
        self.providers: dict[str, BaseModelProvider] = {}
        self.primary_provider: str | None = None
        self.fallback_providers: list[str] = []
        self._raw_config: dict[str, Any] = {}
        self.load_config()

    def load_config(self) -> dict[str, Any]:
        """Load model configuration from file"""
        try:
            config_path = os.path.join(os.getcwd(), self.config_file)
            if os.path.exists(config_path):
                with open(config_path) as f:
                    config = json.load(f)

                # Auto-enable AGNOS gateway when env var is set
                gateway_enabled = os.getenv(
                    "AGNOS_LLM_GATEWAY_ENABLED", ""
                ).lower() in ("true", "1", "yes")
                if gateway_enabled and "agnos_gateway" in config.get("providers", {}):
                    config["providers"]["agnos_gateway"]["enabled"] = True
                    logger.info("AGNOS LLM Gateway auto-enabled via AGNOS_LLM_GATEWAY_ENABLED")

                # Initialize providers
                for provider_name, provider_config in config.get(
                    "providers", {}
                ).items():
                    if provider_config.get("enabled", True):
                        provider = self._create_provider(provider_config)
                        if provider:
                            self.providers[provider_name] = provider

                # Set primary and fallback providers
                self.primary_provider = config.get("primary_provider")
                self.fallback_providers = config.get("fallback_providers", [])

                self._raw_config = config
                logger.info(f"Loaded {len(self.providers)} model providers")
                logger.info(f"Primary provider: {self.primary_provider}")
                return config

            else:
                logger.warning(f"Model config file not found: {config_path}")
                self._create_default_config()
                return {}

        except Exception as e:
            logger.error(f"Error loading model config: {e}")
            self._create_default_config()
            return {}

    def _create_provider(self, config: dict[str, Any]) -> BaseModelProvider | None:
        """Create a provider instance based on configuration"""
        provider_type = config.get("type", "").lower()

        try:
            if provider_type == "openai":
                return OpenAIProvider(config)
            elif provider_type == "anthropic":
                return AnthropicProvider(config)
            elif (
                provider_type == "local"
                or provider_type == "ollama"
                or provider_type == "lm_studio"
            ):
                return LocalLLMProvider(config)
            elif provider_type == "google":
                return GoogleProvider(config)
            else:
                logger.error(f"Unknown provider type: {provider_type}")
                return None
        except Exception as e:
            logger.error(
                f"Error creating provider {config.get('name', 'unknown')}: {e}"
            )
            return None

    def _create_default_config(self) -> dict[str, Any]:
        """Create default configuration for OpenAI"""
        default_config = {
            "providers": {
                "openai": {
                    "type": "openai",
                    "name": "OpenAI",
                    "base_url": "https://api.openai.com/v1",
                    "api_key": os.getenv("OPENAI_API_KEY", ""),
                    "model": os.getenv("OPENAI_MODEL", "gpt-4"),
                    "temperature": 0.1,
                    "max_tokens": 4000,
                    "enabled": True,
                }
            },
            "primary_provider": "openai",
            "fallback_providers": [],
        }

        # Save default config
        config_dir = os.path.join(os.getcwd(), "config")
        os.makedirs(config_dir, exist_ok=True)
        config_path = os.path.join(config_dir, "models.json")

        with open(config_path, "w") as f:
            json.dump(default_config, f, indent=2)

        # Load the default config
        self.load_config()
        return default_config

    async def chat_completion(
        self, messages: list[dict[str, str]], provider: str | None = None, **kwargs
    ) -> dict[str, Any]:
        """Perform chat completion with specified or primary provider"""
        target_provider = provider or self.primary_provider

        if not target_provider or target_provider not in self.providers:
            return {
                "success": False,
                "error": "Provider not available",
                "details": f"Provider '{target_provider}' not found or not enabled",
            }

        # Use cached config for agent-specific settings
        config = self._raw_config

        # Check for agent-specific model configuration
        agent_role = kwargs.get("agent_role")
        if agent_role and "agent_specific_models" in config:
            agent_config = config["agent_specific_models"].get(agent_role, {})
            preferred_provider = agent_config.get("preferred_provider", target_provider)

            # Use agent-specific temperature and tokens if specified
            if "temperature" in agent_config:
                kwargs["temperature"] = agent_config["temperature"]
            if "max_tokens" in agent_config:
                kwargs["max_tokens"] = agent_config["max_tokens"]

            # Use agent-specific fallback chain if configured
            agent_fallbacks = agent_config.get(
                "fallback_providers", self.fallback_providers
            )
        else:
            preferred_provider = target_provider
            agent_fallbacks = self.fallback_providers

        # Try preferred provider first
        if preferred_provider in self.providers:
            logger.info(
                f"Using preferred provider for {agent_role}: {preferred_provider}"
            )
            result = await self.providers[preferred_provider].chat_completion(
                messages, **kwargs
            )

            # If preferred fails and fallbacks are configured, try them
            if not result.get("success", False) and agent_fallbacks:
                for fallback_provider in agent_fallbacks:
                    if (
                        fallback_provider in self.providers
                        and fallback_provider != preferred_provider
                    ):
                        logger.info(f"Trying fallback provider: {fallback_provider}")
                        fallback_result = await self.providers[
                            fallback_provider
                        ].chat_completion(messages, **kwargs)
                        if fallback_result.get("success", False):
                            logger.info(
                                f"Fallback provider {fallback_provider} succeeded"
                            )
                            fallback_result["fallback_used"] = fallback_provider
                            return fallback_result

            return result
        else:
            # Fallback to original target provider if preferred is not available
            result = await self.providers[target_provider].chat_completion(
                messages, **kwargs
            )

            # If primary fails and fallbacks are configured, try them
            if not result.get("success", False) and self.fallback_providers:
                for fallback_provider in self.fallback_providers:
                    if (
                        fallback_provider in self.providers
                        and fallback_provider != target_provider
                    ):
                        logger.info(f"Trying fallback provider: {fallback_provider}")
                        fallback_result = await self.providers[
                            fallback_provider
                        ].chat_completion(messages, **kwargs)
                        if fallback_result.get("success", False):
                            logger.info(
                                f"Fallback provider {fallback_provider} succeeded"
                            )
                            fallback_result["fallback_used"] = fallback_provider
                            return fallback_result

            return result

    async def test_all_connections(self) -> dict[str, bool]:
        """Test connections to all enabled providers"""
        results = {}

        for provider_name, provider in self.providers.items():
            try:
                results[provider_name] = await provider.test_connection()
            except Exception as e:
                logger.error(f"Error testing provider {provider_name}: {e}")
                results[provider_name] = False

        return results

    def get_available_providers(self) -> list[str]:
        """Get list of available provider names"""
        return list(self.providers.keys())

    async def gateway_health(self) -> dict[str, Any]:
        """Check AGNOS LLM Gateway health, if enabled."""
        if "agnos_gateway" not in self.providers:
            return {"enabled": False}

        provider = self.providers["agnos_gateway"]
        # The gateway exposes /health on the base URL (without /v1 suffix)
        base = provider.base_url.rstrip("/")
        if base.endswith("/v1"):
            base = base[:-3]
        health_url = f"{base}/health"

        try:
            session = await provider._get_session()
            async with session.get(health_url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                healthy = resp.status == 200
                body = await resp.json() if healthy else {}
                return {"enabled": True, "healthy": healthy, "detail": body}
        except Exception as e:
            return {"enabled": True, "healthy": False, "error": str(e)}

    def get_provider_info(self, provider_name: str) -> dict[str, Any] | None:
        """Get information about a specific provider"""
        if provider_name in self.providers:
            provider = self.providers[provider_name]
            return {
                "name": provider.name,
                "model": provider.model,
                "base_url": provider.base_url,
                "type": provider.__class__.__name__,
            }
        return None

    async def close(self) -> None:
        """Close all provider sessions (aiohttp/httpx clients)."""
        for name, provider in self.providers.items():
            try:
                await provider.close()
            except Exception as e:
                logger.warning(f"Error closing provider {name}: {e}")


# Global model manager instance
model_manager = ModelManager()
