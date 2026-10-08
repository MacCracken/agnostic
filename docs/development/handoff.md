# agnostic — Port Handoff

> **Start here.** This is the orientation document for picking up the Python → Cyrius port.
> It is deliberately short and links outward rather than restating. §1 says where the port is
> and does not grow per release: what each release did is in [`CHANGELOG.md`](../../CHANGELOG.md),
> today's figures are in [`state.md`](state.md), and what comes next is in [`roadmap.md`](roadmap.md).
> §2–§8 are standing rules and the decisions behind them; each rule says when it was learned.

Read in this order:

| Document | What it answers |
|---|---|
| **this file** | Where the port is, how to build it correctly, what to do next |
| [`state.md`](state.md) | Live numbers — versions, surface area, dep set, gates |
| [`roadmap.md`](roadmap.md) | Open work through v1.0 (M6–M9), what waits on agnosai and other siblings, and the settled decisions |
| [`../../CYRIUS-PORT-BRIEF.md`](../../CYRIUS-PORT-BRIEF.md) | Research snapshot (2026-08-19): language notes, dep stack, **§7 decisions — binding** |
| [`../../ORACLE-AUDIT.md`](../../ORACLE-AUDIT.md) | 86 verified defects in the Python oracle. §3 gated M2, §2.2 gated M3; **§3.15 is what M6's gate now measures** |
| [`../adr/`](../adr/) | Nineteen ADRs: health/readiness split, daimon Tier 1 deferral, one store lock rather than a patra handle per worker, compiled-in WebGUI plugins, the plugin host bridge, loopback-Host and JSON-only writes, plugin requests checked by the server, crews that belong to their tenant, crew progress collected by the server, views that link through the shell with one bridge client, audit entries read from a bounded copy, a cancelled crew keeping its finished results, a crew a restart interrupted answering `interrupted`, the estimator's one-agent baseline as its own model, the HTTP API described by a generated schema, agent selection explained by recomputing it, selection hints on a task, and crews joining their request's trace with OTLP export, and an interrupted crew keeping what its finished tasks answered |

---

## 1. Where the port is

The version is the one in `VERSION`. Per decision #4 the milestones ship together as **1.0.0**
(§4); patch releases are tagged from `main` along the way, and `main` stays green.

| Milestone | Where it stands |
|---|---|
| **M0–M5** | Complete: scaffold, the HTTP skeleton, the crew surface on agnosai (in-process, `dist/agnosai.cyr`), agent definitions and presets, persistence on patra behind libro's tamper-evident audit chain, identity and tenancy. |
| **M6** — QA tools | Started and blocked. The viability gate is built (2 of 38 preset tool names resolve); what blocks it is the tool-registry decision (§8) and agnosai's tool-calling loop (F1). |
| **M7** — MCP and A2A | Not started; the target spec revisions are recorded in the roadmap. |
| **M8** — reports | Not started; HTML, CSV and JSON. Whether PDF joins 1.0 is the user's call. |
| **M9** — WebGUI | Built: the shell at `/ui`, a plugin platform the server enforces (ADRs 0004–0007, 0010), and the Crews, Library, Audit trail and Swarm Command views. Owed: streaming events, reports, the approval roll-up (agnosai F3). |

What a newcomer must not miss, wherever they start:

- ⚠ **Every security property in `src/auth/` is mutation-verified**, and the suites are written so
  that removing a guard breaks a *named* assertion. Re-run those mutations before trusting a
  refactor of any of it — the list is in `state.md`. Since 0.1.9 the same discipline holds for the
  plugin gate, crew tenancy and the transport rules, and every fix since names its mutation in the
  CHANGELOG.
- ⚠ **`AGNOSTIC_AUTH` defaults to `off`**, because nothing can authenticate before an operator has
  provisioned a user. `agnostic_serve_mount` refuses to start with auth off on any bind but
  loopback, and with auth *required* when no users and no bootstrap credential exist.
- ⚠ **One process per database file** — a second process would interrupt the first one's live
  crews at start-up (ADR 0013), so mount claims `<db>.owner` first and refuses if it is held
  (0.1.15, architecture 001).
- ⚠ **The HTTP API is described by a generated snapshot** (ADR 0015): CI fails when
  `docs/api/generated/schema.json` differs from what the binary prints, so an API change
  regenerates it (`scripts/gen-api-schema.sh`), and `scripts/check-skill.py` holds
  `skills/agnostic/SKILL.md` to it.
- **AgnosAI owns the engine tier.** A gap there is closed by releasing agnosai and re-pinning
  (§6), never by an override pin or a fork here; what agnostic waits on is the roadmap's
  "Waiting on agnosai".

## 2. ⚠ Build it correctly, or you will write a lock CI cannot reproduce

This has bitten repeatedly and is the single most important operational fact here.

**The pin is `6.6.14`.** A `cyrius build`, `cyrius deps` or `cyrius lib sync` run
under a toolchain other than the pin rewrites `lib/` and `cyrius.lock` with content
CI — which installs the pin — cannot reproduce. CI has a fatal drift gate precisely
for this. Read `cyrius --version` before provisioning: it must print
`manifest-pin: 6.6.14` with **no** `drift` on the line.

⚠ **Your editor may be building too.** The cyrius language server runs a build on save,
and a build re-provisions `lib/` and rewrites the lock (below). During 0.1.7 it did so
from a half-edited manifest. Treat `lib/` and `cyrius.lock` as scratch until a
deliberate `lib sync --full` + `deps` under the final manifest, then compare them with
the clean replica's.

### ✅ The wrapper pins the compiler now — the `CYRIUS_HOME` shim is retired

Through 6.5.41 a versioned wrapper resolved `cycc` through `$CYRIUS_HOME/bin` →
`~/.cyrius/current`, so `~/.cyrius/versions/<pin>/bin/cyrius` compiled with
whatever was current, and this section prescribed a `CYRIUS_HOME` shim. **Fixed
upstream at v6.5.42** (`2026-08-22-versioned-wrapper-does-not-pin-cycc.md`, now
archived), and the installed `cyrius` also re-execs the toolchain the manifest
pins. Verified 2026-09-26: with 6.6.6 current and this repo still pinned to 6.6.3,
`cyrius --version` answered 6.6.3 and `cyrius which` pointed into
`versions/6.6.3/`. So with the pin installed under `~/.cyrius/versions/`, plain
`cyrius` is enough — confirm with `cyrius which`.

### ⛔ Never read `~/.cyrius/versions/<V>/lib/` as ground truth

**This machine is cyrius's development environment**, so the toolchain moves under
you and install directories are rewritten in place mid-session. Reading one
produced a confidently wrong diagnosis during this port ("6.5.33 folds patra
1.13.10" — it does not) and a fix that was green locally and would have failed CI.

Check what a release actually ships with **`git show <tag>:lib/<mod>`** in
`~/Repos/cyrius`. Same rule for every sibling: hash the dist against
`git show <tag>:dist/<pkg>.cyr`.

Two corollaries that are easy to get wrong:

- **`cyrius build` is not read-only.** It re-resolves `[deps.*]` as a side effect —
  even for a throwaway probe outside `src/`. After any build you did not intend as
  a provisioning step, run `git status --short` and revert stray `lib/` +
  `cyrius.lock` churn.
- **Never bump a `[deps.X]` tag while the sibling tree is ahead of its tag**, and
  confirm the tag is actually **pushed** — via `curl` to the GitHub API, never
  `gh`. A pushed *commit* is not a pushed *tag*: see §6.

`cyrius deps --verify` is read-only and safe to run freely.

**Gates before handing anything back** — all under the pin:

```bash
sh scripts/check-clean.sh && sh scripts/check-symbols.sh && cyrius test
```

---

## 3. What M2–M5 established, and what M6 inherits

**M2's gate was `ORACLE-AUDIT.md` §3** — four defects, all designed out by
mechanism and each pinned by a suite: the vacuous-success demotion in
`outcome.cyr`, engine-assigned ids only, one task model, and the terminal latch
in `ledger.cyr`.

**M3's gate was §2.2** — fourteen fields dropped in translation. It grew a third
disposition in the doing, and that is the part worth carrying:

> A field is **FORWARDED** when the engine has a slot that acts on it, **REFUSED**
> with a 422 naming the missing capability when it does not, and **RETAINED** when
> Agnostic's own content carries it but the engine cannot use it — kept,
> round-tripped, and **named in `unforwarded`**. Three, all visible on the wire.
> There is no fourth.

⚠ **Two lessons generalise past their milestone:**

- **An empty result set is not success.** `all()` over an empty collection is
  vacuously true in Python, and `agnosai_crew_runner_run` makes the identical
  mistake in Cyrius. Assume any new aggregate has the same hole until you look.
- **An unspecified value must not acquire a concrete one.** M3 shipped a bug
  where `gpu_required` alone overwrote the engine's "no floor" sentinel with 0,
  putting a value on the wire the caller never sent. Found by live testing, not
  by the suite — the same class of defect as a dropped field, in the other
  direction.

**M4 was persistence and the audit chain** (complete), and two seams were built for it:

- `agnostic_definitions_*` — nine functions and one storage literal.
  `src/routes/definitions.cyr` touches the store only through them, so M4
  reimplements against `patra` and changes no handler. `"storage":"memory"`
  becomes `"patra"` and nothing else on the wire moves.
- `src/engine/ledger.cyr` — the same shape for crew outcomes, which are also
  memory-resident and capped today.

⚠ **Agent keys are `[a-z0-9][a-z0-9-]*`, at most 100 bytes, and that is
load-bearing for M4.** A key that cannot contain `/` or `.` makes an on-disk path
built from one safe **by construction** rather than by validation — which is the
cheap version of M4's "path-traversal validation on every externally-derived
path" bullet. Do not widen the character set.

⚠ **`patra` constraints to design around, not discover:** one index per table,
per-write fsync by default, and single-writer. The roadmap's M8 note on report storage
records all three, and they apply to M4's tables just as much.

### Carried forward, still open

- **Placeholder mode is indistinguishable from real work by results alone** —
  closed by disclosure (`engine_mode` on every crew response, a WARN at mount),
  not by type. Any new surface reporting crew output must disclose it too.
- ✅ **Route authentication — CLOSED by M5.** The dispatch ladder's auth rung is
  wired, `POST /api/v1/auth/login` issues the tokens it checks, and mount refuses
  to start unauthenticated on any bind but loopback. The one exemption is login
  itself, which cannot require a credential; a per-IP bucket and the Argon2 pool
  cap stand in front of it.
- ⏳ **§3.15 — now MEASURED, not yet closed.** `src/engine/tools.cyr` resolves the
  38-name manifest against the engine's registry: **2 resolve, 36 do not**, pinned
  by `tests/tools.tcyr`. A miss returns 0 and the caller refuses — never a
  silently smaller agent. Closing it is blocked on the registry-ownership decision
  in §8.

## 4. Settled — do not re-open

All six open decisions are closed. The record is `CYRIUS-PORT-BRIEF.md` §7.2, §7.2.1 and §7.3;
the roadmap carries each one against its milestone.

| | Decision |
|---|---|
| Identity | **Own it, thin** — adapt `secureyeoman/yeo-cy-test/src/auth.cyr`. kavach struck (zero identity surface) |
| Presets | **Agnostic's library is canonical** — the two sets share names and nothing else |
| PDF reports | **HTML + CSV + JSON only** in 1.0; wait for `bayan_pdf_*` |
| Release shape | **One release, total** — M1–M9 ship together as 1.0.0 |
| Daimon Tier 1 | **Deferred** — ADR 0002; it cannot be implemented as written |
| MCP transports | **Both shapes**, justified on merit; the 5–8 tool figure is a soft guideline, not a ceiling |

⚠ **Agnostic stands on its own** (§7.3). It is a product, not a frontend layer — SecureYeoman can
consume AgnosAI directly. This is a scope *reduction*. What it does not license is gratuitously
breaking SY: if SY is ever pointed at Agnostic, the answer is an additive compatibility shim built
then, against a real requirement. Out of scope for v1.0.

---

## 5. Cyrius footguns that have already cost time

**Added at 0.1.10:**

- **A plugin page never edits its own copy of the bridge client.** Edit `src/webgui/kit/host.js` and
  run `./scripts/gen-webgui.sh --sync-kit`; the generator refuses a copy that differs by a byte, and a
  page with `permissions` that carries none.
- **A sandboxed plugin cannot `confirm()`** — the shell's iframe has no `allow-modals`, so it answers
  false without asking. Ask inline (the Crews and Library views do). **Nor can it submit a form**: no
  `allow-forms`, so the `submit` event never fires — not even for `requestSubmit()`. Save on a click.
  Both pass every Node test; only a browser shows them.
- **A view re-rendered on every poll loses its reader's place** unless it keeps it: save and restore
  `scrollTop`, and remember which `<details>` were open (the Crews view keeps both).
- **sigil 3.13.6+ installs a crypto block only on a thread that has none**, so a test may not assert
  `_crypto_tls_inited == 1` after mount any more: `main` already gave the main thread a block, and
  sigil leaves it (the flag stays 0); where it installs one, the flag is 2. Assert "settled" — see
  `tests/serve_mount.tcyr`.
- **An `scp` of 200 MB to the Pi can drop mid-file.** Use `rsync -z --partial` and compare
  `sha256sum` on both ends before running anything; a truncated binary fails in confusing ways.
- **`pkill -f <name>` over `ssh` matches the remote shell's own command line** and kills the session
  (exit 255). Use `pgrep -a` to look, `timeout` to bound a server, and a distinct process name.

**Added at 0.1.9:**

- **A crew route must look its crew up IN SCOPE** — `agnostic_ledger_entry_in(key,
  agnostic_reqctx_scope(ctx))`, never `agnostic_ledger_entry(key)` — and answer another tenant's
  crew with the same 404 as an unknown one. A stored outcome is checked against its document's
  `scope` (absent = `_`). `tests/crew_tenancy.tcyr` holds every route to it.
- **The engine's result metadata is a Str-keyed MAP of bayan values, not a bayan object** — read it
  with `map_get`; only `tokens` inside it is an object. Reading it with `bayan_json_v_obj_get_by_str`
  answers nothing, silently.
- **Anything that walks the ledger on a timer must not allocate globally.** `map_keys` builds its
  vec with the global allocator; the collector walks the map's slots instead
  (`agnostic_ledger_live_entries_a`), and each sweep runs in an arena it rewinds. A per-sweep
  `alloc` is a leak at five sweeps a second, forever.
- **A long SQL literal may continue onto a second line** — the newline the `\`-continuation keeps is
  whitespace to patra's tokenizer. That is how a >120-character `CREATE TABLE` passes lint.
- **The plugin rung runs BEFORE authentication.** A plugin request outside its grants never
  authenticates; a test that expects 401 for one must not also send `X-Agnostic-Plugin`.
- **A route the router does not take for that method answers 405 before the plugin rung runs** —
  there is nothing to grant. A test of "granted path, ungranted method" needs a method that route has.
- **In the browser, the sandboxed plugin frame may be IN-process** (headless Chromium put it there
  at 0.1.9, though 0.1.8's notes say out-of-process): a CDP driver that waits only for an attached
  target never finds it. Find it through `Page.getFrameTree` and evaluate in its default execution
  context.
- **Cross-realm arrays fail `assert.deepEqual`** in the Node tests — an array made inside the page's
  `vm` context has that context's prototype. Compare lengths or fields.

**Added at 0.1.8:**

- **Every POST and PUT needs `Content-Type: application/json`** — 415 otherwise, even with
  no body — and with `AGNOSTIC_AUTH=off` the `Host` must be loopback (403 otherwise). A
  `curl` that worked at 0.1.7 may not now; add the header. (ADR 0006.) The rules apply to
  socket requests only, so the suites' direct ladder calls never see them —
  `tests/serve_mount.tcyr` exercises them through `agnostic_serve_handler` over a socketpair.
- **A route that reports a crew's status must refresh the ledger first**
  (`agnostic_crew_refresh_a`). The status it reads is the latch, which nothing updates on its
  own: `GET /crews/{id}/events` used to drain the bus only, and reported `pending` for a crew
  long finished to any client that polled events alone.
- **A plugin page has no network** (`connect-src 'none'`) **and no modal dialogs** (the
  sandbox lacks `allow-modals`, so `confirm()` returns false without asking). It asks the
  shell (ADR 0005), and draws its own dialogs.
- ~~**A new plugin permission is four edits**~~ — **one since 0.1.9**: `src/webgui/permissions.json`
  (and the tables in ADR 0005 and `guides/webgui-plugins.md`). The generator, the server and the
  shell all read that file.
- **Swarm Command's logic runs in Node.** Its page has no top-level DOM access, so its
  `<script>` evaluates in a `vm` context; the simulator, spec normalizer, estimator and crew
  request builder were tested that way at 0.1.8, and the whole flow in headless Chromium over
  CDP (sandboxed frames are out-of-process — attach with `Target.setAutoAttach`, flatten).

**Added at 0.1.7:**

- **A `[deps.X]` without `modules` did nothing — silently — before cyrius 6.6.13.** `cyrius
  deps` cloned a dep only when it listed `modules`, so a block with `git` + `tag` alone was never
  visited and a transitive declaration of the same name resolved instead. This repo's four
  "not optional" pre-pins were inert for their whole life. Filed upstream
  (`2026-10-01-git-dep-without-modules-silently-inert.md`) and fixed in 6.6.13 (I10): such a block
  now means `modules = ["dist/X.cyr"]` — and the root's tag wins — or `cyrius deps` warns by name.
  So it is an override pin, which this repo does not carry.
- **Root deps resolve first, then their own deps breadth-first in MANIFEST ORDER, and the
  first declaration of a name wins.** That is why `[deps.libro]` sits after
  `[deps.agnosai]`: whenever the two declare different sigils, agnosai's (the fold's) must be the
  one the lock records. At 0.1.11 both declare 3.13.7.
- **Embedding a page: a raw multi-line string literal, never `\`-continuations.** A
  continuation keeps the newline and `cyrius fmt` indents the next line, putting spaces
  inside the string — harmless between JSON tokens, a rewrite of an HTML page. Raw
  newlines inside a literal are legal, and since 6.6.6 a line in a string that starts
  `#ifdef` is data. `scripts/gen-webgui.sh` does this; `tests/webgui.tcyr` re-hashes it.
- **A line at column 0 starting `fn ` / `var ` / `enum ` inside an embedded page** would
  be read as a definition by `check-symbols.sh`, which scans `src/` line by line. The
  generator refuses such a page.
- **`check-lib-symbols.py` must evaluate `#ifdef`.** It now does, per shipped target;
  before 0.1.7 it read both arms as live.
- ✅ **The aarch64 binary starts again** (fixed upstream in cyrius 6.6.13, I9; verified at 0.1.10 on
  the Pi: all 29 suites and the server, natively). It died with SIGBUS from 0.1.7 to 0.1.9: a
  typed-array global (`var a: u8[N]`) was not padded, so the globals after sankoch's
  `u8[363]`/`u8[217]`/`u8[50]` were off by 6 and sigil's atomic init flags among them faulted.
  **Re-check on the Pi after every cyrius bump**: cross-build the server and each suite
  (`cyrius build --aarch64`), copy them (`rsync -z --partial`, then compare checksums), run natively.
  Still never size a byte array in agnostic's own globals to a non-multiple of 8.

**Added during M5/M6 — each of these cost a wrong turn:**

- **`secret` is a RESERVED KEYWORD** and cannot be a parameter name. The
  diagnostic attributes the error to the *previously included* file, which sends
  the search to the wrong module.
- **A compile error's file attribution is unreliable in general.** Shadowing
  `agnostic_serve_handler`'s `ctx` parameter was reported against
  `src/routes/crews.cyr`, at a column that line does not have. When a diagnostic
  names a file you did not touch, suspect the *next* included file instead.
- **enum members are compile-time constants; `var` globals are not.** A module may
  read an `AGNOSTIC_ROUTE_*` enum member from above its definition, but a `var`
  read from a module included earlier is **0**. `src/auth/perm.cyr` depends on the
  first half of that rule and says so.
- **Everything is `i64`, so changing what a parameter MEANS is invisible.**
  Turning `agnostic_route_dispatch_a`'s sixth argument from a `Str` header into a
  context struct kept every call site compiling; one test passed a `Str`, and the
  suite **crashed with no output at all** rather than failing an assertion. It
  showed up only as `22 passed, 1 failed` with 23 suites present.
- **A suite that crashes prints nothing.** Do not read a green-looking log as a
  pass — compare the suite *count* against `ls tests/*.tcyr | wc -l`.
- **`agnostic_response_json_a` takes the bayan OBJECT, not an encoded `Str`.**
  `_agnostic_serve_send` serialises it; handing it a `Str` double-encodes the
  response into a JSON string. A test that reads the body directly rather than
  through the send path will not notice.
- **`patra`'s `COL_STR` is a fixed 256-byte slot: 255 bytes and a NUL.** patra **refuses** a
  longer value (`PATRA_ERR_ROWSZ`) and writes nothing; it truncated silently until its own audit
  (2026-08-18 S2-8). So bound every `STR` you bind: refuse it at the door (`src/auth/store.cyr`
  does for emails), or cut it on a character when the column is never read. An unbounded one
  loses the whole row: until 0.1.13 a crew named over 255 bytes never stored its outcome
  (`_agnostic_crews_save_locked`).
- **Worker threads spawned via `lib/thread.cyr` inherit their TLS block through
  `CLONE_SETTLS` and must NOT call `patra_init` / `thread_local_init`.** That is
  what lets a sandhi pool worker touch a patra store at all.



- **One flat symbol namespace, last-definition-wins.** The compiler warns on a duplicate `fn` and is
  **silent** on a duplicate `var`. Every `check-symbols.sh` in the ecosystem scans `src/` only, so a
  `lib/`↔`lib/` collision between two dependencies is invisible to compiler and linter at once.
  This is not theoretical — see §6. `tests/deps_symbols.tcyr` now guards it here.
- **Enum qualifiers are cosmetic.** `Backend.WASM` and `KavachBackend.WASM` both resolve to the
  member `WASM`; the type name plays no part in resolution. Renaming an enum *type* does not protect
  its *members*.
- **No `free()`.** `lib/alloc.cyr` is a bump allocator with only `alloc_reset()`. Per-request arenas
  are mandatory, and only `sandhi_server_run_pooled` populates one — `run`, `run_opts`, `run_async`
  and `run_pooled_tls` do not, so every `_a` site needs a bare-form fallback.
- **Arena exhaustion returns 0, and a `Str` of 0 is indistinguishable from a valid one.** No option
  type, no error channel through the `_a` families. Constructors return 0 rather than a half-built
  record; callers must check. `ARENA_FULL_SPILL` is applied to sandhi's arena so an oversized
  response degrades instead of faulting.
- **sandhi accessors return NUL-terminated cstrings, not `Str`.** Passing one through unwrapped reads
  the pointer as a `Str` header and every downstream length is garbage.
- **sakshi takes `(pointer, length)`, and a miscount fails silently.** One too many puts the NUL
  terminator inside the message — an escaped NUL in JSON output; one too few truncates it. Neither
  is a compile error, a lint warning, nor a test failure, because the suites assert on handler
  behaviour rather than log text. Both shipped in one M2 commit.
  `scripts/check-log-lengths.py` now gates it, from `check-clean.sh`.
- **⚠ The compiler's line numbers for `src/` warnings are wrong.** Two pre-existing
  "assigning non-pointer to typed pointer" warnings in `src/http/router.cyr` were reported at lines
  44 and 56 before M2 and at 98 and 110 after — a shift of exactly the number of lines added
  *elsewhere* in the file. The columns stayed stable, so the diagnostic knows the site and
  mis-attributes the line. **Do not chase a `src/` warning by line number**; find it by column and
  construct. Worth filing upstream — and never patch the cyrius tree from a consumer repo.
- **Two AgnosAI behaviours bite only the async path.** A cyclic DAG submitted through `submit_crew`
  leaves the crew reporting `pending` **forever** — the error return is discarded on the submit
  thread and the registry keeps the PENDING entry `_agnosai_orch_register` seeded — and
  `_agnosai_orch_evict_locked` drops **every** finished crew once the registry holds 1000, so a
  completed crew can 404. Both are worked around in `src/engine/`, not upstream; read those module
  headers before changing either.
- **A Cyrius line continuation KEEPS the newline.** `"abc\<newline>def"` is 7
  bytes, not 6 — verified with a probe. So a generated string literal must never
  break inside a JSON string: the newline would be spliced into the value, and a
  raw newline inside a JSON string is illegal JSON. There is no C-style
  adjacent-literal concatenation to split with either, and `#skip-lint` is scoped
  to a **line**, so it cannot be placed on an offending line that sits inside a
  literal. `scripts/gen-presets.sh` breaks only between JSON tokens for this
  reason, and `check-clean.sh` skips lint for files marked `GENERATED FILE`.
- **`src/app.cyr` holds the include order; add new modules there.** Every suite
  reaching the router includes it. Putting the order in `main.cyr` meant a new
  route module broke all of them with "undefined function" — three times before
  the file existed. And a key used by two modules belongs in
  `src/http/status.cyr`, which is included first: a top-level `var` initialiser
  reading a global declared later silently evaluates to 0.
- **The store handle is only handed out under the store lock** (0.1.4).
  `agnostic_store_db()` returns 0 to a thread that has not called
  `agnostic_store_lock()`, so a new store function that forgets the lock fails its
  suite rather than racing in production. Follow the wrapper shape — `lock; var r =
  _x_locked(...); unlock; return r;` — and never hold the lock across Argon2 or an
  engine call. `scripts/check-store-lock.py` enforces the shape; ADR 0003 says why.
- **`str_new` / `str_new_a` / `str_from` BORROW — they never copy.** Only the
  16-byte header is allocated. Wrapping a `patra_result_get_str` pointer that way
  and keeping it past `patra_result_free` shipped twice (fixed 0.1.5): a segfault
  when a large result was unmapped, and — worse — a principal's tenant silently
  reading another user's bytes when a small one was recycled. Copy with
  `str_from_buf`, or `alloc_via` + `memcpy`; `check-store-lock.py` rule 3 checks it.
- **`thread_local_init` is not idempotent, and lazy library init runs on whatever
  thread gets there first.** Each call installs a new zeroed TLS block. sigil's
  first `cbank()` calls it — so the first hash, if it happened on a pool worker,
  replaced that worker's block and sandhi's arena slot with it (fixed 0.1.5 by
  `agnostic_crypto_main_init()` first thing in mount). Anything with a lazy
  per-process init belongs on the main thread, before `run_pooled`.
- ✅ ~~**Never pair a lock with `defer`.**~~ cycc 6.6.6 skipped a pending `defer` when the
  function returned through `return f(...)`, so a deferred unlock was a deadlock on the next
  caller. Fixed in cyrius 6.6.7; `rlock/ownership` pins the fix at the pin (0.1.15). The store
  wrappers keep their explicit shape because `check-store-lock.py` reads it.
- **`CYRIUS_PKG_VERSION` resolves in the entry file and one include deep, not two** — 6.5.34
  fixed the first level only. `src/routes/health.cyr` is two deep (via `src/app.cyr`), so the
  work-around stays: `main.cyr` reads it and hands it to the module through a setter. Filed
  2026-10-07 (`2026-10-07-pkgver-not-visible-in-nested-includes.md`, measured at 6.6.14–6.7.3).
  ⚠ A comment naming the constant in a file one include deep keeps the declaration, so a probe
  can pass by accident: `tests/health.tcyr` compiles either way.

⚠ **Never modify the cyrius tree from a consumer repo.** File an issue or proposal instead. Two are
already filed from this port.

---

## 6. Cross-repo state

| Repo | Version | How it arrives |
|---|---|---|
| `agnosai` | **2.1.6** | direct, `git` + `tag` + `modules` — **no `path`**; pins everything below at its latest |
| `libro` | **2.10.6** | direct since 0.1.7 (`modules`, after agnosai) — the audit chain |
| `bote` / `majra` | **3.3.16** / **2.9.2** | transitive via agnosai 2.1.6 |
| `ai-hwaccel` / `tyche` / `kavach` | **2.4.1** / **1.1.0** / **3.13.2** | transitive via agnosai 2.1.6 |
| `sigil` | **3.13.7** | folded into the 6.6.14 stdlib; agnosai and libro declare the same 3.13.7 |
| `patra` | **1.15.1** | folded into the 6.6.14 stdlib; libro declares the same version |

✅ **All nine carry a commit pin in `cyrius.lock`**, and every tag was confirmed on
the GitHub remote (API, not `gh`) before its pin moved. The agnosai 2.0.6 episode
this section used to describe — a tag pushed as a commit only, resolved from a
locally seeded cache — is closed. The check that caught it still applies to every
bump: a pushed *commit* is not a pushed *tag*.

⚠ **To move a dep agnosai owns, release agnosai** — as 2.1.2 did for bote and majra, 2.1.3
for bote 3.3.16 (which brought libro 2.10.6), and 2.1.4 for kavach 3.13.2 and ai-hwaccel 2.4.1.
2.1.5 and 2.1.6 moved none (their locks are 2.1.4's byte for byte). The next move is cyrius 6.6.15's chain
(roadmap, "Moving the cyrius pin to 6.6.15").
A root block "ahead of" agnosai works only if it lists `modules` (§5), and it then has
to be kept in step by hand; the four that existed through 0.1.6 never took effect.

### `[deps.agnosai]` has no `path`, deliberately

`path` beats `tag` when a checkout is present, so a local resolve silently vendors
the sibling's work-in-progress into `lib/` and the lock — content matching no tag,
which CI cannot fetch. Deleting it took the lock from **1** commit pin to **9**.
Do not add it back.

### ✅ No `[deps.patra]` hold at this pin

6.6.14 folds patra 1.15.1 and sigil 3.13.7, and since 0.1.11 the deps declare exactly those:
libro 2.10.6 declares patra 1.15.1 and sigil 3.13.7, and agnosai 2.1.6 declares sigil 3.13.7 (so,
since 0.1.12, does kavach 3.13.2).
`cyrius deps` refuses to overwrite a folded leaf ("refusing to overwrite stdlib leaf"), so
`lib/sigil.cyr` and `lib/patra.cyr` are the fold's bytes and `lib/` matches the snapshot with
**zero** files differing — and the lock's sigil and patra lines now name those same versions. At
0.1.10 the sigil line named agnosai 2.1.2's 3.13.5. The hold that agnosai 2.0.5 needed —
because no published Cyrius folded 1.13.10 at the time — is **not** reintroduced
here and must not be. The general rule: taking a patra version through a transitive
`[deps.patra]` obliges a Cyrius pin that folds the same version; the two are one
change.

### Owed, not blocking

- **`yantra`** — needs `Page.captureScreenshot` on its CDP surface before **M6**'s
  browser-automation tools. Not started.
- **`bayan`** — a `bayan_pdf_*` request should be filed before **M8** reports.
- ✅ **`kavach` `STDIN` — CLOSED at 0.1.3.** `InjectionMethod.STDIN` collided with
  `io.cyr`'s `var STDIN = 0` and collapsed onto `ENV_VAR`. kavach 3.12.9 prefixed
  the members (`KAVACH_INJECT_*`), that fix arrived here with 3.13.1, and the
  allow-list line in `scripts/lib-symbol-allow.txt` is deleted — the file is empty.
- **Duplicate-`fn` warnings: 19 → 1 at 0.1.3** (measured; the "20" once recorded
  here included libro ↔ majra `_sub_new`, which was already gone by 0.1.2). All 19
  were kavach's: the `syserr_*` / `agnosys_*` copies it shared with sigil and
  bote-core, which 3.13.1 dropped. The one left was `uname_release` in
  `lib/sys.cyr` and `lib/sigil.cyr`, with identical bodies; sigil 3.13.x no longer defines it,
  and the 0.1.12 build prints no `duplicate fn` at all. All are `fn`, so they announce
  themselves — unlike the `var` case, which does not. `scripts/check-lib-symbols.py`
  (Rule 4 of `check-symbols.sh`) is what catches the silent kind.

---

## 7. Two counting corrections worth carrying

- **`cyrius test`'s final `N passed, 0 failed` line is the *suite* tally, not a suite.** Summing it
  with the per-suite lines inflates the total. M1 is **215 assertions across 7 suites**, not 222;
  agnosai is **98 suites / 7,940 assertions**, not 99 / 8,038. The wrong agnosai figure is in that
  repo's `state.md`, which is already tagged.
- **The oracle is a behavioural reference, not a specification.** 203 Python files at
  `python-port/`, 86 verified defects. Its identity surface in particular is mostly dead code — no
  `password_hash` writer, no user CRUD, no role assignment beyond a hardcoded `VIEWER` — and **none
  of that appears among the 85**. Anything reading it for an identity spec is reading machinery that
  never ran.

---

## 8. ⛔ The decision M6 is waiting on: who owns the tool registry

**Deferred deliberately. Do not guess at it — settle it first.**

`src/engine/tools.cyr` resolves the preset tool vocabulary against the engine's
registry and reports the gap: **2 of 38 resolve; 36 do not**, both pinned by
`tests/tools.tcyr`. M6 is finished when the unresolved count reaches 0.

What is *not* settled is where agnostic's QA tools would register.
`agnostic_engine_init` exposes **no registry handle** — the orchestrator owns one
internally — so there is currently nowhere to put a QA tool that the
orchestrator's agents would actually read. The gate is therefore a library
question, not a served one, and is not wired into mount.

**Implementing tools before settling this means writing 36 of them against a seam
that may not exist.** The options, none chosen:

1. Agnostic stands up its own registry and hands it to the orchestrator.
2. AgnosAI grows a registration entry point agnostic calls at mount.
3. Tools are resolved at crew-build time rather than registered at all.

Two things that are already decided and should not be re-opened:

- ⛔ **No case transform from `LoadTestingTool` to `load_testing`.** It works for
  that name and resolves to nothing for `RiskScoringTool`, making the two
  indistinguishable — it books coverage for 38 and fails at call time for 36.
  The alias table is explicit so that an entry *means* something can run.
- ⛔ **A miss returns 0 and the caller refuses.** That is the direct answer to
  `ORACLE-AUDIT.md` §3.15, where the defect was not the empty registry but that a
  miss silently produced an agent with `tools=[]`. No best-effort path.

`ArtifactManagementTool` and `CIPipelineIntegrationTool` are named by
`quality-large.json` and have no implementation anywhere — unlike the other 36,
which at least had a class in the oracle. The roadmap requires them written or
struck. Worth knowing: `CIPipelineIntegrationTool` has plausible backing already
in agnosai's `delta_trigger_pipeline` / `delta_get_pipeline` / `delta_list_repos`,
but it would be a composite, so it is implementation work rather than an alias.

---
