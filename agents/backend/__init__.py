"""Backend abstraction for crew execution routing.

Supports two backends:
- ``crewai``  — existing Python/CrewAI execution (default)
- ``agnosai`` — Rust-native AgnosAI server via HTTP
"""

from agents.backend.base import BackendResult, CrewBackend
from agents.backend.router import get_backend

__all__ = ["BackendResult", "CrewBackend", "get_backend"]
