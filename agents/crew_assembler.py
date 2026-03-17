"""Crew assembler — build agent definitions from structured team specifications.

Takes a team spec (members with roles, context, and optional constraints) and
produces a list of inline agent definitions ready for CrewRunRequest.

This enables natural-language-style team composition:
    "I need a 4-person team: UX researcher, game engineer, game designer, project lead"

The assembler:
1. Tries to match each requested role to an existing agent definition in the registry
2. Falls back to generating an inline definition for novel roles (game designer, etc.)
3. Returns a list of agent definition dicts ready for the crew builder
"""

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_PRESETS_DIR = Path(__file__).parent / "definitions" / "presets"


# ---------------------------------------------------------------------------
# Models (plain dicts — no pydantic dependency here)
# ---------------------------------------------------------------------------


def assemble_team(members: list[dict], project_context: str = "") -> list[dict]:
    """Build agent definitions from a list of team member specs.

    Each member dict should have:
        role (str, required): The role title (e.g. "UX Researcher", "Game Engineer")
        context (str, optional): Additional context about what this member should focus on
        tools (list[str], optional): Specific tools this agent should have

    Args:
        members: List of member specification dicts.
        project_context: Overall project description to enrich backstories.

    Returns:
        List of agent definition dicts suitable for CrewRunRequest.agent_definitions.
    """
    if not members:
        return []

    # Load all known agents from presets for matching
    known_agents = _load_known_agents()

    definitions = []
    used_keys: set[str] = set()

    for i, member in enumerate(members):
        role = member.get("role", "").strip()
        if not role:
            continue

        context = member.get("context", "")
        tools = member.get("tools", [])
        is_lead = member.get("lead", False) or i == 0

        # Try to find a matching known agent
        match = _find_best_match(role, known_agents)

        if match:
            defn = _adapt_known_agent(match, role, context, tools, is_lead)
        else:
            defn = _generate_agent_definition(role, context, tools, is_lead, project_context)

        # Ensure unique agent keys
        base_key = defn["agent_key"]
        if base_key in used_keys:
            defn["agent_key"] = f"{base_key}-{i}"
        used_keys.add(defn["agent_key"])

        definitions.append(defn)

    return definitions


def recommend_preset(description: str) -> dict:
    """Recommend the best preset and size based on a task description.

    Returns a dict with:
        preset: recommended preset name
        domain: the domain
        size: recommended size
        reason: why this was chosen
        alternatives: other options to consider
    """
    description_lower = description.lower()

    # Keyword → domain scoring
    domain_signals: dict[str, list[str]] = {
        "quality": [
            "test", "qa", "quality", "bug", "regression", "security scan",
            "performance test", "load test", "compliance", "audit",
        ],
        "software-engineering": [
            "code", "implement", "build", "develop", "refactor", "api",
            "backend", "frontend", "engineer", "architect", "review code",
            "pr review", "pull request", "technical debt", "migration",
        ],
        "design": [
            "design", "ux", "ui", "wireframe", "mockup", "prototype",
            "accessibility", "wcag", "usability", "figma", "sketch",
            "user research", "a11y",
        ],
        "data-engineering": [
            "data", "pipeline", "etl", "elt", "warehouse", "lake",
            "spark", "kafka", "airflow", "dbt", "schema", "analytics",
        ],
        "devops": [
            "deploy", "ci/cd", "infrastructure", "kubernetes", "docker",
            "monitoring", "incident", "sre", "terraform", "helm",
        ],
    }

    # Score each domain
    scores: dict[str, int] = {}
    for domain, keywords in domain_signals.items():
        score = sum(1 for kw in keywords if kw in description_lower)
        if score > 0:
            scores[domain] = score

    if not scores:
        # Default to complete-lean for ambiguous requests
        return {
            "preset": "complete-lean",
            "domain": "complete",
            "size": "lean",
            "reason": "No strong domain signal detected — recommending cross-functional lean team",
            "alternatives": [
                {"preset": "qa-standard", "reason": "If this is a testing task"},
                {"preset": "software-engineering-standard", "reason": "If this is a development task"},
            ],
        }

    # Pick top domain
    best_domain = max(scores, key=lambda d: scores[d])

    # Size heuristic
    size_signals = {
        "large": ["enterprise", "comprehensive", "full", "thorough", "extensive", "large"],
        "lean": ["quick", "small", "simple", "mvp", "prototype", "lean", "minimal"],
    }

    size = "standard"
    for s, keywords in size_signals.items():
        if any(kw in description_lower for kw in keywords):
            size = s
            break

    preset = f"{best_domain}-{size}"

    # Build alternatives
    alternatives = []
    for domain, score in sorted(scores.items(), key=lambda x: -x[1]):
        if domain != best_domain:
            alternatives.append({
                "preset": f"{domain}-{size}",
                "reason": f"Also matches: {domain} (score: {score})",
            })

    if size != "standard":
        alternatives.insert(0, {
            "preset": f"{best_domain}-standard",
            "reason": f"Standard-size {best_domain} team as middle ground",
        })

    return {
        "preset": preset,
        "domain": best_domain,
        "size": size,
        "reason": f"Best match for description: {best_domain} domain (score: {scores[best_domain]})",
        "alternatives": alternatives[:3],
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_known_agents() -> list[dict]:
    """Load all agent definitions from preset files."""
    agents = []
    if not _PRESETS_DIR.is_dir():
        return agents

    for path in sorted(_PRESETS_DIR.glob("*.json")):
        try:
            with open(path) as f:
                data = json.load(f)
            for agent in data.get("agents", []):
                agent["_preset"] = path.stem
                agent["_domain"] = data.get("domain", "general")
                agents.append(agent)
        except Exception:
            continue
    return agents


def _normalize(text: str) -> str:
    """Normalize a role name for fuzzy matching."""
    return text.lower().replace("-", " ").replace("_", " ").strip()


def _find_best_match(role: str, known_agents: list[dict]) -> dict | None:
    """Find the best matching known agent for a role description."""
    role_norm = _normalize(role)
    role_words = set(role_norm.split())

    best_match = None
    best_score = 0

    for agent in known_agents:
        # Check exact key match
        if _normalize(agent.get("agent_key", "")) == role_norm:
            return agent

        # Check name match
        name_norm = _normalize(agent.get("name", ""))
        if name_norm == role_norm:
            return agent

        # Check role field match
        agent_role_norm = _normalize(agent.get("role", ""))
        if agent_role_norm == role_norm:
            return agent

        # Word overlap scoring
        candidate_words = set(name_norm.split()) | set(agent_role_norm.split())
        overlap = len(role_words & candidate_words)
        if overlap > best_score:
            best_score = overlap
            best_match = agent

    # Only return if we have meaningful overlap (at least 1 significant word)
    if best_score >= 1 and best_match:
        return best_match

    return None


def _adapt_known_agent(
    agent: dict, requested_role: str, context: str, tools: list[str], is_lead: bool,
) -> dict:
    """Adapt a known agent definition with custom context."""
    defn = {
        "agent_key": agent.get("agent_key", _make_key(requested_role)),
        "name": agent.get("name", requested_role),
        "role": agent.get("role", requested_role),
        "goal": agent.get("goal", ""),
        "backstory": agent.get("backstory", ""),
        "focus": agent.get("focus", ""),
        "domain": agent.get("domain", agent.get("_domain", "general")),
        "tools": tools or agent.get("tools", []),
        "complexity": agent.get("complexity", "medium"),
        "celery_queue": agent.get("celery_queue", _make_key(requested_role).replace("-", "_")),
        "redis_prefix": agent.get("redis_prefix", _make_key(requested_role).split("-")[0]),
    }

    if context:
        defn["goal"] = f"{defn['goal']}. Additional focus: {context}"
        defn["backstory"] = f"{defn['backstory']} For this project: {context}"

    if is_lead:
        defn["allow_delegation"] = True

    return defn


def _generate_agent_definition(
    role: str, context: str, tools: list[str], is_lead: bool, project_context: str,
) -> dict:
    """Generate an inline agent definition for a novel role."""
    key = _make_key(role)
    goal = f"Fulfill the role of {role}"
    if context:
        goal += f" with focus on: {context}"

    backstory = (
        f"You are an experienced {role} with deep expertise in your domain. "
        f"You bring professionalism, attention to detail, and strong collaboration skills."
    )
    if project_context:
        backstory += f" Project context: {project_context}"

    defn = {
        "agent_key": key,
        "name": role,
        "role": role,
        "goal": goal,
        "backstory": backstory,
        "focus": context or f"Core {role} responsibilities",
        "domain": "custom",
        "tools": tools,
        "complexity": "high" if is_lead else "medium",
        "celery_queue": key.replace("-", "_"),
        "redis_prefix": key.split("-")[0],
    }

    if is_lead:
        defn["allow_delegation"] = True

    return defn


def _make_key(role: str) -> str:
    """Convert a role name to a safe agent key."""
    import re
    key = role.lower().strip()
    key = re.sub(r"[^a-z0-9]+", "-", key)
    key = key.strip("-")
    return key or "agent"
