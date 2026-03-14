"""Crew builder and execution endpoints.

Assemble agent crews from definitions or presets and execute them as tasks.
This is the generic workflow engine that replaces hardcoded QA-only orchestration.
"""

import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from agents.constants import DEFINITIONS_DIR, PRESETS_DIR, SAFE_KEY_RE
from shared.audit import AuditAction, audit_log
from webgui.routes.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Request/response models
# ---------------------------------------------------------------------------


class CrewRunRequest(BaseModel):
    """Request to assemble and run a crew."""

    # Source: either a preset name OR a list of agent keys/definitions
    preset: str | None = Field(None, description="Preset name (e.g. 'qa-standard')", pattern=r"^[a-z0-9][a-z0-9\-]*$")
    agent_keys: list[str] = Field(
        default_factory=list,
        description="Agent keys from definitions directory",
    )
    agent_definitions: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Inline agent definitions (for ad-hoc crews)",
        max_length=20,
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
    result: dict | None = None


# ---------------------------------------------------------------------------
# Crew execution
# ---------------------------------------------------------------------------


async def _run_crew_async(
    crew_id: str,
    task_id: str,
    session_id: str,
    crew_config: dict[str, Any],
    redis_client: Any,
    tenant_id: str = "default",
) -> None:
    """Run a generic crew asynchronously."""
    from shared.database.tenants import tenant_manager

    crew_redis_key = tenant_manager.task_key(tenant_id, f"crew:{crew_id}")
    task_redis_key = tenant_manager.task_key(tenant_id, task_id)

    async def _update_status(status: str, result: dict | None = None) -> dict[str, Any]:
        now = datetime.now(UTC).isoformat()

        # Update crew record
        raw = await redis_client.get(crew_redis_key)
        crew_record = json.loads(raw) if raw else {}
        crew_record["status"] = status
        crew_record["updated_at"] = now
        if result:
            crew_record["result"] = result
        await redis_client.setex(crew_redis_key, 86400, json.dumps(crew_record))

        # Update task record
        task_raw = await redis_client.get(task_redis_key)
        task_record = json.loads(task_raw) if task_raw else {}
        task_record["status"] = status
        task_record["updated_at"] = now
        task_record["result"] = result
        await redis_client.setex(task_redis_key, 86400, json.dumps(task_record))

        # Publish status update
        await redis_client.publish(
            f"task:{task_id}",
            json.dumps({
                "type": "crew_status_changed",
                "crew_id": crew_id,
                "task_id": task_id,
                "status": status,
                "timestamp": now,
            }),
        )

        return crew_record

    try:
        await _update_status("running")

        # Build agents from config
        source = crew_config.get("source")
        agents = []

        def _build_agents() -> list:
            from agents.factory import AgentFactory

            built = []
            if source == "preset":
                built = AgentFactory.from_preset(crew_config["preset"])
            elif source == "keys":
                for key in crew_config["agent_keys"]:
                    if not SAFE_KEY_RE.match(key):
                        raise ValueError(f"Invalid agent key: {key!r}")
                    agent = AgentFactory.from_file(DEFINITIONS_DIR / f"{key}.json")
                    built.append(agent)
            elif source == "inline":
                for defn_dict in crew_config["agent_definitions"]:
                    agent = AgentFactory.from_dict(defn_dict)
                    built.append(agent)
            return built

        loop = asyncio.get_running_loop()
        agents = await loop.run_in_executor(None, _build_agents)

        if not agents:
            await _update_status("failed", {"error": "No agents could be created"})
            return

        # Execute each agent's handle_task sequentially (or could be parallel)
        task_data = {
            "session_id": session_id,
            "scenario": {
                "id": crew_id,
                "name": crew_config.get("title", "Crew task"),
                "description": crew_config.get("description", ""),
                "target_url": crew_config.get("target_url"),
            },
        }

        results = {}
        for agent in agents:
            try:
                agent_result = await agent.handle_task(task_data)
                results[agent.definition.agent_key] = agent_result
            except Exception as exc:
                logger.error(
                    "Agent %s failed in crew %s: %s",
                    agent.definition.agent_key, crew_id, exc,
                )
                results[agent.definition.agent_key] = {
                    "status": "failed",
                    "error": str(exc),
                }

        # Aggregate
        all_ok = all(r.get("status") == "completed" for r in results.values())
        final_status = "completed" if all_ok else "partial"

        await _update_status(final_status, {
            "agent_results": results,
            "agents_succeeded": sum(1 for r in results.values() if r.get("status") == "completed"),
            "agents_failed": sum(1 for r in results.values() if r.get("status") == "failed"),
            "completed_at": datetime.now(UTC).isoformat(),
        })

    except Exception as exc:
        logger.error("Crew %s failed: %s", crew_id, exc, exc_info=True)
        try:
            await _update_status("failed", {"error": str(exc)})
        except Exception:
            logger.exception("Crew %s: failed to update status", crew_id)

    # Webhook callback — only fire if we have a valid record
    callback_url = crew_config.get("callback_url")
    if callback_url:
        try:
            from webgui.routes.tasks import _fire_webhook

            raw = await redis_client.get(crew_redis_key)
            if raw:
                record = json.loads(raw)
                if record.get("status"):
                    await _fire_webhook(callback_url, crew_config.get("callback_secret"), record)
        except Exception as exc:
            logger.warning("Crew %s webhook failed: %s", crew_id, exc)


def _crew_done_callback(task: asyncio.Task) -> None:  # type: ignore[type-arg]
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
    user: dict = Depends(get_current_user),
):
    """Assemble and run an agent crew.

    Provide one of:
    - ``preset``: name of a preset (e.g. "qa-standard", "data-engineering")
    - ``agent_keys``: list of agent definition keys from the definitions directory
    - ``agent_definitions``: inline agent definitions for ad-hoc crews
    """
    # Validate exactly one source
    sources = [
        bool(req.preset),
        bool(req.agent_keys),
        bool(req.agent_definitions),
    ]
    if sum(sources) == 0:
        raise HTTPException(
            status_code=400,
            detail="Provide one of: preset, agent_keys, or agent_definitions",
        )
    if sum(sources) > 1:
        raise HTTPException(
            status_code=400,
            detail="Provide only one of: preset, agent_keys, or agent_definitions",
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
        # Read preset to get agent keys for the response
        preset_path = PRESETS_DIR / f"{req.preset}.json"
        if not preset_path.exists():
            raise HTTPException(status_code=404, detail=f"Preset '{req.preset}' not found")
        with open(preset_path) as f:
            preset_data = json.load(f)
        agent_names = [a.get("agent_key", "unknown") for a in preset_data.get("agents", [])]
    elif req.agent_keys:
        source = "keys"
        agent_names = list(req.agent_keys)
    else:
        source = "inline"
        agent_names = [d.get("agent_key", f"inline-{i}") for i, d in enumerate(req.agent_definitions)]

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
    bg_task.add_done_callback(_crew_done_callback)

    audit_log(
        AuditAction.TASK_SUBMITTED,
        actor=user.get("user_id"),
        resource_type="crew",
        resource_id=crew_id,
        detail={"source": source, "agents": agent_names},
    )

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
    user: dict = Depends(get_current_user),
):
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
