# Roadmap

Pending development work for the Agentic QA Team System, ordered by priority. Completed work is tracked in the [Changelog](../project/changelog.md).

See [Dependency Watch](dependency-watch.md) for upstream blockers that affect timeline.

---

## CI/CD Pipeline Stabilization (Complete)

All items from the CI/CD overhaul:

| Item | Status | Description |
|------|--------|-------------|
| Unit tests green | Done | 725 passing, 7 skipped; optional deps skip gracefully |
| Code quality green | Done | Ruff lint + format, Bandit nosec annotations |
| Security scan green | Done | Trivy SARIF + CodeQL v4 + Bandit |
| Helm lint green | Done | Added missing `metrics` values |
| Integration tests | Done | `docker compose` v2 fix; env vars for test compose |
| E2E tests | Done | BuildKit `driver: docker` + `--load`; Chainlit route mounting fix |
| Build release | Done | OCI labels for GHCR repo linking; workflow-level `packages: write` |

---

## SecureYeoman Integration (Complete)

All SecureYeoman integration features are **implemented and tested**. No code blockers — all modules are feature-gated and disabled by default.

| Feature | Module | Status |
|---------|--------|--------|
| A2A Protocol (delegate, status, results) | `shared/yeoman_a2a_client.py` | Done |
| MCP Server (27 tools) | `webgui/routes/mcp.py` | Done |
| MCP Auto-Registration | `shared/yeoman_mcp_server.py` | Done |
| JWT Validation (RS256/ES256/HS256 + OIDC) | `shared/yeoman_jwt.py` | Done |
| Webhook Receiver (6 event types + HMAC) | `webgui/routes/yeoman_webhooks.py` | Done |
| SSE Event Streaming | `webgui/routes/yeoman_webhooks.py` | Done |
| Outbound Event Push | `shared/yeoman_event_stream.py` | Done |
| Embeddable Widget | `webgui/routes/dashboard.py` | Done |
| WebSocket Real-Time Updates | `webgui/realtime.py` | Done |
| Structured Result Schemas | `shared/yeoman_schemas.py` | Done |
| Vector Store Client | `shared/agnos_vector_client.py` | Done |

**Activation:** Set env vars in `.env` — see `.env.example` for all `YEOMAN_*` variables.

---

## AGNOS Deep Integration (Complete)

Agnostic already has client modules for all AGNOS services. This section tracks wiring them into production use.

### P1 — Quick Wins (no AGNOS changes needed)

| Item | Effort | Status | Description |
|------|--------|--------|-------------|
| Call `apply_agnos_profile()` on startup | 1 hr | Done | `webgui/app.py` lifespan calls profile setup before any config is read |
| Agent heartbeat loop | 2 hr | Done | Background `asyncio` task in lifespan, configurable via `AGNOS_HEARTBEAT_INTERVAL_SECONDS` (default 30s) |
| Wire `apply_agnos_profile()` in agents | 1 hr | Done | All 6 agent `main()` functions call profile setup before agent instantiation |

### P2 — Path Prefix Alignment

| Item | Effort | Status | Description |
|------|--------|--------|-------------|
| Align AGNOS client paths | 2 hr | Done | All 8 client modules use `AGNOS_PATH_PREFIX` env var (default `/v1`); tests updated |

### P3 — Containerization & Testing

| Item | Effort | Status | Description |
|------|--------|--------|-------------|
| Create `docker/Dockerfile.agnos` | 2 hr | Done | AGNOS-aware base layer with all integration env vars pre-set |
| `docker-compose.yml` (AGNOS primary) | 2 hr | Done | Primary compose: agnostic container (production), `--profile dev` adds redis + postgres |
| E2E gateway round-trip test | 4 hr | Done | `tests/e2e/test_agnos_gateway.py` — health, gateway round-trip, agent registration, no-key validation |
| Deployment guide | 2 hr | Done | `docs/deployment/agnos.md` — architecture, env vars, networking, troubleshooting |

### P4 — Post-Migration Cleanup

| Item | Effort | Status | Description |
|------|--------|--------|-------------|
| Migrate to AGNOS base image | 3 days | Blocked | Replace root `Dockerfile` with AGNOS Python base image once `.ark` packages are published |
| Remove redundant middleware | 2 days | Not started | Post-migration: remove `RateLimitMiddleware`, `CorrelationIdMiddleware`, docker-compose resource limits (AGNOS handles these) |
| Remove YEOMAN credential provisioning | 1 day | Not started | Post-migration: remove `config/credential_store.py`, MCP/A2A provisioning endpoints, `CREDENTIAL_PROVISIONING_ENABLED` env var, and related tests. All LLM calls route through AGNOS LLM Gateway. See [ADR-028](../adr/028-credential-provisioning.md) |

---

## Bugs — Docker Compose Integration (Found 2026-03-08, **Fixed** 2026-03-08)

Issues discovered during SecureYeoman `--profile full-dev` integration testing — all resolved.

| Issue | Severity | File(s) | Status |
|-------|----------|---------|--------|
| Redis `localhost` hardcode | **High** | `config/environment.py` | **Fixed** — `ConnectionPool` now receives host/port/db/password matching parsed `REDIS_URL` |
| OpenAPI generation crash | Medium | `webgui/app.py` | **Fixed** — monkey-patch adds `.model` attribute to Chainlit's `OAuth2PasswordBearerWithCookie` |
| RabbitMQ health check noise | Low | `webgui/app.py` | **Fixed** — skips RabbitMQ check when neither `RABBITMQ_URL` nor `RABBITMQ_HOST` is set |

---

## Long-term / Blocked

| Item | Blocker |
|------|---------|
| Python 3.14 support | crewai `requires-python <3.14`, chromadb pydantic v1 — see [Dependency Watch](dependency-watch.md) |
| AGNOS base image migration | `.ark` Python packages not yet published — see AGNOS roadmap (Docker Base Images section) |

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
| Cross-project trace coverage | > 80% of requests traced end-to-end |
| AGNOS audit chain coverage | 100% of QA actions forwarded |

---

*Last Updated: 2026-03-08 · Version: 2026.3.8 · Test count: 772 (unit) + 24 (e2e) · Backlog: 1 blocked item · [Changelog](../project/changelog.md) · [Dependency Watch](dependency-watch.md)*
