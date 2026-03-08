#!/bin/bash
# Build script for Agentic QA Team System Docker images
# This script builds the base image first, then all agent images

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}===========================================${NC}"
echo -e "${BLUE}Agentic QA Team - Docker Build Script${NC}"
echo -e "${BLUE}===========================================${NC}"
echo ""

# Read version from VERSION file
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERSION_FILE="$SCRIPT_DIR/../VERSION"
if [[ ! -f "$VERSION_FILE" ]]; then
    echo -e "${RED}Error: VERSION file not found at $VERSION_FILE${NC}"
    exit 1
fi
VERSION=$(tr -d '[:space:]' < "$VERSION_FILE")
echo -e "${BLUE}Version: ${VERSION}${NC}"
echo ""

# Function to check if Docker is running
check_docker() {
    if ! docker info > /dev/null 2>&1; then
        echo -e "${RED}Error: Docker is not running${NC}"
        exit 1
    fi
    echo -e "${GREEN}✓ Docker is running${NC}"
}

# Function to build base image
build_base() {
    echo -e "${YELLOW}Building base image (agnostic-qa-base)...${NC}"
    echo "This may take 10-15 minutes on first build..."
    echo ""
    
    # Enable BuildKit for better caching
    export DOCKER_BUILDKIT=1
    export COMPOSE_DOCKER_CLI_BUILD=1
    
    # Build base image with BuildKit
    docker build \
        --tag agnostic-qa-base:latest \
        --tag "agnostic-qa-base:${VERSION}" \
        --file docker/Dockerfile.base \
        --progress=plain \
        .
    
    echo -e "${GREEN}✓ Base image built successfully${NC}"
    echo ""
}

# Function to build agent images
build_agents() {
    echo -e "${YELLOW}Building agent images...${NC}"
    echo ""
    
    # Build all services except infrastructure (redis, rabbitmq)
    # These will use the cached base image
    docker compose build \
        qa-manager \
        senior-qa \
        junior-qa \
        qa-analyst \
        security-compliance-agent \
        performance-agent \
        webgui
    
    echo -e "${GREEN}✓ All agent images built successfully${NC}"
    echo ""
}

# Function to show image sizes
show_images() {
    echo -e "${BLUE}Docker Images:${NC}"
    docker images | grep agnostic | awk '{printf "  %-30s %s\n", $1, $7}'
    echo ""
}

# Function to clean up old images
cleanup() {
    echo -e "${YELLOW}Cleaning up dangling images...${NC}"
    docker image prune -f
    echo -e "${GREEN}✓ Cleanup complete${NC}"
    echo ""
}

# Main execution
main() {
    check_docker
    
    # Parse arguments
    case "${1:-}" in
        --base-only|-b)
            build_base
            show_images
            ;;
        --agents-only|-a)
            build_agents
            show_images
            ;;
        --cleanup|-c)
            cleanup
            ;;
        --help|-h)
            echo "Usage: $0 [OPTION]"
            echo ""
            echo "Options:"
            echo "  --base-only, -b     Build only the base image"
            echo "  --agents-only, -a  Build only agent images (requires base image)"
            echo "  --cleanup, -c      Clean up dangling images"
            echo "  --help, -h         Show this help message"
            echo ""
            echo "Without options, builds both base and agent images"
            exit 0
            ;;
        *)
            # Full build
            build_base
            build_agents
            cleanup
            show_images
            echo -e "${GREEN}===========================================${NC}"
            echo -e "${GREEN}Build complete!${NC}"
            echo -e "${GREEN}===========================================${NC}"
            echo ""
            echo "To start the system, run:"
            echo "  docker compose up -d"
            echo ""
            ;;
    esac
}

# Run main function
main "$@"
