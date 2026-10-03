# What herdr and the multi-agent field can teach agnostic and agnosai

> **Date:** 2026-10-03 · **Pins at time of writing:** agnostic 0.1.11, agnosai 2.1.3 · **Type:** research note (not an ADR)
>
> **Sources:**
> - herdr: docs 0.9.3 and repo `herdrdev/herdr`.
> - Industry: vendor docs, release registries, and the papers cited inline.
> - agnostic and agnosai: their own `docs/` and `src/`.
>
> Claims about other projects are marked **[secondary]** where the only source was press or aggregator coverage. Any recommendation here that the user adopts becomes an ADR or roadmap item. This note decides nothing by itself.

---

## 1. Summary

1. **herdr is a different layer from us, not a competitor.**
   - herdr owns the *terminals* of CLI coding agents (Claude Code, Codex and others). It infers each agent's lifecycle state (`blocked / working / done / idle / unknown`) and exposes those agents through a socket/CLI API, which lets one agent supervise others.
   - It has no planner, DAG, LLM routing, budgets, sandbox or cost accounting.
   - agnostic and agnosai are an API-driven crew engine. herdr's value to us is in its **lifecycle, wait and resync contracts**, its **survival-table honesty**, and its **agent-as-API-client** ergonomics. Its orchestration model has little to offer us.

2. **The field converged on orchestrator-worker with a single writer, durable execution, and pluggable isolation.**
   - The evidence (Anthropic, Google/DeepMind scaling study, MAST, Tran & Kiela 2026) says multi-agent wins only on breadth-first, parallelizable work under a central coordinator. It also costs roughly 10–15× the tokens.
   - Uncoordinated swarms amplify errors: 17.2× for independent agents versus 4.4× under a central coordinator.

3. **agnosai has most of these industry-standard pieces built but not wired into `crew_runner`.** These include hierarchical delegation, the HITL approval gate, budgets, `durable_state`, fleet and learning.
   - It also has **no tool-calling loop**: `execute_task` is one chat completion plus schema-retry.
   - Wiring these is a better use of time than building anything new.

4. **MCP 2026-07-28 suits agnostic's architecture unusually well.** It has a stateless core with no session handshake, plus the official **Tasks** extension for pollable long-running work. That maps directly onto 202-then-poll crews and the no-SSE pooled-worker constraint (ADR 0009). M7 should target this spec revision.

---

## 2. herdr in one page

| Aspect | herdr (0.9.3, Rust, Apache-2.0, ~42k★, $6M seed) |
|---|---|
| Unit | Real PTY panes in workspaces/tabs, owned by a background **server**. The TUI is just one client. |
| Agent integration | Runs agent CLIs unmodified. State comes from **screen-scraping TOML "detection manifests"** (hot-updated from herdr.dev), from hooks installed into the agent's config, or from agents that **self-report** with `pane report-agent --state … --seq N`. |
| Lifecycle | `blocked` (needs a human) · `working` · `done` (finished, not yet seen) · `idle` · `unknown`. Rolls up pane → tab → workspace. |
| Multi-agent | No engine. Its primitives are `agent start / prompt --wait / read / wait --until <state>` and `pane wait-output --regex`. A supervising agent uses them through a shipped `SKILL.md`. Agents communicate by typing into each other's terminals and reading their screens. |
| Wait semantics | Waits are server-owned and event-driven. A wait is tied to the specific agent it started on, so a replacement agent in that pane can't satisfy it. Errors are explicit: `agent_blocked` (refuses to type into a blocked agent), `agent_prompt_stalled` (no activity within 5 s), `timeout`. The docs warn that a timeout *does not prove input wasn't sent*. |
| Events | `events.subscribe` (NDJSON over a Unix socket). History is not durable. A slow client gets `events_lost` and must resync from `session.snapshot`. |
| Persistence | Documented tier by tier: detach (processes live) → restart (layout restored, agents resumed with `--resume <id>` if the session id was reported) → opt-in screen history → experimental live PTY handoff across a binary update. |
| API surface | The CLI is a thin JSON client of the socket API. `herdr api schema --json` prints the full schema. Exit code 1 means a server error, 2 means a usage error. |
| Plugins | Out-of-process argv commands declared in `herdr-plugin.toml`. **Not sandboxed**: "runs as your user." |
| Gaps | No isolation, no conflict/merge handling, no cost tracking, no task decomposition. Coordination by screen-scraping is fragile by nature. |

---

## 3. Lessons from herdr, mapped to us

### H1. A formal agent and task lifecycle contract with sequence numbers → **agnosai** (fixes B17)

herdr's self-report contract (`--state`, monotonic `--seq`) is a small, testable state machine. agnosai's B17 list breaks exactly that kind of contract:
- `RUNNING` is never stored.
- Timeouts are reported as completed while the registry says FAILED.
- Token events carry `crew_id: "unknown"`.
- `task_started` is emitted per wave.

**Proposal:**
- agnosai specifies one lifecycle state machine for crews and tasks, covering the states, the legal transitions, and a per-crew monotonic `seq` on every event.
- It tests the state machine as an invariant: no event without a valid transition, and no gaps in `seq`.
- agnostic's collector (ADR 0009) then validates `seq` and treats a gap as a defect, not something to tolerate.
- Following the fix-at-source rule, this ships as an agnosai release. It is not a workaround in agnostic.

### H2. A `blocked` / `awaiting_approval` state and roll-up → **both**

herdr's whole UX rests on one question: *which agent needs me?* agnosai's approval gate (`orchestrator/approval.cyr`) is built and has routes, but `crew_runner` never calls it.

**Proposal:**
- Wire the gate (§5, A3) and add `awaiting_approval` to the H1 state machine.
- agnostic surfaces it as a crew status, in its events, and as a **roll-up badge** in the Crews and Swarm Command plugins (task → crew → tenant).
- This is the HITL story agnostic currently lacks entirely.

### H3. A resync signal when events are lost → **agnostic** (cheap)

agnostic's ledger keeps 256 events per crew and 1024 crews (`state.md`). herdr's rule is: if a client falls behind, say so explicitly (`events_lost`) and point it at a snapshot.

**Proposal:**
- When a client's `since` cursor is older than the oldest retained event, `GET /crews/{id}/events?since=` returns an explicit `events_lost: true` along with the oldest available cursor.
- The client then re-reads `GET /crews/{id}`.
- Today a gap like this would be silent.

### H4. Publish a survival table and stop returning 404 for interrupted crews → **agnostic**

herdr documents exactly what survives a detach, a restart, or an update. agnostic persists terminal outcomes only, so a crew interrupted by a restart **returns 404** (`state.md`, `roadmap.md`).

**Proposal:**
- Write a crew row when the crew is submitted.
- At start-up, mark any non-terminal rows as `interrupted`, keeping their completed-task results per ADR 0012's rule.
- Add a "what survives" table to `docs/architecture/`.
- Full resume is a later step that depends on agnosai's `durable_state` (A4).

### H5. Self-describing API: `agnostic api schema` → **agnostic** (supports the v1.0 frozen-API criterion)

herdr's `api schema --json`, together with JSON-only CLI output and distinct exit codes, makes it scriptable by agents.

**Proposal:**
- The binary emits its route table, request/response shapes and error-code catalogue as JSON.
- A test diffs that output against a checked-in snapshot, so v1.0's "frozen API" becomes a mechanical check instead of a promise.

### H6. Ship a `SKILL.md` for driving agnostic → **agnostic**

herdr's `skills/herdr/SKILL.md` lets Claude Code or Codex act as a supervisor. Its guardrails are concrete: check the environment variable, don't close what you didn't create, ask the human before answering a blocked agent.

**Proposal:**
- A `skills/agnostic/SKILL.md` covering submitting a crew, polling with a cursor, cancelling, reading usage and cost, and the refusal semantics (422 per refused field, hierarchical refused).
- SKILL.md is now a cross-vendor standard (Claude Code, Codex, Gemini CLI, Cursor, Goose; adoption counts **[secondary]**).
- It is cheap and complements the M7 MCP work.

### H7. An "explain" endpoint for engine decisions → **agnosai, then agnostic**

`herdr agent explain` shows *why* a pane was classified as it was. agnosai chooses agents per task by weighted scoring (tools, complexity, domain, personality, GPU) and keeps the reasoning internal.

**Proposal:**
- agnosai returns the score breakdown.
- agnostic's existing `/crews/{id}/plan` (or the response to a submit) includes it, which helps both debugging and the Swarm Command UI.

### H8. Render only what is visible → **Swarm Command**

herdr reports ~95% less CPU with 10 agents and 3 clients from retained-frame diffs and rendering only what is visible. Only the selected machine streams. If LIVE missions grow large, Swarm Command's renderer should apply the same idea: skip off-screen units and diff rather than redraw. This is low priority until it shows up in a profile.

### What not to copy from herdr

- **Coordinating by screen-scraping.** It is fragile by herdr's own admission. We have structured events.
- **Unsandboxed out-of-process plugins.** agnostic's model is already stronger: compiled-in, admin-enabled, iframe `connect-src 'none'`, a `postMessage` bridge and `permissions.json` (ADRs 0004/0005/0007/0010).

### A strategic option, not a recommendation yet

herdr's "own the runtime, not the agent" framing raises a question: should an agnosai agent be able to *be* an external coding agent? Claude Code or Codex would be driven through **ACP** (structured JSON-RPC over stdio), not by scraping a PTY. That would make agnostic a QA orchestrator over best-in-class harnesses instead of competing with them. It only matters after the in-house tool loop (A1) exists.

---

## 4. Industry landscape, condensed

### 4.1 Who does what (October 2026)

| Category | Players | Orchestration model | Durability | Isolation |
|---|---|---|---|---|
| Harness / SDK | Claude Code + Agent SDK, Codex CLI / Agents API, OpenHands SDK, Goose | Orchestrator-worker subagents. Claude adds experimental peer "Agent Teams" and Dynamic Workflows (scripted fan-out with adversarial verification). | Transcripts, checkpoints, resumable workflows. OpenHands is event-sourced. | Worktree → OS sandbox → container → cloud VM. The harness and the compute are increasingly split. |
| Frameworks | LangGraph 1.2, MS Agent Framework 1.x (AutoGen + SK), Google ADK 2.x, CrewAI 1.15, AG2 1.x, Pydantic AI 2.x, Mastra 1.x, smolagents, Letta; DSPy as an optimizer | Graphs have won (LangGraph, ADK 2.0, MAF workflows). CrewAI kept role-crews but added deterministic Flows. AG2 replaced GroupChat/swarm with a Hub plus typed channels. | Checkpointers everywhere. Temporal, DBOS, Restate or Durable Task back Pydantic AI, OpenAI SDK and MAF. | Pluggable sandbox providers (E2B, Modal, Daytona, Cloudflare, …) |
| Multi-session UIs | herdr, Conductor, Claude Squad, container-use, Sculptor. Dead or stale: Crystal, Vibe Kanban (company), uzi, Roo Code (archived). | Human as orchestrator | — | Worktrees, or containers (container-use, Sculptor) |
| Vendor command centers | Codex app, Cursor 3 Agents Window, Devin Desktop (manager/child Devins, hosts ACP agents) | The vendor absorbs the multi-session UX | — | Worktrees, then cloud VMs |

### 4.2 Protocols

| Layer | Standard | State (Oct 2026) | Relevance |
|---|---|---|---|
| Agent ↔ tools | **MCP 2026-07-28** | Stateless core: no `initialize` and no `Mcp-Session-Id`. `Mcp-Method`/`Mcp-Name` routing headers. Tasks and Apps are official extensions. **Sampling, Roots and Logging deprecated.** Governed by AAIF/LF. | agnostic M7, and agnosai's `/mcp`. agnosai currently implements the older `initialize`-based handshake. |
| Agent ↔ agent | **A2A v1.0.x** | Signed Agent Cards. JSON-RPC, gRPC and HTTP+SSE transports. Multi-tenant. IBM's ACP merged into it. | agnosai's callback POST is unsent. agnostic M7. |
| Agent ↔ editor | **ACP** (Zed/JetBrains) | JSON-RPC over stdio, with an agent registry | The strategic option in §3 |
| Agent ↔ UI | **AG-UI 1.0** | Event-stream protocol with HITL and shared state | A possible shape for agnostic's event schema |
| Procedures | **SKILL.md / AGENTS.md** | Cross-vendor | H6 |
| Telemetry | **OTel GenAI semconv** | Separate repo, *still "Development"*. `invoke_agent` (CLIENT/INTERNAL), `execute_tool`, `invoke_workflow`, plus MCP conventions. | agnosai's OTLP (ADR 017, B7) |

### 4.3 The evidence on multi-agent

| Source | Finding |
|---|---|
| Anthropic, multi-agent research system (Jun 2025) | Opus lead with Sonnet workers was **+90.2%** over a single agent on research tasks. **80% of variance is explained by token spend.** Multi-agent costs about **15×** chat tokens. Most coding tasks are a poor fit. |
| Google/DeepMind/MIT, *Scaling Agent Systems* (Dec 2025, 180 configs) | Centralized coordination: **+80.9%** on parallelizable tasks, but **−39 to −70%** on sequential reasoning. Error amplification is **17.2×** for independent agents versus **4.4×** centralized. Gains shrink once the single-agent baseline exceeds ~45%. |
| Tran & Kiela (Apr 2026) | **With equal thinking-token budgets, a single agent matches or beats multi-agent** on multi-hop reasoning. Many reported multi-agent gains come from spending more compute. |
| MAST (NeurIPS 2025) | 14 failure modes in 3 classes: specification, inter-agent misalignment, verification. Failures come mostly from **system design**, not model capability. |
| Cognition, *Multi-Agents: What's Actually Working* (Apr 2026) | What works: one writer plus a clean-context **reviewer** (~2 bugs per PR, 58% of them severe), a "smart friend" second model, and manager/child delegation. What fails: **parallel writers** and unstructured networks. |
| Anthropic C compiler (Feb 2026) | 16 agents with Docker, git and lock files, and *no orchestrator agent*. Heavy test infrastructure kept it on track. Parallelism collapsed on monolithic bugs. |

**Taken together:** use multi-agent when the work is breadth-first, read-heavy or parallelizable, there is a coordinator, there is an external verification signal, and the budget is about 10× or more. Otherwise use one writer with extra agents that contribute *intelligence, not actions*.

---

## 5. Lessons from the industry, mapped to us

Ordered by leverage. "A" items belong upstream in agnosai and "B" items in agnostic.

**Note on sequencing for the A items:** agnosai's parity bar is `rust-old/`, and the Rust oracle itself did not wire hierarchical, approvals or budgets. So A2–A5 are *beyond parity* and go on agnosai's roadmap after parity. Each needs its own ADR there.

| # | Item | Why (industry signal) | Current state (verified 2026-10-03) |
|---|---|---|---|
| **A1** | **A tool-calling loop in `execute_task`** (model → tool call → result → model, until done or a budget is hit) | It is the core of every harness and SDK. Without it an "agent" is a single prompt. It also unblocks agnostic M6 (only 2 of the 38 preset tools resolve today) and the tool-registry ownership seam (`handoff.md` §tool registry). | No `tool_call` handling anywhere in `crew_runner.cyr` or `src/llm/`. |
| **A2** | **Wire hierarchical (manager → workers)** | Orchestrator-worker is the pattern that won (Claude subagents, Codex, manager Devins, ADK supervisor, Magentic-One). Centralized coordination cut error amplification from 17.2× to 4.4×. | `orchestrator/hierarchical.cyr` is built and tested. `crew_runner.cyr:1448` falls back to sequential. agnostic refuses `hierarchical` (`request.cyr:108-112`) and would drop that refusal once this ships. |
| **A3** | **Wire the HITL approval gate** and add `awaiting_approval` to the lifecycle (H1/H2) | `interrupt()` and approvals are standard in LangGraph, MAF, ADK, Pydantic AI and the OpenAI SDK. herdr's whole product is built around `blocked`. | `approval.cyr` is built and its routes exist. **No call** from `crew_runner`. |
| **A4** | **Durable execution:** an event-sourced crew log, resumable from the last completed task | It is now a baseline expectation (LangGraph checkpointers, the Temporal integrations, OpenHands event-sourcing, Claude Dynamic Workflows). | `durable_state.cyr` has zero callers. agnostic loses in-flight crews on restart (H4). |
| **A5** | **Enforce budgets and concurrency caps** (tokens and cost per crew/tenant, max concurrent crews, max tasks per crew) | Multi-agent costs ~15× tokens. Claude caps subagents at 20 concurrent and depth 3. | `budget.cyr` and `multi_tenant.cyr` have no callers. B6 says there is no cap on concurrent crews. agnostic removed `max_concurrent_tasks` because nothing enforced it. |
| **A6** | **OTel GenAI semconv alignment.** Span names `invoke_workflow` (crew) → `invoke_agent` (task) → `execute_tool`, with W3C trace context passed in from agnostic. | It is the cross-vendor telemetry standard. Pin a version, since the semconv is still "Development". | OTLP spans at 3 call sites (ADR 017). B7 is open. agnostic has W3C trace ids in sakshi that are not propagated to the engine. |
| **A7** | **Hand downstream tasks compressed context** (a summary or `expected_output`, not the full transcript) | Clean-context workers returning 1–2k-token summaries is how Anthropic, Claude Code and Cognition all keep context manageable. | Memory strategies Full/SlidingWindow/HeadTail exist. A summarizing hand-off does not. |
| **A8** | **Update `/mcp` to the 2026-07-28 spec**, and send the A2A v1.0 callback | Spec currency | `/mcp` uses `initialize` and `protocolVersion` (`mcp.cyr:6,94`). The A2A callback is unsent. |
| **B1** | **Build M7 MCP on the 2026-07-28 spec:** stateless core, with the **Tasks extension mapped onto crews** (submit → task handle → poll) | The fit is direct: no sessions and no held SSE matches ADR 0009's pooled-worker constraint. Avoid **Sampling** (deprecated). | M7 not started (`roadmap.md:280-312`) |
| **B2** | **A first-class "reviewer" task pattern for QA** (a clean-context review or verify task with `output_schema` that depends on the work task) | Cognition's single writer plus reviewer and Claude's adversarial verification are the most robust multi-agent pattern. agnostic is a **QA product**, so this is its core domain. | Expressible today as a DAG. Worth a preset or template plus documentation in M6. |
| **B3** | **Single-agent baseline in the Swarm Command estimator.** Next to each swarm's estimate, show a one-agent run *at an equal token budget*. | Tran & Kiela and Anthropic's 80%-variance-from-tokens finding: users should see whether the swarm actually beats one agent or just spends more. The sim stays first-class; this adds to the sim and changes nothing existing. | The estimator runs 8 seeds headless. No baseline yet. |
| **B4** | **Tag failures with MAST categories** in audit and events (specification / misalignment / verification) | Gives operators a shared vocabulary for *why* crews fail. Cheap once A1–A3 produce richer failure modes. | Not present. Low priority. |
| **B5** | H3, H4, H5, H6 above | — | — |

### Things we are already doing right (keep them)

- **Refusing loudly instead of degrading silently:** 422 per refused field, `engine_mode` disclosure, the tool gate refusing misses, SIM/LIVE labels with `n/a` instead of invented cost. Most of the field does the opposite, and MAST's "specification" failures are exactly this kind of silent fallback.
- **DAG validation before submit.** Graph frameworks won, and agnostic's single-task-model DAG-first stance matches them.
- **Tamper-evident audit and per-task cost metering.** Most frameworks leave these to a SaaS add-on (LangSmith, Logfire).
- **The plugin sandbox model**, which is stronger than herdr's.

---

## 6. Suggested next steps

1. **Cheap and local to agnostic, independent of agnosai:** H3 (`events_lost`), H4 (an `interrupted` row instead of 404, plus a survival table), H5 (`api schema` plus a snapshot test), H6 (SKILL.md).
2. **File in agnosai's roadmap**, each with its own ADR there: A1 tool loop, then A2 hierarchical, then A3 approvals with the H1 lifecycle contract (which absorbs B17), then A4 durability, then A5 budgets and caps. A6–A8 alongside.
3. **When M7 starts:** write an ADR choosing MCP 2026-07-28 (stateless) with Tasks → crews, and A2A v1.0.x.
4. **In the Swarm Command roadmap:** B3, the single-agent baseline.

---

**Adopted into the roadmaps on 2026-10-03.**
- agnostic `roadmap.md`: the "Recorded 2026-10-03" section (0.1.12 carries H3–H6 and B3), plus M6, M7 and M9.
- agnosai `roadmap.md`, Owed work **F**. The A-items map to F like this: A1→F1, A2→F2, A3→F3 (with H1), A4→F4, A5→F5, A6→F6, H7→F7, A8→F8, A7→F9.

## Appendix: key sources

- herdr docs: https://herdr.dev/docs/ (concepts, agents, agent-automation, socket-api, session-state, plugins, integrations, add-herdr-support); https://herdr.dev/compare/; blog posts "coding agents are becoming runtimes" (2026-06-10) and "ten agents, three clients, 95% less CPU" (2026-08-03).
- Anthropic: https://www.anthropic.com/engineering/multi-agent-research-system · https://anthropic.com/engineering/building-c-compiler · https://code.claude.com/docs/en/sub-agents · https://code.claude.com/docs/en/agent-teams
- Cognition: https://cognition.ai/blog/dont-build-multi-agents · https://cognition.com/blog/multi-agents-working
- Google Research: https://research.google/blog/towards-a-science-of-scaling-agent-systems-when-and-why-agent-systems-work/ (arXiv 2512.08296)
- MAST: https://arxiv.org/abs/2503.13657 · Tran & Kiela: https://arxiv.org/abs/2604.02460
- MCP 2026-07-28: https://blog.modelcontextprotocol.io/posts/2026-07-28-release-candidate/
- OTel GenAI: https://github.com/open-telemetry/semantic-conventions-genai
- OpenHands SDK: https://arxiv.org/html/2511.03690v1
- MS Agent Framework durable workflows: https://devblogs.microsoft.com/dotnet/durable-workflows-in-microsoft-agent-framework/
