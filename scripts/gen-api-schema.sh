#!/usr/bin/env bash
# gen-api-schema.sh — write the binary's description of its own HTTP API to the committed snapshot.
#
#   ./scripts/gen-api-schema.sh                 regenerate docs/api/generated/schema.json
#   ./scripts/gen-api-schema.sh --check         fail if the snapshot differs from what the binary prints
#   ./scripts/gen-api-schema.sh --bin PATH ...  ask PATH rather than build/agnostic
#
# The snapshot is `agnostic api schema`'s output (`src/http/schema.cyr`, ADR 0015). It is
# generated, never edited by hand (first-party-documentation.md, `docs/api/generated/`), and it
# is what turns the v1.0 criterion "public API frozen" into a diff: an API change regenerates
# it in the same change, and the reviewer reads the API change there.
#
# ## Two checks, deliberately different
#
#   * `tests/api_schema.tcyr` (`api/snapshot`) compiles the generator FRESH from src/ and
#     compares its text with the snapshot re-printed through the same bayan. It cannot be
#     fooled by a stale binary, and key order counts.
#   * `--check`, here, runs a BINARY — the real argument path, `agnostic api schema` — and
#     compares parsed JSON: values and array order count, whitespace and key order do not, so a
#     bayan formatting change arriving with a toolchain bump is not reported as an API change.
#     CI runs it on the shipped DCE binary after the build; `scripts/check-clean.sh` runs it
#     when `build/agnostic` is newer than everything it is built from.
#
# ## ⚠ It never builds
#
# A `cyrius build` re-provisions lib/ and may rewrite cyrius.lock, and `check-clean.sh` — which
# calls this — runs before the Build step in CI. Build first, as CLAUDE.md says:
#
#   cyrius build src/main.cyr build/agnostic && ./scripts/gen-api-schema.sh
#
# Exit codes: 0 ok, 1 the snapshot differs or the binary failed, 2 usage or no binary.
set -uo pipefail

cd "$(dirname "$0")/.." || exit 2

OUT="docs/api/generated/schema.json"
BIN="build/agnostic"
MODE="generate"

usage() { echo "usage: ./scripts/gen-api-schema.sh [--check] [--bin PATH]" >&2; exit 2; }
while [ $# -gt 0 ]; do
    case "$1" in
        --check) MODE="check" ;;
        --bin) [ $# -ge 2 ] || usage; shift; BIN="$1" ;;
        *) usage ;;
    esac
    shift
done

if [ ! -x "$BIN" ]; then
    echo "gen-api-schema: no binary at $BIN — build it first: cyrius build src/main.cyr build/agnostic" >&2
    exit 2
fi

tmpdir=$(mktemp -d "${TMPDIR:-/tmp}/gen-api-schema.XXXXXX") || exit 2
trap 'rm -rf "$tmpdir"' EXIT
gen="$tmpdir/schema.json"

# ⚠ **Under a time limit.** A binary that does not answer `api schema` SERVES instead, and would
# block CI and check-clean.sh here for good: one from before 0.1.13 passed by --bin, or one that
# cannot read its arguments (`argc()` answers 0, and `src/cli.cyr` then serves, as before).
# The real command takes milliseconds. 124 is timeout's "it ran out", 137 its follow-up KILL.
timeout -k 5 60 "$BIN" api schema > "$gen"
rc=$?
if [ "$rc" -eq 124 ] || [ "$rc" -eq 137 ]; then
    echo "gen-api-schema: '$BIN api schema' did not answer within 60s — a binary that does not" \
         "read its arguments serves instead" >&2
    exit 1
fi
if [ "$rc" -ne 0 ]; then
    echo "gen-api-schema: '$BIN api schema' exited $rc" >&2
    exit 1
fi
if ! python3 -c 'import json, sys; json.load(open(sys.argv[1]))' "$gen" 2>/dev/null; then
    echo "gen-api-schema: '$BIN api schema' did not print one JSON document" >&2
    exit 1
fi

if [ "$MODE" = "check" ]; then
    if [ ! -f "$OUT" ]; then
        echo "gen-api-schema: $OUT is missing — run ./scripts/gen-api-schema.sh" >&2
        exit 1
    fi
    if ! python3 -c 'import json, sys; sys.exit(json.load(open(sys.argv[1])) != json.load(open(sys.argv[2])))' \
            "$OUT" "$gen"; then
        echo "gen-api-schema: $OUT differs from what $BIN prints — the API changed;" \
             "regenerate with ./scripts/gen-api-schema.sh and add a CHANGELOG line" >&2
        diff -u "$OUT" "$gen" | head -60 >&2
        exit 1
    fi
    echo "gen-api-schema: $OUT matches $BIN"
    exit 0
fi

mkdir -p "$(dirname "$OUT")" || exit 2
cp "$gen" "$OUT" || exit 2
echo "gen-api-schema: wrote $OUT"
