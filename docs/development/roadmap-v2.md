# Roadmap v2 — AgnosAI: Rust-Native Agent Orchestration

> Replaces CrewAI with a purpose-built Rust framework. Python only where absolutely necessary, sandboxed when used.

AgnosAI is a Rust-native agent orchestration crate that replaces CrewAI as the core engine powering Agnostic. It distills production-proven patterns from three projects:

- **Agnosticos (daimon)** — Orchestrator, IPC, pub/sub, scoring, scheduling, resource management, RL optimizer, federation (8997+ tests, tokio async, Arc/RwLock/mpsc/DashMap)
- **Agnosticos (hoosh)** — LLM provider abstraction, health tracking, rate limiting, token accounting, response caching
- **SecureYeoman** — 13-provider AI routing, model router (task-complexity scoring), cost budgeting, 9-tier sandbox stack
- **Agnostic v1** — Agent definitions, crew assembly, tool registry, fleet distribution, GPU scheduling, 18 presets across 5 domains

The result: a single `agnosai` crate that any Rust project can depend on for multi-agent orchestration — and that Agnostic uses as its core engine.

---

## Why Replace CrewAI

| Problem | Impact |
|---------|--------|
| Python GIL | Concurrent crew execution serialized; fleet coordination bottlenecked |
| CrewAI release churn | Every RC breaks something (1.10→1.11: Docker required for CodeInterpreter, A2A auth changes, Python 3.14 blocked) |
| Dependency gravity | CrewAI pulls in chromadb, langchain, pydantic v2, litellm — 200+ transitive deps, version conflicts |
| No fleet awareness | CrewAI is single-process; fleet distribution is bolted on via Redis glue code |
| No sandbox integration | Tool execution is unsandboxed `exec()` — we built our own sandbox layer on top |
| Limited scheduling | Sequential or hierarchical only — no DAG, no priority queues, no preemption |
| Opaque internals | Can't control memory layout, allocation, or concurrency model |

AgnosAI eliminates the dependency on CrewAI and its entire Python ML stack. The orchestration layer becomes a compiled Rust binary with predictable performance, real concurrency, and zero GIL.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                      agnosai (crate)                    │
│                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────┐ │
│  │ Orchestr │  │   LLM    │  │  Fleet   │  │ Sand-  │ │
│  │  -ator   │  │ Gateway  │  │ Distrib  │  │  box   │ │
│  ├──────────┤  ├──────────┤  ├──────────┤  ├────────┤ │
│  │ Task DAG │  │ Provider │  │ Registry │  │ WASM   │ │
│  │ Priority │  │  Router  │  │Placement │  │Process │ │
│  │ Scoring  │  │  Health  │  │  Relay   │  │Landlock│ │
│  │ Preempt  │  │  Cache   │  │ Barrier  │  │seccomp │ │
│  │  IPC     │  │  Budget  │  │Failover  │  │  OCI   │ │
│  │ Pub/Sub  │  │Rate Limit│  │   GPU    │  │  TEE   │ │
│  └──────────┘  └──────────┘  └──────────┘  └────────┘ │
│                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────┐ │
│  │  Agent   │  │   Tool   │  │Learning &│  │  API   │ │
│  │Framework │  │ Registry │  │    RL    │  │ Server │ │
│  ├──────────┤  ├──────────┤  ├──────────┤  ├────────┤ │
│  │  Define  │  │  Native  │  │Perf Prof │  │REST/gRP│
│  │  Create  │  │   WASM   │  │UCB1 Sel  │  │  MCP   │ │
│  │  Score   │  │ Sandboxed│  │Exp Replay│  │  A2A   │ │
│  │ Delegate │  │  Python* │  │CapConfid │  │  SSE   │ │
│  └──────────┘  └──────────┘  └──────────┘  └────────┘ │
└─────────────────────────────────────────────────────────┘
                          │
              * Python tools run sandboxed
                (WASM / subprocess / OCI)
```

---

## Crate Structure

```
agnosai/
├── Cargo.toml                    # Workspace root
├── crates/
│   ├── agnosai-core/             # Core types, traits, error handling
│   │   ├── src/
│   │   │   ├── lib.rs
│   │   │   ├── agent.rs          # AgentDefinition, AgentId, AgentState
│   │   │   ├── task.rs           # Task, TaskDAG, TaskPriority, TaskResult
│   │   │   ├── crew.rs           # CrewSpec, CrewState, CrewResult
│   │   │   ├── message.rs        # Message, TopicMessage, A2AMessage
│   │   │   ├── resource.rs       # GpuDevice, CpuInfo, ResourceBudget
│   │   │   └── error.rs          # AgnosaiError (thiserror)
│   │   └── Cargo.toml
│   │
│   ├── agnosai-orchestrator/     # Task scheduling & agent coordination
│   │   ├── src/
│   │   │   ├── lib.rs
│   │   │   ├── orchestrator.rs   # Core orchestrator (Arc<RwLock<State>>)
│   │   │   ├── scheduler.rs      # Priority queue, DAG resolution, preemption
│   │   │   ├── scoring.rs        # Agent scoring (CPU, GPU, capability, affinity)
│   │   │   ├── ipc.rs            # Unix socket IPC (length-prefixed framing)
│   │   │   ├── pubsub.rs         # Topic-based pub/sub with wildcards
│   │   │   └── crew_runner.rs    # Crew lifecycle: assemble → execute → aggregate
│   │   └── Cargo.toml
│   │
│   ├── agnosai-llm/              # LLM provider abstraction
│   │   ├── src/
│   │   │   ├── lib.rs
│   │   │   ├── provider.rs       # LlmProvider trait + implementations
│   │   │   ├── router.rs         # Task-complexity model routing (from SY)
│   │   │   ├── health.rs         # Provider health ring buffer (from SY)
│   │   │   ├── cache.rs          # Response cache (LRU, TTL)
│   │   │   ├── budget.rs         # Token accounting, per-agent budgets
│   │   │   ├── rate_limiter.rs   # Semaphore-based rate limiting
│   │   │   └── providers/
│   │   │       ├── openai.rs     # OpenAI / OpenAI-compatible
│   │   │       ├── anthropic.rs  # Anthropic (direct HTTP, no SDK dep)
│   │   │       ├── ollama.rs     # Ollama local inference
│   │   │       ├── gemini.rs     # Google Gemini
│   │   │       ├── deepseek.rs   # DeepSeek
│   │   │       ├── mistral.rs    # Mistral
│   │   │       ├── groq.rs       # Groq
│   │   │       ├── lmstudio.rs   # LM Studio
│   │   │       └── hoosh.rs      # AGNOS hoosh gateway
│   │   └── Cargo.toml
│   │
│   ├── agnosai-fleet/            # Distributed fleet coordination
│   │   ├── src/
│   │   │   ├── lib.rs
│   │   │   ├── registry.rs       # Node inventory, heartbeat, TTL
│   │   │   ├── placement.rs      # Scheduling policies (gpu-affinity, balanced, etc.)
│   │   │   ├── relay.rs          # Inter-node messaging (Redis pub/sub, gRPC)
│   │   │   ├── coordinator.rs    # Crew fan-out, aggregation, failover
│   │   │   ├── state.rs          # Distributed crew state, barrier sync, checkpoints
│   │   │   ├── gpu.rs            # GPU detection, scheduling, VRAM tracking
│   │   │   └── federation.rs     # Multi-cluster federation (from Agnosticos)
│   │   └── Cargo.toml
│   │
│   ├── agnosai-sandbox/          # Tool execution isolation
│   │   ├── src/
│   │   │   ├── lib.rs
│   │   │   ├── manager.rs        # SandboxManager — policy-based backend selection
│   │   │   ├── wasm.rs           # wasmtime WASM sandbox
│   │   │   ├── process.rs        # Subprocess with seccomp + Landlock + cgroups
│   │   │   ├── oci.rs            # OCI container sandbox (sy-agnos compatible)
│   │   │   ├── python.rs         # Sandboxed Python interpreter for legacy tools
│   │   │   └── policy.rs         # Sandbox profiles (strength scoring)
│   │   └── Cargo.toml
│   │
│   ├── agnosai-tools/            # Tool registry & execution
│   │   ├── src/
│   │   │   ├── lib.rs
│   │   │   ├── registry.rs       # Tool registration, lookup, capability matching
│   │   │   ├── native.rs         # Native Rust tool trait + execution
│   │   │   ├── wasm_tool.rs      # WASM tool loading & execution
│   │   │   ├── python_tool.rs    # Legacy Python tool bridge (sandboxed)
│   │   │   └── builtin/          # Built-in tools (code analysis, security, etc.)
│   │   └── Cargo.toml
│   │
│   ├── agnosai-learning/         # Adaptive learning & RL
│   │   ├── src/
│   │   │   ├── lib.rs
│   │   │   ├── profile.rs        # PerformanceProfile, success rates, duration tracking
│   │   │   ├── strategy.rs       # UCB1 multi-armed bandit strategy selection
│   │   │   ├── replay.rs         # Prioritized experience replay buffer
│   │   │   ├── capability.rs     # Dynamic capability confidence scoring
│   │   │   └── optimizer.rs      # Q-learning, policy gradient
│   │   └── Cargo.toml
│   │
│   ├── agnosai-server/           # HTTP/gRPC API server
│   │   ├── src/
│   │   │   ├── lib.rs
│   │   │   ├── main.rs           # Binary entry point
│   │   │   ├── routes/
│   │   │   │   ├── crews.rs      # POST /crews, GET /crews/:id
│   │   │   │   ├── agents.rs     # Agent CRUD + status
│   │   │   │   ├── definitions.rs # Preset/definition management
│   │   │   │   ├── fleet.rs      # Fleet node inventory
│   │   │   │   ├── gpu.rs        # GPU status + scheduling
│   │   │   │   ├── mcp.rs        # MCP server (tool advertisement)
│   │   │   │   ├── a2a.rs        # A2A protocol (SY webhooks)
│   │   │   │   └── health.rs     # Health + readiness probes
│   │   │   ├── auth.rs           # JWT auth, AGNOS token delegation
│   │   │   └── sse.rs            # Server-sent events for streaming
│   │   └── Cargo.toml
│   │
│   └── agnosai-definitions/      # Preset library
│       ├── src/
│       │   ├── lib.rs
│       │   ├── loader.rs         # JSON/YAML definition loading
│       │   ├── assembler.rs      # Crew assembly from team specs
│       │   ├── versioning.rs     # Definition versioning & rollback
│       │   └── packaging.rs      # .agpkg export/import
│       ├── presets/              # 18 built-in presets (JSON)
│       │   ├── quality-lean.json
│       │   ├── quality-standard.json
│       │   ├── software-engineering-standard.json
│       │   ├── devops-lean.json
│       │   └── ...
│       └── Cargo.toml
│
├── examples/
│   ├── simple_crew.rs            # Minimal crew execution
│   ├── fleet_demo.rs             # Multi-node fleet
│   └── custom_tool.rs            # Native Rust tool
│
└── tests/
    ├── integration/
    └── e2e/
```

---

## Concurrency Model

Patterns proven in Agnosticos (8997+ tests), adapted for AgnosAI:

| Pattern | Where | Why |
|---------|-------|-----|
| `Arc<RwLock<OrchestratorState>>` | Orchestrator | Single lock for compound operations (cancel, preempt, reassign) — readers dominate |
| `tokio::mpsc` channels | IPC, relay | Backpressure-aware message passing between agents and nodes |
| `DashMap` | Agent registry, tool registry | Lock-free concurrent reads; high read:write ratio |
| `AtomicUsize` | Connection limits, metrics counters | Non-blocking global counters |
| `tokio::Semaphore` | Rate limiting, connection limits | Bounded concurrency without busy-waiting |
| Topic pub/sub with wildcards | Inter-agent events | Flexible decoupled communication (`"task.*"` matches `"task.completed"`) |
| Priority `VecDeque` per level | Task scheduler | O(1) enqueue/dequeue per priority tier (Critical → Background) |

---

## Python Boundary — Sandboxed, Not Eliminated

Python is used **only** when a tool or library has no Rust equivalent and cannot reasonably be ported. Every Python invocation runs inside a sandbox.

### When Python Is Required

| Use Case | Why No Rust Alternative | Sandbox |
|----------|------------------------|---------|
| Legacy CrewAI tools (BaseTool subclasses) | Existing tool ecosystem; porting 50+ tools takes time | Process (seccomp + Landlock) |
| Specialized ML libraries (scikit-learn, pandas for data tools) | Domain-specific; Rust equivalents immature | WASM or Process |
| Playwright browser automation | No Rust equivalent for full browser automation | OCI container |
| Custom user-defined tools (uploaded Python) | User code; untrusted by definition | WASM (preferred) or OCI |

### How Python Runs

```
AgnosAI Orchestrator (Rust)
    │
    ├── Native tool? → Execute in-process (zero overhead)
    ├── WASM tool?   → wasmtime sandbox (memory-isolated, capability-controlled)
    └── Python tool? → Spawn sandboxed subprocess:
                       ┌──────────────────────────┐
                       │  seccomp-bpf (syscall)    │
                       │  Landlock (filesystem)    │
                       │  cgroups v2 (resources)   │
                       │  network namespace (net)  │
                       │  ┌────────────────────┐   │
                       │  │  python3 -c <tool>  │   │
                       │  │  stdin → JSON task  │   │
                       │  │  stdout → JSON res  │   │
                       │  └────────────────────┘   │
                       └──────────────────────────┘
```

The Python process has:
- No filesystem access except `/tmp/tool-<id>/` (Landlock)
- No network access by default (network namespace); opt-in allowlist
- CPU + memory capped (cgroups v2)
- Syscall whitelist (seccomp-bpf)
- Max execution time (SIGKILL after timeout)
- stdin/stdout JSON protocol (no shared memory, no FFI)

### Migration Path for Tools

1. **Immediate**: Existing Python tools run sandboxed with zero code changes (stdin/stdout JSON bridge)
2. **Gradual**: High-value tools rewritten as native Rust tools (in-process, zero overhead)
3. **Community**: New tools encouraged as WASM modules (portable, sandboxed by design)
4. **Long-term**: Python sandbox remains for backward compatibility but is the slow path

---

## LLM Integration — Native HTTP, No SDKs

Every LLM provider is implemented as direct HTTP calls via `reqwest`. No Python SDKs, no litellm dependency.

```rust
#[async_trait]
pub trait LlmProvider: Send + Sync {
    async fn infer(&self, request: InferenceRequest) -> Result<InferenceResponse>;
    async fn stream(&self, request: InferenceRequest) -> Result<InferenceStream>;
    async fn list_models(&self) -> Result<Vec<ModelInfo>>;
    fn provider_type(&self) -> ProviderType;
}
```

### Providers (Rust-native, from SY's 13-provider architecture)

| Provider | Protocol | Notes |
|----------|----------|-------|
| OpenAI | REST (`/v1/chat/completions`) | Also covers OpenAI-compatible (vLLM, text-generation-inference) |
| Anthropic | REST (`/v1/messages`) | Direct HTTP, streaming via SSE |
| Google Gemini | REST (`/v1beta/models`) | |
| Ollama | REST (`/api/chat`) | Local inference |
| DeepSeek | REST (OpenAI-compatible) | |
| Mistral | REST (OpenAI-compatible) | |
| Groq | REST (OpenAI-compatible) | |
| LM Studio | REST (OpenAI-compatible) | Local inference |
| AGNOS hoosh | REST (OpenAI-compatible) | System LLM gateway with token budgeting |

### Model Router (from SY)

Task-complexity scoring selects the right model tier:

```rust
pub enum ModelTier { Fast, Capable, Premium }

pub fn route(profile: &TaskProfile) -> ModelTier {
    let base = match profile.task_type {
        TaskType::Summarize | TaskType::Classify => ModelTier::Fast,
        TaskType::Code | TaskType::Plan | TaskType::Reason => ModelTier::Capable,
        TaskType::Research | TaskType::MultiStep => ModelTier::Premium,
    };
    // Upgrade tier for complex tasks
    if profile.complexity == Complexity::Complex && base == ModelTier::Fast {
        ModelTier::Capable
    } else { base }
}
```

### Provider Health (from SY)

5-point ring buffer per provider. After 3 consecutive failures → mark unhealthy → failover to next provider. One success resets.

---

## Agent Definitions — Declarative, Portable

Agent definitions are JSON/YAML (same format as Agnostic v1 — zero migration cost for existing presets):

```json
{
  "agent_key": "senior-qa-engineer",
  "name": "Senior QA Engineer",
  "role": "Senior QA Engineer",
  "goal": "Ensure comprehensive test coverage...",
  "domain": "quality",
  "tools": ["self_healing", "model_based_testing", "edge_case_analysis"],
  "complexity": "high",
  "llm_model": "capable",
  "gpu_required": false,
  "gpu_preferred": true,
  "gpu_memory_min_mb": 4096
}
```

Definitions load identically to v1. The `AgentFactory` becomes Rust-native with the same API surface.

---

## Task DAG (Beyond CrewAI's Sequential/Hierarchical)

CrewAI supports only `sequential` and `hierarchical` process modes. AgnosAI supports arbitrary DAGs:

```rust
pub struct TaskDAG {
    pub tasks: HashMap<String, Task>,
    pub edges: Vec<(String, String)>,    // (from, to) dependency edges
    pub process: ProcessMode,
}

pub enum ProcessMode {
    Sequential,                          // CrewAI compat: A → B → C
    Hierarchical { manager: AgentId },   // CrewAI compat: manager delegates
    DAG,                                 // Arbitrary dependency graph
    Parallel { max_concurrency: usize }, // All tasks concurrently
}
```

DAG resolution uses topological sort. Tasks with no unmet dependencies run concurrently. Priority + preemption applies within the DAG.

---

## Fleet Distribution — Native, Not Bolted On

Fleet is a first-class concept, not Redis glue on top of a single-process framework.

### What Moves from Python to Rust

| Module | Python (v1) | Rust (AgnosAI) | Gain |
|--------|-------------|----------------|------|
| Node registry | `config/fleet/registry.py` | `agnosai-fleet/registry.rs` | Real concurrency, no GIL |
| Placement engine | `config/fleet/placement.py` | `agnosai-fleet/placement.rs` | Deterministic, sub-ms scheduling |
| Inter-node relay | `config/fleet/relay.py` | `agnosai-fleet/relay.rs` | Ordered message passing with sequence dedup |
| Coordinator | `config/fleet/coordinator.py` | `agnosai-fleet/coordinator.rs` | Concurrent result collection without GIL |
| Crew state | `config/fleet/state.py` | `agnosai-fleet/state.rs` | Native Redis optimistic locking |
| GPU scheduler | `config/gpu_scheduler.py` | `agnosai-fleet/gpu.rs` | Atomic VRAM tracking |
| Federation | — (not in v1) | `agnosai-fleet/federation.rs` | From Agnosticos: multi-cluster support |

### Federation (from Agnosticos)

Multi-cluster federation with Raft-inspired coordinator election, mDNS/DNS-SD discovery, gRPC control plane, mTLS inter-node encryption. Already proven in Agnosticos — extracted into AgnosAI.

---

## Learning & RL (from Agnosticos)

Adaptive agent behavior with reinforcement learning — no Python ML libraries needed:

- **Performance profiling**: Success rate, duration tracking per agent per action type
- **UCB1 strategy selection**: Multi-armed bandit for choosing between tool strategies
- **Prioritized experience replay**: Buffer with priority sampling for efficient learning
- **Dynamic capability confidence**: Per-capability confidence scoring with trend detection
- **Q-learning / policy gradient**: Tabular value functions and REINFORCE-like updates

All implemented in pure Rust (proven in Agnosticos with 8997+ tests).

---

## Phases

### Phase 1 — Core Crate (Foundation)

Build `agnosai-core` and `agnosai-orchestrator` with the essential primitives.

| Item | Source | Effort |
|------|--------|--------|
| Core types (Agent, Task, Crew, Message, Resource) | Agnosticos `agnos-common` | Small |
| Orchestrator with `Arc<RwLock<State>>` | Agnosticos `daimon/orchestrator` | Medium |
| Priority task scheduler with DAG resolution | Agnosticos `scheduling.rs` + new DAG | Medium |
| Agent scoring (CPU, GPU, capability, affinity) | Agnosticos `scoring.rs` | Small |
| IPC (Unix sockets, length-prefixed framing) | Agnosticos `ipc.rs` | Small |
| Topic pub/sub with wildcards | Agnosticos `pubsub.rs` | Small |
| Agent definitions (JSON/YAML loading) | Agnostic v1 `agents/base.py` format | Small |
| Crew runner (assemble → execute → aggregate) | New, replaces CrewAI Crew | Medium |

**Exit criteria**: Can define agents in JSON, assemble a crew, execute a task DAG in a single process with native Rust tools.

### Phase 2 — LLM & Tools

| Item | Source | Effort |
|------|--------|--------|
| LlmProvider trait + OpenAI provider | Agnosticos `hoosh` + SY model router | Medium |
| Anthropic, Ollama, Gemini providers | SY provider implementations | Medium |
| Remaining providers (DeepSeek, Mistral, Groq, LM Studio, hoosh) | SY + Agnosticos | Small each |
| Model router (task-complexity scoring) | SY `model-router.ts` | Small |
| Provider health ring buffer + failover | SY health scoring | Small |
| Response cache (LRU + TTL) | SY + Agnosticos | Small |
| Token budget accounting | Agnosticos `hoosh` | Small |
| Rate limiter (semaphore-based) | Agnosticos `rate_limiter.rs` | Small |
| Native Rust tool trait + registry | New (inspired by Agnostic `tool_registry.py`) | Medium |
| WASM tool sandbox (wasmtime) | Agnosticos `sandbox_mod/` | Medium |
| Python tool bridge (sandboxed subprocess) | New | Medium |

**Exit criteria**: Can run a crew that calls LLMs and executes tools (native, WASM, or sandboxed Python).

### Phase 3 — Fleet Distribution

| Item | Source | Effort |
|------|--------|--------|
| Node registry + heartbeat | Agnostic v1 `fleet/registry.py` → Rust | Medium |
| Placement engine (5 scheduling policies) | Agnostic v1 `fleet/placement.py` → Rust | Medium |
| Inter-node relay (Redis pub/sub) | Agnostic v1 `fleet/relay.py` → Rust | Medium |
| Fleet coordinator (fan-out, aggregation, failover) | Agnostic v1 `fleet/coordinator.py` → Rust | Large |
| Crew state manager (barrier sync, checkpoints) | Agnostic v1 `fleet/state.py` → Rust | Medium |
| GPU detection + scheduler | Agnostic v1 `gpu.py` + `gpu_scheduler.py` → Rust | Medium |
| Federation (multi-cluster) | Agnosticos `federation/` | Large |

**Exit criteria**: Can distribute a crew across multiple nodes with lockstep execution, failover, and GPU-aware placement.

### Phase 4 — API Server & Migration

| Item | Source | Effort |
|------|--------|--------|
| axum HTTP server with REST API | New (mirrors Agnostic v1 FastAPI routes) | Medium |
| MCP server (tool advertisement) | Agnostic v1 `routes/mcp.py` | Medium |
| A2A protocol (SY webhooks) | Agnostic v1 `routes/yeoman_webhooks.py` | Medium |
| SSE streaming for crew execution | New | Small |
| JWT auth + AGNOS token delegation | Agnostic v1 `routes/auth.py` | Small |
| Preset library (18 presets) | Agnostic v1 `definitions/presets/` | Small |
| Crew assembler (team spec → agent list) | Agnostic v1 `crew_assembler.py` → Rust | Medium |
| Learning & RL module | Agnosticos `learning.rs` + `rl_optimizer.rs` | Medium |
| Definition versioning & .agpkg packaging | Agnostic v1 `versioning.py` + `packaging.py` | Small |

**Exit criteria**: Full API compatibility with Agnostic v1. Can swap the backend without changing any caller.

### Phase 5 — Agnostic Migration

| Item | Effort | Notes |
|------|--------|-------|
| Feature flag: `AGNOSTIC_BACKEND=agnosai\|crewai` | Small | Default: `crewai` during migration |
| Port existing unit tests to run against both backends | Medium | Assert identical behavior |
| Port E2E tests | Medium | Docker compose with AgnosAI binary |
| Migrate presets one domain at a time | Medium | quality → software-engineering → devops → design → data-engineering |
| Port high-value Python tools to native Rust | Large | Start with most-used: code analysis, security assessment, test generation |
| Community tool SDK (WASM) | Medium | `agnosai-tool-sdk` crate for community tool development |
| Remove CrewAI dependency | Small | Delete `crewai_compat.py`, `requirements.txt` CrewAI entries |
| Remove Python fleet code | Small | Delete `config/fleet/*.py`, `config/gpu*.py` |

**Exit criteria**: Agnostic runs entirely on AgnosAI. Zero Python in the hot path. CrewAI removed.

---

## Dependency Stack

### Rust Dependencies

| Crate | Purpose |
|-------|---------|
| `tokio` | Async runtime (full features) |
| `axum` | HTTP server |
| `reqwest` | HTTP client (LLM providers) |
| `serde` / `serde_json` / `serde_yaml` | Serialization |
| `redis` | Async Redis client |
| `wasmtime` | WASM sandbox runtime |
| `dashmap` | Lock-free concurrent hashmap |
| `thiserror` / `anyhow` | Error handling (thiserror for libs, anyhow for bins) |
| `tracing` | Structured logging + OpenTelemetry |
| `uuid` | Agent/task IDs |
| `chrono` | Timestamps |
| `tonic` | gRPC (fleet inter-node, federation) |
| `rustls` | mTLS for fleet encryption |

### What's NOT Needed

| Removed | Replaced By |
|---------|-------------|
| CrewAI | `agnosai-orchestrator` |
| litellm | `agnosai-llm` (direct HTTP) |
| langchain | Not needed — tools are native/WASM |
| chromadb | Redis + optional external vector DB |
| pydantic | `serde` + Rust type system |
| FastAPI | `axum` |
| Celery + RabbitMQ | `tokio` tasks + Redis streams |
| supervisord | Single binary (like AGNOS argonaut) |

---

## Binary Distribution

AgnosAI compiles to a single static binary (like `secureyeoman-edge`):

```toml
[profile.release]
opt-level = 2
lto = "fat"
strip = true
panic = "abort"
codegen-units = 1
```

| Target | Binary Size (est.) | Boot Time (est.) | Memory (est.) |
|--------|-------------------|-------------------|---------------|
| `agnosai-server` (full) | ~15-25 MB | <2s | 50-150 MB |
| `agnosai-agent` (single agent) | ~8-12 MB | <1s | 20-50 MB |

Compare: Agnostic v1 Python container is ~1.5 GB image, 15-30s boot, 300-500 MB memory.

---

## Success Metrics

| Metric | v1 (Python/CrewAI) | AgnosAI Target |
|--------|-------------------|----------------|
| Container image size | ~1.5 GB | <50 MB |
| Boot to agent-ready | 15-30s | <2s |
| Memory (idle) | 300-500 MB | <100 MB |
| Crew creation latency | ~500ms | <10ms |
| Concurrent crews (single node) | ~5-10 (GIL) | 100+ (real threads) |
| Fleet coordination overhead | ~50ms/msg (Python async) | <1ms/msg (tokio) |
| Dependency count | 200+ (transitive) | ~30 |
| Python in hot path | 100% | 0% |

---

## Relationship to AGNOS

AgnosAI is designed to run standalone OR as a native AGNOS service:

- **Standalone**: Single binary, any Linux, macOS, Windows. Redis optional (in-memory mode for single-node).
- **On AGNOS**: Registers with daimon as a managed service. Uses hoosh for LLM routing. Reports to AGNOS audit chain. Participates in AGNOS federation. Benefits from OS-level sandbox (Landlock, seccomp, dm-verity).

The crate structure means AGNOS can depend on `agnosai-core` and `agnosai-orchestrator` directly — no process boundary for tightly integrated deployments.

---

## Relationship to SecureYeoman

SY continues to use AgnosAI via A2A protocol (HTTP webhooks) — same as today. The API is wire-compatible:

- `POST /api/v1/crews` — same request/response format
- MCP tools — same tool names and schemas
- A2A webhooks — same callback protocol

SY doesn't need to change anything. It just talks to a much faster backend.

---

*Supersedes the previous v2 roadmap (PyO3/maturin fleet wrapper). AgnosAI is a full replacement, not a partial acceleration.*

*See [roadmap.md](roadmap.md) for current v1 work. See [Changelog](../project/changelog.md) for completed work.*
