# Docker Compose Deployment Guide

## Overview

Agnostic runs on [AGNOS](https://github.com/MacCracken/agnosticos). The primary `docker-compose.yml` starts a single `agnostic` container that connects to AGNOS system services (hoosh, daimon, Redis, PostgreSQL) on localhost.

For development without an AGNOS host, use `--profile dev` to add Redis and PostgreSQL as containers. For fully standalone deployment (no AGNOS), use `docker-compose.old-style.yml`.

## Prerequisites

- Docker 20.10+ and Docker Compose
- 4 GB+ RAM
- OpenAI API key (or other LLM provider)

## Quick Start

```bash
# Clone and configure
git clone https://github.com/MacCracken/agnostic && cd agnostic
cp .env.example .env
# Edit .env — set OPENAI_API_KEY

# Build the image
./scripts/build-docker.sh

# Production (on AGNOS host)
docker compose up -d

# Development (adds redis + postgres containers)
docker compose --profile dev up -d
```

**Access:** http://localhost:8000

## Deployment Modes

| Mode | Command | Infrastructure |
|------|---------|---------------|
| Production (AGNOS) | `docker compose up -d` | AGNOS system services on host |
| Development | `docker compose --profile dev up -d` | Redis + PostgreSQL as containers |
| Standalone | `docker compose -f docker-compose.old-style.yml up -d` | All infra + webgui bundled |
| Standalone + workers | `docker compose -f docker-compose.old-style.yml --profile workers up -d` | Full distributed stack |

## Health Checks

```bash
# Agnostic service
curl http://localhost:8000/health

# Container status
docker compose ps
```

## Logs

```bash
# Follow agnostic logs
docker compose logs -f agnostic

# Last 100 lines
docker compose logs --tail=100 agnostic
```

## Environment Variables

See `.env.example` for the full list. Key variables:

```bash
OPENAI_API_KEY=sk-...
REDIS_URL=redis://localhost:6379/0      # AGNOS system Redis
DATABASE_URL=postgresql+asyncpg://...   # AGNOS system PostgreSQL
AGNOSTIC_API_KEY=                       # Static API key for M2M auth
```

AGNOS integration variables (`AGNOS_LLM_GATEWAY_URL`, `AGNOS_AGENT_REGISTRY_URL`, etc.) default to localhost and are documented in the [AGNOS Deployment Guide](agnos.md).

## Standalone Mode (docker-compose.old-style.yml)

For running without AGNOS, the standalone compose bundles Redis, PostgreSQL, and optionally RabbitMQ + 6 agent workers:

```bash
./scripts/build-docker.sh
docker compose -f docker-compose.old-style.yml up -d

# With distributed workers
docker compose -f docker-compose.old-style.yml --profile workers up -d
```

## Troubleshooting

```bash
# Check logs
docker compose logs agnostic

# Check resources
docker system df

# Clean rebuild
docker compose down -v
./scripts/build-docker.sh
docker compose up -d
```

## Additional Resources

- [AGNOS Deployment Guide](agnos.md) — AGNOS-specific configuration
- [Quick Start](../getting-started/quick-start.md) — Get running in 5 minutes
- [Kubernetes Deployment](kubernetes.md) — K8s with Helm
- [Development Setup](../development/setup.md) — Local development

---

*Last Updated: 2026-03-08*
