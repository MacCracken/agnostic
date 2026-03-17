# Development Setup

Detailed instructions for setting up a local development environment for the Agentic QA Team System.

> **Note on Python versions:** Production containers run **Python 3.13-slim**. The local `.venv` may run a newer version; Python 3.14 cannot install the full stack due to upstream blockers — see [Dependency Watch](dependency-watch.md).

---

## Prerequisites

- Python 3.11–3.13 (3.13 in production; 3.14 blocked upstream)
- Docker 20.10+ and Docker Compose
- Git
- 4 GB+ RAM for parallel agent execution
- OpenAI API key (or another supported LLM provider — see [LLM Providers](#llm-providers))

---

## Setup

### 1. Clone and configure

```bash
git clone https://github.com/MacCracken/agnostic && cd agnostic
cp .env.example .env
# Required: set OPENAI_API_KEY (and RABBITMQ_USER / RABBITMQ_PASSWORD)
```

### 2. Install dependencies

```bash
# Full install (recommended for development)
pip install -e ".[dev,test,web,ml,browser,observability]"

# Minimal install (unit tests only — avoids chainlit/playwright wheels)
pip install -e ".[dev,test,ml,observability]"
```

### 3. Start infrastructure services

```bash
docker compose up -d redis rabbitmq
docker compose ps   # verify both are healthy
```

### 4. Run agents in development mode

In separate terminal windows (or use `tmux`):

```bash
python -m agents.manager.qa_manager
python -m agents.senior.senior_qa
python -m agents.junior.junior_qa
python -m agents.analyst.qa_analyst
python -m agents.security_compliance.qa_security_compliance
python -m agents.performance.qa_performance
```

### 5. Start the WebGUI

```bash
python -m webgui.app
# Access at http://localhost:8000
```

---

## Docker (recommended)

```bash
# Build the single image
docker build -t agnostic:latest .

# Production (on AGNOS host)
docker compose up -d

# Development (adds redis + postgres containers)
docker compose --profile dev up -d

# View logs
docker compose logs -f agnostic
```

**Access URLs (Docker):**
- WebGUI: `http://localhost:8000`

---

## Testing

```bash
# All tests with mocks (no external services needed)
.venv/bin/python -m pytest tests/ -v

# Unit tests only
.venv/bin/python -m pytest tests/unit/ -v

# Integration tests (requires Docker services)
.venv/bin/python -m pytest tests/integration/ -m integration

# Coverage report
.venv/bin/python -m pytest --cov=agents --cov=webgui --cov=config
```

**Test structure:**
- `tests/unit/` — fast, no external dependencies
- `tests/integration/` — require Redis + RabbitMQ

---

## Code Quality

```bash
ruff check agents/ config/ shared/ webgui/   # lint
ruff format agents/ config/ shared/ webgui/  # format
mypy agents/ config/ shared/                 # type-check
bandit -r agents/ config/ shared/            # security scan

pre-commit install        # install git hooks (run once)
pre-commit run --all-files
```

---

## Architecture

```
QA Manager (Orchestrator)          ──┐
Senior QA Engineer (Expert)         ─┤
Junior QA Worker (Executor)         ─┤
QA Analyst (Analyst)                ─┼── Redis + RabbitMQ Bus ── Chainlit WebGUI (:8000)
Security & Compliance Agent         ─┤
Performance & Resilience Agent      ─┘
```

### Agent roles and tools

| Agent | File | Tools |
|-------|------|-------|
| **QA Manager** | `agents/manager/qa_manager.py` | `TestPlanDecompositionTool`, `FuzzyVerificationTool` |
| **Senior QA** | `agents/senior/senior_qa.py` | `SelfHealingTool`, `ModelBasedTestingTool`, `EdgeCaseAnalysisTool`, `AITestGenerationTool`, `CodeAnalysisTestGeneratorTool`, `AutonomousTestDataGeneratorTool` |
| **Junior QA** | `agents/junior/junior_qa.py` | `RegressionTestingTool`, `SyntheticDataGeneratorTool`, `TestExecutionOptimizerTool`, `FlakyTestDetectionTool`, `VisualRegressionTool`, `UXUsabilityTestingTool`, `LocalizationTestingTool`, `MobileAppTestingTool`, `DesktopAppTestingTool`, `CrossPlatformTestingTool` |
| **QA Analyst** | `agents/analyst/qa_analyst.py` | `DataOrganizationReportingTool`, `SecurityAssessmentTool`, `PerformanceProfilingTool`, `TestTraceabilityTool`, `DefectPredictionTool`, `QualityTrendAnalysisTool`, `RiskScoringTool`, `ReleaseReadinessTool` |
| **Security & Compliance** | `agents/security_compliance/qa_security_compliance.py` | `ComprehensiveSecurityAssessmentTool`, `GDPRComplianceTool`, `PCIDSSComplianceTool`, `SOC2ComplianceTool`, `ISO27001ComplianceTool`, `HIPAAComplianceTool` |
| **Performance & Resilience** | `agents/performance/qa_performance.py` | `PerformanceMonitoringTool`, `LoadTestingTool`, `ResilienceValidationTool`, `AdvancedProfilingTool` |

### Key modules

| Module | Purpose |
|--------|---------|
| `config/agent_registry.py` | Preset-driven `AgentRegistry` + `AgentDefinition`; loads from `agents/definitions/presets/` |
| `config/model_manager.py` | Multi-provider LLM manager (OpenAI, Anthropic, Google, Ollama, LM Studio) with fallback chains |
| `config/models.json` | Provider routing strategy, retries, timeouts |
| `config/llm_integration.py` | Direct LLM calls via litellm for tool implementations (scenario gen, fuzzy verification, etc.) |
| `config/environment.py` | `Config` class — env vars, Redis client factory, Celery app factory |
| `agents/crew_assembler.py` | Team assembly from role specs; preset recommendation |
| `shared/metrics.py` | Prometheus metrics with no-op fallback; `get_metrics_text()` |
| `shared/logging_config.py` | Structured logging — JSON via structlog or stdlib text |
| `shared/resilience.py` | `CircuitBreaker`, `retry_async` decorator, `GracefulShutdown` |
| `shared/crewai_compat.py` | `crewai.tools.BaseTool` import with fallback stub |
| `shared/data_generation_service.py` | Synthetic test data generation |
| `webgui/api.py` | FastAPI REST router — auth, tasks, dashboard, sessions, reports, agents, A2A |
| `webgui/app.py` | Chainlit app — chat interface + security headers middleware |
| `webgui/realtime.py` | WebSocket / Redis Pub/Sub infrastructure |
| `webgui/exports.py` | PDF / JSON / CSV report generation |
| `webgui/auth.py` | JWT + API key auth, OAuth2 (Google/GitHub/Azure AD), RBAC |

---

## Technology Stack

| Layer | Library | Version |
|-------|---------|---------|
| Agent framework | crewai | `>=1.0.0,<2.0.0` |
| LLM routing | litellm | (via crewai) |
| Web UI | Chainlit + FastAPI | `>=2.0.0,<3.0.0` / `>=0.116.1` |
| Messaging | Redis + Celery + RabbitMQ | `>=5.0.8` / `>=5.4.0` |
| Browser automation | Playwright | `>=1.45.0` |
| ML / CV | scikit-learn, OpenCV, NumPy, Pandas | `>=1.5.1` / `>=4.10.0` |
| Testing | pytest | `>=8.3.2` |

> LangChain was removed on 2026-02-28. See [Dependency Watch](dependency-watch.md) for upstream blockers.

### LLM Providers

crewAI 1.x uses **litellm** internally, giving access to 100+ providers with a single model-string API:

| Provider | Model string example |
|----------|---------------------|
| OpenAI | `gpt-4o`, `gpt-4o-mini` |
| Anthropic | `anthropic/claude-opus-4-5` |
| Google Gemini | `gemini/gemini-2.0-flash` |
| Ollama (local) | `ollama/llama3.3` |
| LM Studio (local) | `openai/local-model` (OpenAI-compatible API) |
| Azure OpenAI | `azure/your-deployment-name` |
| AGNOS OS Gateway | configure `AGNOS_LLM_GATEWAY_URL` (see [ADR-021](../adr/021-agnosticos-integration.md)) |

Set `PRIMARY_MODEL_PROVIDER` and `OPENAI_MODEL` (or equivalent) in `.env`. Fallback chains are configured in `config/models.json`.

---

## Environment Variables

See `.env.example` for the full list with comments. Key variables:

### Connection

```bash
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=          # blank for local dev
RABBITMQ_HOST=localhost
RABBITMQ_PORT=5672
RABBITMQ_USER=qa_user
RABBITMQ_PASSWORD=change_me_strong_password
RABBITMQ_VHOST=/
```

### LLM

```bash
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o
PRIMARY_MODEL_PROVIDER=openai
FALLBACK_MODEL_PROVIDERS=anthropic,ollama
# Optional Anthropic / Google keys
ANTHROPIC_API_KEY=
GOOGLE_API_KEY=
```

### Feature flags

```bash
ENABLE_SELF_HEALING=true
ENABLE_FUZZY_VERIFICATION=true
ENABLE_RISK_BASED_PRIORITIZATION=true
ENABLE_CONTEXT_AWARE_TESTING=true
```

### WebGUI / auth

```bash
WEBGUI_SECRET_KEY=change_me_in_production
ENVIRONMENT=development          # set to "production" to enforce secret key
OAUTH2_GOOGLE_CLIENT_ID=
OAUTH2_GOOGLE_CLIENT_SECRET=
WEBSOCKET_ENABLED=true
REDIS_PUBSUB_CHANNEL=webgui_updates
REPORT_EXPORT_PATH=/app/reports
AGNOSTIC_API_KEY=               # static API key for M2M auth
CORS_ALLOWED_ORIGINS=http://localhost:18789,http://localhost:3001
```

---

## Adding New Agents

Adding a new agent or crew requires **no code changes** to the WebGUI or orchestration layer:

1. **Create a preset** — add a JSON file to `agents/definitions/presets/` following the `{domain}-{size}.json` naming convention. Define agents with `agent_key`, `name`, `role`, `goal`, `backstory`, `focus`, `domain`, and `tools`.
2. **Or create an individual definition** — add a JSON file to `agents/definitions/` for single agents that can be composed into ad-hoc crews via the API.
3. **Or use the API** — POST `/api/v1/presets` or POST `/api/v1/definitions` to create presets/agents dynamically.
4. **Or use the team assembler** — POST `/api/v1/crews` with a `team` spec to describe members by role and context; the assembler matches existing agents or generates inline definitions.

The `AgentRegistry` in `config/agent_registry.py` loads all presets at startup. The crew builder at `webgui/routes/crews.py` handles execution.

---

## Database Migrations (Alembic)

The project uses [Alembic](https://alembic.sqlalchemy.org/) for PostgreSQL schema migrations with async support via `asyncpg`.

### Prerequisites

PostgreSQL must be running and accessible. Configure connection via environment variables:

```bash
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=secret
POSTGRES_DB=agnostic
```

### Running migrations

```bash
# Apply all pending migrations
alembic upgrade head

# Check current revision
alembic current

# View migration history
alembic history --verbose
```

### Creating new migrations

After modifying models in `shared/database/models.py` or `shared/database/tenants.py`:

```bash
# Auto-generate migration from model changes (requires DB connection)
alembic revision --autogenerate -m "describe your change"

# Or create a manual migration
alembic revision -m "describe your change"
# Then edit the generated file in alembic/versions/
```

### Downgrading

```bash
# Roll back one migration
alembic downgrade -1

# Roll back to a specific revision
alembic downgrade <revision_id>

# Roll back everything
alembic downgrade base
```

### Key files

| File | Purpose |
|------|---------|
| `alembic.ini` | Alembic configuration (URL set dynamically from env vars) |
| `alembic/env.py` | Async engine setup, model imports for autogenerate |
| `alembic/versions/` | Migration scripts |

> **Note:** The initial migration (`db8d3fe1686e_initial_schema.py`) creates all 7 tables: `test_sessions`, `test_results`, `test_metrics`, `test_reports`, `tenants`, `tenant_users`, `tenant_api_keys`. If your database was created by SQLAlchemy's `create_all()` before Alembic was added, stamp it: `alembic stamp head`.

---

## Common Tasks

```bash
# Restart the agnostic container
docker compose restart agnostic

# Add custom LLM provider (edit config/models.json)
# Add test data
mkdir -p shared/data && cp my_data.csv shared/data/
```

---

## Troubleshooting

See [Quick Start — Troubleshooting](../getting-started/quick-start.md#troubleshooting) for port conflicts, agent startup failures, Redis/RabbitMQ issues, and LLM API errors.

See [Dependency Watch](dependency-watch.md) for known Python version and dependency blockers.

---

*Related: [Contributing](contributing.md) · [Manual Testing](manual-testing.md) · [Agent Docs](../agents/index.md) · [API Reference](../api/webgui.md)*
