# agnostic — Roadmap

> **This file is forward-facing only**: open and planned work through v1.0, in dependency order.
> What shipped is in [`CHANGELOG.md`](../../CHANGELOG.md), one entry per release; why is in
> [`../adr/`](../adr/); live figures are in [`state.md`](state.md); orientation for picking the
> port up is in [`handoff.md`](handoff.md). When an item ships, delete it here — do not turn it
> into a changelog entry. Settled questions are kept, compactly, under
> [Settled decisions](#settled-decisions) so they are not re-asked.

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

- [ ] Public API frozen — every exported symbol documented and tested. The HTTP API's half has
      been mechanical since 0.1.13
      ([ADR 0015](../adr/0015-the-http-api-is-described-by-a-generated-schema.md),
      [`docs/api/`](../api/README.md)): [`docs/api/generated/schema.json`](../api/generated/schema.json)
      is the frozen description, held by `tests/api_schema.tcyr` and CI's `gen-api-schema.sh --check`
      on the shipped DCE binary. From 1.0, removing or renaming anything in it needs an ADR and a
      **Breaking** CHANGELOG entry. Still open: the exported Cyrius symbols' half, and what the
      schema leaves out (nested shapes, field types; see "Later").
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

M0–M5 are complete (CHANGELOG 0.1.0 and 0.1.1). The decisions they settled are under
[Settled decisions](#settled-decisions).

### M6 — QA tool surface

- The QA tools (**D4**). The 5–8 figure in `first-party-standards.md:625` is a soft guideline for
  typical projects, not a ceiling for platform-scale ones.
- Sandboxing **delegated to kavach** — `first-party-standards.md:76`: *"kavach owns the sandbox,
  not the application."* The oracle hand-rolled an rlimit subprocess; do not repeat it.
- Browser automation via `yantra`; CV pipeline on chitra + ranga + rosnet

**The count is 38, not 28** (corrected 2026-08-21 by extracting the union of every tool name across
the 18 presets). Of the **38 distinct classes**, **36 exist** in the oracle and **2 do not exist at
all** (`ArtifactManagementTool`, `CIPipelineIntegrationTool`, both named by `quality-large.json`).
None of the 36 was ever registered — the oracle's `_REGISTRY` is never populated, so every agent ran
with `tools=[]` (`ORACLE-AUDIT.md` §3.15). The presets' tool lists are a **specification of intent,
not observed behaviour**: port the presets as documents, and treat each tool as a fresh
implementation against its preset-declared intent, not as a port of working code.

- [ ] **The viability gate reaches 0.** The gate is built: `src/engine/tools.cyr` resolves the
  38-name manifest against the engine's registry, pinned by `tests/tools.tcyr`, and **2 of 38
  resolve** ([`state.md`](state.md), M6). M6 is done when every name resolves, the two nonexistent
  tools are written or struck from the presets that name them, and a registry miss is an error,
  never a smaller agent. Do not close the gap with a case transform (`state.md`, M6).
- [ ] **A reviewer preset — the QA shape of the most robust multi-agent pattern.** One task does
  the work, and a dependent review task with a clean context and an `output_schema` verdict
  checks it. This is Cognition's single writer plus reviewer, and Claude's adversarial
  verification. It is expressible as a DAG today, so it needs no engine change: ship it as a
  preset and document it. Why it is here: the
  [landscape review](research/2026-10-03-herdr-and-multi-agent-landscape.md) §5 B2.

**Prerequisite:** `yantra` needs `Page.captureScreenshot` on its CDP surface.

**Prerequisite (recorded 2026-10-03): agnosai must run a tool-calling loop.** `execute_task` is
one chat completion plus the output-schema retry. Nothing in `crew_runner.cyr` or `src/llm/`
handles a `tool_call`, so a resolved tool is never invoked by the model. That makes the
viability gate necessary but not sufficient: every name can resolve and still no tool runs.
This is agnosai **F1**. Settle the tool-registry seam ([`handoff.md`](handoff.md) §8) together
with it: `agnostic_engine_init` exposes no registry handle, so the gate is not wired into mount.

### M7 — MCP surface + A2A

- JSON-RPC 2.0 MCP at `/mcp`, on `bote`
- REST tool invocation at `/api/v1/mcp/invoke`
- A2A callback endpoint
- daimon tool registration: an env-gated, default-off registrar that POSTs each QA tool to
  daimon's tool endpoint, the oracle's shape and default
  ([ADR 0002](../adr/0002-daimon-tier-1-deferred.md); daimon Tier 1 itself is deferred)

**Target spec revisions (recorded 2026-10-03; settle in an ADR when M7 starts):**

- [ ] **MCP 2026-07-28, the stateless core.** It has no `initialize` handshake and no
  `Mcp-Session-Id`, and it adds the `Mcp-Method` / `Mcp-Name` routing headers. No session means
  nothing to hold on a pooled worker, which is the constraint ADR 0009 is built on.
- [ ] **The MCP Tasks extension, mapped onto crews.** A tool call that submits a crew returns a
  task handle, and the client polls it. That is the 202-then-poll shape agnostic already has,
  so no new transport is needed.
- [ ] **Do not build on Sampling, Roots or Logging.** All three are deprecated in 2026-07-28,
  with a 12-month removal window.
- [ ] **A2A v1.0.x**, with signed Agent Cards. agnosai's callback POST is still unsent (agnosai
  F8).

**Both MCP shapes stand (D5), on their own merit.** The original justification was preserving
SecureYeoman's live client; that is gone (see below), but the decision is unchanged — JSON-RPC is
the MCP standard for tool clients, and the REST shape is what scripts, the WebGUI and any
non-MCP-aware caller actually want. The full QA tool surface (D4's "28"; 38 distinct names by
M6's count) is settled: the 5–8 figure in `first-party-standards.md:625` is a soft guideline for
typical projects, not a ceiling for platform-scale ones.

**Agnostic stands on its own** (CYRIUS-PORT-BRIEF §7.3). An earlier draft treated SecureYeoman's
live 43-tool client as a *frozen wire contract* this milestone had to preserve, on the assumption SY
reaches the engine through Agnostic. It does not have to: **SY can consume AgnosAI directly**, since
AgnosAI 2.0.2+ ships both a `/mcp` surface and `dist/agnosai.cyr` for in-process linking. Agnostic is
a product in its own right, not a frontend layer in front of the engine. So the API is designed for
**Agnostic's** users — shape, naming and auth chosen on merit rather than back-fitted to an existing
client — and "consumer green comes after the tag" applies normally, because no live consumer is
waiting on this specific surface.

⚠ **Not a licence to break SY gratuitously.** If SY is ever pointed at Agnostic, the answer is a
**compatibility shim** — an additive translation layer over the real API — not a core API bent to
fit an existing client. Keep the seam shim-able: route tables and request decoding stay separable
from handler logic, so an alternate surface can be mounted without touching either. That is cheap
now and expensive to retrofit.

### M8 — Reports

- HTML + CSV + JSON export; quality trends and comparison reports

**Decided 2026-08-20 — HTML + CSV + JSON only. No PDF in 1.0; wait for `bayan_pdf_*`.**

- "Lift mneme" is not the cheap proven option the brief assumed. It was built and run: a genuine
  PDF 1.4, 21 assertions green. But probed with QA-shaped input it fails on the two things a QA
  report is made of — **UTF-8 becomes mojibake** ("Qualité" → "Qualitˆ'") and **markdown tables
  print as literal `| Test | Status |` pipes** in a proportional font. Tables are the one structure
  the oracle's PDF path actually builds. Fixing that is a rewrite, not a lift.
- Decisive independently: mneme is **AGPL-3.0** and Agnostic is **GPL-3.0-only**, and mneme exposes
  no `[lib]`/`dist/`, so "lift" means copying source. AgnosAI refused mneme for exactly this.
- The oracle's PDF is largely aspirational too: `reportlab` sits in an optional extra, the
  ImportError path writes **HTML into a `.pdf` file**, `_count_pages` is a hardcoded `return 1`,
  and `include_charts` is never read.

- [ ] ⚠ **The decision's premise is stale.** It waits for `bayan_pdf_*`; bayan 1.5.0 (2026-08-21)
  shipped it, and the vendored `lib/bayan.cyr` holds `bayan_pdf_new_a` and `bayan_pdf_write_file`,
  so the old follow-up (file a writer-only `bayan_pdf_*` request) is moot. Whether reports gain a
  PDF form in 1.0 is the user's call (also under "Decisions awaiting the user").

⚠ **Audit point 6 (path traversal) re-opens here.** Report and artefact storage is the first thing
that builds a filename from user-supplied text. Keep `agnostic_key_is_valid` narrow for that reason
(Settled decisions, 2026-08-21).

⚠ **Report storage must fit patra's limits.** It shares the one patra handle
(`src/engine/store.cyr`): at most 63 tables, one index each (column 0 auto-indexed when it is
`COL_INT`), per-write fsync by default, and a single writer.

### M9 — WebGUI

The shell at `/ui`, the plugin platform and the views over the real surface (crews, agent
definitions, presets, the audit trail) are built (CHANGELOG 0.1.7–0.1.10; ADRs 0004–0012). Still
owed for 1.0.0:

- [ ] Streaming crew events (M7's transport) — the cursor replaced the window-matching poll at 0.1.9
  (ADR 0009), but it is still a one-second poll. Needs a transport that does not hold a pooled
  worker per watcher, and sandhi's `send_chunk` fix (see "Upstream").
- [ ] M8's reports, once they exist, as views or downloads from the shell.
- [ ] **"Which crew needs me?"** Once agnosai F3 ships, show `awaiting_approval` as a crew
  status and in its events. Roll it up as a badge from task to crew to tenant in Crews and
  Swarm Command, with an approve/reject action behind a permission. This is the HITL surface
  agnostic has none of today. The model is herdr's `blocked` roll-up (landscape review H2).
- [ ] **Swarm Command sends no selection hints** (ADR 0017). Its roles carry tools that could
  become each task's `required_tools`, so a live swarm's agents would be picked by what they can
  do.

## Waiting on agnosai (release agnosai, then re-pin)

Each of these is filed on agnosai's roadmap under **F** ("Past parity").

- **F1 — tool loop:** M6's prerequisite.
- **F2 — hierarchical wired:** agnostic then accepts `hierarchical`, which
  `agnostic_process_from_wire` (`src/engine/request.cyr:149-159`) leaves out today, so it is a 400.
- **F3 — approvals plus a lifecycle contract with `seq`:** builds on the event and status
  semantics agnosai's B17 fixed in 2.1.5, and feeds M9's roll-up. It is also what would give a
  per-task snapshot that a reader who fell past the event ring (`missed`) can resync from mid-run.
- **F4 — durable crew log:** turns an `interrupted` crew (ADR 0013) into a resumable one.
- **F5 — budgets and caps:** brings back an `AGNOSTIC_CREW_MAX_CONCURRENT_TASKS` that is actually
  enforced.

## Moving the cyrius pin to 6.6.15 — found 2026-10-04, siblings first

cyrius **6.6.15** is tagged; its fold carries sigil **3.13.9**. agnostic pins 6.6.14, and so do
agnosai 2.1.6, kavach 3.13.2, libro 2.10.6 and bote 3.3.16. agnosai's roadmap holds the reading of
what 6.6.15 fixes; the parts that reach agnostic, which makes outbound HTTPS through sandhi to an
`https` LLM gateway and, since 0.1.14, to an `https` OTLP collector:

- **CVE-70**: neither TLS 1.3 side zeroised its ephemeral private key or shared secret after use.
- **CVE-71**: neither TLS 1.3 side refused an all-zero x25519 result (RFC 8446 §7.4.2).
- **CVE-68 part B**: HMAC and HKDF state left in dead stack — every handshake's key schedule, and
  agnostic's own HMAC-SHA256 (JWT signing, `src/auth/jwt.cyr`; the audit chain through libro).
- **CVE-69**: a `secret var` epilogue leaving return registers in dead stack.

Fix it at the source, as 0.1.7 did — agnosai 2.1.2 was released so this manifest could drop its
override blocks — with no override pin here. The chain, from agnosai's plan:

- [ ] kavach and libro on cyrius 6.6.15 with `[deps.sigil] tag = "3.13.9"`, then bote on 6.6.15
  with that libro, then agnosai on 6.6.15 with them.
- [ ] agnostic moves `cyrius = "6.6.15"`, `[deps.agnosai]` and the root `[deps.libro]` together
  (the lockstep `cyrius.cyml` describes), then certifies in a sibling-free replica with an empty dep
  cache and reruns every suite natively on `ssh pi`.
- [ ] ⚠ Check `~/.cyrius/versions/6.6.15/SOURCE_COMMIT` against the 6.6.15 tag before trusting the
  lib snapshot (agnosai's roadmap found this slot dirty and untagged once).

## Open — agnostic only

Found while building, grouped by area. H and B numbers in this file are those of the
[2026-10-03 landscape review](research/2026-10-03-herdr-and-multi-agent-landscape.md).

### Crews and the HTTP API

- [ ] **`GET /api/v1/crews/{id}` for a crew this process holds carries `engine_mode` twice**
  (found at 0.1.13). The route sets it (`src/routes/crews.cyr:366`), then
  `agnostic_ledger_describe_a` (called at `:370`) sets it again (`src/engine/ledger.cyr:570`), and
  bayan's object set appends a second key. `api/responses` in `tests/api_schema.tcyr` compares a
  body's keys as a set, so it passes this; the fix should also make that group assert no key
  appears twice in any answer. `docs/api/README.md` notes it.
- [ ] **A 405 names the methods the path takes (`Allow`)** (found reviewing H5's first change;
  older than H5). `src/http/router.cyr:530` answers `405 {"error":"method not allowed"}` with no
  `Allow` header, and nothing in `src/server/serve.cyr` adds one, though RFC 9110 §15.5.6 says a 405
  MUST carry it.
  - Reproduce: `curl -i -X POST http://127.0.0.1:<port>/health`, or `agnostic_response_headers` of
    `agnostic_route_dispatch_a(a, AGNOSTIC_METHOD_POST, str_from("/health"), ...)`, which is 0.
  - Fix: the routes are rows, so OR the arms of every row whose path matched into a method mask in
    the match record in `agnostic_route_resolve_a`, and write `Allow: GET, POST` from it on the 405
    through the response's extra header lines (`AGNOSTIC_RESP_HEADERS`), naming each method with
    `agnostic_method_name`. Pin it in `router/table`: every row's own path, sent with a method it
    lacks, lists exactly its arms.
- [ ] **Cancel answers 404, not 409, for a stored terminal crew** (H4 follow-up). Cancel needs a
  ledger entry (`src/routes/crews.cyr:384`), so a crew from before a restart — an interrupted one
  included — answers 404 while `GET /crews/{id}` answers 200. Answering 409 from the store would
  make the two agree.
- [ ] **One agnostic process per database file, enforced** (H4 follow-up). The start-up sweep
  assumes it (so does the definition cache), and since 0.1.13 sharing a database file is
  destructive rather than merely racy: a second process would sweep the first one's live crews to
  `interrupted`. Fix: a non-blocking `flock` on a `<db>.owner` sidecar at mount, refusing to start
  when it is held. Documented in
  [ADR 0013](../adr/0013-a-crew-interrupted-by-a-restart-is-interrupted.md) and
  [architecture 001](../architecture/001-what-survives-a-restart.md); not built.
- [ ] **An interrupted crew keeps its finished results** (H4 follow-up), under ADR 0012's rule and
  without changing ADR 0013. Today an interrupted crew has `results: []`: while a crew runs, agnostic
  holds no results, and `task_completed` carries only the task's id and status. ⚠ Re-check the
  premise before building: since agnosai 2.1.5 (its ADR 022; CHANGELOG 0.1.14) every task the model
  answers sends a `token` event carrying its output while the crew runs, which agnostic does not
  keep as a result. No event carries usage; that still needs agnosai F3's per-task payload or F4's
  durable crew log.
- [ ] **Task results do not name their agent** (found at 0.1.14). Since agnosai 2.1.5 every
  LLM-answered result's metadata carries `agent` (its ADR 022); agnostic's result rendering picks
  fields one by one and does not take it. Surfacing it would let a watcher confirm `explain`'s
  winner (ADR 0016) from the outcome.
- [ ] **An agent definition's `complexity` is still free text** (ADR 0017). The engine reads a
  value it does not recognise as medium, the silent default the task's hint now refuses. Closing it
  would refuse stored definitions that hold another value, so it needs a migration note: decide
  whether `PUT`/`POST` refuse and stored ones are read as they are.
- [ ] **Library edits a definition with a last-writer-wins `PUT`** (found at 0.1.10): two editors of
  one definition do not find out about each other. Plugin documents have had revisions since 0.1.9
  (ETag, `If-Match`, `If-None-Match: *`, 412); definitions want an ETag and `If-Match` the same way.

### Audit chain

- [ ] **A trail written before 0.1.13 can never verify clean again, and its verdict hides everything
  after its first break** (found fixing the restart link at 0.1.13). Such a trail holds an entry
  with an empty `prev_hash` after each restart that recorded something. `verify_chain` stops at the
  first failure, so `intact: false, bad_index: N` is all an operator learns. A real alteration
  after entry N would not be reported. The Audit view's banner
  (`src/webgui/plugins/audit/index.html:428`) also says the trail "was altered while the server was
  not running", which is wrong for this kind of break.
  - Reproduce: build `src/main.cyr` with `src/engine/audit.cyr` as at commit f28cb9a. Submit a crew
    with `AGNOSTIC_LLM_URL` at a listener that never answers, `kill -9`, start, create a
    definition, `kill -9`. Then start the current binary on the same files: `intact: false,
    bad_index: 1`.
  - Fix direction: walk the whole chain and report every break, not only the first. Name a break
    whose entry hashes correctly and whose `prev_hash` is empty as a restart break, and anything
    else as an alteration. libro's `verify_chain_from` takes the expected first link, so each
    segment can be verified from its break. That is a wire change to `GET /api/v1/audit`, and the
    banner should follow it.
  - In the same route, the comment at `src/routes/definitions.cyr:283-288` still gives libro's
    cached statements faulting on a pool worker as the reason the verdict is taken at open. libro
    2.8.9 fixed that (see `src/engine/audit.cyr`), and the reason left is cost.
- [ ] **A failed read at open verifies as intact and leaves the chain's head empty** (found fixing
  the restart link at 0.1.13). `_agnostic_audit_open_locked` (`src/engine/audit.cyr:205-209`) reads
  with `patrastore_load_all`. That is libro's legacy shape, which returns an empty vec when the
  query fails, and `verify_chain` of an empty vec is 0. So a store with entries that cannot be read
  reports `intact: true` with nothing verified. With nothing loaded there is no head to seed, so
  the next entry links to "" and the following start reports a break there.
  - Reproduce: read from the code; it needs a patra query failure at open, which no test injects.
  - Fix direction: read with `patrastore_load_all_or_err` and check `libro_is_error`. Report the
    trail as unverified, a state `GET /api/v1/audit` cannot express today, and log at ERROR that
    the head is unknown.
- [ ] **A failed write moves the chain's head anyway, so the next start reports tampering.**
  `_agnostic_audit_record_locked` (`src/engine/audit.cyr:388`) calls `chain_append`, whose
  `_chain_retain` (`lib/libro.cyr:2326-2333`) stores the new entry's hash as the head before
  `patrastore_append` runs (line 394). When that write fails (lines 399-405) the entry is counted
  as dropped, but the head is left on it. The next entry that is saved names a hash that is not in
  the store, and the next open's `verify_chain` says "linkage broken": `intact: false`, "the store
  was altered". Older than 0.1.13; found by the review of the restart fix. The module header's
  "a failed append leaves no hole to find" (`audit.cyr:44-46`) carries a ⚠ saying it is not true
  of a failed write (`audit.cyr:50-56`), and the failure branch points to it.
  - Reproduce: no test reaches it. `audit/gaps` records to a closed store, which returns before
    `chain_append`. It needs a write that fails on an open store (patra fault injection), then a
    write that succeeds, then a reopen.
  - Fix direction: on a failed write, put the head back with
    `chain_set_prev_hash(_agnostic_audit_chain, entry_prev_hash(e))`, so the next entry links to
    the last saved one. A write that reports an error after its row landed would then fork the
    chain, so decide that case first. `patrastore_append` (`lib/libro.cyr:6538`) refuses an
    over-long field before touching patra, a clean refusal. Whether patra's `_exec_insert` can
    return an error after `tbl_insert` (`lib/patra.cyr:5814`) wrote the row is not checked yet; that
    is the case to settle, in patra if need be. Re-reading the store's last row to learn the real
    head is exact but costs a full load (`patrastore_load_all`, which never frees). Add a test that
    injects a failing write.
- [ ] **The audit route serves only the newest 1024 entries** (ADR 0011). A ranged, allocator-aware
  read in libro would let it page the whole trail. Recorded in libro's roadmap ("Ideas",
  2026-10-03), not slotted until a deployment needs more than the newest 1024 entries.

### Memory

- [ ] **Request paths still allocate from the global bump, which has no `free()`** (found during
  H5's fourth change; older than 0.1.13). `src/http/response.cyr`'s header requires the per-request
  arena on every request path, error arms included, and names the 404 as the leak the server can
  least afford. Measured at 0.1.13 with `alloc_used()` around single dispatches, each served from
  its own arena, on a mounted server with auth required: `/health` 0 bytes; a 404 16; a 401 16; any
  authenticated request 16; a failed login 128; a successful login 696; each audited write
  (plugin-data `PUT` or `DELETE`) 416. The bytes are kept until the process exits.
  - Where: the router's refusal arms build their messages with `str_from`
    (`src/http/router.cyr:510`, `:521`, `:530`, `:532`, `:558`, `:562`, `:578`, `:660`); a
    principal with no tenant gets `str_from("")` (`src/auth/authn.cyr:316`); login names its two
    fields, its four response keys and two of their values with `str_from`
    (`src/routes/auth.cyr:56-57`, `:105-111`), and `agnostic_jwt_issue_a` its five claim keys
    (`src/auth/jwt.cyr:226-235`); each audited call site passes `str_from(action)`, and
    `agnostic_audit_detail` (`src/engine/audit.cyr:439`) and `_agnostic_pdata_detail`
    (`src/routes/plugindata.cyr:205`) build with `str_builder_new()`.
  - Reproduce: mount with auth required, then for each request take `alloc_used()` before and
    after `agnostic_route_dispatch_a` with a fresh `arena_allocator(1048576)`, less the 16 bytes per
    `str_from` the caller spends building its own path and body.
  - Fix direction: `str_from_a(a, …)` on the request arena, or keys interned once at load like
    `AGNOSTIC_JK_*`, for the router, authn, login and the JWT claims. The audit strings outlive the
    request only if libro keeps them: check whether `chain_append` and the ring copy them before
    moving them to the arena. libro's own entry (`chain_append` allocates one per append, 2.9.0
    added an opt-in path that does not) is libro's to settle. Then add a guard that fails on the
    regression: a suite asserting `alloc_used()` does not move across a dispatch of each refusal
    arm and an authenticated GET.
- The outbound calls' remaining bytes (an exporter batch, an inference call) are in sandhi's
  dispatch path; see "Upstream".

### Telemetry

- [ ] **agnostic exports no span of its own** (ADR 0018). When agnostic mints the traceparent, a
  crew's `invoke_workflow` span names a parent that is never exported, so a backend shows the
  trace's root as missing; the trace id still joins it to the request's logs. Fix: record an HTTP
  SERVER span per request through agnosai's exporter (`agnosai_telemetry_record_span_in`), whose
  span id is the minted one. Additive.
- [ ] **OTel variables not read** (ADR 0018): `OTEL_SDK_DISABLED` and the sampler variables
  (`OTEL_TRACES_SAMPLER`, `OTEL_TRACES_SAMPLER_ARG`). Add them only with a deployment that needs
  them.
- [ ] → **agnosai**: an operator switch to restart an untrusted inbound trace (agnosai's ADR 023
  follow-up). Until then a `-00` traceparent switches off span export for the sender's own crews
  (ADR 0018).

### Tests, tooling and docs

- [ ] **One warning on our own code is left, in a suite** (found during H5's gate run; older than
  0.1.13). The build prints no warning on `src/`, but `cyrius test` still prints
  `warning:<source>:93:49: assigning non-pointer to typed pointer` for `tests/jwt.tcyr:93`
  (`sig = agnostic_b64u_encode_a(a, mac, 32)`). `sig` is typed `Str` by its initializer at
  `tests/jwt.tcyr:86` (`var sig = str_from("")`), the same shape 0.1.12 fixed in `serve.cyr`.
  Reproduce: `cyrius test tests/jwt.tcyr 2>&1 | grep 'typed pointer'`. Fix: declare it
  `var sig: i64 = str_from("");`, as `serve.cyr` did.
- [ ] **The suites write their stores to fixed `/tmp` paths and ignore `TMPDIR`** (found during the
  audit-seed gate run; older than 0.1.13). 16 suites name 23 `"/tmp/agnostic-*.patra"` literals
  (e.g. `tests/audit.tcyr:9` `_T_AUDIT`, `tests/restart.tcyr:15` `_T_RAUDIT`), and the benchmark
  file `tests/agnostic.bcyr` two more (`:163`, `:195`). Most unlink them only before use
  (`tests/audit.tcyr:15`), not after, so a full `cyrius test` leaves 17 files, about 3.7 MB, in
  `/tmp`. Two runs at once on one machine (two worktrees, two sessions) share each file, so one
  suite can open the other's half-written store. `/tmp` is also a shared quota here, which is why
  the gates set `TMPDIR`.
  - Reproduce: `TMPDIR=$HOME/.cache/agnostic-work cyrius test; ls /tmp/agnostic-*.patra`.
  - Fix direction: build each path from `TMPDIR` (falling back to `/tmp`) plus the pid, through one
    helper the suites and the bench share (there is no shared test include today;
    `tests/api_schema.tcyr:247-263`, `_t_tmp_file` and `_t_tmp_path`, is the shape to share), and
    unlink at the end of each suite's `main` as `tests/restart.tcyr:114-115` already does.
- [ ] **`BENCHMARKS.md` was last generated at 0.1.0.** It is `scripts/bench-history.sh`'s output
  ("do not edit by hand"), and its "Latest" line still reads `59325f3` (dirty), version 0.1.0,
  2026-08-20, with one benchmark, `noop`; `bench-history.csv` holds the same two rows.
  `tests/agnostic.bcyr` had 16 benchmarks at 0.1.13, and `docs/development/state.md`'s Hardening
  table lists `BENCHMARKS.md` as generated.
  - Fix direction: run `./scripts/bench-history.sh` on a clean tree right after a tag, so the row
    names a commit rather than "(dirty)". First check that its parser still reads `cyrius bench`'s
    current lines (`<name>: <value><unit> avg`, units `ns`/`us`/`ms`/`s`). Then decide whether the
    release process regenerates it each time, and say so in the Process or in `state.md`.
- [ ] **`docs/development/handoff.md` grows a paragraph per release.** §1 now reaches 0.1.14, but
  the header still says it was last refreshed 2026-08-23 (after M5) and carries a per-section
  refresh log that grows each release.
  - Fix direction: rewrite §1 as a short current orientation that links `state.md` for figures and
    the CHANGELOG for history, and drop the refresh log from the header.
- [ ] **Two cyrius work-arounds outlived their filings.** The defer-skipped-on-tail-call defect
  was fixed in cyrius 6.6.7 and `CYRIUS_PKG_VERSION` became visible in included files in 6.5.34
  (both in `~/Repos/cyrius/docs/development/issues/archived/`), but `src/engine/rlock.cyr:27-31`,
  `src/main.cyr:42-46`, `src/routes/health.cyr:43-48`, `handoff.md` §5 and `state.md` still
  describe them as open. Both work-arounds still work; retiring them is a code change with its own
  test, not a comment edit.

## Upstream — owed by sibling repos

Each is fixed at its source and reaches agnostic by a re-pin; none is wrapped here.

- [ ] → **sandhi**: `sandhi_server_send_chunk` discards `sock_send`'s result, so a streaming handler
  cannot notice its client left. A prerequisite for any SSE here (M9's streaming). Reproduced on
  cyrius 6.6.14; a fix reaches agnostic only through a cyrius release that refolds sandhi. Filed
  2026-10-03 as `~/Repos/sandhi/docs/development/issues/2026-10-03-chunked-response-verbs-discard-send-result.md`,
  but ⚠ that file is still untracked in the sandhi checkout (checked 2026-10-04), so "filed" holds
  only on this machine until it is committed there.
- [ ] → **sandhi**, through agnosai: an exporter batch still leaves ~480 B, and an inference call
  ~2.6 KB including the reply it keeps, on the global bump in sandhi's dispatch path (16 B is the
  stdlib's `sockaddr_in`). Recorded on agnosai's roadmap as "To file"; not yet filed with sandhi
  (CHANGELOG 0.1.14, Known).
- [ ] → **kavach**, through agnosai's sandbox: on a host whose coreutils are uutils (Ubuntu's default
  from 25.10), kavach's pinned exec cannot run them, so a sandboxed `/bin/echo` or `cat` exits 1.
  Filed with kavach (`docs/development/issues/2026-10-03-pinned-exec-breaks-uutils-coreutils.md`)
  and recorded in agnosai's roadmap C. It matters to a deployment on such a host.
- [ ] → **patra**: an over-length STR *query literal* is clamped (found by CNAME-255, 2026-10-04).
  `_str_hash` and `row_write_str` (`lib/patra.cyr:1706`, `:1758`) cut a literal over 255 bytes to
  its 255-byte prefix. So a `WHERE` on a STR column given a longer literal hashes and compares as
  that prefix. On a write, patra refuses an over-length value (`PATRA_ERR_ROWSZ`), so the two
  paths disagree.
  - Not reachable in agnostic today. Every STR it queries is capped below 255 bytes at the door:
    tenant keys at 64, settings at 64 and 255, and crew ids are UUIDs.
  - Fix direction: an upstream patra release that refuses an over-length literal the way it
    refuses an over-length value. Fix it at source; do not wrap it here. Then re-pin. Not filed yet.
- [ ] → **agnosai**: streamline its preset set (18 in `src/presets/`) to a small illustrative example
  library rather than a competing production one, so the two stop diverging by accident (Settled
  decisions, preset canon). Not yet on agnosai's roadmap.

## Decisions awaiting the user

- [ ] **Should a change to the HTTP surface also update its two derived artefacts?** The proposal is
  a clause in CLAUDE.md's Process step 5: "an API change regenerates
  `docs/api/generated/schema.json` (`scripts/gen-api-schema.sh`) and updates
  `skills/agnostic/SKILL.md` in the same change".
  - CI already enforces the schema (`gen-api-schema.sh --check`). `check-skill.py` catches drift
    in routes, methods, parameters, headers, response keys and marked lists, but not in prose about
    statuses or limits.
  - The H5 and H6 plans both recommended the clause. CLAUDE.md is the user's file, so it is the
    user's call.
- [ ] **Review ADR 0015** ([the API schema](../adr/0015-the-http-api-is-described-by-a-generated-schema.md)).
  It is marked Accepted, like every ADR here, but was written and accepted without the user's
  review. ADRs 0013 and 0014 were approved through their roadmap items; 0015 was not.
- [ ] **What the coverage gate measures.** `CONTRIBUTING.md:32-34` lists `cyrius coverage --min 80`
  as "its own CI step", but `.github/workflows/ci.yml` has no such step, and the gate fails: 330 of
  476 functions referenced, 69% at 0.1.13 (306 of 451, 67%, at 0.1.12). It is reference coverage, a
  static floor: the route handlers (`src/routes/*.cyr`), which the suites drive through
  `agnostic_route_dispatch_a`, count as unreferenced, as do most of `src/cli.cyr` (2/7) and
  `src/server/serve.cyr` (2/7).
  - Reproduce: `TMPDIR=$HOME/.cache/agnostic-work cyrius coverage --min 80` (exit 1, "coverage
    gate FAILED: 69% < --min 80%").
  - Fix direction: decide what the gate measures before wiring it. Either name the handlers the
    suites reach by dispatch (a reference per route in the suite that drives it) and add the CI
    step at 80, or say in `CONTRIBUTING.md` that it is a local report, not a CI gate.
- [ ] **Whether reports gain a PDF form in 1.0.** M8's decision waits for `bayan_pdf_*`, which
  bayan 1.5.0 shipped; see M8.

## Later — recorded, not scheduled

- **A per-agent context cost in the Swarm Command simulator** (recorded at B3,
  [ADR 0014](../adr/0014-the-estimators-one-agent-baseline-is-its-own-model.md)): the tokens each
  new agent reads in before it works — its brief, the plan, its parent's context — as a per-role or
  swarm-wide knob, **default 0, so no existing estimate changes**. Today a swarm's only token
  overhead in the simulator is orchestration and lead coordination, 7–13% on the templates, while
  Anthropic measured a multi-agent system at about 15× a chat's tokens (the landscape review's
  figure) against about 4× for a single agent: roughly 3–4× one agent. So the one-agent baseline's
  token gap (88–98% of the swarm's tokens on the templates, p50 over eight seeds) is a floor. The
  knob is a change to the Sim's model; the estimate test that pins 0.4's figures proves the default
  leaves every estimate as it was.
- **MAST failure tags** (specification / inter-agent misalignment / verification) on failed crews
  in events and audit. Worth doing once F1–F3 make failures richer.
- **External coding agents as crew members over ACP.** Claude Code or Codex would be driven as
  structured JSON-RPC peers, not by scraping a PTY. This is a strategic option, not a
  commitment, and it only makes sense after F1.
- **What the API schema leaves out** (recorded at H5's third change, ADR 0015;
  `docs/api/README.md`, "Known gaps"). Each needs its source made a table first, or it would be a
  hand-kept copy:
  - field types and required-ness of each request field — today they are decoder code
    (`src/engine/request.cyr`, `src/engine/agentdef.cyr`), not data;
  - nested response shapes (H5's fourth change covers only top-level keys);
  - a machine-readable `code` for the 422 refusals — `unknown_field` and `refused_field` — which
    today are `{"error": …}` only, with four different message forms
    (`src/engine/request.cyr:668`, `:477`, `src/engine/agentdef.cyr:339`,
    `src/routes/plugins.cyr:76`, `src/routes/auth.cyr:53`);
  - per-handler 4xx statuses — the route modules' "Route | Codes" headers and `state.md` keep them;
  - the reverse of the declared parts: a query parameter or header a handler starts reading without
    declaring it is caught only for the six known parameter names on GET routes
    (`tests/api_schema.tcyr`, `api/probes`). Closing it means handlers read parameters and headers
    through a per-route table the schema also reads.

## Settled decisions

Decided questions, kept so they are not re-asked. Every ADR in [`../adr/`](../adr/) is one too;
the six decisions of `CYRIUS-PORT-BRIEF.md` §7 are summarised in [`handoff.md`](handoff.md) §4.
M7's and M8's governing decisions stay with those milestones above, and the release shape has its
own section below.

- **2026-08-20 — Agnostic owns identity, thin**, adapted from SecureYeoman's working Cyrius probe
  (`secureyeoman/yeo-cy-test/src/auth.cyr`, 541 lines): HS256 JWT issue and verify; Argon2id
  credentials via `sigil` at sy-core's parameters (m=19456 KiB, t=2, p=1); API keys by `sigil`
  SHA-256 with a `ct_eq_bytes` constant-time compare; tenant CRUD in `patra` with tenant
  key-prefixing and a static role→permission table; webhook HMAC-SHA256; external-IdP verification
  only as an **additive** mode behind a fn-pointer validator. Built as M5 (CHANGELOG 0.1.1, M5
  parts 1–3).
  - **Login-abuse controls are load-bearing, not polish.** Argon2id at ~244 ms makes login a
    request-amplification lever: 8 concurrent attempts pushed `GET /health` from 6 ms to 942 ms,
    and ~40 wedged a 4-worker pool. A per-IP token bucket (`src/auth/ratelimit.cyr`) and a
    worker-concurrency cap (the Argon2 buffer pool, `src/auth/crypto.cyr`) both shed with 429
    **before** any Argon2 work. A verify path does not write: patra fsyncs each write by default,
    and the oracle rewrote a key blob on every validation.
  - **Delegating to kavach was struck, not weighed.** kavach has no identity surface — a grep for
    user/role/apikey/tenant/jwt/oauth/session across all 48 files of `kavach/src/` returns
    nothing, and `credential.cyr` injects secrets *into* sandboxes; it authenticates nobody. There is no
    ecosystem IdP either (`iam` is a neofetch clone, `aegis` a policy daemon, `phylax` threat
    detection).
  - **Do not port the oracle's identity surface faithfully — most of it never ran.** Local
    password login cannot succeed (`_authenticate_local` reads `password_hash`, which `User` does
    not have); no user can create an API key (everyone is `VIEWER`, no role assignment exists, the
    endpoint needs `SUPER_ADMIN`); tenant API keys are read-only (the validator reads a key nothing
    writes); the three OAuth providers are unreachable (no caller passes a provider). Scope is what
    the oracle actually executes, for any further identity work too.
- **2026-08-20 — Agnostic's preset library is canonical; AgnosAI's becomes examples.** The two sets
  of 18 are unrelated content sharing a naming scheme: 15 names collide, and not one of the 15 has
  a matching description, agent roster or tool vocabulary. Agnostic's presets name 38 PascalCase QA
  tool classes, AgnosAI's 23 snake_case capabilities, and the intersection is empty. Agnostic's
  documents also carry five fields AgnosAI's schema has no slot for (`workflow_mode`; per-agent
  `focus`, `celery_queue`, `redis_prefix`, `allow_delegation`), which its parser would silently
  discard.
  Serving an AgnosAI preset would name tools Agnostic cannot resolve. A decision about content, not
  linkage: execution still goes through AgnosAI (`src/engine/presets.cyr`; CHANGELOG 0.1.1). The
  agnosai half is under "Upstream".
- **2026-08-20 — daimon Tier 1 registration is deferred**
  ([ADR 0002](../adr/0002-daimon-tier-1-deferred.md)): it cannot be implemented as written. M7 ships
  the tool registration that does work.
- **2026-08-21 — No `[deps.majra]`; the engine already owns the queue.**
  `agnosai_orchestrator_submit_crew` registers the crew, publishes its cancel flag and runs it on a
  detached thread. A second in-memory queue in front of it would be a second source of truth for
  status — the shape of `ORACLE-AUDIT.md` §3.4, added deliberately. `lib/majra.cyr` also exports ~40
  unprefixed names and unprefixed enum members (`ERR_NONE`…`ERR_IPC`); they are collision-free
  today, but M1 met a `var BACKEND_COUNT` collision nothing warned about. Durable queueing, if a real
  requirement appears, lands on `src/engine/ledger.cyr`. This supersedes CYRIUS-PORT-BRIEF D2's
  "majra owning the queue"; this entry is the only record of it.
- **2026-08-21 — Every request field is forwarded, refused by name, or retained and named.**
  "Forwarded or rejected" was too few: `focus` and `allow_delegation` are carried by the canonical
  presets, and the engine has no slot for either, so they are retained and named in an
  `unforwarded` array on every response. Three dispositions, all visible on the wire, no fourth.
  Why: the oracle dropped six fields silently (`ORACLE-AUDIT.md` §2.2; `gpu_strict` turned a
  hard-fail GPU requirement into a silent CPU fallback). (CHANGELOG 0.1.1, M3 part 2.)
- **2026-08-21 — `AGNOSTIC_CREW_MAX_CONCURRENT_TASKS` stays out until agnosai F5 enforces it.** It
  was removed before it shipped: `agnosai_orchestrator_budget` had no call sites and nothing read
  `max_concurrent_tasks`. `max_duration_secs` is read, so `AGNOSTIC_CREW_TIMEOUT_SECS` stays.
  (CHANGELOG 0.1.1, Removed.)
- **2026-08-21 — Audit point 6 (path traversal): no request input reaches the filesystem.** Only
  `patra_open` and `patrastore_open` touch disk, both with operator config (`AGNOSTIC_DB_PATH`,
  `AGNOSTIC_AUDIT_PATH`). Persistence is a database keyed by validated identifiers, and those are
  closed sets — agent keys `[a-z0-9][a-z0-9-]*` (`agnostic_key_is_valid`), 18 compiled-in preset
  names, UUID crew ids — so a key that cannot contain `/` or `.` is safe by construction rather than
  by a `../` check. It re-opens at M8.
- **2026-10-03 — Not adopted from herdr:** coordinating by screen-scraping, and unsandboxed
  out-of-process plugins. agnostic's plugin model (ADRs 0004, 0005, 0007, 0010) is already
  stronger ([landscape review](research/2026-10-03-herdr-and-multi-agent-landscape.md)).
- **2026-10-03 — A crew a restart interrupted answers `interrupted`, not 404**
  ([ADR 0013](../adr/0013-a-crew-interrupted-by-a-restart-is-interrupted.md),
  [architecture 001](../architecture/001-what-survives-a-restart.md)). Submit writes a status-less
  in-flight row, and mount sweeps each one left to a terminal `interrupted`. Stored outcomes stay
  terminal-only and the ledger is never seeded from disk, which meets M4's objection to persisting
  non-terminal state by construction. Resuming a crew waits on agnosai F4.
- **2026-10-03 — The estimator's one-agent baseline is its own model**
  ([ADR 0014](../adr/0014-the-estimators-one-agent-baseline-is-its-own-model.md)): `soloRun`, at
  the swarm's own token spend, not the Sim with one agent allowed, so the Sim and its pinned
  estimates do not move.
- **2026-10-04 — No `events_lost` field on the event cursor** (H3, closed at 0.1.13 with no wire
  change). Since 0.1.9 a cursor older than the 256-event window gets every event still held, from
  the oldest, plus `missed`, the count the ring overwrote
  ([ADR 0009](../adr/0009-crew-progress-is-collected-by-the-server.md)). `events_lost: true` would
  restate `missed > 0` under a name that collides with `lost_events` (events the bus dropped before
  they were numbered); the oldest cursor still available is `events[0].seq`, and `after=0` already
  means "everything still held"; and re-reading `GET /api/v1/crews/{id}` recovers nothing mid-run.
  A real mid-run resync is agnosai F3's per-task snapshot.
- **2026-10-04 — A task carries selection hints**
  ([ADR 0017](../adr/0017-a-task-carries-selection-hints.md)): `required_tools`, `complexity`,
  `domain` and `gpu_required`, each checked strictly at the door, though they widen the public
  request before the v1.0 freeze. Without them agnosai's selection is degenerate: complexity alone
  decides, and the first agent with medium or unset complexity wins every task.

## Release shape

**Decided 2026-08-20 — one release. M1–M9 ship together as 1.0.0.**

`cyrius/CLAUDE.md:96` permits 1–2 releases for a multi-phase arc and AgnosAI used two, but Agnostic
cuts as a total. The consequence to plan around: there is no intermediate tag, so `main` must stay
green the whole way rather than being stabilised once per release — every milestone lands with its
gates passing, and nothing is left "to be fixed before the cut".

The 0.1.x line changed one part of this: patch releases are tagged from `main` as work lands
(0.1.1 onward; M0–M5 shipped in 0.1.0 and 0.1.1), so there are intermediate tags. The rest stands:
`main` stays green, and 1.0.0 is the release that completes M6–M9. The original plan's
per-milestone versions (v0.2.0 to v0.9.0) are not used.

## Out of scope for v1.0

- **A TUI.** D3 scopes the GUI to a static bundle; a richer GUI comes later and a TUI is optional
  future work.
- **Re-implementing anything AgnosAI owns.** If a capability lives in the engine tier, Agnostic
  calls it — it does not fork it.
- **Kubernetes topology parity.** The oracle's multi-container postgres deployment does not survive
  the move to embedded `patra`, which is a single-file store, `flock`-arbitrated, with no
  client/server mode.
- **The oracle's benchmark numbers as a performance target** — they are invalid
  (`ORACLE-AUDIT.md` §4). The Cyrius line starts its own baseline.
- **A SecureYeoman compatibility shim.** SY can consume AgnosAI directly, so no shim is needed for
  v1.0. If one is wanted later it is *additive* — a translation layer mounted over the published
  API — and it is built then, against a real requirement, rather than pre-emptively shaping v1.0
  around a client that may never call us.
