#!/usr/bin/env bash
# Bump the project version everywhere.
#
# Usage:
#   ./scripts/bump-version.sh 2026.3.8-1  # same-day patch
#   ./scripts/bump-version.sh 2026.3.9    # new day
#   ./scripts/bump-version.sh             # defaults to today's date (YYYY.M.D)
#
# Updates:
#   VERSION                              (source of truth)
#   agnostic.agpkg.toml                  (AGNOS marketplace manifest)
#   k8s/helm/agentic-qa/Chart.yaml       (version + appVersion)
#   docker/README.md                     (example docker tag)
#   docs/adr/022-agnosticos-agent-hud.md (example version)
#
# Python code and pyproject.toml read VERSION at runtime/build time
# so they do not need patching.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

if [[ $# -ge 1 ]]; then
    NEW_VERSION="$1"
else
    # Default to today: YYYY.M.D (no zero-padding, PEP 440 style)
    YEAR="$(date +%Y)"
    MONTH="$(date +%-m)"
    DAY="$(date +%-d)"
    NEW_VERSION="${YEAR}.${MONTH}.${DAY}"
fi

VERSION_FILE="$PROJECT_ROOT/VERSION"
OLD_VERSION="$(tr -d '[:space:]' < "$VERSION_FILE" 2>/dev/null || echo "0.0.0")"

if [[ "$OLD_VERSION" == "$NEW_VERSION" ]]; then
    echo "Version is already $NEW_VERSION — nothing to do."
    exit 0
fi

echo "Bumping version: $OLD_VERSION -> $NEW_VERSION"
echo ""

# 1. VERSION file (source of truth)
printf '%s\n' "$NEW_VERSION" > "$VERSION_FILE"
echo "  Updated VERSION"

# 2. AGNOS marketplace manifest
AGPKG="$PROJECT_ROOT/agnostic.agpkg.toml"
if [[ -f "$AGPKG" ]]; then
    sed -i "s/^version = \"${OLD_VERSION}\"/version = \"${NEW_VERSION}\"/" "$AGPKG"
    echo "  Updated agnostic.agpkg.toml"
fi

# 3. Helm Chart.yaml
CHART="$PROJECT_ROOT/k8s/helm/agentic-qa/Chart.yaml"
if [[ -f "$CHART" ]]; then
    sed -i "s/^version: .*/version: $NEW_VERSION/" "$CHART"
    sed -i "s/^appVersion: .*/appVersion: \"$NEW_VERSION\"/" "$CHART"
    echo "  Updated k8s/helm/agentic-qa/Chart.yaml"
fi

# 4. Docker README example tag
DOCKER_README="$PROJECT_ROOT/docker/README.md"
if [[ -f "$DOCKER_README" ]]; then
    sed -i "s/agnostic:${OLD_VERSION}/agnostic:${NEW_VERSION}/g" "$DOCKER_README"
    echo "  Updated docker/README.md"
fi

# 5. ADR-022 example version
ADR022="$PROJECT_ROOT/docs/adr/022-agnosticos-agent-hud.md"
if [[ -f "$ADR022" ]]; then
    sed -i "s/\"version\": \"${OLD_VERSION}\"/\"version\": \"${NEW_VERSION}\"/g" "$ADR022"
    echo "  Updated docs/adr/022-agnosticos-agent-hud.md"
fi

echo ""
echo "Done. Version is now $NEW_VERSION"
echo ""
echo "Files that read VERSION at runtime (no patching needed):"
echo "  pyproject.toml              (setuptools dynamic version)"
echo "  shared/version.py           (Python code)"
echo "  config/agnos_agent_registration.py"
echo "  shared/yeoman_mcp_server.py"
echo "  webgui/routes/dashboard.py"
echo "  scripts/build-release.sh"
