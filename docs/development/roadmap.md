# Roadmap

Pending development work for the Agnostic Agent Platform, ordered by priority. Completed work is tracked in the [Changelog](../project/changelog.md).

See [Dependency Watch](dependency-watch.md) for upstream blockers that affect timeline.

---

## Cross-project (shared)

| Item | Effort | Notes |
|------|--------|-------|
| E2E test: SY → Agnostic crew delegation | Medium | End-to-end test that SY can delegate a non-QA crew task to Agnostic and poll status |
| E2E test: dynamic agent creation via A2A | Small | SY creates an agent definition on Agnostic via A2A, then runs a crew with it |

---

## AGNOS Fleet Crew Distribution

A distributed AGNOS fleet running Agnostic in lockstep. Every node in the fleet is a full Agnostic participant — not a dumb worker receiving dispatched jobs, but a coordinated peer that understands the crew it belongs to, holds shared state, and executes in sync with the rest of the fleet. The fleet *is* the Agnostic instance, stretched across hardware.

**Core concept:** A crew submitted to any fleet node is transparently distributed across the entire fleet. From the caller's perspective it's a single `POST /crews` — behind the scenes, agents fan out to the optimal nodes and execute as a unified crew with synchronized task handoffs, shared context, and a single aggregated result.

**What this means:**

- **Lockstep execution model** — All agents in a fleet-distributed crew share a synchronized execution clock. Task handoffs between agents are barrier-synchronized: Agent B on Node 2 does not begin until Agent A on Node 1 has committed its output to the shared state. This prevents drift, partial results, and ordering bugs. The crew behaves identically whether it runs on one node or twenty.
- **Unified crew state** — A single Redis-backed state object represents the crew regardless of how many nodes participate. Every agent reads from and writes to the same logical state. Conflict resolution via optimistic locking (Redis WATCH/MULTI) ensures consistency without distributed consensus overhead.
- **Any-node entry point** — A crew request can land on any fleet node. That node becomes the *coordinator* for that crew — it runs the placement engine, fans out agent assignments, and aggregates results. Other nodes are *participants*. If the coordinator fails, another node can pick up coordination from the checkpointed state.
- **Agent placement** — The coordinator assigns each agent to a fleet node based on capabilities (GPU model/VRAM, CPU cores, RAM, installed tools, network locality). Agent 1 runs on a GPU workstation for inference-heavy work while Agent 2 runs on an edge device close to the data source. Placement is deterministic given the same fleet state — replayable and auditable.
- **Fleet inventory** — Live registry of fleet nodes populated by `agnosys` hardware probes and kept current via heartbeat (default 10s TTL). Each node reports: GPU model/VRAM/utilization, CPU cores/load, RAM, disk, network latency to peers, installed tool capabilities. Exposed as `GET /api/v1/fleet/nodes`.
- **Scheduling policies** — Pluggable strategies determine agent-to-node mapping:
  - `gpu-affinity` — prefer GPU nodes for compute-heavy agents (default)
  - `data-locality` — place agents near the data they process (minimize transfer)
  - `balanced` — spread load evenly across nodes
  - `cost-aware` — prefer cheaper/lower-power nodes first, escalate to GPU only when needed
  - `lockstep-strict` — all agents co-located on fewest nodes possible to minimize network hops (for latency-critical crews)
- **Inter-node agent communication** — Agents on different nodes communicate via Redis pub/sub with ordered message delivery. CrewAI task handoffs serialized as JSON with sequence numbers for exactly-once processing. Latency-sensitive crews can opt into gRPC direct links between nodes for sub-millisecond handoffs.
- **Fault tolerance & recovery** — Crew state checkpointed to Redis after every task completion. If a node drops mid-crew, the coordinator detects the loss via heartbeat timeout, re-places the affected agent on another eligible node, and replays from the last checkpoint. The crew continues without restarting. If the *coordinator* drops, any participant can assume coordination from the same checkpoint.
- **GPU-aware placement** — Nodes report GPU availability and VRAM headroom in real time. Agents with `gpu_required` tools or local-inference workloads are only placed on GPU nodes. Multi-GPU nodes can host multiple agents with per-agent CUDA_VISIBLE_DEVICES isolation. Fleet-wide GPU utilization visible at a glance.
- **Security boundary** — Fleet nodes authenticate via mTLS (certificates issued by AGNOS CA). All agent-to-agent traffic encrypted in transit. Crew outputs aggregated at the coordinator before returning to the caller. No raw inter-node traffic is exposed outside the fleet mesh.
- **Scaling model** — Adding a node to the fleet is additive: install Agnostic, point it at the fleet Redis, and it joins automatically via heartbeat registration. No reconfiguration of existing nodes. Removing a node triggers graceful drain — in-flight agents are re-placed before the node is deregistered.
- **Node groups** — Fleet nodes can be organized into logical groups (e.g., `gpu-rack-1`, `edge-west`, `dev-lab`). A group acts as a scheduling unit — the placement engine can target a group rather than individual nodes, and scheduling policies apply at the group level. Crews can be pinned to a group (`"group": "gpu-rack-1"`) or span multiple groups. Groups enable: co-locating related agents on the same rack for low-latency handoffs, isolating tenants to dedicated hardware, running separate crews on separate clusters simultaneously, and treating a multi-GPU rack as a single high-capability unit. Groups are declared via node config (`AGNOS_FLEET_GROUP=gpu-rack-1`) and surfaced in the fleet inventory.

**Deliverables:**

| Item | Effort | Notes |
|------|--------|-------|
| Fleet scaling test | Medium | Add/remove nodes from a running fleet while crews are executing. Verify zero disruption. Test scaffold in `tests/e2e/test_fleet_scaling.py` — needs Docker compose |
| E2E test: multi-node lockstep crew | Medium | Spin up 3+ test containers as fleet nodes. Run a crew that spans all. Verify lockstep ordering, fault recovery, and output correctness. Test scaffold in `tests/e2e/test_fleet_lockstep.py` — needs Docker compose |

---

## Engineering Backlog

All security, performance, code quality, and test coverage sections cleared. Remaining:

### Benchmarking (Docker required)

| Item | Effort | Notes |
|------|--------|-------|
| Crew creation throughput | Medium | Concurrent `POST /crews` (1/5/10/20 simultaneous) — thread pool saturation |
| Crew execution by agent count | Medium | Wall time for 1/3/6/10 agent crews |

---

## crewAI 1.11.0 Upgrade (watching RC1)

RC1 released 2026-03-16. Items for when stable lands.

| Priority | Item | Effort | Notes |
|----------|------|--------|-------|
| **P0** | Docker now required for CodeInterpreterTool | Medium | No fallback sandbox — fails closed. Ensure our Docker containers provide the runtime crewAI expects |
| **P1** | A2A Plus API token auth | Small | New enterprise auth for A2A. Update A2A handler if token required |
| **P2** | Validate concurrency fixes | Small | ContextVar propagation + locking fixes. Run integration tests |
| **P3** | Evaluate plan-execute pattern | Small | New orchestration mode — try with quality presets |

See also [Dependency Watch](dependency-watch.md).

---

## Long-term / Blocked

| Item | Blocker |
|------|---------|
| Python 3.14 support | crewai 1.11.0rc1 still `requires-python <3.14` — sole remaining blocker. chromadb 1.1.1 is now unblocked (`>=3.9`). See [Dependency Watch](dependency-watch.md) |

---

## v2 — Rust Core

Rewrite the performance-critical infrastructure layer in Rust. Python remains the agent execution boundary (CrewAI, LLM calls, tool registry). The split mirrors how AGNOS already works: Rust core with Python agent workers.

**Motivation**: The fleet coordination layer (node registry, placement engine, relay, coordinator, crew state, barrier sync) is concurrent stateful systems code — Rust's sweet spot. Python's GIL and async overhead will become bottlenecks when fleet runs at scale with dozens of nodes and hundreds of concurrent crews.

**Rust core candidates** (in priority order):

| Module | Current | Why Rust |
|--------|---------|----------|
| Fleet registry & heartbeat | `config/fleet/registry.py` | High-frequency Redis writes, concurrent node tracking, TTL management |
| Placement engine | `config/fleet/placement.py` | Deterministic scheduling across many nodes, needs to be fast and predictable |
| Inter-node relay | `config/fleet/relay.py` | Redis pub/sub message ordering, sequence dedup, high throughput |
| Fleet coordinator | `config/fleet/coordinator.py` | Concurrent result collection, health monitoring, failover — all GIL-sensitive |
| Crew state manager | `config/fleet/state.py` | Redis optimistic locking, barrier sync, checkpoint persistence |
| GPU scheduler | `config/gpu_scheduler.py` | Multi-device assignment, memory tracking, cross-crew slot management |
| GPU detection | `config/gpu.py` | nvidia-smi parsing, cached probing — light but benefits from zero-cost abstractions |

**Python boundary** (stays Python):

| Module | Why Python |
|--------|-----------|
| Agent definitions & factory | CrewAI `Agent`/`Crew`/`Task` are Python classes |
| LLM integration | litellm, anthropic SDK, OpenAI SDK — all Python |
| Tool registry | Tools are Python `BaseTool` subclasses, dynamic loading via `exec()` |
| Crew assembler | NLP-style fuzzy matching, keyword scoring — Python-native |
| Local inference routing | litellm model routing, Ollama/vLLM clients — Python ecosystem |
| WebGUI / FastAPI | REST API, Chainlit app — Python web framework |

**Integration approach**: Rust core exposes a Python API via PyO3/maturin. The fleet modules become a `agnostic-fleet` Rust crate compiled as a Python extension module. Python code calls `from agnostic_fleet import FleetRegistry, PlacementEngine` etc. — drop-in replacement, same API, 10-100x faster internals.

**Prerequisites**: Fleet running at scale (real multi-node deployments), benchmarks showing Python as the bottleneck, AGNOS fleet infrastructure stable.

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Test execution time reduction | > 50% via optimisation |
| Defect detection rate | > 95% automated |
| System uptime | > 99.9% |
| Test coverage (agents) | > 90% automated |
| Defect escape rate | < 1% to production |
| Compliance score | > 95% (GDPR, PCI DSS, SOC 2, ISO 27001, HIPAA) |
| Mean time to resolution | < 30 min for QA issues |
| Cross-project trace coverage | > 80% of requests traced end-to-end |
| AGNOS audit chain coverage | 100% of QA actions forwarded |
| Agent preset count | 3+ domain presets (QA, data-eng, devops, ...) |
| Dynamic agent creation latency | < 5s from definition to running agent |

---

*Last Updated: 2026-03-17 · Version: 2026.3.17-2 · Test count: 1099 (unit) + 10 fleet E2E scaffolds + 24 (e2e) · [Changelog](../project/changelog.md) · [Dependency Watch](dependency-watch.md)*
