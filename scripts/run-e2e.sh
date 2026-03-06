#!/usr/bin/env bash
# run-e2e.sh — Start services (if needed), run E2E tests, exit with test status.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

E2E_BASE_URL="${E2E_BASE_URL:-http://localhost:8000}"
E2E_API_KEY="${E2E_API_KEY:-test-e2e-key}"
HEALTH_URL="${E2E_BASE_URL}/health"
MAX_WAIT=60

export E2E_BASE_URL E2E_API_KEY
export AGNOSTIC_API_KEY="${AGNOSTIC_API_KEY:-$E2E_API_KEY}"

# ── 1. Check if services are already running ────────────────────────────
echo "Checking $HEALTH_URL ..."
SERVICES_RUNNING=0
if curl -sf "$HEALTH_URL" >/dev/null 2>&1; then
    SERVICES_RUNNING=1
    echo "Services already running."
fi

# ── 2. Start services if needed ─────────────────────────────────────────
STARTED_SERVICES=0
if [ "$SERVICES_RUNNING" -eq 0 ]; then
    if [ "${E2E_FULL_STACK:-0}" = "1" ]; then
        echo "Starting full stack (docker-compose.yml) ..."
        docker compose up -d
    else
        echo "Starting test services (docker-compose.test.yml) ..."
        docker compose -f docker-compose.test.yml up -d
    fi
    STARTED_SERVICES=1

    # ── 3. Wait for health endpoint ─────────────────────────────────────
    echo "Waiting for $HEALTH_URL (max ${MAX_WAIT}s) ..."
    elapsed=0
    while [ "$elapsed" -lt "$MAX_WAIT" ]; do
        if curl -sf "$HEALTH_URL" >/dev/null 2>&1; then
            echo "Health endpoint ready after ${elapsed}s."
            break
        fi
        sleep 2
        elapsed=$((elapsed + 2))
    done

    if [ "$elapsed" -ge "$MAX_WAIT" ]; then
        echo "ERROR: Health endpoint not ready after ${MAX_WAIT}s."
        exit 1
    fi
fi

# ── 4. Run E2E tests ────────────────────────────────────────────────────
echo "Running E2E tests ..."
set +e
pytest tests/e2e/ -v -m e2e
TEST_EXIT=$?
set -e

# ── 5. Exit with pytest status ──────────────────────────────────────────
exit "$TEST_EXIT"
