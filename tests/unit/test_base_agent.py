"""Tests for the generic agent framework: BaseAgent, AgentDefinition, AgentFactory, tool_registry."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# AgentDefinition
# ---------------------------------------------------------------------------


class TestAgentDefinition:
    """Tests for agents.base.AgentDefinition."""

    def _make(self, **overrides):
        from agents.base import AgentDefinition

        defaults = {
            "agent_key": "test-agent",
            "name": "Test Agent",
            "role": "Tester",
            "goal": "Test things",
            "backstory": "A test agent.",
        }
        defaults.update(overrides)
        return AgentDefinition(**defaults)

    def test_defaults(self):
        defn = self._make()
        assert defn.agent_key == "test-agent"
        assert defn.domain == "general"
        assert defn.complexity == "medium"
        assert defn.celery_queue == "test_agent"  # auto from key
        assert defn.redis_prefix == "test"  # first segment of key
        assert defn.allow_delegation is False
        assert defn.llm_temperature == 0.1
        assert defn.verbose is True
        assert defn.tools == []
        assert defn.tool_instances == []
        assert defn.metadata == {}

    def test_custom_values(self):
        defn = self._make(
            domain="qa",
            complexity="high",
            celery_queue="custom_q",
            redis_prefix="custom",
            allow_delegation=True,
            tools=["ToolA", "ToolB"],
        )
        assert defn.domain == "qa"
        assert defn.complexity == "high"
        assert defn.celery_queue == "custom_q"
        assert defn.redis_prefix == "custom"
        assert defn.allow_delegation is True
        assert defn.tools == ["ToolA", "ToolB"]

    def test_to_dict_roundtrip(self):
        defn = self._make(domain="devops", tools=["Deploy"])
        d = defn.to_dict()
        assert d["agent_key"] == "test-agent"
        assert d["domain"] == "devops"
        assert d["tools"] == ["Deploy"]

        from agents.base import AgentDefinition

        restored = AgentDefinition.from_dict(d)
        assert restored.agent_key == defn.agent_key
        assert restored.domain == defn.domain
        assert restored.tools == defn.tools

    def test_repr(self):
        defn = self._make()
        r = repr(defn)
        assert "test-agent" in r
        assert "Test Agent" in r

    def test_from_dict_ignores_tool_instances(self):
        from agents.base import AgentDefinition

        d = {
            "agent_key": "x",
            "name": "X",
            "role": "R",
            "goal": "G",
            "backstory": "B",
            "tool_instances": ["should_be_ignored"],
        }
        defn = AgentDefinition.from_dict(d)
        assert defn.tool_instances == []


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------


class TestToolRegistry:
    def test_register_and_get(self):
        from agents.tool_registry import _REGISTRY, get_tool, register_tool_class

        class FakeTool:
            name = "fake"

        register_tool_class("FakeTool", FakeTool)
        assert get_tool("FakeTool") is FakeTool
        # cleanup
        _REGISTRY.pop("FakeTool", None)

    def test_decorator(self):
        from agents.tool_registry import _REGISTRY, register_tool

        @register_tool
        class AnotherFakeTool:
            name = "another_fake"

        assert _REGISTRY.get("AnotherFakeTool") is AnotherFakeTool
        _REGISTRY.pop("AnotherFakeTool", None)

    def test_get_missing_returns_none(self):
        from agents.tool_registry import get_tool

        assert get_tool("NonExistentTool") is None


# ---------------------------------------------------------------------------
# BaseAgent
# ---------------------------------------------------------------------------


class TestBaseAgent:
    """Tests for agents.base.BaseAgent with mocked infrastructure."""

    @pytest.fixture(autouse=True)
    def _mock_infra(self):
        """Mock Redis, Celery, LLM, and CrewAI Agent so we can test BaseAgent logic."""
        with (
            patch("agents.base.config") as mock_config,
            patch("agents.base.llm_service"),
            patch("agents.base.LLM") as mock_llm_cls,
            patch("agents.base.Agent") as mock_agent_cls,
        ):
            mock_config.get_redis_client.return_value = MagicMock()
            mock_config.get_celery_app.return_value = MagicMock()
            mock_llm_cls.return_value = MagicMock()
            mock_agent_cls.return_value = MagicMock()
            self.mock_config = mock_config
            self.mock_agent_cls = mock_agent_cls
            yield

    def _make_agent(self, **overrides):
        from agents.base import AgentDefinition, BaseAgent

        defaults = {
            "agent_key": "test-agent",
            "name": "Test Agent",
            "role": "Tester",
            "goal": "Test things",
            "backstory": "A test agent.",
        }
        defaults.update(overrides)
        defn = AgentDefinition(**defaults)
        return BaseAgent(defn)

    def test_init_creates_crewai_agent(self):
        agent = self._make_agent()
        self.mock_agent_cls.assert_called_once()
        call_kwargs = self.mock_agent_cls.call_args[1]
        assert call_kwargs["role"] == "Tester"
        assert call_kwargs["goal"] == "Test things"

    def test_init_uses_celery_queue_from_definition(self):
        self._make_agent(celery_queue="my_queue")
        self.mock_config.get_celery_app.assert_called_with("my_queue")

    def test_set_task_state(self):
        agent = self._make_agent(redis_prefix="tst")
        agent.set_task_state("sess1", "scen1", "in_progress", {"extra": "data"})
        agent.redis_client.set.assert_called_once()
        key = agent.redis_client.set.call_args[0][0]
        assert key == "tst:sess1:scen1"
        payload = json.loads(agent.redis_client.set.call_args[0][1])
        assert payload["status"] == "in_progress"
        assert payload["extra"] == "data"

    @pytest.mark.asyncio
    async def test_notify_manager(self):
        agent = self._make_agent()
        await agent.notify_manager("sess1", "scen1", {"result": "ok"})
        agent.redis_client.publish.assert_called_once()
        channel = agent.redis_client.publish.call_args[0][0]
        assert channel == "manager:sess1:notifications"

    @pytest.mark.asyncio
    async def test_handle_task_success(self):
        agent = self._make_agent()
        # Mock run_task to return a result
        with patch.object(agent, "run_task", return_value="crew output"):
            result = await agent.handle_task({
                "scenario": {"id": "s1", "name": "Test scenario"},
                "session_id": "sess1",
            })
        assert result["status"] == "completed"
        assert result["agent"] == "test-agent"

    @pytest.mark.asyncio
    async def test_handle_task_failure(self):
        agent = self._make_agent()
        with patch.object(agent, "run_task", side_effect=RuntimeError("boom")):
            result = await agent.handle_task({
                "scenario": {"id": "s1"},
                "session_id": "sess1",
            })
        assert result["status"] == "failed"
        assert "boom" in result["error"]

    def test_build_task_description(self):
        agent = self._make_agent(focus="Testing stuff")
        desc = agent._build_task_description({
            "scenario": {
                "name": "Regression",
                "description": "Run regression suite",
                "target_url": "https://example.com",
            },
        })
        assert "Regression" in desc
        assert "Testing stuff" in desc
        assert "https://example.com" in desc

    def test_resolve_tools_with_instances(self):
        """When tool_instances are provided, they're used directly."""
        from agents.base import AgentDefinition, BaseAgent

        mock_tool = MagicMock()
        defn = AgentDefinition(
            agent_key="t",
            name="T",
            role="R",
            goal="G",
            backstory="B",
            tool_instances=[mock_tool],
        )
        agent = BaseAgent(defn)
        # The CrewAI Agent was created with the mock tool
        call_kwargs = self.mock_agent_cls.call_args[1]
        assert mock_tool in call_kwargs["tools"]

    def test_resolve_tools_by_name(self):
        """When tools are specified by name, they're looked up in the registry."""
        from agents.tool_registry import _REGISTRY

        class FakeRegisteredTool:
            name = "fake_reg"

        _REGISTRY["FakeRegisteredTool"] = FakeRegisteredTool
        try:
            agent = self._make_agent(tools=["FakeRegisteredTool"])
            call_kwargs = self.mock_agent_cls.call_args[1]
            assert any(isinstance(t, FakeRegisteredTool) for t in call_kwargs["tools"])
        finally:
            _REGISTRY.pop("FakeRegisteredTool", None)


# ---------------------------------------------------------------------------
# AgentFactory
# ---------------------------------------------------------------------------


class TestAgentFactory:
    @pytest.fixture(autouse=True)
    def _mock_infra(self):
        with (
            patch("agents.base.config") as mock_config,
            patch("agents.base.llm_service"),
            patch("agents.base.LLM"),
            patch("agents.base.Agent"),
        ):
            mock_config.get_redis_client.return_value = MagicMock()
            mock_config.get_celery_app.return_value = MagicMock()
            yield

    def test_from_dict(self):
        from agents.factory import AgentFactory

        agent = AgentFactory.from_dict({
            "agent_key": "test",
            "name": "Test",
            "role": "R",
            "goal": "G",
            "backstory": "B",
        })
        assert agent.definition.agent_key == "test"

    def test_from_definition(self):
        from agents.base import AgentDefinition
        from agents.factory import AgentFactory

        defn = AgentDefinition(
            agent_key="d", name="D", role="R", goal="G", backstory="B"
        )
        agent = AgentFactory.from_definition(defn)
        assert agent.definition is defn

    def test_from_file_json(self, tmp_path):
        from agents.factory import AgentFactory

        data = {
            "agent_key": "file-agent",
            "name": "File Agent",
            "role": "R",
            "goal": "G",
            "backstory": "B",
            "domain": "testing",
        }
        p = tmp_path / "agent.json"
        p.write_text(json.dumps(data))

        # Clear cache so the temp file is loaded fresh
        AgentFactory._definition_cache.clear()
        agent = AgentFactory.from_file(p)
        assert agent.definition.agent_key == "file-agent"
        assert agent.definition.domain == "testing"
        AgentFactory._definition_cache.clear()

    def test_from_preset(self, tmp_path, monkeypatch):
        from agents import factory as factory_mod
        from agents.factory import AgentFactory

        preset_dir = tmp_path / "presets"
        preset_dir.mkdir()
        monkeypatch.setattr(factory_mod, "PRESETS_DIR", preset_dir)

        preset_data = {
            "name": "test-preset",
            "description": "Test preset",
            "domain": "testing",
            "agents": [
                {
                    "agent_key": "a1",
                    "name": "A1",
                    "role": "R",
                    "goal": "G",
                    "backstory": "B",
                },
                {
                    "agent_key": "a2",
                    "name": "A2",
                    "role": "R",
                    "goal": "G",
                    "backstory": "B",
                },
            ],
        }
        (preset_dir / "test-preset.json").write_text(json.dumps(preset_data))

        agents = AgentFactory.from_preset("test-preset")
        assert len(agents) == 2
        assert agents[0].definition.agent_key == "a1"
        assert agents[1].definition.agent_key == "a2"

    def test_from_preset_not_found(self, tmp_path, monkeypatch):
        from agents import factory as factory_mod
        from agents.factory import AgentFactory

        monkeypatch.setattr(factory_mod, "PRESETS_DIR", tmp_path)
        with pytest.raises(FileNotFoundError):
            AgentFactory.from_preset("nonexistent")

    def test_list_presets(self, tmp_path, monkeypatch):
        from agents import factory as factory_mod
        from agents.factory import AgentFactory

        preset_dir = tmp_path / "presets"
        preset_dir.mkdir()
        monkeypatch.setattr(factory_mod, "PRESETS_DIR", preset_dir)

        (preset_dir / "alpha.json").write_text(json.dumps({
            "description": "Alpha crew",
            "domain": "alpha",
            "agents": [{"agent_key": "a1", "name": "A1", "role": "R", "goal": "G", "backstory": "B"}],
        }))

        presets = AgentFactory.list_presets()
        assert len(presets) == 1
        assert presets[0]["name"] == "alpha"
        assert presets[0]["domain"] == "alpha"
        assert presets[0]["agent_count"] == 1

    def test_list_definitions(self, tmp_path, monkeypatch):
        from agents import factory as factory_mod
        from agents.factory import AgentFactory

        monkeypatch.setattr(factory_mod, "DEFINITIONS_DIR", tmp_path)

        (tmp_path / "my-agent.json").write_text(json.dumps({
            "agent_key": "my-agent",
            "name": "My Agent",
            "domain": "custom",
            "focus": "Custom stuff",
        }))

        defs = AgentFactory.list_definitions()
        assert len(defs) == 1
        assert defs[0]["agent_key"] == "my-agent"
        assert defs[0]["domain"] == "custom"


# ---------------------------------------------------------------------------
# Preset file validation
# ---------------------------------------------------------------------------


class TestPresetFiles:
    """Validate the actual preset JSON files ship valid definitions."""

    PRESETS_DIR = Path(__file__).parent.parent.parent / "agents" / "definitions" / "presets"

    def _load_preset(self, name: str) -> dict:
        path = self.PRESETS_DIR / f"{name}.json"
        assert path.exists(), f"Preset {name} not found at {path}"
        with open(path) as f:
            return json.load(f)

    @pytest.mark.parametrize("preset_name", ["qa-standard", "data-engineering", "devops"])
    def test_preset_structure(self, preset_name):
        data = self._load_preset(preset_name)
        assert "name" in data
        assert "description" in data
        assert "domain" in data
        assert "agents" in data
        assert len(data["agents"]) > 0

    @pytest.mark.parametrize("preset_name", ["qa-standard", "data-engineering", "devops"])
    def test_preset_agents_have_required_fields(self, preset_name):
        data = self._load_preset(preset_name)
        required = {"agent_key", "name", "role", "goal", "backstory"}
        for agent in data["agents"]:
            missing = required - set(agent.keys())
            assert not missing, f"Agent {agent.get('agent_key', '?')} missing: {missing}"

    def test_qa_standard_has_six_agents(self):
        data = self._load_preset("qa-standard")
        assert len(data["agents"]) == 6

    def test_qa_standard_agent_keys_match_existing(self):
        data = self._load_preset("qa-standard")
        keys = {a["agent_key"] for a in data["agents"]}
        expected = {"qa-manager", "senior-qa", "junior-qa", "qa-analyst", "security-compliance", "performance"}
        assert keys == expected
