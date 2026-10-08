# 0019 — An interrupted crew keeps what its finished tasks answered

**Status**: Accepted
**Date**: 2026-10-07

## Context

[ADR 0013](0013-a-crew-interrupted-by-a-restart-is-interrupted.md) made a crew that a restart cut
short answer `interrupted` instead of 404, with `results: []`. It could keep nothing else: while a
crew runs, agnostic holds none of its task results — the engine hands them over when the crew ends
— and a `task_completed` event carries only a task id and a status. ADR 0013 said what would change
that: "When agnosai's events carry a finished task's output and usage, an interrupted crew can keep
them under ADR 0012's rule without changing this decision."

Half of that has happened. Since agnosai 2.1.5 (its ADR 022) every task the model answers sends one
`token` event in every process, carrying the whole text: `{task_id, token, complete: true}`. No event
carries usage. So a crew interrupted after three of its five tasks answered lost three answers that
had already reached agnostic's event ring, and possibly money already spent on them.

[ADR 0012](0012-a-cancelled-crew-keeps-its-finished-results.md)'s rule is the one to extend: work
that finished is reported, not dropped because the crew as a whole did not.

## Decision

**While a crew is in flight, agnostic keeps each finished task's output on disk, from its `token`
event. The start-up sweep writes them into the interrupted crew's outcome as its results. The
outcome write discards them.**

- **Collected where events already arrive.** `agnostic_ledger_drain_a` copies each event into the
  crew's ring, as before, and also collects the ones that carry a finished task's output
  (`agnostic_ledger_is_final_token`: a `token` event with `complete: true` and string `task_id` and
  `token`). The refresh — what a poll and the collector run — keeps them once the ledger lock is
  released (`_agnostic_crew_keep_finals`), so the ledger and store locks are never held together.
- **Kept in one more table, under the same rules as the in-flight one.** `agnostic_crew_partial
  (crew_id, task_id, output TEXT)`, with no index, for the reason ADR 0013 gives: its live rows
  belong to the crews in flight, and an index would keep a tombstone for every task ever run.
  `agnostic_crews_save_partial` writes a row only for a crew that has an in-flight row and no stored
  outcome, checked under the store lock with the write. So nothing is kept that the sweep cannot
  find, and nothing after the outcome.
- **The outcome write discards them.** `_agnostic_crews_save_row_locked` deletes a crew's kept
  outputs beside its in-flight row, in the same critical section. Every way an outcome is written —
  the latch, the cancel latch, the sweep — clears them, and no caller has to remember to.
- **The sweep makes them results.** `agnostic_crews_interrupt_inflight` reads a crew's kept outputs
  in the order they were written and passes them to the outcome as engine task results, each
  `completed`, with its output and no metadata. The outcome is rendered as any other: `results`
  holds them, `task_count` counts them, `usage` says nothing was metered. ADR 0013's decision is
  unchanged: the status is `interrupted`, nothing non-terminal is read back into the ledger, and the
  crew is not resumable.

## Consequences

- **Positive**
  - Work a model finished before a crash is not lost. A client resubmitting an interrupted crew
    can see which tasks already answered, and the Crews view and Swarm Command settle those tasks as
    completed — both already read an outcome's `results`.
  - Tested in `tests/crewstore.tcyr` (`crewstore/partials`: kept, refused without an in-flight row,
    folded into the interrupted outcome, cleared by an ordinary outcome and refused after it;
    `crewstore/refresh-keeps`: the refresh keeps a complete token from a real event bus and not a
    partial one). Three mutations each fail by name.
- **Negative**
  - One more store write, an fsync under the one store lock (ADR 0003), per task the model answers.
    A crew of 1,000 tasks pays 1,000. They are spread over the crew's run, at the pace answers
    arrive, and each is far cheaper than the inference that produced it.
  - The outputs are on disk twice for a moment: kept, then in the outcome, then the kept copies are
    deleted. patra frees emptied pages, but not their bytes until it reuses them.
  - Still no usage or cost for an interrupted crew: no event carries one. That needs agnosai F3's
    per-task payload or F4's durable crew log.
- **Neutral**
  - A task that answered without the model — placeholder mode, a tool-only task — sends no `token`
    event, so it is still lost in an interruption.
  - A crew submitted before 0.1.15, or whose in-flight row could not be written, keeps nothing,
    exactly as before.

## Alternatives considered

- **Keep the `token` events in the in-flight row.** Rejected: the row would be rewritten on every
  answer, an UPDATE of a growing TEXT column, and two writers (the collector and a poll) would race
  to rewrite it.
- **Persist the event ring itself.** Rejected: it is mostly progress (`task_started`,
  `crew_started`, …) that nothing reads after a restart, and it would make every event an fsync.
- **Wait for agnosai F4's durable crew log.** Not rejected — F4 makes an interrupted crew resumable,
  which is more than this. But F4 is large and unscheduled, and this keeps the answers meanwhile;
  when F4 lands, its log supersedes this table.
