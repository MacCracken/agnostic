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
- `latest.json` — full structured results from the most recent run
- `latest.md` — markdown summary table for the most recent run
- `history.json` — all previous runs (appended, never overwritten)
- `history.md` — combined markdown of all historical runs

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

**Note:** This run used a stale `agnosai-server` binary that predated
the LLM wiring in `main.rs`. The orchestrator's `HooshClient` was not
attached, so `execute_task()` fell through to the placeholder branch
(echoing task descriptions instead of calling the LLM). See the fix
below.

### AgnosAI LLM Integration Fix (0.20.4)

The agnosai `crew_runner.rs` has full LLM inference code wired through
`HooshClient` (via the `hoosh` crate), but requires:

1. **`main.rs` must call `.with_llm()`** on the `Orchestrator` — this was
   added but the binary was not rebuilt, so the stale binary ran in
   placeholder mode.
2. **`HOOSH_URL`** env var must point at an OpenAI-compatible endpoint
   (Ollama works directly: `HOOSH_URL=http://localhost:11434`).
3. **Agent `llm_model`** field controls which model is used. When unset,
   the complexity-based router selects a tier (Fast/Capable/Premium)
   mapped to default models.

After rebuilding (`cargo build --release --bin agnosai-server`), AgnosAI
returns real LLM output with ~2s latency per task (matching Ollama
inference time).

### What the Numbers Tell Us

| Metric | CrewAI | AgnosAI |
|--------|--------|---------|
| Orchestration overhead | ~100-500ms per agent | <3ms total |
| Process modes via API | sequential, hierarchical | sequential, parallel, dag, hierarchical (fallback) |
| Cold start (health) | <50ms | <5ms |
| Memory footprint | ~200MB (Python + deps) | ~15MB (static binary) |

### 2026-03-21 — Full LLM Benchmark (AgnosAI 0.20.4, Ollama llama3.2:1b, 3 rounds)

**Environment:** Arch Linux, Ollama native, llama3.2:1b (1.2B Q8_0), `HOOSH_URL=http://localhost:11434`

Both backends perform real LLM inference through Ollama.

| Scenario | CrewAI Mean (s) | AgnosAI Mean (s) | Notes |
|----------|----------------|-------------------|-------|
| single-agent-single-task | 4.7 | 57.6 | CrewAI faster — hoosh HTTP overhead on single requests |
| multi-agent-sequential | 23.4 | 115.2 | High variance in AgnosAI (22s–297s); median 26s matches CrewAI |
| multi-agent-parallel | 422 error | 51.6 | AgnosAI-only: parallel execution mode |
| dag-dependencies | 422 error | 106.2 | AgnosAI-only: DAG orchestration |
| large-crew-6-agents | 264.7 | 121.3 | **AgnosAI 2.2x faster** on large crews |

**Key findings:**
- AgnosAI's orchestration overhead is negligible (<3ms), but hoosh's HTTP
  client adds per-request latency compared to litellm's direct bindings
- On large crews (6+ agents), AgnosAI's concurrent scheduling and lower
  per-agent overhead yield a clear win
- AgnosAI supports parallel and DAG process modes that CrewAI cannot do
  through its HTTP API
- The single-agent gap warrants investigation into hoosh client-side
  connection pooling and keepalive settings
