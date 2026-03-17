"""Compatibility helpers for CrewAI tooling."""

from __future__ import annotations

from typing import Any

try:
    from crewai.tools import BaseTool
except Exception:  # pragma: no cover - fallback for older CrewAI builds

    class BaseTool:  # type: ignore[no-redef]
        name: str = ""
        description: str = ""

        def _run(self, *args: Any, **kwargs: Any) -> Any:
            raise NotImplementedError("BaseTool._run must be implemented")


__all__ = ["BaseTool"]
