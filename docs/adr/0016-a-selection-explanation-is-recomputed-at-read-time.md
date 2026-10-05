# 0016 — A crew's agent selection is explained by recomputing it when asked, within a fixed budget

**Status**: Accepted
**Date**: 2026-10-04

## Context

agnosai picks an agent for every task of a crew, and until agnosai 2.1.5 nothing outside it could
see why. `_agnosai_crew_pick_best_agent` ranks the roster with `agnosai_rank_agents` and keeps the
winner; the five component scores it folded into each total — tool coverage, complexity, GPU,
domain and personality, weighted 0.35 / 0.25 / 0.10 / 0.15 / 0.15 — are discarded. A user whose
task went to the wrong agent had nothing to read.

agnosai 2.1.5 (its roadmap F7) added `agnosai_explain_selection_a(a, agents, task)`: the roster
ranked exactly as the runner ranks it, each entry carrying its five scores beside its total, with
entry 0 the agent the runner assigns. Two renderers turn that into JSON
(`agnosai_selection_to_value_a`, `agnosai_selection_scorer_to_value_a`), so agnostic never
hardcodes a factor name. agnosai serves it on no route; agnostic's plan route
(`GET /api/v1/crews/{id}/plan`, 0.1.9) was named as the place to surface it.

Three facts shape how:

- **The engine records only the winner.** Keeping every breakdown would cost every crew run up to
  agents × tasks entries, asked for or not. agnosai's module header states the property that makes
  recomputing exact: selection is a pure function of the roster and the task, and nothing writes
  either once a crew is built — the runner stamps only task status. It names the three planned
  changes that would end it: hierarchical delegation (F2), learning-driven selection, and a
  stateful personality (bhava).
- **The cost is agents × tasks.** At the request caps (100 agents, 1000 tasks) scoring every pair
  is 100,000 entries of 56 bytes — 5.6 MB — and rendering every candidate is far more.
- **agnostic's request arena spills to the global bump allocator, which never frees**
  (`src/server/serve.cyr`). Whatever a request allocates past its arena is leaked for the life
  of the process, so an unbounded explanation is a memory leak any reader could repeat.

## Decision

**`?explain=selection` on the plan route recomputes each task's ranking from the crew's spec when
asked. Scoring runs in one shared scratch arena reset per task; only the rendered candidates go into
the request's arena, and a fixed budget bounds how many.**

- **The wire.** `GET /api/v1/crews/{id}/plan?explain=selection[&task=N]`.
  - Each task — or only task `N`, an index into `tasks` — gains `selection`: agnosai's
    `{winner, candidate_count, candidates: [{index, agent_key, total, scores}]}`, best first.
    `candidates[0]` is the agent the task ran with.
  - The answer gains `scorer` (`{weights, unmeasured}`) and `candidate_limit`.
  - Floats are agnosai's raw f64s, so Σ weight × score in the listed order reproduces `total`
    exactly.
  - Without `explain` the answer is byte-for-byte what 0.1.13 sent.
- **Refusals, all 422, decided before the crew is looked up** where they can be: `explain` other
  than `selection` (including empty); `task` that is not a non-negative integer; `task` without
  `explain`, because it would change nothing; and, once the crew is found, `task` past its last
  task. A crew of another tenant is 404 with or without `explain` (ADR 0008).
- **The budget.** `AGNOSTIC_EXPLAIN_MAX_CANDIDATES` = 256 candidates per answer, shared equally
  between the explained tasks and never fewer than one each — the winner
  (`agnostic_crew_explain_limit`). It is at least the largest roster, so `task=N` always lists
  every agent. `candidate_count` always says how many agents were scored, so a shortened list is
  visible rather than silent.
- **The scratch.** `agnostic_crew_explain_task_a` scores one task in a 32 KiB arena built at mount
  (about 9 KiB is needed at the caps), under its own mutex, and copies the candidates out into the
  request's arena before releasing it. Explaining therefore allocates nothing on the global bump
  beyond the answer itself (`crews/plan-explain` measures fifty explanations at zero).
- **Placement.** The engine half is in `src/engine/crew.cyr`, the agnosai bridge; the route only
  reads the parameters and assembles the answer. The schema declares both query parameters and both
  keys (ADR 0015).

## Consequences

- **Positive**
  - A user can see why a task got its agent, and which factor decided it. The first thing it shows
    is that without per-task hints the selection is degenerate: complexity alone separates agents,
    and the first agent with medium or unset complexity wins every task. 0.1.14 adds those hints to
    the task request (ADR 0017).
  - Nothing is recorded per crew, so a crew nobody asks about costs nothing, and the explanation is
    the engine's own arithmetic, not a copy agnostic could let drift.
  - The cost is bounded: at most 256 rendered candidates and one 32 KiB scratch, whatever the crew.
- **Negative**
  - **The explanation is exact only while selection stays pure.** When agnosai ships any of the
    three changes its header names, the runner must record the selection and this route must read
    the record. The ADR to supersede this one is part of that re-pin.
  - Explanations are serialised by one mutex. Each holds it for one task's scoring and copy —
    about 0.13 ms for 100 agents by agnosai's benches — so a 1000-task crew holds it a thousand
    times, briefly, and a second explainer waits between them. No other route takes it.
  - A large crew lists fewer candidates per task than it has agents unless the caller asks one task
    at a time.
  - The answer can still exceed the default 64 KiB request arena on a large crew — as the plain plan
    of such a crew already does — and the overflow spills. The budget bounds it; it does not remove
    it. That is the broader per-request allocation item on the roadmap.
- **Neutral**
  - The explanation is read from the ledger's spec, so like the plan it answers 404 for a crew from
    before a restart.
  - `personality` is listed in `unmeasured` and scores the neutral 0.5 for every agent until agnosai
    ports bhava; agnostic renders whatever factor names agnosai sends.

## Alternatives considered

- **Record every task's ranking when the crew runs.** Rejected: agents × tasks entries per crew on
  memory that is never freed, paid by every crew whether or not anyone asks, and a second source of
  truth for arithmetic the engine already owns.
- **Score in the request's arena.** Rejected: at the caps that is 5.6 MB per request spilled to the
  global bump and never reclaimed — a leak any reader could repeat.
- **Refuse `explain` for crews past a size.** Rejected: it would remove the feature exactly where a
  wrong assignment is hardest to spot by eye. An equal share of a fixed budget, plus `task=N` for the
  full roster of one task, keeps every crew explainable.
- **A `limit` query parameter for the candidate count.** Not taken: the budget makes the answer's
  size the server's decision, as the listing routes' caps do, and `task=N` already gives the whole
  roster where it matters. A parameter can be added without breaking anyone.
- **A per-thread scratch instead of one shared under a mutex.** Not taken: it needs a thread-local
  slot every worker initialises, for a route that is rarely called; the mutex is held for well under
  a millisecond.
