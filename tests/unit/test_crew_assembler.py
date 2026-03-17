"""Tests for agents/crew_assembler.py — team assembly and preset recommendation."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from agents.crew_assembler import (
    _build_agent_dict,
    _find_best_match,
    _get_known_agents,
    _normalize,
    assemble_team,
    recommend_preset,
)


class TestNormalize:
    def test_basic(self):
        assert _normalize("Senior QA Engineer") == "senior qa engineer"

    def test_hyphens_underscores(self):
        assert _normalize("qa-manager_lead") == "qa manager lead"

    def test_strips_whitespace(self):
        assert _normalize("  spaced  ") == "spaced"


class TestBuildAgentDict:
    def test_basic_fields(self):
        result = _build_agent_dict(
            agent_key="test-agent",
            name="Test Agent",
            role_str="Tester",
            goal="Test things",
            backstory="I test",
            focus="testing",
            domain="quality",
            tools=["ToolA"],
        )
        assert result["agent_key"] == "test-agent"
        assert result["role"] == "Tester"
        assert result["tools"] == ["ToolA"]
        assert result["celery_queue"] == "test_agent"
        assert result["redis_prefix"] == "test"

    def test_context_appended(self):
        result = _build_agent_dict(
            agent_key="a",
            name="A",
            role_str="R",
            goal="Base goal",
            backstory="Base story",
            focus="f",
            domain="d",
            tools=[],
            context="Focus on security",
        )
        assert "Focus on security" in result["goal"]
        assert "Focus on security" in result["backstory"]

    def test_lead_gets_delegation(self):
        result = _build_agent_dict(
            agent_key="a",
            name="A",
            role_str="R",
            goal="G",
            backstory="B",
            focus="f",
            domain="d",
            tools=[],
            is_lead=True,
        )
        assert result["allow_delegation"] is True

    def test_non_lead_no_delegation(self):
        result = _build_agent_dict(
            agent_key="a",
            name="A",
            role_str="R",
            goal="G",
            backstory="B",
            focus="f",
            domain="d",
            tools=[],
            is_lead=False,
        )
        assert "allow_delegation" not in result


class TestGetKnownAgents:
    def test_returns_agents(self):
        agents = _get_known_agents()
        assert len(agents) > 0
        assert all("agent_key" in a for a in agents)
        assert all("_domain" in a for a in agents)

    def test_does_not_mutate_registry(self):
        """Ensure _get_known_agents returns copies, not registry references."""
        from config.agent_registry import agent_registry

        agents = _get_known_agents()
        # Mutate the returned agents
        for a in agents:
            a["_test_mutation"] = True

        # Registry presets should be unaffected
        for preset_data in agent_registry._presets.values():
            for agent in preset_data.get("agents", []):
                assert "_test_mutation" not in agent


class TestFindBestMatch:
    def test_exact_name_match(self):
        agents = [
            {"agent_key": "qa-analyst", "name": "QA Analyst", "role": "QA Analyst"},
            {"agent_key": "ux-lead", "name": "UX Lead", "role": "UX Research Lead"},
        ]
        match = _find_best_match("QA Analyst", agents)
        assert match is not None
        assert match["agent_key"] == "qa-analyst"

    def test_exact_key_match(self):
        agents = [{"agent_key": "ux-lead", "name": "UX Lead", "role": "UX Lead"}]
        match = _find_best_match("ux-lead", agents)
        assert match is not None

    def test_no_match_for_novel_role(self):
        agents = [
            {"agent_key": "qa-analyst", "name": "QA Analyst", "role": "QA Analyst"},
        ]
        match = _find_best_match("Game Designer", agents)
        assert match is None

    def test_single_word_overlap_rejected(self):
        """Single common word like 'engineer' should not match."""
        agents = [
            {"agent_key": "backend-engineer", "name": "Backend Engineer", "role": "Backend & API Engineer"},
        ]
        match = _find_best_match("Sales Engineer", agents)
        assert match is None


class TestAssembleTeam:
    def test_empty_members(self):
        assert assemble_team([]) == []

    def test_single_novel_role(self):
        result = assemble_team([{"role": "Game Designer"}])
        assert len(result) == 1
        assert result[0]["agent_key"] == "game-designer"
        assert result[0]["domain"] == "custom"
        assert result[0]["allow_delegation"] is True  # first member is lead

    def test_known_role_matched(self):
        result = assemble_team([{"role": "QA Analyst"}])
        assert len(result) == 1
        assert result[0]["agent_key"] == "qa-analyst"

    def test_unique_keys_enforced(self):
        result = assemble_team([
            {"role": "Engineer"},
            {"role": "Engineer"},
        ])
        keys = [r["agent_key"] for r in result]
        assert len(keys) == len(set(keys))

    def test_context_passed_through(self):
        result = assemble_team([
            {"role": "Designer", "context": "Mobile gaming UX"},
        ])
        assert "Mobile gaming UX" in result[0]["goal"]

    def test_project_context_in_novel_backstory(self):
        result = assemble_team(
            [{"role": "Game Engineer"}],
            project_context="Unity RPG",
        )
        assert "Unity RPG" in result[0]["backstory"]


class TestRecommendPreset:
    def test_quality_keywords(self):
        rec = recommend_preset("Run regression tests and security scan")
        assert rec["domain"] == "quality"
        assert "quality" in rec["preset"]

    def test_software_engineering_keywords(self):
        rec = recommend_preset("Refactor the backend API and review code")
        assert rec["domain"] == "software-engineering"

    def test_design_keywords(self):
        rec = recommend_preset("Create wireframes and check WCAG accessibility")
        assert rec["domain"] == "design"

    def test_devops_keywords(self):
        rec = recommend_preset("Deploy to kubernetes and set up monitoring")
        assert rec["domain"] == "devops"

    def test_data_engineering_keywords(self):
        rec = recommend_preset("Build a data pipeline with kafka and airflow")
        assert rec["domain"] == "data-engineering"

    def test_ambiguous_defaults_to_complete(self):
        rec = recommend_preset("Do something")
        assert rec["preset"] == "complete-lean"

    def test_large_size_signal(self):
        rec = recommend_preset("Comprehensive enterprise security audit")
        assert rec["size"] == "large"

    def test_lean_size_signal(self):
        rec = recommend_preset("Quick MVP prototype test")
        assert rec["size"] == "lean"

    def test_alternatives_provided(self):
        rec = recommend_preset("Test the API code")
        assert "alternatives" in rec
        assert isinstance(rec["alternatives"], list)
