"""Benchmark tests: CrewAI vs AgnosAI.

Run with:
    .venv/bin/python -m pytest benchmarks/ -v --tb=short

Prerequisites:
    - Agnostic (CrewAI) server running at CREWAI_BENCH_URL  (default :8000)
    - AgnosAI (Rust)  server running at AGNOSAI_BENCH_URL   (default :8080)
    - Ollama running at OLLAMA_URL with OLLAMA_MODEL pulled  (default :11434)

Quick start with docker compose:
    docker compose --profile agnosai --profile benchmark up -d
    .venv/bin/python -m pytest benchmarks/ -v
"""

from __future__ import annotations

import asyncio
import logging

import pytest

from benchmarks.report import (
    build_report,
    render_history_markdown,
    render_markdown,
    save_json,
)
from benchmarks.runner import (
    RunResult,
    check_health,
    check_ollama,
    pull_ollama_model,
    run_scenario,
)
from benchmarks.scenarios import build_scenarios

logger = logging.getLogger(__name__)

# Collect results across all tests for the final report.
_ALL_RESULTS: list[RunResult] = []


# ── Precondition checks ─────────────────────────────────────────────────


@pytest.fixture(scope="session", autouse=True)
def _ensure_ollama(ollama_url: str, ollama_model: str) -> None:
    """Ensure Ollama is running and the model is available."""
    available = asyncio.run(check_ollama(ollama_url, ollama_model))
    if not available:
        logger.info("Model %s not found — attempting pull...", ollama_model)
        pulled = asyncio.run(pull_ollama_model(ollama_url, ollama_model))
        if not pulled:
            pytest.skip(f"Ollama model {ollama_model} unavailable at {ollama_url}")


def _skip_unless_healthy(url: str, name: str) -> None:
    if not asyncio.run(check_health(url)):
        pytest.skip(f"{name} server not reachable at {url}")


# ── Parametrised benchmarks ─────────────────────────────────────────────


def _scenario_ids() -> list[str]:
    """Generate test IDs from scenario names (use a dummy model)."""
    return [s.name for s in build_scenarios("dummy")]


def _run_bench(
    backend: str,
    base_url: str,
    scenario_idx: int,
    ollama_model: str,
    bench_rounds: int,
    api_key: str,
) -> list[RunResult]:
    scenarios = build_scenarios(ollama_model)
    sc = scenarios[scenario_idx]
    results = asyncio.run(
        run_scenario(
            backend=backend,
            base_url=base_url,
            crew_config=sc.crew_config,
            scenario_name=sc.name,
            rounds=bench_rounds,
            api_key=api_key,
        )
    )
    _ALL_RESULTS.extend(results)
    return results


# ── CrewAI benchmarks ───────────────────────────────────────────────────


@pytest.mark.benchmark
class TestCrewAI:
    """Benchmark scenarios against the CrewAI (Python) backend."""

    @pytest.fixture(autouse=True)
    def _check(self, crewai_url: str) -> None:
        _skip_unless_healthy(crewai_url, "CrewAI")

    @pytest.mark.parametrize("scenario_idx", range(5), ids=_scenario_ids())
    def test_scenario(
        self,
        scenario_idx: int,
        crewai_url: str,
        ollama_model: str,
        bench_rounds: int,
        api_key: str,
    ) -> None:
        results = _run_bench(
            "crewai", crewai_url, scenario_idx, ollama_model, bench_rounds, api_key
        )
        failed = [r for r in results if r.status in ("error", "failed")]
        assert len(failed) < len(results), (
            f"All {len(results)} rounds failed for CrewAI"
        )


# ── AgnosAI benchmarks ──────────────────────────────────────────────────


@pytest.mark.benchmark
class TestAgnosAI:
    """Benchmark scenarios against the AgnosAI (Rust) backend."""

    @pytest.fixture(autouse=True)
    def _check(self, agnosai_url: str) -> None:
        _skip_unless_healthy(agnosai_url, "AgnosAI")

    @pytest.mark.parametrize("scenario_idx", range(5), ids=_scenario_ids())
    def test_scenario(
        self,
        scenario_idx: int,
        agnosai_url: str,
        ollama_model: str,
        bench_rounds: int,
        api_key: str,
    ) -> None:
        results = _run_bench(
            "agnosai", agnosai_url, scenario_idx, ollama_model, bench_rounds, api_key
        )
        failed = [r for r in results if r.status in ("error", "failed")]
        assert len(failed) < len(results), (
            f"All {len(results)} rounds failed for AgnosAI"
        )


# ── Cold-start benchmark ────────────────────────────────────────────────


@pytest.mark.benchmark
class TestColdStart:
    """Measure server health-check response time as a cold-start proxy."""

    def test_crewai_health_latency(self, crewai_url: str) -> None:
        import time

        import httpx

        times = []
        for _ in range(10):
            t0 = time.perf_counter()
            try:
                httpx.get(f"{crewai_url}/health", timeout=5)
            except httpx.RequestError:
                pytest.skip("CrewAI not reachable")
            times.append(time.perf_counter() - t0)

        avg = sum(times) / len(times)
        logger.info("CrewAI /health avg: %.4fs", avg)
        assert avg < 5.0, f"CrewAI health too slow: {avg:.3f}s"

    def test_agnosai_health_latency(self, agnosai_url: str) -> None:
        import time

        import httpx

        times = []
        for _ in range(10):
            t0 = time.perf_counter()
            try:
                httpx.get(f"{agnosai_url}/health", timeout=5)
            except httpx.RequestError:
                pytest.skip("AgnosAI not reachable")
            times.append(time.perf_counter() - t0)

        avg = sum(times) / len(times)
        logger.info("AgnosAI /health avg: %.4fs", avg)
        assert avg < 5.0, f"AgnosAI health too slow: {avg:.3f}s"


# ── Report generation (runs after all tests) ────────────────────────────


@pytest.fixture(scope="session", autouse=True)
def _generate_report(
    request: pytest.FixtureRequest,
    ollama_model: str,
    bench_rounds: int,
) -> None:  # noqa: ANN401
    """Write the aggregate report after all benchmarks complete."""

    def _finalizer() -> None:
        if not _ALL_RESULTS:
            return
        from pathlib import Path

        report = build_report(
            _ALL_RESULTS,
            metadata={
                "ollama_model": ollama_model,
                "bench_rounds": bench_rounds,
            },
        )
        out_dir = Path("benchmark-results")
        save_json(report, out_dir / "latest.json")

        md = render_markdown(report)
        (out_dir / "latest.md").write_text(md)
        print("\n" + md)

        # Write combined history markdown
        history_md = render_history_markdown(out_dir / "history.json")
        if history_md:
            (out_dir / "history.md").write_text(history_md)
            print("\n" + history_md)

    request.addfinalizer(_finalizer)
