#!/bin/bash
# Generate Python and TypeScript client SDKs from the FastAPI OpenAPI schema.
#
# Prerequisites:
#   pip install openapi-python-client   (Python SDK)
#   npm install -g @openapitools/openapi-generator-cli   (TypeScript SDK)
#
# Usage:
#   ./scripts/generate-sdk.sh [python|typescript|both]
#
# The script fetches the live OpenAPI schema from http://localhost:8000/openapi.json
# or falls back to generating it offline via Python.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
SDK_DIR="$PROJECT_ROOT/sdk"
SCHEMA_URL="${AGNOSTIC_URL:-http://localhost:8000}/openapi.json"
SCHEMA_FILE="$SDK_DIR/openapi.json"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

mkdir -p "$SDK_DIR"

# ---------------------------------------------------------------------------
# Fetch or generate the OpenAPI schema
# ---------------------------------------------------------------------------
fetch_schema() {
    echo -e "${BLUE}Fetching OpenAPI schema...${NC}"

    # Try live server first
    if curl -sf "$SCHEMA_URL" -o "$SCHEMA_FILE" 2>/dev/null; then
        echo -e "${GREEN}✓ Schema fetched from $SCHEMA_URL${NC}"
        return
    fi

    # Fall back to offline generation
    echo -e "${YELLOW}Server not running, generating schema offline...${NC}"
    cd "$PROJECT_ROOT"
    python -c "
import json, sys
sys.path.insert(0, '.')
from webgui.app import app
schema = app.openapi()
with open('$SCHEMA_FILE', 'w') as f:
    json.dump(schema, f, indent=2)
print('Schema written to $SCHEMA_FILE')
"
    echo -e "${GREEN}✓ Schema generated offline${NC}"
}

# ---------------------------------------------------------------------------
# Python SDK
# ---------------------------------------------------------------------------
generate_python() {
    echo ""
    echo -e "${BLUE}Generating Python SDK...${NC}"

    if ! command -v openapi-python-client &>/dev/null; then
        echo -e "${RED}Error: openapi-python-client not installed${NC}"
        echo "  pip install openapi-python-client"
        return 1
    fi

    rm -rf "$SDK_DIR/python"
    openapi-python-client generate \
        --path "$SCHEMA_FILE" \
        --output-path "$SDK_DIR/python" \
        --config <(echo '{"project_name_override": "agnostic-client", "package_name_override": "agnostic_client"}')

    echo -e "${GREEN}✓ Python SDK generated at sdk/python/${NC}"
}

# ---------------------------------------------------------------------------
# TypeScript SDK
# ---------------------------------------------------------------------------
generate_typescript() {
    echo ""
    echo -e "${BLUE}Generating TypeScript SDK...${NC}"

    if ! command -v openapi-generator-cli &>/dev/null; then
        echo -e "${RED}Error: openapi-generator-cli not installed${NC}"
        echo "  npm install -g @openapitools/openapi-generator-cli"
        return 1
    fi

    rm -rf "$SDK_DIR/typescript"
    openapi-generator-cli generate \
        -i "$SCHEMA_FILE" \
        -g typescript-fetch \
        -o "$SDK_DIR/typescript" \
        --additional-properties=npmName=agnostic-client,supportsES6=true,typescriptThreePlus=true

    echo -e "${GREEN}✓ TypeScript SDK generated at sdk/typescript/${NC}"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
fetch_schema

case "${1:-both}" in
    python)
        generate_python
        ;;
    typescript|ts)
        generate_typescript
        ;;
    both|"")
        generate_python
        generate_typescript
        ;;
    *)
        echo "Usage: $0 [python|typescript|both]"
        exit 1
        ;;
esac

echo ""
echo -e "${GREEN}SDK generation complete!${NC}"
echo "Schema: $SCHEMA_FILE"
