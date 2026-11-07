# 0039 — A file in the binary is an `[embed]` entry, and a page's policy comes from the page

**Status**: Accepted
**Date**: 2026-11-06

## Context

Cyrius had no way to put a file in a binary, so two scripts turned files into source: `gen-presets.sh` made
`src/presets_data.cyr` from the 18 preset documents, and `gen-webgui.sh` made `src/webgui_data.cyr` from the six pages,
the manifests and the permission vocabulary. 13,277 of the 37,312 lines under `src/` were those two files. They were
committed, so that a clone builds, and `check-clean.sh` ran each script's `--check`, so that they could not fall behind.
`check-clean.sh` also skipped lint for them, and a page could not carry a line that looked like a definition at
column 0, because `check-symbols.sh` read it as one.

Since 6.6.19 `cyrius.cyml` can name a file under `[embed]`, and every compile then has `NAME()` and `NAME_len()`. The
file is read at build time, bytes exact, and nothing is generated.

`gen-webgui.sh` did a second job that `[embed]` does not: it hashed each page's inline scripts for the page's
Content-Security-Policy, which admits scripts by SHA-256 and nothing else. It also held every rule about what a page and
a manifest may say.

## Decision

**Every file in the binary is an entry in `[embed]`, and no generated source remains.** 30 entries: 18 presets, 6
pages, 5 manifests and the permission vocabulary. `src/webgui/assets.cyr` and `src/engine/presets.cyr` hold the chains
that turn an index into a file, in the order the API lists them.

**A page's script hashes are worked out at mount, from the bytes that are served.** A hash and its page are one fact,
and a stale hash is a view that opens blank, so nothing stores one. `agnostic_webgui_csp` reads the page as a browser
does where that matters, and a page with a script that never closes has no honest policy and refuses the start.

**The rules move to one gate, `scripts/check-embedded.py`,** which `check-clean.sh` runs. A compiler cannot know that a
new preset was left out of the table, or that a page would be blocked by its own policy. The gate checks the table
against the tree both ways, the chains against the table, each manifest, the vocabulary, the page rules and each page's
copy of the bridge client, and `--sync-kit` stays the way to rewrite those copies.

## Consequences

- **Positive** — A file edited without a rebuild cannot ship stale, because the build reads it. 13,277 lines of
  generated source go, and with them the lint exemption, the column-0 rule and a check whose job was to keep a copy
  honest. A page cannot disagree with its policy.
- **Positive** — The policy is now tested from two sides that share nothing: fixtures whose digests Python computed in
  `tests/webgui.tcyr`, and `scripts/boot-probe.sh`, which takes each served page's hashes again over the socket.
- **Negative** — A start pays for hashing, once, before a worker exists: from start to listening, x86_64 goes 61 → 65 ms
  and a Raspberry Pi 4 about 240 → 530 ms. On the Pi nearly all of that is SHA-256 itself, which sigil runs in software
  there at about 2.2 MB/s. A server starts rarely, and the roadmap holds that rate as owed by sigil.
- **Negative** — A new file has three places to be: the table, its arm in a chain, and the count. The gate refuses a
  file left out of any of them, which is the price of explicit entries: `[embed]` takes no glob.
- **Negative** — Every compile carries every embed, even under dead-code elimination, so a suite that held no page
  compiles about 0.65 s longer and is about 700 KB larger, some 27 s across the 42 suites. The string pool is 2 MiB and
  shared with the program's literals, and these files take about 760 KB of it. The generated literals sat in the same
  pool, so this is no new limit.
- **Neutral** — A browser reads more than `agnostic_webgui_csp` does: a `>` in a quoted attribute of a script tag, a
  `<!--` inside a script. Only these six pages reach it, and a hash that came out wrong fails closed, as a blocked
  script, which `boot-probe.sh` and the browser suites see.

## Alternatives considered

- **Keep `gen-webgui.sh`'s CSP half, generating a smaller file of hashes.** The roadmap's first plan. It leaves one
  generated source, one `--check` and one way for a page and its hashes to differ, to save a third of a second at a
  Pi's start and 4 ms elsewhere.
- **Compute the hashes at build time.** `[embed]` runs nothing, and a build step would be a generator again.
- **Compute the policy per request.** It would cost every page view, for nothing a mount does not do once.
- **Parse HTML properly.** The pages are ours, the gate bounds them, and an error fails closed. A parser would be more
  code to get wrong than the six pages call for.
- **Rules in `tests/`.** `check-clean.sh` already answered what a page may hold, before a compile, with every fault
  listed at once. A suite stops at a compile that a broken table has already refused.
