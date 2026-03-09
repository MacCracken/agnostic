# Quick Start Guide

## Overview

Get the Agentic QA Team System running in 5 minutes. The production image bundles Redis, PostgreSQL, and optionally Caddy TLS — no external infrastructure needed.

## Prerequisites

- **Docker** 20.10+ and Docker Compose v2
- **4GB+ RAM** for parallel agent execution
- **LLM access**: OpenAI API key, or AGNOS LLM Gateway

## Quick Start

### 1. Clone and Setup

```bash
git clone https://github.com/MacCracken/agnostic
cd agnostic
cp .env.example .env
```

### 2. Configure Environment

Edit `.env` and set your LLM provider:

```bash
# Option A: Direct API key
OPENAI_API_KEY=your_openai_api_key_here

# Option B: AGNOS LLM Gateway (no API keys needed in Agnostic)
AGNOS_LLM_GATEWAY_ENABLED=true
AGNOS_LLM_GATEWAY_URL=http://localhost:8088
```

### 3. Build and Launch

```bash
# Build the image
docker build -t agnostic:latest .

# Production (embedded Redis + PostgreSQL)
docker compose up -d

# Or development (separate Redis + PostgreSQL containers)
docker compose --profile dev up -d
```

**Access:** http://localhost:8000

### 4. Verify Installation

```bash
# Check container status
docker compose ps

# Health check
curl http://localhost:8000/health

# View logs
docker compose logs -f agnostic
```

## Architecture

The system uses a 6-agent architecture with embedded Redis and PostgreSQL managed by supervisord. For full details, see the [Development Setup Guide](../development/setup.md#architecture).

## First Test Task

### Submit via WebGUI

1. Navigate to http://localhost:8000
2. Enter your test requirements, for example:
   ```
   Test the user login flow with valid and invalid credentials,
   check for SQL injection vulnerabilities, and measure login response times
   ```
3. Click **"Submit Task"**
4. Watch the agents collaborate in real-time

### Expected Output

- **QA Manager** decomposes the requirement into test scenarios
- **Senior QA Engineer** designs complex test cases
- **Junior QA Worker** executes regression and UI tests
- **QA Analyst** performs security scans and generates reports
- **Security & Compliance Agent** validates OWASP compliance
- **Performance & Resilience Agent** profiles response times

## Running Tests

```bash
# Unit tests
.venv/bin/python -m pytest tests/unit/ -q

# E2E tests (requires running containers)
.venv/bin/python -m pytest tests/e2e/ -q

# With coverage
.venv/bin/python -m pytest tests/unit/ --cov=agents --cov=webgui --cov=config
```

## Monitoring

```bash
# Health check
curl http://localhost:8000/health

# Agent status
curl http://localhost:8000/api/agents

# Container logs
docker compose logs -f agnostic

# Supervisord process status
docker exec agnostic supervisorctl status
```

## TLS (Standalone HTTPS)

```bash
# With provided certs (place in ./certs/)
TLS_ENABLED=true TLS_CERT_PATH=/app/certs/cert.pem TLS_KEY_PATH=/app/certs/key.pem \
  docker compose up -d

# With auto-HTTPS (public domain)
TLS_ENABLED=true TLS_DOMAIN=qa.example.com docker compose up -d
```

## Troubleshooting

### Port Conflicts

```bash
# Check what's using port 8000
ss -tlnp | grep 8000

# Change port in docker-compose.yml or .env
WEBGUI_PORT=8001
```

### LLM Errors

```bash
# Verify API key is set
echo $OPENAI_API_KEY

# Or check AGNOS LLM Gateway
curl http://localhost:8088/v1/health

# Check logs for errors
docker compose logs agnostic | grep -i error
```

### Clean Rebuild

```bash
docker compose down -v
docker build --no-cache -t agnostic:latest .
docker compose up -d
```

## Next Steps

- [Docker Deployment Guide](../deployment/docker-compose.md) — Production, TLS, HA, dev modes
- [AGNOS Deployment](../deployment/agnos.md) — AGNOS-specific setup
- [Development Setup](../development/setup.md) — Local development without Docker
- [Agent Documentation](../agents/index.md) — Agent architecture details
- [API Documentation](../api/webgui.md) — REST API reference
- [Contributing](../development/contributing.md) — How to contribute

---

*Last Updated: 2026-03-09*
