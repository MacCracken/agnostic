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


def _agent(
    key: str,
    name: str,
    role: str,
    goal: str,
    backstory: str,
    model: str,
    complexity: str = "medium",
) -> dict[str, Any]:
    """Build an agent definition dict with all required fields."""
    return {
        "agent_key": key,
        "name": name,
        "role": role,
        "goal": goal,
        "backstory": backstory,
        "complexity": complexity,
        "llm_model": model,
        "tools": [],
    }


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
                    _agent(
                        "bench-analyst",
                        "Benchmark Analyst",
                        "analyst",
                        "Analyse the given data and produce a summary",
                        "You are a data analyst who summarises financial data concisely.",
                        model,
                        "low",
                    ),
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
                    _agent(
                        "bench-researcher",
                        "Researcher",
                        "researcher",
                        "Gather relevant facts",
                        "You are a thorough researcher who finds key facts quickly.",
                        model,
                    ),
                    _agent(
                        "bench-writer",
                        "Writer",
                        "writer",
                        "Draft a clear report from research",
                        "You are a technical writer who produces clear executive summaries.",
                        model,
                    ),
                    _agent(
                        "bench-reviewer",
                        "Reviewer",
                        "reviewer",
                        "Review the report for accuracy and clarity",
                        "You are an editor who reviews reports for factual accuracy.",
                        model,
                        "low",
                    ),
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
                    _agent(
                        "bench-security",
                        "Security Analyst",
                        "security analyst",
                        "Identify security concerns",
                        "You are an application security specialist focused on OWASP top 10.",
                        model,
                    ),
                    _agent(
                        "bench-perf",
                        "Performance Analyst",
                        "performance analyst",
                        "Identify performance bottlenecks",
                        "You are a performance engineer who profiles web applications.",
                        model,
                    ),
                    _agent(
                        "bench-ux",
                        "UX Analyst",
                        "UX analyst",
                        "Evaluate user experience",
                        "You are a UX researcher who evaluates accessibility and usability.",
                        model,
                    ),
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
                    _agent(
                        "bench-planner",
                        "Planner",
                        "planner",
                        "Create a project plan",
                        "You are a project manager who breaks work into milestones.",
                        model,
                    ),
                    _agent(
                        "bench-frontend",
                        "Frontend Dev",
                        "frontend developer",
                        "Implement frontend tasks",
                        "You are a React developer who designs component hierarchies.",
                        model,
                    ),
                    _agent(
                        "bench-backend",
                        "Backend Dev",
                        "backend developer",
                        "Implement backend tasks",
                        "You are a FastAPI developer who designs REST endpoint structures.",
                        model,
                    ),
                    _agent(
                        "bench-integrator",
                        "Integrator",
                        "integration engineer",
                        "Integrate frontend and backend",
                        "You are an integration engineer who defines API contracts.",
                        model,
                        "low",
                    ),
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
                    _agent(
                        f"bench-qa-{i}",
                        f"QA Agent {i}",
                        role,
                        goal,
                        backstory,
                        model,
                        "low",
                    )
                    for i, (role, goal, backstory) in enumerate(
                        [
                            (
                                "test planner",
                                "Plan test strategy",
                                "You are a QA lead who designs test strategies.",
                            ),
                            (
                                "functional tester",
                                "Write functional tests",
                                "You are a QA engineer who writes functional test cases.",
                            ),
                            (
                                "regression tester",
                                "Run regression checks",
                                "You are a QA engineer focused on regression testing.",
                            ),
                            (
                                "security tester",
                                "Check for vulnerabilities",
                                "You are a security tester who checks for OWASP vulnerabilities.",
                            ),
                            (
                                "performance tester",
                                "Run load tests",
                                "You are a performance engineer who designs load tests.",
                            ),
                            (
                                "qa reporter",
                                "Aggregate and report results",
                                "You are a QA analyst who aggregates test results into reports.",
                            ),
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
