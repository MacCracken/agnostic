"""
Tool Registry — global lookup for BaseTool subclasses by name.

When an agent definition references tools by string name (e.g. "LoadTestingTool"),
the BaseAgent resolves them through this registry.

Tools self-register on import, or can be registered explicitly.
Existing QA tools are registered here for backwards compatibility.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from shared.crewai_compat import BaseTool

logger = logging.getLogger(__name__)

# name -> tool class (not instance). Bounded to prevent unbounded growth.
_REGISTRY: dict[str, type[BaseTool]] = {}
_REGISTRY_MAX_SIZE = 500


def _check_registry_capacity(name: str) -> None:
    """Raise ValueError if registry is full and name is not already registered."""
    if len(_REGISTRY) >= _REGISTRY_MAX_SIZE and name not in _REGISTRY:
        raise ValueError(f"Tool registry full ({_REGISTRY_MAX_SIZE} tools)")


def register_tool(cls: type[BaseTool]) -> type[BaseTool]:
    """Decorator: register a BaseTool subclass by its class name."""
    _check_registry_capacity(cls.__name__)
    _REGISTRY[cls.__name__] = cls
    return cls


def register_tool_class(name: str, cls: type[BaseTool]) -> None:
    """Register a tool class under an explicit name."""
    _check_registry_capacity(name)
    _REGISTRY[name] = cls


def get_tool(name: str) -> type[BaseTool] | None:
    """Look up a tool class by name.  Returns None if not found."""
    return _REGISTRY.get(name)


# Dict alias — BaseAgent._resolve_tools does tool_registry.get(name) on this
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


def load_tool_from_source(name: str, source_code: str) -> type[BaseTool] | None:
    """Dynamically load a BaseTool subclass from Python source code.

    The source must define exactly one class that inherits from BaseTool.
    The class is compiled in a namespace with limited builtins.

    **SECURITY WARNING**: The restricted builtins are defense-in-depth only,
    NOT a real sandbox.  CPython ``exec()`` cannot be securely sandboxed — a
    determined attacker can escape via MRO walking (``__subclasses__``,
    ``__globals__``).  This endpoint is gated behind ``super_admin``/
    ``org_admin`` auth.  Only upload tool code from trusted sources.

    For production hardening, consider process-level isolation (nsjail,
    gVisor, or WASM runtime) around this function.

    Args:
        name: Name to register the tool under.
        source_code: Python source code defining the tool class.

    Returns:
        The tool class, or None if loading failed.

    Raises:
        ValueError: If the source doesn't define a valid BaseTool subclass.
    """
    from shared.crewai_compat import BaseTool as _BaseTool

    # Compile in a restricted namespace — no builtins except safe ones
    _real_builtins = __builtins__ if isinstance(__builtins__, dict) else vars(__builtins__)
    _SAFE_BUILTINS = {
        "True": True, "False": False, "None": None,
        "int": int, "float": float, "str": str, "bool": bool,
        "list": list, "dict": dict, "set": set, "tuple": tuple,
        "len": len, "range": range, "enumerate": enumerate,
        "zip": zip, "map": map, "filter": filter,
        "min": min, "max": max, "sum": sum, "abs": abs, "round": round,
        "sorted": sorted, "reversed": reversed,
        "isinstance": isinstance, "issubclass": issubclass,
        "type": type, "hasattr": hasattr, "getattr": getattr,
        "print": print,
        "Exception": Exception, "ValueError": ValueError,
        "TypeError": TypeError, "KeyError": KeyError,
        "__name__": f"__tool_{name}__",
        "__build_class__": _real_builtins["__build_class__"],
    }

    namespace: dict[str, Any] = {
        "__builtins__": _SAFE_BUILTINS,
        "BaseTool": _BaseTool,
        "Any": Any,
    }

    try:
        exec(compile(source_code, f"<tool:{name}>", "exec"), namespace)  # noqa: S102
    except Exception as exc:
        logger.error("Failed to compile tool '%s': %s", name, exc)
        raise ValueError(f"Tool compilation failed: {exc}") from exc

    # Find the BaseTool subclass in the namespace
    tool_classes = [
        v for k, v in namespace.items()
        if isinstance(v, type)
        and issubclass(v, _BaseTool)
        and v is not _BaseTool
        and not k.startswith("_")
    ]

    if not tool_classes:
        raise ValueError(
            f"No BaseTool subclass found in source for '{name}'"
        )

    if len(tool_classes) > 1:
        logger.warning(
            "Multiple BaseTool subclasses in '%s', using first: %s",
            name, tool_classes[0].__name__,
        )

    tool_cls = tool_classes[0]
    _check_registry_capacity(name)
    _REGISTRY[name] = tool_cls
    logger.info("Loaded custom tool '%s' (%s)", name, tool_cls.__name__)
    return tool_cls


def list_registered_tools() -> list[dict[str, str]]:
    """List all registered tools with their names and descriptions."""
    tools = []
    for name, cls in sorted(_REGISTRY.items()):
        desc = ""
        if hasattr(cls, "description"):
            desc = cls.description if isinstance(cls.description, str) else ""
        tools.append({"name": name, "description": desc})
    return tools


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
