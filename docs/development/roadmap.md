# Roadmap

Pending development work for the Agentic QA Team System, ordered by priority. Completed work is tracked in the [Changelog](../project/changelog.md).

See [Dependency Watch](dependency-watch.md) for upstream blockers that affect timeline.

---

## Near-term

No near-term items remaining. See [Recently Completed](#recently-completed) and the [Changelog](../project/changelog.md).

---

## Medium-term

No medium-term items remaining. See [Recently Completed](#recently-completed) and the [Changelog](../project/changelog.md).

---

## Long-term / Blocked

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
| Email delivery channel — SMTP via aiosmtplib, TLS, multi-recipient | 2026-03-28 |
| Persistent database job store — SQLAlchemy backend for APScheduler | 2026-03-28 |
| Alembic migration for `apscheduler_jobs` table | 2026-03-28 |
| ADR-026 — Scheduled report enhancements | 2026-03-28 |
| Scheduled Report Delivery — all items complete | 2026-03-28 |
| WebSocket reconnection — Redis Streams message buffering + replay | 2026-03-05 |
| Report delivery — webhook (HMAC) + Slack + tenant-scoped reports | 2026-03-05 |
| ADR-023 updated with reconnection protocol | 2026-03-05 |
| Multi-tenant hardening complete — all 7 near-term items done | 2026-03-05 |
| Tenant provisioning docs (`docs/api/tenant-provisioning.md`) | 2026-03-05 |
| Tenant data isolation tests — 12 tests (`test_tenant_isolation.py`) | 2026-03-05 |
| Tenant-scoped Redis keys wired into task submit/get/run | 2026-03-05 |
| Tenant-scoped API key validation in `get_current_user` | 2026-03-05 |
| Per-tenant rate limiting (sliding window, HTTP 429) | 2026-03-05 |
| Tenant manager unit tests — 52 total (`test_tenant.py`) | 2026-03-05 |
| Webhook callback retry — exponential backoff, `WEBHOOK_MAX_RETRIES` | 2026-03-05 |
| Configurable YEOMAN thresholds — env-var driven | 2026-03-05 |
| Alembic database migrations — async PostgreSQL, 7 tables | 2026-03-05 |
| Scheduled reports test coverage — 27 tests | 2026-03-05 |
| WebSocket realtime test hang fix | 2026-03-05 |
| pytest collection warning fix (`__test__ = False`) | 2026-03-05 |
| TODO.md consolidated into roadmap | 2026-03-05 |
| Tag release 2026.3.5 | 2026-03-05 |

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

*Last Updated: 2026-03-28 · Test count: 421 · [Changelog](../project/changelog.md) · [Dependency Watch](dependency-watch.md)*
