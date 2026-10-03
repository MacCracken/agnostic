# agnostic — Roadmap

> Milestone plan through v1.0. State lives in [`state.md`](state.md);
> orientation for picking the port up lives in [`handoff.md`](handoff.md);
> this file is the sequencing — what ships, in what order, against
> what dependency gates.

## Shape of the port

**Agnostic 1.0.0 is roughly a third of the Python tree.** AgnosAI owns the entire *engine* tier —
crews, tasks, agents, DAG/priority scheduling, agent scoring, LLM routing through hoosh, the tool
registry with four sandbox tiers, fleet coordination, multi-tenant budgets, approvals, the audit
chain, durable state, SSE, Prometheus and OTLP telemetry, RL learning, definition
versioning/packaging, the crew assembler and the preset library.

What remains is the **product** tier: the HTTP and MCP surfaces consumers bind to, the QA domain
tools, identity and tenancy, persistence and reporting, and the GUI. Sequencing below follows
dependency order, not the Python tree's layout — see [`../../CYRIUS-PORT-BRIEF.md`](../../CYRIUS-PORT-BRIEF.md)
for the three-way split of ported / delegated / dropped.

The oracle at `python-port/` is a **behavioural reference, not a specification**.
[`../../ORACLE-AUDIT.md`](../../ORACLE-AUDIT.md) records 86 verified defects in it; several of its
paths are wrong, and reproducing them faithfully would reproduce the bugs. Check that document
before porting any behaviour.

## v1.0 criteria

- [ ] Public API frozen — every exported symbol documented and tested
- [ ] `python-port/` retired — the Cyrius tree has equal or better coverage
      (`first-party-standards.md:53`). ⚠ The benchmark half of that rule cannot be satisfied as
      written: `ORACLE-AUDIT.md` §4 shows the oracle's published numbers are invalid, so parity is
      assessed on coverage and behaviour, not on its timings.
- [ ] Benchmarks captured in `BENCHMARKS.md` with a CSV trail
- [ ] At least one consumer green against the published API — Agnostic's own, not a
      pre-existing client's contract (see M7)
- [ ] CHANGELOG complete from v0.1.0 onward
- [ ] Security audit pass re-run (`docs/audit/YYYY-MM-DD-audit.md`)
- [ ] Zugot recipe published (`zugot: marketplace/agnostic.toml`)

## Milestones

### M0 — Scaffold + P(-1) hardening (v0.1.0) — ✅ 2026-08-20

- `cyrius init --language=none .` scaffold, GPL-3.0-only, pin 6.5.32
- Root docs, `scripts/{check-symbols,check-clean,version-bump,bench-history}.sh`
- CI raised to the three spec-required jobs (`build`, `security`, `docs`), plus a
  **fatal toolchain-drift gate** — the failure mode that broke AgnosAI 2.0.2 in CI
- P(-1) complete: audit-clean, 0 CRITICAL/HIGH/MEDIUM, baseline benches seeded

### M1 — HTTP foundation (v0.2.0) — ✅ 2026-08-20

- `sandhi` HTTP/1.1 pooled server, `:name` routing, per-request arena with SPILL
- Config from environment, strictly parsed — a malformed value refuses to start
- `sakshi` structured logging with a JSON emit hook; thread-local W3C trace ids
- `/health` (liveness) and `/ready` (readiness registry) — ADR 0001
- `bayan` allow-list codec: an unlisted field is a 422 naming it, never a silent discard
- Signal-driven graceful shutdown via `signalfd` on a dedicated thread

**215 assertions across 7 suites**, 0 failed. All CI gates green. Verified live over a socket:
200/404/405, `?query` handled, trailing slash distinct, SIGTERM drains and exits 0.

**Gates met:** arena exhaustion returns 0 rather than a half-built record, tested for the trace and
both response constructors. Security audit re-run —
[`docs/audit/2026-08-20-audit-m1.md`](../audit/2026-08-20-audit-m1.md), 0 CRITICAL / 0 HIGH /
1 MEDIUM (rate limiting, deliberately deferred to M5 where it belongs with the credential path).

### M2 — AgnosAI integration (v0.3.0) — ✅ 2026-08-21

- `[deps.agnosai]` → `dist/agnosai.cyr`, linked in-process
- Crew submit / status / cancel via `agnosai_orchestrator_submit_crew` (**D2**)
- 202-then-poll semantics; live progress off the event bus

**267 new assertions across 4 suites** (496 total across 12), 0 failed. All three gates green.
Verified live over a socket: 202 with the engine's id, poll to `completed` with results, progress
events drained (`crew_started` → `task_started` → `task_completed` → `crew_completed`), uppercase id
normalised, 404/405/409/422/503 each on its own path, SIGTERM drains and exits 0.

**Gates met.** Each of the four §3 failure modes is designed out rather than avoided:

| Defect | The mechanism that makes it unrepresentable |
|---|---|
| §3.1 failed reported as completed | `_agnostic_outcome_normalise` demotes COMPLETED-with-no-results to FAILED *before* the record exists |
| §3.2 cancel addressing an unknown id | every id originates in `agnosai_crew_new`; Agnostic mints none, and a refusal is returned rather than discarded |
| §3.3 two task models | `tasks` required and non-empty, no fallback path, unlisted key is a 422 naming it |
| §3.4 terminal overwritten | `agnostic_ledger_latch` refuses to write over a terminal status |

**✅ Decided 2026-08-21 — no `[deps.majra]`. The engine already owns the queue.**

An earlier draft of this milestone said "`majra` owns the queue".
`agnosai_orchestrator_submit_crew` already does: it registers the crew, publishes its cancel flag,
and runs it on a detached thread. A second in-memory queue in front of that would be **a second
source of truth for status** — the exact shape of §3.4, added deliberately.

`lib/majra.cyr` also exports ~40 unprefixed names and a set of unprefixed enum members
(`ERR_NONE`…`ERR_IPC`). Those are collision-free against today's compile unit, but the M1 lesson was
a `var BACKEND_COUNT` collision nothing warned about, and taking on that surface for a queue we do
not need is a bad trade. Durable queueing belongs with **M4**, against a real durability
requirement; `src/engine/ledger.cyr` is the seam it will land on.

⚠ **Two engine behaviours found here that bite only the async path.** Neither is among the 85
audited oracle defects — both were found building this milestone, and both are worked around in
Agnostic rather than upstream:

- **A cyclic DAG submitted asynchronously reports `pending` forever.** `agnosai_crew_runner_run`
  returns 0 on exactly one arm, and `_agnosai_orch_finish_err` then returns *without touching the
  crew map*, which `_agnosai_orch_register` has already seeded with PENDING. The blocking caller
  sees the 0; `_agnosai_orch_submit_thread` discards it. Closed by rejecting cycles before submit.
- **A finished crew can be evicted and then 404.** `_agnosai_orch_evict_locked` drops every finished
  crew at 1000 registered, making a successful run indistinguishable from a typo'd id. The ledger
  answers from its own latched outcome.

⚠ **`AGNOSTIC_CREW_MAX_CONCURRENT_TASKS` was removed before it shipped.** The budget slot exists but
`agnosai_orchestrator_budget` has zero call sites and nothing reads
`max_concurrent_tasks` — it is stored, serialised, and enforced by nothing. `max_duration_secs` is
genuinely read, so `AGNOSTIC_CREW_TIMEOUT_SECS` stays.

### M3 — Definitions, presets, agents (v0.4.0) — ✅ 2026-08-21

- Agent definition CRUD; preset listing
- Every field either forwarded or explicitly rejected — never silently dropped

**121 new assertions across 2 suites** (702 total across 14), 0 failed. All three
gates green. Verified live: 201/409/404/422/507 each on its own path, the twelve
refusals each answering by name, and the preset library served end to end.

⚠ **The field-forwarding gate grew a third disposition.** "Forwarded or rejected"
turned out to be too few: `focus` and `allow_delegation` are carried by the
canonical preset library, so dropping them would lose Agnostic's own content —
and the engine has no slot for either, so forwarding is impossible. They are
**retained** and **named** in an `unforwarded` array on every response. Three
dispositions, all visible on the wire, no fourth.
  (`ORACLE-AUDIT.md` §2.2 lists six fields the oracle dropped, `gpu_strict` being the sharp one:
  a hard-fail GPU requirement became a silent CPU fallback)

**✅ Decided 2026-08-20 — Agnostic's preset library is canonical; AgnosAI streamlines to examples.**

The two sets are not two versions of one library — they are unrelated content sharing a naming
scheme. 18 each, 15 names collide, and **not one** of the 15 has a matching description, agent
roster or tool vocabulary. Agnostic's presets name 38 PascalCase QA tool classes; AgnosAI's name 23
snake_case capabilities. **The intersection is empty.** Agnostic's documents also carry five fields
AgnosAI's schema has no slot for (`workflow_mode`; per-agent `focus`, `celery_queue`,
`redis_prefix`, `allow_delegation`) — which its parser would silently discard, the exact failure
this milestone forbids.

Serving an AgnosAI preset through Agnostic would name tools Agnostic cannot resolve, and a registry
miss is **silent**: the crew assembles empty rather than erroring.

This is a decision about **content, not linkage** — Agnostic still calls AgnosAI for execution.

→ **Cross-repo follow-up (agnosai):** streamline its preset set to a small illustrative example
library rather than a competing production one, so the two stop diverging by accident.

→ **M3 task — ✅ answered 2026-08-21, and the answer is no.** The presets were never viable, in the
oracle itself. See `ORACLE-AUDIT.md` §3.15:

- The 18 presets hold **76 agents** naming **38 distinct** PascalCase tool classes.
- The oracle's `_REGISTRY` is **never populated** — `register_existing_qa_tools()` has exactly one
  occurrence in the tree, its own `def` line. Every one of the 38 resolves to `None`, and
  `_resolve_tools` logs a warning and **skips**, so every agent is built with `tools=[]`.
- **Two of the 38 have no implementation anywhere** — `ArtifactManagementTool` and
  `CIPipelineIntegrationTool`, both named by `quality-large.json`. The other 36 exist as classes.

So the preset tool vocabulary is a **specification of intent, not observed behaviour** — the same
category as the identity surface in M5, and it must be read the same way. Port the presets as
*documents*; do not treat their tool lists as evidence that anything worked.

⚠ **The viability gate moves to M6, where it can actually be evaluated**, and M3 carries the half it
can: the 38-name union is pinned as a manifest, and a preset naming an unresolvable tool must be an
**error**, never a silently smaller agent.

### M4 — Persistence + audit chain (v0.5.0) — ✅ 2026-08-21

- `patra` for crews, results and agent definitions
- `libro` tamper-evident audit chain

**60 new assertions across 2 suites** (771 total across 16), 0 failed. All three gates green.
Verified live across real process restarts: a definition, a completed crew's results, and the audit
chain each survive; a byte edited in the audit file is **detected** with the failing entry named.

⚠ **Sessions and tenants were cut from M4 and belong to M5.** The line above said "sessions, crews,
results, tenants", but tenancy is identity-shaped and M5 already owns "Tenant CRUD in `patra`" —
building it here would mean designing a tenant model before the identity model that gives it
meaning, and the oracle's identity surface is mostly dead code (M5's own warning). Crews, results
and definitions are what M2 and M3 actually produce, and those are durable now.

⚠ **Only TERMINAL crew outcomes are persisted, and that is the design.** A crew runs on a detached
thread; when the process dies the thread dies with it, so a PENDING or RUNNING crew is not
resumable — it is gone. Writing non-terminal state would load, on the next start, a crew claiming to
run that never will, and the ledger's terminal latch could never correct it because the wrong value
would be latched first. Writing only COMPLETED / FAILED / CANCELLED removes the problem instead of
guarding it: there is no stale "running" to load because one is never written. A crew interrupted
mid-flight 404s after a restart, which is true.

**Durability seams:** one patra handle (`src/engine/store.cyr`) shared by the definition and crew
tables — patra allows 63 tables and exactly one index each, so `dkey` and `crew_id` get them. The
audit chain keeps its own file because `patrastore_open` opens its own handle.

⚠ **Two sibling-library defects found and filed** (2026-08-21), both worked around rather than
blocking:
- `patra_init` ends with an unconditional `sakshi_set_level(SK_WARN)`, silently discarding the
  operator's log level — filed as a consumer request in `patra/docs/development/requests/`.
- libro's `PatraStore` caches prepared statements at open, and patra's SQL parse scratch is
  per-thread, so reading the store from a pool worker **kills the process** — filed at the top of
  `libro/docs/development/roadmap.md`'s active patch line. Audit verification therefore runs once,
  at open, on the main thread.
- Path-traversal validation on every externally-derived path (audit point 6)

**✅ Audit point 6 answered 2026-08-21 — the surface does not exist yet, and M4 did not create
it.** Re-running the audit's own probe over `src/` finds **zero** filesystem calls. Exactly two
paths reach the disk — `patra_open` and `patrastore_open` — and both take **operator config**
(`AGNOSTIC_DB_PATH`, `AGNOSTIC_AUDIT_PATH`), never request input.

M4's persistence is a *database keyed by validated identifiers*, not a filesystem layout, so
nothing a client sends becomes a path component. The identifiers that would matter are already
closed sets: agent keys are `[a-z0-9][a-z0-9-]*` (`agnostic_key_is_valid`), preset names are a
compiled-in library of 18, and crew ids are UUIDs — a key that cannot contain `/` or `.` is safe
**by construction** rather than by a `../` check.

⚠ **It genuinely re-opens at M8**, not here: report and artefact storage is the first thing that
builds a filename from user-supplied text. Keep `agnostic_key_is_valid` narrow for that reason.

⚠ `patra` is an embedded single-file store, `flock`-arbitrated, with **no client/server mode** —
the oracle's multi-container "everyone talks to postgres" topology cannot be reproduced.

### M5 — Identity + tenancy (v0.6.0)

**✅ Decided 2026-08-20 — Agnostic owns identity, thin, adapted from SecureYeoman's Cyrius probe.**

- HS256 JWT issue + verify, adapted from `secureyeoman/yeo-cy-test/src/auth.cyr` (541 lines, working)
- Argon2id credentials via `sigil` at sy-core's parameters (m=19456, t=2, p=1)
- API keys — `sigil` SHA-256 + `ct_eq_bytes` constant-time compare
- Tenant CRUD in `patra`, tenant key-prefixing, static role→permission table
- Webhook HMAC-SHA256
- External-IdP verification as an **additive** mode behind a fn-pointer validator

⛔ **"Delegate to kavach" was struck, not weighed.** kavach has *zero* identity surface — a grep for
user/role/apikey/tenant/jwt/oauth/session across all 48 files of `kavach/src/` returns nothing.
`credential.cyr` injects secrets *into* sandboxes; it authenticates nobody. There is no ecosystem
IdP either (`iam` is a neofetch clone, `aegis` a policy daemon, `phylax` threat detection).

⚠ **Do not port the oracle's identity surface faithfully — most of it has never run.**
Local password login cannot succeed (`_authenticate_local` reads `password_hash`, but `User` has no
such field, so the writer's guard is permanently false); no user can create an API key (everyone is
`VIEWER`, no role assignment exists, the endpoint needs `SUPER_ADMIN`); tenant API keys are
read-only (the validator reads a key nothing writes); the three OAuth providers are unreachable (no
caller passes a provider). **None of this is among the 86 audited defects** — it was found while
deciding this. Scope covers what the oracle actually executes.

⚠ **Carry SY's login-abuse controls over — they are load-bearing, not polish.** Argon2id at ~244 ms
makes login a request-amplification lever: 8 concurrent attempts pushed `GET /health` from 6 ms to
942 ms, and ~40 wedged a 4-worker pool. A per-IP token bucket and a worker-concurrency cap both shed
with 429 **before** any Argon2 work.

⚠ **Three `patra` constraints to design around, not discover:** one index per table (so user-by-email
and user-by-id need two tables or a scan), per-write fsync by default (never rewrite a key blob on
every validation, as the oracle does), and single-writer (fine for a read-dominated verify path;
key creation serializes).

### M6 — QA tool surface (v0.7.0)

- The QA tools (**D4**). The 5–8 figure in `first-party-standards.md:625` is a soft guideline for
  typical projects, not a ceiling for platform-scale ones.

⚠ **The count is 38, not 28.** Corrected 2026-08-21 by extracting the union of every tool name across
the 18 presets: **38 distinct classes**, of which **36 exist** in the oracle and **2 do not exist at
all** (`ArtifactManagementTool`, `CIPipelineIntegrationTool`, both named by `quality-large.json`).
None of the 36 is ever registered — `ORACLE-AUDIT.md` §3.15 — so none has ever run, and each must be
treated as a fresh implementation against its preset-declared intent rather than as a port of
working code.

**M6 owns the viability gate M3 could not evaluate**: every name in the manifest M3 pins must
resolve in the Cyrius registry, and the two that have no implementation must be either written or
struck from the presets that name them. A registry miss must be an error, not a smaller agent.
- Sandboxing **delegated to kavach** — `first-party-standards.md:76`: *"kavach owns the sandbox,
  not the application."* The oracle hand-rolled an rlimit subprocess; do not repeat it.
- Browser automation via `yantra`; CV pipeline on chitra + ranga + rosnet

**Prerequisite:** `yantra` needs `Page.captureScreenshot` on its CDP surface.

### M7 — MCP surface + A2A (v0.8.0)

- JSON-RPC 2.0 MCP at `/mcp`, on `bote`
- REST tool invocation at `/api/v1/mcp/invoke`
- A2A callback endpoint

**Both MCP shapes stand (D5), on their own merit.** The original justification was preserving
SecureYeoman's live client; that is gone (see below), but the decision is unchanged — JSON-RPC is
the MCP standard for tool clients, and the REST shape is what scripts, the WebGUI and any
non-MCP-aware caller actually want. The **28-tool** surface is settled: the 5–8 figure in
`first-party-standards.md:625` is a soft guideline for typical projects, not a ceiling for
platform-scale ones.

**Agnostic stands on its own.** An earlier draft treated SecureYeoman's live 43-tool client as a
*frozen wire contract* that this milestone had to preserve, on the assumption SY reaches the engine
through Agnostic. It does not have to: **SY can consume AgnosAI directly**, since AgnosAI 2.0.2+
ships both a `/mcp` surface and `dist/agnosai.cyr` for in-process linking. Agnostic is a product in
its own right, not a frontend layer in front of the engine.

The consequences are all simplifications:

- The API is designed for **Agnostic's** users. Shape, naming and auth are chosen on merit rather
  than back-fitted to an existing client.
- Serving two MCP shapes (**D5**) is no longer forced by a migration constraint. Keep both only if
  each earns its place — JSON-RPC is the MCP standard; the REST shape needs its own justification.
- The ordering inversion is gone. "Consumer green comes after the tag" applies normally again,
  because no live consumer is waiting on this specific surface.

⚠ **Not a licence to break SY gratuitously.** If SY is ever pointed at Agnostic, the answer is a
**compatibility shim** — an additive translation layer over the real API — not a core API bent to
fit an existing client. Keep the seam shim-able: route tables and request decoding stay separable
from handler logic, so an alternate surface can be mounted without touching either. That is cheap
now and expensive to retrofit.

### M8 — Reports (v0.9.0)

- HTML + CSV + JSON export; quality trends and comparison reports

**✅ Decided 2026-08-20 — HTML + CSV + JSON only. No PDF in 1.0; wait for `bayan_pdf_*`.**

"Lift mneme" is not the cheap proven option this brief assumed. It was built and run: a genuine
PDF 1.4, 21 assertions green. But probed with QA-shaped input it fails on the two things a QA report
is made of — **UTF-8 becomes mojibake** ("Qualité" → "Qualitˆ'") and **markdown tables print as
literal `| Test | Status |` pipes** in a proportional font. Tables are the one structure the
oracle's PDF path actually builds. Fixing that is a rewrite, not a lift.

Decisive independently: mneme is **AGPL-3.0** and Agnostic is **GPL-3.0-only**, and mneme exposes no
`[lib]`/`dist/` so "lift" means copying source. AgnosAI already refused mneme for exactly this
(`agnosai/docs/development/roadmap.md:95`).

Worth knowing the oracle's PDF is largely aspirational too: `reportlab` sits in an optional extra,
the ImportError path writes **HTML into a `.pdf` file**, `_count_pages` is a hardcoded `return 1`,
and `include_charts` is never read.

→ **Follow-up, separate session:** file a writer-only `bayan_pdf_*` request naming Agnostic as a
second driver. It is currently P2 / post-v1.0 with no date.

### M9 — WebGUI (v1.0.0)

- Static HTML/CSS/JS bundle served through sandhi (**D3**)
- ~~Needs a static file handler + mime map written from scratch~~ — **superseded at 0.1.7 by
  ADR 0004.** Pages are embedded at build time (`scripts/gen-webgui.sh`), so nothing is read
  from disk and no request input becomes a path; the "mime map" is one media type.

**Seeded at 0.1.7** — landed with its gates, as the release shape requires:

- [x] The shell at `/ui`: Overview, a tab per switched-on plugin, Settings; sign-in when
  `AGNOSTIC_AUTH=required`.
- [x] Native plugins: compiled in, switched on per deployment (`PUT /api/v1/plugins/{id}`,
  ADMIN, audited, durable), sandboxed in the shell, served under a generated CSP.
- [x] Swarm Command as the first plugin — on its simulator, disclosed as `data: simulated`.

**Grown at 0.1.8** — the plugin platform, and Swarm Command on real crews:

- [x] The host bridge (ADR 0005): a plugin reaches the API only by asking the shell, which
  answers what the plugin's manifest `permissions` grant, with the user's credential — never
  handed to the plugin. Plugin pages lose their own network (`connect-src 'none'`).
- [x] Plugin documents, per tenant (`/api/v1/plugins/{id}/data[/{key}]`, READ/WRITE, audited,
  32 KiB × 256), shown — and clearable — in Settings.
- [x] Transport hardening (ADR 0006): with auth off only a loopback `Host` is answered, and
  every POST and PUT must declare JSON — request forgery and DNS rebinding closed.
- [x] Swarm Command: saved swarms with every capability editable (roles and caps, models,
  tools, regions, budget, failure model, tasks), headless cost estimates over several seeds,
  and live runs — its tasks submitted as a crew, polled through the bridge, watched, cancelled,
  recorded on the swarm. `data: mixed`; every mission is labelled SIM or LIVE.

**Grown at 0.1.9** — the plugin platform checked by the server, and a crew surface a UI can build on:

- [x] One permission vocabulary (`src/webgui/permissions.json`), enforced by the server on every
  bridged request — the plugin rung, before authentication (ADR 0007). The shell's gate is built
  from the same file, answers only the page session that asked, and is tested under Node.
- [x] Crews belong to their tenant (404 to every other), `GET /api/v1/crews` lists them by cursor,
  and `Idempotency-Key` makes a submit safe to retry (ADR 0008).
- [x] Crew progress collected by the server and read by cursor — numbered, timed events; outcomes
  durable without a poller; RUNNING reported (ADR 0009). Real usage — tokens, cost, model — on every
  result, and the plan route.
- [x] Plugin documents have revisions (ETag, `If-Match`, `If-None-Match: *`, 412).
- [x] Swarm Command 0.3.0: real cost beside the estimate, results, a Crews list that watches any
  crew, safe submits, conflict-safe swarms, viewers read-only. `tests/webgui/` under Node in CI.

**Grown at 0.1.10** — the views over the real surface, and the platform they needed:

- [x] **Crews**, **Library** (presets + agent definitions, which it can write) and **Audit trail** as
  first-party plugins, starting OFF (ADR 0004). New server surface for them: `GET /api/v1/crews?status=`,
  `GET /api/v1/audit/entries` (ADR 0011), and the `definitions:write` / `audit:read` permissions.
- [x] Views link to each other through the shell: `#plugin/<id>?<params>`, `agnostic:navigate`,
  `agnostic:params`, `views` in `init` (ADR 0010). Swarm Command follows `crew=<uuid>`.
- [x] One bridge client, `src/webgui/kit/host.js`, carried byte for byte by every plugin and verified
  by the generator (ADR 0010).

Still owed for 1.0.0:

- [x] ~~Views over the real surface~~ — **done at 0.1.10**: crews, agent definitions, presets and the
  audit trail each have a view.
- [ ] Streaming crew events (M7's transport) — the cursor replaced the window-matching poll at 0.1.9
  (ADR 0009), but it is still a one-second poll. Needs a transport that does not hold a pooled
  worker per watcher.
- [ ] M8's reports, once they exist, as views or downloads from the shell.

Found at 0.1.9, recorded rather than fixed:

- [x] ~~**Cancelling a crew loses the results its finished tasks produced.**~~ **Fixed at 0.1.10**
  (ADR 0012): a stored CANCELLED with no results takes a terminal observation's results once, status
  unchanged, and the stored outcome is rewritten once.
- [ ] → **agnosai follow-ups** (release agnosai, then re-pin): a parallel or DAG crew publishes
  `task_started` for a whole wave before it runs and `task_completed` only after every batch, and
  sends no `token` events from its workers — a watcher cannot see which tasks of a wave are running
  or done; `agent_cost_usd` in the crew profile is always empty (`metadata["agent"]` is never
  written); `token` events carry `crew_id: "unknown"`; on a timeout `crew_completed` can say
  `completed` while the orchestrator records FAILED; the registry never reports RUNNING.
- [ ] → **sandhi**: `sandhi_server_send_chunk` discards `sock_send`'s result, so a streaming handler
  cannot notice its client left. A prerequisite for any SSE here.

Found at 0.1.10, recorded rather than fixed:

- [ ] → **agnosai follow-ups**, with the ones above (release agnosai, then re-pin): its dist calls the
  deprecated `bayan_json_v_obj_get` (bayan 1.5.11) and passes `Str`s where cyrius 6.6.14 wants a
  `cstring` (`file_open(str_data(...))`), warning in every build here; and it declares sigil 3.13.5
  where 6.6.14 folds 3.13.7 — harmless, the fold wins, but the lock's sigil line then names a commit
  `lib/` does not hold.
- [ ] The audit route serves only the newest 1024 entries (ADR 0011). A ranged, allocator-aware read
  in libro would let it page the whole trail — file it with libro when a deployment needs that.
- [ ] Library edits a definition with a last-writer-wins `PUT`: two editors of one definition do not
  find out about each other, as plugin documents do since 0.1.9 (revisions). Definitions want an ETag
  and `If-Match` the same way.

## ~~Moving the cyrius pin to 6.6.13~~ (recorded 2026-10-02) — ✅ done at 0.1.10, at 6.6.14

All three below landed with the 6.6.14 pin: every suite and the server ran natively on the Pi and the
aarch64 artifact is released again; the `cyrius.cyml` note says what a modules-less block means now;
`lib/math.cyr` was re-vendored by the same `cyrius deps`.


- **The aarch64 SIGBUS is fixed upstream** (cyrius 6.6.13, I9, filed by 0.1.7): every global now starts at
  its natural alignment, so sankoch's odd-sized `u8` arrays no longer misalign sigil's atomic init flags or
  majra's `_mq_next_job_id`. Rebuild on the 6.6.13 pin and re-run the release binary and the 12 failing
  suites natively on the pi.
- A modules-less `[deps.X]` now means `dist/X.cyr` or warns by name (I10, filed by 0.1.7): the
  `cyrius.cyml` comment about blocks that must list `modules` can say so.
- Re-vendor `lib/math.cyr` with `cyrius deps` in the same commit — 6.6.13 made `f64_le` / `f64_ge` / `f64_trunc` compiler builtins (reserved names), and a pre-6.6.13 vendored copy still defines them (`reserved keyword`).

## Release shape

**✅ Decided 2026-08-20 — one release. M1–M9 ship together as 1.0.0.**

`cyrius/CLAUDE.md:96` permits 1–2 releases for a multi-phase arc and AgnosAI used two, but Agnostic
cuts as a total. The consequence to plan around: there is no intermediate tag, so `main` must stay
green the whole way rather than being stabilised once per release — every milestone lands with its
gates passing, and nothing is left "to be fixed before the cut".

## Out of scope for v1.0

- **A TUI.** D3 scopes the GUI to a static bundle; a richer GUI comes later and a TUI is optional
  future work.
- **Re-implementing anything AgnosAI owns.** If a capability lives in the engine tier, Agnostic
  calls it — it does not fork it.
- **Kubernetes topology parity.** The oracle's multi-container postgres deployment does not survive
  the move to embedded `patra`.
- **The oracle's benchmark numbers as a performance target** — they are invalid
  (`ORACLE-AUDIT.md` §4). The Cyrius line starts its own baseline.
- **A SecureYeoman compatibility shim.** SY can consume AgnosAI directly, so no shim is needed for
  v1.0. If one is wanted later it is *additive* — a translation layer mounted over the published
  API — and it is built then, against a real requirement, rather than pre-emptively shaping v1.0
  around a client that may never call us.
