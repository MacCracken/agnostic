"""
Universal LLM Adapter for CrewAI
Provides compatibility between the model manager and CrewAI's expected interface.
crewai 1.x uses litellm internally; this module returns a crewai.LLM instance
configured from the project model manager or environment variables.
"""

import logging
import os
from typing import Any

try:
    from model_manager import model_manager
except ImportError:
    logging.getLogger(__name__).warning("model_manager not available, using fallback")
    model_manager = None

try:
    from crewai import LLM as CrewLLM  # type: ignore

    _CREWAI_LLM_AVAILABLE = True
except ImportError:
    _CREWAI_LLM_AVAILABLE = False

logger = logging.getLogger(__name__)

# Provider → litellm model prefix mapping
_PROVIDER_PREFIXES: dict[str, str] = {
    "openai": "",  # e.g. "gpt-4o" (no prefix needed for openai)
    "anthropic": "anthropic/",
    "google": "gemini/",
    "ollama": "ollama/",
    "lmstudio": "openai/",  # LM Studio exposes an OpenAI-compatible API
}


def _build_model_string(provider: str, model_name: str) -> str:
    """Build litellm model string from provider + model name."""
    prefix = _PROVIDER_PREFIXES.get(provider, f"{provider}/")
    if model_name.startswith(prefix):
        return model_name
    return f"{prefix}{model_name}"


def create_llm(
    provider_name: str | None = None,
    model_name: str | None = None,
    temperature: float = 0.1,
    max_tokens: int = 4000,
    **kwargs: Any,
) -> Any:
    """
    Create an LLM instance for CrewAI.

    Returns a ``crewai.LLM`` object on crewai 1.x, or a plain dict describing
    the model spec (used as fallback when crewai is not installed in the local
    dev env which runs Python 3.14).

    Args:
        provider_name: LLM provider (openai, anthropic, google, ollama, lmstudio)
        model_name:    Model identifier.  If None, reads OPENAI_MODEL from env.
        temperature:   Sampling temperature (default 0.1).
        max_tokens:    Max completion tokens (default 4000).
    """
    if not provider_name:
        provider_name = os.getenv("PRIMARY_MODEL_PROVIDER", "openai")

    if not model_name:
        model_name = os.getenv("OPENAI_MODEL", "gpt-4o")

    model_string = _build_model_string(provider_name, model_name)

    if _CREWAI_LLM_AVAILABLE:
        try:
            llm = CrewLLM(
                model=model_string,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
            )
            logger.info("Created crewai LLM: %s (temp=%.2f)", model_string, temperature)
            return llm
        except Exception as exc:
            logger.error(
                "Failed to create crewai LLM %s: %s — falling back to model string",
                model_string,
                exc,
            )

    # crewai 1.x also accepts a plain model string for Agent(llm=...)
    logger.warning(
        "crewai.LLM not available; using bare model string '%s'", model_string
    )
    return model_string


def get_crewai_llm() -> Any:
    """
    Get a CrewAI-compatible LLM instance.
    This is the main entry point for CrewAI agent integration.
    """
    return create_llm()
