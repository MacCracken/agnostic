"""Benchmark runner — drives identical workloads against both backends.

Collects wall-clock latency, HTTP overhead, and memory snapshots so the
results can be compared apples-to-apples.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# How long to wait for an async crew to finish (seconds).
_POLL_INTERVAL = 2.0
_POLL_TIMEOUT = 300.0


@dataclass
class RunResult:
    """Timing + metadata for a single benchmark run."""

    backend: str
    scenario: str
    round_num: int
    wall_secs: float
    status: str
    http_status: int = 0
    error: str | None = None
    response_body: dict[str, Any] = field(default_factory=dict)


async def check_health(base_url: str, *, timeout: float = 5.0) -> bool:
    """Return True if the server's /health endpoint responds 200."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(f"{base_url}/health")
            return resp.status_code == 200
    except httpx.RequestError:
        return False


async def check_ollama(ollama_url: str, model: str, *, timeout: float = 10.0) -> bool:
    """Return True if Ollama is reachable and the model is available."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(f"{ollama_url}/api/tags")
            if resp.status_code != 200:
                return False
            tags = resp.json()
            available = [m.get("name", "") for m in tags.get("models", [])]
            # Model names may have :latest suffix.
            return any(model in name for name in available)
    except httpx.RequestError:
        return False


async def pull_ollama_model(
    ollama_url: str, model: str, *, timeout: float = 600.0
) -> bool:
    """Pull a model into Ollama. Returns True on success."""
    logger.info("Pulling Ollama model %s (this may take a while)...", model)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{ollama_url}/api/pull",
                json={"name": model, "stream": False},
            )
            return resp.status_code == 200
    except httpx.RequestError as exc:
        logger.error("Failed to pull model: %s", exc)
        return False


def _crewai_payload(crew_config: dict[str, Any]) -> dict[str, Any]:
    """Shape the payload for the Agnostic /api/v1/crews endpoint."""
    return {
        "agent_definitions": crew_config["agents"],
        "title": crew_config.get("name", "benchmark"),
        "description": crew_config["tasks"][0]["description"],
        "tasks": crew_config.get("tasks"),
        "process": crew_config.get("process", "sequential"),
    }


def _agnosai_payload(crew_config: dict[str, Any]) -> dict[str, Any]:
    """Shape the payload for the AgnosAI /api/v1/crews endpoint."""
    return {
        "name": crew_config.get("name", "benchmark"),
        "agents": crew_config["agents"],
        "tasks": crew_config["tasks"],
        "process": crew_config.get("process", "sequential"),
    }


async def _poll_crewai(
    client: httpx.AsyncClient,
    base_url: str,
    crew_id: str,
    headers: dict[str, str],
) -> dict[str, Any]:
    """Poll the CrewAI status endpoint until the crew finishes or times out."""
    deadline = time.perf_counter() + _POLL_TIMEOUT
    while time.perf_counter() < deadline:
        await asyncio.sleep(_POLL_INTERVAL)
        try:
            resp = await client.get(
                f"{base_url}/api/v1/crews/{crew_id}", headers=headers
            )
            if resp.status_code != 200:
                continue
            data = resp.json()
            status = data.get("status", "")
            if status in ("completed", "failed", "partial", "error"):
                return data
        except httpx.RequestError:
            continue
    return {"status": "timeout", "error": "Crew did not finish within poll timeout"}


async def _run_one(
    client: httpx.AsyncClient,
    backend: str,
    base_url: str,
    crew_config: dict[str, Any],
    scenario_name: str,
    round_num: int,
    api_key: str,
) -> RunResult:
    """Submit a crew and wait for the result."""
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key

    if backend == "crewai":
        url = f"{base_url}/api/v1/crews"
        payload = _crewai_payload(crew_config)
    else:
        url = f"{base_url}/api/v1/crews"
        payload = _agnosai_payload(crew_config)

    t0 = time.perf_counter()
    try:
        resp = await client.post(url, json=payload, headers=headers)

        if resp.status_code >= 400:
            wall = time.perf_counter() - t0
            body = resp.json() if resp.status_code < 500 else {}
            return RunResult(
                backend=backend,
                scenario=scenario_name,
                round_num=round_num,
                wall_secs=wall,
                status="error",
                http_status=resp.status_code,
                error=f"HTTP {resp.status_code}: {body.get('detail', resp.text[:200])}",
                response_body=body,
            )

        body = resp.json()
        status = body.get("status", "unknown")

        # CrewAI returns "pending" — we need to poll until done.
        if status == "pending" and backend == "crewai":
            crew_id = body.get("crew_id", "")
            if crew_id:
                logger.info("  polling crew %s...", crew_id[:12])
                final = await _poll_crewai(client, base_url, crew_id, headers)
                status = final.get("status", "unknown")
                body = final

        wall = time.perf_counter() - t0
        return RunResult(
            backend=backend,
            scenario=scenario_name,
            round_num=round_num,
            wall_secs=wall,
            status=status,
            http_status=resp.status_code,
            response_body=body,
        )
    except httpx.RequestError as exc:
        wall = time.perf_counter() - t0
        return RunResult(
            backend=backend,
            scenario=scenario_name,
            round_num=round_num,
            wall_secs=wall,
            status="error",
            error=str(exc),
        )


async def run_scenario(
    backend: str,
    base_url: str,
    crew_config: dict[str, Any],
    scenario_name: str,
    rounds: int,
    api_key: str = "",
    timeout: float = 600.0,
) -> list[RunResult]:
    """Run a scenario N times against one backend and collect results."""
    results: list[RunResult] = []
    async with httpx.AsyncClient(timeout=timeout) as client:
        for r in range(rounds):
            logger.info("[%s] %s  round %d/%d", backend, scenario_name, r + 1, rounds)
            result = await _run_one(
                client, backend, base_url, crew_config, scenario_name, r + 1, api_key
            )
            results.append(result)
            logger.info("  -> %s in %.2fs", result.status, result.wall_secs)
            # Small pause between rounds to avoid hammering Ollama.
            if r < rounds - 1:
                await asyncio.sleep(1.0)
    return results
