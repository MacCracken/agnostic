#!/usr/bin/env bash
# check-webgui-js.sh — run the WebGUI's JavaScript tests (tests/webgui/*.test.mjs) under Node.
#
# The WebGUI is Agnostic's one body of JavaScript: the shell's host-bridge gate and every
# plugin's logic (Swarm Command's simulator, spec normalizer, crew builder, live crew source
# and swarm library). None of it is Cyrius, so `cyrius test` never reaches it — until 0.1.9 the
# logic was tested once, by hand, and the tests thrown away. These run it in a `vm` context
# against the pages' own bytes (tests/webgui/harness.mjs), so a test exercises exactly what is
# embedded and served.
#
# Node is a test-time dependency only: nothing that ships runs on it.
#
#   ./scripts/check-webgui-js.sh          run the tests; fail if Node is missing
#   AGNOSTIC_JS_OPTIONAL=1 ./scripts/...   skip with a notice when Node is missing (local use)
set -uo pipefail
cd "$(dirname "$0")/.." || exit 2

if ! command -v node >/dev/null 2>&1; then
    if [ "${AGNOSTIC_JS_OPTIONAL:-0}" = "1" ]; then
        echo "webgui js: node not found — skipped (AGNOSTIC_JS_OPTIONAL=1)"
        exit 0
    fi
    echo "webgui js: node not found — install Node 20 or later to run tests/webgui/" >&2
    exit 1
fi

major=$(node -p 'process.versions.node.split(".")[0]')
if [ "$major" -lt 20 ]; then
    echo "webgui js: Node $major is too old — tests/webgui/ needs Node 20 or later" >&2
    exit 1
fi

# The files are named, not the directory: since Node 21, `--test` arguments are glob patterns,
# and a directory is no longer searched — Node 22 tries to load `tests/webgui/` itself as a module
# ("Cannot find module"), while Node 20 and 26 search it. Naming the files works on all of them.
shopt -s nullglob
files=(tests/webgui/*.test.mjs)
if [ "${#files[@]}" -eq 0 ]; then
    echo "webgui js: no tests found — tests/webgui/*.test.mjs is empty" >&2
    exit 1
fi
out=$(node --test --test-reporter=spec "${files[@]}" 2>&1)
rc=$?
if [ "$rc" -ne 0 ]; then
    printf '%s\n' "$out" | grep -E '✖|Error|expected|actual' | head -40 >&2
    echo "webgui js: FAILED" >&2
    exit "$rc"
fi
pass=$(printf '%s\n' "$out" | grep -oE 'ℹ pass [0-9]+' | grep -oE '[0-9]+$')
echo "webgui js: ${pass:-?} tests passed (node $(node --version))"
