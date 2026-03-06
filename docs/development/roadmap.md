# Roadmap

Pending development work for the Agentic QA Team System, ordered by priority. Completed work is tracked in the [Changelog](../project/changelog.md).

See [Dependency Watch](dependency-watch.md) for upstream blockers that affect timeline.

---

## Near-term

### Code Quality & Architecture
**Priority:** High

- [ ] Split `webgui/api.py` into route modules — auth, tasks, reports, tenants, agents, dashboard (currently 1800+ lines, 85+ endpoints)
- [ ] Split `AuthManager` into `TokenManager`, `OAuthProviderFactory`, `PermissionValidator` (currently 25+ methods mixing auth, tokens, permissions)
- [ ] Add YEOMAN MCP tools for new endpoints — `agnostic_session_diff`, `agnostic_structured_results`, `agnostic_quality_trends` (endpoints exist, tools missing)

---

## Medium-term

### Test Coverage
**Priority:** Medium

- [ ] Add unit tests for untested modules — `shared/rate_limit.py`, `shared/crewai_compat.py`, `shared/data_generation_service.py`, `webgui/app.py`, `webgui/agent_monitor.py`, `webgui/dashboard.py`, `webgui/history.py`

---

## SecureYeoman Integration

### MCP Tool Gaps
**Priority:** High — aligns with near-term MCP item above.

SecureYeoman's MCP manifest (`packages/mcp/src/tools/manifest.ts`) is the sole source for AI-visible tools. The three missing tools noted in near-term (`agnostic_session_diff`, `agnostic_structured_results`, `agnostic_quality_trends`) should be registered there after implementation. Additional candidates:

- [ ] **QA orchestration tools** — Expose `qa-manager` task creation and agent dispatch via MCP so SecureYeoman personalities can trigger QA runs conversationally
- [ ] **Security scan results** — Surface `senior-qa` security findings as structured MCP tool output for SecureYeoman's DLP/compliance pipeline
- [ ] **Quality trend dashboard data** — Feed agent quality metrics into SecureYeoman's observability (OpenTelemetry integration, Phase 139)

### Docker Base Image Migration
**Priority:** Medium — depends on agnosticos Alpha release (Q2 2026).

- [ ] **Migrate per-agent Dockerfiles to agnosticos base** — Current setup uses individual Dockerfiles per agent service. Once AGNOS ships Alpha, switch to `FROM agnos:latest` for the hardened Rust runtime, sandboxed execution, and audit-chain integration. The `agent-runtime` binary in agnosticos provides resource quotas and IPC backpressure that replaces custom container resource limits.
- [ ] **LLM Gateway consolidation** — Agnostic's `universal_llm_adapter.py` and agnosticos's `llm-gateway` (OpenAI-compatible on :8088) overlap. Evaluate routing agent LLM calls through the gateway instead of direct provider calls, gaining request-level audit logging and model routing.

### REST API Proxy
**Priority:** Low — `webgui/api.py` has 85+ endpoints.

- [ ] **`registerApiProxyTool()` wiring** — SecureYeoman's `tool-utils.ts` has a factory for proxying GET/POST endpoints as MCP tools. Once `api.py` is split into route modules (near-term item), register high-value endpoints (session management, test results, agent status) as proxy tools for zero-code MCP integration.

---

## Long-term / Blocked

No long-term items remaining. See [Dependency Watch](dependency-watch.md) for upstream blockers.

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

---

*Last Updated: 2026-03-05 · Test count: 494 (unit) + 19 (e2e) · [Changelog](../project/changelog.md) · [Dependency Watch](dependency-watch.md)*
