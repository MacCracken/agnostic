# Quick Start Guide

## Overview

Get the Agentic QA Team System running in 5 minutes with this step-by-step guide.

## Prerequisites

- **Docker** 20.10+ and Docker Compose
- **4GB+ RAM** for parallel agent execution
- **OpenAI API Key** for LLM capabilities
- **Git** (optional, for cloning)

## 🚀 Quick Start (Docker)

### 1. Clone and Setup

```bash
# Clone repository
git clone <repository-url>
cd agnostic

# Copy environment template
cp .env.example .env
```

### 2. Configure Environment

Edit `.env` and set your API key:

```bash
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4o
PRIMARY_MODEL_PROVIDER=openai
```

### 3. Launch Services

```bash
# Build the image
./scripts/build-docker.sh

# Start (on AGNOS host — webgui only)
docker compose up -d

# Or start with dev infrastructure
docker compose --profile dev up -d
```

**Access URLs:**
- **WebGUI**: http://localhost:8000

### 4. Verify Installation

```bash
# Check all containers are running
docker-compose ps

# View WebGUI logs
docker-compose logs -f webgui

# Access WebGUI
open http://localhost:8000
```

## 🏗️ Architecture

The system uses a 6-agent architecture. For full details, see the [Development Setup Guide](../development/setup.md#architecture).

## 📋 First Test Task

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

Results are displayed in the WebGUI with comprehensive reports.

## 🛠️ Development Setup

For full local development setup (without Docker), environment variables, and advanced configuration, see the [Development Setup Guide](../development/setup.md).

## 🧪 Running Tests

```bash
# All tests with mocks
python run_tests.py --mode all --env mock

# Unit tests only
python run_tests.py --mode unit

# Integration tests (requires Docker)
python run_tests.py --mode integration --env docker

# With coverage report
python run_tests.py --mode coverage
```

## 📊 Monitoring

### Check Agent Status

```bash
# Docker - all agents
docker-compose ps

# Docker - specific agent logs
docker-compose logs qa-manager
docker-compose logs senior-qa
docker-compose logs junior-qa

# Kubernetes
kubectl get pods -n agentic-qa
```

### View System Health

```bash
# WebGUI API
curl http://localhost:8000/api/agents/status

# Redis
docker-compose logs redis

# RabbitMQ Management Console
open http://localhost:15672  # guest/guest
```

## 🔧 Common Tasks

### Restart a Single Agent

```bash
# Restart specific agent
docker-compose restart qa-manager

# Or rebuild and restart
docker-compose up --build -d qa-manager
```

### Add Custom Test Data

```bash
# Option 1: Place files in shared/data directory
mkdir -p shared/data
cp my_test_data.csv shared/data/

# Option 2: Upload via WebGUI
# Navigate to http://localhost:8000 → Upload Data
```

### Configure New LLM Provider

Edit `config/models.json`:

```json
{
  "providers": {
    "anthropic": {
      "api_base": "https://api.anthropic.com",
      "models": ["claude-3-opus-20240229"],
      "auth": {"api_key": "${ANTHROPIC_API_KEY}"}
    }
  }
}
```

## 🚨 Troubleshooting

### Port Conflicts

```bash
# Check what's using required ports
netstat -tulpn | grep -E ':8000|:6379|:5672'

# Change ports in .env if needed
WEBGUI_PORT=8001
REDIS_PORT=6380
RABBITMQ_PORT=5673
```

### Agent Not Responding

```bash
# Check agent logs
docker-compose logs qa-manager

# Verify RabbitMQ connection
docker-compose logs rabbitmq

# Restart the agent
docker-compose restart qa-manager

# Check if RabbitMQ is healthy
curl http://localhost:15672/api/overview -u guest:guest
```

### LLM Errors

```bash
# Verify API key is set
echo $OPENAI_API_KEY

# Test LLM connection
python -c "from openai import OpenAI; OpenAI().models.list()"

# Check agent logs for errors
docker-compose logs webgui | grep -i error
```

### Redis Connection Issues

```bash
# Check Redis is running
docker-compose ps redis

# Test Redis connection
docker-compose exec redis redis-cli ping

# View Redis logs
docker-compose logs redis
```

### Build Issues

```bash
# Clean and rebuild
docker compose down -v
docker system prune -a
./scripts/build-docker.sh
```

## 📚 Next Steps

1. **Read the full documentation**:
   - [Development Setup](../development/setup.md) - Development guidelines
   - [Agent Specifications](../agents/index.md) - Agent architecture details
   - [Docker Deployment](../deployment/docker-compose.md) - Production deployment
   - [Kubernetes Deployment](../deployment/kubernetes.md) - K8s deployment

2. **Review API documentation**:
   - [Agent APIs](../../docs/api/agents.md)
   - [WebGUI APIs](../../docs/api/webgui.md)
   - [LLM Integration](../../docs/api/llm_integration.md)

3. **Explore advanced features**:
   - Self-healing UI selectors
   - Fuzzy verification
   - Risk-based test prioritization
   - Security compliance testing
   - Performance profiling

## 🎯 Success Metrics

Your system is working correctly when:

- ✅ All 6 agents show "active" status: `docker-compose ps`
- ✅ WebGUI loads at http://localhost:8000
- ✅ Test tasks complete with reports
- ✅ Redis/RabbitMQ show healthy connections
- ✅ LLM calls return structured responses
- ✅ No error messages in agent logs

## 📖 Additional Resources

- [Architecture Decision Records (ADRs)](../../docs/adr/) - System design decisions
- [Docker Build Optimization](../../docker/README.md) - Build system details
- [Contributing Guidelines](../development/contributing.md) - How to contribute

Welcome to the Agentic QA Team System!
