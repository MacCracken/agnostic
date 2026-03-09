# Roadmap

Pending development work for the Agentic QA Team System, ordered by priority. Completed work is tracked in the [Changelog](../project/changelog.md).

See [Dependency Watch](dependency-watch.md) for upstream blockers that affect timeline.

---

## Embedded Services & TLS (Complete — 2026-03-09)

Production image now bundles Redis, PostgreSQL, and Caddy TLS — all managed by supervisord. External services can override embedded ones for HA deployments.

| Item | Status | Description |
|------|--------|-------------|
| Embedded Redis | Done | `redis-server` in container, skipped when `REDIS_URL` points to external host |
| Embedded PostgreSQL 17 | Done | Auto-`initdb` on first run, skipped when `DATABASE_URL` points to external host |
| Supervisord process management | Done | Manages Redis, PostgreSQL, Caddy, and Chainlit app with conditional autostart |
| TLS via Caddy reverse proxy | Done | Provided certs (`TLS_CERT_PATH`/`TLS_KEY_PATH`) or auto-HTTPS (`TLS_DOMAIN`). HTTP→HTTPS redirect, HSTS, security headers |
| `DATABASE_URL` env var support | Done | `get_database_url()` respects `DATABASE_URL` directly (was building from components only) |
| Auth `PermissionError` fix | Done | `webgui/auth/__init__.py` handles `PermissionError` when running as `appuser` under supervisord |
| Test warning filters | Done | `pyproject.toml` filters third-party warnings (crewai, aiohttp, asyncio) |
| Flaky test fix | Done | `test_qa_analyst_tools.py` — patched `config.environment.config.get_redis_client` instead of `qa_analyst.redis.Redis` |

**Modes:**
- `docker compose up` — production with embedded Redis + PostgreSQL + optional TLS
- `REDIS_URL=redis://ha:6379/0 DATABASE_URL=postgresql+asyncpg://...@ha:5432/agnostic docker compose up` — external HA services
- `TLS_ENABLED=true TLS_CERT_PATH=/certs/cert.pem TLS_KEY_PATH=/certs/key.pem docker compose up` — standalone HTTPS
- `TLS_ENABLED=true TLS_DOMAIN=qa.example.com docker compose up` — auto-HTTPS with ACME
- `docker compose --profile dev up` — dev with separate containers

---

## LLM Gateway Integration (Confirmed Working — 2026-03-09)

All LLM calls route through AGNOS LLM Gateway (hoosh) when `AGNOS_LLM_GATEWAY_ENABLED=true`. Verified end-to-end.

| Feature | Module | Status |
|---------|--------|--------|
| Gateway routing via litellm | `config/llm_integration.py` | Done |
| Circuit breaker (5 failures → 60s recovery) | `config/llm_integration.py` | Done |
| Fallback data on gateway unavailability | `config/llm_integration.py` | Done |
| Token budget integration | `config/agnos_token_budget.py` | Done |
| Per-agent `x-agent-id` headers | `config/llm_integration.py` | Done |
| Multi-provider fallback chain | `config/model_manager.py` | Done |
| Auto-promotion of gateway to primary | `config/model_manager.py` | Done |
| OpenTelemetry + Prometheus metrics | `shared/telemetry.py` | Done |
| E2E gateway round-trip tests | `tests/e2e/test_agnos_gateway.py` | Done |

**Zero credential sprawl:** When gateway is active, Agnostic needs only `AGNOS_LLM_GATEWAY_API_KEY` — no direct OpenAI/Anthropic keys required.

---

## CI/CD Pipeline Stabilization (Complete)

| Item | Status | Description |
|------|--------|-------------|
| Unit tests green | Done | 816 passing, 2 skipped |
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

All client modules for AGNOS services are wired and working in production.

| Phase | Item | Status |
|-------|------|--------|
| P1 | `apply_agnos_profile()` on startup | Done |
| P1 | Agent heartbeat loop (30s default) | Done |
| P1 | Profile setup in all 6 agents | Done |
| P2 | Path prefix alignment (`AGNOS_PATH_PREFIX`) | Done |
| P3 | `docker/Dockerfile.agnos` | Done |
| P3 | `docker-compose.yml` (AGNOS primary) | Done |
| P3 | E2E gateway round-trip test | Done |
| P3 | Deployment guide (`docs/deployment/agnos.md`) | Done |
| P4 | Migrate to AGNOS base image | Done |

---

## Next Up — Post-Migration Cleanup

| Item | Effort | Status | Description |
|------|--------|--------|-------------|
| Remove redundant middleware | 2 days | Not started | Remove `RateLimitMiddleware`, `CorrelationIdMiddleware`, docker-compose resource limits (AGNOS handles these) |
| Remove YEOMAN credential provisioning | 1 day | Not started | Remove `config/credential_store.py`, MCP/A2A provisioning endpoints, `CREDENTIAL_PROVISIONING_ENABLED` env var, and related tests. All LLM calls route through AGNOS LLM Gateway. See [ADR-028](../adr/028-credential-provisioning.md) |

---

## Bugs — Docker Compose Integration (Found 2026-03-08, Fixed 2026-03-08)

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
| Python 3.14 support | crewai 1.10.1 `requires-python <3.14` — sole remaining blocker. chromadb 1.1.1 is now unblocked (`>=3.9`). See [Dependency Watch](dependency-watch.md) |

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

*Last Updated: 2026-03-09 · Version: 2026.3.9 · Test count: 816 (unit) + 24 (e2e) · Next: post-migration cleanup (3 days) · [Changelog](../project/changelog.md) · [Dependency Watch](dependency-watch.md)*
