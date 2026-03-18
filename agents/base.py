"""
BaseAgent — generic foundation for all Agnostic agents.

Every agent (QA, data-engineering, devops, custom) shares:
- Redis + Celery initialisation
- LLM instantiation
- CrewAI Agent construction from an AgentDefinition
- Session/task lifecycle helpers (Redis state, manager notification)

Existing QA agents continue to work unchanged; they can optionally
subclass BaseAgent to reuse the plumbing and override only domain logic.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from crewai import LLM, Agent, Crew, Process, Task
from pydantic import BaseModel, Field, model_validator

from agents.constants import DEFINITIONS_DIR, validate_agent_key
from config.environment import config

if TYPE_CHECKING:
    from shared.crewai_compat import BaseTool

logger = logging.getLogger(__name__)


class AgentDefinition(BaseModel):
    """Runtime-loadable agent definition (from YAML, JSON, or API).

    Pydantic model that replaces the previous plain class. Provides
    automatic validation, serialization, and schema generation.
    """

    model_config = {"arbitrary_types_allowed": True, "extra": "ignore"}

    agent_key: str
    name: str
    role: str
    goal: str
    backstory: str
    focus: str = ""
    domain: str = "general"
    tools: list[str] = Field(default_factory=list)
    tool_instances: list[Any] = Field(default_factory=list, exclude=True)
    complexity: str = "medium"
    celery_queue: str | None = None
    redis_prefix: str | None = None
    allow_delegation: bool = False
    llm_model: str | None = None
    llm_temperature: float = 0.1
    verbose: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)
    gpu_required: bool = False
    gpu_strict: bool = False
    gpu_preferred: bool = False
    gpu_memory_min_mb: int = 0

    @model_validator(mode="after")
    def _set_defaults(self) -> AgentDefinition:
        if self.celery_queue is None:
            self.celery_queue = self.agent_key.replace("-", "_")
        if self.redis_prefix is None:
            self.redis_prefix = self.agent_key.split("-")[0]
        if self.llm_model is None:
            self.llm_model = os.getenv("OPENAI_MODEL", "gpt-4o")
        return self

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "agent_key": self.agent_key,
            "name": self.name,
            "role": self.role,
            "goal": self.goal,
            "backstory": self.backstory,
            "focus": self.focus,
            "domain": self.domain,
            "tools": self.tools,
            "complexity": self.complexity,
            "celery_queue": self.celery_queue,
            "redis_prefix": self.redis_prefix,
            "allow_delegation": self.allow_delegation,
            "llm_model": self.llm_model,
            "llm_temperature": self.llm_temperature,
            "verbose": self.verbose,
            "metadata": self.metadata,
        }
        # Only include GPU fields when non-default to keep payloads lean
        if self.gpu_required:
            d["gpu_required"] = True
        if self.gpu_strict:
            d["gpu_strict"] = True
        if self.gpu_preferred:
            d["gpu_preferred"] = True
        if self.gpu_memory_min_mb:
            d["gpu_memory_min_mb"] = self.gpu_memory_min_mb
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentDefinition:
        return cls(**{k: v for k, v in data.items() if k != "tool_instances"})

    def __repr__(self) -> str:
        return f"AgentDefinition(key={self.agent_key!r}, name={self.name!r}, domain={self.domain!r})"


class BaseAgent:
    """Generic base class for all Agnostic agents.

    Handles the shared initialisation that every agent needs:
    Redis, Celery, LLM, and CrewAI Agent construction.

    Subclasses only need to:
    1. Provide an AgentDefinition (or pass one to __init__)
    2. Implement domain-specific task methods
    """

    def __init__(
        self,
        definition: AgentDefinition,
        *,
        redis_client: Any | None = None,
        celery_app: Any | None = None,
        llm_service: Any | None = None,
    ):
        self.definition = definition
        self.logger = logging.getLogger(
            f"agents.{definition.domain}.{definition.agent_key}"
        )

        # --- infrastructure: accept shared instances or create new ones ---
        self.redis_client = redis_client or config.get_redis_client()
        self.celery_app = celery_app or config.get_celery_app(definition.celery_queue)
        if llm_service is not None:
            self.llm_service = llm_service
        else:
            from config.llm_integration import llm_service as _llm_svc

            self.llm_service = _llm_svc
        self.llm = LLM(
            model=definition.llm_model or "gpt-4o",
            temperature=definition.llm_temperature,
        )

        # --- resolve tools ---
        tools = self._resolve_tools(definition)

        # --- infer GPU requirements from tools ---
        self._infer_gpu_from_tools(definition)

        # --- build CrewAI Agent ---
        self.agent = Agent(
            role=definition.role,
            goal=definition.goal,
            backstory=definition.backstory,
            tools=tools,
            llm=self.llm,
            verbose=definition.verbose,
            allow_delegation=definition.allow_delegation,
        )

        self.logger.info(
            "Initialised %s agent '%s' (domain=%s, tools=%d)",
            definition.agent_key,
            definition.name,
            definition.domain,
            len(tools),
        )

    # ------------------------------------------------------------------
    # GPU inference from tools
    # ------------------------------------------------------------------

    @staticmethod
    def _infer_gpu_from_tools(definition: AgentDefinition) -> None:
        """Auto-promote agent GPU requirements if any of its tools need GPU.

        If a tool is registered with ``@register_gpu_tool``, the agent
        inherits ``gpu_required=True`` and the max ``gpu_memory_min_mb``
        across all its GPU tools — unless the definition already sets
        explicit GPU fields.
        """
        if definition.gpu_required or definition.gpu_preferred:
            return  # explicit config takes precedence

        if not definition.tools:
            return

        from agents.tool_registry import tool_gpu_memory_min, tool_requires_gpu

        max_mem = 0
        needs_gpu = False
        for tool_name in definition.tools:
            if tool_requires_gpu(tool_name):
                needs_gpu = True
                max_mem = max(max_mem, tool_gpu_memory_min(tool_name))

        if needs_gpu:
            definition.gpu_required = True
            definition.gpu_memory_min_mb = max(definition.gpu_memory_min_mb, max_mem)

    # ------------------------------------------------------------------
    # Tool resolution
    # ------------------------------------------------------------------

    def _resolve_tools(self, definition: AgentDefinition) -> list[BaseTool]:
        """Return tool instances.

        Priority:
        1. Explicit tool_instances on the definition (used by legacy QA agents)
        2. Lookup tool classes by name from the global tool registry
        """
        if definition.tool_instances:
            return list(definition.tool_instances)

        if not definition.tools:
            return []

        from agents.tool_registry import tool_registry

        resolved = []
        for tool_name in definition.tools:
            tool_cls = tool_registry.get(tool_name)
            if tool_cls is not None:
                resolved.append(tool_cls())  # type: ignore[call-arg]
            else:
                self.logger.warning("Tool '%s' not found in registry", tool_name)
        return resolved

    # ------------------------------------------------------------------
    # Crew execution helpers
    # ------------------------------------------------------------------

    async def run_task(
        self,
        description: str,
        expected_output: str = "Structured result",
        context: dict[str, Any] | None = None,
    ) -> Any:
        """Run a single-task crew and return the result."""
        task = Task(
            description=description,
            agent=self.agent,
            expected_output=expected_output,
        )
        crew = Crew(
            agents=[self.agent],
            tasks=[task],
            process=Process.sequential,
            verbose=self.definition.verbose,
        )
        # CrewAI is sync — run in executor to avoid blocking the event loop
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, crew.kickoff)
        return result

    async def run_crew(
        self,
        tasks: list[Task],
        agents: list[Agent] | None = None,
        process: Process = Process.sequential,
    ) -> Any:
        """Run a multi-task crew."""
        crew = Crew(
            agents=agents or [self.agent],  # type: ignore[arg-type]
            tasks=tasks,
            process=process,
            verbose=self.definition.verbose,
        )
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, crew.kickoff)

    # ------------------------------------------------------------------
    # Inter-crew delegation
    # ------------------------------------------------------------------

    async def delegate_to(
        self,
        target_agent_key: str,
        task_data: dict[str, Any],
        *,
        source: str = "key",
    ) -> dict[str, Any]:
        """Delegate a task to another agent (potentially from a different domain/crew).

        Args:
            target_agent_key: The agent_key of the target agent (must have a
                definition file in agents/definitions/).
            task_data: Task data dict passed to the target agent's handle_task().
            source: How to resolve the target — "key" loads from definitions dir.

        Returns:
            The result from the target agent's handle_task().
        """
        from agents.factory import AgentFactory

        validate_agent_key(target_agent_key, "target_agent_key")

        self.logger.info(
            "Delegating from %s to %s",
            self.definition.agent_key,
            target_agent_key,
        )

        target = AgentFactory.from_file(DEFINITIONS_DIR / f"{target_agent_key}.json")

        # Inject delegation context so the target knows who sent the task
        enriched = {
            **task_data,
            "_delegated_from": self.definition.agent_key,
            "_delegated_domain": self.definition.domain,
        }
        return await target.handle_task(enriched)

    # ------------------------------------------------------------------
    # Redis state helpers
    # ------------------------------------------------------------------

    def set_task_state(
        self,
        session_id: str,
        scenario_id: str,
        status: str,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Store task state in Redis under {prefix}:{session_id}:{scenario_id}."""
        payload = {
            "status": status,
            "updated_at": datetime.now(UTC).isoformat(),
            **(extra or {}),
        }
        key = f"{self.definition.redis_prefix}:{session_id}:{scenario_id}"
        self.redis_client.set(key, json.dumps(payload))

    async def notify_manager(
        self, session_id: str, scenario_id: str, result: dict[str, Any]
    ) -> None:
        """Publish completion notification to manager channel."""
        notification = {
            "agent": self.definition.agent_key,
            "session_id": session_id,
            "scenario_id": scenario_id,
            "status": "completed",
            "result": result,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        # Redis client is sync — run in executor to avoid blocking the loop
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            self.redis_client.publish,
            f"manager:{session_id}:notifications",
            json.dumps(notification),
        )

    # ------------------------------------------------------------------
    # Generic task handler (override in subclasses for domain logic)
    # ------------------------------------------------------------------

    async def handle_task(self, task_data: dict[str, Any]) -> dict[str, Any]:
        """Default task handler — runs the scenario through the crew.

        Subclasses should override this for domain-specific orchestration.
        """
        scenario = task_data.get("scenario", {})
        session_id = task_data.get("session_id", "unknown")
        scenario_id = scenario.get("id", "task")

        self.set_task_state(
            session_id, scenario_id, "in_progress", {"scenario": scenario}
        )

        try:
            result = await self.run_task(
                description=self._build_task_description(task_data),
                expected_output=scenario.get("expected_output", "Structured result"),
            )

            output = {
                "agent": self.definition.agent_key,
                "session_id": session_id,
                "scenario_id": scenario_id,
                "status": "completed",
                "result": str(result),
                "completed_at": datetime.now(UTC).isoformat(),
            }

            self.set_task_state(session_id, scenario_id, "completed", output)
            await self.notify_manager(session_id, scenario_id, output)
            return output

        except Exception as exc:
            self.logger.error("Task failed: %s", exc, exc_info=True)
            error_output = {
                "agent": self.definition.agent_key,
                "session_id": session_id,
                "scenario_id": scenario_id,
                "status": "failed",
                "error": str(exc),
                "failed_at": datetime.now(UTC).isoformat(),
            }
            self.set_task_state(session_id, scenario_id, "failed", error_output)
            return error_output

    def _build_task_description(self, task_data: dict[str, Any]) -> str:
        """Build a crew task description from task_data.  Override for custom prompts."""
        scenario = task_data.get("scenario", {})
        parts = [
            f"Agent: {self.definition.name}",
            f"Role: {self.definition.role}",
            f"Focus: {self.definition.focus}",
            "",
            f"Task: {scenario.get('name', 'Execute assigned task')}",
            f"Description: {scenario.get('description', task_data.get('description', ''))}",
        ]
        if scenario.get("target_url"):
            parts.append(f"Target URL: {scenario['target_url']}")
        if scenario.get("constraints"):
            parts.append(f"Constraints: {scenario['constraints']}")
        return "\n".join(parts)
