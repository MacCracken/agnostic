# CLAUDE.md

AI assistant guidance for Claude Code. Full project documentation lives in [docs/](docs/).

## Quick Commands

```bash
# Docker (recommended)
cp .env.example .env             # configure OPENAI_API_KEY, RABBITMQ_USER, RABBITMQ_PASSWORD
./scripts/build-docker.sh --base-only   # one-time base build (~5 min)
./scripts/build-docker.sh --agents-only # subsequent rebuilds (~30 sec)
docker-compose up -d

# Tests
pytest tests/unit/ -v
python run_tests.py --mode all --env mock

# Code quality
ruff check agents/ config/ shared/ webgui/
ruff format agents/ config/ shared/ webgui/
mypy agents/ config/ shared/
bandit -r agents/ config/ shared/
```

## Key Files

| Purpose | Path |
|---------|------|
| REST API endpoints | `webgui/api.py` |
| Chainlit app + middleware | `webgui/app.py` |
| JWT + OAuth2 + API key auth | `webgui/auth.py` |
| Agent registry (plugin arch) | `config/agent_registry.py` |
| LLM routing | `config/universal_llm_adapter.py` |
| Tool LLM calls (litellm) | `config/llm_integration.py` |
| Provider config | `config/models.json` |
| Resilience primitives | `shared/resilience.py` |
| Prometheus metrics | `shared/metrics.py` |
| Team size presets | `config/team_config.json` |

## Documentation

| Guide | Path |
|-------|------|
| Development setup | [docs/development/setup.md](docs/development/setup.md) |
| Agent architecture | [docs/agents/index.md](docs/agents/index.md) |
| API reference | [docs/api/webgui.md](docs/api/webgui.md) |
| Adding new agents | [docs/development/setup.md#adding-new-agents](docs/development/setup.md#adding-new-agents) |
| Roadmap | [docs/development/roadmap.md](docs/development/roadmap.md) |
| Changelog | [docs/project/changelog.md](docs/project/changelog.md) |
| Dependency blockers | [docs/development/dependency-watch.md](docs/development/dependency-watch.md) |
| ADRs | [docs/adr/](docs/adr/) |

## currentDate
Today's date is 2026-02-28.
