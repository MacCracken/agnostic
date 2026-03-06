# ADR-027: Audit Logging & Agent Metrics Dashboard

**Status**: Accepted
**Date**: 2026-03-28
**Authors**: Agnostic team

---

## Context

The platform lacked two operational capabilities:

1. **No audit trail** — security-relevant events (login attempts, task submissions, permission denials, report downloads) were logged alongside application noise with no structured schema. Compliance requirements (SOC 2, ISO 27001) demand a queryable audit trail.

2. **No per-agent visibility** — Prometheus metrics existed (task counters, LLM call duration) but there was no aggregated dashboard view showing per-agent success rates, failure counts, or LLM token consumption. Operators had to query raw Prometheus to understand agent performance.

---

## Decision

### Audit Logging

Add a lightweight structured audit logging module (`shared/audit.py`) that:

- Emits JSON audit events to a dedicated `audit` logger (separate from application logs)
- Defines an `AuditAction` enum covering auth, task, report, tenant, and system events
- Provides a single `audit_log()` function called from API endpoints and auth handlers
- Is log-sink agnostic — outputs to stdout/stderr for consumption by any log aggregator (ELK, Datadog, CloudWatch, etc.)
- Enabled by default (`AUDIT_LOG_ENABLED=true`), configurable log level (`AUDIT_LOG_LEVEL`)

**Event schema:**
```json
{
  "timestamp": "2026-03-28T12:00:00+00:00",
  "event": "audit",
  "action": "task.submitted",
  "actor": "user-123",
  "outcome": "success",
  "resource_type": "task",
  "resource_id": "abc-def",
  "tenant_id": "tenant-1",
  "detail": {}
}
```

**Instrumented points:**
- Auth: login success/failure, logout, token refresh, API key created/deleted/used
- Tasks: submitted, completed, failed
- Reports: generated, downloaded, scheduled, schedule removed
- Tenant: created, updated, deleted, user added/removed
- System: rate limit exceeded, permission denied, path traversal blocked

### Agent Metrics Dashboard

Add per-agent metrics aggregation (`shared/agent_metrics.py`) with two new REST endpoints:

- `GET /api/dashboard/agents` — per-agent task counts, success/failure rates, LLM token usage
- `GET /api/dashboard/llm` — aggregated LLM call counts, error rates, breakdown by method

Add LLM token counters (`LLM_TOKENS_PROMPT`, `LLM_TOKENS_COMPLETION`) to `shared/metrics.py` with `(agent, method)` labels. Instrument `LLMIntegrationService` to record `response.usage.prompt_tokens` and `completion_tokens` from litellm responses.

Metrics are read directly from in-process Prometheus metric objects — no scraping or external Prometheus server required.

---

## Consequences

### Positive

- Compliance-ready audit trail with structured JSON output
- Per-agent operational visibility without external tooling
- Token usage tracking enables cost monitoring and budgeting
- Both features are opt-in and have no-op fallbacks (audit disabled, Prometheus unavailable)
- Audit events are decoupled from storage — can be consumed by any log aggregator

### Negative

- Audit logging adds a small overhead per auditable API call (JSON serialization + log write)
- In-process metric reading (`collect()`) is a prometheus_client internal — may change across versions

### Risks

- High-volume audit logs need log rotation or streaming to avoid disk fill — mitigated by using standard logging handlers
- Prometheus metric cardinality grows with agent × method combinations — bounded by the fixed set of 6 agents and ~6 LLM methods

---

## Alternatives Considered

1. **Database-backed audit table** — rejected as over-engineering for current scale; structured logs are queryable by any log aggregator and don't add database load
2. **Separate audit microservice** — unnecessary complexity; a dedicated logger within the process is sufficient
3. **Grafana dashboards only** — requires external Grafana setup; the REST endpoints provide dashboard data without infrastructure dependencies
4. **OpenTelemetry spans for audit** — heavier dependency; structured logs are simpler and more universally consumable

---

## References

- ADR-015: Observability Stack
- OWASP Logging Cheat Sheet
- SOC 2 audit log requirements
