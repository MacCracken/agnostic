# agnostic — Current State

> Refreshed every release. CLAUDE.md is preferences/process/procedures
> (durable); this file is **state** (volatile).
> Last refreshed: 2026-10-08, at **0.1.16** — the re-pin to **agnosai 2.1.7**, and an HTTP
> SERVER span per request through its exporter (ADR 0020): a crew's trace now has a root a backend
> can find, and with an inbound `traceparent` agnostic's span is a child of the caller's and the
> crews sit under it. The serve adapter's 48 B per request on the global heap is gone. Cyrius
> 6.6.14 and libro 2.10.6 unchanged; the lock moved by agnosai's two lines. Version, Toolchain,
> Dependencies, Source, Tests and Next were refreshed then.
> Before that, 2026-10-07, at **0.1.15** — every agnostic-only roadmap item that needs no
> dependency move, and what the work found: one process per database file, enforced; the audit
> verdict says what it found over the whole trail, and a failed write or read no longer breaks or
> fakes it; an interrupted crew keeps what its finished tasks answered (ADR 0019); agent
> definitions have revisions, and an agent's `complexity` is one of three; a 405 names its
> methods; cancel answers 409 for a stored crew; results name their agent; request paths keep
> nothing on the global heap but libro's audit entry; Swarm Command 0.5.1 sends selection hints;
> the suites keep their stores under `TMPDIR`. No dependency moved: Cyrius 6.6.14, agnosai 2.1.6
> and libro 2.10.6, with `lib/` and the lock byte-identical to 0.1.14's. Version, Source, the route
> table, the WebGUI section, Tests, Persistence, Hardening and Next were refreshed then.
> Before that, 2026-10-04, at **0.1.14** — the re-pin to **agnosai 2.1.6** and its consumer
> halves: crew events and status say what happened (agnosai's B17), `/plan?explain=selection` shows
> why each task got its agent (ADR 0016), a task carries selection hints (ADR 0017), and every crew
> joins its request's trace, with opt-in OTLP export (ADR 0018). agnosai 2.1.6 was released from what
> this release's review found in 2.1.5: bounded inference and export calls, a stranded DAG that ends
> FAILED, and a finished crew that cannot be cancelled. Cyrius 6.6.14 and libro 2.10.6 did not move;
> the lock moved by agnosai's two lines. Version, Toolchain, Dependencies, Source, the route table,
> Tests and Hardening were refreshed then, their totals re-measured at the cut with every CI gate in
> CI's order, every suite natively on the Pi, and a sibling-free, empty-cache certification.
> Before that, 2026-10-04 at **0.1.13** — H3 (closed: the cursor's gap is `missed`), H4 (a crew a
> restart interrupted answers `interrupted`, ADR 0013), B3 (Swarm Command 0.5.0's one-agent baseline,
> ADR 0014), H5 (`agnostic api schema`, ADR 0015), H6 (`skills/agnostic/SKILL.md`), and two older
> fixes (the audit chain links across a restart; a crew named over 255 bytes is stored). No dependency
> moved: Cyrius 6.6.14, agnosai 2.1.4 and libro 2.10.6, with `lib/` and the lock byte-identical to
> 0.1.12's. Version, Toolchain, Dependencies, Source, the route table, the WebGUI section,
> Persistence, Tests and Hardening were refreshed then, their totals re-measured at the cut with every
> CI gate in CI's order (every suite also ran natively on the Pi, in that day's integration run and
> again at the release verification); the milestone narrative below is as of M6 part 1 and did not
> move.
> Before that, 2026-10-03 at **0.1.12** — the re-pin to **agnosai 2.1.4** (kavach 3.13.2,
> ai-hwaccel 2.4.1) and the two `serve.cyr` warnings, so the build prints no warning on code; every
> suite passed natively on the Pi again. Before that, 2026-10-03 at **0.1.11** — the re-pin to
> **agnosai 2.1.3** and **libro 2.10.6**. Before that, 2026-10-02 at **0.1.10** — the views over the
> real surface (**Crews**, **Library**, **Audit trail**) as plugins that link to each other through
> the shell, **one bridge client** every plugin carries (ADR 0010), audit entries read from a bounded
> copy (ADR 0011), a **cancelled crew keeps its finished results** (ADR 0012), **Cyrius 6.6.14**, and
> the **aarch64 artifact restored** after every suite and the server ran natively on a Pi 4.
>
> **Picking this port up?** Start at [`handoff.md`](handoff.md) — orientation,
> the build procedure that avoids an unreproducible lock, and what M6 must decide.
> This file is the numbers.

## Version

**0.1.16** — see `CHANGELOG.md`. **1.0.0** is the target cut, not 2.x. The Cyrius
line is the first SemVer line — the Python line was CalVer (`2026.3.18`).

## Toolchain

- **Cyrius pin**: `6.6.14` (`cyrius.cyml [package].cyrius`), since 0.1.10. Every stdlib file in
  `lib/` (112) is byte-identical to `git show 6.6.14:lib/<mod>` in the cyrius repo, and a
  sibling-free replica with an **empty** dep cache (`lib sync --full` + `deps` from an empty `lib/`)
  reproduced `lib/` and the lock byte for byte; CI's gates and both DCE builds passed there —
  at 0.1.10, 0.1.11 and 0.1.12. At 0.1.13 nothing moved: `lib sync --full` + `deps` left `lib/`
  and the lock byte-identical to 0.1.12's, and `lock-check.sh --no-resolve` matched a clean tag
  resolution (9 commit pins). At 0.1.14 only agnosai moved (2.1.4 → 2.1.6): the lock by its commit
  pin and `lib/agnosai.cyr`'s hash, `lib/agnosai.cyr` byte-identical to the tag's
  `dist/agnosai.cyr`, and the empty-cache replica reproduced `lib/` and the lock byte for byte.
  At 0.1.15 nothing moved: `lib/` and the lock are byte-identical to 0.1.14's. At 0.1.16 only
  agnosai moved (2.1.6 → 2.1.7, tag `9210905`): the lock by its two lines, `lib/agnosai.cyr`
  byte-identical to the tag's `dist/agnosai.cyr`, nothing else in `lib/`.

✅ **No `[deps.patra]` or `[deps.sigil]` hold at this pin.** 6.6.14 folds **sigil 3.13.7** and
**patra 1.15.1**. Since 0.1.11 the deps declare exactly those: agnosai (2.1.7 now) declares sigil 3.13.7,
and libro 2.10.6 declares sigil 3.13.7 and patra 1.15.1. So every commit pin the lock records on a
folded module names the bytes `lib/` holds; at 0.1.10 the sigil line named agnosai 2.1.2's 3.13.5
while `lib/sigil.cyr` was the fold's 3.13.7. Since 0.1.12 no dep pins a module off the fold: kavach
3.13.2 declares sigil 3.13.7 (3.13.1 declared 3.12.18), and ai-hwaccel 2.4.1 declares bayan 1.5.11.

⚠ **The pin and the dep tags move TOGETHER.** `cyrius deps` resolves a declared
  dep's dist on top of the `lib sync --full` snapshot, and `check-clean.sh` allows
  no file to differ from the snapshot — so a chain that declares a patra/sigil the
  pinned Cyrius does not fold goes red, in either direction (this is what kept
  agnosai's `main` red before its 2.0.5). ⛔ The wrong fixes, both tried and
  rejected: a `[deps.patra]` hold in this manifest, and a `check-clean` allowance.
- `cyrius deps` prints `refusing to overwrite stdlib leaf 'sigil'` / `'patra'` on
  every resolve. Since 0.1.11 both skipped artifacts are the folded copies' own bytes again (at
  0.1.10 sigil's was 3.13.5, older than the 3.13.7 fold — harmless, the fold won).
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

**Two root blocks, both with `modules`.** Before cyrius 6.6.13 `cyrius deps` cloned a `[deps.X]`
only when it listed `modules`, so the four "pre-pins" this manifest carried through 0.1.6 (bote,
majra, ai-hwaccel, tyche) never took effect, and 0.1.7 removed them. Filed upstream from here
(`2026-10-01-git-dep-without-modules-silently-inert.md`) and fixed in 6.6.13 (I10): a block without
`modules` now means `dist/X.cyr` — and the root's tag wins — or `cyrius deps` warns by name. Such a
block is therefore an override pin, which this repo does not carry.

| dep | pin | how it arrives |
|---|---|---|
| `agnosai` | **2.1.7** | direct, `git` + `tag` + `modules` — pins every dep below at its latest |
| `libro` | **2.10.6** | direct since 0.1.7 — the audit chain `src/engine/audit.cyr` calls; listed AFTER agnosai so agnosai's sigil wins the lock |
| `bote` / `majra` | **3.3.16** / **2.9.2** | transitive via agnosai 2.1.7 |
| `ai-hwaccel` / `tyche` / `kavach` | **2.4.1** / **1.1.0** / **3.13.2** | transitive via agnosai 2.1.7 |
| `sigil` | **3.13.7** (folded) | folded stdlib (`[deps].stdlib`); agnosai and libro declare the same 3.13.7 |
| `patra` | **1.15.1** (folded) | folded stdlib (`[deps].stdlib`); libro declares the same 1.15.1 |

`cyrius.lock` — **119 files locked, 9 commit pins** (every dep above; agnosai, kavach and
ai-hwaccel moved at 0.1.12, none at 0.1.13, agnosai alone at 0.1.14 and again at 0.1.16), plus a
trailing `cyrius 6.6.14` line recording the toolchain that wrote it. agnosai 2.1.7 — and 2.1.6,
2.1.5 and 2.1.4, and ai-hwaccel 2.4.1, samay 1.1.6 and kavach 3.13.2 before them — was certified
the same way before its tag: its full CI steps in a sibling-free replica against an empty dep
cache (agnosai 2.1.7: 99 suites, 8,679 assertions, coverage 99%; and agnostic 0.1.15's 32 suites
passed against it). Every tag was confirmed on the GitHub remote before the lock was
written, and a sibling-free resolution from an empty dep cache reproduced `lib/` and the lock
byte for byte.

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
(0.1.8), checked by the server and with a crew surface a UI can build on (0.1.9), and its views over
the real surface (0.1.10)** — 50 files, 29,127 lines, 1,183 top-level definitions (0.1.16; 28,989
lines and 1,174 at 0.1.15), all `agnostic_*`-prefixed. 11,740 of those lines are generated:
`src/presets_data.cyr` (837) and `src/webgui_data.cyr` (10,903 — five embedded pages and the plugin
permission vocabulary).

**Tests: 33 suites, 2,784 assertions, 0 failed** (`cyrius test`, 0.1.16; 2,701 at 0.1.15), plus
**80 JavaScript tests** (`scripts/check-webgui-js.sh`, Node 20+; 80 at 0.1.15) — **and the
same 33 suites natively on aarch64, with the same per-suite counts** (Raspberry Pi 4). Gates
green: `check-symbols.sh` (4 rules — Rule 4, the `lib/`↔`lib/` constant check, is evaluated per
shipped target since 0.1.7), `check-clean.sh` (also `gen-webgui.sh --check`,
which since 0.1.10 verifies every plugin's copy of the bridge client; the WebGUI's JavaScript; and,
since 0.1.13, `check-skill.py`, the agent skill against the API schema, and `gen-api-schema.sh
--check` on `build/agnostic` when nothing in `src/` or `cyrius.cyml` is newer than it), `deps
--verify` 119/0.

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
| `src/engine/audit.cyr` | the tamper-evident trail, libro over patra; its newest 1024 entries kept for reading (0.1.10) |
| `src/engine/presets.cyr` | the canonical preset library, parsed once at mount |
| `src/presets_data.cyr` | **generated** — the 18 documents as Cyrius literals |
| `src/engine/settings.cyr` | deployment-wide settings, durable — the plugin switches (0.1.7) |
| `src/engine/plugindata.cyr` | each plugin's own documents, per tenant, durable (0.1.8) |
| `src/webgui/plugins.cyr` | the WebGUI's page table and plugin registry, loaded once at mount (0.1.7); the permission vocabulary and the plugin rung (0.1.9) |
| `src/webgui/permissions.json` | the plugin permission vocabulary — the one source the generator, server and shell read (0.1.9) |
| `src/webgui/kit/host.js` | the bridge client every plugin page carries verbatim (0.1.10, ADR 0010) |
| `src/webgui_data.cyr` | **generated** — the shell and each plugin page, verbatim, with SHA-256 and CSP (0.1.7) |
| `src/routes/health.cyr` | `/health` and `/ready` |
| `src/routes/crews.cyr` | the crew surface |
| `src/routes/definitions.cyr` | agent definition CRUD |
| `src/routes/presets.cyr` | the preset surface, read-only |
| `src/routes/plugins.cyr` | list plugins, switch one on or off (0.1.7) |
| `src/routes/webgui.cyr` | `/ui` and `/ui/plugins/{id}` — the pages (0.1.7) |
| `src/routes/plugindata.cyr` | a plugin's documents — list, read, write, delete (0.1.8) |
| `src/http/guard.cyr` | the transport rules: a JSON media type, a loopback Host (0.1.8) |
| `src/http/schema.cyr` | the API schema, built from the router's rows and the server's own tables; pure (0.1.13, ADR 0015) |
| `src/cli.cyr` | the command line: no arguments serves, `api schema`, `help`, anything else exits 2 (0.1.13) |
| `src/server/serve.cyr` | the only module that touches a socket |
| `src/app.cyr` | the canonical include order — **no definitions** |
| `src/main.cyr` | entry point alone; includes `app.cyr`; reads its arguments before the environment (0.1.13) |

⚠ **`src/app.cyr` exists so adding a route stops breaking every suite.** The
include order used to live in `main.cyr` and every suite reaching the router
reproduced it, so a new route module failed them all with "undefined function"
rather than "missing include" — three times across M2 and M3. `main.cyr` cannot
serve that role itself: its two trailing top-level statements run at include time
and would start a server inside a suite.

**The machine-readable surface is [`docs/api/generated/schema.json`](../api/generated/schema.json)**
(0.1.13, H5, [ADR 0015](../adr/0015-the-http-api-is-described-by-a-generated-schema.md),
[`docs/api/`](../api/README.md)): `./build/agnostic api schema` prints every route's method, path,
authentication, permission, lowest role and granting plugin permissions (each with the parameters it
pins to the plugin's own id), its success statuses and the kind and top-level keys of what it answers
(`?` for a key a success can leave out), the request bodies' allow-lists, the error codes, the
dispatch ladder and the vocabularies — read from the tables the server runs on where one exists, and
declared beside the generator where the handlers hold it. `tests/api_schema.tcyr` fails when the
committed copy differs, and checks each declaration against the handlers (response keys both ways,
on the real mount). The table below keeps what the schema deliberately leaves out: each handler's
refusal statuses.

The crew surface, and what each code means:

| route | codes |
|---|---|
| `POST /api/v1/crews` | **202** accepted (`task_ids`; `replayed` for a repeated `Idempotency-Key`); a task may carry selection hints — `required_tools`, `complexity`, `domain`, `gpu_required` (0.1.14, ADR 0017); the crew joins the request's trace (0.1.14, ADR 0018) · 400 semantic · 422 shape or key reused over another body · 503 engine down |
| `GET /api/v1/crews` | 200 — the caller's tenant's crews, newest first; `?limit=` `?before=` (0.1.9), `?status=` (0.1.10; `interrupted` since 0.1.13) · 422 |
| `GET /api/v1/crews/{id}` | 200 (with `usage`, times, `scope`); **`interrupted`** for a crew a restart cut short, where it answered 404 before 0.1.13 (ADR 0013) · 404 never submitted **or another tenant's** · 422 malformed id |
| `POST /api/v1/crews/{id}/cancel` | 200 · 404 · **409 already terminal** — also for a crew stored before a restart, `interrupted` included (0.1.15) · 422 · 503 |
| *(any)* | a method the path does not take: **405** with `Allow` naming the ones it does (0.1.15) |
| `GET /api/v1/crews/{id}/events` | 200 — refreshed first (0.1.8); `?after=N` cursor, `seq`/`at_ms`, `next`, `missed`, `lost_events` (0.1.9); a cursor older than the window gets every event still held and `missed` > 0 (the H3 gap signal) · 404 · 422 |
| `GET /api/v1/crews/{id}/plan` | 200 — agents and tasks with engine ids (0.1.9) and each task's hints (0.1.14); `?explain=selection[&task=N]`: each task's ranked candidates with their five scores, the `scorer`, a `candidate_limit` (0.1.14, ADR 0016) · 404 not held · 422 (also a bad `explain` or `task`) |
| `GET /api/v1/presets` | 200 — summaries, not documents |
| `GET /api/v1/presets/{name}` | 200 · 404 unknown name |
| `GET /api/v1/agents/definitions` | 200 |
| `POST /api/v1/agents/definitions` | **201** · 400 (also an unknown `complexity`, 0.1.15) · **409** · 422 · **507** |
| `GET /api/v1/agents/definitions/{key}` | 200 — with its revision, `etag` and an `ETag` header (0.1.15) · 404 · 422 |
| `PUT /api/v1/agents/definitions/{key}` | 200 · 400 · 404 · **412** stale `If-Match` (0.1.15) · 422 |
| `DELETE /api/v1/agents/definitions/{key}` | 200 · 404 · **412** stale `If-Match` (0.1.15) · 422 |
| `GET /api/v1/audit` | 200 — count, the chain's verdict at open, appended, dropped; since 0.1.15 `verdict` (`intact` / `restarts` / `altered` / `unverified`), `breaks` and `break_count` — **ADMIN** |
| `GET /api/v1/audit/entries` | 200 — the newest entries by index; `?limit=` `?before=` (0.1.10, ADR 0011) · 422 — **ADMIN** |
| `GET /api/v1/plugins` | 200 — with the permission `catalogue` (0.1.9) — READ |
| `PUT /api/v1/plugins/{id}` | 200 (`changed` true/false) · 400 · 404 · 422 · 500 — **ADMIN** |
| `GET /api/v1/plugins/{id}/data` | 200 — keys, times, sizes, `scope` · 404 · 422 — READ |
| `GET /api/v1/plugins/{id}/data/{key}` | 200 — the document, verbatim, with its `ETag` (0.1.9) · 404 · 422 — READ |
| `PUT /api/v1/plugins/{id}/data/{key}` | **201** · 200 · 400 · 404 · **412** (0.1.9) · 413 · 422 · **507** — WRITE |
| `DELETE /api/v1/plugins/{id}/data/{key}` | 200 · 404 · **412** (0.1.9) · 422 — WRITE |
| `GET /ui` · `/ui/` | 200 — the shell, **public** |
| `GET /ui/plugins/{id}` | 200 · **404 while switched off** · 422 — **public** |

[`skills/agnostic/SKILL.md`](../../skills/agnostic/SKILL.md) (0.1.13, H6) teaches a
coding agent the crew surface above, with herdr-style guardrails. `scripts/check-skill.py`, in
`check-clean.sh`, holds every route, method, query parameter, header, response example and marked
list in it to the API schema. Its prose (statuses, limits, behaviour) is not machine-checked; the
CHANGELOG (0.1.13, Verified) records the live run that confirmed it, and a change to this surface
should re-read the skill.

The table is a flat scan of 20 paths (21 patterns). Since 0.1.13 (H5) it is literally a table
— 21 rows of a pattern and the route id per method, built once at load, which the resolver walks
in the old order and `agnostic_route_row_pattern` / `agnostic_route_row_id` expose. Re-measured then,
in interleaved runs against a copy of the tree with the if-chain restored: 0.107 / 0.87 / 0.72 /
2.15 µs against 0.108 / 0.92 / 0.78 / 2.19 µs — no slower, a miss ~7% faster, because the walk calls
the matcher directly where the if-chain went through a wrapper for every pattern. `cyrius bench` at
the 0.1.13 cut: 0.109 / 0.86 / 0.72 / 2.12 µs, the plugin rung 1.24 µs, one new event 0.13 µs, a
256-event window 5.9 µs, a 50-entry audit page 28.5 µs, and a crew's in-flight mark and clear (two
fdatasyncs, on tmpfs) 159 µs. Measured at 0.1.10
(`tests/agnostic.bcyr`, with a suite running beside it): ~0.11 µs to resolve the first entry, ~0.93 µs
the last, ~0.79 µs for a miss that tries every pattern, ~2.2 µs for the two-capture document path —
against ~48 µs for the per-request user lookup. A request a plugin makes also pays the plugin rung,
~1.2 µs; a cursor poll copies one new event out of the ring in ~0.13 µs (a whole 256-event window
~5.9 µs); a 50-entry page of the audit trail is copied out of its ring in ~28 µs. (0.1.9, 19 paths:
0.10 / 0.87 / 0.73 / 2.0 µs; 0.1.8, 18 paths: 0.12 / 0.93 / 0.78 / 2.1 µs.)
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

## WebGUI and plugins (0.1.7 – 0.1.15)

**M9's first slice (0.1.7), its plugin platform (0.1.8), checked by the server (0.1.9), its views over
the real surface (0.1.10).** Why
compiled-in plugins switched at run time is [ADR 0004](../adr/0004-webgui-plugins-compiled-in-switched-at-run-time.md);
how a plugin reaches the server is [ADR 0005](../adr/0005-plugins-reach-the-server-through-the-host-bridge.md),
and why the server checks it too, against one vocabulary, is [ADR 0007](../adr/0007-plugin-requests-are-checked-by-the-server.md);
how views link to each other and share one client is [ADR 0010](../adr/0010-views-link-through-the-shell-and-share-one-bridge-client.md);
how to add one is [`guides/webgui-plugins.md`](../guides/webgui-plugins.md).

**0.1.10, in one paragraph.** Three views over the real surface — **Crews**, **Library**, **Audit
trail** — as plugins beside Swarm Command, starting OFF. A view's state is in the shell's URL
(`#plugin/<id>?<params>`); `init` carries `params` and the `views` switched on; a plugin opens another
view with `agnostic:navigate` (checked by the shell's pure `checkNavigate`) and hears its own params
change with `agnostic:params` (feature `navigate`). Every plugin carries `src/webgui/kit/host.js`
verbatim, and the generator refuses a copy that differs (`--sync-kit` rewrites them). Two permissions
joined the vocabulary: `definitions:write`, `audit:read`.

**0.1.9, in one paragraph.** Plugin permissions live in `src/webgui/permissions.json` and are enforced
by the server on every request the shell makes for a plugin (`X-Agnostic-Plugin` → the plugin rung,
before authentication: `403` with `plugin_unknown` / `plugin_off` / `plugin_forbidden`). The shell's
gate (`window.AgnosticBridge`, a pure script) is built from the same vocabulary, answers only the page
session that asked, takes messages only from an opaque origin, caps a plugin at 16 requests in flight,
and carries query strings, revisions and idempotency keys. Plugin documents have ETags; `If-Match` /
`If-None-Match: *` answer 412. Swarm Command 0.3.0 runs on real crews and real numbers — see below.

- **`/ui`** — the shell (39,929 B): Overview (`/ready`, the views), a tab per plugin that
  is switched on, Settings (the switches with each plugin's permissions and stored
  documents, the session). With `AGNOSTIC_AUTH=required` it signs in through
  `POST /api/v1/auth/login` and keeps the token per tab (`sessionStorage`). It is also the
  **host bridge**: it answers a plugin's `postMessage` requests that its manifest permits,
  with the user's token, which the plugin never sees.
- **Crews 0.1.2** (`crews`, 49,422 B, `data: live`, `crews:read`, `crews:write`) — the tenant's
  crews by status, a page at a time; a crew's plan, progress by cursor, each task's result with its
  tokens, cost and time, the totals (tokens only when metered, cost only when priced); cancel, asked
  inline; a cancelled crew followed until its finished tasks' results arrive; links to Swarm Command.
  Since 0.1.13: an **Interrupted** filter and pill, and an interrupted crew's `interrupted_at`.
  0.1.2 (with agnostic 0.1.15): each task names the agent that did it from the result's
  `agent_key`, so a finished crew, or one whose events are gone, still says.
- **Library 0.1.1** (`library`, 40,065 B, `data: live`, `presets:read`, `definitions:read`,
  `definitions:write`) — the presets and their agents; definitions listed, created, edited (key
  fixed), deleted; a preset's agent saved as a definition. 0.1.1 (with agnostic 0.1.15): a save or
  delete sends the revision it read as `If-Match`, and a 412 keeps the edits and says someone else
  changed the definition.
- **Audit trail 0.1.1** (`audit`, 28,182 B, `data: live`, `audit:read`) — the chain's verdict at
  start-up, its count and dropped appends, and its newest entries by index (severity and text
  filters; each entry's hash and whether it names the one before it, as sent). ADMIN routes.
  0.1.1 (with agnostic 0.1.15): the verdict as found — RESTART BREAKS (a warning, no alteration),
  BROKEN naming the first altered entry, UNVERIFIED — read as before from an older server.
- **Swarm Command 0.5.1** (`swarm`, 452,787 B, `data: mixed`, permissions `storage`,
  `presets:read`, `crews:read`, `crews:write`) — a launcher of saved swarms (plugin
  documents `swarm-<id>`, per tenant, written with their revision), an editor for every
  capability with defaults, a headless cost estimate over eight seeds — beside one agent at the
  swarm's own token spend (0.5.0) — the simulator driven by the spec, live runs — submitted with an
  idempotency key and recorded before they start, read by cursor, bound by engine task id, ended
  with the tokens and cost agnostic metered beside the estimate, outputs under Results — and a
  **Crews** list that watches any crew of the tenant (and links it to the Crews view). It follows
  `#plugin/swarm?crew=<uuid>` (0.4.0). Every mission is labelled SIM or LIVE; a live cost the
  gateway did not report is n/a, never simulated. 0.5.0 (with agnostic 0.1.13): a crew a restart
  interrupted ends the watch as **INTERRUPTED**, each unsettled task "Interrupted by a server
  restart" — without it the watch followed the crew forever (H4, first numbered 0.4.1); and every
  estimate carries a **one-agent baseline** (B3,
  [ADR 0014](../adr/0014-the-estimators-one-agent-baseline-is-its-own-model.md)) — `soloRun` works
  the swarm's own plan one task at a time on each seed, capped at the tokens the swarm spent there,
  shown SIM on the card and in the editor with what it does not model (answer quality, per-agent
  context). The Sim is untouched, so every swarm estimate is what it was. 0.5.1 (with agnostic
  0.1.15, ADR 0017): with its role roster each agent carries `domain` (its role) and `tools` (the
  kinds the role uses), and each task the same `domain` and `required_tools`, so the engine gives
  each task to its role's agent; a preset roster sends none.
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
opaque origin, so a plugin cannot read the shell's token, reach the network, open a
modal dialog — or submit a form: without `allow-forms` the `submit` event never fires (found live
at 0.1.10; the Library saves on a click). Opened in its own tab, Swarm Command finds no shell, keeps swarms in that
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

⚠ **Verified in headless Chromium at 0.1.10** against a scratch server running real crews through a
stand-in gateway that prices calls: **31 checks** with auth off — the Crews list, filter and detail, a
crew's metered tokens and cost, deep links, a crew cancelled mid-run keeping its finished task's
result (on screen and on the server), Watch in Swarm Command, Library create / edit / delete, the Audit
trail's verdict, entries and links, a reload keeping the open crew, a navigate to a view that is off
refused — and **10** with auth required (sign-in through the shell, the ADMIN audit routes through the
bridge, sign-out leaving the view). No uncaught exception. It found two bugs the Node tests could not:
the cancel rule read an empty results vec as "has results", and a sandboxed form never submits.
Chromium now isolates sandboxed frames in their own process; the driver runs with
`--disable-features=IsolateSandboxedIframes` to reach the frame's context.

At 0.1.9 (CDP; the plugin frame was in-process, reached through its execution context), against
scratch servers running real crews through a stand-in gateway that prices calls: auth off — 29 checks, from the bridge features through a live crew's
metered cost, results, the run record, watching, the Crews list, a crew from a script, a two-tab
conflict and switching the plugin off under an open view; auth required — 13, including a session
invalidated mid-crew pausing and resuming the watch; the standalone page — 7. No uncaught exception
in either frame. (0.1.8: 112 checks, much of the same ground before these changes.)

✅ **The page's logic is tested in the repo now** — `tests/webgui/` under Node (`check-clean.sh` runs
it): the shell's gate against the real vocabulary, and Swarm Command's simulator, specs, library and
live crew source against a fake agnostic that answers as the server does at 0.1.13 (the event
cursor's `missed`, a crew a restart left `interrupted`). At 0.1.8 the 225 assertions that covered
this ran once and were discarded.

The Python implementation is retained at `python-port/` as a behavioural oracle.
It is never built or shipped, and it is **not** a specification —
[`ORACLE-AUDIT.md`](../../ORACLE-AUDIT.md) records 86 verified defects in it.

## Tests

**33 suites, 2,784 assertions, 0 failed** (`cyrius test`, under the 6.6.14 pin, 0.1.16, 2026-10-08;
2,701 at 0.1.15), and **80 JavaScript tests** (`./scripts/check-webgui-js.sh`; 80). 0.1.16's
additions, each guard mutation-checked (CHANGELOG [0.1.16]): a new suite, `tests/server_span.tcyr`
(55 — the SERVER span through the real handler, a crew's `invoke_workflow` under it, and 0 B per
request on the global heap through the handler), `trace/child` and `trace/begin` (+20), and the
route-pattern checks in `router/table` (+8).
At 0.1.15: 32 suites and 2,701 assertions. Its additions, each guard mutation-checked (CHANGELOG
[0.1.15]): a new suite, `tests/request_alloc.tcyr`
(16 — what a request keeps on the global heap); `audit/failed-write`, `audit/restart-breaks` and
`audit/unverified`; `crewstore/partials` and `crewstore/refresh-keeps`; `restart/one-process`;
`router/definition-revisions`, `router/definition-complexity` and the `Allow` probes in
`router/table`; `request/agent-complexity` and `request/swarm-roles`; `serve/allow-on-405`;
`outcome/agent`; the `defer` pin in `rlock/ownership`; and the API schema's checks now refuse a key
written twice and probe six headers. Every suite keeps its stores under `$TMPDIR` since 0.1.15
(`tests/support/tmp.cyr`).
At 0.1.13: 31 suites, 2,347 assertions (every suite natively on aarch64 on the Pi, Ubuntu 26.04.1,
with the same counts), and 77 JavaScript tests. At 0.1.12: 29 suites, 1,885 assertions
(unchanged since 0.1.10; every suite also passed natively on the Pi then — 0.1.11's re-pin was not
re-run there) and 61 JavaScript tests. 0.1.13's additions (CHANGELOG [0.1.13]):
`tests/crews_route.tcyr` +20
(`crews/events-gap`: the cursor's gap over HTTP, H3) and `crews.test.mjs` +1 (a gap counted once,
its task settled by the outcome); and for H4 (`interrupted`, ADR 0013) `tests/outcome.tcyr` +3,
`tests/ledger.tcyr` +1, `tests/crewstore.tcyr` +58 (`crewstore/inflight`, `inflight-after-outcome`,
`sweep`, `sweep-keeps-outcome`, `cancel-then-restart`, and the no-store case), `tests/crews_route.tcyr`
+20 (`crews/inflight-mark`, `crews/interrupted-not-404`, and the collector clearing the row),
`tests/crew_tenancy.tcyr` +18 (`tenancy/interrupted`, and the filter in `list-status`), a new suite
`tests/restart.tcyr` (14 — the real mount on a seeded database), and `crews.test.mjs` +1 and
`swarm.test.mjs` +1. Each guard was mutation-checked: dropping it fails a named assertion. H3's gap
in Swarm Command's live watch, `swarm.test.mjs` +1 (counted once in EVENTS MISSED, every task still
settled from the outcome; three mutations of the page fail it). For B3
(the one-agent baseline, ADR 0014) `swarm.test.mjs` +12 — deterministic; every number `SOLO`
restates checked against its Sim method's source; the swarm's own plan on each seed; never past its
budget, out of tokens only at it, and what is left counted; ⭐ the estimate paired seed by seed, with
the swarm's figures recomputed from the Sim and pinned to 0.4's; ⭐ every template's eight-run
estimate pinned to 0.4's; ⭐ every template's eight-run baseline pinned bit for bit, and to ADR 0014's
table; a 0.4 estimate still reads, a baseline round-trips clamped; the card's SIM line; the editor's
SIM box; ⭐ each shown where it belongs, through the page's own card and side-panel renders — each
guard mutation-checked, failing a named test.
For H5's first change (the route table as rows) `tests/router.tcyr` +67 (`router/table`: every one of
the 27 arms round-trips its own concrete path to its own id and captures, every route id has an arm,
the table has room left, an unknown verb is 405 on a known path) — each guard mutation-checked.
For its second (the closed catalogues) +63: `tests/health.tcyr` +29 (`http/error-codes`: exactly four
codes, each name and status pinned; the build refused no code, and a gap, a repeat or a row past the
storage is refused a row; no row for 0 or past the last, no other value a code at any power of two or
beside one; an unlisted one, 0 and the one past the last a 500 with no `code`; the coded constructor on
a full arena), `tests/agentdef.tcyr` +17 (`agentdef/refuse-rows`: the twelve refused fields in order,
each refused with the message that names it), `tests/authz.tcyr` +8 (`perm/names`), `tests/router.tcyr`
+4 (each method round-trips through its name), and the coded refusals' whole bodies, byte for byte —
`tests/webgui.tcyr` +3, `tests/plugindata.tcyr` +2 — each guard mutation-checked.
For the audit chain's restart link (a fix, older than 0.1.13) `tests/audit.tcyr` +24
(`audit/durable-append`, 18: append, reopen, append, reopen, intact, and every link read back through
libro; `audit/tamper` names the edited entry exactly and re-verifies, +2, and an entry recorded after
reopening the altered trail links to its last stored entry, +4) — each guard mutation-checked.
For a crew named over 255 bytes (a fix, older than 0.1.13) `tests/crewstore.tcyr` +26
(`crewstore/long-name`, 12: four long names stored, each document byte for byte, and the `cname`
column cut on a character; `crewstore/long-name-sweep`, 14: two long-named crews in flight are
interrupted and the in-flight count reaches 0) — each guard mutation-checked.
For H5's third and fourth changes (`agnostic api schema`, ADR 0015) a new suite, `tests/api_schema.tcyr` (148):
`api/snapshot` (the generator, compiled fresh, prints exactly `docs/api/generated/schema.json`),
`api/routes` (27 routes, each resolving through the router with the auth and permission it states),
⭐ `api/plugin-vocabulary` (every `permissions.json` route names exactly one real route, which lists
the grant with the parameters its `:self` pins — ADR 0007's silent rename now fails), `api/bodies`, `api/vocabularies` (each round-trips
through its real parser), `api/errors` (the catalogue, and seven of the eight ladder rungs driven
through the dispatcher in order), `api/cli` (the parse, and ⭐ each command's exit code and what it
writes where), and ⭐ `api/probes` (each declared body, query parameter and header driven against its
handler; every GET route ignores the known parameters it does not declare; each grant's `self`
against the plugin gate) — fifteen mutations each fail a named assertion — and, for the fourth
change, ⭐ `api/responses` (14: the real mount with auth required drives every route's success path,
and each answer's status, kind and keys must match its declaration; then every route, every status
`ok` lists and every declared key, optional ones too, must have been seen) — eleven more mutations,
each failing a named assertion.
0.1.10's additions:
`tests/ledger.tcyr` (a cancelled crew takes its results once — including over the engine's empty
vec), `tests/crewstore.tcyr` (the stored outcome rewritten once, across a reopen),
`tests/crew_tenancy.tcyr` (the status filter, across pages), `tests/audit.tcyr` (the ring: newest
first, seeded at open, bounded at 1024, a UTF-8-safe cut, the route and its cursor), `tests/webgui.tcyr`
(four plugins, each OFF at start, the new permissions on the rung), `tests/serve_mount.tcyr` (sigil
3.13.6's crypto contract); under Node, `kit.test.mjs` (the bridge client every plugin carries),
`crews`, `library` and `audit` against fakes, and the shell's route parser and navigate gate.
0.1.9's additions:
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

**agnosai 2.1.7** (`modules = ["dist/agnosai.cyr"]`), linked in-process rather
than called over HTTP. Everything crew/task/agent/scheduling-shaped lives there;
Agnostic owns the product tier. Versions and pins: see the table under
[Dependencies](#dependencies) above.

`lib/` holds **119** `.cyr`: **112** from the 6.6.14 stdlib snapshot (`unicode/` included) plus 7 dep
dists (`agnosai`, `bote-core`, `majra`, `ai-hwaccel`, `tyche`, `kavach`, `libro`).
`deps --verify` 119/0. The compile set `check-lib-symbols.py` resolves is **53**
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
| API snapshot (0.1.13) | [ADR 0015](../adr/0015-the-http-api-is-described-by-a-generated-schema.md): `docs/api/generated/schema.json` is `agnostic api schema`'s output — checked fresh by `tests/api_schema.tcyr`, on the DCE binary in CI (`gen-api-schema.sh --check`, under a 60 s limit, and "Command line exit codes"), and by `check-clean.sh` when `build/agnostic` is current; every `permissions.json` route checked against the router, and each grant's `self` against the gate; every route's success statuses and response keys checked both ways on the real mount (`api/responses`) |
| agent skill (0.1.13) | `skills/agnostic/SKILL.md`; `scripts/check-skill.py` in `check-clean.sh` checks its frontmatter, and every route, method, query parameter, curl header, response example and `<!-- schema: … -->` list against `docs/api/generated/schema.json`; 22 mutations, each failing by name |
| views (0.1.10) | [ADR 0010](../adr/0010-views-link-through-the-shell-and-share-one-bridge-client.md): a navigate only to a view that is switched on, params in a fixed alphabet (`shell.test.mjs`); every plugin's bridge client verified byte for byte by the generator |
| aarch64 (0.1.10) | every suite and the server run natively on a Raspberry Pi 4 before an aarch64 artifact ships |
| symbols | `check-symbols.sh` OK — 1,183 top-level definitions across 50 files, no duplicates, all prefixed (0.1.16; 1,174 at 0.1.15) |
| request allocations (0.1.15) | `tests/request_alloc.tcyr`: every refusal arm, an authenticated read, a failed and a successful login, and an audited write keep 0 bytes of agnostic's own on the global heap; an audited request keeps only libro's entry (roadmap, Memory). Since 0.1.16 the serve adapter around dispatch too: `tests/server_span.tcyr` holds a request through the real handler to 0 B, with its span recorded or not |
| server spans (0.1.16) | [ADR 0020](../adr/0020-each-request-records-an-http-server-span.md): one SERVER span per request when OTLP is on, under the request's own span id; a crew's `invoke_workflow` under it, in one trace; ten mutations in `tests/server_span.tcyr`, each failing by name |
| one process per database (0.1.15) | mount claims `<db>.owner` with an exclusive `flock` before anything opens; `restart/one-process` holds a claim from a separate open and checks mount refuses and sweeps nothing |
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

**One patra database, ten tables**, behind `src/engine/store.cyr`:
`agnostic_definitions (dkey, doc)`, `agnostic_crews (crew_id, cname, cstatus, doc)` (`cname`, never
read, holds at most the name's first 255 bytes, cut on a character, since 0.1.13),
the identity tables `agnostic_users`, `agnostic_apikeys` and `agnostic_tenants` (M5),
`agnostic_settings (skey, sval)` (0.1.7), `agnostic_plugin_data` (0.1.8),
`agnostic_crew_index` (0.1.9 — one row per terminal crew, indexed on `scope`, what the listing reads), and
`agnostic_crew_inflight` (0.1.13 — one status-less row per accepted crew with no outcome
yet, ADR 0013), and `agnostic_crew_partial` (0.1.15 — the output of each task the model answered,
while its crew has no outcome, ADR 0019). patra allows exactly **one index per
table** — `SCH_IDX_COL` is a single slot in the schema page — so each gets it on the
column everything looks up by, except `agnostic_crew_inflight` and `agnostic_crew_partial`, which
have **none on purpose**: their live rows belong only to the crews in flight, so a delete scans a
few pages, where an index would keep a tombstone per crew or task ever run until VACUUM. The audit chain has its own file: `patrastore_open`
opens its own handle. What survives a restart, table by table, is
[`architecture/001`](../architecture/001-what-survives-a-restart.md).

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
`defer` may release it since 0.1.15: cycc 6.6.6 skipped a `defer` on `return f(...)`,
cyrius 6.6.7 fixed it, and `rlock/ownership` pins the fix at the pin.

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

✅ **aarch64 — the SIGBUS of 0.1.7–0.1.9 is fixed upstream, and the artifact is released again.**
Root-caused on the Pi at 0.1.7: a typed-array global (`var a: u8[N]`) left the next global
unaligned, and sankoch's `u8[363]`/`u8[217]`/`u8[50]` misaligned 1,101 globals after them — twelve
used atomically, sigil's crypto init flags among them — so `ldaxr` faulted on aarch64 (never on
x86). Filed as `cyrius/docs/development/issues/2026-10-01-typed-array-globals-not-padded-aarch64-atomics-sigbus.md`
and fixed in cyrius 6.6.13 (I9): every global now starts at its natural alignment. Since 0.1.10
(6.6.14) `agnostic-aarch64` is released again, and every suite and the server run natively on the Pi
4 (`ssh pi`) at each release.

⚠ **Only terminal crew outcomes are stored, and a crew in flight is an obligation, not a
status** (0.1.13, [ADR 0013](../adr/0013-a-crew-interrupted-by-a-restart-is-interrupted.md)).
A running crew's thread dies with the process, so persisting non-terminal state would load a crew
that claims to run and never will. Instead, submit writes a status-less row to
`agnostic_crew_inflight`, the outcome write deletes it in the same critical section, and mount —
after the audit chain opens, before the server listens — turns every row still there into a
terminal **`interrupted`** outcome (listed, audited as `crew.interrupted`), keeping what was known
at submit and, since 0.1.15, the outputs its finished tasks sent (ADR 0019), but no usage or cost.
Until 0.1.13 such a crew answered 404 after a restart. ⚠ This needs **one agnostic process per
`AGNOSTIC_DB_PATH`** — a second one would sweep the first one's live crews — and since 0.1.15 mount
enforces it: an exclusive, non-blocking `flock` on `<db>.owner`, taken before anything opens, and a
second process refuses to start.

✅ **The two sibling-library work-arounds of 2026-08-21 are gone** (removed 2026-08-22, see
Dependencies above): patra 1.13.10 stopped `patra_init` stomping the host's log level, and libro
2.8.9 stopped a `PatraStore` read from another thread killing the process.

## Next

See [`roadmap.md`](roadmap.md). After 0.1.16: the cyrius pin move through its
sibling chain (kavach and libro, bote, agnosai, then agnostic), held for now by the user; agnosai's
F1 tool loop and F9's hand-off of dependency outputs (M6's prerequisites, with the tool-registry
decision of `handoff.md` §8); and what 0.1.15 recorded upstream (libro's per-append entry, patra's
unchecked page write, cyrius's pkgver two includes deep). The notes below were written for M5 and remain true.

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
- ~~**The crew routes are unauthenticated.**~~ The dispatch ladder's auth rung has been wired
  since M5, and crews belong to their tenant since 0.1.9 (ADR 0008).
- **The ledger is memory-resident and capped.** It retains 1,024 crews and 256 progress events
  each. Terminal outcomes are durable since M4 (and an interrupted crew since 0.1.13), so a crew
  the ledger dropped still answers from the store; only its events and plan are gone.
