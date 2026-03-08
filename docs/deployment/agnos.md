# AGNOS Deployment Guide

Deploy Agnostic QA Platform on AGNOS — or simulate the AGNOS environment in dev containers.

## Understanding AGNOS

AGNOS is an operating system. In production, **hoosh** (LLM Gateway), **daimon** (Agent Runtime), **Redis**, and **PostgreSQL** are all system services running on the host — not containers. Only the `webgui` container is needed.

For development without an AGNOS host, use `--profile dev` to spin up these services as containers.

## Quick Start

```bash
# 1. Build base + webgui images
./scripts/build-docker.sh --base-only   # one-time (~5 min)
./scripts/build-docker.sh --agents-only # rebuilds (~30 sec)

# 2. Configure
cp .env.example .env
# Edit .env — set POSTGRES_PASSWORD, provider API keys, etc.

# 3a. Production (on AGNOS host — only webgui)
docker compose -f docker-compose.agnos.yml up -d

# 3b. Development (simulate AGNOS with containers)
docker compose -f docker-compose.agnos.yml --profile dev up -d

# 3c. Development with distributed workers
docker compose -f docker-compose.agnos.yml --profile dev --profile workers up -d
```

## Compose Profiles

| Profile | Services | Use Case |
|---------|----------|----------|
| (none) | `webgui` | Production on AGNOS host |
| `dev` | `webgui` + `agnos` + `redis` + `postgres` | Local development |
| `dev` + `workers` | All above + `rabbitmq` + 6 agent workers | Full distributed stack |

## Architecture

```
Production (on AGNOS host):
┌──────────────┐
│   webgui     │──▶ hoosh (system service :8088) ──▶ LLM providers
│  :8000       │──▶ daimon (system service :8090)
│  agents      │──▶ Redis (system service :6379)
│  (in-proc)   │──▶ Postgres (system service :5432)
└──────────────┘

Dev (containerized):
┌──────────────┐     ┌─────────────┐
│   webgui     │────▶│   agnos     │──▶ OpenAI / Anthropic / Google
│  :8000       │     │  hoosh:8088 │
│              │     │  daimon:8090│
│  agents      │     └─────────────┘
│  (in-proc)   │
└──────────────┘
       │
  ┌─────────┐  ┌──────────┐
  │  Redis  │  │ Postgres │
  │  :6379  │  │  :5433   │
  └─────────┘  └──────────┘
```

- **hoosh** (port 8088): LLM Gateway. Holds all provider API keys. Exposes OpenAI-compatible `/v1/chat/completions`. Agnostic routes all LLM calls through it via litellm.
- **daimon** (port 8090): Agent Runtime. Receives agent registration, heartbeats, audit events, reasoning traces, and dashboard data.
- **agnos container** (dev only): Runs both hoosh and daimon in a single process via the `daemon` entrypoint.

## Environment Variables

### Required

| Variable | Description |
|----------|-------------|
| `POSTGRES_PASSWORD` | PostgreSQL password |
| `OPENAI_API_KEY` | LLM provider key — consumed by **hoosh** (not Agnostic) |

### AGNOS Integration (set automatically by `docker-compose.agnos.yml`)

| Variable | Default | Description |
|----------|---------|-------------|
| `AGNOS_LLM_GATEWAY_ENABLED` | `true` | Route LLM calls through hoosh |
| `AGNOS_LLM_GATEWAY_URL` | `http://agnos:8088` | hoosh endpoint (override to `http://localhost:8088` on AGNOS host) |
| `AGNOS_LLM_GATEWAY_MODEL` | `default` | Model alias in hoosh |
| `AGNOS_LLM_GATEWAY_API_KEY` | (empty) | API key for hoosh (if required) |
| `AGNOS_AGENT_REGISTRATION_ENABLED` | `true` | Register agents with daimon |
| `AGNOS_AGENT_REGISTRY_URL` | `http://agnos:8090` | daimon endpoint (override to `http://localhost:8090` on AGNOS host) |
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
| `AGNOS_IMAGE` | `agnos:latest` | AGNOS container image (dev profile only) |
| `HOOSH_PORT` | `8088` | Host port for hoosh (dev profile only) |
| `DAIMON_PORT` | `8090` | Host port for daimon (dev profile only) |
| `AGNOS_AGENT_API_KEY` | (empty) | API key for daimon registration |
| `AGNOS_TOKEN_BUDGET_POOL` | `agnostic-qa` | Token budget pool name |

## Health Checks

```bash
# All services
docker compose -f docker-compose.agnos.yml --profile dev ps

# Individual service health
curl http://localhost:8000/health      # webgui
curl http://localhost:8088/v1/health   # hoosh
curl http://localhost:8090/v1/health   # daimon

# Verify agent registration
curl http://localhost:8000/api/v1/agents/status
```

## Networking

All services communicate on the `qa-network` Docker bridge. Service names resolve via Docker DNS. In production on AGNOS, override `AGNOS_*_URL` env vars to point at `http://localhost:PORT`.

| Service | Internal Port | External Port |
|---------|---------------|---------------|
| webgui | 8000 | 8000 |
| agnos (dev) | 8088, 8090 | 8088, 8090 |
| redis (dev) | 6379 | 6379 |
| postgres (dev) | 5432 | 5433 |

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

**webgui can't reach hoosh/daimon**: In production, override URLs to localhost: `AGNOS_LLM_GATEWAY_URL=http://localhost:8088`. In dev, ensure `--profile dev` is set.

**LLM calls return fallbacks**: Verify hoosh has valid provider keys. Check logs: `docker logs agnostic-agnos-1`.

**Agent registration fails**: Check daimon logs. Registration failure is non-fatal — Agnostic continues to work without it.

**Path prefix mismatch**: If using a custom AGNOS build with different API paths, set `AGNOS_PATH_PREFIX` accordingly (default `/v1`).

## E2E Testing

```bash
# Start dev stack
docker compose -f docker-compose.agnos.yml --profile dev up -d

# Run E2E gateway tests
pytest tests/e2e/test_agnos_gateway.py -v

# Override URLs if needed
HOOSH_URL=http://localhost:8088 DAIMON_URL=http://localhost:8090 \
  pytest tests/e2e/test_agnos_gateway.py -v
```
