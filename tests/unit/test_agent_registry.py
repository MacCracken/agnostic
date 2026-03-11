import os
import sys

import pytest

# Add config path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

try:
    from config.agent_registry import AgentDefinition, AgentRegistry
except ImportError:
    pytest.skip("agent_registry module not available", allow_module_level=True)


class TestAgentDefinition:
    """Unit tests for AgentDefinition dataclass"""

    def test_creation(self):
        ad = AgentDefinition(
            agent_key="test-agent",
            name="Test Agent",
            role="test_agent",
            focus="Testing",
            tools=["ToolA"],
            complexity="high",
            celery_task="test_agent.handle",
            celery_queue="test_agent",
            redis_prefix="test",
        )
        assert ad.agent_key == "test-agent"
        assert ad.role == "test_agent"
        assert ad.celery_task == "test_agent.handle"

    def test_hash(self):
        ad1 = AgentDefinition("a", "A", "a", "", [], "low", "", "", "")
        ad2 = AgentDefinition("a", "A", "a", "", [], "low", "", "", "")
        assert hash(ad1) == hash(ad2)

    def test_different_keys_different_hash(self):
        ad1 = AgentDefinition("a", "A", "a", "", [], "low", "", "", "")
        ad2 = AgentDefinition("b", "B", "b", "", [], "low", "", "", "")
        assert hash(ad1) != hash(ad2)


class TestAgentRegistry:
    """Unit tests for AgentRegistry"""

    def test_initialization(self):
        registry = AgentRegistry()
        agents = registry.get_all_agents()
        assert len(agents) > 0

    def test_get_agent_senior(self):
        registry = AgentRegistry()
        agent = registry.get_agent("senior-qa")
        assert agent is not None
        assert agent.name == "Senior QA Engineer"
        assert agent.role == "senior_qa"
        assert agent.celery_task == "senior_qa.handle_complex_scenario"
        assert agent.celery_queue == "senior_qa"
        assert agent.redis_prefix == "senior"

    def test_get_agent_nonexistent(self):
        registry = AgentRegistry()
        assert registry.get_agent("nonexistent-agent") is None

    def test_get_all_agents_includes_standard_agents(self):
        registry = AgentRegistry()
        keys = [a.agent_key for a in registry.get_all_agents()]
        for expected in ["qa-manager", "senior-qa", "junior-qa", "qa-analyst"]:
            assert expected in keys, f"Expected {expected} in registry"

    def test_get_agents_for_team_standard(self):
        registry = AgentRegistry()
        team = registry.get_agents_for_team("standard")
        keys = [a.agent_key for a in team]
        assert "qa-manager" in keys
        assert "senior-qa" in keys
        assert "junior-qa" in keys

    def test_get_agents_for_team_lean(self):
        registry = AgentRegistry()
        team = registry.get_agents_for_team("lean")
        keys = [a.agent_key for a in team]
        assert "qa-manager" in keys
        assert len(keys) <= 4  # lean teams are small

    def test_route_task_senior(self):
        registry = AgentRegistry()
        scenario = {"assigned_to": "senior", "name": "Complex test"}
        agent = registry.route_task(scenario)
        assert agent is not None
        assert agent.agent_key == "senior-qa"

    def test_route_task_junior(self):
        registry = AgentRegistry()
        scenario = {"assigned_to": "junior", "name": "Regression test"}
        agent = registry.route_task(scenario)
        assert agent is not None
        assert agent.agent_key == "junior-qa"

    def test_route_task_performance(self):
        registry = AgentRegistry()
        scenario = {"assigned_to": "performance", "name": "Load test"}
        agent = registry.route_task(scenario)
        assert agent is not None
        assert agent.agent_key == "performance"

    def test_route_task_security(self):
        registry = AgentRegistry()
        scenario = {"assigned_to": "security_compliance", "name": "OWASP scan"}
        agent = registry.route_task(scenario)
        assert agent is not None
        assert agent.agent_key == "security-compliance"

    def test_route_task_analyst(self):
        registry = AgentRegistry()
        scenario = {"assigned_to": "analyst", "name": "Report"}
        agent = registry.route_task(scenario)
        assert agent is not None
        assert agent.agent_key == "qa-analyst"

    def test_get_agent_for_complexity(self):
        registry = AgentRegistry()
        # "complex" should route to senior-qa per team_config.json
        agent = registry.get_agent_for_complexity("complex")
        assert agent is not None
        assert agent.agent_key == "senior-qa"

    def test_get_agent_for_complexity_simple(self):
        registry = AgentRegistry()
        agent = registry.get_agent_for_complexity("simple")
        assert agent is not None
        assert agent.agent_key == "junior-qa"
