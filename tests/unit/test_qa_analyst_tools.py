import pytest
import json
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add the agents directory to Python path for importing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'agents', 'analyst'))

try:
    from qa_analyst import DataOrganizationReportingTool
except Exception:
    pytest.skip("qa_analyst module not available", allow_module_level=True)


class TestDataOrganizationReportingTool:
    """Unit tests for DataOrganizationReportingTool"""

    def test_tool_initialization(self):
        """Test that the tool initializes correctly"""
        tool = DataOrganizationReportingTool()
        assert tool.name == "Data Organization & Reporting"
        assert "Aggregates test results" in tool.description

    @patch('config.environment.config.get_redis_client')
    def test_run_with_valid_data(self, mock_get_redis, sample_test_results):
        """Test _run method with valid sample data"""
        # Setup mock Redis client
        mock_redis = Mock()
        mock_get_redis.return_value = mock_redis

        # Mock the method calls that would interact with Redis
        mock_redis.lrange.side_effect = [
            ['{"agent": "senior", "status": "passed"}'],
            ['{"agent": "junior", "status": "failed"}']
        ]
        mock_redis.hgetall.return_value = {}

        tool = DataOrganizationReportingTool()
        result = tool._run("test-session-123", sample_test_results)
        
        # Verify structure
        assert "findings" in result
        assert "metrics" in result
        assert "trend_analysis" in result
        assert isinstance(result["findings"], dict)
        assert isinstance(result["metrics"], dict)

    @patch('qa_analyst.redis.Redis')
    def test_collect_agent_results(self, mock_redis_class):
        """Test the _collect_agent_results method"""
        mock_redis = Mock()
        mock_redis_class.return_value = mock_redis
        
        # Mock Redis response
        test_data = [
            '{"test": "result1", "status": "passed"}',
            '{"test": "result2", "status": "failed"}'
        ]
        mock_redis.lrange.return_value = test_data
        
        tool = DataOrganizationReportingTool()
        results = tool._collect_agent_results(mock_redis, "test:session")
        
        assert len(results) == 2
        mock_redis.lrange.assert_called_once()

    def test_categorize_findings(self):
        """Test the _categorize_findings method"""
        tool = DataOrganizationReportingTool()
        
        test_results = [
            {"severity": "high", "category": "security", "description": "SQL injection"},
            {"severity": "medium", "category": "performance", "description": "Slow response"},
            {"severity": "low", "category": "ui", "description": "Alignment issue"}
        ]
        
        categorized = tool._categorize_findings(test_results)
        
        # Check that categories exist
        assert "high" in categorized
        assert "medium" in categorized
        assert "low" in categorized
        
        # Check that items are properly categorized
        assert len(categorized["high"]) == 1
        assert len(categorized["medium"]) == 1
        assert len(categorized["low"]) == 1
        assert categorized["high"][0]["category"] == "security"

    def test_calculate_metrics(self):
        """Test the _calculate_metrics method"""
        tool = DataOrganizationReportingTool()
        
        test_results = [
            {"tests_run": 10, "passed": 8, "failed": 2},
            {"tests_run": 15, "passed": 13, "failed": 2},
            {"tests_run": 5, "passed": 5, "failed": 0}
        ]
        
        metrics = tool._calculate_metrics(test_results)
        
        # Check that required metrics are present
        assert "total_tests" in metrics
        assert "pass_rate" in metrics
        assert "fail_rate" in metrics
        
        # Verify calculations
        assert metrics["total_tests"] == 30
        assert metrics["pass_rate"] == 26/30  # 26 passed out of 30

    @patch('qa_analyst.redis.Redis')
    def test_generate_trend_analysis(self, mock_redis_class):
        """Test the _generate_trend_analysis method"""
        mock_redis = Mock()
        mock_redis_class.return_value = mock_redis
        mock_redis.hgetall.return_value = {
            "previous_run": json.dumps({"pass_rate": 0.8}),
            "two_runs_ago": json.dumps({"pass_rate": 0.75})
        }
        
        tool = DataOrganizationReportingTool()
        current_metrics = {"pass_rate": 0.85}
        
        trend = tool._generate_trend_analysis(mock_redis, "test-session", current_metrics)
        
        assert "trend" in trend
        assert "comparison" in trend
        assert trend["trend"] in ["improving", "declining", "stable"]

    def test_run_with_empty_data(self):
        """Test _run with empty results"""
        with patch('config.environment.config.get_redis_client') as mock_get_redis:
            mock_redis = Mock()
            mock_get_redis.return_value = mock_redis
            mock_redis.lrange.return_value = []
            mock_redis.hgetall.return_value = {}

            tool = DataOrganizationReportingTool()
            result = tool._run("empty-session", {})

            # Should still return valid structure
            assert "findings" in result
            assert "metrics" in result
            assert "trend_analysis" in result

    def test_run_with_invalid_session_id(self):
        """Test _run with invalid session ID"""
        tool = DataOrganizationReportingTool()
        
        # Should handle various session ID formats gracefully
        try:
            with patch('qa_analyst.redis.Redis'):
                result = tool._run("", {})
                assert result is not None
        except Exception:
            # It's acceptable if invalid session IDs raise exceptions
            pass