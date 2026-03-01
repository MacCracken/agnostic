# Agentic QA Team System - Roadmap

## Overview
This roadmap outlines the strategic direction and upcoming enhancements for the Agentic QA Team System. The system is currently feature-complete with comprehensive functionality, including all core agents, WebGUI, monitoring, logging, and deployment infrastructure.

---

## Recently Completed (2026-02-28 Security Audit)

### API Security Hardening
- **Path traversal prevention**: `GET /reports/{id}/download` validates `file_path` stays inside `/app/reports` using `Path.resolve().is_relative_to()`
- **Session ID sanitization**: Filename construction in `exports.py` sanitizes session IDs with `re.sub` before use
- **Constant-time API key comparison**: `hmac.compare_digest()` replaces `==` for timing-attack resistance
- **Required RabbitMQ credentials**: `guest:guest` fallback removed from `docker-compose.yml`; credentials required at startup
- **Security headers middleware**: `SecurityHeadersMiddleware` in `app.py` sets OWASP-recommended headers on every response
- **Input validation**: `TaskSubmitRequest` enforces field length limits and `Literal` enum for priority

### Documentation & Testing
- Manual test sweep guide: `docs/development/manual-testing.md` — smoke, integration, and E2E tests with exact commands
- 21 new security-focused unit tests across the webgui test suite
- ADR-010, ADR-017 updated with security amendment sections

---

## Recently Completed (2026-02-16 Audit Fixes)

### Security Fixes
- **OAuth2 JWT Signature Verification**: Replaced `verify_signature: False` with proper JWKS verification for Google, GitHub, and Azure AD providers
- **GitHub OAuth Flow**: Implemented full code→token exchange via GitHub API
- **Azure AD OAuth Flow**: Implemented JWKS-based ID token verification
- **SAML Guard**: Added explicit handler returning None with warning log
- **Secret Key Validation**: `WEBGUI_SECRET_KEY` is now required in production (`ENVIRONMENT=production`)
- **Hardcoded Credentials Removed**: RabbitMQ credentials in `docker-compose.yml` now reference environment variables

### Infrastructure Fixes
- **Docker Health Checks**: Agent health checks now perform actual Redis ping instead of `print('healthy')`
- **PDF Export**: Implemented real PDF generation with ReportLab (`SimpleDocTemplate`, `Paragraph`, `Table`) with HTML fallback
- **WebGUI RABBITMQ_URL**: Added missing `RABBITMQ_URL` to webgui service in docker-compose

### Documentation & Configuration Fixes
- **CLAUDE.md Tool Inventory**: Corrected all agent tool lists to match code (added 4 missing tools, fixed 3 wrong names)
- **CLAUDE.md API Endpoints**: Separated implemented (`/health`) from planned endpoints
- **CLAUDE.md Undocumented Modules**: Added `config/environment.py`, `config/team_config_loader.py`, `shared/crewai_compat.py`, `shared/data_generation_service.py`
- **`.env.example`**: Removed duplicate keys, added 11 missing variables (OAuth, WebSocket, reporting, team config)
- **`pyproject.toml`**: Added missing dependencies (`PyJWT[crypto]`, `faker`, `reportlab`, `requests`)
- **Agent READMEs**: Added missing tools to junior, security_compliance, and performance docs

---

## Completed Infrastructure & Deployment

### Container Resource Management
- **Status**: Completed
- Memory/CPU limits on all Docker containers with health checks and restart policies

### Centralized Logging
- **Status**: Completed
- ELK stack (Elasticsearch, Logstash, Kibana) for centralized log aggregation

### Monitoring & Alerting
- **Status**: Completed
- Prometheus + Grafana monitoring stack with AlertManager

### TLS Security
- **Status**: Completed
- TLS encryption for all inter-service communication

---

## Completed QA Features

### Agent Tools (All Completed)
- Flaky Test Detection & Management (Junior)
- UX/Usability Testing (Junior)
- i18n/Localization Testing (Junior)
- Advanced Performance Profiling (Performance)
- Test Data Privacy (Security & Compliance)
- Test Management & Traceability (Analyst)
- CI/CD Pipeline Integration (GitHub Actions)
- SOC 2, ISO 27001, HIPAA Compliance Automation (Security & Compliance)
- Cross-Platform Testing — Web, Mobile, Desktop (Junior)
- Predictive Quality Analytics — Defect Prediction, Quality Trends, Risk Scoring, Release Readiness (Analyst)
- AI-Enhanced Test Generation — Requirements-driven, Code Analysis, Autonomous Data Generation (Senior)

### Team Configuration
- Lean/Standard/Large team presets via `QA_TEAM_SIZE` environment variable
- Configuration: `config/team_config.json`, `config/team_config_loader.py`

---

## Next Phase — Implementation Priorities

### Recently Completed (2026-02-16 Phase 2)

#### Plugin Architecture
- **Status**: Completed
- Config-driven `AgentRegistry` replaces hardcoded if/elif routing
- Adding new agents: 5 steps instead of 7, no code changes to manager or WebGUI
- See ADR-013

#### WebGUI REST API
- **Status**: Completed
- 18 FastAPI endpoints wrapping existing manager singletons (dashboard, sessions, reports, agents, auth)
- JWT authentication on all endpoints
- See ADR-014

#### CI/CD Pipeline Hardening
- **Status**: Completed
- Fixed `pip install` to use `pip install -e .[dev,test,web,ml]`
- Added Bandit security scan job
- Added Helm chart lint job

#### Test Coverage Expansion
- **Status**: Completed
- 48 new unit tests across agent_registry, webgui auth, webgui exports, webgui API, config environment

### Recently Completed (2026-02-16 Phase 3)

#### Observability Stack Integration
- **Status**: Completed
- Prometheus metrics (`shared/metrics.py`) with no-op fallback — tasks, LLM calls, HTTP requests, agents, circuit breaker
- Structured logging (`shared/logging_config.py`) — JSON via structlog or stdlib text
- `/api/metrics` endpoint for Prometheus scraping
- LLM call instrumentation (counter + histogram on all 6 methods)
- See ADR-015

#### Agent Communication Hardening
- **Status**: Completed
- Circuit breaker for LLM API calls (`shared/resilience.py`) — CLOSED/OPEN/HALF_OPEN states
- Celery reliability: `task_acks_late`, `task_reject_on_worker_lost`, retry config
- Graceful shutdown (`GracefulShutdown` context manager) in all 6 agent `main()` functions
- `retry_async` decorator with exponential backoff
- See ADR-016

### Recently Completed (2026-02-22 Phase 5)

#### Kubernetes Production Readiness
- **Status**: Completed
- HorizontalPodAutoscalers (`autoscaling/v2`) for all 6 agents + WebGUI — CPU/memory-based, conservative scale-down
- PodDisruptionBudgets (`policy/v1`, `minAvailable: 1`) for all 7 deployments — zero-downtime node maintenance
- NetworkPolicies for least-privilege traffic isolation — agents, Redis, RabbitMQ, WebGUI scoped separately
- ResourceQuota at namespace level — caps total CPU, RAM, pods, services, secrets, PVCs
- Helm chart: new `hpa.yaml`, `pdb.yaml`, `resource-quota.yaml` templates; `values.yaml` feature flags for all four controls
- Kustomize: fixed `kustomization.yaml` to include all new production manifests
- Environment-specific values files: `values-dev.yaml` and `values-prod.yaml`
- See ADR-020

### Recently Completed (2026-02-21 Phase 4)

#### REST Task Submission API
- **Status**: Completed
- `POST /api/tasks` and `GET /api/tasks/{id}` — fire-and-forget task submission with Redis polling
- `asyncio.create_task` background execution, 24-hour Redis TTL, `pending → running → completed | failed`
- See ADR-017

#### API Key Authentication
- **Status**: Completed
- `X-API-Key` header auth — dual mode: static `AGNOSTIC_API_KEY` env var + Redis-backed per-client keys
- Management endpoints: `POST/GET /api/auth/api-keys`, `DELETE /api/auth/api-keys/{key_id}`
- HMAC-SHA256 used as signing algorithm; raw keys never stored (only sha256 hashes)
- See ADR-017

#### Webhook Callbacks
- **Status**: Completed
- Optional `callback_url` + `callback_secret` on task submission
- HMAC-SHA256 `X-Signature` header on callback POST
- Failures logged but do not affect task result
- See ADR-018

#### Agent-Specific Convenience Endpoints
- **Status**: Completed
- `POST /api/tasks/security`, `/performance`, `/regression`, `/full`
- See ADR-017

#### Enhanced Health Endpoint
- **Status**: Completed
- Redis ping, RabbitMQ TCP connect, per-agent heartbeat freshness check
- Returns `healthy | degraded | unhealthy` with per-component detail
- Configurable via `AGENT_STALE_THRESHOLD_SECONDS`

#### CORS Configuration
- **Status**: Completed
- `CORSMiddleware` with `CORS_ALLOWED_ORIGINS` env var
- Default allows YEOMAN dashboard (`localhost:18789`) and common dev port (`localhost:3001`)
- See ADR-018

#### A2A Protocol Integration
- **Status**: Completed
- `POST /api/v1/a2a/receive` handles `a2a:delegate`, `a2a:heartbeat`, and unknown types (forward-compatible)
- `GET /api/v1/a2a/capabilities` advertises QA, security-audit, and performance-test capabilities
- Agnostic is now a first-class peer in YEOMAN's agent delegation tree
- Reuses existing task submission, auth, and Redis infrastructure
- See ADR-019

---

### Immediate (Next 3 Months)

#### WebSocket Real-Time Dashboard
- **Priority**: High
- **Scope**: Wire `/ws/realtime` WebSocket endpoint to the existing `webgui/realtime.py` infrastructure and Redis Pub/Sub channel (`REDIS_PUBSUB_CHANNEL`). Enables the dashboard to receive task progress, agent status changes, and session events without polling. YEOMAN MCP tools that call `agnostic_task_status` currently poll `GET /api/tasks/{id}` — WebSocket push would let the bridge subscribe once and receive completion events.
- **Files**: `webgui/realtime.py`, `webgui/app.py`, `webgui/static/js/`

#### Scheduled Report Generation
- **Priority**: Medium-High
- **Scope**: Integrate APScheduler or Celery Beat for automated periodic report generation (daily executive summary, weekly compliance report). Configurable per-team via environment variables or a future admin UI. Complements the current on-demand `POST /api/reports/generate` endpoint.

#### CrewAI / LangChain Stack Upgrade
- **Priority**: High
- **Scope**: Upgrade `crewai 0.11.x → ≥1.0` to eliminate pydantic v1 compatibility shim warnings and align with the actively-maintained crewai API. The project's own code is already pydantic v2 native; the shim is a transitive dependency from langchain 0.1.x.
- **Note on Python 3.14**: crewai 1.x still requires `Python <3.14` (chromadb dependency uses `pydantic.v1.BaseSettings`). Python 3.14 support is not achievable until chromadb migrates to `pydantic-settings`. The upgrade to crewai 1.x is still worthwhile for API modernisation and dropping LangChain, but will not unlock Python 3.14.
- **Breaking changes**: crewai 1.x dropped LangChain and LangChain-OpenAI in favour of litellm; `Crew`, `Agent`, and `Task` constructors changed. All six agent implementations (`agents/*/`) plus `config/universal_llm_adapter.py` will need updating.
- **Side effects**: `langchain`, `langchain-openai`, and `langchain-community` deps removed; `numpy <2.0` cap in `ml` extras can be removed once langchain is gone.

#### Grafana / Prometheus Observability Stack
- **Priority**: High
- **Scope**: `ServiceMonitor` CRD for Prometheus scraping, Grafana dashboard JSON for agent metrics (tasks, LLM calls, circuit breaker state), AlertManager rules for critical thresholds

#### GitOps / ArgoCD Integration
- **Priority**: Medium-High
- **Scope**: ArgoCD `ApplicationSet` for multi-environment promotion, Sealed Secrets or External Secrets Operator for secret rotation, chart published to OCI registry

### Medium Term (3-6 Months)

#### AGNOS OS Deep Integration
- **Priority**: High (foundational)
- **Status**: Phase 1 in progress (LLM Gateway routing — config done, agnosticos HTTP server pending)
- **Phase 1** (current): Route LLM calls through AGNOS LLM Gateway (port 8088, OpenAI-compatible API). Config-only change — no Python code changes. See ADR-021.
- **Phase 2**: Register Agnostic CrewAI agents as agnosticos agents via `agnos-sys` SDK. Surfaces agents in AGNOS Agent HUD and security UI.
- **Phase 3**: Agnostic messaging (Redis/RabbitMQ) optionally replaced by agnosticos MessageBus for native OS IPC.
- See [ADR-021](../adr/021-agnosticos-integration.md) and [agnosticos ADR-007](../../../agnosticos/docs/adr/adr-007-agnostic-integration.md).

#### 7. Multi-Tenant WebGUI
- **Priority**: Medium
- **Scope**: Tenant-scoped Redis keyspaces, per-team RabbitMQ vhosts, tenant-aware session management, admin dashboard

#### 8. Test Result Persistence & Analytics
- **Priority**: Medium
- **Scope**: PostgreSQL/SQLite backend for test result history, time-series storage for quality metrics, historical comparison API

---

## Success Metrics

### System Performance
- **Test Execution Time**: < 50% reduction through optimization
- **Defect Detection Rate**: > 95% automated detection
- **System Uptime**: > 99.9% availability
- **Cost Efficiency**: 30% reduction in testing costs

### Quality Improvements
- **Test Coverage**: > 90% automated coverage (agents); > 60% module coverage (all source)
- **Defect Escape Rate**: < 1% to production
- **Compliance Score**: > 95% automated compliance (GDPR, PCI DSS, SOC 2, ISO 27001, HIPAA)

### Operational Excellence
- **Mean Time to Resolution**: < 30 minutes for QA issues
- **Agent Efficiency**: > 80% successful autonomous task completion
- **Team Productivity**: 5x improvement in QA throughput

---

## Agnostic as an Independent Tool vs. Sub-Agent

Agnostic is designed to serve two distinct usage patterns simultaneously. Both are supported today; the roadmap items above improve each.

### Standalone / Independent Tool

Used directly by developers, QA engineers, or CI/CD pipelines:

- **WebGUI chat** (`http://localhost:8000`) — natural language requirement input → test plan → full execution
- **REST API** (`POST /api/tasks`, `GET /api/tasks/{id}`) — programmatic submission from scripts, GitHub Actions, or any HTTP client
- **Prometheus metrics** + structured logging — plugs into existing observability stacks

**Immediate next steps for this path:** WebSocket dashboard for real-time feedback; test result persistence (PostgreSQL) for historical trend queries; scheduled reports for regular stakeholders.

### Sub-Agent / Delegated Tool (via YEOMAN MCP)

Used as a specialized QA team delegated to by a higher-level orchestrator (SecureYeoman):

- **10 MCP tools** in `secureyeoman/packages/mcp/src/tools/agnostic-tools.ts` — YEOMAN agents can invoke the full QA pipeline, get results, and generate reports with a single tool call
- **A2A protocol** (`POST /api/v1/a2a/receive`) — Agnostic peers with YEOMAN in the agent delegation tree; tasks can arrive via `a2a:delegate` messages rather than REST
- **`secureyeoman agnostic start|stop|status`** — YEOMAN manages the Docker Compose lifecycle

**Immediate next steps for this path:** WebSocket support in the MCP bridge so `agnostic_task_status` can subscribe rather than poll; AGNOS OS Phase 2 (register CrewAI agents as agnosticos agents in the Agent HUD); structured result schemas so YEOMAN can parse and act on QA findings programmatically.

---

*Last Updated: 2026-02-28*
*Next Review: May 2026*
