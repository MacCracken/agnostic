#!/usr/bin/env bash
# Build release artifacts and rename to agnostic_qa_YYYY_MM_DD format.
#
# Usage:
#   ./scripts/build-release.sh          # uses version from pyproject.toml
#   ./scripts/build-release.sh 2026.3.7 # explicit version
#
# Git tags/releases use YYYY.M.D (PEP 440).
# Build artifacts use agnostic_qa_YYYY_MM_DD (underscore format).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DIST_DIR="$PROJECT_ROOT/dist"
PYTHON="${PYTHON:-${PROJECT_ROOT}/.venv/bin/python}"

if [[ ! -x "$PYTHON" ]]; then
    PYTHON="$(command -v python3 || command -v python)"
fi

# Read version from VERSION file or CLI arg
if [[ $# -ge 1 ]]; then
    PEP_VERSION="$1"
else
    VERSION_FILE="$PROJECT_ROOT/VERSION"
    if [[ ! -f "$VERSION_FILE" ]]; then
        echo "ERROR: VERSION file not found at $VERSION_FILE" >&2
        exit 1
    fi
    PEP_VERSION="$(tr -d '[:space:]' < "$VERSION_FILE")"
fi

# Convert YYYY.M.D -> YYYY_MM_DD
IFS='.' read -r YEAR MONTH DAY <<< "$PEP_VERSION"
UNDERSCORE_VERSION="${YEAR}_$(printf '%02d' "$MONTH")_$(printf '%02d' "$DAY")"
BUILD_NAME="agnostic_qa_${UNDERSCORE_VERSION}"

echo "PEP 440 version : $PEP_VERSION"
echo "Build name       : $BUILD_NAME"
echo ""

# Build sdist + wheel
cd "$PROJECT_ROOT"
"$PYTHON" -m build --sdist --wheel

# Rename artifacts
PEP_NAME="agnostic_qa-${PEP_VERSION}"

for ext in tar.gz; do
    src="$DIST_DIR/${PEP_NAME}.${ext}"
    dst="$DIST_DIR/${BUILD_NAME}.${ext}"
    if [[ -f "$src" ]]; then
        mv "$src" "$dst"
        echo "Renamed: $(basename "$src") -> $(basename "$dst")"
    fi
done

for whl in "$DIST_DIR"/${PEP_NAME}-*.whl; do
    if [[ -f "$whl" ]]; then
        base="$(basename "$whl")"
        new_base="${base/${PEP_NAME}/${BUILD_NAME}}"
        mv "$whl" "$DIST_DIR/$new_base"
        echo "Renamed: $base -> $new_base"
    fi
done

echo ""
echo "Release artifacts:"
ls -1 "$DIST_DIR"/${BUILD_NAME}*
echo ""
echo "Git tag/release: $PEP_VERSION"
