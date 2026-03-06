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
