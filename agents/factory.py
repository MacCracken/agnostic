"""
AgentFactory — create agents from definitions (YAML, JSON, API, or presets).

This is the primary entry point for creating agents dynamically.
Existing QA agents are wrapped via from_legacy() without changing their code.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from agents.base import AgentDefinition, BaseAgent

logger = logging.getLogger(__name__)

# Where YAML/JSON agent definitions live
_DEFINITIONS_DIR = Path(__file__).parent / "definitions"
_PRESETS_DIR = _DEFINITIONS_DIR / "presets"


class AgentFactory:
    """Create BaseAgent instances from various sources."""

    # Cache loaded definitions so we don't re-parse on every call
    _definition_cache: dict[str, AgentDefinition] = {}

    @classmethod
    def from_definition(cls, definition: AgentDefinition) -> BaseAgent:
        """Create an agent directly from an AgentDefinition."""
        return BaseAgent(definition)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BaseAgent:
        """Create an agent from a plain dict (e.g. API request body)."""
        defn = AgentDefinition.from_dict(data)
        return BaseAgent(defn)

    @classmethod
    def from_file(cls, path: str | Path) -> BaseAgent:
        """Load an agent definition from a JSON or YAML file."""
        path = Path(path)
        defn = cls._load_definition_file(path)
        return BaseAgent(defn)

    @classmethod
    def from_preset(cls, preset_name: str) -> list[BaseAgent]:
        """Load all agents for a named preset (e.g. 'qa-standard')."""
        preset_path = _PRESETS_DIR / f"{preset_name}.json"
        if not preset_path.exists():
            raise FileNotFoundError(f"Preset '{preset_name}' not found at {preset_path}")

        with open(preset_path) as f:
            preset_data = json.load(f)

        agents = []
        for agent_data in preset_data.get("agents", []):
            defn = AgentDefinition.from_dict(agent_data)
            agents.append(BaseAgent(defn))

        logger.info("Loaded preset '%s' with %d agents", preset_name, len(agents))
        return agents

    @classmethod
    def list_presets(cls) -> list[dict[str, Any]]:
        """List available presets with metadata."""
        presets = []
        if _PRESETS_DIR.exists():
            for p in sorted(_PRESETS_DIR.glob("*.json")):
                try:
                    with open(p) as f:
                        data = json.load(f)
                    presets.append({
                        "name": p.stem,
                        "description": data.get("description", ""),
                        "domain": data.get("domain", "general"),
                        "agent_count": len(data.get("agents", [])),
                    })
                except Exception as exc:
                    logger.warning("Skipping invalid preset %s: %s", p, exc)
        return presets

    @classmethod
    def list_definitions(cls) -> list[dict[str, Any]]:
        """List individual agent definitions available in the definitions directory."""
        definitions = []
        if _DEFINITIONS_DIR.exists():
            for p in sorted(_DEFINITIONS_DIR.glob("*.json")):
                try:
                    with open(p) as f:
                        data = json.load(f)
                    definitions.append({
                        "agent_key": data.get("agent_key", p.stem),
                        "name": data.get("name", p.stem),
                        "domain": data.get("domain", "general"),
                        "description": data.get("focus", ""),
                    })
                except Exception as exc:
                    logger.warning("Skipping invalid definition %s: %s", p, exc)
        return definitions

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @classmethod
    def _load_definition_file(cls, path: Path) -> AgentDefinition:
        """Parse a JSON or YAML file into an AgentDefinition."""
        cache_key = str(path.resolve())
        if cache_key in cls._definition_cache:
            return cls._definition_cache[cache_key]

        with open(path) as f:
            if path.suffix in (".yaml", ".yml"):
                try:
                    import yaml

                    data = yaml.safe_load(f)
                except ImportError:
                    raise ImportError(
                        "PyYAML is required to load YAML agent definitions. "
                        "Install it with: pip install pyyaml"
                    )
            else:
                data = json.load(f)

        defn = AgentDefinition.from_dict(data)
        cls._definition_cache[cache_key] = defn
        return defn
