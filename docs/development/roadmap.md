# Roadmap

Pending development work for the Agnostic Agent Platform, ordered by priority. Completed work is tracked in the [Changelog](../project/changelog.md).

See [Dependency Watch](dependency-watch.md) for upstream blockers that affect timeline.

---

## Downstream Integration (pending)

Remaining work in **Agnosticos** and **SecureYeoman** to fully consume AAS multi-domain capabilities.

### Agnosticos (AGNOS OS)

| Item | Effort | Notes |
|------|--------|-------|
| Agent HUD multi-domain UI | Medium | Group agents by domain in the HUD. Add domain filter/tabs |
| RPC method registration for crew agents | Medium | Dynamic agents from presets need RPC methods registered on-the-fly |

### SecureYeoman

| Item | Effort | Notes |
|------|--------|-------|
| Preset selector UI | Medium | Connections > Agnostic panel should show presets and allow crew selection |
| MCP auto-discovery integration test | Small | Verify the 5 new crew tools auto-appear in SY's MCP discovery |

### Shared / Cross-project

| Item | Effort | Notes |
|------|--------|-------|
| E2E test: SY → Agnostic crew delegation | Medium | End-to-end test that SY can delegate a non-QA crew task to Agnostic and poll status |
| E2E test: dynamic agent creation via A2A | Small | SY creates an agent definition on Agnostic via A2A, then runs a crew with it |
| Documentation: cross-project API contract | Small | Document the new API surface (crew endpoints, preset endpoints, A2A message types) as a shared contract |

---

## AGNOS & SecureYeoman Integration

*Cross-project integration items for the ecosystem.*

### AGNOS Integration

| Item | Effort | Notes |
|------|--------|-------|
| Crew status in AGNOS HUD | Medium | Push crew lifecycle events to AGNOS daimon for display in aethersafha HUD. Use `GET /crews` with status filter |
| Crew cancellation from agnoshi | Small | Wire `POST /crews/{crew_id}/cancel` to AGNOS MCP tool `agnostic_cancel_crew` and agnoshi intent "cancel crew {id}" |

### AGNOS-side Integration (work needed in AGNOS / Agnosticos)

Agnostic's GPU features are **OS-agnostic by design** — `nvidia-smi` probing and `CUDA_VISIBLE_DEVICES` work on any Linux/Windows host with NVIDIA drivers. Running on AGNOS gets additional benefits: `agnosys` hardware probes, fleet-wide GPU inventory, HUD integration, and daimon-coordinated scheduling.

| Item | Where | Effort | Notes |
|------|-------|--------|-------|
| `agnosys` GPU probe JSON | AGNOS | Small | `agnosys` already probes hardware — add GPU fields to the probe output and write `/var/lib/agnosys/gpu.json` (Agnostic already reads this path) |
| GPU status in aethersafha HUD | Agnosticos | Medium | Consume `GET /api/v1/gpu/status` and `GET /api/v1/gpu/memory` from the Agnostic instance. Show per-device VRAM bars, utilization, and temperature in the Agent HUD |
| GPU placement in crew HUD cards | Agnosticos | Small | When displaying crew status, show which agents are on GPU vs CPU and their VRAM usage (data already in crew result `gpu_placement` and per-agent `gpu_vram`) |
| agnoshi GPU intents | AGNOS | Small | "show gpu status", "show gpu memory" intents that call Agnostic GPU endpoints via MCP |
| Fleet GPU aggregation | AGNOS | Medium | Aggregate `GET /api/v1/gpu/status` across all fleet nodes into a single fleet-wide GPU inventory. Feed into fleet placement engine |
| agnosys GPU budget recommendations | AGNOS | Small | Based on observed VRAM usage patterns, recommend `gpu_memory_budget_mb` values for common crew presets |
| MCP tool: `agnostic_gpu_status` | Agnosticos | Small | New MCP tool exposing GPU status so other AGNOS components can query Agnostic's GPU state without HTTP |
| Daimon GPU event forwarding | AGNOS | Medium | Forward GPU allocation/release events from crew runs to the daimon event stream. Enables fleet-wide GPU utilization tracking and alerting |
| Non-AGNOS fallback docs | Agnostic | Small | Document the GPU feature behavior on non-AGNOS hosts: nvidia-smi only, no fleet inventory, no HUD — all scheduling still works |

### AGNOS Fleet Crew Distribution

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
| Fleet node inventory & heartbeat | Medium | `agnosys` probe reports hardware caps + load. Central registry with TTL-based liveness. `GET /api/v1/fleet/nodes` |
| Fleet join/leave protocol | Medium | Auto-registration via heartbeat. Graceful drain on leave. Node discovery without manual config |
| Node group support | Small | `AGNOS_FLEET_GROUP` config. Group-level scheduling, crew pinning (`"group": "gpu-rack-1"`). Groups in fleet inventory and HUD |
| Unified crew state layer | Medium | Redis-backed shared state with optimistic locking. Single logical state object per crew regardless of node count |
| Lockstep barrier sync | Medium | Barrier-synchronized task handoffs between agents on different nodes. Sequence-numbered messages for exactly-once delivery |
| Placement engine | Large | Match agent requirements (GPU, memory, tools) to node capabilities. Pluggable scheduling policies. Deterministic placement |
| Coordinator election & failover | Medium | Any-node entry point. Coordinator failure detected via heartbeat. Participant promotion from checkpointed state |
| Inter-node task relay | Large | Serialize CrewAI task handoffs over Redis pub/sub with ordering guarantees. Optional gRPC fast path. Partial failure handling and retries |
| Fleet-aware crew builder | Medium | Extend `assemble_team()` and `_run_crew_async()` to accept placement hints and distribute agents across nodes transparently |
| Agent checkpoint & recovery | Medium | Persist agent state to Redis after each task. On node failure, reschedule agent on new node and resume from checkpoint |
| Fleet GPU status dashboard | Small | Aggregate GPU utilization across all fleet nodes. Surface in AGNOS HUD and via `GET /api/v1/fleet/gpu` |
| Fleet scaling test | Medium | Add/remove nodes from a running fleet while crews are executing. Verify zero disruption |
| E2E test: multi-node lockstep crew | Medium | Spin up 3+ test containers as fleet nodes. Run a crew that spans all. Verify lockstep ordering, fault recovery, and output correctness |

### SecureYeoman Integration

| Item | Effort | Notes |
|------|--------|-------|
| Crew delegation from SY workflows | Medium | SY DAG workflow step type `agnostic_crew` that creates and monitors an Agnostic crew. Poll `GET /crews/{id}` until completion |
| SY DLP integration for crew output | Medium | Route crew output through SY's DLP pipeline before returning to user. Prevents data leakage from crew agents |
| SY audit forwarding for crew actions | Small | Forward crew action logs to SY's cryptographic audit trail via delegated auth |
| Preset management from SY dashboard | Medium | SY Connections > Agnostic panel: browse/select presets, create crews, view crew history |

---

## Engineering Backlog

Items identified during code review and audit. Not blocking, but should be addressed over time.

*Security, Performance, and Code Quality sections cleared — all items completed.*

### Test Coverage

| Item | Effort | Notes |
|------|--------|-------|
| ZIP bomb / entry count limit tests | Small | `_MAX_UNCOMPRESSED_SIZE` and `_MAX_ENTRY_COUNT` checks untested |
| `AgentFactory.invalidate_cache()` selective test | Small | Path-specific invalidation untested |
| YAML definition loading test | Small | `factory.from_file()` YAML branch untested |
| `_run_crew_async()` integration test | Medium | Background execution mocked away in current tests |
| `delegate_to()` edge cases | Small | Invalid key rejection, missing file, delegation failure untested |
| `rollback_definition` endpoint test | Small | API-level rollback test missing |
| Factory/registry cache bounds tests | Small | Eviction behavior at `_CACHE_MAX_SIZE` / `_REGISTRY_MAX_SIZE` untested |

### Benchmarking

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

*Last Updated: 2026-03-17 · Version: 2026.3.17 · Test count: 1055 (unit) + 24 (e2e) · [Changelog](../project/changelog.md) · [Dependency Watch](dependency-watch.md)*
