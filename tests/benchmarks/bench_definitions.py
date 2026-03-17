"""Benchmark: definition list scalability.

Measures GET /definitions at 10/50/200/500 definition files.
Run: .venv/bin/python tests/benchmarks/bench_definitions.py
"""

from __future__ import annotations

import json
import os
import shutil
import sys

# Ensure project root is on path
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
os.environ.setdefault("ENVIRONMENT", "test")
import tempfile
import time
from pathlib import Path

from fastapi.testclient import TestClient


def _make_definition(key: str) -> dict:
    return {
        "agent_key": key,
        "name": f"Agent {key}",
        "role": "tester",
        "goal": "test",
        "backstory": "benchmark agent",
        "focus": "benchmarking",
        "domain": "quality",
        "tools": [],
        "complexity": "medium",
    }


def _setup_app(definitions_dir: Path):
    """Create a test app with patched definitions dir."""
    import webgui.routes.definitions as defs_mod

    original = defs_mod.DEFINITIONS_DIR
    defs_mod.DEFINITIONS_DIR = definitions_dir

    from fastapi import FastAPI

    from webgui.routes.definitions import router
    from webgui.routes.dependencies import get_current_user

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: {
        "user_id": "bench",
        "role": "admin",
    }
    return TestClient(app), original


def bench_list_definitions():
    """Benchmark list_definitions at various file counts."""
    counts = [10, 50, 200, 500]
    results = []

    for count in counts:
        tmpdir = Path(tempfile.mkdtemp())
        try:
            # Create definition files
            for i in range(count):
                key = f"bench-agent-{i:04d}"
                (tmpdir / f"{key}.json").write_text(json.dumps(_make_definition(key)))

            client, original = _setup_app(tmpdir)

            # Warm up
            client.get("/api/v1/definitions")

            # Benchmark
            iterations = 20
            start = time.monotonic()
            for _ in range(iterations):
                resp = client.get("/api/v1/definitions?limit=200")
                assert resp.status_code == 200
            elapsed = time.monotonic() - start

            avg_ms = (elapsed / iterations) * 1000
            results.append(
                {"files": count, "avg_ms": round(avg_ms, 2), "iterations": iterations}
            )
            print(f"  {count:>4} files: {avg_ms:>8.2f} ms/request")

            # Restore
            import webgui.routes.definitions as defs_mod

            defs_mod.DEFINITIONS_DIR = original
        finally:
            shutil.rmtree(tmpdir)

    return results


def bench_get_definition():
    """Benchmark single definition fetch."""
    tmpdir = Path(tempfile.mkdtemp())
    try:
        key = "bench-single"
        (tmpdir / f"{key}.json").write_text(json.dumps(_make_definition(key)))

        client, original = _setup_app(tmpdir)

        iterations = 100
        start = time.monotonic()
        for _ in range(iterations):
            resp = client.get(f"/api/v1/definitions/{key}")
            assert resp.status_code == 200
        elapsed = time.monotonic() - start

        avg_ms = (elapsed / iterations) * 1000
        print(f"  Single fetch: {avg_ms:.2f} ms/request ({iterations} iterations)")

        import webgui.routes.definitions as defs_mod

        defs_mod.DEFINITIONS_DIR = original
    finally:
        shutil.rmtree(tmpdir)


if __name__ == "__main__":
    print("=" * 60)
    print("Benchmark: Definition List Scalability")
    print("=" * 60)
    print("\nGET /definitions (paginated, limit=200):")
    bench_list_definitions()
    print("\nGET /definitions/{key} (single):")
    bench_get_definition()
    print()
