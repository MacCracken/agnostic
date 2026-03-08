"""Single source of truth for the project version.

Reads from the VERSION file at the project root. Falls back to a hardcoded
value if the file cannot be found (e.g. inside a Docker container where the
file layout differs).
"""

from __future__ import annotations

from pathlib import Path

_FALLBACK = "0.0.0"


def _read_version() -> str:
    """Read version string from the VERSION file."""
    # Walk up from this file to find the project root VERSION file.
    # shared/version.py -> shared/ -> project root
    candidates = [
        Path(__file__).resolve().parent.parent / "VERSION",  # dev layout
        Path("/app/VERSION"),  # Docker container layout
    ]
    for path in candidates:
        try:
            return path.read_text().strip()
        except OSError:
            continue
    return _FALLBACK


VERSION: str = _read_version()
