"""
Agent Registry — config-driven agent discovery and task routing.

Reads agent definitions from team_config.json and provides:
- Agent lookup by key, role, or complexity
- Task routing (replaces hardcoded if/elif in qa_manager.py)
- Team-aware agent lists for WebGUI and orchestration
"""

import logging
from dataclasses import dataclass

from config.team_config_loader import team_config

logger = logging.getLogger(__name__)


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


# Default mappings for agents that don't have explicit fields in config.
# Convention: key "senior-qa" -> role "senior_qa" -> queue "senior_qa" -> prefix = first segment.
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


class AgentRegistry:
    """Config-driven agent registry.

    Loads agent definitions from team_config.json once and provides
    fast lookups for routing, display, and orchestration.
    """

    def __init__(self):
        self._agents: dict[str, AgentDefinition] = {}
        self._load_agents()

    def _load_agents(self):
        """Build AgentDefinition objects from team_config agent_roles."""
        config = team_config._config  # raw config dict
        agent_roles = config.get("agent_roles", {})

        for key, info in agent_roles.items():
            defaults = _AGENT_DEFAULTS.get(key, {})
            # Explicit config fields override defaults; fall back to convention.
            role = info.get("role", defaults.get("role", key.replace("-", "_")))
            celery_task = info.get(
                "celery_task",
                defaults.get("celery_task", f"{role}.handle_task"),
            )
            celery_queue = info.get("celery_queue", defaults.get("celery_queue", role))
            redis_prefix = info.get(
                "redis_prefix", defaults.get("redis_prefix", key.split("-")[0])
            )

            self._agents[key] = AgentDefinition(
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

        logger.info(f"AgentRegistry loaded {len(self._agents)} agent definitions")

    def get_agent(self, key: str) -> AgentDefinition | None:
        """Get agent definition by config key (e.g. 'senior-qa')."""
        return self._agents.get(key)

    def get_all_agents(self) -> list[AgentDefinition]:
        """Return all registered agent definitions."""
        return list(self._agents.values())

    def get_agents_for_team(self, size: str | None = None) -> list[AgentDefinition]:
        """Return agents for the given team size (or current default)."""
        agent_keys = team_config.get_all_agents_for_current_team()
        if size:
            preset = team_config.get_team_preset(size)
            agent_keys = preset.get("agents", agent_keys)

        return [self._agents[k] for k in agent_keys if k in self._agents]

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
        """Route by complexity using team_config complexity_routing."""
        route_to = team_config.get_routing_for_complexity(complexity)
        return self._agents.get(route_to)


# Singleton
agent_registry = AgentRegistry()
