# Roadmap

Pending development work for the Agentic QA Team System, ordered by priority. Completed work is tracked in the [Changelog](../project/changelog.md).

See [Dependency Watch](dependency-watch.md) for upstream blockers that affect timeline.

---

## Near-term

### Multi-Tenant Hardening
**Priority:** High

Tenant CRUD endpoints are wired to `TenantRepository` with real database operations. Runtime tenant isolation is implemented for task submit/get and API key validation.

- [x] Wire `TenantRepository` into tenant API endpoints
- [x] Unit tests for `TenantManager`, `TenantRepository`, and endpoints (52 tests)
- [x] Integrate tenant isolation into session/task management (tenant-scoped Redis keys in submit_task, get_task, _run_task_async)
- [x] Tenant-scoped API key validation (wired into `get_current_user`)
- [x] Rate limiting per tenant (sliding-window check in submit_task, 429 response)
- [x] Tenant data isolation tests — 12 tests covering key isolation, endpoint cross-tenant leakage, rate limit independence, API key scoping, quota isolation (`tests/unit/test_tenant_isolation.py`)
- [x] Tenant provisioning documentation (`docs/api/tenant-provisioning.md`)

---

## Medium-term

### WebSocket Reconnection & Missed Message Recovery
**Priority:** Medium

ADR-023 notes Redis pub/sub is fire-and-forget — disconnected clients lose messages. MCP bridge falls back to polling, but a proper recovery mechanism would be better.

- [ ] Message buffering for disconnected subscribers (Redis Streams or similar)
- [ ] Client-side reconnection with last-seen message ID
- [ ] Update ADR-023

### Scheduled Report Delivery
**Priority:** Medium

APScheduler generates reports on schedule but has no delivery mechanism beyond API retrieval.

- [ ] Persistent job store (database-backed, not in-memory) — currently uses Redis
- [ ] Report delivery channels (email, Slack webhook)
- [ ] Tenant-scoped scheduled reports (depends on multi-tenant completion)

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

## Recently Completed

| Item | Date |
|------|------|
| Tag release 2026.3.5 — changelog updated | 2026-03-05 |
| Alembic database migrations — async PostgreSQL, initial migration (7 tables) | 2026-03-05 |
| Migration docs — Alembic section added to `docs/development/setup.md` | 2026-03-05 |
| Scheduled reports test coverage — 27 tests in `test_scheduled_reports.py` | 2026-03-05 |
| Configurable YEOMAN thresholds — `YEOMAN_COVERAGE_THRESHOLD`, `YEOMAN_ERROR_RATE_THRESHOLD`, `YEOMAN_PERF_DEGRADATION_FACTOR` | 2026-03-05 |
| Webhook callback retry — exponential backoff (1s/2s/4s), configurable `WEBHOOK_MAX_RETRIES` | 2026-03-05 |
| WebSocket realtime test hang fix | 2026-03-05 |
| pytest collection warning fix (`__test__ = False`) | 2026-03-05 |
| TODO.md consolidated into roadmap | 2026-03-05 |

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
