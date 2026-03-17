"""Tests for AgentRegistry preset loading, team sizing, and domain support."""

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from config.agent_registry import AgentRegistry


class TestPresetLoading:
    def test_loads_all_qa_presets(self):
        registry = AgentRegistry()
        names = registry.list_presets()
        assert "quality-lean" in names
        assert "quality-standard" in names
        assert "quality-large" in names

    def test_loads_all_domains_all_sizes(self):
        registry = AgentRegistry()
        names = registry.list_presets()
        for domain in ["quality", "software-engineering", "design", "data-engineering", "devops"]:
            for size in ["lean", "standard", "large"]:
                assert f"{domain}-{size}" in names, f"Missing preset {domain}-{size}"

    def test_all_presets_loaded(self):
        registry = AgentRegistry()
        # 5 domains x 3 sizes + complete-lean = 16
        assert len(registry.list_presets()) >= 16

    def test_get_preset_by_name(self):
        registry = AgentRegistry()
        preset = registry.get_preset("quality-standard")
        assert preset is not None
        assert preset["name"] == "quality-standard"
        assert "agents" in preset

    def test_get_nonexistent_preset(self):
        registry = AgentRegistry()
        assert registry.get_preset("nonexistent") is None

    def test_all_presets_have_size_field(self):
        registry = AgentRegistry()
        for name in registry.list_presets():
            preset = registry.get_preset(name)
            assert "size" in preset, f"Preset {name} missing size field"
            assert preset["size"] in ("lean", "standard", "large")

    def test_all_presets_have_domain_field(self):
        registry = AgentRegistry()
        for name in registry.list_presets():
            preset = registry.get_preset(name)
            assert "domain" in preset, f"Preset {name} missing domain field"


class TestListPresetsFiltering:
    def test_filter_by_domain(self):
        registry = AgentRegistry()
        qa_presets = registry.list_presets(domain="quality")
        assert len(qa_presets) == 3
        assert all("quality" in n for n in qa_presets)

    def test_filter_by_size(self):
        registry = AgentRegistry()
        lean_presets = registry.list_presets(size="lean")
        # 5 domains + complete-lean = 6
        assert len(lean_presets) >= 5
        assert all("lean" in n for n in lean_presets)

    def test_filter_by_domain_and_size(self):
        registry = AgentRegistry()
        result = registry.list_presets(domain="design", size="large")
        assert result == ["design-large"]

    def test_list_domains(self):
        registry = AgentRegistry()
        domains = registry.list_domains()
        for expected in ["quality", "software-engineering", "design", "data-engineering", "devops"]:
            assert expected in domains


class TestQATeamSize:
    def test_default_standard(self):
        registry = AgentRegistry()
        assert registry.get_default_size() == "standard"

    def test_env_override(self):
        registry = AgentRegistry()
        with patch.dict(os.environ, {"QA_TEAM_SIZE": "large"}):
            assert registry.get_default_size() == "large"

    def test_preset_name_mapping(self):
        registry = AgentRegistry()
        assert registry.get_preset_name("quality", "lean") == "quality-lean"
        assert registry.get_preset_name("quality", "standard") == "quality-standard"
        assert registry.get_preset_name("quality", "large") == "quality-large"

    def test_generic_preset_name(self):
        registry = AgentRegistry()
        assert registry.get_preset_name("design", "large") == "design-large"
        assert registry.get_preset_name("devops", "lean") == "devops-lean"
        assert registry.get_preset_name("software-engineering", "standard") == "software-engineering-standard"


class TestTeamAgents:
    def test_qa_standard_has_6_agents(self):
        registry = AgentRegistry()
        team = registry.get_agents_for_team("standard")
        assert len(team) == 6

    def test_qa_lean_has_3_agents(self):
        registry = AgentRegistry()
        team = registry.get_agents_for_team("lean")
        assert len(team) == 3
        keys = [a.agent_key for a in team]
        assert "qa-manager" in keys
        assert "qa-executor" in keys
        assert "qa-analyst" in keys

    def test_qa_large_has_9_agents(self):
        registry = AgentRegistry()
        team = registry.get_agents_for_team("large")
        assert len(team) == 9

    def test_unknown_size_falls_back_to_standard(self):
        registry = AgentRegistry()
        team = registry.get_agents_for_team("nonexistent")
        assert len(team) == 6

    def test_design_lean(self):
        registry = AgentRegistry()
        team = registry.get_agents_for_team("lean", domain="design")
        assert len(team) == 2
        keys = [a.agent_key for a in team]
        assert "ux-lead" in keys

    def test_design_standard(self):
        registry = AgentRegistry()
        team = registry.get_agents_for_team("standard", domain="design")
        assert len(team) == 4

    def test_design_large(self):
        registry = AgentRegistry()
        team = registry.get_agents_for_team("large", domain="design")
        assert len(team) == 7

    def test_software_engineering_lean(self):
        registry = AgentRegistry()
        team = registry.get_agents_for_team("lean", domain="software-engineering")
        assert len(team) == 2

    def test_software_engineering_standard(self):
        registry = AgentRegistry()
        team = registry.get_agents_for_team("standard", domain="software-engineering")
        assert len(team) == 5

    def test_software_engineering_large(self):
        registry = AgentRegistry()
        team = registry.get_agents_for_team("large", domain="software-engineering")
        assert len(team) == 8

    def test_data_engineering_sizes(self):
        registry = AgentRegistry()
        assert len(registry.get_agents_for_team("lean", domain="data-engineering")) == 2
        assert len(registry.get_agents_for_team("standard", domain="data-engineering")) == 3
        assert len(registry.get_agents_for_team("large", domain="data-engineering")) == 6

    def test_devops_sizes(self):
        registry = AgentRegistry()
        assert len(registry.get_agents_for_team("lean", domain="devops")) == 2
        assert len(registry.get_agents_for_team("standard", domain="devops")) == 3
        assert len(registry.get_agents_for_team("large", domain="devops")) == 6


class TestComplexityRouting:
    def test_simple_routes_to_junior(self):
        registry = AgentRegistry()
        agent = registry.get_agent_for_complexity("simple")
        assert agent is not None
        assert agent.agent_key == "junior-qa"

    def test_complex_routes_to_senior(self):
        registry = AgentRegistry()
        agent = registry.get_agent_for_complexity("complex")
        assert agent is not None
        assert agent.agent_key == "senior-qa"

    def test_unknown_falls_back_to_junior(self):
        registry = AgentRegistry()
        agent = registry.get_agent_for_complexity("unknown")
        assert agent is not None
        assert agent.agent_key == "junior-qa"
