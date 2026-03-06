# Roadmap

Pending development work for the Agentic QA Team System, ordered by priority. Completed work is tracked in the [Changelog](../project/changelog.md).

See [Dependency Watch](dependency-watch.md) for upstream blockers that affect timeline.

---

## Near-term

No near-term items remaining. See the [Changelog](../project/changelog.md).

---

## Medium-term

### Hardening & Operational Improvements
**Priority:** Medium

- [ ] Rate limiting for all API endpoints — currently only tenant task submission has sliding-window limiting
- [ ] Request tracing — correlation IDs across API → Redis → agent → webhook
- [ ] Database connection pooling tuning — stress test async pool under load

### New Features
**Priority:** Medium

- [ ] Test result diffing — compare sessions to detect regressions across runs
- [ ] Notification system — real-time alerts on agent failures, circuit breaker trips, degraded health (beyond scheduled reports)
- [ ] API pagination — list endpoints currently return unbounded results
- [ ] OpenAPI client SDK generation — auto-generate Python/TypeScript clients from FastAPI schema

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

*Last Updated: 2026-03-05 · Test count: 465 (unit) + 19 (e2e) · [Changelog](../project/changelog.md) · [Dependency Watch](dependency-watch.md)*
