# Roadmap

Pending development work for the Agentic QA Team System, ordered by priority. Completed work is tracked in the [Changelog](../project/changelog.md).

See [Dependency Watch](dependency-watch.md) for upstream blockers that affect timeline.

---

## Near-term

### Cut Release 2026.3.5
**Priority:** High

The `[Unreleased]` changelog section has grown large (WebSocket bridge, structured schemas, test persistence, multi-tenant, AGNOS Agent HUD, Prometheus ServiceMonitor, scheduled reports, GitOps/ArgoCD). Commit outstanding changes, tag and release.

- [ ] Commit database model fix (`metadata` → `extra_metadata` rename)
- [ ] Commit new ADRs (023, 024, 025)
- [ ] Commit new unit tests (agent registration, database models, yeoman schemas, yeoman websocket)
- [ ] Run full test suite, confirm all 289+ tests pass
- [ ] Tag release `2026.3.5`

### Database Schema Migrations
**Priority:** High

ADR-025 notes PostgreSQL persistence is live but has no automated migration tooling. Schema changes will break existing databases without it.

- [ ] Add Alembic for SQLAlchemy migration management
- [ ] Generate initial migration from current models
- [ ] Document migration workflow in `docs/development/setup.md`

### Multi-Tenant Testing & Hardening
**Priority:** High

Multi-tenant support (`shared/database/tenants.py`) is implemented but lacks integration tests and production hardening.

- [ ] Integration tests for tenant isolation (data leakage prevention)
- [ ] Tenant-scoped API key validation tests
- [ ] Rate limiting per tenant
- [ ] Document tenant provisioning workflow

---

## Medium-term

### Configurable YEOMAN Action Thresholds
**Priority:** Medium

ADR-024 notes that action thresholds in `shared/yeoman_schemas.py` are hardcoded (80% coverage, 5% error rate, 2x response time degradation). These should be configurable per-project or per-tenant.

- [ ] Extract thresholds to config (env vars or database)
- [ ] Allow per-tenant threshold overrides
- [ ] Update ADR-024

### WebSocket Reconnection & Missed Message Recovery
**Priority:** Medium

ADR-023 notes Redis pub/sub is fire-and-forget — disconnected clients lose messages. MCP bridge falls back to polling, but a proper recovery mechanism would be better.

- [ ] Message buffering for disconnected subscribers (Redis Streams or similar)
- [ ] Client-side reconnection with last-seen message ID
- [ ] Update ADR-023

### Scheduled Report Enhancements
**Priority:** Medium

Basic APScheduler integration is in place. Production needs:

- [ ] Persistent job store (database-backed, not in-memory)
- [ ] Report delivery (email, Slack webhook)
- [ ] Tenant-scoped scheduled reports

---

## Long-term / Blocked

### Python 3.14 Support
**Priority:** Low (blocked upstream)

The local dev environment uses Python 3.14, which cannot install crewai 1.x because `chromadb` uses `pydantic.v1.BaseSettings` (removed in Python 3.14). Production Docker containers run Python 3.11 and are unaffected.

Unblocked when chromadb migrates to `pydantic-settings`. See [Dependency Watch](dependency-watch.md).

### Full E2E Test Suite
**Priority:** Low

Manual testing guide exists (`docs/development/manual-testing.md`) but automated E2E tests (Docker Compose up, submit task, verify results) are not yet implemented.

- [ ] Docker Compose test harness
- [ ] Automated smoke test (health check, task submit, report download)
- [ ] CI integration for E2E suite

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

*Last Updated: 2026-03-05 · [Changelog](../project/changelog.md) · [Dependency Watch](dependency-watch.md)*
