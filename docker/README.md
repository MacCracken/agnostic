# Docker Build

Single image build for the AAS (Agnostic Agent System) platform.

## Build

```bash
./scripts/build-docker.sh
```

This produces `agnostic:latest` (and `agnostic:<version>` from the VERSION file).

## Run

```bash
# Production (on AGNOS host — webgui only)
docker compose up -d

# Development (simulate AGNOS with containers)
docker compose --profile dev up -d

# Development + distributed workers
docker compose --profile dev --profile workers up -d
```

## Image

One image serves all roles and agent domains (QA, data-engineering, devops, custom):

- **webgui** (default CMD) — Chainlit + FastAPI web interface, agents run in-process
- **workers** (via `agent-entrypoint.sh`) — distributed agent workers selected by `AGENT_ROLE` env var
- **crews** — any domain crew can be assembled and run via the `/api/v1/crews` endpoint or presets

```
┌──────────────────────────────────────┐
│          agnostic:latest             │
│                                      │
│  Python 3.13 + all dependencies      │
│  • CrewAI 1.x + litellm             │
│  • Chainlit + FastAPI + Uvicorn      │
│  • Redis + Celery                    │
│  • Playwright + Chromium             │
│  • OpenCV + scikit-learn + pandas    │
│                                      │
│  Application code:                   │
│  • webgui/  agents/  config/  shared/│
│  • agents/definitions/presets/       │
│                                      │
│  CMD: chainlit run webgui/app.py     │
│  ALT: ./agent-entrypoint.sh (worker) │
└──────────────────────────────────────┘
```

## Build Performance

| Scenario | Time |
|----------|------|
| First build | ~10-15 min |
| Code-only change | ~30 sec (cached deps layer) |

## Files

| File | Purpose |
|------|---------|
| `Dockerfile` | Single-stage image definition |
| `docker/agent-entrypoint.sh` | Worker entrypoint (resolves `AGENT_ROLE`) |
| `requirements-docker.txt` | Runtime Python dependencies |
| `scripts/build-docker.sh` | Build script |

## Troubleshooting

**Rebuild after dependency changes:**

```bash
./scripts/build-docker.sh  # rebuilds from requirements-docker.txt layer
```

**Clean build (no cache):**

```bash
docker build --no-cache -t agnostic:latest .
```
