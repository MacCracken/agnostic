"""Agent definition and preset management API endpoints.

CRUD for agent definitions (JSON files) and preset management.
Definitions are stored as JSON files in agents/definitions/ and
presets in agents/definitions/presets/.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from webgui.routes.dependencies import PaginatedResponse, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()

# Resolve paths relative to project root
_PROJECT_ROOT = Path(__file__).parent.parent.parent
_DEFINITIONS_DIR = _PROJECT_ROOT / "agents" / "definitions"
_PRESETS_DIR = _DEFINITIONS_DIR / "presets"

# Required fields for a valid agent definition
_REQUIRED_FIELDS = {"agent_key", "name", "role", "goal", "backstory"}


# ---------------------------------------------------------------------------
# Request/response models
# ---------------------------------------------------------------------------


class AgentDefinitionRequest(BaseModel):
    """Request body for creating/updating an agent definition."""

    agent_key: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-z0-9][a-z0-9\-]*$")
    name: str = Field(..., min_length=1, max_length=200)
    role: str = Field(..., min_length=1, max_length=500)
    goal: str = Field(..., min_length=1, max_length=2000)
    backstory: str = Field(..., min_length=1, max_length=5000)
    focus: str = Field(default="", max_length=500)
    domain: str = Field(default="general", max_length=100)
    tools: list[str] = Field(default_factory=list)
    complexity: str = Field(default="medium", pattern=r"^(low|medium|high)$")
    celery_queue: str | None = None
    redis_prefix: str | None = None
    allow_delegation: bool = False
    llm_model: str | None = None
    llm_temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    verbose: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentDefinitionResponse(BaseModel):
    agent_key: str
    name: str
    role: str
    goal: str
    backstory: str
    focus: str = ""
    domain: str = "general"
    tools: list[str] = []
    complexity: str = "medium"
    celery_queue: str | None = None
    redis_prefix: str | None = None
    allow_delegation: bool = False
    llm_model: str | None = None
    llm_temperature: float = 0.1
    verbose: bool = True
    metadata: dict[str, Any] = {}


class PresetCreateRequest(BaseModel):
    """Request body for creating a crew preset."""

    name: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-z0-9][a-z0-9\-]*$")
    description: str = Field(..., min_length=1, max_length=500)
    domain: str = Field(default="general", max_length=100)
    version: str = Field(default="1.0.0", max_length=20)
    agents: list[AgentDefinitionRequest] = Field(..., min_length=1)


class PresetResponse(BaseModel):
    name: str
    description: str
    domain: str
    version: str = "1.0.0"
    agent_count: int
    agents: list[dict[str, Any]] = []


class PresetListItem(BaseModel):
    name: str
    description: str
    domain: str
    agent_count: int


# ---------------------------------------------------------------------------
# Agent definition CRUD
# ---------------------------------------------------------------------------


@router.get("/definitions", response_model=PaginatedResponse)
async def list_definitions(
    domain: str | None = Query(None, description="Filter by domain"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: dict = Depends(get_current_user),
):
    """List all available agent definitions."""
    items = []
    if _DEFINITIONS_DIR.exists():
        for p in sorted(_DEFINITIONS_DIR.glob("*.json")):
            try:
                with open(p) as f:
                    data = json.load(f)
                if domain and data.get("domain", "general") != domain:
                    continue
                items.append({
                    "agent_key": data.get("agent_key", p.stem),
                    "name": data.get("name", p.stem),
                    "domain": data.get("domain", "general"),
                    "focus": data.get("focus", ""),
                    "complexity": data.get("complexity", "medium"),
                    "tools": data.get("tools", []),
                })
            except Exception:
                continue

    total = len(items)
    return {
        "items": items[offset : offset + limit],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/definitions/{agent_key}", response_model=AgentDefinitionResponse)
async def get_definition(
    agent_key: str,
    user: dict = Depends(get_current_user),
):
    """Get a single agent definition by key."""
    path = _DEFINITIONS_DIR / f"{agent_key}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Definition '{agent_key}' not found")

    with open(path) as f:
        data = json.load(f)
    return AgentDefinitionResponse(**data)


@router.post("/definitions", response_model=AgentDefinitionResponse, status_code=201)
async def create_definition(
    req: AgentDefinitionRequest,
    user: dict = Depends(get_current_user),
):
    """Create a new agent definition."""
    if user.get("role") not in ("super_admin", "org_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    path = _DEFINITIONS_DIR / f"{req.agent_key}.json"
    if path.exists():
        raise HTTPException(
            status_code=409,
            detail=f"Definition '{req.agent_key}' already exists. Use PUT to update.",
        )

    _DEFINITIONS_DIR.mkdir(parents=True, exist_ok=True)
    data = req.model_dump(mode="json")
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

    logger.info("Created agent definition: %s", req.agent_key)
    return AgentDefinitionResponse(**data)


@router.put("/definitions/{agent_key}", response_model=AgentDefinitionResponse)
async def update_definition(
    agent_key: str,
    req: AgentDefinitionRequest,
    user: dict = Depends(get_current_user),
):
    """Update an existing agent definition."""
    if user.get("role") not in ("super_admin", "org_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    if req.agent_key != agent_key:
        raise HTTPException(
            status_code=400, detail="agent_key in body must match URL parameter"
        )

    path = _DEFINITIONS_DIR / f"{agent_key}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Definition '{agent_key}' not found")

    data = req.model_dump(mode="json")
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

    logger.info("Updated agent definition: %s", agent_key)
    return AgentDefinitionResponse(**data)


@router.delete("/definitions/{agent_key}", status_code=204)
async def delete_definition(
    agent_key: str,
    user: dict = Depends(get_current_user),
):
    """Delete an agent definition."""
    if user.get("role") not in ("super_admin", "org_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    path = _DEFINITIONS_DIR / f"{agent_key}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Definition '{agent_key}' not found")

    path.unlink()
    logger.info("Deleted agent definition: %s", agent_key)


# ---------------------------------------------------------------------------
# Preset management
# ---------------------------------------------------------------------------


@router.get("/presets", response_model=list[PresetListItem])
async def list_presets(
    domain: str | None = Query(None, description="Filter by domain"),
    user: dict = Depends(get_current_user),
):
    """List available crew presets."""
    presets = []
    if _PRESETS_DIR.exists():
        for p in sorted(_PRESETS_DIR.glob("*.json")):
            try:
                with open(p) as f:
                    data = json.load(f)
                if domain and data.get("domain", "general") != domain:
                    continue
                presets.append(PresetListItem(
                    name=p.stem,
                    description=data.get("description", ""),
                    domain=data.get("domain", "general"),
                    agent_count=len(data.get("agents", [])),
                ))
            except Exception:
                continue
    return presets


@router.get("/presets/{preset_name}", response_model=PresetResponse)
async def get_preset(
    preset_name: str,
    user: dict = Depends(get_current_user),
):
    """Get full details of a crew preset."""
    path = _PRESETS_DIR / f"{preset_name}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Preset '{preset_name}' not found")

    with open(path) as f:
        data = json.load(f)

    return PresetResponse(
        name=data.get("name", preset_name),
        description=data.get("description", ""),
        domain=data.get("domain", "general"),
        version=data.get("version", "1.0.0"),
        agent_count=len(data.get("agents", [])),
        agents=data.get("agents", []),
    )


@router.post("/presets", response_model=PresetResponse, status_code=201)
async def create_preset(
    req: PresetCreateRequest,
    user: dict = Depends(get_current_user),
):
    """Create a new crew preset."""
    if user.get("role") not in ("super_admin", "org_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    path = _PRESETS_DIR / f"{req.name}.json"
    if path.exists():
        raise HTTPException(
            status_code=409,
            detail=f"Preset '{req.name}' already exists",
        )

    _PRESETS_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "name": req.name,
        "description": req.description,
        "domain": req.domain,
        "version": req.version,
        "agents": [a.model_dump(mode="json") for a in req.agents],
    }
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

    logger.info("Created preset: %s with %d agents", req.name, len(req.agents))
    return PresetResponse(
        name=req.name,
        description=req.description,
        domain=req.domain,
        version=req.version,
        agent_count=len(req.agents),
        agents=data["agents"],
    )


@router.delete("/presets/{preset_name}", status_code=204)
async def delete_preset(
    preset_name: str,
    user: dict = Depends(get_current_user),
):
    """Delete a crew preset."""
    if user.get("role") not in ("super_admin", "org_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    # Protect built-in presets
    if preset_name in ("qa-standard",):
        raise HTTPException(status_code=403, detail="Cannot delete built-in presets")

    path = _PRESETS_DIR / f"{preset_name}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Preset '{preset_name}' not found")

    path.unlink()
    logger.info("Deleted preset: %s", preset_name)
