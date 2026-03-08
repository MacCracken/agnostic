#!/bin/bash
# Build the Agnostic QA Platform Docker image.
#
# Produces a single image: agnostic:latest (+ version tag)
# Used by webgui (default CMD) and workers (via agent-entrypoint.sh).
#
#   ./scripts/build-docker.sh          # build agnostic:latest
#   ./scripts/build-docker.sh --clean  # prune dangling images after build

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERSION_FILE="$SCRIPT_DIR/../VERSION"
if [[ ! -f "$VERSION_FILE" ]]; then
    echo -e "${RED}Error: VERSION file not found${NC}"
    exit 1
fi
VERSION=$(tr -d '[:space:]' < "$VERSION_FILE")

if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}Error: Docker is not running${NC}"
    exit 1
fi

echo -e "${BLUE}Building agnostic:latest (v${VERSION})${NC}"
echo ""

export DOCKER_BUILDKIT=1

docker build \
    --tag agnostic:latest \
    --tag "agnostic:${VERSION}" \
    --file Dockerfile \
    --progress=plain \
    --load \
    .

echo ""
echo -e "${GREEN}✓ Built agnostic:latest (agnostic:${VERSION})${NC}"

if [[ "${1:-}" == "--clean" ]]; then
    docker image prune -f
fi

echo ""
echo "Run:"
echo "  docker compose up -d                                  # production"
echo "  docker compose --profile dev up -d                    # development"
echo "  docker compose --profile dev --profile workers up -d  # + workers"
