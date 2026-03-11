#!/bin/bash
# Agnostic QA Platform — production entrypoint
#
# Starts embedded Redis and/or PostgreSQL unless external URLs are provided.
# Optionally enables TLS via Caddy reverse proxy for standalone deployments.
# Managed by supervisord for process supervision and log routing.
set -e

# ---------------------------------------------------------------------------
# Detect whether to use embedded or external services
# ---------------------------------------------------------------------------

# Redis: skip embedded if REDIS_URL points to a remote host
REDIS_EMBEDDED=true
if [ -n "$REDIS_URL" ]; then
    REDIS_HOST=$(python3 -c "from urllib.parse import urlparse; print(urlparse('$REDIS_URL').hostname or 'localhost')")
    if [ "$REDIS_HOST" != "localhost" ] && [ "$REDIS_HOST" != "127.0.0.1" ]; then
        echo "[entrypoint] External Redis detected ($REDIS_HOST) — skipping embedded Redis"
        REDIS_EMBEDDED=false
    fi
fi

# PostgreSQL: skip embedded if DATABASE_URL points to a remote host, or DB is disabled
POSTGRES_EMBEDDED=true
if [ "${DATABASE_ENABLED}" != "true" ]; then
    echo "[entrypoint] DATABASE_ENABLED != true — skipping embedded PostgreSQL"
    POSTGRES_EMBEDDED=false
elif [ -n "$DATABASE_URL" ]; then
    PG_HOST=$(python3 -c "from urllib.parse import urlparse; print(urlparse('$DATABASE_URL').hostname or 'localhost')")
    if [ "$PG_HOST" != "localhost" ] && [ "$PG_HOST" != "127.0.0.1" ]; then
        echo "[entrypoint] External PostgreSQL detected ($PG_HOST) — skipping embedded PostgreSQL"
        POSTGRES_EMBEDDED=false
    fi
fi

# Set defaults for embedded services
if [ "$REDIS_EMBEDDED" = "true" ]; then
    export REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6379/0}"
    echo "[entrypoint] Starting embedded Redis"
fi

if [ "$POSTGRES_EMBEDDED" = "true" ]; then
    export POSTGRES_USER="${POSTGRES_USER:-agnostic}"
    export POSTGRES_DB="${POSTGRES_DB:-agnostic}"
    export DATABASE_URL="${DATABASE_URL:-postgresql+asyncpg://${POSTGRES_USER}@127.0.0.1:5432/${POSTGRES_DB}}"
    export DATABASE_ENABLED=true
    echo "[entrypoint] Starting embedded PostgreSQL"
fi

# ---------------------------------------------------------------------------
# Initialize PostgreSQL data directory on first run
# ---------------------------------------------------------------------------
if [ "$POSTGRES_EMBEDDED" = "true" ] && [ ! -f /data/postgres/PG_VERSION ]; then
    echo "[entrypoint] Initializing PostgreSQL data directory..."
    chown -R postgres:postgres /data/postgres
    su -s /bin/bash - postgres -c \
        "/usr/lib/postgresql/17/bin/initdb -D /data/postgres --auth=md5 --no-locale --encoding=UTF8"
    export PG_FIRST_RUN=true
fi

# ---------------------------------------------------------------------------
# TLS configuration
# ---------------------------------------------------------------------------
TLS_ENABLED="${TLS_ENABLED:-false}"
CADDY_ENABLED=false

if [ "$TLS_ENABLED" = "true" ]; then
    TLS_CERT_PATH="${TLS_CERT_PATH:-}"
    TLS_KEY_PATH="${TLS_KEY_PATH:-}"
    TLS_DOMAIN="${TLS_DOMAIN:-}"

    # Generate Caddyfile based on TLS mode
    if [ -n "$TLS_CERT_PATH" ] && [ -n "$TLS_KEY_PATH" ]; then
        # Mode 1: Provided certs (matches SY pattern, internal CA, etc.)
        echo "[entrypoint] TLS enabled with provided certs: ${TLS_CERT_PATH}"
        mkdir -p /etc/caddy
        cat > /etc/caddy/Caddyfile <<CADDYEOF
{
    auto_https off
    admin off
}

:443 {
    tls ${TLS_CERT_PATH} ${TLS_KEY_PATH}
    reverse_proxy 127.0.0.1:8000
    encode gzip
    header {
        Strict-Transport-Security "max-age=63072000; includeSubDomains; preload"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
        Referrer-Policy "strict-origin-when-cross-origin"
    }
}

:80 {
    redir https://{host}{uri} permanent
}
CADDYEOF
        CADDY_ENABLED=true

    elif [ -n "$TLS_DOMAIN" ]; then
        # Mode 2: Auto-HTTPS with ACME (standalone, public domain)
        echo "[entrypoint] TLS enabled with auto-HTTPS for domain: ${TLS_DOMAIN}"
        mkdir -p /etc/caddy
        cat > /etc/caddy/Caddyfile <<CADDYEOF
{
    admin off
}

${TLS_DOMAIN} {
    reverse_proxy 127.0.0.1:8000
    encode gzip
    header {
        Strict-Transport-Security "max-age=63072000; includeSubDomains; preload"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
        Referrer-Policy "strict-origin-when-cross-origin"
    }
}
CADDYEOF
        CADDY_ENABLED=true

    else
        echo "[entrypoint] WARNING: TLS_ENABLED=true but no TLS_CERT_PATH/TLS_KEY_PATH or TLS_DOMAIN set — TLS disabled"
        TLS_ENABLED=false
    fi
fi

# ---------------------------------------------------------------------------
# Export flags for supervisord conditional autostart
# ---------------------------------------------------------------------------
export REDIS_EMBEDDED
export POSTGRES_EMBEDDED
export CADDY_ENABLED
export PG_FIRST_RUN="${PG_FIRST_RUN:-false}"

# When Caddy handles TLS, bind app to loopback only (prevent direct access bypassing TLS)
if [ "$CADDY_ENABLED" = "true" ]; then
    export CHAINLIT_HOST="127.0.0.1"
    echo "[entrypoint] App bound to 127.0.0.1 (Caddy handles external traffic)"
fi

echo "[entrypoint] Services: redis=${REDIS_EMBEDDED}, postgres=${POSTGRES_EMBEDDED}, tls=${CADDY_ENABLED}"
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/agnostic.conf
