# ADR-026: Scheduled Report Enhancements — Email Delivery & Persistent Job Store

**Status**: Accepted
**Date**: 2026-03-28
**Authors**: Agnostic team

---

## Context

The scheduled report system (ADR-004, implemented in `webgui/scheduled_reports.py`) supports two delivery channels — webhook (HMAC-signed HTTP POST) and Slack (incoming webhook). Two gaps remain:

1. **No email delivery** — many teams rely on email for report distribution, especially for stakeholders who don't monitor Slack or webhook endpoints.
2. **Redis-only job store** — APScheduler jobs are stored in Redis. If Redis is flushed or restarted without persistence, all scheduled jobs are lost. For production deployments with `DATABASE_ENABLED=true`, a database-backed store is more durable.

---

## Decision

### Email Delivery Channel

Add SMTP-based email delivery as a third channel in `ReportDeliveryService`. The implementation:

- Uses `aiosmtplib` for async SMTP communication (TLS/STARTTLS supported)
- Constructs HTML emails via stdlib `email.mime` (no template engine dependency)
- Sends to a configurable recipient list (`REPORT_EMAIL_RECIPIENTS`, comma-separated)
- Follows the same retry pattern as webhook/Slack (exponential backoff, `REPORT_DELIVERY_MAX_RETRIES`)
- Enabled via `REPORT_EMAIL_ENABLED=true` (disabled by default)

**Configuration:**

| Variable | Default | Purpose |
|----------|---------|---------|
| `REPORT_EMAIL_ENABLED` | `false` | Enable email delivery |
| `SMTP_HOST` | — | SMTP server hostname |
| `SMTP_PORT` | `587` | SMTP port (587 = STARTTLS, 465 = SSL) |
| `SMTP_USERNAME` | — | SMTP authentication username |
| `SMTP_PASSWORD` | — | SMTP authentication password |
| `SMTP_USE_TLS` | `true` | Use STARTTLS |
| `SMTP_FROM` | — | Sender address |
| `REPORT_EMAIL_RECIPIENTS` | — | Comma-separated recipient list |

### Persistent Database Job Store

Add SQLAlchemy as an alternative APScheduler job store backend. The implementation:

- Uses APScheduler's built-in `SQLAlchemyJobStore` with a sync `psycopg2` connection (APScheduler 3.x does not support async engines for job stores)
- Creates an `apscheduler_jobs` table matching APScheduler's expected schema (id, next_run_time, job_state)
- Managed via Alembic migration for consistent schema management
- Selected via `SCHEDULER_JOBSTORE=database` when `DATABASE_ENABLED=true`
- Falls back to Redis when database is not available or not configured

| Variable | Default | Purpose |
|----------|---------|---------|
| `SCHEDULER_JOBSTORE` | `redis` | Job store backend: `redis` or `database` |

---

## Consequences

### Positive

- Reports can be delivered to stakeholders who only use email
- Scheduled jobs survive Redis restarts when database job store is configured
- All three delivery channels (webhook, Slack, email) follow the same retry pattern
- Database job store reuses the existing PostgreSQL infrastructure — no new services required
- Both features are opt-in and backward-compatible

### Negative

- `aiosmtplib` adds a new dependency for email delivery
- `psycopg2-binary` adds a sync PostgreSQL driver alongside the async `asyncpg` (needed because APScheduler 3.x job stores are synchronous)
- Email delivery introduces a dependency on external SMTP infrastructure

### Risks

- SMTP servers may rate-limit or block bulk sends — mitigated by retry logic and configurable recipient lists
- APScheduler 4.x (when released) will have native async job stores, making the sync `psycopg2` bridge unnecessary — migration path is straightforward

---

## Alternatives Considered

1. **Template engine for emails** (Jinja2) — rejected as over-engineering; HTML is simple enough to construct inline
2. **APScheduler 4.x async job store** — not yet released; using 3.x built-in SQLAlchemyJobStore is stable and well-tested
3. **Custom async job store wrapper** — unnecessary complexity when APScheduler's sync store works correctly with the async scheduler
4. **SendGrid/SES API instead of SMTP** — SMTP is more portable and doesn't lock into a specific provider

---

## References

- [APScheduler SQLAlchemyJobStore docs](https://apscheduler.readthedocs.io/en/3.x/modules/jobstores/sqlalchemy.html)
- [aiosmtplib docs](https://aiosmtplib.readthedocs.io/)
- ADR-004: Report Generation Strategy
- ADR-025: Test Result Persistence
