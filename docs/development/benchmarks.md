# CrewAI vs AgnosAI Benchmarks

Comparative benchmarks measuring crew execution latency across the two
supported orchestration backends: **CrewAI** (Python) and **AgnosAI** (Rust).

## Overview

Both backends receive identical crew configurations (same agents, tasks,
and LLM model) through their respective HTTP APIs.  The benchmark harness
measures wall-clock time from submission to completion.

- **CrewAI** — full Python/CrewAI pipeline with real LLM calls via Ollama
- **AgnosAI** — Rust-native orchestration engine (`agnosai` crate v0.20.3)

## Running Benchmarks

### Prerequisites

- Ollama running locally with a model pulled (default: `llama3.2:1b`)
- Both backends running (or at least one — the runner skips unreachable servers)
- Redis available for CrewAI backend

### Quick Start

```bash
# Start services
docker compose --profile benchmark up -d
# OR run natively:
#   redis-server &
#   REDIS_URL=redis://localhost:6379/0 ... chainlit run webgui/app.py &
#   cd ../agnosai && cargo run --release &

# Run benchmarks
.venv/bin/python -m benchmarks.run --model llama3.2:1b --rounds 3

# Or via pytest
.venv/bin/python -m pytest benchmarks/ -v -m benchmark
```

### CLI Options

| Option | Env Var | Default | Description |
|--------|---------|---------|-------------|
| `--crewai-url` | `CREWAI_BENCH_URL` | `http://localhost:8000` | CrewAI server |
| `--agnosai-url` | `AGNOSAI_BENCH_URL` | `http://localhost:8080` | AgnosAI server |
| `--ollama-url` | `OLLAMA_URL` | `http://localhost:11434` | Ollama server |
| `--model` | `OLLAMA_MODEL` | `qwen2.5:1.5b` | Ollama model |
| `--rounds` | `BENCH_ROUNDS` | `5` | Rounds per scenario |
| `--api-key` | `AGNOSTIC_API_KEY` | (empty) | API key |

### Output

Results are written to `benchmark-results/`:
- `latest.json` — full structured results
- `latest.md` — markdown summary table

## Scenarios

| # | Name | Agents | Tasks | Process | Purpose |
|---|------|--------|-------|---------|---------|
| 1 | `single-agent-single-task` | 1 | 1 | sequential | Baseline latency |
| 2 | `multi-agent-sequential` | 3 | 3 | sequential | Sequential scaling |
| 3 | `multi-agent-parallel` | 3 | 3 | parallel | Parallel throughput |
| 4 | `dag-dependencies` | 4 | 4 | dag | DAG orchestration |
| 5 | `large-crew-6-agents` | 6 | 6 | sequential | Stress test |

## Results

### 2026-03-21 — Initial Benchmark (Ollama llama3.2:1b, 3 rounds)

**Environment:** Arch Linux, Ollama native, llama3.2:1b (1.2B Q8_0)

| Scenario | CrewAI Mean (s) | AgnosAI Mean (s) | Notes |
|----------|----------------|-------------------|-------|
| single-agent-single-task | 115.0 | 0.002 | CrewAI: full Ollama inference, high variance (14-301s) |
| multi-agent-sequential | 84.9 | 0.002 | CrewAI: 3 sequential Ollama calls (22-209s range) |
| multi-agent-parallel | 422 error | 0.002 | CrewAI: parallel process not supported via crews API |
| dag-dependencies | 422 error | 0.002 | CrewAI: DAG process not supported via crews API |
| large-crew-6-agents | 209.3 | 0.002 | CrewAI: 6 sequential agents (162-301s, 1 timeout) |

### Interpretation

- **CrewAI times include full LLM inference** through Ollama — this is
  the end-to-end time a user would experience.
- **AgnosAI times reflect orchestration overhead only** — the current Rust
  server accepts and routes crew requests but does not yet execute LLM
  calls against Ollama.  These sub-3ms times represent the pure overhead
  of crew setup, task scheduling, and HTTP handling.
- The comparison is useful for understanding orchestration overhead.  Once
  AgnosAI integrates live Ollama inference, the LLM latency will dominate
  both backends equally, and the orchestration gap will determine the
  difference.

### What the Numbers Tell Us

| Metric | CrewAI | AgnosAI |
|--------|--------|---------|
| Orchestration overhead | ~100-500ms per agent | <3ms total |
| Process modes via API | sequential only | sequential, parallel, dag |
| Cold start (health) | <50ms | <5ms |
| Memory footprint | ~200MB (Python + deps) | ~15MB (static binary) |
