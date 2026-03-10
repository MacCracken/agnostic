#!/bin/bash
# One-shot PostgreSQL database initialization.
# Called by supervisord on first run when PG_FIRST_RUN=true.
set -e

if [ "${PG_FIRST_RUN}" != "true" ]; then
    echo "[pg-init] Not first run — skipping"
    exit 0
fi

PG_USER="${POSTGRES_USER:-agnostic}"
PG_DB="${POSTGRES_DB:-agnostic}"
PG_PASSWORD="${POSTGRES_PASSWORD:-}"

echo "[pg-init] Waiting for PostgreSQL to accept connections..."
for i in $(seq 1 30); do
    if su -s /bin/bash - postgres -c "/usr/lib/postgresql/17/bin/pg_isready -q" 2>/dev/null; then
        break
    fi
    sleep 1
done

echo "[pg-init] Creating user '${PG_USER}' and database '${PG_DB}'..."
su -s /bin/bash - postgres -c "createuser -s ${PG_USER} 2>/dev/null || true"
if [ -n "$PG_PASSWORD" ]; then
    su -s /bin/bash - postgres -c "psql -c \"ALTER USER ${PG_USER} WITH PASSWORD '${PG_PASSWORD}';\"" 2>/dev/null || true
fi
su -s /bin/bash - postgres -c "createdb -O ${PG_USER} ${PG_DB} 2>/dev/null || true"
echo "[pg-init] Done"
