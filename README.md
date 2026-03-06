[![CI/CD](https://img.shields.io/github/actions/workflow/status/MacCracken/Agnostic/ci-cd.yml?branch=main&label=CI/CD)](https://github.com/MacCracken/Agnostic/actions/workflows/ci-cd.yml)
![Coverage](https://img.shields.io/badge/coverage-85%25-brightgreen)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.11+-blue)
![Docker](https://img.shields.io/badge/docker-ready-blue)

# Agentic QA Team System

A containerized, multi-agent QA platform powered by CrewAI. Six specialized AI agents collaborate via Redis/RabbitMQ to orchestrate intelligent testing workflows with self-healing, fuzzy verification, risk-based prioritization, and comprehensive reliability/security/performance testing.

## Quick Start

```bash
# 1. Clone and setup
git clone https://github.com/MacCracken/agnostic && cd agnostic
cp .env.example .env
# Edit .env — required:
#   OPENAI_API_KEY=sk-...
#   RABBITMQ_USER=qa_user
#   RABBITMQ_PASSWORD=your_strong_password

# 2. Launch (Docker)
docker compose up --build -d

# 3. Access WebGUI
open http://localhost:8000
```

[Full Quick Start Guide →](docs/getting-started/quick-start.md)

## 6-Agent Architecture

```
QA Manager (Orchestrator)          ──┐
Senior QA Engineer (Expert)         ─┤
Junior QA Worker (Executor)         ─┤
QA Analyst (Analyst)                ─┼── Redis + RabbitMQ ── WebGUI (:8000)
Security & Compliance Agent         ─┤
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

## Documentation

| Guide | Description |
|-------|-------------|
| [Quick Start](docs/getting-started/quick-start.md) | Get running in 5 minutes |
| [Docker Deployment](docs/deployment/docker-compose.md) | Local & production Docker setup |
| [Kubernetes Deployment](docs/deployment/kubernetes.md) | Production K8s with Helm |
| [Development Setup](docs/development/setup.md) | Local development guide |
| [Manual Testing Guide](docs/development/manual-testing.md) | Smoke, integration & E2E test sweep |
| [Agent Docs](docs/agents/index.md) | Agent architecture details |
| [Contributing](docs/development/contributing.md) | Contribution guidelines |
| [Changelog](docs/project/changelog.md) | Version history |
| [Roadmap](docs/development/roadmap.md) | Upcoming work (pending items only) |

### Additional Resources

- [Architecture Decision Records](docs/adr/) — 27 ADRs documenting system design decisions
- [API Documentation](docs/api/) — Agent, WebGUI, LLM APIs
- [Tenant Provisioning](docs/api/tenant-provisioning.md) — Multi-tenant setup and isolation
- [Security Assessment](docs/security/assessment.md) — Security findings
- [Docker Build](docker/README.md) — Build optimization
- [Dependency Watch](docs/development/dependency-watch.md) — Upstream blockers & compatibility tracking
- [Helm Chart](k8s/helm/agentic-qa/README.md) — K8s deployment

## Deployment Options

### Docker Compose (Recommended for Local)

```bash
# Optimized build (99% faster)
./scripts/build-docker.sh --base-only  # One-time (~5 min)
./scripts/build-docker.sh --agents-only  # Rebuilds (~30 sec)
docker compose up -d
```

[Docker Deployment Guide →](docs/deployment/docker-compose.md)

### Kubernetes (Production)

```bash
# Using Helm (recommended)
helm install agentic-qa ./k8s/helm/agentic-qa \
  --namespace agentic-qa \
  --create-namespace \
  --set secrets.openaiApiKey=$(echo -n "your-key" | base64)
```

[Kubernetes Deployment Guide →](docs/deployment/kubernetes.md)

## Usage Example

```python
from agents.manager.qa_manager_optimized import OptimizedQAManager

manager = OptimizedQAManager()
result = await manager.orchestrate_qa_session({
    "requirements": "Test user authentication flow",
    "target_url": "http://localhost:8000",
    "compliance_standards": ["GDPR", "PCI DSS", "SOC 2", "ISO 27001", "HIPAA"]
})
```

## Key Features

- **Self-Healing UI Testing**: CV-based element detection with automatic selector repair
- **Fuzzy Verification**: LLM-based quality scoring beyond pass/fail
- **Risk-Based Prioritization**: ML-driven test ordering by risk score
- **Security & Compliance**: Automated OWASP, GDPR, PCI DSS, SOC 2, ISO 27001, HIPAA validation
- **Cross-Platform Testing**: Web, mobile (iOS/Android), and desktop (Windows/macOS/Linux) unified testing
- **Predictive Quality Analytics**: ML-driven defect prediction, quality trend analysis, risk scoring, and release readiness assessment
- **AI-Enhanced Test Generation**: Autonomous test case generation from requirements and code analysis using LLM
- **Performance Profiling**: Load testing with bottleneck identification
- **Real-time Dashboard**: Live monitoring via Chainlit WebGUI with WebSocket missed-message recovery
- **Multi-Tenant Isolation**: Tenant-scoped Redis keys, API keys, rate limiting, and scheduled reports
- **Test Result Persistence**: PostgreSQL-backed storage for sessions, results, metrics, and reports with quality trends API
- **Structured Audit Logging**: JSON audit trail for auth, task, report, tenant, and system events
- **Agent & LLM Metrics Dashboard**: Per-agent task counts, success rates, and LLM token usage via Prometheus
- **Scheduled Report Delivery**: Automated reports via webhook (HMAC-signed), Slack, and email with retry logic
- **A2A Protocol**: Agent-to-agent delegation for YEOMAN orchestration

## Technology Stack

- **Agents**: CrewAI 1.x + litellm (LangChain removed)
- **LLMs**: OpenAI, Anthropic, Google Gemini, Ollama, LM Studio
- **Web UI**: Chainlit 1.1+ / 2.x compatible + FastAPI
- **Messaging**: Redis 5.0+ + RabbitMQ + Celery
- **Database**: PostgreSQL (optional, async via SQLAlchemy + asyncpg) + Alembic migrations
- **Scheduling**: APScheduler with Redis or PostgreSQL job store
- **Automation**: Playwright 1.45+
- **Observability**: Prometheus metrics, structured JSON logging, audit logging
- **ML/CV**: scikit-learn, OpenCV, NumPy, Pandas

**Python**: 3.11–3.13 (production); 3.14 not yet supported (see [Dependency Watch](docs/development/dependency-watch.md))

**Tests**: 465 unit + 19 E2E (CI via GitHub Actions)

## YEOMAN Integration

Agnostic can be orchestrated by [SecureYeoman](https://github.com/MacCracken/secureyeoman) via 10 MCP bridge tools (`agnostic_*`). The integration is production-ready — Priorities P1–P4 are fully implemented.

### Quick setup

```bash
# 1. Start the Agnostic stack (or set AGNOSTIC_AUTO_START=true in YEOMAN's .env)
docker compose up -d

# 2. Configure YEOMAN
MCP_EXPOSE_AGNOSTIC_TOOLS=true
AGNOSTIC_URL=http://127.0.0.1:8000
AGNOSTIC_API_KEY=your-api-key      # preferred (P2 implemented)
```

### Available MCP tools

| Tool | Purpose |
|------|---------|
| `agnostic_health` | Reachability check |
| `agnostic_agents_status` | Per-agent live status |
| `agnostic_agents_queues` | RabbitMQ queue depths |
| `agnostic_dashboard` | Aggregate metrics |
| `agnostic_session_list` | Recent QA sessions |
| `agnostic_session_detail` | Full session results |
| `agnostic_generate_report` | Generate exec/security/perf report |
| `agnostic_submit_qa` | Submit a QA task (REST, webhook-ready) |
| `agnostic_task_status` | Poll task status |
| `agnostic_delegate_a2a` | Delegate via A2A protocol (requires P8) |

See the [Roadmap](docs/development/roadmap.md) for pending work and the [Changelog](docs/project/changelog.md) for completed work.

## Contributing

See [Contributing Guidelines](docs/development/contributing.md).

## License

MIT License - see [LICENSE](LICENSE) file.

---

*Last Updated: 2026-03-05* | [Documentation](docs/README.md) | [Changelog](docs/project/changelog.md) | [Roadmap](docs/development/roadmap.md)
