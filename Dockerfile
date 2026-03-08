# Agnostic QA Platform
#
# Single image for webgui (default) and distributed workers (via AGENT_ROLE).
#
# Build:
#   docker build -t agnostic:latest .
#
# Run:
#   docker compose up -d                          # webgui on AGNOS
#   docker compose --profile dev up -d            # dev with infra containers
#   docker compose --profile dev --profile workers up -d  # + workers

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
    && rm -rf /var/lib/apt/lists/* && apt-get clean

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

# Application code
COPY --chown=appuser:appuser VERSION ./VERSION
COPY --chown=appuser:appuser webgui/ ./webgui/
COPY --chown=appuser:appuser agents/ ./agents/
COPY --chown=appuser:appuser config/ ./config/
COPY --chown=appuser:appuser shared/ ./shared/
COPY --chown=appuser:appuser docker/agent-entrypoint.sh ./agent-entrypoint.sh

# WebGUI defaults
ENV CHAINLIT_HOST=0.0.0.0
ENV CHAINLIT_PORT=8000

USER appuser

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

LABEL org.opencontainers.image.source="https://github.com/MacCracken/agnostic"
LABEL org.opencontainers.image.description="Agnostic QA Platform"
LABEL org.opencontainers.image.licenses="MIT"

CMD ["chainlit", "run", "webgui/app.py", "--host", "0.0.0.0", "--port", "8000"]
