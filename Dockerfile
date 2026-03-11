# Agnostic QA Platform
#
# Production image with embedded Redis + PostgreSQL (managed by supervisord).
# Optional TLS termination via Caddy for standalone deployments.
# External services can be used instead by setting REDIS_URL / DATABASE_URL.
#
# Build:
#   docker build -t agnostic:latest .
#
# Run:
#   docker compose up -d                          # production (embedded services)
#   docker compose --profile dev up -d            # dev with separate containers
#
# TLS (standalone):
#   TLS_ENABLED=true TLS_CERT_PATH=/certs/cert.pem TLS_KEY_PATH=/certs/key.pem docker compose up -d
#   TLS_ENABLED=true TLS_DOMAIN=qa.example.com docker compose up -d   # auto-HTTPS

FROM python:3.13-slim

# Environment
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/app
ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ git curl make \
    # OpenCV / computer vision
    libgl1 libglib2.0-0 libsm6 libxext6 libxrender-dev libgomp1 libgthread-2.0-0 \
    # Crypto
    libssl-dev libffi-dev \
    # Playwright
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libasound2 \
    # Health check
    netcat-openbsd \
    # Embedded services (skipped at runtime if external URLs provided)
    redis-server \
    postgresql-17 postgresql-client-17 \
    supervisor \
    && rm -rf /var/lib/apt/lists/* && apt-get clean

# Caddy — production TLS reverse proxy (skipped at runtime if TLS_ENABLED!=true)
RUN ARCH=$(dpkg --print-architecture) \
    && curl -fsSL "https://caddyserver.com/api/download?os=linux&arch=${ARCH}" -o /usr/local/bin/caddy \
    && chmod +x /usr/local/bin/caddy

# Python dependencies
COPY requirements-docker.txt /tmp/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir -r /tmp/requirements.txt

# App user
RUN groupadd -r appuser && useradd -r -m -g appuser appuser
RUN mkdir -p /app/logs && chown -R appuser:appuser /app

# Playwright browsers
USER appuser
RUN playwright install chromium
USER root

# Persistent data directories for embedded services
RUN mkdir -p /data/redis /data/postgres /data/caddy /var/log/supervisor \
    && chown -R appuser:appuser /data/redis \
    && chown -R postgres:postgres /data/postgres

# Application code
COPY --chown=appuser:appuser VERSION ./VERSION
COPY --chown=appuser:appuser webgui/ ./webgui/
COPY --chown=appuser:appuser agents/ ./agents/
COPY --chown=appuser:appuser config/ ./config/
COPY --chown=appuser:appuser shared/ ./shared/
COPY --chown=appuser:appuser docker/agent-entrypoint.sh ./agent-entrypoint.sh

# Supervisord config and entrypoint
COPY docker/supervisord.conf /etc/supervisor/conf.d/agnostic.conf
COPY docker/entrypoint.sh /app/docker/entrypoint.sh
COPY docker/pg-init.sh /app/docker/pg-init.sh
RUN chmod +x /app/docker/entrypoint.sh /app/docker/pg-init.sh

# WebGUI defaults
ENV CHAINLIT_HOST=0.0.0.0
ENV CHAINLIT_PORT=8000

# Caddy data/config persistence
ENV XDG_DATA_HOME=/data/caddy
ENV XDG_CONFIG_HOME=/data/caddy/config

VOLUME ["/data"]

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000 443 80

LABEL org.opencontainers.image.source="https://github.com/MacCracken/agnostic"
LABEL org.opencontainers.image.description="Agnostic QA Platform"
LABEL org.opencontainers.image.licenses="MIT"

ENTRYPOINT ["/app/docker/entrypoint.sh"]
