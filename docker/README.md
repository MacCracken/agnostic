# Docker Build Optimization

This directory contains optimized Docker build configurations for the Agentic QA Team System.

## Overview

The build system uses a **base image** pattern to significantly speed up agent container builds:

- **Base Image** (`agnostic-qa-base`): Contains all common dependencies (Python, CrewAI, LangChain, Redis, RabbitMQ, Playwright, OpenCV, etc.)
- **Agent Images**: Lightweight images that extend the base with only agent-specific code

## Benefits

- **~90% faster builds** after the first base image build
- **~70% smaller incremental builds** (only code changes, not dependencies)
- **Consistent environment** across all agents
- **Shared layer caching** between all agent containers

## Quick Start

### Build Everything (Base + All Agents)

```bash
./scripts/build-docker.sh
```

### Build Only the Base Image

```bash
./scripts/build-docker.sh --base-only
# or
./scripts/build-docker.sh -b
```

### Build Only Agent Images (requires base image)

```bash
./scripts/build-docker.sh --agents-only
# or
./scripts/build-docker.sh -a
```

### Clean Up Dangling Images

```bash
./scripts/build-docker.sh --cleanup
# or
./scripts/build-docker.sh -c
```

## Manual Build Commands

### Build Base Image

```bash
# Using docker-compose
docker compose -f docker-compose.build.yml build base

# Or using docker build directly
docker build -t agnostic-qa-base:latest -t agnostic-qa-base:2026.3.6 -f docker/Dockerfile.base .
```

### Build Agent Images

```bash
docker compose build qa-manager senior-qa junior-qa qa-analyst security-compliance-agent performance-agent webgui
```

## Docker Compose Usage

### Start All Services

```bash
docker compose up -d
```

### Start Only Infrastructure (Redis + RabbitMQ)

```bash
docker compose up -d redis rabbitmq
```

### Start Specific Agents

```bash
docker compose up -d qa-manager senior-qa
```

## Build Performance

| Build Type | First Build | Incremental |
|------------|-------------|-------------|
| Base Image | ~10-15 min | N/A |
| Manager Agent | ~30 sec | ~5 sec |
| Senior Agent | ~30 sec | ~5 sec |
| Junior Agent | ~30 sec | ~5 sec |
| Analyst Agent | ~30 sec | ~5 sec |
| Security Agent | ~30 sec | ~5 sec |
| Performance Agent | ~30 sec | ~5 sec |
| WebGUI | ~30 sec | ~5 sec |

## Troubleshooting

### Base image not found

If you get "pull access denied" errors, the base image hasn't been built locally:

```bash
./scripts/build-docker.sh --base-only
```

### Rebuild base image after requirements.txt changes

```bash
./scripts/build-docker.sh --base-only
./scripts/build-docker.sh --agents-only
```

### Clean build (no cache)

```bash
docker compose build --no-cache qa-manager
```

## Files

- `docker/Dockerfile.base` - Base image definition
- `docker-compose.build.yml` - Docker Compose for building base image
- `scripts/build-docker.sh` - Convenience build script
- `agents/*/Dockerfile` - Agent-specific Dockerfiles (all use base image)

## Architecture

```
┌─────────────────────────────────────────────────┐
│           agnostic-qa-base:latest               │
│  ┌───────────────────────────────────────────┐  │
│  │  Python 3.11 + All Dependencies          │  │
│  │  • CrewAI + CrewAI Tools                  │  │
│  │  • LangChain + LangChain OpenAI          │  │
│  │  • Redis + Celery                        │  │
│  │  • Chainlit + FastAPI + Uvicorn          │  │
│  │  • Playwright + Chromium                 │  │
│  │  • OpenCV + scikit-learn + pandas        │  │
│  │  • pytest + pytest-playwright            │  │
│  │  • All other requirements...             │  │
│  └───────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
           │
    ┌──────┴──────┐
    │             │
    ▼             ▼
┌─────────┐  ┌─────────┐  ┌─────────┐
│ Manager │  │ Senior  │  │ Junior  │
│  Agent  │  │  Agent  │  │  Agent  │
└─────────┘  └─────────┘  └─────────┘
    │             │             │
    ▼             ▼             ▼
┌─────────┐  ┌─────────┐  ┌─────────┐
│ Analyst │  │Security │  │Perform. │
│  Agent  │  │  Agent  │  │  Agent  │
└─────────┘  └─────────┘  └─────────┘
                  │
                  ▼
            ┌─────────┐
            │ WebGUI  │
            └─────────┘
```
