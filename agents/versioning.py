"""
Agent Versioning — version agent definitions with rollback support.

Each agent definition can have multiple versions stored as:
  agents/definitions/versions/{agent_key}/v{N}.json

The active version is the file at agents/definitions/{agent_key}.json.
Previous versions are kept for rollback.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).parent.parent
_DEFINITIONS_DIR = _PROJECT_ROOT / "agents" / "definitions"
_VERSIONS_DIR = _DEFINITIONS_DIR / "versions"


def _version_dir(agent_key: str) -> Path:
    return _VERSIONS_DIR / agent_key


def _next_version(agent_key: str) -> int:
    """Return the next version number for an agent."""
    vdir = _version_dir(agent_key)
    if not vdir.exists():
        return 1
    existing = sorted(vdir.glob("v*.json"))
    if not existing:
        return 1
    # Extract version number from filename like v3.json
    nums = []
    for p in existing:
        try:
            nums.append(int(p.stem[1:]))
        except ValueError:
            continue
    return (max(nums) + 1) if nums else 1


def save_version(agent_key: str, definition_data: dict[str, Any] | None = None) -> dict[str, Any]:
    """Save the current definition as a versioned snapshot.

    If definition_data is provided, it's used directly. Otherwise, reads from
    the active definition file.

    Returns metadata about the saved version.
    """
    active_path = _DEFINITIONS_DIR / f"{agent_key}.json"

    if definition_data is None:
        if not active_path.exists():
            return {"error": f"No active definition for '{agent_key}'"}
        with open(active_path) as f:
            definition_data = json.load(f)

    version_num = _next_version(agent_key)
    vdir = _version_dir(agent_key)
    vdir.mkdir(parents=True, exist_ok=True)

    version_path = vdir / f"v{version_num}.json"
    with open(version_path, "w") as f:
        json.dump(definition_data, f, indent=2)

    logger.info("Saved version v%d for agent '%s'", version_num, agent_key)
    return {
        "agent_key": agent_key,
        "version": version_num,
        "path": str(version_path),
    }


def list_versions(agent_key: str) -> list[dict[str, Any]]:
    """List all saved versions for an agent definition."""
    vdir = _version_dir(agent_key)
    if not vdir.exists():
        return []

    versions = []
    for p in sorted(vdir.glob("v*.json")):
        try:
            num = int(p.stem[1:])
            with open(p) as f:
                data = json.load(f)
            versions.append({
                "version": num,
                "name": data.get("name", agent_key),
                "domain": data.get("domain", "general"),
                "file": p.name,
            })
        except Exception:
            continue
    return versions


def get_version(agent_key: str, version: int) -> dict[str, Any] | None:
    """Get a specific version of an agent definition."""
    path = _version_dir(agent_key) / f"v{version}.json"
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def rollback(agent_key: str, version: int) -> dict[str, Any]:
    """Rollback an agent definition to a previous version.

    Saves the current active definition as a new version first, then
    replaces the active definition with the specified version.
    """
    # Verify the target version exists
    target_data = get_version(agent_key, version)
    if target_data is None:
        return {"error": f"Version v{version} not found for '{agent_key}'"}

    # Save current as a new version before overwriting
    active_path = _DEFINITIONS_DIR / f"{agent_key}.json"
    if active_path.exists():
        save_version(agent_key)

    # Write the target version as the active definition
    with open(active_path, "w") as f:
        json.dump(target_data, f, indent=2)

    logger.info("Rolled back agent '%s' to v%d", agent_key, version)
    return {
        "agent_key": agent_key,
        "rolled_back_to": version,
        "status": "ok",
    }
