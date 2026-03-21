"""Benchmark scenario definitions.

Each scenario is a crew configuration that can be submitted to both the
CrewAI (Python) and AgnosAI (Rust) backends.  We keep them identical so
the comparison is fair — same agents, same tasks, same LLM model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class BenchScenario:
    """A single benchmark scenario."""

    name: str
    description: str
    crew_config: dict[str, Any]
    tags: list[str] = field(default_factory=list)


def _make_ollama_model(model: str) -> str:
    """Return litellm-compatible model string for Ollama."""
    return f"ollama/{model}"


def build_scenarios(ollama_model: str) -> list[BenchScenario]:
    """Return all benchmark scenarios configured for the given Ollama model."""
    model = _make_ollama_model(ollama_model)

    return [
        # ── 1. Single-agent, single-task (baseline) ──────────────────────
        BenchScenario(
            name="single-agent-single-task",
            description="Minimal crew: 1 agent, 1 simple task",
            tags=["baseline", "latency"],
            crew_config={
                "name": "bench-single",
                "agents": [
                    {
                        "agent_key": "bench-analyst",
                        "name": "Benchmark Analyst",
                        "role": "analyst",
                        "goal": "Analyse the given data and produce a summary",
                        "complexity": "low",
                        "llm_model": model,
                        "tools": [],
                    },
                ],
                "tasks": [
                    {
                        "description": (
                            "Summarise the following quarterly revenue figures: "
                            "Q1=$1.2M, Q2=$1.5M, Q3=$1.1M, Q4=$1.8M. "
                            "Return a one-paragraph summary with the total."
                        ),
                        "expected_output": "A one-paragraph revenue summary",
                    },
                ],
                "process": "sequential",
            },
        ),
        # ── 2. Multi-agent sequential ────────────────────────────────────
        BenchScenario(
            name="multi-agent-sequential",
            description="3 agents executing sequentially",
            tags=["multi-agent", "sequential"],
            crew_config={
                "name": "bench-seq-3",
                "agents": [
                    {
                        "agent_key": "bench-researcher",
                        "name": "Researcher",
                        "role": "researcher",
                        "goal": "Gather relevant facts",
                        "complexity": "medium",
                        "llm_model": model,
                        "tools": [],
                    },
                    {
                        "agent_key": "bench-writer",
                        "name": "Writer",
                        "role": "writer",
                        "goal": "Draft a clear report from research",
                        "complexity": "medium",
                        "llm_model": model,
                        "tools": [],
                    },
                    {
                        "agent_key": "bench-reviewer",
                        "name": "Reviewer",
                        "role": "reviewer",
                        "goal": "Review the report for accuracy and clarity",
                        "complexity": "low",
                        "llm_model": model,
                        "tools": [],
                    },
                ],
                "tasks": [
                    {
                        "description": "Research the benefits and risks of microservice architecture for a startup.",
                        "expected_output": "A list of 5 benefits and 5 risks",
                    },
                    {
                        "description": "Write a 200-word executive summary from the research findings.",
                        "expected_output": "Executive summary paragraph",
                    },
                    {
                        "description": "Review the summary for factual accuracy and suggest improvements.",
                        "expected_output": "Review notes with corrections",
                    },
                ],
                "process": "sequential",
            },
        ),
        # ── 3. Multi-agent parallel ──────────────────────────────────────
        BenchScenario(
            name="multi-agent-parallel",
            description="3 independent agents executing in parallel",
            tags=["multi-agent", "parallel", "throughput"],
            crew_config={
                "name": "bench-par-3",
                "agents": [
                    {
                        "agent_key": "bench-security",
                        "name": "Security Analyst",
                        "role": "security analyst",
                        "goal": "Identify security concerns",
                        "complexity": "medium",
                        "llm_model": model,
                        "tools": [],
                    },
                    {
                        "agent_key": "bench-perf",
                        "name": "Performance Analyst",
                        "role": "performance analyst",
                        "goal": "Identify performance bottlenecks",
                        "complexity": "medium",
                        "llm_model": model,
                        "tools": [],
                    },
                    {
                        "agent_key": "bench-ux",
                        "name": "UX Analyst",
                        "role": "UX analyst",
                        "goal": "Evaluate user experience",
                        "complexity": "medium",
                        "llm_model": model,
                        "tools": [],
                    },
                ],
                "tasks": [
                    {
                        "description": "Review a login form for SQL injection, XSS, and CSRF vulnerabilities.",
                        "expected_output": "Security findings list",
                    },
                    {
                        "description": "Evaluate the login form's response time and rendering performance.",
                        "expected_output": "Performance findings list",
                    },
                    {
                        "description": "Assess the login form's accessibility and usability.",
                        "expected_output": "UX findings list",
                    },
                ],
                "process": "parallel",
            },
        ),
        # ── 4. DAG with dependencies ─────────────────────────────────────
        BenchScenario(
            name="dag-dependencies",
            description="4 tasks in a diamond DAG (A -> B,C -> D)",
            tags=["dag", "orchestration"],
            crew_config={
                "name": "bench-dag-diamond",
                "agents": [
                    {
                        "agent_key": "bench-planner",
                        "name": "Planner",
                        "role": "planner",
                        "goal": "Create a project plan",
                        "complexity": "medium",
                        "llm_model": model,
                        "tools": [],
                    },
                    {
                        "agent_key": "bench-frontend",
                        "name": "Frontend Dev",
                        "role": "frontend developer",
                        "goal": "Implement frontend tasks",
                        "complexity": "medium",
                        "llm_model": model,
                        "tools": [],
                    },
                    {
                        "agent_key": "bench-backend",
                        "name": "Backend Dev",
                        "role": "backend developer",
                        "goal": "Implement backend tasks",
                        "complexity": "medium",
                        "llm_model": model,
                        "tools": [],
                    },
                    {
                        "agent_key": "bench-integrator",
                        "name": "Integrator",
                        "role": "integration engineer",
                        "goal": "Integrate frontend and backend",
                        "complexity": "low",
                        "llm_model": model,
                        "tools": [],
                    },
                ],
                "tasks": [
                    {
                        "description": "Create a plan for building a REST API with a React frontend.",
                        "expected_output": "Project plan with milestones",
                    },
                    {
                        "description": "Design React component hierarchy for the dashboard page.",
                        "expected_output": "Component tree description",
                        "dependencies": [0],
                    },
                    {
                        "description": "Design FastAPI endpoint structure for the dashboard data.",
                        "expected_output": "Endpoint list with schemas",
                        "dependencies": [0],
                    },
                    {
                        "description": "Define the integration contract between frontend and backend.",
                        "expected_output": "API contract document",
                        "dependencies": [1, 2],
                    },
                ],
                "process": "dag",
            },
        ),
        # ── 5. Large crew (stress test) ──────────────────────────────────
        BenchScenario(
            name="large-crew-6-agents",
            description="6-agent crew simulating a full QA team",
            tags=["stress", "large-crew"],
            crew_config={
                "name": "bench-large-qa",
                "agents": [
                    {
                        "agent_key": f"bench-qa-{i}",
                        "name": f"QA Agent {i}",
                        "role": role,
                        "goal": goal,
                        "complexity": "low",
                        "llm_model": model,
                        "tools": [],
                    }
                    for i, (role, goal) in enumerate(
                        [
                            ("test planner", "Plan test strategy"),
                            ("functional tester", "Write functional tests"),
                            ("regression tester", "Run regression checks"),
                            ("security tester", "Check for vulnerabilities"),
                            ("performance tester", "Run load tests"),
                            ("qa reporter", "Aggregate and report results"),
                        ]
                    )
                ],
                "tasks": [
                    {
                        "description": f"Execute {phase} for a user registration API endpoint.",
                        "expected_output": f"{phase} results",
                    }
                    for phase in [
                        "test planning",
                        "functional testing",
                        "regression testing",
                        "security testing",
                        "performance testing",
                        "results aggregation",
                    ]
                ],
                "process": "sequential",
            },
        ),
    ]
