# Deployment Guide - Optimized 6-Agent QA System

## 🚀 Quick Start

### Prerequisites
- **Docker** 20.10+ and Docker Compose
- **4GB+ RAM** for parallel agent execution
- **OpenAI API Key** for LLM capabilities
- **Git** for code management

### 1. Environment Setup

```bash
# Clone Repository
git clone <repository-url>
cd agnostic

# Copy Environment Template
cp .env.example .env

# Configure Required Variables
nano .env
```

```env
# Core Configuration
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4o
REDIS_URL=redis://redis:6379/0
RABBITMQ_URL=amqp://guest:guest@rabbitmq:5672/

# Feature Flags
ENABLE_SELF_HEALING=true
ENABLE_FUZZY_VERIFICATION=true
ENABLE_RISK_BASED_PRIORITIZATION=true

# Optional Performance Settings
MAX_CONCURRENT_AGENTS=6
AGENT_TIMEOUT=1800
CACHE_TTL=3600
```

### 2. System Deployment

#### Build and Deploy

```bash
# Build the single image
./scripts/build-docker.sh

# Production (on AGNOS host — webgui only)
docker compose up -d

# Development (simulate AGNOS with containers)
docker compose --profile dev up -d

# Development + distributed workers
docker compose --profile dev --profile workers up -d

# Verify deployment
docker compose ps
```

#### Development Environment
```bash
# Start Development Services
docker-compose -f docker-compose.dev.yml up -d

# View Logs
docker-compose logs -f

# Stop Services
docker-compose -f docker-compose.dev.yml down
```

#### Production Environment (Traditional Build)
```bash
# Start Core Infrastructure
docker-compose up -d redis rabbitmq

# Wait for Services (Optional)
sleep 10

# Build and start 6-Agent System (slower without base image)
docker-compose up --build -d

# Verify All Services
docker-compose ps
```

### 3. Health Checks

#### Verify Core Services
```bash
# Redis Connection
docker-compose exec redis redis-cli ping

# RabbitMQ Management
curl http://localhost:15672/api/health

# WebGUI Access
curl http://localhost:8000/health
```

#### Verify Agent Services
```bash
# Check container health status
docker-compose ps

# Inspect a specific container health
docker inspect --format='{{.State.Health.Status}}' <container-name>
```

## 🏗️ Service Architecture

### Container Network
```yaml
networks:
  qa-network:
    driver: bridge
    ipam:
      config:
        - subnet: 172.20.0.0/16
```

### Service Dependencies
```yaml
services:
  # Core Infrastructure
  redis:
    depends_on: []
    networks: [qa-network]
    
  rabbitmq:
    depends_on: []
    networks: [qa-network]
    
  # 6-Agent System
  performance-agent:
    depends_on: [redis, rabbitmq]
    networks: [qa-network]
    
  security-compliance-agent:
    depends_on: [redis, rabbitmq]
    networks: [qa-network]
    
  senior-qa:
    depends_on: [redis, rabbitmq]
    networks: [qa-network]
    
  junior-qa:
    depends_on: [redis, rabbitmq]
    networks: [qa-network]
    
  qa-analyst:
    depends_on: [redis, rabbitmq]
    networks: [qa-network]
    
  # Orchestration
  qa-manager:
    depends_on: [redis, rabbitmq, performance-agent, security-compliance-agent, senior-qa, junior-qa, qa-analyst]
    networks: [qa-network]
    
  # Interface
  webgui:
    depends_on: [redis, rabbitmq, qa-manager]
    networks: [qa-network]
```

## 📊 Monitoring & Observability

### Log Management
```bash
# View All Logs
docker-compose logs

# View Specific Service Logs
docker-compose logs performance-agent
docker-compose logs qa-manager

# Follow Logs in Real-time
docker-compose logs -f qa-manager

# Export Logs
docker-compose logs --tail=1000 qa-manager > qa-manager.log
```

### Health Monitoring
```bash
# Check Container Status
docker-compose ps

# Health Check All Services
docker-compose ps

# Resource Usage
docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}"
```

### Performance Monitoring
```bash
# Agent Resource Usage
docker stats --format "table {{.Container}}\t{{.MemUsage}}\t{{.CPUPerc}}" $(docker-compose ps -q)
```

## 🔧 Configuration Management

### Environment-Specific Configurations

#### Development (.env.dev)
```env
# Development Optimizations
DEBUG=true
LOG_LEVEL=DEBUG
OPENAI_MODEL=gpt-4o-mini  # Faster, cheaper for development

# Resource Limits
MAX_CONCURRENT_AGENTS=3  # Reduce for development
AGENT_TIMEOUT=300      # Shorter timeouts

# Security Relaxation (Development Only!)
DISABLE_AUTH=true
ALLOW_CORS=true
```

#### Production (.env.prod)
```env
# Production Hardening
DEBUG=false
LOG_LEVEL=INFO
OPENAI_MODEL=gpt-4o

# Resource Optimization
MAX_CONCURRENT_AGENTS=6
AGENT_TIMEOUT=1800
CACHE_TTL=7200

# Security Hardening
ENABLE_RATE_LIMITING=true
ENABLE_AUDIT_LOGGING=true
REQUIRE_AUTHENTICATION=true
```

#### Testing (.env.test)
```env
# Testing Configuration
DEBUG=false
LOG_LEVEL=INFO
OPENAI_MODEL=gpt-3.5-turbo

# Test Optimization
MAX_CONCURRENT_AGENTS=4
AGENT_TIMEOUT=600
CACHE_TTL=1800

# Test Data
USE_TEST_DATA=true
MOCK_EXTERNAL_APIS=true
```

## 🔒 Security Configuration

### Production Security
```yaml
# docker-compose.prod.yml
version: '3.8'

services:
  redis:
    image: redis:7-alpine
    restart: unless-stopped
    command: redis-server --requirepass ${REDIS_PASSWORD}
    environment:
      - REDIS_PASSWORD
    
  rabbitmq:
    image: rabbitmq:3-management-alpine
    restart: unless-stopped
    environment:
      - RABBITMQ_DEFAULT_USER=${RABBITMQ_USER}
      - RABBITMQ_DEFAULT_PASS=${RABBITMQ_PASSWORD}
    
  # Agent Services with Security
  performance-agent:
    image: agentic/performance-agent:latest
    restart: unless-stopped
    environment:
      - ENABLE_RATE_LIMITING=true
    cap_drop:
      - ALL
    cap_add:
      - CHOWN
      - SETGID
      - SETUID

  webgui:
    image: agentic/webgui:latest
    restart: unless-stopped
    environment:
      - ENABLE_AUTHENTICATION=true
      - OAUTH2_CLIENT_ID=${OAUTH2_CLIENT_ID}
      - OAUTH2_CLIENT_SECRET=${OAUTH2_CLIENT_SECRET}
```

### TLS/SSL Configuration
```yaml
# Enable HTTPS for all external communications
services:
  webgui:
    ports:
      - "443:8443"
    volumes:
      - ./ssl:/etc/ssl/certs:ro
    environment:
      - SSL_CERT_PATH=/etc/ssl/certs/cert.pem
      - SSL_KEY_PATH=/etc/ssl/certs/key.pem
      
  nginx-proxy:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ./ssl:/etc/ssl/certs:ro
```

## 📈 Scaling Strategies

### Horizontal Scaling
```bash
# Scale Individual Agents
docker-compose up -d --scale performance-agent=3
docker-compose up -d --scale senior-qa=2

# Load Balancer Configuration
# Use nginx or traefik for load balancing across multiple agent instances
```

### Resource Limits
```yaml
services:
  performance-agent:
    deploy:
      resources:
        limits:
          cpus: '1.0'
          memory: 1G
        reservations:
          cpus: '0.5'
          memory: 512M
    restart_policy:
      condition: on-failure
      delay: 5s
      max_attempts: 3
```

## 🔄 Update & Maintenance

### Zero-Downtime Updates
```bash
# Rolling Update Strategy
docker-compose pull
docker-compose up -d --no-deps --scale performance-agent=2

# Health Check After Update
docker-compose ps performance-agent
docker-compose up -d --scale performance-agent=3

# Update Remaining Services
# Repeat for each service
```

### Backup Strategy
```bash
# Backup Configuration
./scripts/backup-config.sh

# Backup Data
docker-compose exec redis redis-cli BGSAVE
docker-compose exec rabbitmq rabbitmqctl export_definitions

# Create System Backup
docker run --rm -v $(pwd):/backup:/backup alpine tar -czf /backup/system-backup-$(date +%Y%m%d).tar.gz .
```

## 🚨 Troubleshooting

### Common Issues

#### Container Won't Start
```bash
# Check Logs
docker-compose logs <service-name>

# Check Configuration
docker-compose config <service-name>

# Check Resources
docker system df
docker system prune

# Rebuild and Restart
docker-compose down
docker-compose up --build <service-name>
```

#### Agent Communication Issues
```bash
# Check Network
docker network ls
docker network inspect agentic_qa-network

# Test Redis Connection
docker-compose exec performance-agent ping redis

# Test RabbitMQ Connection
docker-compose exec performance-agent curl http://rabbitmq:15672/api/health
```

#### Performance Issues
```bash
# Monitor Resource Usage
docker stats

# Check Agent Health
docker-compose ps

# Optimize Configuration
# Reduce concurrent agents, increase timeouts, enable caching
```

## 📊 Performance Optimization

### Environment-Specific Optimizations

#### Development
- Use faster LLM models (gpt-4o-mini)
- Reduce parallel execution
- Enable debug logging
- Use test data where possible

#### Staging
- Use production-like models (gpt-4o)
- Full parallel execution
- Enable comprehensive logging
- Use realistic data

#### Production
- Optimize LLM usage with caching
- Full parallel execution with load balancing
- Comprehensive monitoring and alerting
- Resource optimization and limits

## 🔮 Advanced Configuration

### Custom Agent Configuration
```python
# Customize agent behavior in agent-specific config files
# Example: agents/performance/config.py
PERFORMANCE_PROFILES = {
    "quick": {"concurrent": 5, "requests": 10},
    "standard": {"concurrent": 10, "requests": 50},
    "stress": {"concurrent": 20, "requests": 100}
}
```

### Integration with External Systems
```bash
# External API Integration
# Configure in .env:
EXTERNAL_API_BASE_URL=https://api.example.com
EXTERNAL_API_AUTH_TOKEN=your_token_here

# CI/CD Integration
# Configure webhook notifications:
WEBHOOK_URL=https://your-ci-cd.com/webhook
WEBHOOK_SECRET=your_webhook_secret
```

## 📚 Additional Resources

### Documentation
- [Quick Start](../getting-started/quick-start.md)
- [Agent Documentation](../agents/index.md)
- [Kubernetes Deployment](kubernetes.md)

### Monitoring Dashboards
- WebGUI: http://localhost:8000
- Metrics: Configure with Prometheus + Grafana
- Logs: Configure with ELK Stack

### Support
- Check logs first: `docker-compose logs <service>`
- Review documentation: [Agent Documentation](../agents/index.md)
- Check system requirements: Memory, disk, network
- Create issue with full environment details and error logs

---

*Last Updated: 2026-02-10*  
*Version: Optimized 6-Agent System v2.0*
