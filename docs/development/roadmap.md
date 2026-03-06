# Roadmap

Pending development work for the Agentic QA Team System, ordered by priority. Completed work is tracked in the [Changelog](../project/changelog.md).

See [Dependency Watch](dependency-watch.md) for upstream blockers that affect timeline.

---

## Medium-term

### Test Coverage
**Priority:** Medium

- [ ] Add unit tests for untested modules — `shared/rate_limit.py`, `shared/crewai_compat.py`, `shared/data_generation_service.py`, `webgui/app.py`, `webgui/agent_monitor.py`, `webgui/dashboard.py`, `webgui/history.py`

---

## SecureYeoman Integration

### Docker Base Image Migration
**Priority:** Medium — depends on agnosticos Alpha release (Q2 2026).

- [ ] **Migrate per-agent Dockerfiles to agnosticos base** — Current setup uses individual Dockerfiles per agent service. Once AGNOS ships Alpha, switch to `FROM agnos:latest` for the hardened Rust runtime, sandboxed execution, and audit-chain integration. The `agent-runtime` binary in agnosticos provides resource quotas and IPC backpressure that replaces custom container resource limits.

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

*Last Updated: 2026-03-05 · Test count: 451 (unit) + 19 (e2e) · [Changelog](../project/changelog.md) · [Dependency Watch](dependency-watch.md)*
