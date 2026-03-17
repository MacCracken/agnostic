"""Benchmark: package import/export with large bundles.

Measures export and import of bundles with 50 definitions + 10 presets,
and import of 100-entry bundles.
Run: .venv/bin/python tests/benchmarks/bench_packaging.py
"""

from __future__ import annotations

import json
import os
import shutil
import sys

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
os.environ.setdefault("ENVIRONMENT", "test")
import tempfile
import time
from pathlib import Path

from agents.constants import PRESETS_DIR


def _make_definition(key: str) -> dict:
    return {
        "agent_key": key,
        "name": f"Agent {key}",
        "role": "tester",
        "goal": "test",
        "backstory": "benchmark agent",
        "focus": "bench",
        "domain": "quality",
        "tools": [],
        "complexity": "medium",
    }


def _make_preset(name: str, agent_count: int = 3) -> dict:
    return {
        "name": name,
        "description": f"Benchmark preset {name}",
        "domain": "quality",
        "size": "standard",
        "version": "1.0.0",
        "agents": [_make_definition(f"{name}-agent-{i}") for i in range(agent_count)],
    }


def bench_export():
    """Benchmark exporting 50 definitions + 10 presets."""
    import agents.packaging as pkg_mod

    tmpdir = Path(tempfile.mkdtemp())
    old_defs = pkg_mod.DEFINITIONS_DIR
    old_presets = pkg_mod.PRESETS_DIR
    pkg_mod.DEFINITIONS_DIR = tmpdir / "definitions"
    pkg_mod.PRESETS_DIR = tmpdir / "presets"
    pkg_mod.DEFINITIONS_DIR.mkdir(parents=True)
    pkg_mod.PRESETS_DIR.mkdir(parents=True)

    try:
        # Create files
        def_keys = []
        for i in range(50):
            key = f"bench-def-{i:03d}"
            (pkg_mod.DEFINITIONS_DIR / f"{key}.json").write_text(
                json.dumps(_make_definition(key))
            )
            def_keys.append(key)

        preset_names = []
        for i in range(10):
            name = f"bench-preset-{i:02d}"
            (pkg_mod.PRESETS_DIR / f"{name}.json").write_text(
                json.dumps(_make_preset(name))
            )
            preset_names.append(name)

        # Benchmark export
        iterations = 10
        start = time.monotonic()
        for _ in range(iterations):
            data = pkg_mod.export_package(
                "bench-bundle",
                definition_keys=def_keys,
                preset_names=preset_names,
            )
        elapsed = time.monotonic() - start

        avg_ms = (elapsed / iterations) * 1000
        size_kb = len(data) / 1024
        print(f"  Export 50 defs + 10 presets: {avg_ms:.1f} ms, {size_kb:.1f} KB")

        return data
    finally:
        pkg_mod.DEFINITIONS_DIR = old_defs
        pkg_mod.PRESETS_DIR = old_presets
        shutil.rmtree(tmpdir)


def bench_import():
    """Benchmark importing a large bundle."""
    import agents.packaging as pkg_mod

    # Create a bundle to import
    tmpdir = Path(tempfile.mkdtemp())
    old_defs = pkg_mod.DEFINITIONS_DIR
    old_presets = pkg_mod.PRESETS_DIR
    pkg_mod.DEFINITIONS_DIR = tmpdir / "src_defs"
    pkg_mod.PRESETS_DIR = tmpdir / "src_presets"
    pkg_mod.DEFINITIONS_DIR.mkdir(parents=True)
    pkg_mod.PRESETS_DIR.mkdir(parents=True)

    try:
        def_keys = []
        for i in range(50):
            key = f"import-def-{i:03d}"
            (pkg_mod.DEFINITIONS_DIR / f"{key}.json").write_text(
                json.dumps(_make_definition(key))
            )
            def_keys.append(key)

        preset_names = []
        for i in range(10):
            name = f"import-preset-{i:02d}"
            (pkg_mod.PRESETS_DIR / f"{name}.json").write_text(
                json.dumps(_make_preset(name))
            )
            preset_names.append(name)

        bundle = pkg_mod.export_package(
            "import-bench", definition_keys=def_keys, preset_names=preset_names
        )

        # Now import into a clean target
        target = tmpdir / "target"
        pkg_mod.DEFINITIONS_DIR = target / "definitions"
        pkg_mod.PRESETS_DIR = target / "presets"

        iterations = 10
        start = time.monotonic()
        for _ in range(iterations):
            # Clean target each time
            if (target / "definitions").exists():
                shutil.rmtree(target / "definitions")
            if (target / "presets").exists():
                shutil.rmtree(target / "presets")
            result = pkg_mod.import_package(bundle, overwrite=True)
            assert not result["errors"], result["errors"]
        elapsed = time.monotonic() - start

        avg_ms = (elapsed / iterations) * 1000
        print(
            f"  Import 50 defs + 10 presets: {avg_ms:.1f} ms, "
            f"{len(result['definitions_installed'])} defs, "
            f"{len(result['presets_installed'])} presets"
        )
    finally:
        pkg_mod.DEFINITIONS_DIR = old_defs
        pkg_mod.PRESETS_DIR = old_presets
        shutil.rmtree(tmpdir)


if __name__ == "__main__":
    print("=" * 60)
    print("Benchmark: Package Import/Export")
    print("=" * 60)
    print()
    bench_export()
    bench_import()
    print()
