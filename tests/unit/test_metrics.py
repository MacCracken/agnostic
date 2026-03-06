"""Unit tests for shared.metrics — Prometheus metrics with no-op fallback."""

import pytest


class TestNoOpMetrics:
    """Tests that always pass regardless of prometheus_client availability."""

    def test_noop_counter_inc(self):
        from shared.metrics import TASKS_TOTAL

        # Should not raise even without prometheus_client
        TASKS_TOTAL.labels(agent="test", status="success").inc()

    def test_noop_histogram_observe(self):
        from shared.metrics import TASK_DURATION

        TASK_DURATION.labels(agent="test").observe(1.5)

    def test_noop_gauge_set(self):
        from shared.metrics import AGENTS_ACTIVE

        AGENTS_ACTIVE.labels(agent="test").set(3)

    def test_llm_metrics_inc(self):
        from shared.metrics import LLM_CALLS_TOTAL, LLM_CALL_DURATION

        LLM_CALLS_TOTAL.labels(method="test", status="success").inc()
        LLM_CALL_DURATION.labels(method="test").observe(0.5)

    def test_llm_tokens_prompt_counter_exists(self):
        from shared.metrics import LLM_TOKENS_PROMPT

        LLM_TOKENS_PROMPT.labels(agent="test", method="test").inc(100)

    def test_llm_tokens_completion_counter_exists(self):
        from shared.metrics import LLM_TOKENS_COMPLETION

        LLM_TOKENS_COMPLETION.labels(agent="test", method="test").inc(50)

    def test_circuit_breaker_gauge(self):
        from shared.metrics import CIRCUIT_BREAKER_STATE

        CIRCUIT_BREAKER_STATE.labels(service="llm_api").set(0)

    def test_http_requests_counter(self):
        from shared.metrics import HTTP_REQUESTS_TOTAL

        HTTP_REQUESTS_TOTAL.labels(method="GET", endpoint="/api/test", status_code="200").inc()

    def test_get_metrics_text_returns_string(self):
        from shared.metrics import get_metrics_text

        result = get_metrics_text()
        assert isinstance(result, str)

    def test_get_content_type_returns_string(self):
        from shared.metrics import get_content_type

        result = get_content_type()
        assert isinstance(result, str)
        assert "text/" in result or "openmetrics" in result.lower()

    def test_prometheus_available_is_bool(self):
        from shared.metrics import PROMETHEUS_AVAILABLE

        assert isinstance(PROMETHEUS_AVAILABLE, bool)


@pytest.mark.skipif(
    not __import__("shared.metrics", fromlist=["PROMETHEUS_AVAILABLE"]).PROMETHEUS_AVAILABLE,
    reason="prometheus_client not installed",
)
class TestPrometheusMetrics:
    """Tests that only run when prometheus_client is available."""

    def test_metrics_text_contains_metric_names(self):
        from shared.metrics import TASKS_TOTAL, get_metrics_text

        TASKS_TOTAL.labels(agent="prom_test", status="ok").inc()
        text = get_metrics_text()
        assert "qa_tasks_total" in text

    def test_content_type_is_prometheus(self):
        from shared.metrics import get_content_type

        ct = get_content_type()
        assert "text/plain" in ct or "openmetrics" in ct.lower()
