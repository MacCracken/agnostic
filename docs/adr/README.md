# Architecture Decision Records (ADRs)

This directory contains Architecture Decision Records (ADRs) for the Agentic QA Team System. ADRs capture important architectural decisions along with their context, consequences, and rationale.

## ADR Index

| ADR | Title | Status |
|-----|-------|--------|
| [ADR-001](001-webgui-technology-stack.md) | WebGUI Technology Stack Selection | Accepted |
| [ADR-002](002-realtime-communication-infrastructure.md) | Real-time Communication Infrastructure | Accepted |
| [ADR-003](003-session-management-architecture.md) | Session Management Architecture | Accepted |
| [ADR-004](004-report-generation-strategy.md) | Report Generation Strategy | Accepted |
| [ADR-005](005-authentication-authorization-design.md) | Authentication and Authorization Design | Accepted |
| [ADR-006](006-agent-architecture.md) | Agent Architecture | Accepted |
| [ADR-007](007-llm-integration.md) | LLM Integration | Accepted |
| [ADR-008](008-deployment-strategy.md) | Deployment Strategy | Accepted |
| [ADR-009](009-webgui-architecture.md) | WebGUI Architecture | Accepted |
| [ADR-010](010-security-strategy.md) | Security Strategy | Accepted |
| [ADR-011](011-scalable-team-architecture.md) | Scalable Team Architecture | Accepted |
| [ADR-012](012-testing-strategy.md) | Testing Strategy | Accepted |
| [ADR-013](013-plugin-architecture.md) | Plugin Architecture for Agent Registration | Accepted |
| [ADR-014](014-webgui-rest-api.md) | WebGUI REST API | Accepted |
| [ADR-015](015-observability-stack.md) | Observability Stack Integration | Accepted |
| [ADR-016](016-communication-hardening.md) | Agent Communication Hardening | Accepted |
| [ADR-017](017-rest-task-submission-api-keys.md) | REST Task Submission and API Key Authentication | Accepted |
| [ADR-018](018-webhook-callbacks-cors.md) | Webhook Callbacks and CORS Configuration | Accepted |
| [ADR-019](019-a2a-protocol.md) | A2A Protocol Integration | Accepted |
| [ADR-020](020-kubernetes-production-readiness.md) | Kubernetes Production Readiness | Accepted |
| [ADR-021](021-agnosticos-integration.md) | AGNOS OS Integration | Accepted |
| [ADR-022](022-agnosticos-agent-hud.md) | AGNOS OS Phase 2 — Agent HUD Registration | Accepted |
| [ADR-023](023-yeoman-websocket-bridge.md) | YEOMAN MCP Bridge WebSocket Support | Accepted |
| [ADR-024](024-structured-result-schemas.md) | Structured Result Schemas for YEOMAN | Accepted |
| [ADR-025](025-test-result-persistence.md) | Test Result Persistence (PostgreSQL) | Accepted |
| [ADR-026](026-scheduled-report-enhancements.md) | Scheduled Report Enhancements — Email & Persistent Job Store | Accepted |
| [ADR-027](027-audit-logging-agent-metrics.md) | Audit Logging & Agent Metrics Dashboard | Accepted |
| [ADR-028](028-credential-provisioning.md) | Runtime LLM Credential Provisioning | Accepted |

## ADR Template

ADRs follow the MADR (Markdown Any Decision Record) format:

1. **Title and Status** - Clear, descriptive title and current status
2. **Context** - Problem statement and background
3. **Decision** - The actual decision made
4. **Consequences** - Positive and negative consequences of the decision
5. **Rationale** - Why this decision was made over alternatives

## ADR Lifecycle

1. **Proposed** - Initial draft under consideration
2. **Accepted** - Decision has been made and implemented
3. **Deprecated** - Decision replaced by newer approach
4. **Superseded** - Decision replaced by specific ADR reference