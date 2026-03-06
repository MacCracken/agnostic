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

- [x] Rate limiting for all API endpoints — `RateLimitMiddleware` on all `/api/*` paths with per-IP sliding window; configurable via `RATE_LIMIT_MAX_REQUESTS`, `RATE_LIMIT_WINDOW_SECONDS`; returns 429 with `Retry-After` and `X-RateLimit-*` headers
- [x] Request tracing — `CorrelationIdMiddleware` generates/propagates `X-Correlation-ID` on every request; bound to structlog contextvars and audit log events
- [x] Database connection pooling tuning — added `DB_POOL_TIMEOUT` env var, pool config logging on startup, `close_db()` in shutdown handler to prevent connection leaks

### New Features
**Priority:** Medium

- [ ] Test result diffing — compare sessions to detect regressions across runs
- [x] Notification system — `AlertManager` with webhook/Slack/email delivery, cooldown throttling; `HealthMonitor` background task polls health state and fires alerts on transitions (degraded, unhealthy, agent offline/stale); circuit breaker `on_state_change` callback; configurable via `ALERTS_ENABLED`, `ALERT_POLL_INTERVAL_SECONDS`, `ALERT_COOLDOWN_SECONDS`
- [x] API pagination — all list endpoints return `{items, total, limit, offset}` with `limit`/`offset` query params; paginated: reports, scheduled reports, agents, tenants, tenant users, API keys
- [x] OpenAPI client SDK generation — `scripts/generate-sdk.sh` fetches OpenAPI schema (live or offline) and generates Python (`openapi-python-client`) and TypeScript (`openapi-generator-cli`) client SDKs

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

*Last Updated: 2026-03-05 · Test count: 471 (unit) + 19 (e2e) · [Changelog](../project/changelog.md) · [Dependency Watch](dependency-watch.md)*
