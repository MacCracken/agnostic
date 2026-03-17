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

import logging

from agents.constants import make_agent_key

logger = logging.getLogger(__name__)

# Minimum word-overlap score to consider a fuzzy match valid.
# 2+ prevents false positives from single common words like "engineer".
_MIN_FUZZY_SCORE = 2


# ---------------------------------------------------------------------------
# Public API
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

    known_agents = _get_known_agents()
    definitions = []
    used_keys: set[str] = set()

    for i, member in enumerate(members):
        role = member.get("role", "").strip()
        if not role:
            continue

        context = member.get("context", "")
        tools = member.get("tools", [])
        is_lead = member.get("lead", False) or i == 0

        match = _find_best_match(role, known_agents)

        if match:
            defn = _build_agent_dict(
                agent_key=match.get("agent_key", make_agent_key(role)),
                name=match.get("name", role),
                role_str=match.get("role", role),
                goal=match.get("goal", ""),
                backstory=match.get("backstory", ""),
                focus=match.get("focus", ""),
                domain=match.get("domain", "general"),
                tools=tools or match.get("tools", []),
                complexity=match.get("complexity", "medium"),
                celery_queue=match.get("celery_queue"),
                redis_prefix=match.get("redis_prefix"),
                context=context,
                is_lead=is_lead,
            )
        else:
            key = make_agent_key(role)
            goal = f"Fulfill the role of {role}"
            if context:
                goal += f" with focus on: {context}"
            backstory = (
                f"You are an experienced {role} with deep expertise in your domain. "
                f"You bring professionalism, attention to detail, and strong collaboration skills."
            )
            if project_context:
                backstory += f" Project context: {project_context}"

            defn = _build_agent_dict(
                agent_key=key,
                name=role,
                role_str=role,
                goal=goal,
                backstory=backstory,
                focus=context or f"Core {role} responsibilities",
                domain="custom",
                tools=tools,
                complexity="high" if is_lead else "medium",
                context="",  # already baked into goal/backstory
                is_lead=is_lead,
            )

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
        return {
            "preset": "complete-lean",
            "domain": "complete",
            "size": "lean",
            "reason": "No strong domain signal detected — recommending cross-functional lean team",
            "alternatives": [
                {"preset": "quality-standard", "reason": "If this is a testing task"},
                {"preset": "software-engineering-standard", "reason": "If this is a development task"},
            ],
        }

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


def _get_known_agents() -> list[dict]:
    """Get all agent definitions from the agent registry singleton."""
    try:
        from config.agent_registry import agent_registry

        agents = []
        for name, preset_data in agent_registry._presets.items():
            for agent in preset_data.get("agents", []):
                # Shallow copy to avoid mutating cached data
                entry = dict(agent)
                entry["_domain"] = preset_data.get("domain", "general")
                agents.append(entry)
        return agents
    except Exception:
        logger.warning("Could not load agents from registry, returning empty list")
        return []


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

    # Require 2+ word overlap to prevent false positives from
    # single common words like "engineer" or "lead"
    if best_score >= _MIN_FUZZY_SCORE and best_match:
        return best_match

    return None


def _build_agent_dict(
    *,
    agent_key: str,
    name: str,
    role_str: str,
    goal: str,
    backstory: str,
    focus: str,
    domain: str,
    tools: list[str],
    complexity: str = "medium",
    celery_queue: str | None = None,
    redis_prefix: str | None = None,
    context: str = "",
    is_lead: bool = False,
) -> dict:
    """Build a canonical agent definition dict."""
    defn = {
        "agent_key": agent_key,
        "name": name,
        "role": role_str,
        "goal": goal,
        "backstory": backstory,
        "focus": focus,
        "domain": domain,
        "tools": tools,
        "complexity": complexity,
        "celery_queue": celery_queue or agent_key.replace("-", "_"),
        "redis_prefix": redis_prefix or agent_key.split("-")[0],
    }

    if context:
        defn["goal"] = f"{defn['goal']}. Additional focus: {context}"
        defn["backstory"] = f"{defn['backstory']} For this project: {context}"

    if is_lead:
        defn["allow_delegation"] = True

    return defn
