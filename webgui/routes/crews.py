"""Crew builder and execution endpoints.

Assemble agent crews from definitions or presets and execute them as tasks.
This is the generic workflow engine that replaces hardcoded QA-only orchestration.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from agents.constants import DEFINITIONS_DIR, SAFE_KEY_RE
from shared.audit import AuditAction, audit_log
from webgui.routes.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()

# Track background crew tasks to prevent garbage collection
_background_tasks: set[asyncio.Task] = set()  # type: ignore[type-arg]


# ---------------------------------------------------------------------------
# Request/response models
# ---------------------------------------------------------------------------


class TeamMember(BaseModel):
    """A member in a custom team specification."""

    role: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Role title (e.g. 'Game Designer', 'UX Researcher')",
    )
    context: str = Field(
        default="", max_length=1000, description="What this member should focus on"
    )
    tools: list[str] = Field(
        default_factory=list, description="Specific tools for this agent"
    )
    lead: bool = Field(default=False, description="Whether this member leads the team")


class TeamSpec(BaseModel):
    """Structured team specification for custom crew assembly."""

    members: list[TeamMember] = Field(
        ...,
        min_length=1,
        max_length=20,
        description="Team members with roles and context",
    )
    project_context: str = Field(
        default="", max_length=2000, description="Overall project description"
    )

    @classmethod
    def from_payload(cls, data: dict[str, Any] | None) -> TeamSpec | None:
        """Build a TeamSpec from a raw dict payload, or return None."""
        if data and isinstance(data, dict):
            return cls(**data)
        return None


class CrewRunRequest(BaseModel):
    """Request to assemble and run a crew."""

    # Source: preset name, agent keys, inline definitions, OR team spec
    preset: str | None = Field(
        None,
        description="Preset name (e.g. 'quality-standard', 'design-lean')",
        pattern=r"^[a-z0-9][a-z0-9\-]*$",
    )
    agent_keys: list[str] = Field(
        default_factory=list,
        description="Agent keys from definitions directory",
    )
    agent_definitions: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Inline agent definitions (for ad-hoc crews)",
        max_length=20,
    )
    team: TeamSpec | None = Field(
        None,
        description="Custom team spec — describe members by role and context, "
        "and the system assembles the right agents automatically",
    )

    # Task to execute
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1, max_length=5000)
    target_url: str | None = None
    priority: Literal["critical", "high", "medium", "low"] = "high"

    # Execution options
    process: Literal["sequential", "hierarchical"] = "sequential"
    callback_url: str | None = None
    callback_secret: str | None = None

    # GPU options
    gpu_memory_budget_mb: int | None = Field(
        None,
        ge=0,
        description="Max total GPU memory (MB) this crew may use. "
        "0 or None = unlimited. Scheduler rejects if budget exceeded.",
    )


class CrewRunResponse(BaseModel):
    crew_id: str
    task_id: str
    session_id: str
    status: str
    agent_count: int
    agents: list[str]
    created_at: str


class CrewStatusResponse(BaseModel):
    crew_id: str
    task_id: str
    session_id: str
    status: str
    agents: list[str]
    created_at: str
    updated_at: str
    result: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Crew execution
# ---------------------------------------------------------------------------


def _build_agents_sync(crew_config: dict[str, Any]) -> list[Any]:
    """Build agent instances from crew config (runs in executor).

    Agents in the same crew share a single Redis client and Celery app
    to avoid creating N connections for an N-agent crew.
    """
    from agents.factory import AgentFactory
    from config.environment import config as env_config

    # Shared infrastructure for all agents in this crew
    shared = {
        "redis_client": env_config.get_redis_client(),
        "celery_app": env_config.get_celery_app("crew_shared"),
    }

    source = crew_config.get("source")
    if source == "preset":
        return AgentFactory.from_preset(crew_config["preset"], **shared)
    if source == "keys":
        built = []
        for key in crew_config["agent_keys"]:
            if not SAFE_KEY_RE.match(key):
                raise ValueError(f"Invalid agent key: {key!r}")
            built.append(
                AgentFactory.from_file(DEFINITIONS_DIR / f"{key}.json", **shared)
            )
        return built
    if source == "inline":
        return [
            AgentFactory.from_dict(d, **shared)
            for d in crew_config["agent_definitions"]
        ]
    return []


async def _execute_agents(
    agents: list[Any],
    task_data: dict[str, Any],
    gpu_plan: Any,
    crew_id: str,
) -> dict[str, Any]:
    """Execute each agent sequentially with GPU env management and VRAM tracking."""
    from config.gpu_scheduler import apply_gpu_assignment

    results: dict[str, Any] = {}
    for agent in agents:
        assignment = gpu_plan.get_assignment(agent.definition.agent_key)
        gpu_env = apply_gpu_assignment(assignment) if assignment else {}
        saved_env: dict[str, str | None] = {}

        try:
            for k, v in gpu_env.items():
                saved_env[k] = os.environ.get(k)
                os.environ[k] = v

            if assignment and assignment.is_gpu:
                logger.info(
                    "Agent %s running on GPU %d (%s)",
                    agent.definition.agent_key,
                    assignment.device_index,
                    assignment.device_name,
                )

            # Snapshot VRAM before execution
            vram_before = None
            if assignment and assignment.is_gpu:
                from config.gpu import check_memory_usage

                vram_before = check_memory_usage(assignment.device_index)

            agent_result = await agent.handle_task(task_data)

            # Snapshot VRAM after execution
            if assignment and assignment.is_gpu and vram_before:
                vram_after = check_memory_usage(assignment.device_index)
                if vram_after:
                    agent_result["gpu_vram"] = {
                        "device_index": assignment.device_index,
                        "before_mb": vram_before["used_mb"],
                        "after_mb": vram_after["used_mb"],
                        "delta_mb": vram_after["used_mb"] - vram_before["used_mb"],
                    }

            results[agent.definition.agent_key] = agent_result
        except Exception as exc:
            logger.error(
                "Agent %s failed in crew %s: %s",
                agent.definition.agent_key,
                crew_id,
                exc,
            )
            results[agent.definition.agent_key] = {
                "status": "failed",
                "error": str(exc),
            }
        finally:
            for k, original in saved_env.items():
                if original is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = original

    return results


async def _finalize_crew(
    crew_id: str,
    crew_config: dict[str, Any],
    redis_client: Any,
    crew_redis_key: str,
) -> None:
    """Fire webhook callback if configured."""
    callback_url = crew_config.get("callback_url")
    if not callback_url:
        return
    try:
        from webgui.routes.tasks import _fire_webhook

        raw = await redis_client.get(crew_redis_key)
        if raw:
            record = json.loads(raw)
            if record.get("status"):
                await _fire_webhook(
                    callback_url, crew_config.get("callback_secret"), record
                )
    except Exception as exc:
        logger.warning("Crew %s webhook failed: %s", crew_id, exc)


async def _run_crew_async(
    crew_id: str,
    task_id: str,
    session_id: str,
    crew_config: dict[str, Any],
    redis_client: Any,
    tenant_id: str = "default",
) -> None:
    """Run a generic crew asynchronously.

    Phases:
    1. _build_agents_sync — instantiate agents from config (in executor)
    2. GPU scheduling — assign agents to devices
    3. _execute_agents — run each agent with GPU env isolation
    4. _finalize_crew — fire webhook callback
    """
    import time as _time

    from shared.database.tenants import tenant_manager
    from shared.metrics import ACTIVE_CREW_TASKS

    crew_start = _time.monotonic()
    source = crew_config.get("source", "unknown")
    ACTIVE_CREW_TASKS.inc()

    crew_redis_key = tenant_manager.task_key(tenant_id, f"crew:{crew_id}")
    task_redis_key = tenant_manager.task_key(tenant_id, task_id)

    async def _update_status(
        status: str, result: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        now = datetime.now(UTC).isoformat()

        raw_crew, raw_task = await asyncio.gather(
            redis_client.get(crew_redis_key),
            redis_client.get(task_redis_key),
        )

        crew_record: dict[str, Any] = json.loads(raw_crew) if raw_crew else {}
        crew_record["status"] = status
        crew_record["updated_at"] = now
        if result:
            crew_record["result"] = result

        task_record: dict[str, Any] = json.loads(raw_task) if raw_task else {}
        task_record["status"] = status
        task_record["updated_at"] = now
        task_record["result"] = result

        status_msg = json.dumps(
            {
                "type": "crew_status_changed",
                "crew_id": crew_id,
                "task_id": task_id,
                "status": status,
                "timestamp": now,
            }
        )

        await asyncio.gather(
            redis_client.setex(crew_redis_key, 86400, json.dumps(crew_record)),
            redis_client.setex(task_redis_key, 86400, json.dumps(task_record)),
            redis_client.publish(f"task:{task_id}", status_msg),
        )

        return crew_record

    try:
        await _update_status("running")

        # Phase 1: Build agents
        loop = asyncio.get_running_loop()
        agents = await loop.run_in_executor(None, _build_agents_sync, crew_config)

        if not agents:
            await _update_status("failed", {"error": "No agents could be created"})
            return

        # Phase 2: GPU scheduling
        from config.gpu_scheduler import gpu_slot_tracker, schedule_crew_gpus

        gpu_plan = schedule_crew_gpus(
            [a.definition for a in agents],
            memory_budget_mb=crew_config.get("gpu_memory_budget_mb"),
        )

        if gpu_plan.has_errors:
            await _update_status(
                "failed",
                {"error": "GPU scheduling failed", "gpu_errors": gpu_plan.errors},
            )
            return

        for ga in gpu_plan.gpu_agents:
            gpu_slot_tracker.reserve(crew_id, ga.device_index, ga.memory_reserved_mb)

        # Phase 3: Execute agents
        task_data = {
            "session_id": session_id,
            "scenario": {
                "id": crew_id,
                "name": crew_config.get("title", "Crew task"),
                "description": crew_config.get("description", ""),
                "target_url": crew_config.get("target_url"),
            },
        }

        results = await _execute_agents(agents, task_data, gpu_plan, crew_id)

        # Aggregate
        all_ok = all(r.get("status") == "completed" for r in results.values())
        final_status = "completed" if all_ok else "partial"

        gpu_slot_tracker.release(crew_id)

        # DLP scan — route crew output through SY's DLP pipeline if enabled
        try:
            from shared.yeoman_dlp import scan_crew_output

            result_payload = {
                "agent_results": results,
                "agents_succeeded": sum(
                    1 for r in results.values() if r.get("status") == "completed"
                ),
                "agents_failed": sum(
                    1 for r in results.values() if r.get("status") == "failed"
                ),
            }
            result_payload = await scan_crew_output(crew_id, result_payload)
            # Update results from (possibly sanitized) payload
            results = result_payload.get("agent_results", results)
        except ImportError:
            pass

        # Audit forwarding — log crew completion to SY's audit trail
        try:
            from shared.yeoman_audit import forward_crew_event

            await forward_crew_event(
                "crew_completed" if all_ok else "crew_partial",
                crew_id,
                detail={
                    "source": source,
                    "agent_count": len(agents),
                    "status": final_status,
                    "gpu_agents": len(gpu_plan.gpu_agents),
                },
            )
        except ImportError:
            pass

        # Record metrics
        from shared.metrics import (
            CREW_AGENT_COUNT,
            CREW_RUN_DURATION,
            CREW_RUNS_TOTAL,
            GPU_AGENTS_SCHEDULED,
        )

        CREW_RUNS_TOTAL.labels(source=source, status=final_status).inc()
        CREW_RUN_DURATION.labels(source=source).observe(_time.monotonic() - crew_start)
        CREW_AGENT_COUNT.labels(source=source).observe(len(agents))
        for _ga in gpu_plan.gpu_agents:
            GPU_AGENTS_SCHEDULED.inc()
        ACTIVE_CREW_TASKS.dec()

        await _update_status(
            final_status,
            {
                "agent_results": results,
                "agents_succeeded": sum(
                    1 for r in results.values() if r.get("status") == "completed"
                ),
                "agents_failed": sum(
                    1 for r in results.values() if r.get("status") == "failed"
                ),
                "gpu_placement": gpu_plan.to_dict(),
                "completed_at": datetime.now(UTC).isoformat(),
            },
        )

    except Exception as exc:
        logger.error("Crew %s failed: %s", crew_id, exc, exc_info=True)
        ACTIVE_CREW_TASKS.dec()
        from shared.metrics import CREW_RUNS_TOTAL as _CRT

        _CRT.labels(source=source, status="failed").inc()
        try:
            from config.gpu_scheduler import gpu_slot_tracker as _tracker

            _tracker.release(crew_id)
        except Exception:
            pass
        try:
            await _update_status("failed", {"error": str(exc)})
        except Exception:
            logger.exception("Crew %s: failed to update status", crew_id)

    # Phase 4: Webhook
    await _finalize_crew(crew_id, crew_config, redis_client, crew_redis_key)


def _crew_done_callback(task: asyncio.Task) -> None:  # type: ignore[type-arg]
    _background_tasks.discard(task)
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.error("Background crew task crashed: %s", exc, exc_info=exc)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/crews", response_model=CrewRunResponse, status_code=201)
async def run_crew(
    req: CrewRunRequest,
    user: dict[str, Any] = Depends(get_current_user),
) -> CrewRunResponse:
    """Assemble and run an agent crew.

    Provide one of:
    - ``preset``: name of a preset (e.g. "quality-standard", "design-lean")
    - ``agent_keys``: list of agent definition keys from the definitions directory
    - ``agent_definitions``: inline agent definitions for ad-hoc crews
    """
    # If team spec provided, assemble into inline definitions
    if req.team and not req.agent_definitions:
        from agents.crew_assembler import assemble_team

        members_raw = [m.model_dump() for m in req.team.members]
        req.agent_definitions = assemble_team(members_raw, req.team.project_context)

    # Validate exactly one source
    sources = [
        bool(req.preset),
        bool(req.agent_keys),
        bool(req.agent_definitions),
    ]
    if sum(sources) == 0:
        raise HTTPException(
            status_code=400,
            detail="Provide one of: preset, agent_keys, agent_definitions, or team",
        )
    if sum(sources) > 1:
        raise HTTPException(
            status_code=400,
            detail="Provide only one of: preset, agent_keys, agent_definitions, or team",
        )

    # Validate callback URL
    if req.callback_url:
        from webgui.routes.dependencies import _validate_callback_url

        try:
            _validate_callback_url(req.callback_url)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    # Determine source and agent list for the response
    if req.preset:
        source = "preset"
        # Read preset to get agent keys — use registry cache when available
        from config.agent_registry import agent_registry

        preset_data = agent_registry.get_preset(req.preset)
        if not preset_data:
            raise HTTPException(
                status_code=404, detail=f"Preset '{req.preset}' not found"
            )
        agent_names = [
            a.get("agent_key", "unknown") for a in preset_data.get("agents", [])
        ]
    elif req.agent_keys:
        source = "keys"
        agent_names = list(req.agent_keys)
    else:
        source = "inline"
        agent_names = [
            d.get("agent_key", f"inline-{i}")
            for i, d in enumerate(req.agent_definitions)
        ]

    from config.environment import config

    crew_id = str(uuid.uuid4())
    task_id = str(uuid.uuid4())
    session_id = f"crew_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{crew_id[:8]}"
    now = datetime.now(UTC).isoformat()

    redis_client = config.get_async_redis_client()

    from shared.database.tenants import tenant_manager

    tenant_id = user.get("tenant_id", tenant_manager.default_tenant_id)

    # Store crew record
    crew_record = {
        "crew_id": crew_id,
        "task_id": task_id,
        "session_id": session_id,
        "status": "pending",
        "agents": agent_names,
        "agent_count": len(agent_names),
        "created_at": now,
        "updated_at": now,
        "result": None,
    }
    crew_redis_key = tenant_manager.task_key(tenant_id, f"crew:{crew_id}")
    await redis_client.setex(crew_redis_key, 86400, json.dumps(crew_record))

    # Store task record (so /tasks/{task_id} also works)
    task_record = {
        "task_id": task_id,
        "session_id": session_id,
        "status": "pending",
        "created_at": now,
        "updated_at": now,
        "result": None,
    }
    task_redis_key = tenant_manager.task_key(tenant_id, task_id)
    await redis_client.setex(task_redis_key, 86400, json.dumps(task_record))

    # Build crew config for the async runner
    crew_config = {
        "source": source,
        "preset": req.preset,
        "agent_keys": req.agent_keys,
        "agent_definitions": req.agent_definitions,
        "title": req.title,
        "description": req.description,
        "target_url": req.target_url,
        "priority": req.priority,
        "process": req.process,
        "callback_url": req.callback_url,
        "callback_secret": req.callback_secret,
        "gpu_memory_budget_mb": req.gpu_memory_budget_mb,
    }

    # Fire-and-forget
    bg_task = asyncio.create_task(
        _run_crew_async(
            crew_id=crew_id,
            task_id=task_id,
            session_id=session_id,
            crew_config=crew_config,
            redis_client=redis_client,
            tenant_id=tenant_id,
        )
    )
    _background_tasks.add(bg_task)
    bg_task.add_done_callback(_crew_done_callback)

    audit_log(
        AuditAction.TASK_SUBMITTED,
        actor=user.get("user_id"),
        resource_type="crew",
        resource_id=crew_id,
        detail={"source": source, "agents": agent_names},
    )

    # Forward crew creation to SY audit trail
    try:
        from shared.yeoman_audit import forward_crew_event

        asyncio.get_running_loop().create_task(
            forward_crew_event(
                "crew_created",
                crew_id,
                actor=user.get("user_id"),
                detail={"source": source, "agents": agent_names},
            )
        )
    except ImportError:
        pass

    return CrewRunResponse(
        crew_id=crew_id,
        task_id=task_id,
        session_id=session_id,
        status="pending",
        agent_count=len(agent_names),
        agents=agent_names,
        created_at=now,
    )


@router.get("/crews/{crew_id}", response_model=CrewStatusResponse)
async def get_crew_status(
    crew_id: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> CrewStatusResponse:
    """Get the status of a running or completed crew."""
    from config.environment import config
    from shared.database.tenants import tenant_manager

    redis_client = config.get_async_redis_client()
    tenant_id = user.get("tenant_id", tenant_manager.default_tenant_id)
    crew_redis_key = tenant_manager.task_key(tenant_id, f"crew:{crew_id}")

    data = await redis_client.get(crew_redis_key)
    if not data:
        raise HTTPException(status_code=404, detail="Crew not found")

    record = json.loads(data)
    return CrewStatusResponse(**record)


@router.get("/crews")
async def list_crews(
    status: str | None = Query(None, description="Filter by status"),
    limit: int = Query(20, ge=1, le=100, description="Max results per page"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """List crews with optional status filter and pagination."""
    from config.environment import config
    from shared.database.tenants import tenant_manager

    redis_client = config.get_async_redis_client()
    tenant_id = user.get("tenant_id", tenant_manager.default_tenant_id)

    # Build scan pattern scoped to tenant
    scan_pattern = tenant_manager.task_key(tenant_id, "crew:*")

    # Collect all crew keys via SCAN
    crew_keys: list[str] = []
    cursor: int = 0
    while True:
        cursor, keys = await redis_client.scan(
            cursor=cursor, match=scan_pattern, count=100
        )
        crew_keys.extend(keys)
        if cursor == 0:
            break

    # Fetch all crew records
    crews: list[dict[str, Any]] = []
    for key in crew_keys:
        raw = await redis_client.get(key)
        if not raw:
            continue
        record = json.loads(raw)
        if status and record.get("status") != status:
            continue
        crews.append(record)

    # Sort by created_at descending (newest first)
    crews.sort(key=lambda c: c.get("created_at", ""), reverse=True)

    total = len(crews)
    paginated = crews[offset : offset + limit]

    return {
        "crews": paginated,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/crews/{crew_id}/cancel")
async def cancel_crew(
    crew_id: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Cancel a running or pending crew."""
    from config.environment import config
    from shared.database.tenants import tenant_manager

    redis_client = config.get_async_redis_client()
    tenant_id = user.get("tenant_id", tenant_manager.default_tenant_id)
    crew_redis_key = tenant_manager.task_key(tenant_id, f"crew:{crew_id}")

    raw = await redis_client.get(crew_redis_key)
    if not raw:
        raise HTTPException(status_code=404, detail="Crew not found")

    record: dict[str, Any] = json.loads(raw)
    current_status = record.get("status")

    if current_status not in ("running", "pending"):
        raise HTTPException(
            status_code=409,
            detail=f"Crew cannot be cancelled — current status is '{current_status}'",
        )

    now = datetime.now(UTC).isoformat()
    record["status"] = "cancelled"
    record["updated_at"] = now
    await redis_client.setex(crew_redis_key, 86400, json.dumps(record))

    # Update the associated task record
    task_id = record.get("task_id")
    if task_id:
        task_redis_key = tenant_manager.task_key(tenant_id, task_id)
        task_raw = await redis_client.get(task_redis_key)
        if task_raw:
            task_record: dict[str, Any] = json.loads(task_raw)
            task_record["status"] = "cancelled"
            task_record["updated_at"] = now
            await redis_client.setex(task_redis_key, 86400, json.dumps(task_record))

    # Publish status update
    if task_id:
        await redis_client.publish(
            f"task:{task_id}",
            json.dumps(
                {
                    "type": "crew_status_changed",
                    "crew_id": crew_id,
                    "task_id": task_id,
                    "status": "cancelled",
                    "timestamp": now,
                }
            ),
        )

    audit_log(
        AuditAction.TASK_SUBMITTED,
        actor=user.get("user_id"),
        resource_type="crew",
        resource_id=crew_id,
        detail={"action": "cancel", "previous_status": current_status},
    )

    return record
