[![CI](https://img.shields.io/github/actions/workflow/status/MacCracken/agnostic/ci.yml?branch=main&label=CI)](https://github.com/MacCracken/agnostic/actions/workflows/ci.yml)
![Coverage](https://img.shields.io/badge/coverage-85%25-brightgreen)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.13-blue)
![Docker](https://img.shields.io/badge/docker-ready-blue)

# AAS — Agnostic Agentics Systems

A containerized, **general-purpose agent platform** powered by CrewAI. Define, assemble, and run any kind of AI agent crew — QA, data engineering, DevOps, or your own custom domain — via JSON/YAML definitions, API requests, or SecureYeoman orchestration.

Ships with a production-ready **QA crew preset** (6 specialized agents for intelligent testing workflows) and example presets for data engineering and DevOps. Create your own agents in minutes with the `BaseAgent` framework and `AgentFactory`.

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

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Agent Definitions (JSON/YAML/API)                          │
│  ┌──────────┐  ┌─────────────────┐  ┌──────────┐           │
│  │ QA Preset│  │ Data-Eng Preset │  │ Custom   │  ...      │
│  └────┬─────┘  └───────┬─────────┘  └────┬─────┘           │
│       └────────────────┼──────────────────┘                 │
│                        ▼                                    │
│              AgentFactory / BaseAgent                        │
│         (Redis + Celery + LLM + CrewAI)                     │
│                        │                                    │
│            ┌───────────┼───────────┐                        │
│            ▼           ▼           ▼                        │
│        Agent 1     Agent 2     Agent N                      │
│            └───────────┼───────────┘                        │
│                        ▼                                    │
│    Embedded Redis + PostgreSQL ── WebGUI (:8000)            │
│                                  Caddy TLS (:443, optional) │
└─────────────────────────────────────────────────────────────┘
```

### Built-in Presets

| Preset | Agents | Domain |
|--------|--------|--------|
| **qa-standard** | QA Manager, Senior QA, Junior QA, QA Analyst, Security & Compliance, Performance | QA / Testing |
| **data-engineering** | Pipeline Architect, Data Quality Engineer, DataOps Engineer | Data Pipelines |
| **devops** | Deployment Manager, Infrastructure Monitor, Incident Responder | DevOps / SRE |

### QA Crew (Default Preset)

| Agent | Capabilities | Primary Focus |
|-------|--------------|---------------|
| **QA Manager** | Test planning, delegation, fuzzy verification | Orchestration |
| **Senior QA Engineer** | Self-healing UI, model-based testing, edge cases, AI test generation | Complex Testing |
| **Junior QA Worker** | Regression, data generation, optimization, cross-platform testing | Test Automation |
| **QA Analyst** | Reporting, security, performance, predictive analytics | Analysis |
| **Security & Compliance Agent** | OWASP, GDPR, PCI DSS, SOC 2, ISO 27001, HIPAA | Security |
| **Performance & Resilience Agent** | Load testing, monitoring, resilience checks | Performance |

### Custom Agents

Create any agent by defining a JSON/YAML file or posting to the API:

```json
{
  "agent_key": "my-agent",
  "name": "My Custom Agent",
  "role": "Domain Expert",
  "goal": "Accomplish domain-specific tasks",
  "backstory": "You are an expert in ...",
  "domain": "my-domain",
  "tools": ["ToolA", "ToolB"]
}
```

```python
from agents.factory import AgentFactory

# From a file
agent = AgentFactory.from_file("agents/definitions/my-agent.json")

# From a preset
crew = AgentFactory.from_preset("qa-standard")

# From a dict (e.g. API request)
agent = AgentFactory.from_dict(request_body)
```

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
| [Agent Framework](docs/agents/index.md) | BaseAgent, AgentFactory, presets, custom agents |
| [Docker Deployment](docs/deployment/docker-compose.md) | Docker setup (production, dev, HA, TLS) |
| [AGNOS Deployment](docs/deployment/agnos.md) | AGNOS-specific deployment |
| [Kubernetes Deployment](docs/deployment/kubernetes.md) | Production K8s with Helm |
| [Development Setup](docs/development/setup.md) | Local development guide |
| [Manual Testing Guide](docs/development/manual-testing.md) | Smoke, integration & E2E test sweep |
| [Contributing](docs/development/contributing.md) | Contribution guidelines |
| [Changelog](docs/project/changelog.md) | Version history |
| [Roadmap](docs/development/roadmap.md) | Upcoming work |

### Additional Resources

- [Architecture Decision Records](docs/adr/) — 28 ADRs documenting system design decisions
- [API Documentation](docs/api/) — Agent, WebGUI, LLM, A2A, Tenant APIs
- [Security Assessment](docs/security/assessment.md) — Security findings
- [Dependency Watch](docs/development/dependency-watch.md) — Upstream blockers

## Key Features

- **General-Purpose Agent Platform**: Define and run any kind of agent crew via JSON/YAML presets
- **BaseAgent Framework**: Shared Redis/Celery/LLM/CrewAI init — write domain logic, not boilerplate
- **AgentFactory**: Create agents from files, dicts, or presets in one line
- **Tool Registry**: Register custom BaseTool subclasses, resolved by name at agent init
- **Embedded Infrastructure**: Redis + PostgreSQL bundled in production image via supervisord
- **Production TLS**: Caddy reverse proxy with auto-HTTPS or provided certs
- **LLM Gateway Integration**: Route all calls through AGNOS hoosh — zero API key sprawl
- **Self-Healing UI Testing**: CV-based element detection with automatic selector repair (QA preset)
- **Fuzzy Verification**: LLM-based quality scoring beyond pass/fail (QA preset)
- **Security & Compliance**: Automated OWASP, GDPR, PCI DSS, SOC 2, ISO 27001, HIPAA (QA preset)
- **Predictive Quality Analytics**: Defect prediction, quality trends, release readiness (QA preset)
- **Real-time Dashboard**: Live monitoring via Chainlit WebGUI with WebSocket recovery
- **Multi-Tenant Isolation**: Tenant-scoped keys, rate limiting, and scheduled reports
- **Result Persistence**: PostgreSQL-backed storage with quality trends API
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

**Python**: 3.13 (production) | **Tests**: 865 unit + 24 E2E

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

*Version 2026.3.14* | [Documentation](docs/README.md) | [Changelog](docs/project/changelog.md) | [Roadmap](docs/development/roadmap.md)
