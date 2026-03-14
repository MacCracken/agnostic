"""
Tool Registry — global lookup for BaseTool subclasses by name.

When an agent definition references tools by string name (e.g. "LoadTestingTool"),
the BaseAgent resolves them through this registry.

Tools self-register on import, or can be registered explicitly.
Existing QA tools are registered here for backwards compatibility.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shared.crewai_compat import BaseTool

logger = logging.getLogger(__name__)

# name -> tool class (not instance)
_REGISTRY: dict[str, type[BaseTool]] = {}


def register_tool(cls: type[BaseTool]) -> type[BaseTool]:
    """Decorator: register a BaseTool subclass by its class name."""
    _REGISTRY[cls.__name__] = cls
    return cls


def register_tool_class(name: str, cls: type[BaseTool]) -> None:
    """Register a tool class under an explicit name."""
    _REGISTRY[name] = cls


def get_tool(name: str) -> type[BaseTool] | None:
    """Look up a tool class by name.  Returns None if not found."""
    return _REGISTRY.get(name)


# Module-level alias for BaseAgent._resolve_tools
tool_registry = _REGISTRY


def register_existing_qa_tools() -> None:
    """Import existing QA agent modules to populate the registry.

    This is called lazily on first tool resolution so we don't
    break imports if agent modules aren't available (e.g. in tests).
    """
    _import_safe("agents.performance.qa_performance", [
        "PerformanceMonitoringTool",
        "LoadTestingTool",
        "ResilienceValidationTool",
        "AdvancedProfilingTool",
    ])
    # Add other agent modules as needed — the modules are large,
    # so we only register the tool classes we can find.
    logger.info("Registered %d tools from existing QA agents", len(_REGISTRY))


def _import_safe(module_path: str, class_names: list[str]) -> None:
    """Import tool classes from a module without failing hard."""
    try:
        import importlib

        mod = importlib.import_module(module_path)
        for name in class_names:
            cls = getattr(mod, name, None)
            if cls is not None:
                _REGISTRY[name] = cls
    except Exception as exc:
        logger.debug("Could not import %s: %s", module_path, exc)
