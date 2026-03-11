# Agnostic QA Platform on AGNOS Python 3.13
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

FROM ghcr.io/maccracken/agnosticos:python3.13

ENV PYTHONPATH=/app
ENV DEBIAN_FRONTEND=noninteractive

USER root

WORKDIR /app

# Additional system deps: embedded services + supervisor
RUN apt-get update && apt-get install -y --no-install-recommends \
    netcat-openbsd \
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
RUN pip install --no-cache-dir --break-system-packages -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

# App user (UID 1000 — primary AGNOS app-space user)
RUN groupadd -g 1000 agnostic && useradd -u 1000 -g agnostic -m -s /bin/bash agnostic
RUN mkdir -p /app/logs && chown -R agnostic:agnostic /app

# Playwright browsers
USER agnostic
RUN playwright install chromium
USER root

# Persistent data directories for embedded services
RUN mkdir -p /data/redis /data/postgres /data/caddy /var/log/supervisor \
    && chown -R agnostic:agnostic /data/redis \
    && chown -R postgres:postgres /data/postgres

# Application code
COPY --chown=agnostic:agnostic VERSION ./VERSION
COPY --chown=agnostic:agnostic webgui/ ./webgui/
COPY --chown=agnostic:agnostic agents/ ./agents/
COPY --chown=agnostic:agnostic config/ ./config/
COPY --chown=agnostic:agnostic shared/ ./shared/
COPY --chown=agnostic:agnostic docker/agent-entrypoint.sh ./agent-entrypoint.sh

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
LABEL org.opencontainers.image.description="Agnostic QA Platform on AGNOS"
LABEL org.opencontainers.image.licenses="MIT"
LABEL org.opencontainers.image.base.name="ghcr.io/maccracken/agnosticos:python3.13"

ENTRYPOINT ["/app/docker/entrypoint.sh"]
