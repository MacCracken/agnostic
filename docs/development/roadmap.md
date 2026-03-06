# Roadmap

Pending development work for the Agentic QA Team System, ordered by priority. Completed work is tracked in the [Changelog](../project/changelog.md).

See [Dependency Watch](dependency-watch.md) for upstream blockers that affect timeline.

---

## AGNOS Integration — Unified Platform (Q2–Q3 2026)

AGNOSTIC and AGNOS are converging into a unified agent platform. AGNOSTIC provides the QA intelligence layer (6-agent CrewAI team) while AGNOS provides the OS-level runtime (sandboxing, audit, LLM gateway, fleet management). These items make the two projects work as one.

### Phase 3: Deep Integration (Q2 2026, post-Alpha)

**Priority:** High — transforms AGNOSTIC from a standalone tool into an OS-native QA service.

All Phase 3 client modules are implemented. Each defaults to disabled and falls back gracefully, so AGNOSTIC runs identically on bare Docker, Kubernetes, or any other OS — AGNOS adds the unified dashboard/audit chain/telemetry layer on top.

| Item | AGNOSTIC Component | AGNOS Component | Status | Description |
|------|-------------------|-----------------|--------|-------------|
| Audit log forwarding | `shared/agnos_audit.py` | `agent-runtime/http_api.rs` | Done | Batched async forwarder with circuit breaker. `audit_log()` fires-and-forgets to AGNOS audit chain. `X-Correlation-ID` propagated |
| Agent persistent memory via AGNOS | `shared/agnos_memory.py` | `agent-runtime/memory_store.rs` | Done | REST client for AgentMemoryStore: store/retrieve/list/delete with pattern and risk model convenience methods. Per-agent, per-namespace scoping |
| Shared OpenTelemetry pipeline | `shared/telemetry.py` | `agnos-common/telemetry.rs` | Done | `TracerProvider` + `MeterProvider` with OTLP exporters. `trace_llm_call()` context manager wired into `LLMIntegrationService`. Full no-op fallback when OTEL packages absent |
| Reasoning trace submission | `shared/agnos_reasoning.py` | `agent-runtime/tool_analysis.rs` | Done | `ReasoningTrace`/`ReasoningStep` dataclasses. Submit, append, finalize traces via REST with circuit breaker |
| LLM token budget integration | `config/agnos_token_budget.py` | `llm-gateway` | Done | Check/reserve/report/release token budget. Open-by-default (LLM calls proceed if budget service is down). Wired into `_llm_call()` |
| Environment profile sync | `config/agnos_environment.py` | `agnos-common/config.rs` | Done | `AGNOS_PROFILE=dev/staging/prod` auto-sets 10+ env vars via `os.environ.setdefault()`. Explicit env vars always win. Optional remote overrides from AGNOS API |
| Capability advertisement | `config/agnos_agent_registration.py` | `agent-runtime/registry.rs` | Done | 8 capability definitions (security_audit, load_testing, compliance_check, test_planning, test_execution, quality_analysis, regression_testing, fuzzy_verification). Advertised on `register_all_agents()`, withdrawn on deregister |

### Phase 4: Docker Base Image Migration (Q3 2026, post-Alpha)

**Priority:** Medium — depends on AGNOS publishing `agnos:python3.12` base image.

| Item | Effort | Priority | Description |
|------|--------|----------|-------------|
| Migrate per-agent Dockerfiles to `agnos:python3.12` | 3 days | P2 | Replace 6 per-agent Dockerfiles + `docker/Dockerfile.base` with `FROM agnos:python3.12`. Gains: Landlock+seccomp sandbox per agent, cryptographic audit chain, agent-runtime sidecar for resource quotas and IPC backpressure, fleet management via `fleet.toml` |
| Fleet config declaration | 1 day | P2 | Define all 6 QA agents + WebGUI in AGNOS `fleet.toml`. Service manager handles start/stop/restart with dependency ordering (Redis/RabbitMQ before agents). Replaces `docker-compose.yml` service definitions |
| Remove redundant middleware | 2 days | P3 | After migration: remove `RateLimitMiddleware` (AGNOS handles per-agent rate limiting), remove `CorrelationIdMiddleware` (AGNOS distributed tracing), remove custom resource limits from docker-compose (AGNOS `ResourceLimits`). Reduces AGNOSTIC surface area |

---

## SecureYeoman Integration

### Existing (Complete)
- [x] 25 MCP tools registered (15 core + 10 REST proxy)
- [x] A2A protocol (`/api/v1/a2a/receive`, `/api/v1/a2a/delegate`)
- [x] WebSocket task subscription
- [x] Structured result schemas with `to_yeoman_action()`

### Recently Completed
- [x] **Bidirectional AGNOS dashboard** — `shared/agnos_dashboard_bridge.py` pushes agent status/sessions/metrics to AGNOS dashboard API on a configurable interval. `shared/yeoman_a2a_client.py` enables AGNOSTIC to delegate tasks, query status/results, and send heartbeats to YEOMAN. A2A protocol extended with `a2a:result` (YEOMAN → AGNOSTIC result caching) and `a2a:status_query` (YEOMAN queries AGNOSTIC status). New dashboard endpoints: `/dashboard/yeoman`, `/dashboard/unified`

---

## Engineering Backlog

Issues identified during the 2026-03-06 comprehensive code audit. Items marked ~~strikethrough~~ were fixed in the same session.

### Security

| Item | Location | Priority | Status |
|------|----------|----------|--------|
| ~~SSRF DNS rebinding protection~~ | `webgui/routes/dependencies.py` | P0 | Done |
| ~~Timing attack on refresh token comparison~~ | `webgui/auth/token_manager.py:110` | P0 | Done |
| ~~Azure AD issuer verification disabled (`verify_iss: False`)~~ | `webgui/auth/oauth_provider.py:250` | P0 | Done — tenant-specific issuer + JWKS |
| ~~MD5 used for user ID generation (use SHA-256 or UUID)~~ | `webgui/auth/oauth_provider.py:309` | P2 | Done — SHA-256 |
| ~~Ephemeral JWT secret in dev mode (lost on restart)~~ | `webgui/auth/__init__.py:55-62` | P2 | Done — persisted to `~/.agnostic_dev_secret_key` |
| ~~No input validation on `task_id` path parameter~~ | `webgui/routes/tasks.py:305` | P2 | Done — regex validation |
| Unauthenticated `/metrics` endpoint (Prometheus) | `webgui/routes/dashboard.py:172` | P3 | Pending |
| Missing refresh token rotation (old tokens remain valid) | `webgui/auth/token_manager.py:88-121` | P2 | Pending |
| ~~No rate limiting on `/auth/login`~~ | `webgui/routes/auth.py` | P2 | Done — Redis-based per-email rate limit |
| WebSocket message size not validated before JSON parse | `webgui/realtime.py:378` | P3 | Pending |

### Memory & Resource Management

| Item | Location | Priority | Status |
|------|----------|----------|--------|
| ~~Unbounded YEOMAN result cache~~ | `shared/yeoman_a2a_client.py:75` | P0 | Done — LRU OrderedDict, max 500 |
| ~~Unbounded audit buffer when event loop unavailable~~ | `shared/agnos_audit.py:44` | P0 | Done — hard cap 10K + warning |
| ~~Missing shutdown cleanup (dashboard bridge, YEOMAN, alerts, audit, model manager)~~ | `webgui/app.py:923` | P1 | Done |
| ~~Proactive cooldown eviction in AlertManager~~ | `shared/alerts.py:90` | P1 | Done — every 100 entries + hard cap |
| ~~Stale WebSocket connections (no idle timeout)~~ | `webgui/realtime.py:125-131` | P1 | Done — idle pruning with `time.monotonic()` |
| ~~Background task accumulation on Redis listener error~~ | `webgui/realtime.py:345-372` | P1 | Done — internal retry loop |
| Unclosed aiohttp sessions in model providers | `config/model_manager.py:27-36` | P1 | Pending (close() added, needs wiring) |
| Unbounded `active_sessions` dict in AgenticQAGUI | `webgui/app.py:38-52` | P2 | Pending |
| ~~Per-call httpx client creation in token budget~~ | `config/agnos_token_budget.py:81+` | P2 | Done — shared client + close() |

### Performance

| Item | Location | Priority | Status |
|------|----------|----------|--------|
| ~~Synchronous Redis calls blocking event loop~~ | `webgui/routes/tasks.py:147-175` | P0 | Done — `run_in_executor` |
| ~~`redis.keys()` blocking server-wide scan~~ | `webgui/dashboard.py:119,175` | P0 | Done — `scan_iter()` |
| ~~Redundant double-fetch in `get_resource_metrics()`~~ | `webgui/dashboard.py:228-246` | P1 | Done — fetch once |
| ~~Race condition on global webhook HTTP client~~ | `webgui/routes/tasks.py:72-82` | P1 | Done — `asyncio.Lock` |
| Per-request Redis client creation | `webgui/routes/tasks.py:260` | P1 | Pending — singleton via `Depends()` |
| N+1 HTTP pattern in AGNOS memory client | `shared/agnos_memory.py:155-163` | P2 | Pending |
| ~~Missing aiohttp `TCPConnector` pool config~~ | `config/model_manager.py:27-31` | P2 | Done — limit=20, limit_per_host=10, DNS cache |
| ~~Webhook retry without jitter (thundering herd)~~ | `webgui/routes/tasks.py:115-121` | P3 | Done — jittered exponential backoff |

### Code Quality & API Consistency

| Item | Location | Priority | Status |
|------|----------|----------|--------|
| ~~PostgreSQL missing from docker-compose.yml~~ | `docker-compose.yml` | P1 | Done — postgres:16-alpine + webgui DATABASE_URL |
| Inconsistent API response wrapper formats | `webgui/routes/` | P2 | Pending |
| ~~Missing `status_code=201` on POST/PUT endpoints~~ | `webgui/routes/persistence.py` | P2 | Done — POST endpoints return 201 |
| ~~Silent exception swallowing (bare `except Exception: pass`)~~ | `dashboard.py:163`, `tasks.py:404` | P2 | Done — added warning logs |
| Missing `response_model` on dashboard endpoints | `webgui/routes/dashboard.py` | P3 | Pending |
| Inconsistent pagination defaults across routes | `webgui/routes/` | P3 | Pending |
| ~~Duplicate .env.example entries for AGNOS LLM Gateway~~ | `.env.example:122-125, 204-207` | P3 | Done — removed duplicate block |
| A2A protocol undocumented (5+ message types) | `webgui/routes/tasks.py:371-425` | P2 | Pending |

### Integration (YEOMAN / AGNOS)

| Item | Location | Priority | Status |
|------|----------|----------|--------|
| No circuit breaker recovery notifications | `shared/yeoman_a2a_client.py`, `agnos_dashboard_bridge.py` | P2 | Pending |
| Missing YEOMAN/AGNOS health in `/health` endpoint | `webgui/app.py:1001` | P2 | Pending |
| No batch A2A operations (N round-trips) | `shared/yeoman_a2a_client.py` | P3 | Pending |
| Unidirectional dashboard bridge (push only) | `shared/agnos_dashboard_bridge.py` | P3 | Pending |
| ~~A2A endpoints not behind YEOMAN_A2A_ENABLED feature gate~~ | `webgui/routes/tasks.py:371` | P2 | Done — 503 when disabled |
| `a2a:status_query` response format undefined (no schema) | `webgui/routes/tasks.py:404` | P3 | Pending |

---

## Long-term / Blocked

| Item | Blocker | Notes |
|------|---------|-------|
| Python 3.14 support | crewai `requires-python` upper bound, chromadb pydantic v1 | See [Dependency Watch](dependency-watch.md) |
| AGNOS base images | AGNOS Alpha release (Q2 2026) + `agnos:python3.12` published | Phase 4 above |

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

*Last Updated: 2026-03-06 · Test count: 674 (unit) + 19 (e2e) · [Changelog](../project/changelog.md) · [Dependency Watch](dependency-watch.md)*
