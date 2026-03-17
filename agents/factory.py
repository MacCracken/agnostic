"""
AgentFactory — create agents from definitions (YAML, JSON, API, or presets).

This is the primary entry point for creating agents dynamically.
Existing QA agents are wrapped via from_legacy() without changing their code.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from agents.base import AgentDefinition, BaseAgent
from agents.constants import DEFINITIONS_DIR, PRESETS_DIR, SAFE_KEY_RE

logger = logging.getLogger(__name__)


class AgentFactory:
    """Create BaseAgent instances from various sources."""

    # Cache loaded definitions so we don't re-parse on every call.
    # Bounded to prevent unbounded memory growth in long-running processes.
    _definition_cache: dict[str, AgentDefinition] = {}
    _CACHE_MAX_SIZE = 200

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
        """Load an agent definition from a JSON or YAML file.

        The resolved path must be under the project's definitions directory
        or an explicit absolute path. Relative paths containing '..' are rejected.
        """
        path = Path(path)
        resolved = path.resolve()
        # Block path traversal via symlinks — if the caller provided a path
        # under DEFINITIONS_DIR, the resolved path must stay there.
        # Absolute paths outside DEFINITIONS_DIR are allowed (e.g. preset loading).
        if path != resolved and not resolved.is_relative_to(DEFINITIONS_DIR):
            raise ValueError(f"Path traversal not allowed: {path}")
        if not path.is_absolute() and not resolved.is_relative_to(DEFINITIONS_DIR):
            raise ValueError(f"Path traversal not allowed: {path}")
        if not resolved.exists():
            raise FileNotFoundError(f"Definition file not found: {resolved}")
        defn = cls._load_definition_file(resolved)
        return BaseAgent(defn)

    @classmethod
    def invalidate_cache(cls, path: str | None = None) -> None:
        """Clear definition cache. Pass a path to clear a single entry, or None for all."""
        if path is None:
            cls._definition_cache.clear()
        else:
            cls._definition_cache.pop(str(Path(path).resolve()), None)

    @classmethod
    def from_preset(cls, preset_name: str) -> list[BaseAgent]:
        """Load all agents for a named preset (e.g. 'quality-standard')."""
        if not SAFE_KEY_RE.match(preset_name):
            raise ValueError(f"Invalid preset name: {preset_name!r}")
        preset_path = PRESETS_DIR / f"{preset_name}.json"
        if not preset_path.exists():
            raise FileNotFoundError(
                f"Preset '{preset_name}' not found at {preset_path}"
            )

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
        """List available presets with metadata from the agent registry cache."""
        from config.agent_registry import agent_registry

        presets = []
        for name in agent_registry.list_presets():
            data = agent_registry.get_preset(name)
            if data:
                presets.append(
                    {
                        "name": name,
                        "description": data.get("description", ""),
                        "domain": data.get("domain", "general"),
                        "agent_count": len(data.get("agents", [])),
                    }
                )
        return presets

    @classmethod
    def list_definitions(cls) -> list[dict[str, Any]]:
        """List individual agent definitions available in the definitions directory."""
        definitions = []
        if DEFINITIONS_DIR.exists():
            for p in sorted(DEFINITIONS_DIR.glob("*.json")):
                try:
                    with open(p) as f:
                        data = json.load(f)
                    definitions.append(
                        {
                            "agent_key": data.get("agent_key", p.stem),
                            "name": data.get("name", p.stem),
                            "domain": data.get("domain", "general"),
                            "description": data.get("focus", ""),
                        }
                    )
                except Exception as exc:
                    logger.warning("Skipping invalid definition %s: %s", p, exc)
        return definitions

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @classmethod
    def _load_definition_file(cls, path: Path) -> AgentDefinition:
        """Parse a JSON or YAML file into an AgentDefinition."""
        from shared.metrics import DEFINITION_CACHE_HITS, DEFINITION_CACHE_MISSES

        cache_key = str(path.resolve())
        if cache_key in cls._definition_cache:
            DEFINITION_CACHE_HITS.inc()
            return cls._definition_cache[cache_key]
        DEFINITION_CACHE_MISSES.inc()

        with open(path) as f:
            if path.suffix in (".yaml", ".yml"):
                try:
                    import yaml  # type: ignore[import-untyped]

                    data = yaml.safe_load(f)
                except ImportError as exc:
                    raise ImportError(
                        "PyYAML is required to load YAML agent definitions. "
                        "Install it with: pip install pyyaml"
                    ) from exc
            else:
                data = json.load(f)

        defn = AgentDefinition.from_dict(data)
        # Evict oldest entries if cache is full
        if len(cls._definition_cache) >= cls._CACHE_MAX_SIZE:
            oldest_key = next(iter(cls._definition_cache))
            del cls._definition_cache[oldest_key]
        cls._definition_cache[cache_key] = defn
        return defn
