"""Local LLM inference offload.

When a GPU is available and ``AGNOS_LOCAL_INFERENCE_ENABLED=true``, eligible
LLM calls (small models, embeddings, reranking) are routed to a local
inference server (vLLM, Ollama, llama.cpp) instead of the cloud gateway.

The local inference router sits *in front of* litellm — it inspects the
requested model and, if it matches a locally-served model, rewrites the
call to point at the local server.  Otherwise the call passes through
unchanged to the cloud provider.

Environment variables
---------------------
AGNOS_LOCAL_INFERENCE_ENABLED
    Master switch.  Default ``false``.
AGNOS_LOCAL_INFERENCE_URL
    Base URL of the local inference server (e.g. ``http://localhost:11434``
    for Ollama, ``http://localhost:8000`` for vLLM).  Default
    ``http://localhost:11434``.
AGNOS_LOCAL_INFERENCE_PROVIDER
    Which local server: ``ollama``, ``vllm``, or ``openai`` (any
    OpenAI-compatible server).  Default ``ollama``.
AGNOS_LOCAL_INFERENCE_MODELS
    Comma-separated list of model names available locally (e.g.
    ``llama3.1:8b,nomic-embed-text,bge-reranker-v2-m3``).
AGNOS_LOCAL_INFERENCE_MAX_PARAMS_B
    Maximum model size (in billions of parameters) to route locally.
    Models larger than this are always sent to the cloud.  Default ``14``.
AGNOS_LOCAL_INFERENCE_GPU_MIN_FREE_MB
    Minimum free GPU VRAM (MB) required before routing locally.  If free
    memory is below this, fall back to cloud.  Default ``2000``.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

_ENABLED = os.getenv("AGNOS_LOCAL_INFERENCE_ENABLED", "false").lower() in (
    "true",
    "1",
    "yes",
)
_LOCAL_URL = os.getenv("AGNOS_LOCAL_INFERENCE_URL", "http://localhost:11434")
_PROVIDER = os.getenv("AGNOS_LOCAL_INFERENCE_PROVIDER", "ollama")
_LOCAL_MODELS_RAW = os.getenv("AGNOS_LOCAL_INFERENCE_MODELS", "")
_MAX_PARAMS_B = float(os.getenv("AGNOS_LOCAL_INFERENCE_MAX_PARAMS_B", "14"))
_GPU_MIN_FREE_MB = int(os.getenv("AGNOS_LOCAL_INFERENCE_GPU_MIN_FREE_MB", "2000"))

# Parse local model list into a set for O(1) lookup
_LOCAL_MODELS: set[str] = {
    m.strip().lower() for m in _LOCAL_MODELS_RAW.split(",") if m.strip()
}

# Heuristic model size estimates (billions of params) by name pattern
_MODEL_SIZE_HINTS: dict[str, float] = {
    "7b": 7,
    "8b": 8,
    "13b": 13,
    "14b": 14,
    "34b": 34,
    "70b": 70,
    "embed": 0.5,
    "rerank": 0.5,
    "nomic": 0.5,
    "bge": 0.5,
    "minilm": 0.1,
}


@dataclass
class InferenceRoute:
    """Where to send an LLM call."""

    local: bool
    model_name: str  # litellm-compatible model string
    base_url: str | None = None
    api_key: str | None = None
    reason: str = ""


def _estimate_params_b(model_name: str) -> float:
    """Estimate model size from its name."""
    name_lower = model_name.lower()
    for hint, size in _MODEL_SIZE_HINTS.items():
        if hint in name_lower:
            return size
    # Unknown — assume large to be safe
    return 100.0


def _gpu_has_headroom() -> bool:
    """Check if the GPU has enough free VRAM for local inference."""
    try:
        from config.gpu import detect_gpus

        status = detect_gpus()
        if not status.available:
            return False
        return status.free_memory_mb >= _GPU_MIN_FREE_MB
    except Exception:
        return False


def route_inference(
    requested_model: str,
    *,
    force_local: bool = False,
    force_cloud: bool = False,
) -> InferenceRoute:
    """Decide whether to route an LLM call locally or to the cloud.

    Args:
        requested_model: The model name requested by the caller.
        force_local: Override — always use local (fails if not available).
        force_cloud: Override — always use cloud.

    Returns:
        An InferenceRoute indicating where to send the call.
    """
    if force_cloud:
        return InferenceRoute(
            local=False, model_name=requested_model, reason="force_cloud"
        )

    if not _ENABLED and not force_local:
        return InferenceRoute(
            local=False, model_name=requested_model, reason="local_inference_disabled"
        )

    model_lower = requested_model.lower()

    # Strip provider prefix for matching (e.g. "ollama/llama3.1:8b" → "llama3.1:8b")
    bare_model = model_lower
    for prefix in ("ollama/", "openai/", "vllm/", "local/"):
        if bare_model.startswith(prefix):
            bare_model = bare_model[len(prefix) :]
            break

    # Check if model is in the local model list
    is_local_model = bare_model in _LOCAL_MODELS or any(
        bare_model.startswith(m) for m in _LOCAL_MODELS
    )

    if not is_local_model and not force_local:
        return InferenceRoute(
            local=False,
            model_name=requested_model,
            reason=f"model '{bare_model}' not in local model list",
        )

    # Check model size
    estimated_size = _estimate_params_b(bare_model)
    if estimated_size > _MAX_PARAMS_B and not force_local:
        return InferenceRoute(
            local=False,
            model_name=requested_model,
            reason=f"model too large ({estimated_size}B > {_MAX_PARAMS_B}B max)",
        )

    # Check GPU headroom
    if not _gpu_has_headroom() and not force_local:
        return InferenceRoute(
            local=False,
            model_name=requested_model,
            reason=f"insufficient GPU VRAM (need {_GPU_MIN_FREE_MB} MB free)",
        )

    # Route locally
    if _PROVIDER == "ollama":
        litellm_model = f"ollama/{bare_model}"
        base_url = _LOCAL_URL
    elif _PROVIDER == "vllm":
        litellm_model = f"openai/{bare_model}"
        base_url = f"{_LOCAL_URL}/v1"
    else:
        # Generic OpenAI-compatible
        litellm_model = f"openai/{bare_model}"
        base_url = f"{_LOCAL_URL}/v1"

    logger.info(
        "Routing '%s' to local inference (%s at %s)",
        requested_model,
        _PROVIDER,
        _LOCAL_URL,
    )

    return InferenceRoute(
        local=True,
        model_name=litellm_model,
        base_url=base_url,
        api_key=os.getenv("AGNOS_LOCAL_INFERENCE_API_KEY", ""),
        reason="routed_to_local",
    )


def get_local_models() -> list[dict[str, Any]]:
    """Return info about locally available models."""
    models = []
    for m in sorted(_LOCAL_MODELS):
        models.append(
            {
                "name": m,
                "estimated_params_b": _estimate_params_b(m),
                "eligible": _estimate_params_b(m) <= _MAX_PARAMS_B,
                "provider": _PROVIDER,
                "url": _LOCAL_URL,
            }
        )
    return models


def is_enabled() -> bool:
    """Whether local inference offload is enabled."""
    return _ENABLED
