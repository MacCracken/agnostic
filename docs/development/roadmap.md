# Roadmap

Pending development work for the Agentic QA Team System, ordered by priority. Completed work is tracked in the [Changelog](../project/changelog.md).

See [Dependency Watch](dependency-watch.md) for upstream blockers that affect timeline.

---

## Near-term

### WebSocket Real-Time Dashboard
**Priority:** High

Wire `/ws/realtime` WebSocket endpoint to the existing `webgui/realtime.py` infrastructure and Redis Pub/Sub channel (`REDIS_PUBSUB_CHANNEL`). Enables the dashboard to push task progress, agent status changes, and session events without polling.

YEOMAN MCP tools that call `agnostic_task_status` currently poll `GET /api/tasks/{id}` — WebSocket push lets the bridge subscribe once and receive completion events.

**Files:** `webgui/realtime.py`, `webgui/app.py`, `webgui/static/js/`

---

### Scheduled Report Generation
**Priority:** Medium-High

Integrate APScheduler or Celery Beat for automated periodic report generation (daily executive summary, weekly compliance report). Configurable per-team via environment variables or a future admin UI. Complements the current on-demand `POST /api/reports/generate` endpoint.

---

### Grafana / Prometheus Observability Stack
**Priority:** High

- `ServiceMonitor` CRD for Prometheus scraping of `/api/metrics`
- Grafana dashboard JSON for agent metrics (tasks, LLM calls, circuit breaker state)
- AlertManager rules for critical thresholds (agent offline, circuit breaker open, queue depth)

---

### GitOps / ArgoCD Integration
**Priority:** Medium-High

- ArgoCD `ApplicationSet` for multi-environment promotion (dev → staging → prod)
- Sealed Secrets or External Secrets Operator for secret rotation
- Helm chart published to OCI registry

---

## Medium-term

### Test Result Persistence
**Priority:** Medium

PostgreSQL or SQLite backend for test result history, replacing Redis-only storage. Enables time-series quality metrics, historical comparison API, and long-term trend dashboards.

---

### Multi-Tenant WebGUI
**Priority:** Medium

Tenant-scoped Redis keyspaces, per-team RabbitMQ vhosts, tenant-aware session management, admin dashboard for tenant provisioning.

---

### AGNOS OS Phase 2 — Agent HUD Registration
**Priority:** High (for AGNOS OS users)

Register Agnostic CrewAI agents as agnosticos agents via the `agnos-sys` SDK. Surfaces agents in the AGNOS Agent HUD and security UI. Requires Phase 1 (LLM Gateway routing, config-only — complete) as a prerequisite.

See [ADR-021](../adr/021-agnosticos-integration.md).

---

### AGNOS OS Phase 3 — Native MessageBus
**Priority:** Medium

Replace Redis/RabbitMQ inter-agent messaging with the agnosticos MessageBus for native OS IPC. Optional — Redis/RabbitMQ remains the default.

---

## Long-term / Blocked

### Python 3.14 Support
**Priority:** Low (blocked upstream)

The local dev environment uses Python 3.14, which cannot install crewai 1.x because `chromadb` uses `pydantic.v1.BaseSettings` (removed in Python 3.14). Production Docker containers run Python 3.11 and are unaffected.

Unblocked when chromadb migrates to `pydantic-settings`. See [Dependency Watch](dependency-watch.md).

---

### WebSocket Support in YEOMAN MCP Bridge
**Priority:** Medium (depends on WebSocket Real-Time Dashboard above)

Once `/ws/realtime` is live, update `agnostic_task_status` in the YEOMAN MCP bridge to subscribe via WebSocket rather than polling `GET /api/tasks/{id}`.

**File:** `../secureyeoman/packages/mcp/src/tools/agnostic-tools.ts`

---

### Structured Result Schemas for YEOMAN
**Priority:** Medium

Define typed result schemas for QA findings so YEOMAN can parse and act on results programmatically — e.g., auto-open issues for critical security findings, block PRs on regression failures.

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

*Last Updated: 2026-02-28 · [Changelog](../project/changelog.md) · [Dependency Watch](dependency-watch.md)*
