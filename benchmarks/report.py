"""Benchmark report generation.

Produces a JSON results file and a human-readable markdown summary table.
"""

from __future__ import annotations

import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from benchmarks.runner import RunResult


def _stats(values: list[float]) -> dict[str, float]:
    """Return min/max/mean/median/stdev for a list of floats."""
    if not values:
        return {"min": 0, "max": 0, "mean": 0, "median": 0, "stdev": 0}
    s: dict[str, float] = {
        "min": min(values),
        "max": max(values),
        "mean": statistics.mean(values),
        "median": statistics.median(values),
    }
    s["stdev"] = statistics.stdev(values) if len(values) > 1 else 0.0
    return s


def build_report(
    results: list[RunResult], metadata: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Aggregate raw results into a structured report."""
    # Group by (backend, scenario).
    groups: dict[tuple[str, str], list[RunResult]] = {}
    for r in results:
        key = (r.backend, r.scenario)
        groups.setdefault(key, []).append(r)

    scenarios: list[dict[str, Any]] = []
    for (backend, scenario), runs in sorted(groups.items()):
        times = [r.wall_secs for r in runs if r.status != "error"]
        success = sum(1 for r in runs if r.status not in ("error", "failed"))
        entry: dict[str, Any] = {
            "backend": backend,
            "scenario": scenario,
            "rounds": len(runs),
            "success_count": success,
            "failure_count": len(runs) - success,
            "latency": _stats(times),
        }
        # Server-side profiling (AgnosAI 0.21.3+)
        profiled = [r for r in runs if r.profile_wall_ms > 0]
        if profiled:
            server_ms = [r.profile_wall_ms for r in profiled]
            entry["profile"] = {
                "server_wall_ms": _stats([float(v) for v in server_ms]),
                "task_count": profiled[0].profile_task_count,
                "cost_usd": sum(r.profile_cost_usd for r in profiled) / len(profiled),
                "overhead_ms": _stats(
                    [r.wall_secs * 1000 - r.profile_wall_ms for r in profiled]
                ),
            }
        scenarios.append(entry)

    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "metadata": metadata or {},
        "scenarios": scenarios,
    }
    return report


def save_json(report: dict[str, Any], path: Path) -> None:
    """Write the report to a JSON file, archiving previous runs.

    Previous results are preserved under a ``runs`` list in a combined
    ``history.json`` file in the same directory.  The ``latest.json``
    file is always overwritten with the most recent run.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n")

    # Append to history
    history_path = path.parent / "history.json"
    history: list[dict[str, Any]] = []
    if history_path.exists():
        try:
            history = json.loads(history_path.read_text())
        except (json.JSONDecodeError, ValueError):
            history = []
    history.append(report)
    history_path.write_text(json.dumps(history, indent=2) + "\n")


def render_markdown(report: dict[str, Any]) -> str:
    """Render the report as a markdown table for terminal / CI output."""
    lines: list[str] = []
    lines.append("# Benchmark Results")
    lines.append("")
    lines.append(f"Generated: {report['generated_at']}")
    if report.get("metadata"):
        meta = report["metadata"]
        if "ollama_model" in meta:
            lines.append(f"LLM: Ollama `{meta['ollama_model']}`")
        if "bench_rounds" in meta:
            lines.append(f"Rounds per scenario: {meta['bench_rounds']}")
    lines.append("")

    # Header
    lines.append(
        "| Scenario | Backend | Rounds | OK | Fail "
        "| Mean (s) | Median (s) | Min (s) | Max (s) | StdDev |"
    )
    lines.append(
        "|----------|---------|--------|----|------"
        "|----------|------------|---------|---------|--------|"
    )

    for s in report["scenarios"]:
        lat = s["latency"]
        lines.append(
            f"| {s['scenario']} | {s['backend']} | {s['rounds']} "
            f"| {s['success_count']} | {s['failure_count']} "
            f"| {lat['mean']:.3f} | {lat['median']:.3f} "
            f"| {lat['min']:.3f} | {lat['max']:.3f} | {lat['stdev']:.3f} |"
        )

    # Server-side profiling section (AgnosAI 0.21.3+)
    profiled = [s for s in report["scenarios"] if "profile" in s]
    if profiled:
        lines.append("")
        lines.append("## Server-Side Profiling (AgnosAI 0.21.3+)")
        lines.append("")
        lines.append(
            "| Scenario | Backend | Server Wall (ms) "
            "| HTTP Overhead (ms) | Tasks | Avg Cost (USD) |"
        )
        lines.append(
            "|----------|---------|-------------------"
            "|--------------------|-------|----------------|"
        )
        for s in profiled:
            p = s["profile"]
            sw = p["server_wall_ms"]
            oh = p["overhead_ms"]
            lines.append(
                f"| {s['scenario']} | {s['backend']} "
                f"| {sw['mean']:.1f} "
                f"| {oh['mean']:.1f} "
                f"| {p['task_count']} "
                f"| {p['cost_usd']:.4f} |"
            )

    # Comparison section — pair up same-scenario across backends.
    crewai = {s["scenario"]: s for s in report["scenarios"] if s["backend"] == "crewai"}
    agnosai = {
        s["scenario"]: s for s in report["scenarios"] if s["backend"] == "agnosai"
    }
    common = sorted(set(crewai) & set(agnosai))

    if common:
        lines.append("")
        lines.append("## Head-to-Head Comparison")
        lines.append("")
        lines.append("| Scenario | CrewAI Mean (s) | AgnosAI Mean (s) | Speedup |")
        lines.append("|----------|-----------------|------------------|---------|")
        for name in common:
            c_mean = crewai[name]["latency"]["mean"]
            a_mean = agnosai[name]["latency"]["mean"]
            if a_mean > 0:
                speedup = c_mean / a_mean
                lines.append(
                    f"| {name} | {c_mean:.3f} | {a_mean:.3f} | {speedup:.2f}x |"
                )
            else:
                lines.append(f"| {name} | {c_mean:.3f} | {a_mean:.3f} | N/A |")

    lines.append("")
    return "\n".join(lines)


def render_history_markdown(history_path: Path) -> str:
    """Render all historical runs as a combined markdown document."""
    if not history_path.exists():
        return ""
    try:
        runs: list[dict[str, Any]] = json.loads(history_path.read_text())
    except (json.JSONDecodeError, ValueError):
        return ""

    sections: list[str] = ["# Benchmark History", ""]
    for i, run in enumerate(runs, 1):
        sections.append(f"## Run {i} — {run.get('generated_at', 'unknown')}")
        meta = run.get("metadata", {})
        if meta.get("ollama_model"):
            sections.append(f"LLM: Ollama `{meta['ollama_model']}`")
        if meta.get("bench_rounds"):
            sections.append(f"Rounds: {meta['bench_rounds']}")
        sections.append("")

        # Per-scenario table
        sections.append("| Scenario | Backend | OK/Total | Mean (s) | Median (s) |")
        sections.append("|----------|---------|----------|----------|------------|")
        for s in run.get("scenarios", []):
            lat = s["latency"]
            sections.append(
                f"| {s['scenario']} | {s['backend']} "
                f"| {s['success_count']}/{s['rounds']} "
                f"| {lat['mean']:.3f} | {lat['median']:.3f} |"
            )
        sections.append("")
    return "\n".join(sections)
