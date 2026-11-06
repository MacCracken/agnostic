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
tools, identity and tenancy, persistence and reporting, and the GUI. Sequencing follows
the release plan below, not the Python tree's layout. What has and has not been ported, area by
area, is in the [parity review](research/2026-11-05-python-port-parity.md).

agnostic is the project, written in Cyrius. `python-port/` is its former code: a **reference, not a
specification**.
[`../../ORACLE-AUDIT.md`](../../ORACLE-AUDIT.md) records 86 verified defects in it; several of its
paths are wrong, and reproducing them faithfully would reproduce the bugs. Check that document
before porting any behaviour.

## Release plan

Which release line takes which owed item. The items themselves, with their evidence, are in the
sections below; this one only sequences them. One minor line per theme, with patch releases inside a
line as each piece lands. Decided 2026-11-05: this replaces "one release", though 1.0.0 is still the
release that completes M6–M9 (see *Release shape*).

agnostic's lines lean on agnosai's: its 2.3.x carries the tool loop M6 needs, 2.4.x the approvals and
budgets, 2.5.x the durable crew log, and 2.6.x MCP 2026-07-28 and A2A v1.0.x.

### 0.2.x — hardening and housekeeping

- **Re-pin agnosai once it carries the crew-registry fix**, and delete `_agnostic_crew_retire_a`'s reach
  into the orchestrator's fields ([ADR 0022](../adr/0022-a-finished-crew-leaves-the-engines-registry.md),
  *Upstream*). bote 3.8.15 comes with that re-pin.
- **`GET /crews` reads the tenant's whole history**, whatever `limit` says (*Open*, Performance).
- **A stored crew is parsed and re-encoded** on read (*Open*, Performance).
- **A CI step that boots the binary and probes it** (the parity review's G17): socketpair suites miss
  what a real listen catches, and `CYRIUS_DCE=1` on CI's test builds tests the shape it ships.
- The benchmark rows the audit asked for (*Open*, Tests).
- **A load test in the tree**: 16 clients and 6,000 crews, as the audit ran by hand. The first version
  of ADR 0022's fix passed every suite and lost most of them under this.
- Any time: `[embed]` and `deps --locked` (*Available from the toolchain*).

### 0.3.x — identity, tenancy and deployment

Comes first among the feature lines because nothing else can be used by a machine without it. A
deployment has one user, no issuable API key, and tokens that die on restart, and the v1.0 criterion
"a consumer green against the published API" cannot be met until it is done. Details under *Identity and deployment*.

- **Provisioning**: users, API keys and tenants, by route or an `agnostic admin` command, with an ADR.
- **`AGNOSTIC_JWT_SECRET`**, length-checked, so a restart does not log everyone out.
- **Scope what is not scoped**: agent definitions, and ADMIN against SUPER (audit S3, S4). Both are
  latent today and become real the moment a second user can exist, so they ship together with it.
- **A trusted-proxy setting**, since TLS belongs to a proxy and a proxy gives every client one login
  bucket (audit S7).
- **Password change**, which also closes the bootstrap credential's rotation (audit S12b).
- **Deployment**: a guide for the binary, a reverse proxy and a unit file, and the Zugot recipe.
- **What a refusal leaves behind**: the rest of the audit vocabulary, and the rate-limit and Argon2
  shed counters, which nothing reads.
- **Crew memory** (*Open*, Memory), with agnosai's half.

### 0.4.x — the QA tool surface (M6)

Waits on agnosai 2.3.x: F1, and B33. M6 says "preset-declared intent", and a preset declares only a
class name and a `focus`, so each tool is designed for agnostic as it is written.

- **M6**: every one of the 38 names resolved, written or struck, with a miss an error.
- **The tool-registry seam** (`handoff.md` §8), decided with F1.
- **The reviewer preset**, once F9 hands a dependent task its dependencies' outputs (agnosai 2.4.x).
- **A crew's target** (G4): its form is question 3 in the parity review.
- **`GET /tools`** (G10), which the viability gate wants.
- **The model picker** (M9), on B33.

### 0.5.x — MCP, reports and streaming (M7, M8, M9)

Waits on agnosai 2.6.x for MCP 2026-07-28 and A2A v1.0.x.

- **M7**: `/mcp`, `/api/v1/mcp/invoke`, A2A, and the daimon registrar. Which surface it exposes is
  question 12 in the parity review.
- **The completion webhook** (G3), on agnosai's guarded fetch: how a CI job learns a run ended.
- **M8**: exports, trends and comparison. What reports read is question 4 in the parity review.
- **M9**: streaming crew events, reports in the shell, and the "which crew needs me?" badge, which
  needs agnosai F3.

### 1.0.0 — the freeze

The v1.0 criteria below, the exported symbols' half of the API freeze, a security audit re-run, and
the deletion of `python-port/`.

## Deleting `python-port/` — at 1.0.0, once M6–M8 and identity are in

Full record: [the parity review](research/2026-11-05-python-port-parity.md), which went over all 397
tracked files, 106 routes and 192 environment variables.

**The verdict: it can go whenever you say.** Nothing in the repo reads the tree: no script, suite or
CI step, and `gen-presets.sh` reads `src/presets/`, whose 18 documents match byte for byte. All of it
stays in git. What stands in the way is `first-party-standards.md:53`, which asks for equal or better
coverage, so the list below is what agnostic does not have yet.

**Blockers:**

- [ ] **M6:** 36 of 38 tool names resolve to nothing, and agnosai F1 means none would be called if they
  did.
- [ ] **M7:** MCP and A2A are not started.
- [ ] **M8:** reports are not started.
- [ ] **G1 and G2:** a deployment has one user, no issuable API key, and tokens that die on restart
  (0.3.x).
- [ ] Any parity-review question answered yes (*Decisions awaiting the user*).

M9's streaming is on 0.5.x and is not needed for the rule: the event cursor gives a client the same
events.

**Before the deletion commit:**

- [ ] Tag the parent commit, and put that rev in `ORACLE-AUDIT.md`'s header, so its citations resolve.

Everything else is recoverable with `git show <rev>:python-port/...`. There are no Grafana dashboards
or alert rules to save: `monitoring/grafana/dashboards/dashboard.yml` is a provisioning stub.

**The deletion commit:**

- [ ] `git rm -r python-port`, and delete its 8 untracked `benchmarks/__pycache__/*.pyc` from disk.
- [ ] Edit `scripts/bench-history.sh:119`, or the mention returns to `BENCHMARKS.md`.
- [ ] Update the prose that names it: `CONTRIBUTING.md`, `ORACLE-AUDIT.md`, `CYRIUS-PORT-BRIEF.md`,
  `SECURITY.md`, `docs/adr/0001…`, `docs/audit/*`, `state.md`, `handoff.md`, this file, and
  `src/routes/health.cyr:12`. All of it is stale prose: none of it breaks anything.

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
      (`first-party-standards.md:53`; *Deleting `python-port/`* above). ⚠ The benchmark half of that
      rule cannot be satisfied as written: `ORACLE-AUDIT.md` §4 shows the oracle's published numbers
      are invalid, so parity is assessed on coverage and behaviour, not on its timings.
- [x] Benchmarks captured in `BENCHMARKS.md` with a CSV trail — met at 0.1.16: all 18 benchmarks,
      run on the clean tagged tree (`024be8b`, 2026-10-08), the first full run since 0.1.0's one
      row. Keep it met: re-run `./scripts/bench-history.sh` right after each tag.
- [ ] At least one consumer green against the published API — Agnostic's own, not a
      pre-existing client's contract (see M7)
- [ ] CHANGELOG complete from v0.1.0 onward
- [ ] Security audit pass re-run at the cut. The last is
      [`docs/audit/2026-11-05-audit.md`](../audit/2026-11-05-audit.md), for 0.2.2.
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
implementation against its intent, not as a port of working code. A preset declares only a class name
and an agent's `focus`. The rest of that intent is in the Python tool classes, the only copy.

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
  worker per watcher.
- [ ] M8's reports, once they exist, as views or downloads from the shell.
- [ ] **"Which crew needs me?"** Once agnosai F3 ships, show `awaiting_approval` as a crew
  status and in its events. Roll it up as a badge from task to crew to tenant in Crews and
  Swarm Command, with an approve/reject action behind a permission. This is the HITL surface
  agnostic has none of today. The model is herdr's `blocked` roll-up (landscape review H2).
- [ ] **Pick a model from the gateway's catalog** (recorded 2026-10-09). Two places take a model id as
  free text today: the Library's agent editor (`input('llm_model', …)`,
  `src/webgui/plugins/library/index.html:705`) and Swarm Command's Live tab, one field per role
  (`paneLive`, `src/webgui/plugins/swarm/index.html`, checked against `RE_LIVE_MODEL` at `:2063`). Both say
  that leaving it empty means "the server's default", which today is agnosai's `llama3:70b` or
  `llama3:405b` (see *Waiting on agnosai*). Offer the ids hoosh's `GET /v1/models/catalog` lists, with each
  one's provider, context window and price, through an agnostic route, so the browser never holds the
  gateway's address or `AGNOSTIC_LLM_API_KEY`. Keep free text for an id the catalog does not list. With no
  `AGNOSTIC_LLM_URL` (placeholder mode) the route says there is no gateway and the field stays plain. Once
  B33 ships, the route serves agnosai's cached copy rather than a second fetch, and an empty field says what
  agnosai picks for the agent's complexity. The route sits behind a permission, as the presets list does
  (`presets:read`); the route, its permission and the cache go in an ADR.

## Identity and deployment (0.3.x)

From the [parity review](research/2026-11-05-python-port-parity.md) (G1, G2, G12, G14) and the
[2026-11-05 audit](../audit/2026-11-05-audit.md).

- [ ] **Provisioning (G1).** Nothing can add anyone after the bootstrap admin:
  `agnostic_users_create_a` is called only by bootstrap, and `agnostic_tenant_create_a` and
  `agnostic_apikey_issue_a` have no callers in `src/`. Admin routes or an `agnostic admin` command,
  with an ADR. `src/auth/jwt.cyr:72` already says an operator can install a secret; nothing lets them.
- [ ] **`AGNOSTIC_JWT_SECRET` (G2)**, refused at mount when short.
- [ ] **Agent definitions are not tenant-scoped (audit S3).** A tenant-b OPERATOR listed, read, replaced
  and deleted tenant-a's definition, reproduced in-process through the real dispatcher. Key them by
  scope, as plugin documents are. It needs a store migration.
- [ ] **Any ADMIN is a deployment admin (audit S4), against ADR 0008.** A tenant-c ADMIN read tenant-a's
  entries from the audit trail and switched a deployment-wide plugin; no route requires
  `AGNOSTIC_PERM_SUPER`. Require SUPER for those routes, or filter entries by scope.
- [ ] **A trusted-proxy setting (audit S7).** `src/auth/ratelimit.cyr:90` keys the login bucket on the
  socket peer, so behind a proxy about 5 anonymous requests a minute lock out every login.
- [ ] **Password change (audit S12b).** The mount WARN says to rotate the bootstrap credential, and
  nothing can.
- [ ] **The audit vocabulary (G12).** A failed login is audited since 0.2.2. A 401, a 403 and a
  rate-limit hit still leave nothing, and `agnostic_rl_shed_count` and `agnostic_argon_shed_count`
  have no callers. Bounded, so the trail does not become a write amplifier.
- [ ] **Deployment (G14):** a guide for the binary, a reverse proxy and a unit file. TLS is the proxy's
  job. A small image is optional.

## Waiting on agnosai (release agnosai, then re-pin)

Each of these is filed on agnosai's roadmap: F1–F5 under **F** ("Past parity"), B33 under **B** ("Owed").

- **F1 — tool loop:** M6's prerequisite.
- **F2 — hierarchical wired:** agnostic then accepts `hierarchical`, which
  `agnostic_process_from_wire` (`src/engine/request.cyr:149-159`) leaves out today, so it is a 400.
- **F3 — approvals plus a lifecycle contract with `seq`:** builds on the event and status
  semantics agnosai's B17 fixed in 2.1.5, and feeds M9's roll-up. It is also what would give a
  per-task snapshot that a reader who fell past the event ring (`missed`) can resync from mid-run.
- **F4 — durable crew log:** turns an `interrupted` crew (ADR 0013) into a resumable one.
- **F5 — budgets and caps:** brings back an `AGNOSTIC_CREW_MAX_CONCURRENT_TASKS` that is actually
  enforced.
- **The crew registry (agnostic 0.2.2's H1):** evict oldest-first down to a low-water mark, and give a
  consumer a call to forget a crew it has read. Until then `_agnostic_crew_retire_a` reaches into the
  orchestrator's fields (ADR 0022). Filed with agnosai.
- **A transport error that names the gateway's URL:** agnostic scrubs it from results. Filed with agnosai.
- **bote 3.8.15:** agnosai 2.2.3 pins 3.8.11. Nothing reaches agnostic, because neither repo calls a
  bote function, so it moves with the next agnosai release and not by an override pin here.
- **B33 — models from hoosh's catalog (recorded 2026-10-09):** a crew whose agents name no model is
  sent a model agnosai names itself: `llama3:70b`, or `llama3:405b` for a complex agent. That covers every
  preset, since none sets `llm_model`, and every agent whose *LLM model* field is left empty in the Library
  or in Swarm Command's Live tab. A gateway with no `llama*` route answers each such call
  `404 "no provider for model"`. An id an operator does type loses a leading `openai/`, `anthropic/` and the
  like, so a vendor-prefixed id such as Groq's `openai/gpt-oss-120b` reaches hoosh renamed. And a response
  that names no provider is billed by agnosai's guess from the name, which bills `o4-mini` and newer
  families to Ollama. B33 has agnosai choose and attribute from hoosh 2.8.0's `GET /v1/models/catalog`
  instead. Re-pin when it ships (the pin is `[deps.agnosai]` tag 2.2.3); M9's model picker builds on it.

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

## Open — agnostic only

Found while building, grouped by area. H and B numbers in this file are those of the
[2026-10-03 landscape review](research/2026-10-03-herdr-and-multi-agent-landscape.md).

### Audit chain

- [ ] **The audit route serves only the newest 1024 entries** (ADR 0011). A ranged, allocator-aware
  read in libro would let it page the whole trail. Recorded in libro's roadmap ("Ideas",
  2026-10-03), not slotted until a deployment needs more than the newest 1024 entries.

### Memory

- [ ] **An audited request keeps libro's entry on the global heap** (~250 B per audit record,
  measured at 0.1.15 by `tests/request_alloc.tcyr`'s `_t_libro_record_cost`). Every other byte a
  request path kept is in the request's arena — dispatch's since 0.1.15, the serve adapter's since
  0.1.16, a refused crew or definition body's since 0.1.17 — and `request_alloc` and `server_span`
  hold them to 0.
  `chain_append` builds an entry (struct, timestamp, hash, algorithm Strs) per append; a streaming
  chain keeps only its hash. libro 2.9.0's `chain_append_nokeep` reuses one scratch entry but
  returns only the head hash, and agnostic needs the entry to store it (`patrastore_append`) and
  to copy it into the kept ring. The ask, for libro: an append that builds its entry in a caller's
  allocator, or a `nokeep` that hands back the scratch entry for the duration of the call. Then
  re-pin and drop `_t_libro_record_cost`'s allowance. Filed with libro.
- The outbound calls' remaining bytes (an exporter batch, an inference call) are in sandhi's
  dispatch path; see "Upstream".
- [ ] **Under sustained load the outcome writes fall behind**, by about 200 crews a second against 86
  here (ADR 0022). A graceful stop drains the backlog, and a crash loses it to `interrupted`. Nothing
  bounds it but the load. If a deployment meets this, batching several outcomes per fsync is the next
  step; BATCH mode as it stands loses the outcome-before-delete ordering (see Performance).
- [ ] **A crew keeps about 16 KB for life, plus 1.6× its output** (audit P2): about 16 GB per million
  crews. The ledger's cap bounds entries and frees nothing, since eviction unlinks an entry and the
  global heap has no `free`. The largest parts are the ledger's event ring (4,096 B), the subscribe
  channel (2.4 KB) and the engine's spec (2.0 KB). Needs a crew-scoped arena in agnosai, and ring
  recycling here. An evicted entry can still be held by a request, so clear its ring pointer under the
  lock first.
- [ ] **Audit open holds the whole trail** (`src/engine/audit.cyr:251`): 589 B and ~16 µs per entry, so
  100,000 entries take 1.4 s and 59 MB for life. Needs a streaming verify read from libro, beside the
  ranged read already recorded.

### Telemetry

- [ ] **OTel variables not read** (ADR 0018): `OTEL_SDK_DISABLED` and the sampler variables
  (`OTEL_TRACES_SAMPLER`, `OTEL_TRACES_SAMPLER_ARG`). Add them only with a deployment that needs
  them.
- [ ] → **agnosai**: an operator switch to restart an untrusted inbound trace (agnosai's ADR 023
  follow-up). Until then a `-00` traceparent switches off span export for the sender's own crews
  (ADR 0018).

### Performance

From the audit's performance review, at 10,000 crews.

- [ ] **`GET /crews` reads the tenant's whole history**, whatever `limit` says
  (`src/routes/crews.cyr`, `src/engine/crewstore.cyr:640`): 88 ms a request, ~75 ms of it holding the
  store lock, so the p99 of another store-touching GET went from 0.45 to 80 ms with a list every
  300 ms. Memory stopped leaking at 0.2.2, but the work is still O(tenant history). Pick the page from
  the result set in place and copy only those rows, or `ORDER BY submitted DESC LIMIT n`, with `n`
  covering the crews the ledger holds. Only a recency index shortens the lock, and patra has one
  index per table.
- [ ] **A stored crew is parsed and re-encoded** on read (`src/routes/crews.cyr:160`), despite
  "verbatim" at `crewstore.cyr:38`: a 422 KB document costs 20.8 ms against 13 ms held. Read the scope
  from the index row and send the bytes; a document with no index row still needs the parse.
- ⛔ **Measured, and not to do:** a transaction around a finished crew's writes (31.5 ms against
  11.5 ms autocommit), BATCH mode for them (7.4 ms, but it loses outcome-before-delete ordering on a
  power cut), and reusing prepared statements (22 µs against 50 µs, single-threaded only:
  `audit.cyr:88` records a process-killing fault from that shape).

### Tests, tooling and docs

- [ ] **Benchmark rows the audit asked for:** `crews_list_10k`, `authn_bearer` and `authn_apikey` (109
  and 153 µs before 0.2.2), `crew_save_row` (11.5 ms), `audit_open_10k`, `serve_handler_health` (16 µs).
- [ ] **A CI step that boots the binary and probes it** (G17), and `CYRIUS_DCE=1` on CI's test builds.
- [ ] **A load test in the tree.** A suite runs one thread with no store contention, so it cannot show
  what a sweep does at 200 crews a second. Only a real server with concurrent clients did.

## Upstream — owed by sibling repos

Each is fixed at its source and reaches agnostic by a re-pin. One exception is wrapped here until
then, ADR 0022, with the gateway-URL scrub beside it. Filings are in each repo's
`docs/development/issues/`.

- [ ] → **cyrius**: `_arena_grow` keeps a chunk per slightly larger allocation (`lib/alloc.cyr`). A need
  over the chunk size gets a chunk of its own in front of the next, and a chunk too small for what comes
  next is not looked at again, so needs that keep rising each keep one. agnostic keeps its chunks at
  least the body cap (ADR 0021), which covers bodies and not responses over 1 MiB. Filed with cyrius.
- [ ] → **sandhi**: one connection holds one worker while it is read (audit S2). A per-peer connection
  cap is what closes it, since `AGNOSTIC_REQUEST_MS` only shortens it. `AGNOSTIC_IDLE_MS` also has no
  effect on that wait: `_sandhi_server_wait_request` polls until the deadline, so a shorter idle
  limit is ignored. Accepted sockets have no `SO_SNDTIMEO` either.
- [ ] → **patra**: its database and WAL files are created 0644 (`lib/patra.cyr:404`, `:1379`). agnostic
  sets the database to 0600 at mount and uses no transaction, so no WAL exists today.
- [ ] → **sandhi**, through agnosai: an exporter batch still leaves ~480 B, and an inference call
  ~2.6 KB including the reply it keeps, on the global bump in sandhi's dispatch path (16 B is the
  stdlib's `sockaddr_in`). Filed with sandhi (CHANGELOG 0.1.14, Known).
- [ ] → **patra**: an over-length STR *query literal* is clamped (found by CNAME-255, 2026-10-04).
  `row_write_str` and `_str_hash64` (`lib/patra.cyr:2128`, `:2180`, 1.16.6) cut a literal over 255 bytes to
  its 255-byte prefix. So a `WHERE` on a STR column given a longer literal hashes and compares as
  that prefix. On a write, patra refuses an over-length value (`PATRA_ERR_ROWSZ`), so the two
  paths disagree.
  - Not reachable in agnostic today. Every STR it queries is capped below 255 bytes at the door:
    tenant keys at 64, settings at 64 and 255, and crew ids are UUIDs.
  - Fix direction: an upstream patra release that refuses an over-length literal the way it
    refuses an over-length value. Fix it at source; do not wrap it here. Then re-pin. Filed with patra.
- [ ] → **patra**: an INSERT whose page write fails reports success (found 2026-10-07, reading
  patra for 0.1.15's audit fix). `tbl_insert` (`lib/patra.cyr:4989`, 1.16.6) calls `page_write`
  three times and ignores each result, though `page_write` answers `PATRA_ERR_IO` or a WAL refusal;
  it returns `PATRA_OK`, and `_exec_insert` then commits the header. So a full disk or an I/O error
  loses the row while the caller is told it was stored. For agnostic: a crew outcome, a definition
  or a plugin document is reported saved and is not; an audit entry is counted appended, the chain's
  head moves to it, and the next start reports the trail `altered` at the entry after it.
  - Not reachable in a suite here (it needs an I/O error on write). Fix at source: propagate each
    `page_write` result out of `tbl_insert` (and check the other callers that ignore it), then
    re-pin through a cyrius fold. Filed with patra.
- [ ] → **agnosai**: streamline its preset set (18 in `src/presets/`) to a small illustrative example
  library rather than a competing production one, so the two stop diverging by accident (Settled
  decisions, preset canon). Filed with agnosai.
- [ ] → **bote**, through agnosai's tool registry (F1): the client half of MCP, so a crew's agents
  can call tools on external MCP servers. bote is the ecosystem's MCP layer (Settled decisions,
  2026-10-07). At 3.3.16 it is the server half — dispatch, six transports, sessions — plus a
  `HostRegistry` of permitted external hosts behind an SSRF guard, whose entries can already
  declare a `tools/call` capability. Nothing in it sends `initialize`, `tools/list` or `tools/call`
  to another server yet (checked 2026-10-07). Recorded in agnosai's roadmap (*C*, bote); not
  filed with bote yet.

## Decisions awaiting the user

- [ ] **The parity review's thirteen questions**
  ([§3](research/2026-11-05-python-port-parity.md#questions-for-the-user)). Each asks whether the project
  wants something agnostic does not have. A yes puts it on the release plan.
- [ ] **Make the post-tag benchmark run part of the Process?** 0.1.16's was run on request, right
  after the tag, on the clean tree: `./scripts/bench-history.sh`, then commit `BENCHMARKS.md` and
  `bench-history.csv`, so each row names a tagged commit. The proposal is a clause in CLAUDE.md's
  Process; CLAUDE.md is the user's file.

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

**Decided 2026-08-20: one release, with M1–M9 shipping together as 1.0.0. Changed 2026-11-05: minor
lines, 0.2.x to 0.5.x**, as in the *Release plan* above.

1.0.0 is still the release that completes M6–M9, and `main` still stays green the whole way: every
line lands with its gates passing, and nothing is left "to be fixed before the cut". Patch releases
are tagged from `main` as work lands.

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

## Available from the toolchain, not adopted

Each is optional, and nothing here gates a release.

- **`cyrius deps --locked`** (6.7.6) resolves, writes nothing and fails naming each difference, so it
  can replace `scripts/lock-check.sh`.
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
