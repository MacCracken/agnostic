# Changelog

All notable changes to the Agentic QA Team System are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versions use **YYYY.M.D** (calendar versioning).

---

## [Unreleased]

### Added

- **Webhook callback retry with exponential backoff** — `_fire_webhook` retries up to 3 times with 1s/2s/4s delays on failure; configurable via `WEBHOOK_MAX_RETRIES` env var; failed deliveries logged with attempt count (`webgui/api.py`)
- **Configurable YEOMAN action thresholds** — coverage, error rate, and performance degradation thresholds extracted from hardcoded values to env vars: `YEOMAN_COVERAGE_THRESHOLD`, `YEOMAN_ERROR_RATE_THRESHOLD`, `YEOMAN_PERF_DEGRADATION_FACTOR` (`shared/yeoman_schemas.py`)
- **Tenant-scoped Redis key isolation** — `submit_task`, `get_task`, and `_run_task_async` use `tenant_manager.task_key()` for tenant-prefixed Redis keys when `MULTI_TENANT_ENABLED=true`; backward-compatible (plain keys when disabled) (`webgui/api.py`, `shared/database/tenants.py`)
- **Tenant-scoped API key validation** — `get_current_user` checks tenant API keys via `tenant_manager.validate_tenant_api_key()` with SHA-256 hash lookup and last-used tracking (`webgui/api.py`)
- **Per-tenant rate limiting** — sliding-window rate limiter in `submit_task` returns HTTP 429 when tenant exceeds `TENANT_DEFAULT_RATE_LIMIT` per minute; uses Redis INCR with 60s TTL (`webgui/api.py`, `shared/database/tenants.py`)
- **Tenant manager unit tests** — 13 new tests for `task_key`, `session_key`, `check_rate_limit`, and `validate_tenant_api_key` (52 total tenant tests) (`tests/unit/test_tenant.py`)
- **Tenant data isolation tests** — 12 tests verifying cross-tenant leakage prevention: key isolation, endpoint-level task visibility, rate limit independence, API key scoping, quota boundaries (`tests/unit/test_tenant_isolation.py`)
- **Tenant provisioning documentation** — provisioning workflow, API key issuance, isolation model, rate limiting, lifecycle states, backward compatibility (`docs/api/tenant-provisioning.md`)
- **Scheduled report delivery channels** — `ReportDeliveryService` with webhook (HMAC-SHA256 signed POST, exponential backoff retry) and Slack (incoming webhook with status emoji) delivery; configurable via `REPORT_WEBHOOK_URL`, `REPORT_WEBHOOK_SECRET`, `REPORT_SLACK_WEBHOOK_URL`, `REPORT_DELIVERY_MAX_RETRIES`; integrated into `_generate_and_deliver()` for both built-in and custom reports; failure notifications also delivered (`webgui/scheduled_reports.py`)
- **Tenant-scoped scheduled reports** — `schedule_custom_report()` accepts optional `tenant_id`; job IDs include tenant prefix for namespace isolation (`webgui/scheduled_reports.py`, `webgui/api.py`)
- **WebSocket missed-message recovery** — `MessageBuffer` class buffers all pub/sub messages to Redis Streams (`XADD` with configurable `REALTIME_STREAM_MAX_LEN`); `replay_missed_messages()` replays buffered messages via `XRANGE` on reconnection; live messages include `stream_id` for position tracking; replayed messages tagged with `"replayed": true` (`webgui/realtime.py`)
- **Client reconnection with last_message_id** — `subscribe_session` and `subscribe_task` messages accept optional `last_message_id` field; server replays missed messages (up to `REALTIME_STREAM_REPLAY_LIMIT`) before resuming live updates; backward-compatible with clients that don't send it (`webgui/realtime.py`)
- **Report delivery unit tests** — 13 tests covering webhook delivery, HMAC signatures, retry logic, Slack formatting, multi-channel dispatch, tenant-scoped job IDs (`tests/unit/test_report_delivery.py`)
- **Message buffer unit tests** — 15 tests covering Redis Streams XADD/XRANGE, replay mechanics, reconnection protocol, publish buffering (`tests/unit/test_message_buffer.py`)
- **Email delivery channel for scheduled reports** — `ReportDeliveryService._deliver_email()` sends HTML reports via SMTP using `aiosmtplib`; supports TLS/STARTTLS, authentication, multiple recipients; exponential backoff retry matching webhook/Slack pattern; configurable via `REPORT_EMAIL_ENABLED`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_USE_TLS`, `SMTP_FROM`, `REPORT_EMAIL_RECIPIENTS` env vars (`webgui/scheduled_reports.py`)
- **Persistent database job store for APScheduler** — `ScheduledReportManager._create_jobstore()` selects between Redis (default) and SQLAlchemy job store; database store uses APScheduler's built-in `SQLAlchemyJobStore` with sync `psycopg2` driver; selected via `SCHEDULER_JOBSTORE=database` when `DATABASE_ENABLED=true`; falls back to Redis when database unavailable (`webgui/scheduled_reports.py`)
- **Alembic migration for APScheduler jobs table** — `apscheduler_jobs` table (id, next_run_time, job_state) matching APScheduler's expected schema (`alembic/versions/a1b2c3d4e5f6_apscheduler_jobs_table.py`)
- **Email delivery unit tests** — 7 tests covering enable/disable, SMTP send, retry logic, HTML body content, multi-channel dispatch (`tests/unit/test_report_delivery.py`)
- **Job store selection unit tests** — 5 tests covering Redis default, explicit Redis, database fallback when DB disabled, SQLAlchemy selection, sync URL conversion (`tests/unit/test_scheduled_reports.py`)
- **ADR-026** — Scheduled report enhancements: email delivery and persistent job store (`docs/adr/026-scheduled-report-enhancements.md`)

---

## [2026.3.5]

### Added

- **WebSocket Real-Time Dashboard** — `/ws/realtime` endpoint fully wired in `webgui/app.py`; initializes Redis pub/sub on startup, subscribes to agent task channels (`manager:tasks`, `senior:tasks`, etc.) for real-time task progress; dashboard.js auto-subscribes to active sessions on connect (`webgui/realtime.py`, `webgui/static/js/dashboard.js`)
- **Prometheus ServiceMonitor** — `ServiceMonitor` and `PodMonitor` CRDs for Prometheus scraping of `/api/metrics` endpoint; configurable via `metrics.enabled` in Helm values (`k8s/helm/agentic-qa/templates/service-monitor.yaml`)
- **Scheduled Report Generation** — APScheduler integration for automated daily/weekly reports; `POST /api/reports/scheduled`, `GET /api/reports/scheduled`, `DELETE /api/reports/scheduled/{job_id}` endpoints; configurable via `SCHEDULED_REPORTS_ENABLED`, `SCHEDULED_REPORT_DAILY_TIME`, `SCHEDULED_REPORT_WEEKLY_DAY`, `SCHEDULED_REPORT_WEEKLY_TIME` env vars (`webgui/scheduled_reports.py`, `webgui/api.py`, `pyproject.toml`)
- **GitOps/ArgoCD Integration** — ArgoCD `ApplicationSet` for multi-environment promotion; External Secrets Operator for Vault-backed secret rotation; Kustomize overlays for dev/staging/prod (`k8s/argocd/applicationset.yaml`, `k8s/argocd/external-secrets.yaml`, `k8s/overlays/`)
- **Test Result Persistence (PostgreSQL)** — SQLAlchemy async models for test sessions, results, metrics, and reports; REST endpoints for CRUD operations; quality trends API; configurable via `DATABASE_ENABLED`, `POSTGRES_*` env vars (`shared/database/models.py`, `shared/database/repository.py`, `webgui/api.py`, `pyproject.toml`)
- **Multi-Tenant WebGUI** — Tenant models (`Tenant`, `TenantUser`, `TenantAPIKey`) with `TenantRepository` for database CRUD; admin endpoints for tenant provisioning (create, update, soft-delete, user management); tenant-scoped Redis keyspaces; configurable via `MULTI_TENANT_ENABLED` env var (`shared/database/tenants.py`, `shared/database/tenant_repository.py`, `webgui/api.py`)
- **AGNOS OS Phase 2 - Agent HUD Registration** — AgentRegistryClient for registering Agnostic QA agents with agnosticos Agent HUD; registration on startup, deregistration on shutdown; REST endpoints for status and manual registration; configurable via `AGNOS_AGENT_REGISTRATION_ENABLED`, `AGNOS_AGENT_REGISTRY_URL` env vars (`config/agnos_agent_registration.py`, `webgui/api.py`, `docs/adr/022-agnosticos-agent-hud.md`)
- **YEOMAN MCP Bridge WebSocket Support** — WebSocket task subscription via `subscribe_task` message; task status updates published to Redis `task:{id}` channel on status changes; enables MCP bridge to receive push notifications instead of polling (`webgui/realtime.py`, `webgui/api.py`)
- **Structured Result Schemas for YEOMAN** — Typed dataclasses for security, performance, and test execution results with `to_yeoman_action()` method for programmatic actions (auto-create issues, block PRs); `GET /results/structured/{session_id}` endpoint (`shared/yeoman_schemas.py`, `webgui/api.py`)
- **Alembic database migrations** — async PostgreSQL migration support; initial migration covering all 7 tables (test_sessions, test_results, test_metrics, test_reports, tenants, tenant_users, tenant_api_keys); `alembic/env.py` configured for `asyncpg` (`alembic/`)
- **Scheduled reports unit tests** (`tests/unit/test_scheduled_reports.py`) — 27 tests covering init, enabled/disabled behavior, job scheduling, triggers, day mapping, error handling
- **Multi-tenant unit tests** (`tests/unit/test_tenant.py`) — 39 tests covering TenantManager, TenantRepository CRUD, endpoint guards, auth, 404 handling
- **Unit tests for WebSocket realtime** (`tests/unit/test_webgui_realtime.py`) — 15 tests covering EventType, WebSocketMessage, RealtimeManager, WebSocketHandler, and channel configuration

### Fixed

- **WebSocket realtime test hang** — `test_handle_websocket_accepts_connection` blocked forever due to missing `receive_json` side_effect; handler's `while True` receive loop now properly terminated in test
- **pytest collection warnings** — `TestStatus` and `TestExecutionResult` in `shared/yeoman_schemas.py` suppressed via `__test__ = False`
- **SQLAlchemy reserved name conflict** — `TestResult.metadata` renamed to `extra_metadata` with explicit column name `"metadata"` to avoid collision with SQLAlchemy's `Base.metadata`

### Changed

- **TODO.md consolidated** — deleted `TODO.md` (was a redirect); all tracking moved to `docs/development/roadmap.md`; references in `README.md` and `docs/README.md` updated

---

## [2026.2.28]

### Security

- **Path traversal prevention** — `GET /reports/{id}/download` resolves `file_path` with `Path.resolve()` and asserts `is_relative_to(_REPORTS_DIR)` before serving; paths outside `/app/reports` return HTTP 403 (`webgui/api.py`)
- **Session ID sanitization** — session IDs stripped of non-alphanumeric characters via `re.sub` before use in generated filenames, preventing directory traversal in report generation (`webgui/exports.py`)
- **Constant-time API key comparison** — static `AGNOSTIC_API_KEY` comparison changed from `==` to `hmac.compare_digest()` to prevent timing side-channel attacks (`webgui/api.py`)
- **Required RabbitMQ credentials** — `guest:guest` fallback removed; `RABBITMQ_USER` and `RABBITMQ_PASSWORD` must be explicitly set; Docker Compose uses `:?` syntax to fail clearly if unset (`docker-compose.yml`, `.env.example`)
- **Security headers middleware** — `SecurityHeadersMiddleware` sets `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `X-XSS-Protection: 1; mode=block`, `Referrer-Policy: strict-origin-when-cross-origin` on every response (`webgui/app.py`)
- **Input validation hardening** — `TaskSubmitRequest` enforces `min_length`/`max_length` on all text fields (title: 200, description: 5000, goals/constraints: 500) and `Literal["critical","high","medium","low"]` for priority; invalid values return HTTP 422 (`webgui/api.py`)

### Added

- **Manual testing guide** (`docs/development/manual-testing.md`) — ~45 test steps covering smoke, integration, and E2E sweeps with exact `curl` commands, expected outputs, and pass/fail criteria; includes YEOMAN MCP bridge verification
- **AGNOS OS integration** ([ADR-021](../adr/021-agnosticos-integration.md)) — route LLM calls through the AGNOS OS LLM Gateway (port 8088, OpenAI-compatible); config-only change, no agent code modified
  - `config/models.json`: new `agnos_gateway` provider entry (disabled by default)
  - `.env.example`: `AGNOS_LLM_GATEWAY_ENABLED`, `AGNOS_LLM_GATEWAY_URL`, `AGNOS_LLM_GATEWAY_API_KEY`, `AGNOS_LLM_GATEWAY_MODEL`
  - `docs/adr/021-agnosticos-integration.md`, `docs/deployment/agnosticos.md`
  - `tests/unit/test_model_manager.py`: 41 unit tests covering provider schema, gateway routing, env-var guards
- **Kubernetes production readiness** ([ADR-020](../adr/020-kubernetes-production-readiness.md)) — full production controls for manifests and Helm chart
  - `HorizontalPodAutoscalers` (`autoscaling/v2`) for all 6 agents + WebGUI; CPU/memory-based, 300 s scale-down stabilisation
  - `PodDisruptionBudgets` (`policy/v1`, `minAvailable: 1`) for all 7 deployments
  - `NetworkPolicies` — least-privilege ingress/egress; agents may reach public internet (LLM APIs) but not private CIDRs
  - `ResourceQuota` — namespace cap (32 CPU, 64 Gi RAM, 20 pods/services/secrets/ConfigMaps, 10 PVCs)
  - Helm templates: `hpa.yaml`, `pdb.yaml`, `resource-quota.yaml`; `values-dev.yaml` and `values-prod.yaml`
  - K8s YAML validation test suite (`tests/k8s/`)
- **A2A Protocol integration** ([ADR-019](../adr/019-a2a-protocol.md)) — Agnostic as a first-class peer in YEOMAN's agent delegation tree
  - `POST /api/v1/a2a/receive` — handles `a2a:delegate` (routes to task submission), `a2a:heartbeat`, unknown types (forward-compatible)
  - `GET /api/v1/a2a/capabilities` — advertises QA, security-audit, and performance-test capabilities (unauthenticated)
  - 8 unit tests covering delegate, heartbeat, unknown type, auth enforcement, validation
- **REST task submission + API key auth** ([ADR-017](../adr/017-rest-task-submission-api-keys.md))
  - `POST /api/tasks`, `GET /api/tasks/{id}` — fire-and-forget with Redis-backed status polling; 24 h TTL; `pending → running → completed | failed`
  - `POST /api/tasks/security`, `/performance`, `/regression`, `/full` — convenience endpoints for agent-specific runs
  - `X-API-Key` header auth — dual mode: static `AGNOSTIC_API_KEY` env var + Redis-backed per-client keys (sha256-hashed, never stored raw)
  - `POST/GET /api/auth/api-keys`, `DELETE /api/auth/api-keys/{key_id}` — key management endpoints
- **Webhook callbacks + CORS** ([ADR-018](../adr/018-webhook-callbacks-cors.md))
  - Optional `callback_url` + `callback_secret` on task submission; HMAC-SHA256 `X-Signature` header on callback POST
  - `CORSMiddleware` with `CORS_ALLOWED_ORIGINS` env var; defaults allow YEOMAN dashboard ports
- **Observability stack** ([ADR-015](../adr/015-observability-stack.md))
  - `shared/metrics.py` — Prometheus counters, histograms, gauges with no-op fallback; `get_metrics_text()`
  - `shared/logging_config.py` — structured JSON logging via structlog or stdlib text fallback
  - `GET /api/metrics` — Prometheus scrape endpoint (unauthenticated)
  - LLM call instrumentation (counter + histogram on all 6 `LLMIntegrationService` methods)
- **Agent communication hardening** ([ADR-016](../adr/016-communication-hardening.md))
  - `shared/resilience.py` — `CircuitBreaker` (CLOSED/OPEN/HALF_OPEN), `retry_async` decorator with exponential backoff, `GracefulShutdown` async context manager
  - Celery reliability: `task_acks_late`, `task_reject_on_worker_lost`, retry config
  - `GracefulShutdown` wired into all 6 agent `main()` functions
- **Plugin architecture** ([ADR-013](../adr/013-plugin-architecture.md)) — config-driven `AgentRegistry` + `AgentDefinition` in `config/agent_registry.py`; replaces hardcoded if/elif routing; new agents require 5 steps instead of 7 with no code changes to manager or WebGUI
- **WebGUI REST API** ([ADR-014](../adr/014-webgui-rest-api.md)) — 18+ FastAPI endpoints (dashboard, sessions, reports, agents, auth) with JWT authentication; OpenAPI schema at `/docs`
- **Enhanced health endpoint** — `GET /health` returns `healthy | degraded | unhealthy` with per-component detail (Redis ping, RabbitMQ TCP connect, per-agent heartbeat freshness); configurable via `AGENT_STALE_THRESHOLD_SECONDS`
- **Dependency Watch** (`docs/development/dependency-watch.md`) — tracks upstream blockers (chromadb/Python 3.14, chainlit FastAPI conflict) with exact error context, fix conditions, and monitoring links

### Changed

- **crewAI 1.x migration — LangChain removed** — all application code now targets `crewai>=1.0.0,<2.0.0` with litellm for LLM routing
  - `pyproject.toml`: `crewai>=1.0.0,<2.0.0`; removed `langchain`, `langchain-openai`, `langchain-community`; `numpy <2.0` cap lifted; `requires-python` narrowed to `>=3.11,<3.14`
  - `config/llm_integration.py`: `ChatOpenAI` + LangChain schema messages replaced with `litellm.acompletion()`
  - `config/universal_llm_adapter.py`: rewritten — `langchain.llms.base.LLM` subclass replaced with `crewai.LLM` factory (`create_llm()` / `get_crewai_llm()`)
  - All 6 agent files: `from langchain_openai import ChatOpenAI` → `from crewai import LLM`; `ChatOpenAI(...)` → `LLM(...)`
  - `agents/performance/qa_performance.py`: `from langchain.tools import BaseTool` → `from shared.crewai_compat import BaseTool`
  - Python 3.14 still blocked by chromadb — see `docs/development/dependency-watch.md`; production Docker (Python 3.11) unaffected
- **OAuth2 JWT signature verification** — replaced `verify_signature: False` with proper JWKS verification for Google, GitHub, and Azure AD providers (`webgui/auth.py`)
- **Docker health checks** — agent health checks now perform an actual Redis ping instead of `print('healthy')` (`docker-compose.yml`)
- **PDF export** — implemented real PDF generation with ReportLab (`SimpleDocTemplate`, `Paragraph`, `Table`) with HTML fallback (`webgui/exports.py`)
- **Documentation consolidation** — CLAUDE.md slimmed to commands + pointers; full project documentation now lives in `docs/`; roadmap moved to `docs/development/roadmap.md`; `docs/development/setup.md` updated with current tech stack and plugin-architecture agent-adding steps

### Fixed

- `datetime.utcnow()` replaced with `datetime.now(timezone.utc)` across codebase
- `RABBITMQ_URL` missing from WebGUI service in `docker-compose.yml`
- `.env.example`: removed duplicate keys, added 11 missing variables (OAuth, WebSocket, reporting, team config)
- `pyproject.toml`: added missing dependencies (`PyJWT[crypto]`, `faker`, `reportlab`, `requests`)

### Removed

- `langchain>=0.1.0,<0.2.0`, `langchain-openai>=0.0.5,<0.1.0`, `langchain-community>=0.0.38,<0.1.0` — replaced by litellm (via crewai 1.x)
- `numpy <2.0` upper bound — was required only by langchain 0.1.x
- `guest:guest` RabbitMQ default credentials — credentials now required at startup

### Tests

- `tests/unit/test_webgui_api.py`: `TestReportDownloadSecurity` (4 tests — valid path, path traversal blocked 403, dotdot blocked 403, missing file 404); `TestSecurityHeaders`
- `tests/unit/test_webgui_tasks.py`: 10 new validation tests (empty title, oversized fields, invalid priority enum, 422 responses)
- `tests/unit/test_webgui_exports.py`: `TestGenerateFileSanitization` (path traversal in session ID neutralised, normal IDs preserved)
- `tests/unit/test_model_manager.py`: 41 tests for AGNOS OS provider, gateway routing, env-var guards
- `tests/k8s/`: YAML structural validation for all Kubernetes manifests and Helm values
- **179 tests passing** across all unit suites

---

## [2026.2.16]

### Added

- Complete 6-agent QA platform (QA Manager, Senior QA, Junior QA, QA Analyst, Security & Compliance, Performance & Resilience)
- CrewAI-based multi-agent orchestration via Redis + RabbitMQ Celery bus
- Chainlit WebGUI (`http://localhost:8000`) with real-time dashboard, session history, report generation
- Docker Compose deployment (9 containers) with optimised base image (99% faster rebuilds)
- Kubernetes deployment — Kustomize manifests + Helm chart with hardened security contexts (`readOnlyRootFilesystem`, drop ALL capabilities, seccomp RuntimeDefault)
- CI/CD pipeline (GitHub Actions) — test, lint, security scan (Bandit), Helm lint
- Multi-provider LLM integration (OpenAI primary; Anthropic, Google Gemini, Ollama, LM Studio fallbacks) via `config/model_manager.py`
- Advanced testing — self-healing UI selectors (CV + semantic analysis), fuzzy verification (LLM-based 0–1 quality scoring), risk-based test prioritisation (ML-driven)
- JWT authentication + RBAC (Super Admin, Org Admin, Team Lead, QA Engineer, Viewer, API User)
- Multi-format report export (PDF via ReportLab, JSON, CSV)
- Cross-platform testing support — web (Playwright), mobile (Appium), desktop (cross-platform)
- Compliance automation — OWASP, GDPR, PCI DSS, SOC 2, ISO 27001, HIPAA
- Predictive quality analytics — defect prediction, quality trends, risk scoring, release readiness
- AI-enhanced test generation — requirements-driven, code analysis, autonomous data generation
- Team size presets — Lean / Standard / Large via `QA_TEAM_SIZE` env var (`config/team_config.json`)
- 21 Architecture Decision Records (ADR-001 through ADR-016 + 021)
- YEOMAN MCP integration — 10 `agnostic_*` tools in SecureYeoman bridge

---

[Unreleased]: https://github.com/MacCracken/agnostic/compare/2026.3.5...HEAD
[2026.3.5]: https://github.com/MacCracken/agnostic/compare/2026.2.28...2026.3.5
[2026.2.28]: https://github.com/MacCracken/agnostic/compare/2026.2.16...2026.2.28
[2026.2.16]: https://github.com/MacCracken/agnostic/releases/tag/2026.2.16
