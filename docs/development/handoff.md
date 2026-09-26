# agnostic — Port Handoff

> **Start here.** This is the orientation document for picking up the Python → Cyrius port.
> It is deliberately short and links outward rather than restating.
> Last refreshed: **2026-08-23**, after M5 and the M6 viability gate. The toolchain
> and dependency facts in §2 and §6 were refreshed **2026-09-26**, at 0.1.3, and §5
> gained the store-lock rules at 0.1.4.

Read in this order:

| Document | What it answers |
|---|---|
| **this file** | Where the port is, how to build it correctly, what to do next |
| [`state.md`](state.md) | Live numbers — versions, surface area, dep set, gates |
| [`roadmap.md`](roadmap.md) | M0–M9 sequencing and per-milestone gates |
| [`../../CYRIUS-PORT-BRIEF.md`](../../CYRIUS-PORT-BRIEF.md) | Research snapshot (2026-08-19): language notes, dep stack, **§7 decisions — binding** |
| [`../../ORACLE-AUDIT.md`](../../ORACLE-AUDIT.md) | 86 verified defects in the Python oracle. §3 gated M2, §2.2 gated M3; **§3.15 is what M6's gate now measures** |
| [`../adr/`](../adr/) | Three ADRs: health/readiness split, daimon Tier 1 deferral, one store lock rather than a patra handle per worker |

---

## 1. Where the port is

**M0 through M5 are complete. M6 — the QA tool surface — has started, and is
blocked on one decision that has been deliberately deferred (§8).**

Agnostic runs crews, serves its own catalogue, persists definitions and outcomes
behind a tamper-evident audit chain, and **authenticates**. 37 source files,
~10.2k lines, 631 top-level definitions.
**24 test suites, 1,175 assertions, 0 failed.**

M5 landed identity end to end: users and API keys on patra, HS256 tokens, a
static role→permission table, tenancy with key-prefixing, the dispatch ladder's
auth rung, login-abuse controls, webhook signatures, `POST /api/v1/auth/login`
and a first-administrator bootstrap.

⚠ **Every security property in `src/auth/` is mutation-verified**, and the suites
are written so that removing a guard breaks a *named* assertion. Before trusting
a refactor of any of it, re-run those mutations — the list is in `state.md`. A
passing suite is not evidence on its own; several of these guards were confirmed
only by watching the test fail without them.

⚠ **`AGNOSTIC_AUTH` defaults to `off`**, because nothing can authenticate before
an operator has provisioned a user. What keeps that from being fail-open:
`agnostic_serve_mount` **refuses to start** with auth off on any bind but
loopback, and refuses to start with auth *required* when no users and no
bootstrap credential exist.

Version is **0.1.4** — see `CHANGELOG.md`. Per decision #4 the port's milestones
ship together as **1.0.0** (§4).

## 2. ⚠ Build it correctly, or you will write a lock CI cannot reproduce

This has bitten repeatedly and is the single most important operational fact here.

**The pin is `6.6.6`.** A `cyrius build`, `cyrius deps` or `cyrius lib sync` run
under a toolchain other than the pin rewrites `lib/` and `cyrius.lock` with content
CI — which installs the pin — cannot reproduce. CI has a fatal drift gate precisely
for this. Read `cyrius --version` before provisioning: it must print
`manifest-pin: 6.6.6` with **no** `drift` on the line.

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
per-write fsync by default, and single-writer. All three are in the M5 section of
the roadmap and they apply to M4's tables just as much.

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
- **`patra`'s `COL_STR` is a fixed 256-byte slot that truncates silently.** For an
  identifier that is a collision primitive, not a storage wart — `src/auth/store.cyr`
  refuses over-long emails at the door for exactly this reason.
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
- **Never pair a lock with `defer`.** cycc 6.6.6 skips a pending `defer` when the
  function returns through `return f(...)` — for any callee. A skipped unlock is a
  deadlock on the next caller. Filed upstream 2026-09-26 with a repro.
- **`CYRIUS_PKG_VERSION` resolves only in the entry file**, not in `include`d files — filed upstream
  (`2026-08-20-pkgver-not-visible-in-included-files.md`, open at 6.5.33). Workaround in place: read
  it in `main.cyr` and hand it to the module via a setter.

⚠ **Never modify the cyrius tree from a consumer repo.** File an issue or proposal instead. Two are
already filed from this port.

---

## 6. Cross-repo state

| Repo | Version | How it arrives |
|---|---|---|
| `agnosai` | **2.1.0** | direct, `git` + `tag` — **no `path`** |
| `bote` | **3.3.13** | direct pin, matching agnosai 2.1.0's |
| `majra` | **2.9.1** | direct pin, matching agnosai 2.1.0's |
| `ai-hwaccel` / `tyche` | **2.4.0** / **1.1.0** | direct pins, matching agnosai 2.1.0's |
| `libro` | **2.10.3** | transitive via bote — the audit chain |
| `kavach` | **3.13.1** | transitive via agnosai |
| `sigil` | **3.12.18** | folded into the 6.6.6 stdlib; also declared by agnosai, kavach, libro |
| `patra` | **1.14.3** | folded into the 6.6.6 stdlib; also declared by libro |

✅ **All nine carry a commit pin in `cyrius.lock`**, and every tag was confirmed on
the GitHub remote (API, not `gh`) before its pin moved. The agnosai 2.0.6 episode
this section used to describe — a tag pushed as a commit only, resolved from a
locally seeded cache — is closed. The check that caught it still applies to every
bump: a pushed *commit* is not a pushed *tag*.

### `[deps.agnosai]` has no `path`, deliberately

`path` beats `tag` when a checkout is present, so a local resolve silently vendors
the sibling's work-in-progress into `lib/` and the lock — content matching no tag,
which CI cannot fetch. Deleting it took the lock from **1** commit pin to **9**.
Do not add it back.

### ✅ No `[deps.patra]` hold at this pin

6.6.6 folds patra 1.14.3 (and sigil 3.12.18), which is what libro 2.10.3 declares,
so `lib/` matches the snapshot with **zero** files differing. The hold that agnosai 2.0.5 needed —
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
  bote-core, which 3.13.1 dropped. The one left is `uname_release` in
  `lib/sys.cyr` and `lib/sigil.cyr`, with identical bodies. All are `fn`, so they announce
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
