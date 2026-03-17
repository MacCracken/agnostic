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
| GPU-aware crew scheduling | Medium | Detect available GPU on AGNOS host via `agnosys` GPU probe. Route compute-intensive agents to GPU-enabled nodes. Inspired by NemoClaw's compute-aware routing |
| Crew status in AGNOS HUD | Medium | Push crew lifecycle events to AGNOS daimon for display in aethersafha HUD. Use `GET /crews` with status filter |
| Crew cancellation from agnoshi | Small | Wire `POST /crews/{crew_id}/cancel` to AGNOS MCP tool `agnostic_cancel_crew` and agnoshi intent "cancel crew {id}" |
| AGNOS fleet crew distribution | Large | Distribute crew agents across AGNOS edge fleet. Agent 1 runs on device A (has GPU), Agent 2 on device B. Requires fleet-aware orchestrator |

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

### Security Hardening

| Item | Effort | Notes |
|------|--------|-------|
| Process-level sandbox for `load_tool_from_source()` | Medium | Current `exec()` restricted builtins is defense-in-depth only. Add nsjail/gVisor/WASM isolation for untrusted tool code |
| `.agpkg` import: multipart file upload endpoint | Small | Currently only Python API; HTTP file upload endpoint removed. Implement via FastAPI `UploadFile` |
| Symlink traversal in `factory.from_file()` | Small | Add `resolved.is_relative_to(DEFINITIONS_DIR)` check after `Path.resolve()` |
| Rate limiting on definition/preset/tool endpoints | Small | No per-user rate limits on CRUD mutations or tool upload |
| Re-validate callback URL at webhook fire time in `_run_crew_async` | Small | SSRF check only at request time; stored config could be tampered |

### Performance

| Item | Effort | Notes |
|------|--------|-------|
| Async file I/O in definition/preset endpoints | Medium | `list_definitions`, `get_definition`, `create_definition`, etc. do sync `open()`/`json.load()` on the event loop. Use `aiofiles` or `run_in_executor` |
| TTL cache for `list_definitions` / `list_presets` | Small | Re-scans filesystem on every request. Add 5s in-memory TTL cache (matches dashboard pattern) |
| Shared infrastructure for crew agents | Medium | Each `BaseAgent` creates own Redis client + Celery app. Crew of 6 = 6 connections. Share across agents in same crew |
| `export_package` sync ZIP on event loop | Small | Synchronous `zipfile.ZipFile` in async handler blocks under load |

### Code Quality

| Item | Effort | Notes |
|------|--------|-------|
| `AgentDefinition` → Pydantic model or dataclass | Medium | Currently a plain class with manual `__init__`/`to_dict`/`from_dict`. Inconsistent with rest of codebase |
| Extract `require_admin` FastAPI dependency | Small | Admin role check duplicated 7+ times. Should be reusable `Depends()` |
| Status string enum | Small | `"completed"`, `"failed"`, `"pending"`, `"running"`, `"partial"` scattered as bare strings |
| `_run_crew_async()` function split | Small | 147 lines. Split into `_build_agents`, `_execute_agents`, `_finalize_crew` |
| `import_package()` loop dedup | Small | Definition and preset install loops nearly identical |
| Background task reference tracking | Small | `asyncio.create_task` refs not tracked in a set |
| `asyncio.Lock()` at module scope in `tasks.py` | Small | Pre-existing; may fail in Python 3.12+ |
| Version pruning | Small | `save_version` creates unlimited `v{N}.json` files. Add max-versions cap with oldest eviction |

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
| Definition list scalability | Small | Measure `GET /definitions` at 10/50/200/500 files |
| Crew creation throughput | Medium | Concurrent `POST /crews` (1/5/10/20 simultaneous) — thread pool saturation |
| Crew execution by agent count | Medium | Wall time for 1/3/6/10 agent crews |
| Package import/export large bundles | Small | 50 definitions + 10 presets export; 100-entry import |
| Production metrics | Medium | Add Prometheus gauges: `agnostic_crew_run_duration_seconds`, `agnostic_tool_registry_size`, `agnostic_active_crew_tasks`, `agnostic_definition_cache_hits` |

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

*Last Updated: 2026-03-17 · Version: 2026.3.16 · Test count: 922 (unit) + 24 (e2e) · [Changelog](../project/changelog.md) · [Dependency Watch](dependency-watch.md)*
