"""Shared constants and validation for the agent framework.

Single source of truth for paths, key validation, and common patterns
used across agents/base.py, agents/factory.py, agents/versioning.py,
agents/packaging.py, and webgui/routes/definitions.py.
"""

from __future__ import annotations

import re
from pathlib import Path

# Canonical directory paths
PROJECT_ROOT = Path(__file__).parent.parent
DEFINITIONS_DIR = PROJECT_ROOT / "agents" / "definitions"
PRESETS_DIR = DEFINITIONS_DIR / "presets"
VERSIONS_DIR = DEFINITIONS_DIR / "versions"

# Agent/preset key validation — prevents path traversal
SAFE_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9\-]*$")


def validate_agent_key(key: str, label: str = "key") -> None:
    """Raise ValueError if key contains path traversal characters or invalid chars."""
    if not SAFE_KEY_RE.match(key):
        raise ValueError(f"Invalid {label}: {key!r} (must match [a-z0-9][a-z0-9-]*)")
