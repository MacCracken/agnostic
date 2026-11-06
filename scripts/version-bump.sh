#!/usr/bin/env bash
# version-bump.sh — set the project version.
#
# VERSION at the repo root is the single source of truth. cyrius.cyml reads it
# back with `version = "${file:VERSION}"`, so the manifest cannot drift and
# needs no edit — this script only verifies the interpolation is still there
# rather than a hardcoded number. That leaves the CHANGELOG as the one other
# place the number appears, so a bump cuts the [Unreleased] section over to a
# dated release heading.
#
# Everything is checked before anything is written: a failed check leaves the
# repo untouched instead of half-bumped.
set -euo pipefail

if [ $# -ne 1 ]; then
    echo "Usage: $0 <new-version>"
    echo "Example: $0 2.0.0"
    exit 1
fi

NEW_VERSION="$1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

VERSION_FILE="$REPO_ROOT/VERSION"
CYML="$REPO_ROOT/cyrius.cyml"
CHANGELOG="$REPO_ROOT/CHANGELOG.md"
DATE="$(date -u +%Y-%m-%d)"

# The one form cyrius.cyml's [package].version is allowed to take.
CYML_INTERP='version = "${file:VERSION}"'

echo "Bumping Agnostic to version ${NEW_VERSION}..."

# Pre-flight — nothing is written until every check below passes.

if ! echo "$NEW_VERSION" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?$'; then
    echo "ERROR: not a semantic version: ${NEW_VERSION} (tags are bare, e.g. 2.0.0)"
    exit 1
fi

for f in "$VERSION_FILE" "$CYML" "$CHANGELOG"; do
    if [ ! -f "$f" ]; then
        echo "ERROR: missing ${f#"$REPO_ROOT"/}"
        exit 1
    fi
done

CYML_LINE="$(grep -m1 '^version = ' "$CYML" || true)"
if [ "$CYML_LINE" != "$CYML_INTERP" ]; then
    echo "ERROR: cyrius.cyml [package].version is not the interpolation form"
    echo "       expected: ${CYML_INTERP}"
    echo "       found:    ${CYML_LINE:-<no version line>}"
    echo "       VERSION is the source of truth — restore the interpolation, do not hardcode."
    exit 1
fi

# The top released heading is the first `## [X.Y.Z]`; [Unreleased] is not one.
TOP_VERSION="$(grep -m1 -E '^## \[[0-9]' "$CHANGELOG" | sed -n 's/^## \[\([^]]*\)\].*/\1/p' || true)"

CUT_CHANGELOG=1
if [ "$TOP_VERSION" = "$NEW_VERSION" ]; then
    # Already cut — a re-run. Leave the heading and its release date alone.
    CUT_CHANGELOG=0
else
    UNRELEASED_LINE="$(grep -n -m1 '^## \[Unreleased\]' "$CHANGELOG" | cut -d: -f1 || true)"
    if [ -z "$UNRELEASED_LINE" ]; then
        echo "ERROR: CHANGELOG.md has no [Unreleased] section to cut into ${NEW_VERSION}"
        echo "       top released heading is ${TOP_VERSION:-<none>}"
        exit 1
    fi
    UNRELEASED_BODY="$(awk -v start="$UNRELEASED_LINE" \
        'NR > start { if (/^## \[/) exit; print }' "$CHANGELOG" | tr -d '[:space:]')"
    if [ -z "$UNRELEASED_BODY" ]; then
        echo "ERROR: CHANGELOG.md [Unreleased] is empty — nothing to release as ${NEW_VERSION}"
        exit 1
    fi
fi

# Write.

echo "$NEW_VERSION" > "$VERSION_FILE"
echo "  Updated VERSION"
echo "  cyrius.cyml interpolates VERSION — no edit needed"

if [ "$CUT_CHANGELOG" -eq 1 ]; then
    TMPFILE="$(mktemp)"
    trap 'rm -f "$TMPFILE"' EXIT
    # Insert the release heading directly under [Unreleased], which leaves the
    # unreleased entries as the new release's body and [Unreleased] empty.
    awk -v heading="## [${NEW_VERSION}] — ${DATE}" '
        !cut && /^## \[Unreleased\]/ { print; print ""; print heading; cut = 1; next }
        { print }
    ' "$CHANGELOG" > "$TMPFILE"
    cat "$TMPFILE" > "$CHANGELOG"
    echo "  Cut CHANGELOG [Unreleased] to [${NEW_VERSION}] — ${DATE}"
else
    echo "  CHANGELOG already headed by [${NEW_VERSION}] — left alone"
fi

# Validate.

FILE_VERSION="$(tr -d '[:space:]' < "$VERSION_FILE")"
if [ "$FILE_VERSION" != "$NEW_VERSION" ]; then
    echo "ERROR: VERSION file mismatch: expected $NEW_VERSION, got $FILE_VERSION"
    exit 1
fi

CYML_LINE="$(grep -m1 '^version = ' "$CYML" || true)"
if [ "$CYML_LINE" != "$CYML_INTERP" ]; then
    echo "ERROR: cyrius.cyml version line no longer interpolates: ${CYML_LINE:-<no version line>}"
    exit 1
fi

TOP_VERSION="$(grep -m1 -E '^## \[[0-9]' "$CHANGELOG" | sed -n 's/^## \[\([^]]*\)\].*/\1/p' || true)"
if [ "$TOP_VERSION" != "$NEW_VERSION" ]; then
    echo "ERROR: CHANGELOG top released heading mismatch: expected $NEW_VERSION, got ${TOP_VERSION:-<none>}"
    exit 1
fi

echo ""
echo "Version bumped to ${NEW_VERSION}"
echo ""
echo "Next steps:"
echo "  refresh docs/development/state.md — it carries the version too"
echo "  git add VERSION CHANGELOG.md"
echo "  git commit -m \"bump to ${NEW_VERSION}\""
echo "  git tag ${NEW_VERSION}"
echo "  git push && git push --tags"
