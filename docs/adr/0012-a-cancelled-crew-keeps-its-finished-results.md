# 0012 — A cancelled crew keeps the results its finished tasks produced

**Status**: Accepted
**Date**: 2026-10-02

## Context

Two rules have held since M2 and M4, and both exist because the oracle broke them
(`ORACLE-AUDIT.md` §3.4): **a terminal status is latched once** — `agnostic_ledger_latch` refuses
every later observation — and **a terminal outcome is written to the store once**.

Cancelling a running crew met both rules badly. `POST /crews/{id}/cancel` asks the engine to stop
scheduling — tasks already running finish — and latches CANCELLED at once, with no results, because
the engine has none yet: its registry holds a crew's results only when the crew ends. When the
running tasks finish, the engine records the crew CANCELLED again, now WITH those tasks' results, and
then closes the crew's event channel. The latch refused that observation, and the store had already
written the result-less outcome. The work — and its cost, already spent — was lost; only the
outputs that came as events survived, and only in the event window. Found at 0.1.9.

## Decision

**One exception to each rule, and only for this case: a stored CANCELLED with no results takes the
results of a terminal observation, once — status, reason and finishing time unchanged — and the
stored outcome is rewritten once to carry them.**

- **The latch** (`agnostic_ledger_latch`): when the stored status is CANCELLED, the entry holds no
  results, and the observation is terminal with results, the results are attached and the call
  answers 2 (1 is a status write, 0 a refusal). Afterwards the entry has results, so the exception
  cannot fire again. "No results" is a null **or an empty** vec: while a crew runs, every refresh
  latches the registry's state, whose results vec is empty but not null — a check for null alone
  passed every unit test and never fired against the real engine (found by the live check). No
  other terminal state takes anything, and the observation's status and reason are ignored: the
  crew was cancelled, and that stays the answer.
- **The store** (`agnostic_crews_resave_row`): rewrites the stored document and the listing row's
  tokens and cost for a CANCELLED crew; refuses any other status. If the first write had failed, it
  writes the crew now.
- **The collector already sees it**: an entry stays live while its event channel is open, and the
  engine records the final state before it closes the channel, so the sweep that finds the channel
  closed has already latched the results. No poller is needed.
- **The Crews view follows a cancelled crew** until its `crew_completed` arrives, then reads its
  outcome once more, so the results appear where the cancel was made.

## Consequences

- **Positive** — Work done before a cancel is kept: its outputs, and what it cost, on the crew's
  outcome, in the listing's totals, and across a restart.
- **Negative** — The terminal latch and the write-once store each have an exception now, and a
  reader must know it. Both are narrow — one stored status, one transition, once — and each is tested
  (`tests/ledger.tcyr` `ledger/cancel-results`, `tests/crewstore.tcyr` `crewstore/cancel-results`).
- **Neutral** — A crew cancelled before any task ran ends with an empty result set, as before.

## Alternatives considered

- **Delay the cancel's latch until the engine finishes.** Rejected: the client asked to cancel and
  is owed an answer that says so now; reporting `running` for a crew being cancelled reads as if the
  cancel failed.
- **A new status, e.g. `cancelling`.** Rejected: it is a wire change every client must learn, and it
  says nothing a client cannot already tell from `cancelled` plus an outcome that later gains
  results.
- **Keep the outputs only in the event window.** Rejected: the window is bounded and in memory; the
  outputs and their cost belong on the outcome, which is what is durable.
