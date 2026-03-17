"""
Agent Registry — preset-driven agent discovery and task routing.

Reads agent definitions from preset JSON files in agents/definitions/presets/
and provides:
- Agent lookup by key, role, or complexity
- Task routing (replaces hardcoded if/elif in qa_manager.py)
- Team-aware agent lists for WebGUI and orchestration
"""

import json
import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_PRESETS_DIR = os.path.join(
    os.path.dirname(__file__), "..", "agents", "definitions", "presets"
)

# All domains follow {domain}-{size} naming convention.
_DOMAINS = ["quality", "software-engineering", "design", "data-engineering", "devops"]
_SIZES = ["lean", "standard", "large"]


@dataclass(frozen=True)
class AgentDefinition:
    agent_key: str  # "senior-qa"
    name: str  # "Senior QA Engineer"
    role: str  # "senior_qa"
    focus: str
    tools: list[str]
    complexity: str
    celery_task: str  # "senior_qa.handle_complex_scenario"
    celery_queue: str  # "senior_qa"
    redis_prefix: str  # "senior"

    def __hash__(self):
        return hash(self.agent_key)


# Default celery task/queue mappings for core QA agents.
_AGENT_DEFAULTS = {
    "qa-manager": {
        "role": "qa_manager",
        "celery_task": "qa_manager.process_requirements",
        "celery_queue": "qa_manager",
        "redis_prefix": "manager",
    },
    "senior-qa": {
        "role": "senior_qa",
        "celery_task": "senior_qa.handle_complex_scenario",
        "celery_queue": "senior_qa",
        "redis_prefix": "senior",
    },
    "junior-qa": {
        "role": "junior_qa",
        "celery_task": "junior_qa.execute_regression_test",
        "celery_queue": "junior_qa",
        "redis_prefix": "junior",
    },
    "qa-analyst": {
        "role": "qa_analyst",
        "celery_task": "qa_analyst.analyze_and_report",
        "celery_queue": "qa_analyst",
        "redis_prefix": "analyst",
    },
    "security-compliance": {
        "role": "security_compliance",
        "celery_task": "security_compliance_agent.run_security_compliance_audit",
        "celery_queue": "security_compliance",
        "redis_prefix": "security_compliance",
    },
    "performance": {
        "role": "performance",
        "celery_task": "performance_agent.run_performance_suite",
        "celery_queue": "performance",
        "redis_prefix": "performance",
    },
}

# Maps the scenario "assigned_to" values used in qa_manager to agent keys.
_ASSIGNED_TO_AGENT_KEY = {
    "senior": "senior-qa",
    "junior": "junior-qa",
    "analyst": "qa-analyst",
    "security_compliance": "security-compliance",
    "performance": "performance",
    "manager": "qa-manager",
}

# Complexity → agent routing (previously in team_config.json).
_COMPLEXITY_ROUTING = {
    "trivial": "junior-qa",
    "simple": "junior-qa",
    "moderate": "junior-qa",
    "complex": "senior-qa",
    "critical": "senior-qa",
}


def _load_preset(name: str) -> dict | None:
    """Load a preset JSON file by name."""
    path = os.path.join(_PRESETS_DIR, f"{name}.json")
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning(f"Could not load preset {name}: {e}")
        return None


def _agent_def_from_info(key: str, info: dict) -> AgentDefinition:
    """Build an AgentDefinition from a preset agent entry."""
    defaults = _AGENT_DEFAULTS.get(key, {})
    # Internal role identifier (e.g. "senior_qa"), NOT the display role string.
    role = defaults.get("role", key.replace("-", "_"))
    celery_task = info.get(
        "celery_task",
        defaults.get("celery_task", f"{role}.handle_task"),
    )
    celery_queue = info.get("celery_queue", defaults.get("celery_queue", role))
    redis_prefix = info.get(
        "redis_prefix", defaults.get("redis_prefix", key.split("-")[0])
    )

    return AgentDefinition(
        agent_key=key,
        name=info.get("name", key),
        role=role,
        focus=info.get("focus", ""),
        tools=info.get("tools", []),
        complexity=info.get("complexity", "medium"),
        celery_task=celery_task,
        celery_queue=celery_queue,
        redis_prefix=redis_prefix,
    )


class AgentRegistry:
    """Preset-driven agent registry.

    Loads agent definitions from preset JSON files and provides
    fast lookups for routing, display, and orchestration.
    """

    def __init__(self):
        self._agents: dict[str, AgentDefinition] = {}
        self._presets: dict[str, dict] = {}
        self._load_all_presets()

    def _load_all_presets(self):
        """Load all preset files and index their agents."""
        if not os.path.isdir(_PRESETS_DIR):
            logger.warning(f"Presets directory not found: {_PRESETS_DIR}")
            return

        for filename in sorted(os.listdir(_PRESETS_DIR)):
            if not filename.endswith(".json"):
                continue
            name = filename.removesuffix(".json")
            preset = _load_preset(name)
            if preset:
                self._presets[name] = preset
                for agent_info in preset.get("agents", []):
                    key = agent_info.get("agent_key", "")
                    if key and key not in self._agents:
                        self._agents[key] = _agent_def_from_info(key, agent_info)

        logger.info(
            f"AgentRegistry loaded {len(self._agents)} agent definitions "
            f"from {len(self._presets)} presets"
        )

    def get_agent(self, key: str) -> AgentDefinition | None:
        """Get agent definition by config key (e.g. 'senior-qa')."""
        return self._agents.get(key)

    def get_all_agents(self) -> list[AgentDefinition]:
        """Return all registered agent definitions."""
        return list(self._agents.values())

    def get_default_size(self) -> str:
        """Return default team size from env var or 'standard'."""
        return os.getenv("QA_TEAM_SIZE", "standard")

    def get_preset_name(self, domain: str, size: str = "standard") -> str:
        """Map a domain + size to a preset name (e.g. 'design' + 'large' -> 'design-large')."""
        return f"{domain}-{size}"

    def get_agents_for_team(self, size: str | None = None, domain: str = "quality") -> list[AgentDefinition]:
        """Return agents for the given domain and team size."""
        size = size or self.get_default_size()
        preset_name = self.get_preset_name(domain, size)
        preset = self._presets.get(preset_name)
        if not preset:
            # Fall back to domain-standard, then quality-standard
            preset = self._presets.get(f"{domain}-standard", self._presets.get("quality-standard", {}))

        agent_keys = [a.get("agent_key") for a in preset.get("agents", [])]
        return [self._agents[k] for k in agent_keys if k in self._agents]

    def get_preset(self, name: str) -> dict | None:
        """Get a loaded preset by name."""
        return self._presets.get(name)

    def list_presets(self, domain: str | None = None, size: str | None = None) -> list[str]:
        """Return loaded preset names, optionally filtered by domain and/or size."""
        results = []
        for name, data in self._presets.items():
            if domain and data.get("domain") != domain:
                continue
            if size and data.get("size", "standard") != size:
                continue
            results.append(name)
        return results

    def list_domains(self) -> list[str]:
        """Return unique domains across all loaded presets."""
        return sorted({d.get("domain", "general") for d in self._presets.values()})

    def route_task(self, scenario: dict) -> AgentDefinition | None:
        """Route a scenario to the appropriate agent.

        Looks at scenario["assigned_to"] and maps it to an agent key.
        Falls back to complexity-based routing if no direct match.
        """
        assigned_to = scenario.get("assigned_to", "")

        # Direct match via assigned_to mapping
        agent_key = _ASSIGNED_TO_AGENT_KEY.get(assigned_to)
        if agent_key and agent_key in self._agents:
            return self._agents[agent_key]

        # Try assigned_to as a raw agent key
        if assigned_to in self._agents:
            return self._agents[assigned_to]

        # Fall back to complexity routing
        complexity = scenario.get("complexity") or scenario.get("priority", "medium")
        return self.get_agent_for_complexity(complexity)

    def get_agent_for_complexity(self, complexity: str) -> AgentDefinition | None:
        """Route by complexity level."""
        route_to = _COMPLEXITY_ROUTING.get(complexity, "junior-qa")
        return self._agents.get(route_to)


# Singleton
agent_registry = AgentRegistry()
