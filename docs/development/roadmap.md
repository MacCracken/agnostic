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
  verification. Why it is here: the
  [landscape review](research/2026-10-03-herdr-and-multi-agent-landscape.md) §5 B2.
  - ⚠ **Not expressible today, corrected 2026-10-07.** The review called it "expressible as a DAG
    today, so it needs no engine change". It is not: agnosai's DAG only orders tasks. A task's
    prompt is its own context and description (`_agnosai_crew_build_request`); no runner hands a
    dependent task its dependencies' outputs (`_agnosai_crew_run_dag` keeps them in `completed`
    only to decide what is ready). So the review task would have nothing to review.
  - Needs, in order: (1) agnosai hands a dependent task its dependencies' outputs, as data, in its
    context — the first half of agnosai **F9**, whose harness rule (a hand-off is as untrusted as
    what it summarised) applies; (2) agnostic forwards a task's `output_schema` (agnosai validates
    and retries against it already; agnostic's task allow-list has no slot), a widening of the
    public request ahead of the v1.0 freeze; (3) the preset and its documentation.

**Prerequisite:** `yantra` needs `Page.captureScreenshot` on its CDP surface.

**Prerequisite (recorded 2026-10-03): agnosai must run a tool-calling loop.** `execute_task` is
one chat completion plus the output-schema retry. Nothing in `crew_runner.cyr` or `src/llm/`
handles a `tool_call`, so a resolved tool is never invoked by the model. That makes the
viability gate necessary but not sufficient: every name can resolve and still no tool runs.
This is agnosai **F1**. Settle the tool-registry seam ([`handoff.md`](handoff.md) §8) together
with it: `agnostic_engine_init` exposes no registry handle, so the gate is not wired into mount.
What agnostic will hold the loop to is under
[Waiting on agnosai](#waiting-on-agnosai-release-agnosai-then-re-pin).

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

**What agnostic will hold them to — harness rules, recorded 2026-10-07.** From a comparison with
[turnstone](https://github.com/turnstonelabs/turnstone), a self-hosted, tool-using agent harness,
whose [`PRIMER.md`](https://github.com/turnstonelabs/turnstone/blob/dev/PRIMER.md) states these
rules ("the model proposes; the gate disposes"). Mirrored the same day in agnosai's roadmap, in
its F1–F3, F5 and F9 rows; each goes into the ADR of the item it names.

- **F1 — every tool call is journaled before it runs, and its result says what it did:** committed,
  none (it never started) or unknown (it may have run). A crew a restart interrupts then names its
  unknown effects instead of implying there were none. ADR 0013's in-flight row is the same rule for
  a whole crew. turnstone also records `partial` and `rolled_back`.
- **F1 — a tool's output is data, never instructions.** Check each result for injected
  instructions before it reaches the model, and never let one change the plan, the agent's grants
  or its budget. A summary handed downstream (F9) is as untrusted as what it summarised. A QA
  product needs this more than most: the system under test produces the tools' output, so that
  output is untrusted by definition. turnstone's output guard is heuristic and only annotates;
  decide in F1's ADR whether a flagged result is held back.
- **F1 — the calls a model makes in one turn are approved as a set.** "Read the secret" and "post
  to the web" each pass alone and leak together. turnstone's pipeline is a template: prepare each
  call in turn, approve the batch, run it in parallel, then check the results and append them in
  one step.
- **F1 — the registry can hold tools from external MCP servers**, through bote's client (see
  "Upstream"), and each agent sees only the tools granted to it (see "Agent skills" under "Later").
  turnstone's harness owns its registry, gives each role its own subset (interactive, coordinator,
  sub-agent) and merges a session's MCP tools in when it starts — a data point for the registry
  seam (`handoff.md` §8).
- **F2 — authority only narrows.** A worker holds at most its manager's tools and budget. A need
  beyond them goes up to a human; neither the manager nor the model can grant it.
- **F3 — a model judge may only tighten.** If approvals gain an LLM judge, it may refuse what the
  rules allow and never allow what they refuse, and it gives its reasons from a fixed list, not
  free text. An automatic approval covers a whole batch or none of it, and anything uncertain goes
  to a human (turnstone's Smart Approvals).
- **F5 — budgets subdivide** down the tree: crew, then task, then delegated worker.

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

### Audit chain

- [ ] **The audit route serves only the newest 1024 entries** (ADR 0011). A ranged, allocator-aware
  read in libro would let it page the whole trail. Recorded in libro's roadmap ("Ideas",
  2026-10-03), not slotted until a deployment needs more than the newest 1024 entries.

### Memory

- [ ] **A crew or definition body refused part-way keeps what the decoder had built** (measured at
  0.1.15 with `tests/request_alloc.tcyr`'s method: 152 B for a crew refused for an agent's unknown
  field, 672 B for one refused for a task's, 392 B for a definition refused for its `complexity`).
  `agnostic_crew_req_from_value_a` and `agnostic_agent_def_decode_a` build the engine's objects as
  they go — `agnosai_agent_new` and the `str_clone`d fields, the agents and tasks vecs, the
  definition record — on the global heap, because an accepted request hands them to the engine or
  the definition cache; a refusal after the first of them strands them. 0.1.15 moved the refusal
  messages, the field-name keys and the wire names into the arena or interned them; what is left is
  the objects. Authenticated callers only (`crews:write`, `definitions:write`).
  - Fix direction: validate the whole body first, in the request's arena, and build the engine
    objects only once nothing can be refused. Then add the three cases to `request_alloc`.
- [ ] **An audited request keeps libro's entry on the global heap** (~250 B per audit record,
  measured at 0.1.15 by `tests/request_alloc.tcyr`'s `_t_libro_record_cost`). Every other byte a
  request path kept is in the request's arena since 0.1.15, and that suite holds them to 0.
  `chain_append` builds an entry (struct, timestamp, hash, algorithm Strs) per append; a streaming
  chain keeps only its hash. libro 2.9.0's `chain_append_nokeep` reuses one scratch entry but
  returns only the head hash, and agnostic needs the entry to store it (`patrastore_append`) and
  to copy it into the kept ring. The ask, for libro: an append that builds its entry in a caller's
  allocator, or a `nokeep` that hands back the scratch entry for the duration of the call. Then
  re-pin and drop `_t_libro_record_cost`'s allowance. Not filed yet.
- The outbound calls' remaining bytes (an exporter batch, an inference call) are in sandhi's
  dispatch path; see "Upstream".

### Telemetry

- [ ] **agnostic exports no span of its own** (ADR 0018). When agnostic mints the traceparent, a
  crew's `invoke_workflow` span names a parent that is never exported, so a backend shows the
  trace's root as missing; the trace id still joins it to the request's logs. Fix: record an HTTP
  SERVER span per request through agnosai's exporter (`agnosai_telemetry_record_span_in`), whose
  span id is the minted one. Additive. agnosai 2.1.7 carries what it needs (its ADR 024; checked
  against this plan before the cut): build the span with `agnosai_http_server_span_a` in the
  request's arena and record it with `self_sc = agnosai_otlp_span_context_parse_a(a, tp)`; the
  ring encodes into its own arena, so neither step touches the global heap. With an inbound
  `traceparent`, mint a child of it in `src/trace.cyr` (same trace id and flags, a fresh span id,
  in the arena), record the SERVER span under it with the inbound one as `parent_sc`, and hand
  the crew the child, so `invoke_workflow` nests under agnostic's span. Not
  `agnosai_otlp_span_context_child`: it allocates 32 B on the global heap per call, which
  `tests/request_alloc.tcyr` would catch. Waits on the 2.1.7 tag and the re-pin.
- [ ] **OTel variables not read** (ADR 0018): `OTEL_SDK_DISABLED` and the sampler variables
  (`OTEL_TRACES_SAMPLER`, `OTEL_TRACES_SAMPLER_ARG`). Add them only with a deployment that needs
  them.
- [ ] → **agnosai**: an operator switch to restart an untrusted inbound trace (agnosai's ADR 023
  follow-up). Until then a `-00` traceparent switches off span export for the sender's own crews
  (ADR 0018).

### Tests, tooling and docs

- [ ] **`BENCHMARKS.md` was last generated at 0.1.0** (`59325f3`, dirty, one benchmark); the bench
  has 16 now. The parser is not the problem: checked at 0.1.15, `scripts/bench-history.sh`'s pattern
  matches every line of `cyrius bench`'s output at 6.6.14. What is owed is the run, on a clean tree
  right after a tag so the row names a commit: `git checkout 0.1.15 && ./scripts/bench-history.sh`,
  then commit `BENCHMARKS.md` and `bench-history.csv`. Do it at each tag from then on, and add that
  step to the Process if the user agrees (CLAUDE.md is the user's file).
- [ ] **Retire the `CYRIUS_PKG_VERSION` setter when cyrius resolves it two includes deep.**
  `src/main.cyr` hands the version to `src/routes/health.cyr` (`agnostic_version_set`) because the
  constant resolves only in the entry file and the files it includes directly; health is two deep.
  Filed 2026-10-07 as cyrius `2026-10-07-pkgver-not-visible-in-nested-includes.md` (⚠ untracked in
  the cyrius checkout until its maintainer commits it). When a cyrius that fixes it is pinned:
  read the constant in `health.cyr`, delete the setter and its call, and pin the version to the
  `VERSION` file in `tests/health.tcyr` (`routes/version`). ⚠ A probe must not mention the name in
  a comment of the entry or a directly included file — that alone keeps the declaration.

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
- [ ] → **patra**: an INSERT whose page write fails reports success (found 2026-10-07, reading
  patra for 0.1.15's audit fix). `tbl_insert` (`lib/patra.cyr:4200`, 1.15.1) calls `page_write`
  three times and ignores each result, though `page_write` answers `PATRA_ERR_IO` or a WAL refusal;
  it returns `PATRA_OK`, and `_exec_insert` then commits the header. So a full disk or an I/O error
  loses the row while the caller is told it was stored. For agnostic: a crew outcome, a definition
  or a plugin document is reported saved and is not; an audit entry is counted appended, the chain's
  head moves to it, and the next start reports the trail `altered` at the entry after it.
  - Not reachable in a suite here (it needs an I/O error on write). Fix at source: propagate each
    `page_write` result out of `tbl_insert` (and check the other callers that ignore it), then
    re-pin through a cyrius fold. Not filed yet.
- [ ] → **agnosai**: streamline its preset set (18 in `src/presets/`) to a small illustrative example
  library rather than a competing production one, so the two stop diverging by accident (Settled
  decisions, preset canon). Not yet on agnosai's roadmap.
- [ ] → **bote**, through agnosai's tool registry (F1): the client half of MCP, so a crew's agents
  can call tools on external MCP servers. bote is the ecosystem's MCP layer (Settled decisions,
  2026-10-07). At 3.3.16 it is the server half — dispatch, six transports, sessions — plus a
  `HostRegistry` of permitted external hosts behind an SSRF guard, whose entries can already
  declare a `tools/call` capability. Nothing in it sends `initialize`, `tools/list` or `tools/call`
  to another server yet (checked 2026-10-07). Recorded in agnosai's roadmap (*C*, bote); not
  filed with bote yet.

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
    through a per-route table the schema also reads;
  - an OpenAPI 3.1 rendering, which needs the field types above — ADR 0015 rejected it until then.
    After that it is one more generator over the same data, and standard tooling can produce
    clients from it, as turnstone produces its Python and TypeScript SDKs from its specs.
- **Agent skills, narrowed to the work** (recorded 2026-10-07; a maybe). A skill is a named
  procedure, instructions plus the tools it needs, in the SKILL.md shape `skills/agnostic/SKILL.md`
  already uses for coding agents. An agent definition or a task names the skills its work needs,
  and the agent sees only those: their instructions in its prompt, their tools within its grants. A
  skill can narrow what an agent sees and does, never widen it (F2's rule, under "Waiting on
  agnosai"). turnstone's skills carry instructions with allowed tools, an auto-approve policy and a
  token budget, applied when a session starts, and each role gets its own tool surface.
  - Open: where the catalogue lives (agnostic owns definitions and presets; the engine would
    inject the instructions and restrict the tools); whether instructions load on demand
    (SKILL.md's name and description first, the body when used); and whether the retained `focus`
    maps onto skills — it is free text on all 76 preset agents, and the engine has no slot for it.
  - A `skills` field on the agent model follows the three dispositions: refused by name until the
    engine acts on it. It needs F1, and belongs with the tool-registry seam (`handoff.md` §8).
- **An evaluation harness: incorporate or port [model_testing](https://github.com/MacCracken/model_testing)**
  (recorded 2026-10-07). A Node bench, so far mostly a front end for testing a model with and
  without a harness, with more work needed. It scores the same goal in four modes — no harness,
  tools only, an output schema only, both — against a local system under test, over task families
  from tool selection, chained calls and long context to extraction, multi-turn policy and public
  anchors (GSM8K, IFEval, BFCL), and reports each harness delta with its significance. Its
  `@stress:injected` documents already measure what F1's output rule is for. Whether to
  incorporate it as it is or port it to Cyrius is decided when it is picked up.
  - Why: Swarm Command's simulator models time, tokens and cost, and has no model of answer
    quality ([ADR 0014](../adr/0014-the-estimators-one-agent-baseline-is-its-own-model.md)). This
    would measure quality. turnstone ships the same pair as `turnstone-eval` and a prompt optimizer.
  - Its tool modes need F1: today no agent calls a tool.

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
- **2026-10-07 — The MCP client is bote's.** A crew's agents reach external MCP servers through
  bote, the ecosystem's MCP layer, by way of agnosai's tool registry (F1). Neither agnostic nor
  agnosai carries its own MCP client. The client half is owed upstream (see "Upstream").

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

## Recorded by cyrius 6.6.17 (2026-10-05) — for the next cyrius pin move

⛔ **Nothing to do until cyrius 6.6.17 is tagged and out.** Docs-only note from the cyrius 6.6.17 lanes; each item
is this repo's to adopt when it pins ≥ 6.6.17. Nothing here gates a cyrius release.

- **`lib sync` now checks the lock** (cyrius 6.6.17 t1). This repo's CI runs `lib sync` → `deps` →
  `deps --verify`: no change needed — with a correct committed lock `lib sync` leaves it byte-identical. If the
  installed snapshot moves under the pin, CI now fails at `lib sync` with a named refusal instead of later at
  `deps`.
  ⚠ One agnostic workflow runs `lib sync` → `deps` with NO final `deps --verify`; that one CAN go red: a lock
  committed after a build-first pin move carries the previous pin's rows, which `lib sync` now refuses — run
  `cyrius lib sync --full` before committing the lock, or `--relock` if `deps` / `build` already ran.
- **`[deps] stdlib` now reads as written** (cyrius 6.6.17 m6). A `]` inside a `#` comment within a string
  array used to END the array; this manifest's `stdlib` comments name `` `[deps.*]` `` and
  `` `[deps.sigil]` ``, so its "patra" and "sigil" leaves were silently dropped. From 6.6.17 they are vendored
  and the include order moves (both orders build; +16 B). Nothing to change unless those leaves were meant
  to be out.

## Recorded by cyrius 6.6.19 (2026-10-06) — for the next cyrius pin move

⛔ **Needs cyrius >= 6.6.19 — do not bump the pin until 6.6.19 is tagged and out.** Docs-only note from the cyrius
6.6.19 lanes; each item is this repo's to adopt when it pins ≥ 6.6.19. Nothing here gates a cyrius release.

- **`scripts/gen-presets.sh` retires, and `scripts/gen-webgui.sh` keeps only its CSP half, via `[embed]`**
  (cyrius P2, shipped in 6.6.19).
  `[embed] NAME = "path"` in cyrius.cyml gives every compile `NAME()` (the file's bytes, NUL-terminated) and
  `NAME_len()`, read from the file at build time — no generated `.cyr`, nothing to drift. Explicit entries only
  (the `{dir, glob}` set form is refused by name). All embeds share cycc's 2 MiB string pool with the program's
  own literals, and every binary of the project (test binaries too) carries every declared embed. Reference: the
  cyrius guide's *Embedding data files: [embed]*, CHANGELOG [6.6.19] *Embed — P2*.
  - Replaces `gen-presets.sh` outright (one `[embed]` entry per preset) and the ESCAPING half of `gen-webgui.sh`:
    the pages embed verbatim (`WEBGUI_INDEX = "webgui/index.html"`), bytes exact, no raw-LF literal shaping.
  - Stays yours: the Content-Security-Policy hashing and validation (`check-webgui-js.sh` and the hash step of
    `gen-webgui.sh`). `[embed]` does not hash; compute the CSP hashes from the same files in a script, or at run
    time from `NAME()` / `NAME_len()`.
  - Freshness: a page edited without a rebuild can no longer ship stale — the build reads the file.
