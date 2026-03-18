# Roadmap v2 — Rust Core

> Future vision. Not scheduled. Triggered when fleet runs at scale and benchmarks prove Python is the bottleneck.

Rewrite the performance-critical infrastructure layer in Rust. Python remains the agent execution boundary (CrewAI, LLM calls, tool registry). The split mirrors how AGNOS already works: Rust core with Python agent workers.

---

## Motivation

The fleet coordination layer (node registry, placement engine, relay, coordinator, crew state, barrier sync) is concurrent stateful systems code — Rust's sweet spot. Python's GIL and async overhead will become bottlenecks when fleet runs at scale with dozens of nodes and hundreds of concurrent crews.

---

## Rust Core Candidates

In priority order — these are the modules that would benefit most from a Rust rewrite.

| # | Module | Current location | Why Rust |
|---|--------|-----------------|----------|
| 1 | Fleet registry & heartbeat | `config/fleet/registry.py` | High-frequency Redis writes, concurrent node tracking, TTL management |
| 2 | Placement engine | `config/fleet/placement.py` | Deterministic scheduling across many nodes, needs to be fast and predictable |
| 3 | Inter-node relay | `config/fleet/relay.py` | Redis pub/sub message ordering, sequence dedup, high throughput |
| 4 | Fleet coordinator | `config/fleet/coordinator.py` | Concurrent result collection, health monitoring, failover — all GIL-sensitive |
| 5 | Crew state manager | `config/fleet/state.py` | Redis optimistic locking, barrier sync, checkpoint persistence |
| 6 | GPU scheduler | `config/gpu_scheduler.py` | Multi-device assignment, memory tracking, cross-crew slot management |
| 7 | GPU detection | `config/gpu.py` | nvidia-smi parsing, cached probing — light but benefits from zero-cost abstractions |

---

## Python Boundary (stays Python)

These modules depend on the Python ML/AI ecosystem and would not benefit from a Rust rewrite.

| Module | Why Python |
|--------|-----------|
| Agent definitions & factory | CrewAI `Agent`/`Crew`/`Task` are Python classes |
| LLM integration | litellm, anthropic SDK, OpenAI SDK — all Python |
| Tool registry | Tools are Python `BaseTool` subclasses, dynamic loading via `exec()` |
| Crew assembler | NLP-style fuzzy matching, keyword scoring — Python-native |
| Local inference routing | litellm model routing, Ollama/vLLM clients — Python ecosystem |
| WebGUI / FastAPI | REST API, Chainlit app — Python web framework |

---

## Integration Approach

Rust core exposes a Python API via **PyO3/maturin**. The fleet modules become an `agnostic-fleet` Rust crate compiled as a Python extension module.

```python
# Drop-in replacement — same API, 10-100x faster internals
from agnostic_fleet import FleetRegistry, PlacementEngine, TaskRelay, CrewStateManager
```

The Python side calls into Rust for all fleet operations. Agent execution remains pure Python. The boundary is clean: Rust handles infrastructure (Redis, scheduling, messaging), Python handles AI (CrewAI, LLM, tools).

### Crate structure

```
agnostic-fleet/
├── Cargo.toml
├── pyproject.toml          # maturin build config
├── src/
│   ├── lib.rs              # PyO3 module entry point
│   ├── registry.rs         # FleetRegistry — node inventory, heartbeat
│   ├── placement.rs        # PlacementEngine — scheduling policies
│   ├── relay.rs            # TaskRelay — Redis pub/sub message passing
│   ├── coordinator.rs      # FleetCoordinator — crew lifecycle
│   ├── state.rs            # CrewStateManager — distributed crew state
│   ├── gpu_scheduler.rs    # GPU scheduling + slot tracking
│   └── gpu_detect.rs       # nvidia-smi probing
└── tests/
```

### Dependencies

- `redis` (Rust) — async Redis client
- `pyo3` — Python bindings
- `tokio` — async runtime
- `serde` / `serde_json` — serialization

---

## Prerequisites

All of these must be true before starting the v2 rewrite:

- [ ] Fleet running at scale (real multi-node deployments, not just dev)
- [ ] Benchmarks showing Python GIL / async as the bottleneck in fleet operations
- [ ] AGNOS fleet infrastructure stable (node registration, heartbeat, scheduling all production-proven)
- [ ] v1 Python fleet code has been exercised in production for 3+ months
- [ ] PyO3/maturin build pipeline established (CI, wheel publishing, cross-platform)

---

## Migration Strategy

1. **Parallel implementation** — build `agnostic-fleet` crate alongside existing Python modules
2. **Feature flag** — `AGNOSTIC_FLEET_BACKEND=rust|python` (default: python) switches between implementations
3. **Compatibility tests** — run the existing 32 fleet unit tests against both backends, assert identical behavior
4. **Gradual rollout** — one module at a time (registry first, then placement, then relay)
5. **Deprecate Python fleet** — once all modules are ported and stable, remove `config/fleet/*.py`

---

*See [roadmap.md](roadmap.md) for current v1 work. See [Changelog](../project/changelog.md) for completed work.*
