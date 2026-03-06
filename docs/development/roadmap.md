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

*Last Updated: 2026-03-05 · Test count: 492 (unit) + 19 (e2e) · [Changelog](../project/changelog.md) · [Dependency Watch](dependency-watch.md)*
