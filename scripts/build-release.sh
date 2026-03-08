#!/usr/bin/env bash
# Build release artifacts and rename to agnostic-VERSION format.
#
# Usage:
#   ./scripts/build-release.sh            # uses version from VERSION file
#   ./scripts/build-release.sh 2026.3.8   # explicit version
#   ./scripts/build-release.sh 2026.3.8-1 # same-day patch
#
# Git tags/releases use YYYY.M.D or YYYY.M.D-N (calendar versioning).
# Build artifacts use agnostic-VERSION (e.g. agnostic-2026.3.8-1).

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
    VERSION="$1"
else
    VERSION_FILE="$PROJECT_ROOT/VERSION"
    if [[ ! -f "$VERSION_FILE" ]]; then
        echo "ERROR: VERSION file not found at $VERSION_FILE" >&2
        exit 1
    fi
    VERSION="$(tr -d '[:space:]' < "$VERSION_FILE")"
fi

BUILD_NAME="agnostic-${VERSION}"

echo "Version    : $VERSION"
echo "Build name : $BUILD_NAME"
echo ""

# Build sdist + wheel
cd "$PROJECT_ROOT"
"$PYTHON" -m build --sdist --wheel

# PEP 440 normalizes "2026.3.8-1" to "2026.3.8.post1", so we need to match
# the normalized name that `python -m build` actually produces.
BASE_VERSION="${VERSION%%-*}"
if [[ "$VERSION" == *-* ]]; then
    PATCH_NUM="${VERSION#*-}"
    PEP_NORMALIZED="agnostic_qa-${BASE_VERSION}.post${PATCH_NUM}"
else
    PEP_NORMALIZED="agnostic_qa-${VERSION}"
fi

# Rename artifacts
for ext in tar.gz; do
    src="$DIST_DIR/${PEP_NORMALIZED}.${ext}"
    dst="$DIST_DIR/${BUILD_NAME}.${ext}"
    if [[ -f "$src" ]]; then
        mv "$src" "$dst"
        echo "Renamed: $(basename "$src") -> $(basename "$dst")"
    fi
done

for whl in "$DIST_DIR"/${PEP_NORMALIZED}-*.whl; do
    if [[ -f "$whl" ]]; then
        base="$(basename "$whl")"
        new_base="${base/${PEP_NORMALIZED}/${BUILD_NAME}}"
        mv "$whl" "$DIST_DIR/$new_base"
        echo "Renamed: $base -> $new_base"
    fi
done

echo ""
echo "Release artifacts:"
ls -1 "$DIST_DIR"/${BUILD_NAME}*
echo ""
echo "Git tag/release: $VERSION"
