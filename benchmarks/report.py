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
        scenarios.append(
            {
                "backend": backend,
                "scenario": scenario,
                "rounds": len(runs),
                "success_count": success,
                "failure_count": len(runs) - success,
                "latency": _stats(times),
            }
        )

    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "metadata": metadata or {},
        "scenarios": scenarios,
    }
    return report


def save_json(report: dict[str, Any], path: Path) -> None:
    """Write the report to a JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n")


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
