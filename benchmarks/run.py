#!/usr/bin/env python3
"""Standalone benchmark CLI — run without pytest if preferred.

Usage:
    .venv/bin/python -m benchmarks.run [OPTIONS]

Options (via env vars or CLI):
    CREWAI_BENCH_URL    default http://localhost:8000
    AGNOSAI_BENCH_URL   default http://localhost:8080
    OLLAMA_URL          default http://localhost:11434
    OLLAMA_MODEL        default qwen2.5:1.5b
    BENCH_ROUNDS        default 5
    AGNOSTIC_API_KEY    default ""
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from benchmarks.report import build_report, render_markdown, save_json
from benchmarks.runner import (
    check_health,
    check_ollama,
    pull_ollama_model,
    run_scenario,
)
from benchmarks.scenarios import build_scenarios

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
)
logger = logging.getLogger(__name__)


async def main(args: argparse.Namespace) -> int:
    # ── Preflight ────────────────────────────────────────────────────
    logger.info("Checking Ollama at %s for model %s...", args.ollama_url, args.model)
    if not await check_ollama(args.ollama_url, args.model):
        logger.info("Model not found — pulling...")
        if not await pull_ollama_model(args.ollama_url, args.model):
            logger.error("Cannot pull model %s — aborting.", args.model)
            return 1

    crewai_ok = await check_health(args.crewai_url)
    agnosai_ok = await check_health(args.agnosai_url)
    if not crewai_ok and not agnosai_ok:
        logger.error("Neither backend is reachable — aborting.")
        return 1

    backends: list[tuple[str, str]] = []
    if crewai_ok:
        logger.info("CrewAI backend: %s", args.crewai_url)
        backends.append(("crewai", args.crewai_url))
    else:
        logger.warning("CrewAI backend not reachable — skipping.")
    if agnosai_ok:
        logger.info("AgnosAI backend: %s", args.agnosai_url)
        backends.append(("agnosai", args.agnosai_url))
    else:
        logger.warning("AgnosAI backend not reachable — skipping.")

    scenarios = build_scenarios(args.model)
    all_results = []

    for backend, url in backends:
        for sc in scenarios:
            results = await run_scenario(
                backend=backend,
                base_url=url,
                crew_config=sc.crew_config,
                scenario_name=sc.name,
                rounds=args.rounds,
                api_key=args.api_key,
            )
            all_results.extend(results)

    # ── Report ───────────────────────────────────────────────────────
    report = build_report(
        all_results,
        metadata={"ollama_model": args.model, "bench_rounds": args.rounds},
    )
    out = Path("benchmark-results")
    save_json(report, out / "latest.json")
    md = render_markdown(report)
    (out / "latest.md").write_text(md)
    print(md)
    logger.info("Results saved to %s/", out)
    return 0


def cli() -> None:
    p = argparse.ArgumentParser(description="CrewAI vs AgnosAI benchmark runner")
    p.add_argument("--crewai-url", default="http://localhost:8000")
    p.add_argument("--agnosai-url", default="http://localhost:8080")
    p.add_argument("--ollama-url", default="http://localhost:11434")
    p.add_argument("--model", default="qwen2.5:1.5b", help="Ollama model name")
    p.add_argument("--rounds", type=int, default=5, help="Rounds per scenario")
    p.add_argument("--api-key", default="", help="API key for both servers")
    args = p.parse_args()
    sys.exit(asyncio.run(main(args)))


if __name__ == "__main__":
    cli()
