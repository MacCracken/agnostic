# CrewAI vs AgnosAI Benchmarks

Comparative benchmarks measuring crew execution latency across the two
supported orchestration backends: **CrewAI** (Python) and **AgnosAI** (Rust).

## Overview

Both backends receive identical crew configurations (same agents, tasks,
and LLM model) through their respective HTTP APIs.  The benchmark harness
measures wall-clock time from submission to completion.

- **CrewAI** — full Python/CrewAI pipeline with real LLM calls via Ollama
- **AgnosAI** — Rust-native orchestration engine (`agnosai` crate v0.21.3+)

The full inference chain:

```
Agnostic (Python/CrewAI) ──HTTP──▶ Ollama (via litellm)
AgnosAI (Rust)           ──HTTP──▶ hoosh client ──▶ Ollama (/v1/chat/completions)
                                   ↕
                                 majra (queue/multiplex/fleet)
```

## Setup

### Prerequisites

- **Ollama** running locally with a model pulled
- **Redis** running locally (CrewAI backend stores crew state in Redis)
- **Docker** for building container images
- Python `.venv` with benchmark deps (`httpx`)

### 1. Verify Ollama

```bash
# Check Ollama is running and has a model
curl -s http://localhost:11434/api/tags | python3 -c "import sys,json; print([m['name'] for m in json.load(sys.stdin)['models']])"

# Pull a model if needed
ollama pull llama3.2:1b

# Verify the OpenAI-compatible endpoint works (AgnosAI uses this)
curl -s http://localhost:11434/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"llama3.2:1b","messages":[{"role":"user","content":"hi"}],"max_tokens":5}'
```

**Important:** Ollama must be accessible from Docker containers. If using
`--network host`, Ollama's default `127.0.0.1` binding works fine. If using
bridge networking, either:
- Set `OLLAMA_HOST=0.0.0.0` in the Ollama systemd service and restart, or
- Use `--add-host host.docker.internal:host-gateway` and point URLs at
  `http://host.docker.internal:11434`

### 2. Verify Redis

```bash
# Check Redis is running on localhost
ss -tlnp | grep 6379
# Should show: LISTEN ... 127.0.0.1:6379
```

Redis is needed by the CrewAI backend for crew state storage.

### 3. Build Docker Images

```bash
# Build the Agnostic (Python/CrewAI) image
docker compose build agnostic

# Build the AgnosAI (Rust) image — first build takes several minutes
docker compose --profile benchmark build agnosai-server
```

### 4. Start Benchmark Containers

#### Option A: Docker Compose (recommended)

Start both backends plus a dedicated Ollama container on the same Docker
network. Select the Ollama profile matching your GPU hardware:

```bash
# NVIDIA (default — uses nvidia container runtime)
docker compose --profile benchmark up -d

# AMD ROCm (passes /dev/kfd + /dev/dri, uses ollama:rocm image)
docker compose --profile benchmark --profile ollama-amd up -d

# Vulkan (AMD/Intel iGPU — passes /dev/dri, sets OLLAMA_VULKAN=true)
docker compose --profile benchmark --profile ollama-vulkan up -d

# CPU only (no GPU passthrough)
docker compose --profile benchmark --profile ollama-cpu up -d
```

All Ollama variants register with the network alias `ollama`, so AgnosAI
and CrewAI reach them at `http://ollama:11434` without config changes.

**Known gotchas with Docker Compose:**

| Issue | Cause | Solution |
|-------|-------|----------|
| Ollama port 11434 in use | Host Ollama (systemd) is running | Stop it (`sudo systemctl stop ollama`) or use `OLLAMA_PORT=11435` to map to an alternate host port |
| Port 443/80 in use | Other services on the host | Set `TLS_HTTPS_PORT=8443 TLS_HTTP_PORT=8880` |
| Redis port 6379 in use | Host Redis running; compose Redis tries to bind same port | Start Redis manually without host port: `docker run -d --name agnostic-redis-1 --network agnostic_qa-network --network-alias redis redis:7-alpine` |
| CrewAI `PermissionError: /data/caddy/app` | Caddy sets `XDG_DATA_HOME=/data/caddy`; CrewAI's ChromaDB storage inherits it and can't write | Fixed in compose: `XDG_DATA_HOME` overridden to `/home/agnostic/.local/share` |
| CrewAI `OllamaError: Connection refused` | `OLLAMA_URL` not set; litellm defaults to `localhost:11434` which doesn't resolve inside the container | Fixed in compose: `OLLAMA_URL` defaults to `http://ollama:11434` |
| AgnosAI 404 on LLM calls | `HOOSH_URL` not set or agent has no `llm_model`; defaults to `llama3` which may not be pulled | Fixed in compose: `HOOSH_URL` defaults to `http://ollama:11434`. Agents must set `llm_model` (benchmark scenarios do this). |
| Systemd Ollama auto-restarts | `ollama.service` is enabled and restarts after stop | Use alternate host port (`OLLAMA_PORT=11435`) instead of fighting systemd |
| `NVIDIA driver` error on non-NVIDIA GPU | Default `ollama` service requires NVIDIA runtime | Use the correct profile: `ollama-vulkan`, `ollama-amd`, or `ollama-cpu` |

**Recommended launch (non-NVIDIA, host Redis/Ollama running):**

```bash
OLLAMA_PORT=11435 TLS_HTTPS_PORT=8443 TLS_HTTP_PORT=8880 \
AGNOSTIC_API_KEY=bench-key-2026 POSTGRES_PASSWORD=benchmark DATABASE_ENABLED=false \
docker compose --profile benchmark --profile ollama-vulkan up -d \
  agnostic agnosai-server ollama-vulkan

# Start Redis on internal network only (avoids host port conflict)
docker run -d --name agnostic-redis-1 \
  --network agnostic_qa-network --network-alias redis redis:7-alpine
```

#### Option B: Host Networking (no GPU / host Ollama)

When the GPU driver isn't available for Docker (e.g., Vulkan-only, AMD, or
CPU inference), use `--network host` so containers share the host's network
stack and can reach the host Ollama directly on `localhost:11434`.

**Known gotchas with host networking:**

| Issue | Cause | Solution |
|-------|-------|----------|
| Port 8000 in use | Local dev server running | Kill it: find PID with `ss -tlnp \| grep 8000` |
| Port 6379 conflict | Container tries to start embedded Redis but host Redis owns the port | Bypass the entrypoint (see below) |
| Port 443 in use | Another service on the host | Set `TLS_ENABLED=false` (already done below) |
| AgnosAI 404 on LLM | Default model (`llama3`) not in Ollama | Agents must set `llm_model` field (benchmark scenarios do this) |
| AgnosAI cache hits | `ResponseCache` returns cached responses for identical prompts | Expected for rounds 2+; first round does real inference |

**Start AgnosAI:**

```bash
docker run -d --name bench-agnosai --network host \
  -e HOOSH_URL=http://127.0.0.1:11434 \
  ghcr.io/maccracken/agnosai:1.0.2
```

Key env vars:
- `HOOSH_URL` — points AgnosAI's LLM client at Ollama's OpenAI-compatible
  endpoint. **Not** `OLLAMA_URL` — AgnosAI uses the hoosh client which
  expects an OpenAI-compatible `/v1/chat/completions` path.

**Start Agnostic (CrewAI):**

The standard entrypoint tries to start embedded Redis, which fails on host
networking when the host already runs Redis. Bypass the entrypoint and run
chainlit directly:

```bash
docker run -d --name bench-agnostic --network host \
  -e REDIS_URL=redis://127.0.0.1:6379/0 \
  -e DATABASE_ENABLED=false \
  -e AGNOSTIC_BACKEND=crewai \
  -e AGNOSTIC_API_KEY=bench-key-2026 \
  -e AGNOS_LLM_GATEWAY_ENABLED=false \
  -e AGNOS_AGENT_REGISTRATION_ENABLED=false \
  -e AGNOS_AUDIT_ENABLED=false \
  -e AGNOS_DASHBOARD_BRIDGE_ENABLED=false \
  -e AGNOS_REASONING_ENABLED=false \
  -e AGNOS_TOKEN_BUDGET_ENABLED=false \
  -e OLLAMA_URL=http://127.0.0.1:11434 \
  --entrypoint "" \
  agnostic:latest \
  bash -c 'cd /app && exec chainlit run webgui/app.py --host 0.0.0.0 --port 8000'
```

Key env vars:
- `AGNOSTIC_API_KEY` — **required**, auth has no "disabled" mode. The
  benchmark runner sends this via `--api-key`.
- `AGNOS_*_ENABLED=false` — disables all AGNOS integrations (hoosh gateway,
  daimon, audit, dashboard, reasoning, token budget) since they aren't
  running during benchmarks.
- `--entrypoint ""` — bypasses `docker/entrypoint.sh` which would try to
  start embedded Redis (fails on host networking due to port conflict).
- `OLLAMA_URL` — litellm uses this for `ollama/` prefixed model names.

### 5. Verify Health

```bash
# AgnosAI
curl -s http://localhost:8080/health
# → {"status":"ok"}

# Agnostic (CrewAI)
curl -s http://localhost:8000/health
# → {"status":"degraded", "redis":"ok", ...}
# "degraded" is normal — agents are offline until a crew is submitted
```

### 6. Run Benchmarks

```bash
.venv/bin/python -m benchmarks.run \
  --crewai-url http://localhost:8000 \
  --agnosai-url http://localhost:8080 \
  --ollama-url http://localhost:11434 \
  --model llama3.2:1b \
  --rounds 3 \
  --api-key bench-key-2026
```

Or via pytest:

```bash
.venv/bin/python -m pytest benchmarks/ -v -m benchmark \
  --crewai-url http://localhost:8000 \
  --agnosai-url http://localhost:8080 \
  --ollama-model llama3.2:1b \
  --bench-rounds 3 \
  --api-key bench-key-2026
```

### 7. Cleanup

```bash
docker rm -f bench-agnosai bench-agnostic
docker network rm bench-net 2>/dev/null
```

## CLI Options

| Option | Env Var | Default | Description |
|--------|---------|---------|-------------|
| `--crewai-url` | `CREWAI_BENCH_URL` | `http://localhost:8000` | CrewAI server |
| `--agnosai-url` | `AGNOSAI_BENCH_URL` | `http://localhost:8080` | AgnosAI server |
| `--ollama-url` | `OLLAMA_URL` | `http://localhost:11434` | Ollama server |
| `--model` | `OLLAMA_MODEL` | `qwen2.5:1.5b` | Ollama model |
| `--rounds` | `BENCH_ROUNDS` | `5` | Rounds per scenario |
| `--api-key` | `AGNOSTIC_API_KEY` | (empty) | API key for Agnostic |
| `--cooldown` | — | `30` | Seconds between backends for Ollama to drain |

## Output

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
| 3 | `multi-agent-parallel` | 3 | 3 | parallel | Parallel throughput (AgnosAI only) |
| 4 | `dag-dependencies` | 4 | 4 | dag | DAG orchestration (AgnosAI only) |
| 5 | `large-crew-6-agents` | 6 | 6 | sequential | Stress test |

**Note:** Scenarios 3 and 4 use `parallel` and `dag` process modes which
CrewAI does not support via the crews API — these return 422 on the CrewAI
backend and are AgnosAI-only benchmarks.

## Server-Side Profiling (AgnosAI 0.21.3+)

AgnosAI 0.21.3 added `CrewProfile` to every crew response, containing:

| Field | Description |
|-------|-------------|
| `wall_ms` | Total server-side wall-clock time |
| `task_ms` | Per-task duration in milliseconds (keyed by task ID) |
| `task_count` | Number of tasks executed |
| `cost_usd` | Estimated inference cost |

The benchmark report includes a **Server-Side Profiling** section showing:
- **Server Wall (ms)** — time spent inside AgnosAI (excludes HTTP overhead)
- **HTTP Overhead (ms)** — difference between client wall time and server
  wall time, quantifying the cost of the HTTP transport layer
- **Avg Cost (USD)** — average inference cost per run

This overhead measurement directly informs the Phase 4.5 roadmap item
(Unix socket IPC transport).

## Ollama Contention (Single-Instance Benchmarks)

When running both backends against a single Ollama instance, async crews
from the first backend (CrewAI) may still be executing when the second
backend (AgnosAI) starts. CrewAI crews run in background tasks — if they
exceed the poll timeout (300s), the benchmark moves on but the crew keeps
sending inference requests to Ollama.

The `--cooldown` flag (default 30s) adds a pause between backends to let
Ollama drain. For large crews on CPU inference, increase this:

```bash
.venv/bin/python -m benchmarks.run --cooldown 60 ...
```

For accurate results with zero contention, run backends in separate
benchmark passes, or use majra to multiplex across multiple Ollama instances.

## AgnosAI Response Caching

AgnosAI 0.21.3 includes a `ResponseCache` (LRU + TTL) that caches LLM
responses by prompt content. For benchmarks with fixed prompts:

- **Round 1** — cold: real LLM inference through Ollama
- **Rounds 2+** — warm: cache hits, near-zero latency

This is expected behavior. To measure pure inference latency, look at
round 1 results only. To measure amortized throughput including cache
benefits, use all rounds.

## Environment Notes

### AgnosAI LLM Model Selection

When an agent's `llm_model` field is unset, AgnosAI's complexity-based
router selects a default model tier:

| Tier | Default Model |
|------|---------------|
| Fast | `llama3` |
| Capable | `llama3:70b` |
| Premium | `llama3:405b` |

These defaults must exist in Ollama for inference to succeed. The benchmark
scenarios explicitly set `llm_model` to `ollama/<model>` to avoid this.
The `strip_provider_prefix()` function removes the `ollama/` prefix before
sending to the hoosh client.

### `HOOSH_URL` vs `OLLAMA_URL`

- **AgnosAI** uses `HOOSH_URL` — its LLM client (hoosh) sends requests to
  the OpenAI-compatible `/v1/chat/completions` endpoint. Ollama supports
  this natively, so `HOOSH_URL=http://localhost:11434` works.
- **Agnostic/CrewAI** uses `OLLAMA_URL` — litellm reads this for routing
  `ollama/` prefixed model names to the Ollama native API.

These are different env vars pointing at the same Ollama instance via
different API paths.

## Historical Results

### 2026-03-22 — AgnosAI 0.21.3 (with response cache), Ollama llama3.2:1b, 3 rounds

**Environment:** Arch Linux, host networking, Ollama native (Vulkan), llama3.2:1b (1.2B Q8_0)

**AgnosAI 0.21.3 changes:** lazy LLM init, `CrewProfile` on responses, `ResponseCache` (LRU+TTL)

| Scenario | CrewAI Mean (s) | AgnosAI Round 1 (s) | AgnosAI Rounds 2-3 (s) | Notes |
|----------|----------------|---------------------|------------------------|-------|
| single-agent-single-task | 4.7 | 104.0 | 0.002 | Cold: hoosh overhead. Warm: cache hit. |
| multi-agent-sequential | 26.7 | — (cache) | 0.002 | Prompts cached from single-agent run |
| multi-agent-parallel | 422 error | — (cache) | 0.002 | AgnosAI-only |
| dag-dependencies | 422 error | — (cache) | 0.002 | AgnosAI-only |
| large-crew-6-agents | 300.8 (timeout) | — (cache) | 0.002 | CrewAI hit 300s poll timeout |

**Key findings:**
- **Response cache works** — identical prompts return in <3ms after first inference
- **Cold single-agent: CrewAI 22x faster** (4.7s vs 104s) — hoosh→Ollama path
  has significant overhead vs litellm's direct Ollama bindings. This is the
  primary target for the Phase 4.5 socket IPC work.
- **CrewAI large-crew timeout** — 6 sequential agents on CPU exceeded the 300s
  poll timeout. Previous runs (0.20.4) completed in ~265s, suggesting Ollama
  load or scheduling variance.
- **AgnosAI cache amortizes cost** — for workloads with repeated prompts (e.g.,
  regression testing, CI), the cache eliminates inference entirely on repeat runs
- **Parallel/DAG still AgnosAI-only** — CrewAI returns 422 for non-sequential
  process modes via the crews API

### 2026-03-22 — Full Docker Compose Stack (Vulkan GPU, all fixes), 3 rounds

**Environment:** Arch Linux, Docker Compose, AMD Renoir iGPU (Vulkan),
llama3.2:1b (1.2B Q8_0), Redis container, 30s cooldown between backends.

All issues resolved: `XDG_DATA_HOME`, `OLLAMA_URL`, Redis connectivity.

| Scenario | CrewAI Mean (s) | AgnosAI Round 1 (s) | AgnosAI Rounds 2-3 (s) |
|----------|----------------|---------------------|------------------------|
| single-agent-single-task | **2.1** | 8.7 | 0.002 |
| multi-agent-sequential | **4.7** | 0.002 (cache) | 0.002 |
| multi-agent-parallel | 422 (unsupported) | 0.002 (cache) | 0.002 |
| dag-dependencies | 422 (unsupported) | 0.002 (cache) | 0.002 |
| large-crew-6-agents | **8.7** | 0.002 (cache) | 0.002 |

**Key findings:**
- **CrewAI is working end-to-end** — previous failures were infrastructure
  (Redis, XDG, Ollama URL), not code issues
- **Cold single-agent: CrewAI 4x faster** (2.1s vs 8.7s) — the delta is
  Ollama model loading on the first hoosh request. litellm keeps the model
  warm across requests.
- **CrewAI large-crew: 8.7s** — down from 300s timeout. The previous
  timeout was caused by the container not reaching Ollama at all.
- **AgnosAI cache: <2ms** — response cache eliminates repeat inference cost
- **Sequential scenarios work** for both backends; parallel/DAG still
  AgnosAI-only

**Previous 104s AgnosAI result was Ollama contention** — CrewAI async crews
kept running after poll timeout. See solo run below.

---

### 2026-03-22 — AgnosAI 0.21.3 Solo (no CrewAI, clean Ollama), 3 rounds

**Environment:** Same as above, AgnosAI only, zero Ollama contention.

| Scenario | Round 1 (s) | Rounds 2-3 (s) | Notes |
|----------|-------------|----------------|-------|
| single-agent-single-task | **10.6** | 0.002 | Cold: model load + inference. Warm: cache. |
| multi-agent-sequential | 0.002 | 0.002 | Cache hit (same prompts as single-agent) |
| multi-agent-parallel | 0.002 | 0.002 | Cache hit |
| dag-dependencies | 0.002 | 0.002 | Cache hit |
| large-crew-6-agents | 0.002 | 0.002 | Cache hit |

**Key findings:**
- **hoosh→Ollama is fine** — 10.6s cold (includes Ollama model load) vs
  CrewAI's 4.7s. The ~6s delta is Ollama first-request model loading, not
  hoosh overhead. Subsequent cold requests (different prompts) would be ~4-5s.
- **Previous 104s was Ollama contention**, not a hoosh issue — CrewAI async
  crews that exceeded the poll timeout kept running inference in the background
- **Response cache eliminates repeat cost** — identical prompts return in <3ms
- The `--cooldown` flag was added to the runner to prevent this in future runs

---

### 2026-03-21 — AgnosAI 0.20.4, Ollama llama3.2:1b, 3 rounds

**Environment:** Arch Linux, Ollama native, llama3.2:1b (1.2B Q8_0)

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
