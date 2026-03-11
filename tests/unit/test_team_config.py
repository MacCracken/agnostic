"""Tests for config/team_config_loader.py — TeamConfig."""

import json
import os
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


def _make_config(config_path=None):
    from config.team_config_loader import TeamConfig

    return TeamConfig(config_path=config_path)


class TestLoadConfig:
    def test_loads_real_config(self):
        """Loads the actual team_config.json."""
        cfg = _make_config()
        assert "team_presets" in cfg._config

    def test_fallback_on_missing_file(self):
        cfg = _make_config("/nonexistent/path.json")
        assert "team_presets" in cfg._config
        assert "standard" in cfg._config["team_presets"]

    def test_fallback_on_invalid_json(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("not valid json{{{")
            f.flush()
            cfg = _make_config(f.name)
        os.unlink(f.name)
        assert "team_presets" in cfg._config

    def test_loads_custom_json(self):
        custom = {
            "team_presets": {"tiny": {"agent_count": 2, "agents": ["a", "b"]}},
            "default_team_size": "tiny",
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(custom, f)
            f.flush()
            cfg = _make_config(f.name)
        os.unlink(f.name)
        assert cfg._config["default_team_size"] == "tiny"


class TestGetTeamSize:
    def test_returns_default(self):
        cfg = _make_config()
        size = cfg.get_team_size()
        assert isinstance(size, str)

    def test_env_override(self):
        cfg = _make_config()
        with patch.dict(os.environ, {"QA_TEAM_SIZE": "large"}):
            assert cfg.get_team_size() == "large"


class TestGetTeamPreset:
    def test_returns_preset(self):
        cfg = _make_config()
        preset = cfg.get_team_preset()
        assert "agents" in preset or "agent_count" in preset

    def test_explicit_size(self):
        cfg = _make_config()
        preset = cfg.get_team_preset("standard")
        assert isinstance(preset, dict)

    def test_unknown_size_falls_back(self):
        cfg = _make_config()
        preset = cfg.get_team_preset("nonexistent")
        # Should fall back to standard or empty
        assert isinstance(preset, dict)


class TestGetAgentConfig:
    def test_returns_none_for_unknown(self):
        cfg = _make_config()
        assert cfg.get_agent_config("nonexistent-agent") is None

    def test_returns_config_if_present(self):
        custom = {
            "team_presets": {"standard": {"agents": []}},
            "agent_roles": {
                "qa-manager": {"focus": "orchestration", "tools": ["planner"]}
            },
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(custom, f)
            f.flush()
            cfg = _make_config(f.name)
        os.unlink(f.name)
        result = cfg.get_agent_config("qa-manager")
        assert result["focus"] == "orchestration"


class TestWorkflow:
    def test_get_workflow_mode(self):
        cfg = _make_config()
        mode = cfg.get_workflow_mode()
        assert isinstance(mode, str)

    def test_get_workflow_config(self):
        cfg = _make_config()
        wf = cfg.get_workflow_config()
        assert isinstance(wf, dict)


class TestRouting:
    def test_default_fallback(self):
        cfg = _make_config()
        route = cfg.get_routing_for_complexity("unknown")
        assert route == "junior-qa"

    def test_with_routing_config(self):
        custom = {
            "team_presets": {"standard": {"agents": []}},
            "complexity_routing": {
                "high": {"route_to": "senior-qa"},
            },
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(custom, f)
            f.flush()
            cfg = _make_config(f.name)
        os.unlink(f.name)
        assert cfg.get_routing_for_complexity("high") == "senior-qa"


class TestAgentQueries:
    def test_get_all_agents(self):
        cfg = _make_config()
        agents = cfg.get_all_agents_for_current_team()
        assert isinstance(agents, list)

    def test_is_agent_in_team(self):
        custom = {
            "team_presets": {"standard": {"agents": ["qa-manager", "senior-qa"]}},
            "default_team_size": "standard",
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(custom, f)
            f.flush()
            cfg = _make_config(f.name)
        os.unlink(f.name)
        assert cfg.is_agent_in_current_team("qa-manager") is True
        assert cfg.is_agent_in_current_team("nonexistent") is False

    def test_get_tools_for_agent(self):
        cfg = _make_config()
        tools = cfg.get_tools_for_agent("nonexistent")
        assert tools == []

    def test_get_agent_focus(self):
        cfg = _make_config()
        focus = cfg.get_agent_focus("nonexistent")
        assert focus == ""

    def test_get_delegation_rules(self):
        cfg = _make_config()
        rules = cfg.get_delegation_rules()
        assert isinstance(rules, dict)

    def test_get_agent_capabilities(self):
        cfg = _make_config()
        caps = cfg.get_agent_capabilities()
        assert isinstance(caps, dict)


class TestTeamSummary:
    def test_summary_structure(self):
        cfg = _make_config()
        summary = cfg.get_team_summary()
        assert "team_size" in summary
        assert "agent_count" in summary
        assert "agents" in summary
        assert "workflow_mode" in summary


class TestDynamicScaling:
    def test_default_true(self):
        cfg = _make_config()
        assert cfg.supports_dynamic_scaling() is True

    def test_explicit_false(self):
        custom = {
            "team_presets": {"standard": {"agents": []}},
            "supports_dynamic_scaling": False,
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(custom, f)
            f.flush()
            cfg = _make_config(f.name)
        os.unlink(f.name)
        assert cfg.supports_dynamic_scaling() is False
