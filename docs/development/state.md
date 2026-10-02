# agnostic — Current State

> Refreshed every release. CLAUDE.md is preferences/process/procedures
> (durable); this file is **state** (volatile).
> Last refreshed: 2026-10-02, at **0.1.9** — plugin requests **checked by the server** against one
> permission vocabulary (ADR 0007), crews that **belong to their tenant**, a crew **listing** and
> **idempotent submits** (ADR 0008), crew progress **collected by the server** and read by
> **cursor** (ADR 0009), **real usage** (tokens, cost) on every result, document **revisions**, and
> **Swarm Command 0.3.0** on all of it. Toolchain and dependencies are unchanged from 0.1.7. (Version,
> Source, the route table, the WebGUI section, Persistence, Tests, Hardening and the gate counts were
> refreshed then; the milestone narrative below is as of M6 part 1 and did not move.)
>
> **Picking this port up?** Start at [`handoff.md`](handoff.md) — orientation,
> the build procedure that avoids an unreproducible lock, and what M6 must decide.
> This file is the numbers.

## Version

**0.1.9** — see `CHANGELOG.md`. **1.0.0** is the target cut, not 2.x. The Cyrius
line is the first SemVer line — the Python line was CalVer (`2026.3.18`).

## Toolchain

- **Cyrius pin**: `6.6.12` (`cyrius.cyml [package].cyrius`). Every stdlib file in
  `lib/` is byte-identical to `git show 6.6.12:lib/<mod>` in the cyrius repo, and a
  clean-copy CI run (fresh dep cache, `lib sync --full` + `deps`) reproduced `lib/`
  and the lock.

✅ **No `[deps.patra]` or `[deps.sigil]` hold at this pin, and nothing is skewed.**
6.6.12 folds **sigil 3.13.5** and **patra 1.15.1**. agnosai 2.1.2 declares sigil
3.13.5 and libro 2.10.5 declares patra 1.15.1 — the fold's own versions — so the two
artifacts `cyrius deps` skips ("refusing to overwrite stdlib leaf") are byte-identical
to the folded copies it keeps (checked at 0.1.7). kavach 3.13.1 still declares sigil
3.12.18, and libro 2.10.5 declares sigil 3.13.4; closest-wins skips both.

⚠ **The pin and the dep tags move TOGETHER.** `cyrius deps` resolves a declared
  dep's dist on top of the `lib sync --full` snapshot, and `check-clean.sh` allows
  no file to differ from the snapshot — so a chain that declares a patra/sigil the
  pinned Cyrius does not fold goes red, in either direction (this is what kept
  agnosai's `main` red before its 2.0.5). ⛔ The wrong fixes, both tried and
  rejected: a `[deps.patra]` hold in this manifest, and a `check-clean` allowance.
- `cyrius deps` prints `refusing to overwrite stdlib leaf 'sigil'` / `'patra'` on
  every resolve. At 6.6.11 the skipped artifacts (3.12.18 / 1.14.3) differed from the
  folded copies; **at 6.6.12 they are the same bytes again**, because agnosai 2.1.2 and
  the directly-declared libro 2.10.5 pin the fold's own versions.
- ✅ **The wrapper pins `cycc` now** — fixed upstream at v6.5.42, and the installed
  `cyrius` re-execs the toolchain the manifest pins. The `CYRIUS_HOME` shim this
  section used to prescribe is no longer needed; confirm with `cyrius --version`
  (a `manifest-pin:` line with **no** `drift`) and `cyrius which`.
- ⚠ **Never read `~/.cyrius/versions/<V>/lib/` as ground truth.** A concurrent
  session working on cyrius rewrites those files in place; that produced a wrong
  diagnosis on 2026-08-22 ("6.5.33 folds patra 1.13.10" — it does not). Check what
  a release folds with `git show <tag>:lib/<mod>` in `~/Repos/cyrius`.

## Dependencies

`[deps.agnosai]` is **tag-only — no `path`**. `path` beats `tag` when a checkout is
present, so a local resolve silently vendors the sibling's work-in-progress into
`lib/` and the lock: content matching no tag, which CI cannot fetch. Deleting it
took the lock from **1 commit pin to 9**.

**Two root blocks, both with `modules`.** `cyrius deps` clones a `[deps.X]` only when it
lists `modules`; a block with `git` + `tag` alone is never visited and resolves nothing.
That is why the four "pre-pins" this manifest carried through 0.1.6 (bote, majra,
ai-hwaccel, tyche) never took effect — agnosai's own declarations resolved all four —
and why 0.1.7 removed them rather than moving them. Filed upstream:
`cyrius/docs/development/issues/2026-10-01-git-dep-without-modules-silently-inert.md`.

| dep | pin | how it arrives |
|---|---|---|
| `agnosai` | **2.1.2** | direct, `git` + `tag` + `modules` — pins every dep below at its latest |
| `libro` | **2.10.5** | direct since 0.1.7 — the audit chain `src/engine/audit.cyr` calls; listed AFTER agnosai so agnosai's sigil wins the lock |
| `bote` / `majra` | **3.3.15** / **2.9.2** | transitive via agnosai 2.1.2 |
| `ai-hwaccel` / `tyche` / `kavach` | **2.4.0** / **1.1.0** / **3.13.1** | transitive via agnosai 2.1.2 |
| `sigil` | **3.13.5** (folded) | folded stdlib (`[deps].stdlib`); agnosai declares the same 3.13.5 |
| `patra` | **1.15.1** (folded) | folded stdlib (`[deps].stdlib`); libro declares the same 1.15.1 |

`cyrius.lock` — **118 files locked, 9 commit pins** (every dep above), plus a trailing
`cyrius 6.6.12` line recording the toolchain that wrote it. agnosai 2.1.2 was prepared
alongside this release and certified the same way: its full CI steps in a clean copy
against an empty dep cache with no sibling checkouts (99 suites, 8,058 assertions). Every
tag was confirmed on the GitHub remote before the lock was written, and a sibling-free
resolution from an empty dep cache reproduced `lib/` and the lock byte for byte.

✅ **Both sibling work-arounds are REMOVED** (2026-08-22). patra 1.13.10 stopped
`patra_init` clobbering the host log level, and libro 2.8.9 stopped a `PatraStore`
read from another thread killing the process. `src/engine/store.cyr` no longer
saves/restores the level; `agnostic_audit_count` queries live instead of doing
`at_open + appended` arithmetic, and the new `agnostic_audit_reverify` runs on any
thread. Each removal is covered by an assertion — `store/log-level` and
`audit/off-thread` — because both upstream failures were silent (missing log lines;
a process kill with no diagnostic).

## Source

**M4 complete; M5 complete; M6 started; M9 seeded (0.1.7) with a plugin platform
(0.1.8), checked by the server and with a crew surface a UI can build on (0.1.9)** — 48 files,
22,814 lines, 927 top-level definitions, all `agnostic_*`-prefixed. 9,075 of those lines are
generated: `src/presets_data.cyr` (837) and `src/webgui_data.cyr` (8,238 — two embedded pages and
the plugin permission vocabulary).

**Tests: 29 suites, 1,749 assertions, 0 failed** (`cyrius test`), plus **30 JavaScript
tests** (`scripts/check-webgui-js.sh`, Node 20+). Gates green: `check-symbols.sh` (4 rules — Rule 4,
the `lib/`↔`lib/` constant check, is evaluated per shipped target since 0.1.7), `check-clean.sh`
(also `gen-webgui.sh --check` and, since 0.1.9, the WebGUI's JavaScript), `deps --verify` 118/0.

**M5 — identity and tenancy — is done.** `src/auth/` holds credential primitives
(`crypto`), users and API keys (`store`), HS256 tokens (`jwt`), the static
role→permission table (`perm`), tenancy and key-prefixing (`tenant`), the
credential→principal path (`authn`), login-abuse controls (`ratelimit`) and
callback signatures (`webhook`). The dispatch ladder's auth rung at
`src/http/router.cyr` is **wired**, not a comment, and `POST /api/v1/auth/login`
issues the tokens it checks.

⚠ **`agnostic_route_dispatch_a` takes a request CONTEXT as its sixth argument**
(credential + peer address), not a bare header. Passing a `Str` there compiles —
everything is `i64` — and **crashes at run time with no output**, which is how it
presents in a suite run. `agnostic_serve_handler`'s first parameter is already
named `ctx`; do not shadow it.

### M6 — the tool gate, and the number that has to reach 0

`src/engine/tools.cyr` resolves the preset tool vocabulary against the engine's
registry. **2 of 38 resolve; 36 do not**, both pinned by `tests/tools.tcyr`. M6 is
finished when the unresolved count is 0.

⚠ **Do not "fix" the gap with a case transform.** `LoadTestingTool` →
`load_testing` works and `RiskScoringTool` → `risk_scoring` resolves to nothing;
a transform makes them indistinguishable and books coverage for 36 tools that
cannot run. The alias table is explicit on purpose, and an entry is a claim that
the backend does the job — which is why `ComprehensiveSecurityAssessmentTool` is
NOT aliased onto `security_audit`.

⚠ **NEXT DECISION, and it gates everything else: who owns the tool registry.**
`agnostic_engine_init` exposes no registry handle — the orchestrator owns one
internally — so the gate is not wired into mount and agnostic's QA tools have
nowhere to register that the orchestrator's agents would read. Settle that before
implementing tools, or they will be written against the wrong seam.

⚠ **`agnostic_response_json_a` takes the bayan OBJECT, not an encoded `Str`.**
`_agnostic_serve_send` serialises it. Handing it a `Str` double-encodes the
response into a JSON string, and a test that reads the body directly rather than
through the send path will not notice.

⚠ **`AGNOSTIC_AUTH` defaults to `off`, and `agnostic_serve_mount` REFUSES TO
START with it off on any bind but loopback.** There is no bootstrap route yet, so
nothing could authenticate on a fresh deployment — the refusal is what keeps that
from being fail-open rather than a promise that it is not.

⚠ **Every security property in `src/auth/` is mutation-verified.** The suites are
written so that removing a guard breaks a named assertion: the bucket re-checks,
the JWT signature compare and `exp` rule, the permission table, tenant unscoping,
the role-from-row rule, the rate limiter's position before Argon2, and the
webhook timestamp being inside the MAC. Re-run those mutations before trusting a
refactor of any of it.

| module | role |
|---|---|
| `src/config.cyr` | env config, strictly parsed; a malformed value refuses to start |
| `src/strcase.cyr` | ASCII case folding without allocating |
| `src/trace.cyr` | thread-local W3C trace ids (sakshi's is a process global) |
| `src/log.cyr` | sakshi emit hook, one JSON object per event |
| `src/http/{status,response,codec,router}.cyr` | status table, response records, JSON allow-list codec, route matching |
| `src/engine/outcome.cyr` | the result type carrying status + error + engine id + results |
| `src/engine/ledger.cyr` | what Agnostic remembers about submitted crews; the terminal latch; the numbered event ring, scope and idempotency key (0.1.9) |
| `src/engine/request.cyr` | one task model, allow-list decoded, DAG validated |
| `src/engine/crew.cyr` | the orchestrator bridge — submit, poll, cancel |
| `src/engine/collector.cyr` | the thread that keeps every live crew's ledger entry current (0.1.9, ADR 0009) |
| `src/engine/reject.cyr` | how a request says no; the typed-field readers |
| `src/engine/agentdef.cyr` | **one** agent model — forwarded, retained, or refused |
| `src/engine/definitions.cyr` | the definition store — **patra-backed** since M4 |
| `src/engine/rlock.cyr` | the re-entrant lock the store and the audit trail serialize under |
| `src/engine/store.cyr` | the one patra handle the durable tables share — **handed out only under the store lock** |
| `src/engine/crewstore.cyr` | terminal crew outcomes, durable; the crew index the listing reads (0.1.9) |
| `src/engine/audit.cyr` | the tamper-evident trail, libro over patra |
| `src/engine/presets.cyr` | the canonical preset library, parsed once at mount |
| `src/presets_data.cyr` | **generated** — the 18 documents as Cyrius literals |
| `src/engine/settings.cyr` | deployment-wide settings, durable — the plugin switches (0.1.7) |
| `src/engine/plugindata.cyr` | each plugin's own documents, per tenant, durable (0.1.8) |
| `src/webgui/plugins.cyr` | the WebGUI's page table and plugin registry, loaded once at mount (0.1.7); the permission vocabulary and the plugin rung (0.1.9) |
| `src/webgui/permissions.json` | the plugin permission vocabulary — the one source the generator, server and shell read (0.1.9) |
| `src/webgui_data.cyr` | **generated** — the shell and each plugin page, verbatim, with SHA-256 and CSP (0.1.7) |
| `src/routes/health.cyr` | `/health` and `/ready` |
| `src/routes/crews.cyr` | the crew surface |
| `src/routes/definitions.cyr` | agent definition CRUD |
| `src/routes/presets.cyr` | the preset surface, read-only |
| `src/routes/plugins.cyr` | list plugins, switch one on or off (0.1.7) |
| `src/routes/webgui.cyr` | `/ui` and `/ui/plugins/{id}` — the pages (0.1.7) |
| `src/routes/plugindata.cyr` | a plugin's documents — list, read, write, delete (0.1.8) |
| `src/http/guard.cyr` | the transport rules: a JSON media type, a loopback Host (0.1.8) |
| `src/server/serve.cyr` | the only module that touches a socket |
| `src/app.cyr` | the canonical include order — **no definitions** |
| `src/main.cyr` | entry point alone; includes `app.cyr` |

⚠ **`src/app.cyr` exists so adding a route stops breaking every suite.** The
include order used to live in `main.cyr` and every suite reaching the router
reproduced it, so a new route module failed them all with "undefined function"
rather than "missing include" — three times across M2 and M3. `main.cyr` cannot
serve that role itself: its two trailing top-level statements run at include time
and would start a server inside a suite.

The crew surface, and what each code means:

| route | codes |
|---|---|
| `POST /api/v1/crews` | **202** accepted (`task_ids`; `replayed` for a repeated `Idempotency-Key`) · 400 semantic · 422 shape or key reused over another body · 503 engine down |
| `GET /api/v1/crews` | 200 — the caller's tenant's crews, newest first; `?limit=` `?before=` (0.1.9) · 422 |
| `GET /api/v1/crews/{id}` | 200 (with `usage`, times, `scope`) · 404 never submitted **or another tenant's** · 422 malformed id |
| `POST /api/v1/crews/{id}/cancel` | 200 · 404 · **409 already terminal** · 422 · 503 |
| `GET /api/v1/crews/{id}/events` | 200 — refreshed first (0.1.8); `?after=N` cursor, `seq`/`at_ms`, `next`, `missed`, `lost_events` (0.1.9) · 404 · 422 |
| `GET /api/v1/crews/{id}/plan` | 200 — agents and tasks with engine ids (0.1.9) · 404 not held · 422 |
| `GET /api/v1/presets` | 200 — summaries, not documents |
| `GET /api/v1/presets/{name}` | 200 · 404 unknown name |
| `GET /api/v1/agents/definitions` | 200 |
| `POST /api/v1/agents/definitions` | **201** · 400 · **409** · 422 · **507** |
| `GET /api/v1/agents/definitions/{key}` | 200 · 404 · 422 |
| `PUT /api/v1/agents/definitions/{key}` | 200 · 400 · 404 · 422 |
| `DELETE /api/v1/agents/definitions/{key}` | 200 · 404 · 422 |
| `GET /api/v1/plugins` | 200 — with the permission `catalogue` (0.1.9) — READ |
| `PUT /api/v1/plugins/{id}` | 200 (`changed` true/false) · 400 · 404 · 422 · 500 — **ADMIN** |
| `GET /api/v1/plugins/{id}/data` | 200 — keys, times, sizes, `scope` · 404 · 422 — READ |
| `GET /api/v1/plugins/{id}/data/{key}` | 200 — the document, verbatim, with its `ETag` (0.1.9) · 404 · 422 — READ |
| `PUT /api/v1/plugins/{id}/data/{key}` | **201** · 200 · 400 · 404 · **412** (0.1.9) · 413 · 422 · **507** — WRITE |
| `DELETE /api/v1/plugins/{id}/data/{key}` | 200 · 404 · **412** (0.1.9) · 422 — WRITE |
| `GET /ui` · `/ui/` | 200 — the shell, **public** |
| `GET /ui/plugins/{id}` | 200 · **404 while switched off** · 422 — **public** |

The table is a flat scan of 19 paths (20 patterns). Measured at 0.1.9 (`tests/agnostic.bcyr`): ~0.10 µs
to resolve the first entry, ~0.87 µs the last, ~0.73 µs for a miss that tries every pattern,
~2.0 µs for the two-capture document path — against ~48 µs for the per-request user lookup. A request
a plugin makes also pays the plugin rung, ~1.2 µs; a cursor poll copies one new event out of the ring
in ~0.12 µs (a whole 256-event window ~5.7 µs). (0.1.8, 18 paths: 0.12 / 0.93 / 0.78 / 2.1 µs.)
Still not worth an index. (0.1.7, 16 paths — once miscounted as 15: 0.11 / 0.81 / 0.65 µs.) The 0.1.8 transport rules
cost ~0.15 µs each per socket request; validating a full 32 KiB plugin document ~0.2 ms.
⚠ The machine was under heavy load from other work during the 0.1.8 runs — successive runs
varied up to 2×; these are from the run whose `noop` matched the 2 ns baseline.

⚠ **201 for a definition, 202 for a crew.** A crew is accepted work that is not
finished; a definition *is* complete when the call returns. **No upsert** in
either direction: `POST` to an existing key is 409, `PUT` to an absent one is 404
— an upsert turns a typo'd key into a second silently-created definition.

✅ `GET /api/v1/crews` **lists** since 0.1.9 — it answered 405 until a listing could be
paginated (a cursor) and scoped (crews belong to their tenant, ADR 0008). ⚠ A crew is
**404 to every other tenant** on every crew route; a crew stored before 0.1.9 belongs to `_`
and is not listed.

## WebGUI and plugins (0.1.7, 0.1.8, 0.1.9)

**M9's first slice (0.1.7), its plugin platform (0.1.8), checked by the server (0.1.9).** Why
compiled-in plugins switched at run time is [ADR 0004](../adr/0004-webgui-plugins-compiled-in-switched-at-run-time.md);
how a plugin reaches the server is [ADR 0005](../adr/0005-plugins-reach-the-server-through-the-host-bridge.md),
and why the server checks it too, against one vocabulary, is [ADR 0007](../adr/0007-plugin-requests-are-checked-by-the-server.md);
how to add one is [`guides/webgui-plugins.md`](../guides/webgui-plugins.md).

**0.1.9, in one paragraph.** Plugin permissions live in `src/webgui/permissions.json` and are enforced
by the server on every request the shell makes for a plugin (`X-Agnostic-Plugin` → the plugin rung,
before authentication: `403` with `plugin_unknown` / `plugin_off` / `plugin_forbidden`). The shell's
gate (`window.AgnosticBridge`, a pure script) is built from the same vocabulary, answers only the page
session that asked, takes messages only from an opaque origin, caps a plugin at 16 requests in flight,
and carries query strings, revisions and idempotency keys. Plugin documents have ETags; `If-Match` /
`If-None-Match: *` answer 412. Swarm Command 0.3.0 runs on real crews and real numbers — see below.

- **`/ui`** — the shell (30,931 B): Overview (`/ready`, the views), a tab per plugin that
  is switched on, Settings (the switches with each plugin's permissions and stored
  documents, the session). With `AGNOSTIC_AUTH=required` it signs in through
  `POST /api/v1/auth/login` and keeps the token per tab (`sessionStorage`). It is also the
  **host bridge**: it answers a plugin's `postMessage` requests that its manifest permits,
  with the user's token, which the plugin never sees.
- **Swarm Command 0.3.0** (`swarm`, 429,829 B, `data: mixed`, permissions `storage`,
  `presets:read`, `crews:read`, `crews:write`) — a launcher of saved swarms (plugin
  documents `swarm-<id>`, per tenant, written with their revision), an editor for every
  capability with defaults, a headless cost estimate over eight seeds, the simulator driven by
  the spec, live runs — submitted with an idempotency key and recorded before they start, read by
  cursor, bound by engine task id, ended with the tokens and cost agnostic metered beside the
  estimate, outputs under Results — and a **Crews** list that watches any crew of the tenant. Every
  mission is labelled SIM or LIVE; a live cost the gateway did not report is n/a, never simulated.
- **Every plugin starts OFF.** The switch is `plugin.<id>.enabled` in the settings table;
  it survives a restart, flipping it is ADMIN, and only a real change is audited. A plugin's
  documents survive it being switched off.

⚠ **Pages are public; the API is not.** A browser navigation cannot carry a bearer token,
and a page is the same compiled-in bytes for every caller. Everything it shows comes from
authenticated API calls.

⚠ **Each page's CSP is computed by the generator** — `default-src 'none'`, inline scripts
admitted by SHA-256; the shell `connect-src 'self'`, a plugin **`connect-src 'none'`**
(0.1.8: its only way out is the bridge). A page that needs anything else is refused at
generation. `style-src 'unsafe-inline'` is accepted (the view styles from script and
markup); scripts are never inline-unsafe.

⚠ **Plugins run sandboxed** (`allow-scripts allow-downloads`, no `allow-same-origin`): an
opaque origin, so a plugin cannot read the shell's token, reach the network, or open a
modal dialog. Opened in its own tab, Swarm Command finds no shell, keeps swarms in that
browser and disables live runs.

✅ **Permissions are ONE list since 0.1.9** — `src/webgui/permissions.json`, read by the generator
(manifests are checked against it), the server (it enforces it) and the shell (from
`GET /api/v1/plugins`). The shell's `permitted()` and the generator's hard-coded `PERMISSIONS` are
gone. A new permission is one edit to that file, and the docs.

⚠ **The embedded pages are proven, not assumed.** `src/webgui_data.cyr` holds each page as
a raw multi-line literal; `tests/webgui.tcyr` re-hashes the bytes in the binary against
the source file's SHA-256, and `check-clean.sh` runs `gen-webgui.sh --check`. A
`\`-continued literal would have been wrong: `cyrius fmt` indents continuation lines,
and the spaces land inside the string.

⚠ **Verified in headless Chromium at 0.1.9** (CDP; the plugin frame is in-process there, reached
through its execution context), against scratch servers running real crews through a stand-in
gateway that prices calls: auth off — 29 checks, from the bridge features through a live crew's
metered cost, results, the run record, watching, the Crews list, a crew from a script, a two-tab
conflict and switching the plugin off under an open view; auth required — 13, including a session
invalidated mid-crew pausing and resuming the watch; the standalone page — 7. No uncaught exception
in either frame. (0.1.8: 112 checks, much of the same ground before these changes.)

✅ **The page's logic is tested in the repo now** — `tests/webgui/` under Node (`check-clean.sh` runs
it): the shell's gate against the real vocabulary, and Swarm Command's simulator, specs, library and
live crew source against a fake agnostic that answers as 0.1.9's server does. At 0.1.8 the 225
assertions that covered this ran once and were discarded.

The Python implementation is retained at `python-port/` as a behavioural oracle.
It is never built or shipped, and it is **not** a specification —
[`ORACLE-AUDIT.md`](../../ORACLE-AUDIT.md) records 86 verified defects in it.

## Tests

**29 suites, 1,749 assertions, 0 failed** (`cyrius test`, under the 6.6.12 pin), and
**30 JavaScript tests** (`./scripts/check-webgui-js.sh`). 0.1.9's additions:
`tests/ledger.tcyr` (the ring, the cursor, a drain that allocates nothing, lost vs trimmed),
`tests/crews_route.tcyr` (the cursor over HTTP, the collector carrying an unpolled crew to a persisted
outcome, task ids and the plan), `tests/outcome.tcyr` (usage, per task and per crew), the new
`tests/crew_tenancy.tcyr` (isolation on every crew route, the listing and its cursor, the durable
index across a restart, idempotency keys — four mutations each fail a named assertion),
`tests/webgui.tcyr` (the plugin rung — two mutations) and `tests/plugindata.tcyr` (revisions — one).
`tests/store_concurrency.tcyr` (43, 0.1.4) is the only multi-threaded suite.
`tests/webgui.tcyr` (141, 0.1.7) holds the WebGUI: the embedded pages re-hashed against
their sources, the registry, durable switching, every route and code, the permission
split and audit-only-on-change — six mutations of those guards each fail a named
assertion — and, since 0.1.8, the manifest permissions and the plugin CSP.
`tests/plugindata.tcyr` (124, 0.1.8) holds the plugin platform's server half: the JSON
validator, the transport guards, the two-capture router, the document store and its
limits, the routes with tenant isolation and the permission split, and the ladder's
transport rungs — each of four mutations (scope collapse, depth, any Host, no media rung)
fails a named assertion. `tests/serve_mount.tcyr` (21) drives both rungs through the
socket handler; `tests/crews_route.tcyr` (62) pins the events route's current status.
The per-suite list below predates M5 and M6; its counts are as of then.

⚠ Counts here are assertion-suite lines only. `cyrius test`'s final
`N passed, 0 failed` line is the **suite** tally, not a suite — earlier figures
in this repo (`222`) and in agnosai (`8,038`) double-counted it.

- `tests/{agnostic,codec,config,health,log,router,trace}.tcyr` — M1 coverage (7 suites, 215 assertions)
- `tests/deps_symbols.tcyr` — **14 assertions**, cross-dependency symbol integrity;
  see Hardening below
- `tests/outcome.tcyr` — **63 assertions**, the result type. Carries the §3.1 barrier:
  an engine COMPLETED with an empty result set must demote to FAILED
- `tests/ledger.tcyr` — **53 assertions**, the §3.4 barrier: a terminal status
  cannot be moved, in either direction, by any later observation
- `tests/crew_request.tcyr` — **92 assertions**, the §3.3 barrier: `tasks` is
  required, there is no fallback, and a cyclic graph is refused before submission
- `tests/crews_route.tcyr` — **59 assertions**, the surface end to end, including
  the §3.2 barrier: an id we never submitted is a 404 that relabels nothing
- `tests/crewstore.tcyr` — **25 assertions**, terminal-only persistence, written
  once, and durable across a reopen
- `tests/audit.tcyr` — **35 assertions**, the trail: durable across a reopen, and
  a byte edited on disk is **detected** with the failing entry named
- `tests/agentdef.tcyr` — **106 assertions**, the one agent model: every field
  forwarded, retained or refused by name, plus the store's no-upsert and
  never-evict policies
- `tests/presets.tcyr` — **71 assertions**, the canonical library: all 18 parse,
  the declared order, the off-canon `complete` domain, and the **38-name tool
  manifest** that is M6's contract
- `tests/agnostic.bcyr` — benchmark stub · `tests/agnostic.fcyr` — fuzz stub

## Dependency layout

**agnosai 2.1.2** (`modules = ["dist/agnosai.cyr"]`), linked in-process rather
than called over HTTP. Everything crew/task/agent/scheduling-shaped lives there;
Agnostic owns the product tier. Versions and pins: see the table under
[Dependencies](#dependencies) above.

`lib/` holds **118** `.cyr`: **111** from the 6.6.12 stdlib snapshot plus 7 dep
dists (`agnosai`, `bote-core`, `majra`, `ai-hwaccel`, `tyche`, `kavach`, `libro`).
`deps --verify` 118/0. The compile set `check-lib-symbols.py` resolves is **53**
modules — `sys` joined at 0.1.3, because sigil 3.12.18 calls `sys_uname`.

⚠ **`check-lib-symbols.py` evaluates `#ifdef` per target since 0.1.7.** sigil 3.13.5
declares eight errno names in both arms of `#ifdef CYRIUS_TARGET_MACOS`, and a gate that
read every line as live failed against kavach on every target built here. Rules run once
for x86_64-linux and once for aarch64-linux. It also honours `CYRIUS_HOME` for dep
sidecars now — under the certification shim it had silently shrunk the compile set
from 53 modules to 49.

## Consumers

_None yet._ SecureYeoman may pull agnosai directly without this frontend tier —
Agnostic is built to stand on its own, not as a required layer.

## Hardening

**P(-1) complete — 2026-08-20**, re-audited at M1.

| Criterion | Status |
|---|---|
| audit-clean | [`2026-08-20-audit-m1.md`](../audit/2026-08-20-audit-m1.md) — 0 CRITICAL / 0 HIGH / 1 MEDIUM / 2 LOW; the MEDIUM is accepted with a documented bound |
| fmt / lint / vet / deny | `check-clean.sh` OK |
| store lock (0.1.4, 0.1.5) | `check-store-lock.py`, in `check-clean.sh` — every handle fetch under the store lock; no result string borrowed past its result set |
| transport (0.1.8) | [ADR 0006](../adr/0006-loopback-host-and-json-only-writes.md): with auth off a non-loopback `Host` is 403; a POST or PUT without a JSON media type is 415 — both through the socket handler in `tests/serve_mount.tcyr`, mutation-checked |
| plugins (0.1.9) | [ADR 0007](../adr/0007-plugin-requests-are-checked-by-the-server.md): every bridged request is checked by the server against `permissions.json`; mutation-checked in `tests/webgui.tcyr` and, for the shell's gate, `tests/webgui/shell.test.mjs` |
| crew tenancy (0.1.9) | [ADR 0008](../adr/0008-crews-belong-to-the-submitting-tenant.md): another tenant's crew is 404 on every route; mutation-checked in `tests/crew_tenancy.tcyr` |
| webgui js (0.1.9) | `scripts/check-webgui-js.sh` in `check-clean.sh` — Node 20+, a test-time dependency only |
| symbols | `check-symbols.sh` OK — 927 top-level definitions across 48 files, no duplicates, all prefixed |
| security | CI `security` job clean |
| baseline benches | `bench-history.csv` seeded — `noop` 2 ns @ `830216c` |
| documented | `BENCHMARKS.md` generated |

### Two gates added at M2

**`check-symbols.sh` rule 3 now scans enum members on both sides.** It compared
only `^(fn|var)` against `lib/`. Cyrius enum qualifiers are **cosmetic**, so a
`src/` enum member colliding with a `lib/` one silently replaced it for the whole
program — the same mechanism as the `BACKEND_COUNT` defect below, in the one
declaration kind the gate did not cover. Mutation-verified.

**`scripts/check-log-lengths.py`**, wired into `check-clean.sh`. sakshi takes
`(pointer, length)` pairs, so every message's byte count is hand-written and
nothing checked it. Both failure modes are silent and both shipped in one M2
commit: a count one too high put the **NUL terminator inside a JSON string**, and
one too low **truncated** a message. Invisible to the compiler, to lint, and to
suites that assert on handler behaviour rather than log text. Mutation-verified.

### The gap `check-symbols.sh` still does not cover

⚠ **Rules 1 and 2 scan `src/` only.** Cyrius has one flat symbol namespace with
last-definition-wins; the compiler warns on a duplicate `fn` but is **silent**
on a duplicate `var`. A collision between two *dependencies* inside `lib/` is
therefore invisible to the compiler and the linter at the same time — and
Agnostic, linking kavach and ai-hwaccel through agnosai, is where such a
collision lands.

That is not hypothetical: `BACKEND_COUNT` was 10 in kavach and 18 in
ai-hwaccel, and resolved to 18, disabling kavach's `_backend_fp` bounds check
over a 10-slot table. Fixed upstream; `tests/deps_symbols.tcyr` now guards the
class rather than the instance.

A full `lib/`-wide sweep at this dep set found **no remaining silent collision**:
of 3,040 top-level `var`s, only `AT_FDCWD` and `TASK_SIZE` differ across files,
and both are platform-variant families (`syscalls_*`, `async_*`) where exactly
one variant is prepended per target. `HTTP_OK`/`HTTP_NOT_FOUND` are defined by
both `http.cyr` and `sandhi.cyr` with identical values — redundant, not a defect.

✅ **Duplicate-`fn` warnings: 19 at 0.1.2, 1 at 0.1.3** — both measured on a DCE
build; the "20" once recorded here included libro ↔ majra `_sub_new`, already gone
by 0.1.2. All 19 were kavach's: 3.13.1 no longer redefines the `syserr_*` /
`agnosys_*` family and the rest of what it shared with sigil and bote-core. The one
left is `uname_release`, in both `lib/sys.cyr` and
`lib/sigil.cyr` with **identical** bodies (`return uts + UTS_RELEASE;`), so which
one wins does not matter. Upstream, and it announces itself.

## Preset library

**18 documents, 76 agents, 45 distinct agent keys, 38 distinct tool names.**
Checked in at `src/presets/*.json` and embedded into `src/presets_data.cyr` by
`scripts/gen-presets.sh`, because Cyrius has no `include_str!`. The generated file
is committed; `check-clean.sh` runs the generator's `--check` mode so it cannot
go stale.

Parsed **once at mount** into a name-keyed registry — `agnosai_builtin_presets()`
re-parses all eighteen on every call and the engine has no name lookup at all.
A parse shortfall refuses to start rather than serving a quieter, smaller library.

⚠ **The listing returns summaries, not documents.** The library is 61,412 bytes of
compact JSON against a 65,536-byte default request arena, and the arena spills
into the no-`free()` global bump — a full-document listing would leak permanently
on every call. Measured live: the listing is **4,416 bytes** and the largest
single document (`quality-large`) is **7,064**, so the default arena has ample
headroom and was left unchanged.

⚠ **The 38 tool names have never resolved to anything** — `ORACLE-AUDIT.md` §3.15.
`agnostic_preset_tool_*` pins the union as M6's contract; two of the names
(`ArtifactManagementTool`, `CIPipelineIntegrationTool`) have no implementation
anywhere and M6 owes a decision on each.

## Agent definitions

**One model, three dispositions, all of them visible on the wire.** A crew's
`agents` array and a stored definition are decoded by
`agnostic_agent_def_decode_a` and by nothing else.

| Disposition | Count | What it means |
|---|---|---|
| FORWARDED | 12 | the engine has a slot that acts on it |
| RETAINED | 2 | `focus`, `allow_delegation` — kept, round-tripped, and **named** in `unforwarded` |
| REFUSED | 12 | a 422 naming the missing capability |

Membership of RETAINED was decided by one test: does the canonical preset library
carry it? All 76 preset agents carry `focus`; 18 carry `allow_delegation`.
Neither reaches the engine, so saying so beats dropping it.

⚠ **`agent_key` is refused with a message pointing at `key`.** The oracle and the
engine both spell it `agent_key`; Agnostic spells it `key`, because M2's crew
decoder already did and one model cannot have two spellings.

⚠ **`hardware` is the one field refused despite the engine having a slot** — the
record is `ai-hwaccel`-shaped and Agnostic has no decoder for it. Every other
refusal is refused because the engine genuinely cannot act on it.

✅ **The store is durable, in patra, since M4.** `"storage": "patra"` on all five
responses; the nine store functions kept their signatures and
`src/routes/definitions.cyr` was not touched. A definition created in one process
is served by another after a restart — asserted in `tests/agentdef.tcyr` and
verified live.

The stored document is the **wire form**, read back through the same decoder that
validates a client request — so there is no second serialiser, a row that no
longer decodes is caught rather than half-read, and the two retained fields
persist without a column each.

⚠ `AGNOSTIC_DEFINITIONS_MAX` is now a **decode-cache bound, not a store ceiling**
— there is still no `free()`, so decoding per `GET` would leak. The cache assumes
this process is the only writer; patra is flock-arbitrated and multi-process, so
if that changes the cache goes rather than gets patched.

## Persistence

**One patra database, eight tables**, behind `src/engine/store.cyr`:
`agnostic_definitions (dkey, doc)`, `agnostic_crews (crew_id, cname, cstatus, doc)`,
the identity tables `agnostic_users`, `agnostic_apikeys` and `agnostic_tenants` (M5),
`agnostic_settings (skey, sval)` (0.1.7), `agnostic_plugin_data` (0.1.8), and
`agnostic_crew_index` (0.1.9 — one row per terminal crew, indexed on `scope`, what the listing reads). patra allows exactly **one index per
table** — `SCH_IDX_COL` is a single slot in the schema page — so each gets it on the
column everything looks up by. The audit chain has its own file: `patrastore_open`
opens its own handle.

⛔ **Every use of either handle is serialized — since 0.1.4.** All pool workers
share each handle, and patra's read path takes no lock, so before 0.1.4 eight
threads doing only the per-request user lookup killed the process (SIGBUS, every
run) and concurrent audit appends could fork the chain. Now:

- one **re-entrant** store lock (`src/engine/rlock.cyr`); every store operation is
  a wrapper — `lock; var r = _x_locked(...); unlock; return r;` — so each is one
  critical section, and check-then-insert cannot be split;
- **`agnostic_store_db()` refuses the handle** to a thread without the lock (0 and
  an ERROR line); `agnostic_store_is_open()` answers availability without it;
- the audit trail has its own lock; the two are never held together;
- **never under the store lock:** Argon2 (`create` hashes outside it and re-checks
  under it), engine calls, the audit lock;
- `scripts/check-store-lock.py` (in `check-clean.sh`) checks the rule statically.

Cost: ~0.7 µs per uncontended enter/exit (two `gettid` syscalls) against ~48 µs
per user lookup; the ceiling is serial store access, ~20k lookups/s here. Why not
a handle per worker — patra's advice for read parallelism — is ADR 0003.
⚠ Do not release it with `defer`: cycc 6.6.6 skips a `defer` on `return f(...)`
(filed upstream 2026-09-26).

✅ **The two server crashes found at 0.1.4 are fixed in 0.1.5** (both dated from
at least 0.1.3):

- mount now runs sigil's `crypto_tls_main_init()` FIRST, on the main thread —
  left lazy, the first hash ran it on a pool worker, replacing that worker's TLS
  block and its request arena, and the worker's next request killed the process.
  The handler also falls back to the global allocator rather than dereference a
  missing arena. `tests/serve_mount.tcyr` calls the real mount to pin both.
- strings read out of patra are now COPIED. `str_new` / `str_new_a` borrow, and
  two sites kept `patra_result_get_str` pointers past `patra_result_free`: the
  definitions listing (segfault at ~300 rows) and `_agnostic_auth_str_a` (a
  principal's tenant could turn into another user's mid-request).
  `check-store-lock.py` rule 3 forbids the pattern.

⛔ **aarch64: the server dies at startup, and 12 of 27 suites die, with SIGBUS — root-caused on
real hardware at 0.1.7, a cyrius layout defect, filed upstream.** Run natively on the Pi 4 (`ssh
pi`): 15 suites pass (717 assertions); `audit`, `authn`, `authstore`, `authz`, `crews_route`,
`crypto`, `jwt`, `loginguard`, `loginroute`, `serve_mount`, `store_concurrency` and `webgui` crash —
every suite that reaches sigil's crypto init. 0.1.6 is identical, so this is the "SIGBUS under qemu"
recorded since 0.1.3, not a regression. **0.1.8 adds `plugindata` to the list** — at the same
`ldaxr`, when its route group first initialises crypto, after its validator, guard, two-capture
router, store and limit groups have passed natively; `codec` and `router` (touched at 0.1.8) still
pass on the Pi.

- **Mechanism (gdb on the Pi):** `ldaxr x4, [x0]` on `x0 = 0xa200f6` — an `atomic_cas` on sigil's
  `_sha_ni_probe_lock`, which is not 8-aligned. aarch64 faults on a misaligned exclusive or
  acquire/release access; x86 does not, which is why every x86 gate is green.
- **Why it is misaligned:** a typed-array global (`var a: u8[N]`) occupies exactly `N` bytes and the
  NEXT global is not re-aligned. sankoch (folded; arrives through agnosai's sidecar) declares
  `u8[363]`, `u8[217]` and `u8[50]` — 630 bytes, ≡ 6 mod 8 — and **1,101 of the program's 1,962
  globals** sit misaligned after them, twelve of them used atomically (eleven sigil init flags,
  `_crypto_tls_inited` among them — the first thing mount touches — and majra's job counter).
- **Filed:** `cyrius/docs/development/issues/2026-10-01-typed-array-globals-not-padded-aarch64-atomics-sigbus.md`,
  with a 15-line repro (`8 363 3`, then SIGBUS on the Pi). No consumer-side work-around is sane: the
  offset comes from a module agnostic does not include itself and the victims are private flags in
  another.
- **The aarch64 artifact is WITHHELD since 0.1.7** — not released, not uploaded by CI, `cross_bins`
  commented out — by decision, as a temporary exception to the release checklist. CI still
  cross-builds it as a compile gate. Restore it (steps in `cyrius.cyml` and `release.yml`) once a
  cyrius release aligns globals and every suite passes natively on the Pi.

⚠ **Only terminal crew outcomes are stored.** A running crew's thread dies with
the process, so persisting non-terminal state would load a crew that claims to
run and never will. A crew interrupted mid-flight 404s after a restart.

⚠ **Two sibling-library defects are worked around, both filed upstream
2026-08-21.** `patra_init` stomps the host's log level (saved/restored in
`store.cyr`); libro's `PatraStore` caches prepared statements that fault on any
thread but the opener's, so audit verification runs once at open. Both
work-arounds carry a pointer to the filing and can be removed when they land.

## Next

See [`roadmap.md`](roadmap.md). **M5 — identity and tenancy.** Two things it
inherits:

✅ **patra's single index per table does NOT bind here — corrected 2026-08-21.**
The earlier note said M5 needs users by id *and* by email and would therefore
need two tables, a scan, or a patra change. It needs none of them.

`tbl_create` (`lib/patra.cyr:3437`) **auto-indexes column 0 when its type is
`COL_INT`**, so deriving the key from the value — `uid = trunc64(sha256(lower(email)))`
— makes one index serve both lookups, and M5 issues **zero `CREATE INDEX`**
statements. The same trick keys API keys by `trunc64(sha256(raw_key))` and
tenants by `trunc64(sha256(tenant_id))`.

⚠ **A truncated hash is a bucket, not an identity.** patra re-checks *STR* index
hits itself but gives no such re-check for an app-computed INT key — its INT
equality is exact on the truncated value stored. A 64-bit collision without an
app-side full compare is an **authentication bypass**, so every hit must be
re-verified against the full value with `ct_eq_bytes` before it authenticates
anything.

The limit may still be worth fixing upstream on its own merits, but M5 is not
the forcing case it was thought to be.

⚠ **Agent keys are `[a-z0-9][a-z0-9-]*`** so an identifier can never become a
path component. Audit point 6 is answered for M4 (no filesystem call in `src/`
takes request input) and genuinely re-opens at **M8**, where report filenames are
built from user text. Keep the character set narrow. The
field-forwarding gate it turns on is already built and under test:
`src/engine/request.cyr` establishes the pattern M3 extends.

⚠ **`gpu_strict` is refused, not forwarded, and that is deliberate.** It is a
field distinct from `gpu_required` — the oracle hard-fails only on
`gpu_required AND gpu_strict` — and the Cyrius engine cannot express strictness
at all (`gpu_strict` appears zero times in `lib/agnosai.cyr`). M2 refuses it with
a message naming the missing capability rather than accepting and dropping it.

⚠ **Carried into M3 and beyond, from M2:**

- **Placeholder mode is indistinguishable from real work by results alone.**
  Without `AGNOSTIC_LLM_URL` the engine echoes task descriptions back with status
  COMPLETED. Closed by disclosure (`engine_mode` on every response, a WARN at
  mount), not by type — so any *new* surface that reports crew output must
  disclose it too.
- **The crew routes are unauthenticated.** `agnostic_route_needs_auth` answers 1
  for all four, but the dispatch ladder's auth rung is still a comment until M5.
  The default bind is loopback, which is the only thing standing in front of them.
- **Results are memory-resident and capped.** The ledger retains 1,024 crews and
  256 progress events each; beyond that a poll answers `unknown` rather than a
  wrong answer. Durable results are M4's.
