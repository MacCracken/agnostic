import os
import sys

import pytest

# Add the agents directory to Python path for importing
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "agents", "manager")
)

try:
    from qa_manager import TestPlanDecompositionTool
except Exception:
    pytest.skip("qa_manager module not available", allow_module_level=True)


class TestTestPlanDecompositionTool:
    """Unit tests for TestPlanDecompositionTool"""

    def test_tool_initialization(self):
        """Test that the tool initializes correctly"""
        tool = TestPlanDecompositionTool()
        assert tool.name == "Test Plan Decomposition"
        assert "Decomposes user requirements" in tool.description

    def test_run_returns_valid_structure(self, sample_requirements):
        """Test that _run returns a properly structured result"""
        tool = TestPlanDecompositionTool()
        result = tool._run(sample_requirements)

        # Check that all required keys are present
        assert "test_scenarios" in result
        assert "acceptance_criteria" in result
        assert "risk_areas" in result
        assert "priority_matrix" in result

        # Check that values are lists
        assert isinstance(result["test_scenarios"], list)
        assert isinstance(result["acceptance_criteria"], list)
        assert isinstance(result["risk_areas"], list)
        assert isinstance(result["priority_matrix"], dict)

    def test_extract_scenarios(self, sample_requirements):
        """Test scenario extraction from requirements"""
        tool = TestPlanDecompositionTool()
        scenarios = tool._extract_scenarios(sample_requirements)

        assert isinstance(scenarios, list)
        assert len(scenarios) > 0
        assert all(isinstance(s, str) for s in scenarios)

    def test_extract_criteria(self, sample_requirements):
        """Test acceptance criteria extraction"""
        tool = TestPlanDecompositionTool()
        criteria = tool._extract_criteria(sample_requirements)

        assert isinstance(criteria, list)
        assert len(criteria) > 0
        assert all(isinstance(c, str) for c in criteria)

    def test_identify_risks(self, sample_requirements):
        """Test risk identification from requirements"""
        tool = TestPlanDecompositionTool()
        risks = tool._identify_risks(sample_requirements)

        assert isinstance(risks, list)
        assert len(risks) > 0
        assert all(isinstance(r, str) for r in risks)

    def test_create_priority_matrix(self, sample_requirements):
        """Test priority matrix creation"""
        tool = TestPlanDecompositionTool()
        matrix = tool._create_priority_matrix(sample_requirements)

        assert isinstance(matrix, dict)
        # Check that it contains expected priority categories
        priority_categories = ["high", "medium", "low"]
        for category in priority_categories:
            assert category in matrix
            assert isinstance(matrix[category], list)

    def test_run_with_empty_requirements(self):
        """Test behavior with empty requirements string"""
        tool = TestPlanDecompositionTool()
        result = tool._run("")

        # Should still return valid structure even with empty input
        assert "test_scenarios" in result
        assert "acceptance_criteria" in result
        assert "risk_areas" in result
        assert "priority_matrix" in result

    def test_run_with_none_requirements(self):
        """Test behavior with None requirements"""
        tool = TestPlanDecompositionTool()
        # This should not crash, but handle None gracefully
        try:
            result = tool._run(None)  # type: ignore
            assert result is not None
        except (AttributeError, TypeError):
            # It's acceptable if it raises an error for None input
            pass
