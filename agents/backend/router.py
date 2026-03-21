"""Backend router — selects the active crew execution backend.

Reads ``AGNOSTIC_BACKEND`` from the environment:
- ``crewai``  (default) — local Python/CrewAI execution
- ``agnosai`` — Rust-native AgnosAI server via HTTP
"""

from __future__ import annotations

import os

from agents.backend.base import CrewBackend

_VALID_BACKENDS = ("crewai", "agnosai")


def get_backend() -> CrewBackend:
    """Return the configured crew execution backend."""
    name = os.getenv("AGNOSTIC_BACKEND", "crewai").lower().strip()

    if name not in _VALID_BACKENDS:
        raise ValueError(
            f"Invalid AGNOSTIC_BACKEND={name!r}. Must be one of: {', '.join(_VALID_BACKENDS)}"
        )

    if name == "agnosai":
        from agents.backend.agnosai_backend import AgnosAIBackend

        base_url = os.getenv("AGNOSAI_URL", "http://localhost:8080")
        api_key = os.getenv("AGNOSAI_API_KEY", "")
        return AgnosAIBackend(base_url=base_url, api_key=api_key)

    from agents.backend.crewai_backend import CrewAIBackend

    return CrewAIBackend()
