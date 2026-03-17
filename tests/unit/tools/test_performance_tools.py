import os
import sys

import pytest

# Add the agents directory to Python path for importing
sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "agents", "performance"),
)

try:
    from qa_performance import (
        LoadTestingTool,
        PerformanceMonitoringTool,
        ResilienceValidationTool,
    )
except Exception:
    pytest.skip("qa_performance module not available", allow_module_level=True)


class TestPerformanceMonitoringTool:
    """Unit tests for PerformanceMonitoringTool"""

    def test_tool_initialization(self):
        """Test that the tool initializes correctly"""
        tool = PerformanceMonitoringTool()
        assert tool.name == "performance_monitoring"
        assert "performance" in tool.description.lower()

    def test_run_returns_metrics(self):
        """Test _run method returns performance metrics"""
        tool = PerformanceMonitoringTool()
        result = tool._run({"target_url": "https://example.com"})

        assert isinstance(result, dict)
        assert result["status"] == "completed"
        assert "metrics" in result
        assert "latency_ms" in result["metrics"]
        assert "throughput_rps" in result["metrics"]
        assert "cpu_usage" in result["metrics"]
        assert "memory_usage" in result["metrics"]

    def test_run_with_empty_specs(self):
        """Test _run method with empty system specs"""
        tool = PerformanceMonitoringTool()
        result = tool._run({})

        assert isinstance(result, dict)
        assert result["status"] == "completed"


class TestLoadTestingTool:
    """Unit tests for LoadTestingTool"""

    def test_tool_initialization(self):
        """Test that the tool initializes correctly"""
        tool = LoadTestingTool()
        assert tool.name == "load_testing"
        assert "load" in tool.description.lower()

    def test_run_returns_results(self):
        """Test _run method returns load test results"""
        tool = LoadTestingTool()
        result = tool._run(
            {
                "target_url": "https://example.com",
                "concurrent_users": 100,
                "duration_seconds": 60,
            }
        )

        assert isinstance(result, dict)
        assert result["status"] == "completed"
        assert "test_results" in result
        assert "concurrent_users" in result["test_results"]
        assert "response_time_avg" in result["test_results"]
        assert "error_rate" in result["test_results"]

    def test_run_with_empty_config(self):
        """Test _run method with empty config"""
        tool = LoadTestingTool()
        result = tool._run({})

        assert isinstance(result, dict)
        assert result["status"] == "completed"


class TestResilienceValidationTool:
    """Unit tests for ResilienceValidationTool"""

    def test_tool_initialization(self):
        """Test that the tool initializes correctly"""
        tool = ResilienceValidationTool()
        assert tool.name == "resilience_validation"
        assert "resilience" in tool.description.lower()

    def test_run_returns_results(self):
        """Test _run method returns resilience results"""
        tool = ResilienceValidationTool()
        result = tool._run(
            {
                "target_services": ["api", "database", "cache"],
                "failure_scenarios": ["network_partition", "service_crash"],
            }
        )

        assert isinstance(result, dict)
        assert result["status"] == "completed"
        assert "resilience_score" in result
        assert "recovery_time_seconds" in result
        assert "failure_scenarios_tested" in result

    def test_resilience_score_range(self):
        """Test that resilience score is in valid range"""
        tool = ResilienceValidationTool()
        result = tool._run({})

        assert 0.0 <= result["resilience_score"] <= 1.0

    def test_run_with_empty_config(self):
        """Test _run method with empty config"""
        tool = ResilienceValidationTool()
        result = tool._run({})

        assert isinstance(result, dict)
        assert result["status"] == "completed"
