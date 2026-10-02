#!/usr/bin/env bash
# The cleanliness gate: fmt, lint, doc, vet, deny, deps --verify, generated sources.
#
# CLAUDE.md's work loop runs these at steps 2 and 6, but until 2026-07-31 CI ran
# none of them — only the symbol check, build, and test. The drift that caused
# was not hypothetical: `cyrius doc --check` had accumulated **31 undocumented
# public symbols** across five modules, and `cyrius lint` four untracked
# deferrals, none of which any pipeline would ever have reported.
#
# `cyrius fmt`, `cyrius lint` and `cyrius doc` all take a FILE. Written bare they
# print usage and exit 1 — which a gate that only checks the exit code reads as
# a failure, and a gate that ignores it reads as a pass over zero files. Both
# are wrong, so this loops explicitly.
set -uo pipefail

fail=0
note() { printf '  %s\n' "$1"; }

# --- fmt: src/ AND tests/ ------------------------------------------------
# Test files are covered deliberately. CLAUDE.md calls this out because a
# `src/`-only sweep is the easy mistake, and `.tcyr` files are two-fifths of the
# tree by count.
#
# `benches/*.bcyr` are covered too, added 2026-08-10. They were in neither this
# loop nor CI, and three of the six had rotted into hard compile errors against a
# src/ that moved under them — 50 of 79 benchmarks silently not running. fmt and
# lint below would not have caught that (only compiling does, which is now a CI
# step), but leaving benches/ out of the sweep entirely is what let it go unseen.
n=0
for f in $(find src -name "*.cyr" | sort) $(find tests -name "*.tcyr" | sort) \
         $(find benches -name "*.bcyr" | sort) \
         $(find examples -name "*.cyr" 2>/dev/null | sort); do
    [ -e "$f" ] || continue
    n=$((n + 1))
    if ! cyrius fmt "$f" --check >/dev/null 2>&1; then
        note "fmt: $f"
        fail=1
    fi
done
echo "fmt: $n files"

# --- lint: warnings and untracked deferrals ------------------------------
# A deferral comment ("deferred", "not yet", "TODO") must cross-reference a
# CHANGELOG, issue, or roadmap entry on the SAME line, or carry `#skip-lint`.
# The rule is what keeps a deferral from quietly becoming permanent.
#
# ⚠ **Files carrying the `GENERATED FILE` marker are skipped, and only here.**
# `src/presets_data.cyr` embeds the 18 preset documents as Cyrius string
# literals, and some of its lines exceed 120 characters unavoidably:
#
#   * a single JSON atom — a `backstory` — is up to 442 characters, and the
#     wrapper must not split inside one, because a Cyrius line continuation
#     KEEPS the newline (verified: `"abc\<newline>def"` is 7 bytes, not 6) and a
#     raw newline inside a JSON string is illegal JSON;
#   * Cyrius has no C-style adjacent-literal concatenation to split it with;
#   * and `#skip-lint` is scoped to a LINE, so it cannot be placed on an
#     offending line that sits inside a string literal.
#
# The line length is a property of the documents, not of anyone's style, and the
# file says "Do not edit by hand" at the top. It is still covered by `fmt`, by
# `doc`, by the compiler, by `gen-presets.sh --check` against its source JSON,
# and by `tests/presets.tcyr` — this exemption is one rule, not the gate.
n=0
skipped=0
for f in $(find src -name "*.cyr" | sort) $(find benches -name "*.bcyr" | sort) \
         $(find examples -name "*.cyr" 2>/dev/null | sort); do
    [ -e "$f" ] || continue
    if head -5 "$f" | grep -q 'GENERATED FILE'; then
        skipped=$((skipped + 1))
        continue
    fi
    n=$((n + 1))
    out=$(cyrius lint "$f" 2>&1)
    d=$(printf '%s' "$out" | grep -oE '^[0-9]+ untracked' | grep -oE '^[0-9]+' || echo 0)
    w=$(printf '%s' "$out" | grep -oE '^[0-9]+ warnings' | grep -oE '^[0-9]+' || echo 0)
    if [ "${d:-0}" != "0" ] || [ "${w:-0}" != "0" ]; then
        note "lint: $f — ${d:-0} untracked deferral(s), ${w:-0} warning(s)"
        printf '%s\n' "$out" | grep -E 'deferral line|warning' | sed 's/^/      /'
        fail=1
    fi
done
echo "lint: $n files ($skipped generated, skipped — see the note above)"

# --- doc: every public symbol documented ---------------------------------
# examples/ too — an example whose functions are undocumented is a worse example
# than one that does not exist, since it is read more than it is run.
n=0
for f in $(find src -name "*.cyr" | sort) \
         $(find examples -name "*.cyr" 2>/dev/null | sort); do
    [ -e "$f" ] || continue
    n=$((n + 1))
    if ! out=$(cyrius doc --check "$f" 2>&1); then
        note "doc: $f"
        printf '%s\n' "$out" | grep 'undocumented:' | sed 's/^/      /'
        fail=1
    fi
done
echo "doc: $n files"

# --- doctest: the `# >>>` blocks actually run ----------------------------
# Added 2026-08-10. `cyrius doctest` EXISTS — an earlier claim in this tree that
# "Cyrius has no doctest runner" was wrong, and nothing was running the one
# doctest the port has. It takes a single FILE and has no sweep, so this loops.
#
# Only files that contain a `# >>>` block are worth invoking it on: on a file
# with none it reports "0 passed, 0 failed" and exits 0, so a blanket sweep is
# just slow rather than wrong.
n=0
for f in $(grep -rl '^# >>>' src examples 2>/dev/null | sort); do
    n=$((n + 1))
    if ! out=$(cyrius doctest "$f" 2>&1) || ! printf '%s' "$out" | grep -q ', 0 failed'; then
        note "doctest: $f"
        printf '%s\n' "$out" | tail -3 | sed 's/^/      /'
        fail=1
    fi
done
echo "doctest: $n files"

# --- log lengths: the declared byte count matches the literal -------------
# Added at M2, after two miscounts shipped in one commit: one appended the NUL
# terminator to a JSON log message, the other truncated a message by a
# character. sakshi takes (pointer, length) pairs, so the count is hand-written
# at every call site and NOTHING else checks it — not the compiler, not lint,
# and not the suites, which assert on handler behaviour rather than log text.
#
# Mutation-verified: changing any declared length by one makes this print the
# site and exit 1.
if ! out=$(python3 scripts/check-log-lengths.py 2>&1); then
    note "log lengths: a declared length does not match its literal"
    printf '%s\n' "$out" | sed 's/^/      /'
    fail=1
else
    printf '%s\n' "$out"
fi

# --- store lock: the shared patra handle is only reachable under it --------
# Added at 0.1.4. Every pool worker shares one patra handle, and patra's read
# path takes no lock, so concurrent statements on it race patra's header buffer
# and file offset — on the 0.1.3 code, eight threads doing only the per-request
# user lookup killed the process with SIGBUS on every run. `agnostic_store_db()`
# refuses the handle to a thread without the store lock at RUN time; this is the
# same rule checked statically, for the paths no suite reaches.
#
# Mutation-verified: a wrapper that drops its `agnostic_store_lock()`, a body that
# fetches the handle without the lock or the `_locked` name, and a direct use of
# the raw global each fail with the site named; on the 0.1.3 tree it reports 46.
#
# Rule 3 (0.1.5): no patra result string is wrapped in a BORROWING Str
# (`str_new` and friends keep the pointer; the result set is freed under it).
# Both 0.1.4 instances — the definitions listing and `_agnostic_auth_str_a` — fail
# it by name when restored.
if ! out=$(python3 scripts/check-store-lock.py 2>&1); then
    note "store lock: the shared patra handle is reachable without the store lock"
    printf '%s\n' "$out" | sed 's/^/      /'
    fail=1
else
    printf '%s\n' "$out"
fi

# --- vet + deny: the dependency gates ------------------------------------
if ! cyrius vet src/main.cyr >/dev/null 2>&1; then
    note "vet: src/main.cyr"
    fail=1
fi
if ! cyrius deny src/main.cyr >/dev/null 2>&1; then
    note "deny: src/main.cyr"
    fail=1
fi
echo "vet + deny: ok"

# --- deps --verify: cyrius.lock describes the lib/ actually on disk ------
# Added 2026-08-03 after finding lib/kavach.cyr was 3.11.0 while cyrius.lock
# recorded 3.9.3's sha256 and cyrius.cyml pinned `tag = "3.9.3"`. Nothing
# reported it: every other gate reads src/, and the build happily compiles
# whatever bytes lib/ holds.
#
# The mechanism is that each [deps.NAME] carries `path = "../NAME"` alongside
# `git`/`tag`, and the local path WINS. So a developer whose sibling checkout
# has moved ahead builds against a version the manifest does not name, while CI
# — which has no sibling checkouts — resolves the tag and builds something
# else. Here that was kavach 3.11.0 locally against 3.9.3 in CI.
#
# Mutation-verified: restoring the stale 3.9.3 hash makes this print
# `FAIL: lib/kavach.cyr (hash mismatch)` and exit 1.
# No git deps yet → no cyrius.lock, and that is the documented default:
# first-party-standards.md:135 — "No lockfile by default — zero transitive deps.
# Optional `cyrius.lock` pins git-dep hashes when present." Verifying an absent
# lock reports a failure for a conforming state, so skip until a [deps.NAME]
# block exists. This becomes live the moment agnosai/majra/bote are declared.
if [ ! -f cyrius.lock ]; then
    if grep -qE '^\[deps\.[a-z0-9_-]+\]' cyrius.cyml; then
        note "deps --verify: cyrius.cyml declares git deps but no cyrius.lock — run 'cyrius deps'"
        fail=1
    else
        echo "deps --verify: skipped (no git deps declared, no lockfile expected)"
    fi
elif ! out=$(cyrius deps --verify 2>&1); then
    note "deps --verify: cyrius.lock does not match lib/"
    printf '%s\n' "$out" | grep -E 'FAIL|failed' | sed 's/^/      /'
    fail=1
fi
if [ -f cyrius.lock ]; then
    echo "deps --verify: $(printf '%s' "$out" | grep -oE '^[0-9]+ verified' || echo 'ok')"
fi

# --- lib/ actually matches the pinned toolchain snapshot -----------------
# Added 2026-08-03. This is NOT redundant with `deps --verify` above, and the
# difference is the whole reason it exists:
#
#   * `deps --verify` compares cyrius.lock against lib/ on disk. The lock is
#     WRITTEN FROM disk, so it can only catch a lock that has gone stale — never
#     a lib/ that has.
#   * This compares lib/ against ~/.cyrius/versions/<pin>/lib, i.e. against what
#     the pin actually says the stdlib is.
#
# Proven necessary the day it was added: after `cyrius lib sync --full` +
# `cyrius deps` for the 6.5.6 bump, `lib/vani.cyr` was still 1.1.2 against the
# snapshot's 1.1.3 — and `deps --verify` reported "105 verified, 0 failed",
# because the lock had been regenerated from the stale file.
#
# Root cause, confirmed by controlled mutation: **`cyrius lib sync` skips on
# file SIZE, not content.** A same-size edit survives `--full` (a one-character
# swap is not restored); a size-changing edit is synced. A version-comment bump
# like `1.1.2` -> `1.1.3` is exactly size-neutral, so a patch release whose only
# change is the stamp never lands. Filed upstream.
# **Recursive**, and that is not cosmetic. `cyrius lib sync` copies only the
# top level, so the snapshot's `unicode/` subdirectory never lands — and since
# `src/sandbox/oci.cyr` began calling `unicode_category` for oracle-exact
# `is_alphanumeric`, those files are load-bearing and vendored BY HAND. Nothing
# upstream will keep them current, so this gate is the only thing that notices
# when they go stale.
_snap="$HOME/.cyrius/versions/$(grep '^cyrius = ' cyrius.cyml | sed 's/.*"\(.*\)"/\1/')/lib"
if [ -d "$_snap" ]; then
    # **No file is allowed to differ.** An allowance for `sakshi.cyr` lived here
    # from 2026-08-05 to 2026-08-07 and is gone: the tree built 2.4.7 while the
    # pin shipped 2.4.8, silently reverting the `i64::MIN` decimal fix.
    #
    # The cause was **not** the siblings' vendored `lib/`, which is what the old
    # comment here claimed. sigil and bote declare `[deps.sakshi]` in their own
    # manifests at an older tag, and `cyrius deps` overlays that transitive
    # resolution on top of the `lib sync --full` snapshot — on every `cyrius
    # build`, since build performs an implicit resolve. Bumping those tags fixed
    # it; agnostic now also pins `[deps.sakshi]` itself so a lagging sibling
    # cannot reintroduce it. See the comment on that pin in `cyrius.cyml`.
    #
    # ⚠ This gate is the **only** thing that catches the class. `deps --verify`
    # cannot: the lock is written *from disk*, so a downgraded file just gets its
    # downgraded hash recorded and the check reports success.
    n=0
    for f in $(cd "$_snap" && find . -name '*.cyr' | sed 's|^\./||' | sort); do
        [ -e "lib/$f" ] || { note "lib: $f missing from lib/"; fail=1; continue; }
        if ! cmp -s "lib/$f" "$_snap/$f"; then
            note "lib: $f differs from the $(basename "$(dirname "$_snap")") snapshot"
            fail=1
        fi
        n=$((n + 1))
    done
    echo "lib snapshot: $n files"
else
    note "lib snapshot: $_snap not found — cannot verify lib/ against the pin"
    fail=1
fi

# --- generated sources match their inputs --------------------------------
# `src/presets_data.cyr` is generated from `src/presets/*.json`, because Cyrius
# has no `include_str!` and `include` takes a path to *source*. The generated
# file is committed so a clone builds without running the generator — and this is
# what keeps that copy honest. Edit a preset, forget to regenerate, and the gate
# says so instead of the binary shipping stale documents.
#
# Mutation-verified: bumping a `version` in any preset makes this fail with the
# diff, and restoring it passes.
if ! out=$(./scripts/gen-presets.sh --check 2>&1); then
    note "gen-presets: src/presets_data.cyr is stale — run ./scripts/gen-presets.sh"
    printf '%s\n' "$out" | head -20 | sed 's/^/      /'
    fail=1
else
    printf '%s\n' "$out"
fi

# The same for the WebGUI (0.1.7): `src/webgui_data.cyr` is generated from the pages
# and plugin manifests under `src/webgui/`. This check also re-runs the generator's
# page rules — a page that loads an external resource or carries an inline handler
# its CSP would block fails HERE, not blank in a browser. Mutation-verified: one
# changed byte in a page makes this fail with the diff.
if ! out=$(./scripts/gen-webgui.sh --check 2>&1); then
    note "gen-webgui: src/webgui_data.cyr is stale or a page breaks a rule — run ./scripts/gen-webgui.sh"
    printf '%s\n' "$out" | head -20 | sed 's/^/      /'
    fail=1
else
    printf '%s\n' "$out"
fi

# --- the WebGUI's JavaScript (0.1.9) ---------------------------------------
# The shell's host-bridge gate and each plugin's logic run under Node, against the pages'
# own bytes (`tests/webgui/`). Until 0.1.9 that logic was tested once, by hand, and the
# tests discarded; `cyrius test` cannot reach it. Node is a test-time dependency only.
# Mutation-verified: making the gate grant a route outside a plugin's permissions, or
# binding a live crew's tasks by position instead of by id, fails a named test.
if ! out=$(./scripts/check-webgui-js.sh 2>&1); then
    note "webgui js: tests/webgui/ failed"
    printf '%s\n' "$out" | head -30 | sed 's/^/      /'
    fail=1
else
    printf '%s\n' "$out"
fi

if [ "$fail" -ne 0 ]; then
    echo "cleanliness check FAILED"
    exit 1
fi
echo "cleanliness check OK — fmt, lint, doc, log lengths, store lock, vet, deny, deps --verify, lib snapshot, generated sources, webgui js all clean"
