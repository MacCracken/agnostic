[![CI](https://img.shields.io/github/actions/workflow/status/MacCracken/agnostic/ci.yml?branch=main&label=CI)](https://github.com/MacCracken/agnostic/actions/workflows/ci.yml)
![Coverage](https://img.shields.io/badge/coverage-85%25-brightgreen)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.13-blue)
![Docker](https://img.shields.io/badge/docker-ready-blue)

# Agentic QA Team System

A containerized, multi-agent QA platform powered by CrewAI. Six specialized AI agents collaborate to orchestrate intelligent testing workflows with self-healing, fuzzy verification, risk-based prioritization, and comprehensive reliability/security/performance testing.

Production image embeds Redis, PostgreSQL, and Caddy TLS — no external infrastructure required. External services can be used for HA by setting `REDIS_URL` / `DATABASE_URL`.

## Quick Start

```bash
# 1. Clone and setup
git clone https://github.com/MacCracken/agnostic && cd agnostic
cp .env.example .env
# Edit .env — set OPENAI_API_KEY (or configure AGNOS LLM Gateway)

# 2. Build and launch
docker build -t agnostic:latest .
docker compose up -d

# 3. Access WebGUI
open http://localhost:8000
```

[Full Quick Start Guide](docs/getting-started/quick-start.md)

## 6-Agent Architecture

```
QA Manager (Orchestrator)          ──┐
Senior QA Engineer (Expert)         ─┤
Junior QA Worker (Executor)         ─┤── Embedded Redis + PostgreSQL ── WebGUI (:8000)
QA Analyst (Analyst)                ─┤
Security & Compliance Agent         ─┤     Optional: Caddy TLS (:443)
Performance & Resilience Agent      ─┘
```

| Agent | Capabilities | Primary Focus |
|-------|--------------|---------------|
| **QA Manager** | Test planning, delegation, fuzzy verification | Orchestration |
| **Senior QA Engineer** | Self-healing UI, model-based testing, edge cases, AI test generation | Complex Testing |
| **Junior QA Worker** | Regression, data generation, optimization, cross-platform testing | Test Automation |
| **QA Analyst** | Reporting, security, performance, predictive analytics | Analysis |
| **Security & Compliance Agent** | OWASP, GDPR, PCI DSS, SOC 2, ISO 27001, HIPAA | Security |
| **Performance & Resilience Agent** | Load testing, monitoring, resilience checks | Performance |

## Deployment Options

### Production (Default)

The production image bundles Redis, PostgreSQL, and optionally Caddy for TLS. Just run:

```bash
docker compose up -d
```

### With TLS (Standalone)

```bash
# Provided certs
TLS_ENABLED=true TLS_CERT_PATH=/certs/cert.pem TLS_KEY_PATH=/certs/key.pem \
  docker compose up -d

# Auto-HTTPS (public domain)
TLS_ENABLED=true TLS_DOMAIN=qa.example.com docker compose up -d
```

### External HA Services

```bash
REDIS_URL=redis://ha-redis:6379/0 \
DATABASE_URL=postgresql+asyncpg://user:pass@ha-pg:5432/agnostic \
  docker compose up -d
```

### On AGNOS

When running on [AGNOS](https://github.com/MacCracken/agnosticos), hoosh (LLM Gateway) and daimon (Agent Runtime) are system services. Set `AGNOS_LLM_GATEWAY_ENABLED=true` to route all LLM calls through the gateway — no direct API keys needed.

### Development

```bash
docker compose --profile dev up -d   # separate Redis + PostgreSQL containers
```

[Docker Deployment Guide](docs/deployment/docker-compose.md) | [AGNOS Guide](docs/deployment/agnos.md) | [Kubernetes Guide](docs/deployment/kubernetes.md)

## Documentation

| Guide | Description |
|-------|-------------|
| [Quick Start](docs/getting-started/quick-start.md) | Get running in 5 minutes |
| [Docker Deployment](docs/deployment/docker-compose.md) | Docker setup (production, dev, HA, TLS) |
| [AGNOS Deployment](docs/deployment/agnos.md) | AGNOS-specific deployment |
| [Kubernetes Deployment](docs/deployment/kubernetes.md) | Production K8s with Helm |
| [Development Setup](docs/development/setup.md) | Local development guide |
| [Manual Testing Guide](docs/development/manual-testing.md) | Smoke, integration & E2E test sweep |
| [Agent Docs](docs/agents/index.md) | Agent architecture details |
| [Contributing](docs/development/contributing.md) | Contribution guidelines |
| [Changelog](docs/project/changelog.md) | Version history |
| [Roadmap](docs/development/roadmap.md) | Upcoming work |

### Additional Resources

- [Architecture Decision Records](docs/adr/) — 28 ADRs documenting system design decisions
- [API Documentation](docs/api/) — Agent, WebGUI, LLM, A2A, Tenant APIs
- [Security Assessment](docs/security/assessment.md) — Security findings
- [Dependency Watch](docs/development/dependency-watch.md) — Upstream blockers

## Key Features

- **Embedded Infrastructure**: Redis + PostgreSQL bundled in production image via supervisord
- **Production TLS**: Caddy reverse proxy with auto-HTTPS or provided certs
- **LLM Gateway Integration**: Route all calls through AGNOS hoosh — zero API key sprawl
- **Self-Healing UI Testing**: CV-based element detection with automatic selector repair
- **Fuzzy Verification**: LLM-based quality scoring beyond pass/fail
- **Risk-Based Prioritization**: ML-driven test ordering by risk score
- **Security & Compliance**: Automated OWASP, GDPR, PCI DSS, SOC 2, ISO 27001, HIPAA
- **Predictive Quality Analytics**: Defect prediction, quality trends, release readiness
- **Real-time Dashboard**: Live monitoring via Chainlit WebGUI with WebSocket recovery
- **Multi-Tenant Isolation**: Tenant-scoped keys, rate limiting, and scheduled reports
- **Test Result Persistence**: PostgreSQL-backed storage with quality trends API
- **A2A Protocol**: Agent-to-agent delegation for YEOMAN orchestration
- **MCP Server**: 27 tools for SecureYeoman integration

## Technology Stack

- **Agents**: CrewAI 1.10.1 + litellm
- **LLMs**: OpenAI, Anthropic, Google Gemini, Ollama, LM Studio (or AGNOS LLM Gateway)
- **Web UI**: Chainlit 2.x + FastAPI
- **Database**: PostgreSQL 17 (embedded or external) + SQLAlchemy + asyncpg + Alembic
- **Cache**: Redis (embedded or external)
- **TLS**: Caddy (embedded, optional)
- **Process Manager**: supervisord
- **Automation**: Playwright 1.45+
- **Observability**: OpenTelemetry, Prometheus, structured JSON logging
- **ML/CV**: scikit-learn, OpenCV, NumPy, Pandas

**Python**: 3.13 (production) | **Tests**: 816 unit + 24 E2E

## YEOMAN Integration

Agnostic can be orchestrated by [SecureYeoman](https://github.com/MacCracken/secureyeoman) via 25 MCP bridge tools (`agnostic_*`) and the A2A protocol. The integration is production-ready and feature-gated.

```bash
# In SecureYeoman .env:
MCP_EXPOSE_AGNOSTIC_TOOLS=true
AGNOSTIC_URL=http://agnostic:8000
AGNOSTIC_API_KEY=your-api-key
```

See [SecureYeoman Integration](docs/development/roadmap.md#secureyeoman-integration-complete) for full status.

## Contributing

See [Contributing Guidelines](docs/development/contributing.md).

## License

MIT License - see [LICENSE](LICENSE) file.

---

*Version 2026.3.9* | [Documentation](docs/README.md) | [Changelog](docs/project/changelog.md) | [Roadmap](docs/development/roadmap.md)
