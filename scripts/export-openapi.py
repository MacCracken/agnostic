"""Export FastAPI OpenAPI schema to docs/api/openapi.json.

Usage:
    python scripts/export-openapi.py

Requires the webgui dependencies to be installed:
    pip install -e ".[web]"
"""

import json
import os
import sys

# Ensure project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Minimal env setup so imports don't crash
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("WEBGUI_SECRET_KEY", os.urandom(32).hex())

try:
    from webgui.app import app  # FastAPI application instance

    schema = app.openapi()
    out_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "docs",
        "api",
        "openapi.json",
    )
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(schema, f, indent=2)
    print(f"Schema written to {out_path}")
except Exception as e:
    print(f"Error generating schema: {e}", file=sys.stderr)
    sys.exit(1)
