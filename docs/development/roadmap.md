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

## Engineering Backlog

Items identified during code review and audit. Not blocking, but should be addressed over time.

### Security Hardening

| Item | Effort | Notes |
|------|--------|-------|
| Process-level sandbox for `load_tool_from_source()` | Medium | Current `exec()` restricted builtins is defense-in-depth only. Add nsjail/gVisor/WASM isolation for untrusted tool code |
| `.agpkg` import: multipart file upload endpoint | Small | Currently only Python API; HTTP file upload endpoint is a stub (removed). Implement via FastAPI `UploadFile` |
| Symlink traversal in `factory.from_file()` | Small | `Path.resolve()` is called but not validated against an allowed base directory. Symlinks could escape |

### Code Quality

| Item | Effort | Notes |
|------|--------|-------|
| `AgentDefinition` → Pydantic model or dataclass | Medium | Currently a plain class with manual `__init__`/`to_dict`/`from_dict`. Inconsistent with rest of codebase |
| Extract `require_admin` FastAPI dependency | Small | Admin role check `user.get("role") not in ("super_admin", "org_admin")` duplicated 7+ times. Should be a reusable `Depends()` |
| Status string enum | Small | `"completed"`, `"failed"`, `"pending"`, `"running"`, `"partial"` scattered as bare strings. Should be a shared `Status` enum |
| `_run_crew_async()` function split | Small | 147 lines with 2 nested functions. Split into `_build_agents`, `_execute_agents`, `_finalize_crew` |
| `import_package()` loop dedup | Small | Definition and preset install loops are nearly identical. Extract `_install_entries()` helper |
| Background task reference tracking | Small | `asyncio.create_task` references not tracked in a set. Standard pattern: `tasks.add(t); t.add_done_callback(tasks.discard)` |
| `asyncio.Lock()` at module scope in `tasks.py` | Small | Pre-existing. `_webhook_client_lock` created at import time; may fail in Python 3.12+ if imported before event loop |

### Test Coverage

| Item | Effort | Notes |
|------|--------|-------|
| ZIP bomb / entry count limit tests | Small | `_MAX_UNCOMPRESSED_SIZE` and `_MAX_ENTRY_COUNT` checks have no test |
| `AgentFactory.invalidate_cache()` selective test | Small | Only full-clear tested; path-specific invalidation untested |
| YAML definition loading test | Small | `factory.from_file()` YAML branch untested |
| `_run_crew_async()` integration test | Medium | Background execution mocked away in current tests |
| `delegate_to()` edge cases | Small | Invalid key rejection, missing file, delegation failure untested |
| `rollback_definition` endpoint test | Small | API-level rollback test missing |

---

## Long-term / Blocked

| Item | Blocker |
|------|---------|
| Python 3.14 support | crewai 1.10.1 `requires-python <3.14` — sole remaining blocker. chromadb 1.1.1 is now unblocked (`>=3.9`). See [Dependency Watch](dependency-watch.md) |

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

*Last Updated: 2026-03-14 · Version: 2026.3.14 · Test count: 922 (unit) + 24 (e2e) · [Changelog](../project/changelog.md) · [Dependency Watch](dependency-watch.md)*
