"""Shared constants and validation for the agent framework.

Single source of truth for paths, key validation, domains, sizes, and
common patterns used across agents, config, and webgui modules.
"""

from __future__ import annotations

import re
from typing import Literal

from pathlib import Path

# Canonical directory paths
PROJECT_ROOT = Path(__file__).parent.parent
DEFINITIONS_DIR = PROJECT_ROOT / "agents" / "definitions"
PRESETS_DIR = DEFINITIONS_DIR / "presets"
VERSIONS_DIR = DEFINITIONS_DIR / "versions"

# Agent/preset key validation — prevents path traversal
SAFE_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9\-]*$")

# Canonical domain and size lists — single source of truth
DOMAINS: tuple[str, ...] = (
    "quality",
    "software-engineering",
    "design",
    "data-engineering",
    "devops",
)
SIZES: tuple[str, ...] = ("lean", "standard", "large")

# Type aliases for use in Pydantic models and signatures
DomainType = Literal[
    "quality", "software-engineering", "design", "data-engineering", "devops"
]
SizeType = Literal["lean", "standard", "large"]


def validate_agent_key(key: str, label: str = "key") -> None:
    """Raise ValueError if key contains path traversal characters or invalid chars."""
    if not SAFE_KEY_RE.match(key):
        raise ValueError(f"Invalid {label}: {key!r} (must match [a-z0-9][a-z0-9-]*)")


def make_agent_key(role: str) -> str:
    """Convert a role name to a safe kebab-case agent key."""
    key = role.lower().strip()
    key = re.sub(r"[^a-z0-9]+", "-", key)
    key = key.strip("-")
    return key or "agent"
