"""
Prometheus metrics for the Agentic QA Team System.

Provides named metric objects (Counter, Histogram, Gauge) with a no-op
fallback when ``prometheus_client`` is not installed, so callers can
always call ``.labels(...).inc()`` / ``.observe()`` / ``.set()`` without
guarding imports.
"""

from __future__ import annotations

try:
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        Counter,
        Gauge,
        Histogram,
        generate_latest,
    )

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False


# ------------------------------------------------------------------
# No-op fallback when prometheus_client is absent
# ------------------------------------------------------------------


class _NoOpMetric:
    """Drop-in replacement that silently ignores all metric operations."""

    def labels(self, **_kwargs: object) -> _NoOpMetric:
        return self

    def inc(self, amount: float = 1) -> None:
        pass

    def dec(self, amount: float = 1) -> None:
        pass

    def observe(self, amount: float) -> None:
        pass

    def set(self, value: float) -> None:
        pass


# ------------------------------------------------------------------
# Metric definitions
# ------------------------------------------------------------------


def _counter(
    name: str, documentation: str, labelnames: tuple[str, ...]
) -> Counter | _NoOpMetric:
    if PROMETHEUS_AVAILABLE:
        return Counter(name, documentation, labelnames)
    return _NoOpMetric()


def _histogram(
    name: str, documentation: str, labelnames: tuple[str, ...]
) -> Histogram | _NoOpMetric:
    if PROMETHEUS_AVAILABLE:
        return Histogram(name, documentation, labelnames)
    return _NoOpMetric()


def _gauge(
    name: str, documentation: str, labelnames: tuple[str, ...]
) -> Gauge | _NoOpMetric:
    if PROMETHEUS_AVAILABLE:
        return Gauge(name, documentation, labelnames)
    return _NoOpMetric()


# Task metrics
TASKS_TOTAL = _counter(
    "qa_tasks_total",
    "Total number of QA tasks processed",
    ("agent", "status"),
)
TASK_DURATION = _histogram(
    "qa_task_duration_seconds",
    "Duration of QA task execution in seconds",
    ("agent",),
)

# LLM call metrics
LLM_CALLS_TOTAL = _counter(
    "qa_llm_calls_total",
    "Total number of LLM API calls",
    ("method", "status"),
)
LLM_CALL_DURATION = _histogram(
    "qa_llm_call_duration_seconds",
    "Duration of LLM API calls in seconds",
    ("method",),
)

# LLM token usage
LLM_TOKENS_PROMPT = _counter(
    "qa_llm_tokens_prompt_total",
    "Total prompt tokens consumed by LLM calls",
    ("agent", "method"),
)
LLM_TOKENS_COMPLETION = _counter(
    "qa_llm_tokens_completion_total",
    "Total completion tokens consumed by LLM calls",
    ("agent", "method"),
)

# HTTP request metrics
HTTP_REQUESTS_TOTAL = _counter(
    "qa_http_requests_total",
    "Total number of HTTP requests",
    ("method", "endpoint", "status_code"),
)

# Agent status metrics
AGENTS_ACTIVE = _gauge(
    "qa_agents_active",
    "Number of currently active agents",
    ("agent",),
)

# Circuit breaker metrics
CIRCUIT_BREAKER_STATE = _gauge(
    "qa_circuit_breaker_state",
    "Circuit breaker state (0=closed, 1=open, 2=half-open)",
    ("service",),
)

# Crew execution metrics
CREW_RUNS_TOTAL = _counter(
    "agnostic_crew_runs_total",
    "Total crew runs by preset/source and final status",
    ("source", "status"),
)
CREW_RUN_DURATION = _histogram(
    "agnostic_crew_run_duration_seconds",
    "End-to-end crew execution time in seconds",
    ("source",),
)
CREW_AGENT_COUNT = _histogram(
    "agnostic_crew_agent_count",
    "Number of agents per crew run",
    ("source",),
)
ACTIVE_CREW_TASKS = _gauge(
    "agnostic_active_crew_tasks",
    "Currently running crew tasks",
    (),
)

# Tool registry metrics
TOOL_REGISTRY_SIZE = _gauge(
    "agnostic_tool_registry_size",
    "Number of tools in the global tool registry",
    (),
)

# Definition cache metrics
DEFINITION_CACHE_HITS = _counter(
    "agnostic_definition_cache_hits_total",
    "Definition cache hits in AgentFactory",
    (),
)
DEFINITION_CACHE_MISSES = _counter(
    "agnostic_definition_cache_misses_total",
    "Definition cache misses in AgentFactory",
    (),
)

# GPU metrics
GPU_AGENTS_SCHEDULED = _counter(
    "agnostic_gpu_agents_scheduled_total",
    "Total agents scheduled on GPU",
    (),
)
GPU_MEMORY_RESERVED_MB = _gauge(
    "agnostic_gpu_memory_reserved_mb",
    "Total GPU memory currently reserved across active crews",
    (),
)


# ------------------------------------------------------------------
# Exposition helpers
# ------------------------------------------------------------------


def get_metrics_text() -> str:
    """Return Prometheus exposition format text, or empty string if unavailable."""
    if PROMETHEUS_AVAILABLE:
        return generate_latest().decode("utf-8")
    return ""


def get_content_type() -> str:
    """Return the MIME type for Prometheus exposition format."""
    if PROMETHEUS_AVAILABLE:
        return CONTENT_TYPE_LATEST
    return "text/plain; charset=utf-8"
