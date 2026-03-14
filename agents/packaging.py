"""
Agent Packaging — import/export agent definitions and presets as .agpkg bundles.

An .agpkg bundle is a ZIP archive containing:
- manifest.json  — package metadata (name, version, domain, author, etc.)
- definitions/   — agent definition JSON files
- presets/        — crew preset JSON files
- tools/          — optional custom tool Python modules

Bundles can be imported via API or CLI to add agents to a running AAS instance.
"""

from __future__ import annotations

import io
import json
import logging
import os
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).parent.parent
_DEFINITIONS_DIR = _PROJECT_ROOT / "agents" / "definitions"
_PRESETS_DIR = _DEFINITIONS_DIR / "presets"

MANIFEST_FILENAME = "manifest.json"

# Safety limits for ZIP import
_MAX_UNCOMPRESSED_SIZE = 10 * 1024 * 1024  # 10 MB
_MAX_ENTRY_COUNT = 100
_SAFE_KEY_RE = __import__("re").compile(r"^[a-z0-9][a-z0-9\-]*$")


class PackageManifest:
    """Metadata for an .agpkg bundle."""

    def __init__(
        self,
        *,
        name: str,
        version: str = "1.0.0",
        description: str = "",
        domain: str = "general",
        author: str = "",
        license: str = "MIT",
        min_aas_version: str = "2026.3.14",
        definitions: list[str] | None = None,
        presets: list[str] | None = None,
        tools: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        self.name = name
        self.version = version
        self.description = description
        self.domain = domain
        self.author = author
        self.license = license
        self.min_aas_version = min_aas_version
        self.definitions = definitions or []
        self.presets = presets or []
        self.tools = tools or []
        self.metadata = metadata or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "domain": self.domain,
            "author": self.author,
            "license": self.license,
            "min_aas_version": self.min_aas_version,
            "definitions": self.definitions,
            "presets": self.presets,
            "tools": self.tools,
            "metadata": self.metadata,
            "packaged_at": datetime.now(UTC).isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PackageManifest:
        return cls(**{k: v for k, v in data.items() if k in {
            "name", "version", "description", "domain", "author",
            "license", "min_aas_version", "definitions", "presets",
            "tools", "metadata",
        }})


def export_package(
    name: str,
    *,
    definition_keys: list[str] | None = None,
    preset_names: list[str] | None = None,
    version: str = "1.0.0",
    description: str = "",
    domain: str = "general",
    author: str = "",
) -> bytes:
    """Export agent definitions and/or presets as a .agpkg ZIP bundle.

    Returns the ZIP file as bytes (suitable for HTTP response or file write).
    """
    buf = io.BytesIO()

    manifest = PackageManifest(
        name=name,
        version=version,
        description=description,
        domain=domain,
        author=author,
        definitions=definition_keys or [],
        presets=preset_names or [],
    )

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # Add definitions
        for key in (definition_keys or []):
            path = _DEFINITIONS_DIR / f"{key}.json"
            if path.exists():
                zf.write(path, f"definitions/{key}.json")
            else:
                logger.warning("Definition '%s' not found, skipping", key)

        # Add presets
        for preset_name in (preset_names or []):
            path = _PRESETS_DIR / f"{preset_name}.json"
            if path.exists():
                zf.write(path, f"presets/{preset_name}.json")
            else:
                logger.warning("Preset '%s' not found, skipping", preset_name)

        # Write manifest
        zf.writestr(MANIFEST_FILENAME, json.dumps(manifest.to_dict(), indent=2))

    logger.info(
        "Exported package '%s' v%s (%d definitions, %d presets)",
        name, version,
        len(definition_keys or []),
        len(preset_names or []),
    )
    return buf.getvalue()


def import_package(data: bytes, *, overwrite: bool = False) -> dict[str, Any]:
    """Import a .agpkg ZIP bundle, installing definitions and presets.

    Returns a summary of what was installed.

    Args:
        data: Raw bytes of the .agpkg ZIP file.
        overwrite: If True, overwrite existing definitions/presets.
    """
    buf = io.BytesIO(data)
    result: dict[str, Any] = {
        "definitions_installed": [],
        "presets_installed": [],
        "skipped": [],
        "errors": [],
    }

    try:
        with zipfile.ZipFile(buf, "r") as zf:
            # Safety: check entry count and total uncompressed size
            infos = zf.infolist()
            if len(infos) > _MAX_ENTRY_COUNT:
                return {"errors": [f"Package has {len(infos)} entries (max {_MAX_ENTRY_COUNT})"]}
            total_size = sum(i.file_size for i in infos)
            if total_size > _MAX_UNCOMPRESSED_SIZE:
                return {"errors": [f"Total uncompressed size {total_size} exceeds {_MAX_UNCOMPRESSED_SIZE} bytes"]}

            # Read manifest
            if MANIFEST_FILENAME not in zf.namelist():
                return {"errors": ["Missing manifest.json in package"]}

            manifest_data = json.loads(zf.read(MANIFEST_FILENAME))
            manifest = PackageManifest.from_dict(manifest_data)
            result["manifest"] = manifest.to_dict()

            # Install definitions
            _DEFINITIONS_DIR.mkdir(parents=True, exist_ok=True)
            for name in zf.namelist():
                if name.startswith("definitions/") and name.endswith(".json"):
                    key = Path(name).stem
                    # Validate key is safe (no path traversal)
                    if not _SAFE_KEY_RE.match(key):
                        result["errors"].append(f"Invalid definition key: {key}")
                        continue
                    # Validate content is valid JSON
                    raw = zf.read(name)
                    try:
                        json.loads(raw)
                    except json.JSONDecodeError:
                        result["errors"].append(f"Invalid JSON in {name}")
                        continue
                    target = _DEFINITIONS_DIR / f"{key}.json"
                    if target.exists() and not overwrite:
                        result["skipped"].append(f"definition:{key}")
                        continue
                    target.write_bytes(raw)
                    result["definitions_installed"].append(key)

            # Install presets
            _PRESETS_DIR.mkdir(parents=True, exist_ok=True)
            for name in zf.namelist():
                if name.startswith("presets/") and name.endswith(".json"):
                    preset_name = Path(name).stem
                    if not _SAFE_KEY_RE.match(preset_name):
                        result["errors"].append(f"Invalid preset name: {preset_name}")
                        continue
                    raw = zf.read(name)
                    try:
                        json.loads(raw)
                    except json.JSONDecodeError:
                        result["errors"].append(f"Invalid JSON in {name}")
                        continue
                    target = _PRESETS_DIR / f"{preset_name}.json"
                    if target.exists() and not overwrite:
                        result["skipped"].append(f"preset:{preset_name}")
                        continue
                    target.write_bytes(raw)
                    result["presets_installed"].append(preset_name)

    except zipfile.BadZipFile:
        result["errors"].append("Invalid ZIP file")
    except Exception as exc:
        result["errors"].append(str(exc))

    logger.info(
        "Imported package: %d definitions, %d presets, %d skipped, %d errors",
        len(result["definitions_installed"]),
        len(result["presets_installed"]),
        len(result["skipped"]),
        len(result["errors"]),
    )
    return result
