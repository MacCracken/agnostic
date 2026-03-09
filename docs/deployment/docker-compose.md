# Docker Compose Deployment Guide

## Overview

The Agnostic production image bundles everything needed to run: Redis, PostgreSQL 17, and optionally Caddy for TLS termination — all managed by supervisord. No external infrastructure is required for a basic deployment.

For high-availability, external Redis and PostgreSQL can be used by setting `REDIS_URL` and `DATABASE_URL`. For development, `--profile dev` starts Redis and PostgreSQL as separate containers.

## Prerequisites

- Docker 20.10+ and Docker Compose v2
- 4 GB+ RAM
- LLM provider API key (or AGNOS LLM Gateway)

## Quick Start

```bash
git clone https://github.com/MacCracken/agnostic && cd agnostic
cp .env.example .env
# Edit .env — set OPENAI_API_KEY (or AGNOS_LLM_GATEWAY_ENABLED=true)

docker build -t agnostic:latest .
docker compose up -d
```

**Access:** http://localhost:8000

## Deployment Modes

| Mode | Command | What Runs |
|------|---------|-----------|
| Production | `docker compose up -d` | Single container: app + embedded Redis + PostgreSQL |
| Production + TLS | `TLS_ENABLED=true ... docker compose up -d` | Above + Caddy on :443/:80 |
| External HA | `REDIS_URL=... DATABASE_URL=... docker compose up -d` | App only (embedded services skipped) |
| Development | `docker compose --profile dev up -d` | App + separate Redis + PostgreSQL containers |

## Embedded Services

The production container runs four processes via supervisord:

| Process | Port | Skipped When |
|---------|------|--------------|
| **Redis** | 127.0.0.1:6379 | `REDIS_URL` points to external host |
| **PostgreSQL 17** | 127.0.0.1:5432 | `DATABASE_URL` points to external host |
| **Caddy** (TLS) | 0.0.0.0:443/80 | `TLS_ENABLED` is not `true` |
| **Chainlit app** | 0.0.0.0:8000 | Never (always runs) |

Data is persisted in the `agnostic_data` Docker volume at `/data` (Redis snapshots + PostgreSQL data directory + Caddy certs).

## TLS Configuration

### Provided Certificates

Mount certs and set environment variables:

```bash
TLS_ENABLED=true \
TLS_CERT_PATH=/app/certs/cert.pem \
TLS_KEY_PATH=/app/certs/key.pem \
  docker compose up -d
```

The `./certs:/app/certs:ro` volume is pre-configured in `docker-compose.yml`. Place your cert and key in `./certs/`.

### Auto-HTTPS (ACME / Let's Encrypt)

For public-facing deployments with a domain:

```bash
TLS_ENABLED=true \
TLS_DOMAIN=qa.example.com \
  docker compose up -d
```

Caddy automatically obtains and renews certificates. Ensure ports 80 and 443 are reachable.

### No TLS (Default)

When `TLS_ENABLED` is unset or `false`, Caddy does not start. The app serves plain HTTP on port 8000. This is the correct mode when running behind SecureYeoman or another reverse proxy.

## External HA Services

To skip embedded Redis and/or PostgreSQL, point the URLs to external hosts:

```bash
# External Redis cluster
REDIS_URL=redis://my-redis:6379/0

# External PostgreSQL
DATABASE_URL=postgresql+asyncpg://user:pass@my-pg:5432/agnostic

docker compose up -d
```

The entrypoint detects non-localhost hostnames and skips the corresponding embedded service.

## Environment Variables

### Core

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | `redis://127.0.0.1:6379/0` | Redis connection (embedded if localhost) |
| `DATABASE_URL` | (built from POSTGRES_*) | PostgreSQL connection (embedded if localhost) |
| `DATABASE_ENABLED` | `true` | Enable PostgreSQL persistence |
| `AGNOSTIC_API_KEY` | (empty) | Static API key for M2M auth |

### TLS

| Variable | Default | Description |
|----------|---------|-------------|
| `TLS_ENABLED` | `false` | Enable Caddy TLS reverse proxy |
| `TLS_CERT_PATH` | (empty) | Path to PEM certificate |
| `TLS_KEY_PATH` | (empty) | Path to PEM private key |
| `TLS_DOMAIN` | (empty) | Domain for auto-HTTPS (ACME) |

### AGNOS Integration

| Variable | Default | Description |
|----------|---------|-------------|
| `AGNOS_LLM_GATEWAY_ENABLED` | `true` | Route LLM calls through hoosh |
| `AGNOS_LLM_GATEWAY_URL` | `http://localhost:8088` | hoosh endpoint |
| `AGNOS_LLM_GATEWAY_API_KEY` | (empty) | Gateway auth token |
| `AGNOS_AGENT_REGISTRATION_ENABLED` | `true` | Register with daimon |

See `.env.example` for the full list.

## Health Checks

```bash
curl http://localhost:8000/health

# Expected: {"redis": "ok", "status": "degraded", ...}
# "degraded" is normal — agents are offline until tasks are submitted
```

## Logs

```bash
docker compose logs -f agnostic
docker compose logs --tail=100 agnostic
```

## Data Persistence

The `agnostic_data` volume stores:
- `/data/redis/` — Redis RDB snapshots
- `/data/postgres/` — PostgreSQL data directory
- `/data/caddy/` — ACME certificates (auto-HTTPS mode)

To back up, bind-mount `/data` to a host directory:

```yaml
volumes:
  - ./agnostic-data:/data
```

## Troubleshooting

```bash
# Check all processes inside the container
docker exec agnostic supervisorctl status

# Check Redis
docker exec agnostic redis-cli ping

# Check PostgreSQL
docker exec agnostic su - postgres -c "pg_isready"

# Clean rebuild
docker compose down -v
docker build -t agnostic:latest .
docker compose up -d
```

## Additional Resources

- [AGNOS Deployment Guide](agnos.md) — AGNOS-specific configuration
- [Quick Start](../getting-started/quick-start.md) — Get running in 5 minutes
- [Kubernetes Deployment](kubernetes.md) — K8s with Helm
- [Development Setup](../development/setup.md) — Local development

---

*Last Updated: 2026-03-09*
