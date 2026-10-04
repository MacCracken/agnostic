# 0014 — The swarm estimator's one-agent baseline is its own model, at the swarm's token spend

**Status**: Accepted
**Date**: 2026-10-03

## Context

Swarm Command's estimator (`estimateSpec`, `src/webgui/plugins/swarm/index.html`) prices a swarm by
running its simulator headless on eight seeds. Two findings make a swarm's price hard to read on its
own:

- Tran & Kiela (2026): with **equal thinking-token budgets**, a single agent matches or beats a
  multi-agent system on multi-hop reasoning.
- Anthropic (2025): token spend explains about 80% of the variance in multi-agent results.

A swarm should therefore be shown beside one agent given the same spend (roadmap B3, from the
2026-10-03 landscape review). The simulator is first-class and stays as it is, so the baseline must
be additive: no existing estimate may change.

What the simulator models limits what a baseline can mean:

- Tokens accrue only while an agent works, coordinates or orchestrates, and on a successful tool
  call (`Sim.tickAgent`, `Sim.toolReturn`). They track the amount of work, not the number of agents.
- On the four templates, measured at 0.1.13 (p50 over the estimator's eight seeds), orchestration
  plus lead coordination is 7–13% of a swarm's tokens: custom 13%, refactor 8%, research 7%,
  incident 11%.
- The spec's `budget` is in dollars, and the simulator never stops on it.
- There is no model of answer quality, and none of the context each new agent reads in. That
  context is a large part of what a real multi-agent system spends over one agent. Anthropic
  (2025) measured a multi-agent system at about 15× the tokens of a chat (the figure the
  2026-10-03 landscape review quotes) and a single agent at about 4×: roughly 3–4× one agent.

## Decision

**The baseline is a separate, seeded, one-agent model, `soloRun`. On each seed it works the swarm's
own plan one task at a time, and is capped at the tokens the swarm spent on that seed.**

- **Same plan.** The plan is built exactly as `Sim.start` builds it: `sc.build` on
  `RNG(seed ^ hashStr(key))`, as its first draw. So the tasks and fan-out counts are the swarm's on
  that seed. Fan-out part sizes and rework are drawn from the same distributions.
- **Same agent per task.** Each task runs with its role's model (the local one in Local), rate,
  tools and region, so per-token prices and region speeds are identical. Only the topology differs.
- **Same failure model.** Every number it restates from the Sim — 34, in 20 entries, from
  `Sim.work`, `Sim.travelMs`, `Sim.latency`, `Sim.tickAgent`, `Sim.callTool`, `Sim.toolReturn`,
  `Sim.hurt`, `Sim.spawnAgent`, `Sim.scheduleRetry`, `Sim.workCap` and `Sim.requestRework` — is
  in one `SOLO` block, each entry naming its method. Retries count per task. A fan-out lead does
  half its own work, then its parts, then the rest, as `Sim.workCap` and `Sim.split` have it. A
  lead that fails before its split never makes its parts, as in the Sim, which creates them at the
  split: one task failed. Review rework adds a fix, then the last tenth of the review, as in
  `Sim.requestRework`. A failed task does not hold up its dependents.
- **No coordination.** No orchestrator, no coordinating leads, nothing in parallel.
- **Equal tokens, paired by seed.** Run *i* of the baseline gets the tokens of run *i* of the swarm.
  It stops where they run out: a work step, or a tool result larger than what is left, is cut at the
  budget, for its share of the work. So a run that ran out spent its whole budget. What is left
  counts as unreached. Ratios are taken per seed, then the p50.
- **Stored with the estimate** as `estimate.solo` (`normalizeEstimate` reads it back, clamped). An
  estimate saved before it reads `solo: null`, and the views say to estimate again. No spec version
  change: the field is optional and recomputable, and `fitSpec` already drops the estimate, after
  old simulations and before any live run record, when a swarm outgrows the server's limit.
- **Shown as SIM**, on the library card and in the editor's **ONE AGENT, SAME TOKENS** box, with its
  assumption and its limits stated: it models time, tokens and cost — not answer quality, and not
  per-agent context.
- `Sim` is not changed. Every estimate's swarm figures are the same simulations on the same seeds.

## Consequences

- **Positive**
  - Each estimate shows what the swarm buys over one agent at the same spend. On the templates, at
    p50 over eight seeds, one agent spends 88–98% of the swarm's tokens and 73–93% of its cost, and
    takes 2.5–8.9× its time:

    | template | tokens vs the swarm | cost | time | ran out of tokens |
    |---|---|---|---|---|
    | custom | 88% | $0.96 vs $1.33 | 2.5× | 1 of 8 |
    | refactor | 95% | $5.28 vs $5.70 | 8.9× | 2 of 8 |
    | research | 98% | $4.34 vs $5.22 | 7.6× | 4 of 8 |
    | incident | 92% | $3.90 vs $4.83 | 6.3× | 2 of 8 |

    In this simulator the swarm buys wall-clock time, at a modest premium. A test pins each
    template's eight-run baseline bit for bit and checks this table's rows against it.
  - Existing estimates cannot move. `tests/webgui/swarm.test.mjs` recomputes an estimate's swarm
    figures from the Sim alone, and pins every template's estimate at the estimator's eight runs
    to the numbers Swarm Command 0.4 reported.
  - An estimate saved before this reads unchanged; it shows no baseline until estimated again.
  - The baseline is cheap beside the swarm's headless run: under 1 ms per seed for the templates
    at 1×, and up to about 3.5 ms at 3×, in Node. It is synchronous, and a 200,000-step guard bounds
    a huge spec; a run cut off by it counts as `stalled`.
- **Negative**
  - `soloRun` restates 34 numbers of `Sim`, in `SOLO`, and the shape of its agent's step
    machine. A change to how a Sim agent works must change both. A test reads each Sim method's
    source and fails, naming the `SOLO` entry, when one of those numbers changes there; no test
    catches a change to the step machine's shape.
  - It does not reproduce the swarm's exact run. Fan-out part sizes and rework are drawn again, and
    running out of tokens is partly that noise: research hits the cap in 4 of 8 runs at a 98% p50,
    leaving about half a task per run. A run that ran out has time and cost for only the work it
    did, so the card and the editor show the tasks left per run beside the count.
  - Smaller simplifications, each stated in `soloRun`'s comment: a fan-out part runs in its
    parent's region, where the Sim may spread parts to other clouds; a tool is its kind's in the
    task's region, else the nearest, without the Sim's 12% wander; a crash drawn past the end of a
    work step is dropped, where the Sim carries it into the agent's next phase; health resets per
    task — one context per task.
- **Neutral**
  - Because the simulator charges no context per new agent, the swarm's token overhead here is a
    floor: orchestration and coordination are 7–13% of its tokens, where Anthropic's measurements
    put a real multi-agent system at roughly 3–4× one agent's tokens. The editor's note says so. A
    per-agent context cost in the simulator — tokens each new agent reads in, default 0 so no
    estimate changes — is recorded on the roadmap as a follow-up. It is a change to the Sim's
    model, so it is not part of this decision.

## Alternatives considered

- **`Sim` with `maxActive = 1`.** Rejected: it is a swarm with a cap of one, not one agent. It keeps
  the orchestrator's tokens for the whole run, the coordinating leads, a fresh agent per sub-task
  with its spawn and travel, and the cap-stall rule.
- **Subtracting the orchestrator's and the leads' tokens from the swarm's own run.** Rejected:
  - the budget becomes a tautology — the result is always under the swarm's tokens and can never
    run out;
  - it would need a per-phase ledger inside `Sim`, which means changing the simulator.
- **Equal dollars instead of equal tokens.** Rejected: the evidence is stated in tokens, and dollars
  would mix model prices into a comparison of topologies. Cost is reported as an outcome instead.
- **One model for the single agent** (for example the orchestrator's). Rejected: it changes the
  per-token price and rate, so the comparison would measure the choice of model, not the number of
  agents. That is a separate question.
- **The p50 of the swarm's tokens as one budget for every run.** Rejected: pairing by seed gives a
  run that spent more a larger budget, which is the fair comparison.
- **Sharing the restated numbers with `Sim`.** Deferred: hoisting them out of `Sim` is a refactor
  of the simulator. The estimate test that pins the swarm's figures would prove such a refactor
  changes nothing, so it can be done later, deliberately.
