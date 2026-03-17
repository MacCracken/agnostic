"""Agent definition and preset management API endpoints.

CRUD for agent definitions (JSON files) and preset management.
Definitions are stored as JSON files in agents/definitions/ and
presets in agents/definitions/presets/.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from agents.constants import DEFINITIONS_DIR, PRESETS_DIR, validate_agent_key
from shared.audit import AuditAction, audit_log
from webgui.routes.dependencies import (
    PaginatedResponse,
    get_current_user,
)

logger = logging.getLogger(__name__)


def _validate_path_key(key: str, label: str = "key") -> None:
    """Validate a path parameter used in file operations. Prevents path traversal."""
    try:
        validate_agent_key(key, label)
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail=f"Invalid {label}: must match [a-z0-9][a-z0-9-]*"
        ) from exc


router = APIRouter()

# Required fields for a valid agent definition
_REQUIRED_FIELDS = {"agent_key", "name", "role", "goal", "backstory"}


# ---------------------------------------------------------------------------
# Request/response models
# ---------------------------------------------------------------------------


class AgentDefinitionRequest(BaseModel):
    """Request body for creating/updating an agent definition."""

    agent_key: str = Field(
        ..., min_length=1, max_length=100, pattern=r"^[a-z0-9][a-z0-9\-]*$"
    )
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

    name: str = Field(
        ..., min_length=1, max_length=100, pattern=r"^[a-z0-9][a-z0-9\-]*$"
    )
    description: str = Field(..., min_length=1, max_length=500)
    domain: str = Field(default="general", max_length=100)
    size: str = Field(default="standard", pattern=r"^(lean|standard|large)$")
    version: str = Field(default="1.0.0", max_length=20)
    agents: list[AgentDefinitionRequest] = Field(..., min_length=1)


class PresetResponse(BaseModel):
    name: str
    description: str
    domain: str
    size: str = "standard"
    version: str = "1.0.0"
    agent_count: int
    agents: list[dict[str, Any]] = []


class PresetAgentSummary(BaseModel):
    agent_key: str
    name: str
    role: str
    focus: str = ""


class PresetListItem(BaseModel):
    name: str
    description: str
    domain: str
    size: str = "standard"
    agent_count: int
    agents: list[PresetAgentSummary] = []


# ---------------------------------------------------------------------------
# Agent definition CRUD
# ---------------------------------------------------------------------------


@router.get("/definitions", response_model=PaginatedResponse)
async def list_definitions(
    domain: str | None = Query(None, description="Filter by domain"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """List all available agent definitions."""
    import asyncio

    def _scan() -> list[dict[str, Any]]:
        items = []
        if DEFINITIONS_DIR.exists():
            for p in sorted(DEFINITIONS_DIR.glob("*.json")):
                try:
                    with open(p) as f:
                        data = json.load(f)
                    if domain and data.get("domain", "general") != domain:
                        continue
                    items.append(
                        {
                            "agent_key": data.get("agent_key", p.stem),
                            "name": data.get("name", p.stem),
                            "domain": data.get("domain", "general"),
                            "focus": data.get("focus", ""),
                            "complexity": data.get("complexity", "medium"),
                            "tools": data.get("tools", []),
                        }
                    )
                except Exception:
                    continue
        return items

    loop = asyncio.get_running_loop()
    items = await loop.run_in_executor(None, _scan)

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
    user: dict[str, Any] = Depends(get_current_user),
) -> AgentDefinitionResponse:
    """Get a single agent definition by key."""
    _validate_path_key(agent_key, "agent_key")
    path = DEFINITIONS_DIR / f"{agent_key}.json"
    if not path.exists():
        raise HTTPException(
            status_code=404, detail=f"Definition '{agent_key}' not found"
        )

    with open(path) as f:
        data = json.load(f)
    return AgentDefinitionResponse(**data)


@router.post("/definitions", response_model=AgentDefinitionResponse, status_code=201)
async def create_definition(
    req: AgentDefinitionRequest,
    user: dict[str, Any] = Depends(get_current_user),
) -> AgentDefinitionResponse:
    """Create a new agent definition."""

    if user.get("role") not in ("super_admin", "org_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    path = DEFINITIONS_DIR / f"{req.agent_key}.json"
    if path.exists():
        raise HTTPException(
            status_code=409,
            detail=f"Definition '{req.agent_key}' already exists. Use PUT to update.",
        )

    DEFINITIONS_DIR.mkdir(parents=True, exist_ok=True)
    data = req.model_dump(mode="json")
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

    audit_log(
        AuditAction.CONFIG_CHANGED,
        actor=user.get("user_id"),
        resource_type="definition",
        resource_id=req.agent_key,
        detail={"action": "create"},
    )
    logger.info("Created agent definition: %s", req.agent_key)
    return AgentDefinitionResponse(**data)


@router.put("/definitions/{agent_key}", response_model=AgentDefinitionResponse)
async def update_definition(
    agent_key: str,
    req: AgentDefinitionRequest,
    user: dict[str, Any] = Depends(get_current_user),
) -> AgentDefinitionResponse:
    """Update an existing agent definition."""
    _validate_path_key(agent_key, "agent_key")
    if user.get("role") not in ("super_admin", "org_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    if req.agent_key != agent_key:
        raise HTTPException(
            status_code=400, detail="agent_key in body must match URL parameter"
        )

    path = DEFINITIONS_DIR / f"{agent_key}.json"
    if not path.exists():
        raise HTTPException(
            status_code=404, detail=f"Definition '{agent_key}' not found"
        )

    data = req.model_dump(mode="json")
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

    audit_log(
        AuditAction.CONFIG_CHANGED,
        actor=user.get("user_id"),
        resource_type="definition",
        resource_id=agent_key,
        detail={"action": "update"},
    )
    logger.info("Updated agent definition: %s", agent_key)
    return AgentDefinitionResponse(**data)


@router.delete("/definitions/{agent_key}", status_code=204)
async def delete_definition(
    agent_key: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> None:
    """Delete an agent definition."""
    _validate_path_key(agent_key, "agent_key")
    if user.get("role") not in ("super_admin", "org_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    path = DEFINITIONS_DIR / f"{agent_key}.json"
    if not path.exists():
        raise HTTPException(
            status_code=404, detail=f"Definition '{agent_key}' not found"
        )

    path.unlink()
    audit_log(
        AuditAction.CONFIG_CHANGED,
        actor=user.get("user_id"),
        resource_type="definition",
        resource_id=agent_key,
        detail={"action": "delete"},
    )
    logger.info("Deleted agent definition: %s", agent_key)


# ---------------------------------------------------------------------------
# Preset management
# ---------------------------------------------------------------------------


@router.get("/presets", response_model=list[PresetListItem])
async def list_presets(
    domain: str | None = Query(
        None,
        description="Filter by domain (e.g. 'qa', 'design', 'software-engineering')",
    ),
    size: str | None = Query(
        None, description="Filter by team size: lean, standard, large"
    ),
    user: dict[str, Any] = Depends(get_current_user),
) -> list[PresetListItem]:
    """List available crew presets (registry cache + user-created on disk)."""
    from config.agent_registry import agent_registry

    # Collect preset data: registry first, then any disk-only presets
    seen: set[str] = set()
    all_presets: list[tuple[str, dict[str, Any]]] = []

    for name in agent_registry.list_presets(domain=domain, size=size):
        data = agent_registry.get_preset(name)
        if data:
            all_presets.append((name, data))
            seen.add(name)

    # Also check disk for user-created presets not in the registry
    if PRESETS_DIR.exists():
        for p in sorted(PRESETS_DIR.glob("*.json")):
            if p.stem in seen:
                continue
            try:
                with open(p) as f:
                    data = json.load(f)
                if domain and data.get("domain", "general") != domain:
                    continue
                if size and data.get("size", "standard") != size:
                    continue
                all_presets.append((p.stem, data))
            except Exception:
                continue

    presets = []
    for name, data in all_presets:
        agent_summaries = [
            PresetAgentSummary(
                agent_key=a.get("agent_key", ""),
                name=a.get("name", ""),
                role=a.get("role", ""),
                focus=a.get("focus", ""),
            )
            for a in data.get("agents", [])
        ]
        presets.append(
            PresetListItem(
                name=name,
                description=data.get("description", ""),
                domain=data.get("domain", "general"),
                size=data.get("size", "standard"),
                agent_count=len(data.get("agents", [])),
                agents=agent_summaries,
            )
        )
    return presets


@router.get("/presets/{preset_name}", response_model=PresetResponse)
async def get_preset(
    preset_name: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> PresetResponse:
    """Get full details of a crew preset."""
    _validate_path_key(preset_name, "preset_name")

    from config.agent_registry import agent_registry

    data = agent_registry.get_preset(preset_name)
    if not data:
        # Fall back to file for user-created presets not in registry
        path = PRESETS_DIR / f"{preset_name}.json"
        if not path.exists():
            raise HTTPException(
                status_code=404, detail=f"Preset '{preset_name}' not found"
            )
        with open(path) as f:
            data = json.load(f)

    return PresetResponse(
        name=data.get("name", preset_name),
        description=data.get("description", ""),
        domain=data.get("domain", "general"),
        size=data.get("size", "standard"),
        version=data.get("version", "1.0.0"),
        agent_count=len(data.get("agents", [])),
        agents=data.get("agents", []),
    )


@router.post("/presets", response_model=PresetResponse, status_code=201)
async def create_preset(
    req: PresetCreateRequest,
    user: dict[str, Any] = Depends(get_current_user),
) -> PresetResponse:
    """Create a new crew preset."""
    if user.get("role") not in ("super_admin", "org_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    path = PRESETS_DIR / f"{req.name}.json"
    if path.exists():
        raise HTTPException(
            status_code=409,
            detail=f"Preset '{req.name}' already exists",
        )

    PRESETS_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "name": req.name,
        "description": req.description,
        "domain": req.domain,
        "size": req.size,
        "version": req.version,
        "agents": [a.model_dump(mode="json") for a in req.agents],
    }
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

    audit_log(
        AuditAction.CONFIG_CHANGED,
        actor=user.get("user_id"),
        resource_type="preset",
        resource_id=req.name,
        detail={"action": "create", "agent_count": len(req.agents)},
    )
    logger.info("Created preset: %s with %d agents", req.name, len(req.agents))
    return PresetResponse(
        name=req.name,
        description=req.description,
        domain=req.domain,
        size=req.size,
        version=req.version,
        agent_count=len(req.agents),
        agents=data["agents"],  # type: ignore[arg-type]
    )


@router.delete("/presets/{preset_name}", status_code=204)
async def delete_preset(
    preset_name: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> None:
    """Delete a crew preset."""
    _validate_path_key(preset_name, "preset_name")
    if user.get("role") not in ("super_admin", "org_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    # Protect built-in presets
    if preset_name in ("quality-standard",):
        raise HTTPException(status_code=403, detail="Cannot delete built-in presets")

    path = PRESETS_DIR / f"{preset_name}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Preset '{preset_name}' not found")

    path.unlink()
    audit_log(
        AuditAction.CONFIG_CHANGED,
        actor=user.get("user_id"),
        resource_type="preset",
        resource_id=preset_name,
        detail={"action": "delete"},
    )
    logger.info("Deleted preset: %s", preset_name)


# ---------------------------------------------------------------------------
# Agent versioning
# ---------------------------------------------------------------------------


class VersionInfo(BaseModel):
    version: int
    name: str = ""
    domain: str = "general"
    file: str = ""


class VersionListResponse(BaseModel):
    agent_key: str
    versions: list[VersionInfo]


class RollbackRequest(BaseModel):
    version: int = Field(..., ge=1)


@router.get("/definitions/{agent_key}/versions", response_model=VersionListResponse)
async def list_definition_versions(
    agent_key: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> VersionListResponse:
    """List all saved versions of an agent definition."""
    _validate_path_key(agent_key, "agent_key")
    from agents.versioning import list_versions

    raw_versions = list_versions(agent_key)
    versions = [VersionInfo(**v) for v in raw_versions]
    return VersionListResponse(agent_key=agent_key, versions=versions)


@router.post("/definitions/{agent_key}/versions", status_code=201)
async def save_definition_version(
    agent_key: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Save the current definition as a versioned snapshot."""
    _validate_path_key(agent_key, "agent_key")
    if user.get("role") not in ("super_admin", "org_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    from agents.versioning import save_version

    result = save_version(agent_key)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.post("/definitions/{agent_key}/rollback")
async def rollback_definition(
    agent_key: str,
    req: RollbackRequest,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Rollback an agent definition to a previous version."""
    _validate_path_key(agent_key, "agent_key")
    if user.get("role") not in ("super_admin", "org_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    from agents.versioning import rollback

    result = rollback(agent_key, req.version)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


# ---------------------------------------------------------------------------
# Package import/export
# ---------------------------------------------------------------------------


class ExportPackageRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    definition_keys: list[str] = Field(default_factory=list)
    preset_names: list[str] = Field(default_factory=list)
    version: str = Field(default="1.0.0", max_length=20)
    description: str = Field(default="", max_length=500)
    domain: str = Field(default="general", max_length=100)
    author: str = Field(default="", max_length=200)


@router.post("/packages/export")
async def export_package_endpoint(
    req: ExportPackageRequest,
    user: dict[str, Any] = Depends(get_current_user),
) -> Response:
    """Export agent definitions and presets as a downloadable .agpkg bundle."""
    import asyncio

    from agents.packaging import export_package

    loop = asyncio.get_running_loop()
    data = await loop.run_in_executor(
        None,
        lambda: export_package(
            name=req.name,
            definition_keys=req.definition_keys,
            preset_names=req.preset_names,
            version=req.version,
            description=req.description,
            domain=req.domain,
            author=req.author,
        ),
    )
    return Response(
        content=data,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{req.name.replace(chr(34), "")}-{req.version.replace(chr(34), "")}.agpkg"',
        },
    )


# ---------------------------------------------------------------------------
# Custom tool upload
# ---------------------------------------------------------------------------


class ToolUploadRequest(BaseModel):
    name: str = Field(
        ..., min_length=1, max_length=100, pattern=r"^[A-Za-z][A-Za-z0-9_]*$"
    )
    source_code: str = Field(..., min_length=10, max_length=50000)


class ToolUploadResponse(BaseModel):
    name: str
    status: str
    description: str = ""


@router.post("/tools/upload", response_model=ToolUploadResponse, status_code=201)
async def upload_custom_tool(
    req: ToolUploadRequest,
    user: dict[str, Any] = Depends(get_current_user),
) -> ToolUploadResponse:
    """Upload a custom BaseTool implementation.

    The source code must define exactly one class that inherits from BaseTool.
    The tool will be registered globally and available to all agents.
    """
    if user.get("role") not in ("super_admin", "org_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    from agents.tool_registry import load_tool_from_source

    try:
        tool_cls = load_tool_from_source(req.name, req.source_code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    desc = ""
    if tool_cls and hasattr(tool_cls, "description"):
        desc = tool_cls.description if isinstance(tool_cls.description, str) else ""

    audit_log(
        AuditAction.CONFIG_CHANGED,
        actor=user.get("user_id"),
        resource_type="tool",
        resource_id=req.name,
        detail={"action": "upload"},
    )
    return ToolUploadResponse(name=req.name, status="registered", description=desc)


@router.get("/tools")
async def list_tools(
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """List all registered tools."""
    from agents.tool_registry import list_registered_tools

    return {"tools": list_registered_tools()}
