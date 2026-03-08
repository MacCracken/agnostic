# AGNOS Deployment Guide

Deploy Agnostic QA Platform on AGNOS — or simulate the AGNOS environment in dev containers.

## Understanding AGNOS

AGNOS is an operating system. In production, **hoosh** (LLM Gateway), **daimon** (Agent Runtime), **Redis**, and **PostgreSQL** are all system services running on the host — not containers. Only the `webgui` container is needed.

For development without an AGNOS host, use `--profile dev` to spin up these services as containers.

## Quick Start

```bash
# 1. Build the image
./scripts/build-docker.sh

# 2. Configure
cp .env.example .env
# Edit .env — set provider API keys, etc.

# 3. Production (on AGNOS host)
docker compose up -d
```

On AGNOS, hoosh, daimon, Redis, and PostgreSQL are system services. The `docker-compose.yml` starts the agnostic container which connects to them on localhost.

For development without an AGNOS host, use `--profile dev` to spin up redis and postgres as containers:

```bash
docker compose --profile dev up -d
```

For standalone deployment (no AGNOS at all), use `docker-compose.old-style.yml` which bundles all infrastructure including rabbitmq and workers.

## Architecture

```
On AGNOS host:
┌──────────────┐
│  agnostic    │──▶ hoosh (system service :8088) ──▶ LLM providers
│  :8000       │──▶ daimon (system service :8090)
│  agents      │──▶ Redis (system service :6379)
│  (in-proc)   │──▶ Postgres (system service :5432)
└──────────────┘
```

- **hoosh** (port 8088): LLM Gateway. Holds all provider API keys. Exposes OpenAI-compatible `/v1/chat/completions`. Agnostic routes all LLM calls through it via litellm.
- **daimon** (port 8090): Agent Runtime. Receives agent registration, heartbeats, audit events, reasoning traces, and dashboard data.

## Environment Variables

### Required

| Variable | Description |
|----------|-------------|
| `POSTGRES_PASSWORD` | PostgreSQL password |
| `OPENAI_API_KEY` | LLM provider key — consumed by **hoosh** (not Agnostic) |

### AGNOS Integration (set automatically by `docker-compose.yml`)

| Variable | Default | Description |
|----------|---------|-------------|
| `AGNOS_LLM_GATEWAY_ENABLED` | `true` | Route LLM calls through hoosh |
| `AGNOS_LLM_GATEWAY_URL` | `http://localhost:8088` | hoosh endpoint |
| `AGNOS_LLM_GATEWAY_MODEL` | `default` | Model alias in hoosh |
| `AGNOS_LLM_GATEWAY_API_KEY` | (empty) | API key for hoosh (if required) |
| `AGNOS_AGENT_REGISTRATION_ENABLED` | `true` | Register agents with daimon |
| `AGNOS_AGENT_REGISTRY_URL` | `http://localhost:8090` | daimon endpoint |
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
| `AGNOS_AGENT_API_KEY` | (empty) | API key for daimon registration |
| `AGNOS_TOKEN_BUDGET_POOL` | `agnostic-qa` | Token budget pool name |

## Health Checks

```bash
# Agnostic
curl http://localhost:8000/health

# AGNOS system services
curl http://localhost:8088/v1/health   # hoosh
curl http://localhost:8090/v1/health   # daimon

# Verify agent registration
curl http://localhost:8000/api/v1/agents/status
```

## Troubleshooting

**Can't reach hoosh/daimon**: Verify AGNOS system services are running. Check `AGNOS_LLM_GATEWAY_URL` and `AGNOS_AGENT_REGISTRY_URL` env vars (default `http://localhost:8088` and `http://localhost:8090`).

**LLM calls return fallbacks**: Verify hoosh has valid provider keys.

**Agent registration fails**: Check daimon logs. Registration failure is non-fatal — Agnostic continues to work without it.

**Path prefix mismatch**: If using a custom AGNOS build with different API paths, set `AGNOS_PATH_PREFIX` accordingly (default `/v1`).

## E2E Testing

```bash
# Start agnostic
docker compose up -d

# Run E2E gateway tests
pytest tests/e2e/test_agnos_gateway.py -v
```
