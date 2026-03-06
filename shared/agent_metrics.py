"""
Agent metrics aggregation for the dashboard.

Reads from Prometheus metric objects (in-process, no scraping needed) and
returns per-agent statistics for task completion, success rates, and LLM usage.
"""

import logging
from typing import Any

from shared.metrics import (
    AGENTS_ACTIVE,
    LLM_CALLS_TOTAL,
    LLM_TOKENS_COMPLETION,
    LLM_TOKENS_PROMPT,
    PROMETHEUS_AVAILABLE,
    TASKS_TOTAL,
)

logger = logging.getLogger(__name__)

AGENT_NAMES = [
    "qa-manager",
    "senior-qa",
    "junior-qa",
    "qa-analyst",
    "security-compliance",
    "performance",
]


def get_agent_metrics() -> list[dict[str, Any]]:
    """Return per-agent metrics summary."""
    if not PROMETHEUS_AVAILABLE:
        return [{"agent": name, "available": False} for name in AGENT_NAMES]

    results = []
    for agent in AGENT_NAMES:
        success = _get_counter_value(TASKS_TOTAL, {"agent": agent, "status": "success"})
        failure = _get_counter_value(TASKS_TOTAL, {"agent": agent, "status": "error"})
        total = success + failure

        results.append(
            {
                "agent": agent,
                "tasks_total": total,
                "tasks_success": success,
                "tasks_failed": failure,
                "success_rate": round(success / total, 4) if total > 0 else None,
                "prompt_tokens": _get_counter_value(
                    LLM_TOKENS_PROMPT, {"agent": agent}
                ),
                "completion_tokens": _get_counter_value(
                    LLM_TOKENS_COMPLETION, {"agent": agent}
                ),
                "active": _get_gauge_value(AGENTS_ACTIVE, {"agent": agent}),
            }
        )

    return results


def get_llm_metrics() -> dict[str, Any]:
    """Return aggregated LLM usage metrics."""
    if not PROMETHEUS_AVAILABLE:
        return {"available": False}

    total_calls = 0
    total_errors = 0
    methods: dict[str, dict[str, int]] = {}

    for sample in _iter_samples(LLM_CALLS_TOTAL):
        method = sample.labels.get("method", "unknown")
        status = sample.labels.get("status", "unknown")
        if method not in methods:
            methods[method] = {"calls": 0, "errors": 0}
        if status == "success":
            methods[method]["calls"] += int(sample.value)
            total_calls += int(sample.value)
        elif status == "error":
            methods[method]["errors"] += int(sample.value)
            total_errors += int(sample.value)

    total = total_calls + total_errors
    return {
        "total_calls": total_calls,
        "total_errors": total_errors,
        "error_rate": round(total_errors / total, 4) if total > 0 else None,
        "by_method": methods,
    }


def _get_counter_value(counter: Any, labels: dict[str, str]) -> int:
    """Safely read a counter value for given labels (partial match)."""
    try:
        for sample in _iter_samples(counter):
            if all(sample.labels.get(k) == v for k, v in labels.items()):
                return int(sample.value)
    except Exception:
        pass
    return 0


def _get_gauge_value(gauge: Any, labels: dict[str, str]) -> float:
    """Safely read a gauge value for given labels."""
    try:
        for sample in _iter_samples(gauge):
            if all(sample.labels.get(k) == v for k, v in labels.items()):
                return sample.value
    except Exception:
        pass
    return 0.0


def _iter_samples(metric: Any):
    """Iterate over prometheus_client metric samples."""
    try:
        for m in metric.collect():
            yield from m.samples
    except Exception:
        return
