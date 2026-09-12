#!/usr/bin/env bash
# lock-check.sh — verify the committed cyrius.lock still describes a clean
# resolution from the tags in cyrius.cyml.
#
# WHAT IT GUARDS. A `path = "../<dep>"` override in cyrius.cyml silently WINS
# over that dep's `tag`, so a lock produced with one active describes whatever
# the sibling checkout happened to be — which is not what CI, with no siblings,
# will build. This script fails the build when the committed lock disagrees with
# a tag-only resolution.
#
# WHY NOT `git diff --exit-code -- cyrius.lock`. That was the first attempt and
# it false-positived on the very first CI run: `cyrius deps` does NOT emit the
# lock's entries in a stable ORDER across machines. The order tracks the
# directory read order of lib/, so a fresh CI checkout produces the same 119
# hashes in a different sequence — a diff of ~100 reordered-but-identical lines,
# with `lib/bayan.cyr` carrying byte-identical hashes on both sides. Comparing
# byte-for-byte tests the filesystem, not the dependency graph.
#
# So the comparison is ORDER-INSENSITIVE, and split in two so the failure
# message can say which half moved:
#   - `commit` lines — the actual dep pins (sha, name, url, tag). A path
#     override or an advanced tag shows up here.
#   - `<sha256>  lib/<file>` lines — the resolved file set, compared as a
#     sorted set.
#
# Usage:
#   scripts/lock-check.sh              # re-resolves, compares against HEAD
#   scripts/lock-check.sh --no-resolve # compare the working tree against HEAD
#                                      # without re-resolving (the lock is
#                                      # assumed already resolved by a prior step)
#
# Exit codes:
#   0  — lock matches a clean tag resolution
#   1  — mismatch (or the lock is missing)

set -euo pipefail

LOCK="cyrius.lock"
RESOLVE=1
[[ "${1:-}" == "--no-resolve" ]] && RESOLVE=0

if [[ ! -f "$LOCK" ]]; then
  echo "lock-check: $LOCK not found — it is committed on purpose; run 'cyrius deps' and commit it" >&2
  exit 1
fi

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

# Baseline comes from the COMMITTED lock (git), not the working tree.
#
# Audit 2026-08-26, A-03 (HIGH) — this script was inert in CI as first wired.
# ci.yml runs a "Resolve dependencies" step (`cyrius deps`) BEFORE this one, so
# by the time we ran, the committed lock had already been overwritten by a
# fresh resolution. Snapshotting the working tree then compared a regeneration
# against another regeneration: identical by construction, always exit 0. A
# lock committed with a `path` override active — zero `commit` lines — passed
# cleanly. Verified: with the guard as written, a deliberately tampered lock
# was reported OK.
#
# Reading the baseline from `git show HEAD:cyrius.lock` makes the check
# independent of whatever earlier steps did to the file, so it cannot be
# defeated by reordering. Falls back to the working tree outside a git
# checkout (local runs from a tarball), where the ordering hazard does not
# apply because nothing has resolved yet.
if git rev-parse --git-dir >/dev/null 2>&1 && git cat-file -e HEAD:"$LOCK" 2>/dev/null; then
  git show HEAD:"$LOCK" > "$tmp/before"
  echo "lock-check: baseline = committed $LOCK (HEAD)"
else
  cp "$LOCK" "$tmp/before"
  echo "lock-check: baseline = working-tree $LOCK (not in a git checkout)" >&2
fi

if [[ "$RESOLVE" == "1" ]]; then
  cyrius deps >/dev/null 2>&1 || { echo "lock-check: 'cyrius deps' failed" >&2; exit 1; }
fi

# Split each side into its two parts, sorted. Sorting is the whole point: it is
# what makes this test the dependency graph rather than readdir order.
_commits() { grep '^commit' "$1" 2>/dev/null | sort || true; }
_hashes()  { grep -v '^commit' "$1" 2>/dev/null | sed '/^[[:space:]]*$/d' | sort || true; }

rc=0

if ! diff -u <(_commits "$tmp/before") <(_commits "$LOCK") > "$tmp/commit.diff"; then
  echo "::error::cyrius.lock: the dep PINS changed after re-resolving from tags." >&2
  echo "  A committed lock should already describe a tag-only resolution. The usual" >&2
  echo "  cause is a [deps.*] 'path = \"../<dep>\"' override left active when the lock" >&2
  echo "  was generated — it silently beats the tag. Re-resolve with the override" >&2
  echo "  commented out and recommit." >&2
  sed -n '1,40p' "$tmp/commit.diff" >&2
  rc=1
fi

if ! diff -u <(_hashes "$tmp/before") <(_hashes "$LOCK") > "$tmp/hash.diff"; then
  echo "::error::cyrius.lock: the resolved FILE SET changed after re-resolving from tags." >&2
  echo "  (Compared as a sorted set, so this is a real content change, not line order.)" >&2
  echo "  Re-run 'cyrius deps' locally and commit the result." >&2
  sed -n '1,40p' "$tmp/hash.diff" >&2
  rc=1
fi

if [[ "$rc" == "0" ]]; then
  echo "lock-check: OK — $(_commits "$LOCK" | wc -l) dep pin(s), $(_hashes "$LOCK" | wc -l) locked file(s), matching a clean tag resolution"
fi

exit "$rc"
