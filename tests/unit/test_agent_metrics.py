"""Tests for shared.agent_metrics — per-agent metrics aggregation."""

from unittest.mock import patch

import pytest


class TestGetAgentMetrics:
    """Tests for get_agent_metrics."""

    def test_returns_all_agents(self):
        from shared.agent_metrics import AGENT_NAMES, get_agent_metrics

        results = get_agent_metrics()
        agents = [r["agent"] for r in results]
        assert agents == AGENT_NAMES

    def test_without_prometheus(self):
        """When prometheus_client unavailable, all agents show available=False."""
        with patch("shared.agent_metrics.PROMETHEUS_AVAILABLE", False):
            from shared.agent_metrics import get_agent_metrics

            results = get_agent_metrics()
            for r in results:
                assert r["available"] is False

    def test_structure(self):
        """Each agent dict has expected keys."""
        from shared.agent_metrics import get_agent_metrics

        results = get_agent_metrics()
        expected_keys = {
            "agent",
            "tasks_total",
            "tasks_success",
            "tasks_failed",
            "success_rate",
            "prompt_tokens",
            "completion_tokens",
            "active",
        }
        for r in results:
            assert set(r.keys()) == expected_keys

    def test_success_rate_none_when_no_tasks(self):
        """success_rate is None when no tasks recorded."""
        from shared.agent_metrics import get_agent_metrics

        results = get_agent_metrics()
        for r in results:
            assert r["success_rate"] is None

    def test_defaults_to_zero(self):
        """Counters default to 0 when no data."""
        from shared.agent_metrics import get_agent_metrics

        results = get_agent_metrics()
        for r in results:
            assert r["tasks_total"] == 0
            assert r["tasks_success"] == 0
            assert r["tasks_failed"] == 0
            assert r["prompt_tokens"] == 0
            assert r["completion_tokens"] == 0


class TestGetLlmMetrics:
    """Tests for get_llm_metrics."""

    def test_structure(self):
        """Result has expected keys."""
        from shared.agent_metrics import get_llm_metrics

        result = get_llm_metrics()
        assert "total_calls" in result
        assert "total_errors" in result
        assert "error_rate" in result
        assert "by_method" in result

    def test_without_prometheus(self):
        """When prometheus unavailable, returns available=False."""
        with patch("shared.agent_metrics.PROMETHEUS_AVAILABLE", False):
            from shared.agent_metrics import get_llm_metrics

            result = get_llm_metrics()
            assert result["available"] is False

    def test_error_rate_none_when_no_calls(self):
        """error_rate is None when no calls recorded."""
        from shared.agent_metrics import get_llm_metrics

        result = get_llm_metrics()
        assert result["error_rate"] is None

    def test_by_method_empty_when_no_calls(self):
        """by_method is empty dict when no calls recorded."""
        from shared.agent_metrics import get_llm_metrics

        result = get_llm_metrics()
        assert result["by_method"] == {}


class TestSuccessRateCalculation:
    """Test success rate with mocked counter values."""

    def test_success_rate_calculation(self):
        """success_rate = success / (success + failure)."""
        with patch("shared.agent_metrics._get_counter_value") as mock_get:

            def side_effect(counter, labels):
                agent = labels.get("agent", "")
                status = labels.get("status", "")
                if agent == "qa-manager" and status == "success":
                    return 8
                if agent == "qa-manager" and status == "error":
                    return 2
                return 0

            mock_get.side_effect = side_effect

            from shared.agent_metrics import get_agent_metrics

            results = get_agent_metrics()
            mgr = next(r for r in results if r["agent"] == "qa-manager")
            assert mgr["tasks_total"] == 10
            assert mgr["success_rate"] == 0.8


class TestHelpers:
    """Tests for _get_counter_value, _get_gauge_value, _iter_samples."""

    def test_get_counter_value_matching(self):
        from types import SimpleNamespace
        from unittest.mock import MagicMock

        from shared.agent_metrics import _get_counter_value

        sample = SimpleNamespace(labels={"agent": "qa-manager", "status": "success"}, value=42)
        metric = MagicMock()
        inner = MagicMock()
        inner.samples = [sample]
        metric.collect.return_value = [inner]
        assert _get_counter_value(metric, {"agent": "qa-manager", "status": "success"}) == 42

    def test_get_counter_value_no_match(self):
        from types import SimpleNamespace
        from unittest.mock import MagicMock

        from shared.agent_metrics import _get_counter_value

        sample = SimpleNamespace(labels={"agent": "other"}, value=10)
        metric = MagicMock()
        inner = MagicMock()
        inner.samples = [sample]
        metric.collect.return_value = [inner]
        assert _get_counter_value(metric, {"agent": "qa-manager"}) == 0

    def test_get_counter_value_exception(self):
        from unittest.mock import MagicMock

        from shared.agent_metrics import _get_counter_value

        metric = MagicMock()
        metric.collect.side_effect = Exception("broken")
        assert _get_counter_value(metric, {}) == 0

    def test_get_gauge_value(self):
        from types import SimpleNamespace
        from unittest.mock import MagicMock

        from shared.agent_metrics import _get_gauge_value

        sample = SimpleNamespace(labels={"agent": "qa-manager"}, value=3.14)
        metric = MagicMock()
        inner = MagicMock()
        inner.samples = [sample]
        metric.collect.return_value = [inner]
        assert _get_gauge_value(metric, {"agent": "qa-manager"}) == 3.14

    def test_get_gauge_value_default(self):
        from unittest.mock import MagicMock

        from shared.agent_metrics import _get_gauge_value

        metric = MagicMock()
        inner = MagicMock()
        inner.samples = []
        metric.collect.return_value = [inner]
        assert _get_gauge_value(metric, {"agent": "missing"}) == 0.0

    def test_iter_samples_exception(self):
        from unittest.mock import MagicMock

        from shared.agent_metrics import _iter_samples

        metric = MagicMock()
        metric.collect.side_effect = Exception("broken")
        assert list(_iter_samples(metric)) == []

    def test_iter_samples_yields(self):
        from types import SimpleNamespace
        from unittest.mock import MagicMock

        from shared.agent_metrics import _iter_samples

        s1 = SimpleNamespace(labels={}, value=1)
        s2 = SimpleNamespace(labels={}, value=2)
        metric = MagicMock()
        inner = MagicMock()
        inner.samples = [s1, s2]
        metric.collect.return_value = [inner]
        assert list(_iter_samples(metric)) == [s1, s2]


class TestGetLlmMetricsWithData:
    def test_with_samples(self):
        from types import SimpleNamespace

        from shared.agent_metrics import get_llm_metrics

        samples = [
            SimpleNamespace(labels={"method": "generate", "status": "success"}, value=100),
            SimpleNamespace(labels={"method": "generate", "status": "error"}, value=5),
            SimpleNamespace(labels={"method": "analyze", "status": "success"}, value=50),
        ]

        def mock_iter(metric):
            yield from samples

        with patch("shared.agent_metrics._iter_samples", side_effect=mock_iter):
            result = get_llm_metrics()
        assert result["total_calls"] == 150
        assert result["total_errors"] == 5
        assert result["error_rate"] == pytest.approx(5 / 155, abs=0.001)
        assert "generate" in result["by_method"]
        assert result["by_method"]["generate"]["calls"] == 100
