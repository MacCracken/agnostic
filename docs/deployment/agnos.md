# AGNOS Deployment Guide

Deploy Agnostic QA Platform with AGNOS services (hoosh LLM Gateway + daimon Agent Runtime).

## Prerequisites

- Docker Engine 24+ with Compose v2
- AGNOS container images (hoosh + daimon) — either built locally from agnosticos or pulled from GHCR
- At least one LLM provider API key (held by hoosh, **not** by Agnostic)

## Quick Start

```bash
# 1. Build AGNOS-aware base image (one-time)
docker build -f docker/Dockerfile.agnos -t agnostic-qa-base:agnos .

# 2. Build agent + webgui images on top
./scripts/build-docker.sh --agents-only

# 3. Configure
cp .env.example .env
# Edit .env — set POSTGRES_PASSWORD, OPENAI_API_KEY (for hoosh), etc.

# 4. Start
docker compose -f docker-compose.agnos.yml up -d

# 5. With distributed agent workers
docker compose -f docker-compose.agnos.yml --profile workers up -d
```

## Architecture

```
┌──────────────┐     ┌─────────────┐
│   webgui     │────▶│   hoosh     │──▶ OpenAI / Anthropic / Google
│  :8000       │     │  LLM GW     │
│              │     │  :8088      │
│  agents      │     └─────────────┘
│  (in-proc)   │
│              │     ┌─────────────┐
│              │────▶│   daimon    │
│              │     │  Agent RT   │
└──────────────┘     │  :8090      │
       │             └─────────────┘
       ▼
  ┌─────────┐  ┌──────────┐
  │  Redis  │  │ Postgres │
  │  :6379  │  │  :5433   │
  └─────────┘  └──────────┘
```

- **hoosh** (port 8088): LLM Gateway. Holds all provider API keys. Exposes an OpenAI-compatible `/v1/chat/completions` endpoint. Agnostic routes all LLM calls through it via litellm.
- **daimon** (port 8090): Agent Runtime. Receives agent registration, heartbeats, audit events, reasoning traces, and dashboard data from Agnostic.

## Environment Variables

### Required

| Variable | Description |
|----------|-------------|
| `POSTGRES_PASSWORD` | PostgreSQL password |
| `OPENAI_API_KEY` | LLM provider key — set in `.env`, consumed by **hoosh** (not Agnostic) |

### AGNOS Integration (set automatically by `docker-compose.agnos.yml`)

| Variable | Default | Description |
|----------|---------|-------------|
| `AGNOS_LLM_GATEWAY_ENABLED` | `true` | Route LLM calls through hoosh |
| `AGNOS_LLM_GATEWAY_URL` | `http://hoosh:8088` | hoosh endpoint |
| `AGNOS_LLM_GATEWAY_MODEL` | `default` | Model alias in hoosh |
| `AGNOS_LLM_GATEWAY_API_KEY` | (empty) | API key for hoosh (if required) |
| `AGNOS_AGENT_REGISTRATION_ENABLED` | `true` | Register agents with daimon |
| `AGNOS_AGENT_REGISTRY_URL` | `http://daimon:8090` | daimon endpoint |
| `AGNOS_HEARTBEAT_INTERVAL_SECONDS` | `30` | Agent heartbeat frequency |
| `AGNOS_PATH_PREFIX` | `/v1` | REST path prefix for AGNOS APIs |
| `AGNOS_AUDIT_ENABLED` | `true` | Forward audit events to daimon |
| `AGNOS_DASHBOARD_BRIDGE_ENABLED` | `true` | Push dashboard data to daimon |
| `AGNOS_REASONING_ENABLED` | `true` | Submit reasoning traces to daimon |
| `AGNOS_TOKEN_BUDGET_ENABLED` | `true` | Check token budgets via hoosh |
| `AGNOS_PROFILE` | (empty) | Environment profile: `dev`, `staging`, or `prod` |

### Optional

| Variable | Default | Description |
|----------|---------|-------------|
| `AGNOS_HOOSH_IMAGE` | `ghcr.io/maccracken/agnosticos:alpha` | hoosh container image |
| `AGNOS_DAIMON_IMAGE` | `ghcr.io/maccracken/agnosticos:alpha` | daimon container image |
| `AGNOS_AGENT_API_KEY` | (empty) | API key for daimon registration |
| `AGNOS_TOKEN_BUDGET_POOL` | `agnostic-qa` | Token budget pool name |

## Health Checks

```bash
# All services
docker compose -f docker-compose.agnos.yml ps

# Individual service health
curl http://localhost:8000/health      # webgui
curl http://localhost:8088/v1/health   # hoosh
curl http://localhost:8090/v1/health   # daimon

# Verify gateway routing (webgui should show gateway in LLM config)
curl http://localhost:8000/api/v1/agents/status
```

## Networking

All services communicate on the `qa-network` Docker bridge network. Service names (`hoosh`, `daimon`, `redis`, `postgres`) resolve via Docker DNS.

| Service | Internal Port | External Port |
|---------|---------------|---------------|
| webgui | 8000 | 8000 |
| hoosh | 8088 | 8088 |
| daimon | 8090 | 8090 |
| redis | 6379 | 6379 |
| postgres | 5432 | 5433 |

## Standalone vs AGNOS Mode

| Feature | Standalone (`docker-compose.yml`) | AGNOS (`docker-compose.agnos.yml`) |
|---------|-----------------------------------|------------------------------------|
| LLM keys | In Agnostic's `.env` | In hoosh only |
| LLM routing | Direct to provider | Through hoosh gateway |
| Agent registration | None | Registers with daimon |
| Heartbeats | None | Every 30s to daimon |
| Audit forwarding | Local only | Forwarded to daimon |
| Token budgets | None | Enforced by hoosh |

## Troubleshooting

**webgui fails to start**: Check that hoosh and daimon are healthy first. The webgui `depends_on` ensures ordering, but health checks may need time.

**LLM calls return fallbacks**: Verify hoosh has valid provider keys (`OPENAI_API_KEY` in `.env`). Check hoosh logs: `docker compose -f docker-compose.agnos.yml logs hoosh`.

**Agent registration fails**: Check daimon logs and ensure `AGNOS_AGENT_REGISTRATION_ENABLED=true`. Registration failure is non-fatal — Agnostic continues to work without it.

**Path prefix mismatch**: If using a custom AGNOS build with different API paths, set `AGNOS_PATH_PREFIX` accordingly (default `/v1`).

## E2E Testing

```bash
# Start AGNOS stack
docker compose -f docker-compose.agnos.yml up -d

# Run E2E gateway tests
pytest tests/e2e/test_agnos_gateway.py -v

# Override URLs if needed
HOOSH_URL=http://localhost:8088 DAIMON_URL=http://localhost:8090 \
  pytest tests/e2e/test_agnos_gateway.py -v
```
