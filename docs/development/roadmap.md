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

All items from the 2026-03-06 code audit are complete. See [Changelog](../project/changelog.md).

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

*Last Updated: 2026-03-06 · Test count: 674 (unit) + 19 (e2e) · Backlog: 0 items · [Changelog](../project/changelog.md) · [Dependency Watch](dependency-watch.md)*
