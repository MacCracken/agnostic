# 0013 — A crew a restart interrupted answers `interrupted`, not 404

**Status**: Accepted
**Date**: 2026-10-03

## Context

Since M4 only terminal crew outcomes have been stored. `agnostic_ledger_latch` persists a crew when it latches COMPLETED, FAILED or CANCELLED (`_agnostic_ledger_persist` → `agnostic_crews_save_row`), and `_agnostic_crews_save_locked` refuses any other status.

The roadmap's M4 note gives the reason. A crew runs on a detached thread that dies with the process. A stored PENDING or RUNNING would therefore come back on the next start as a crew that claims to run and never will, and the ledger's latch could not correct it, because the wrong value would be latched first. The note accepted the price: "a crew interrupted mid-flight 404s after a restart, which is true."

That is true, but a client cannot act on it. A 404 for an id the server itself handed out in a 202 reads exactly like a typo, and that is the confusion the ledger exists to prevent. Swarm Command records such a run as `lost`; the Crews view says there is no such crew. Nobody is told that the work did not happen and should be submitted again. The 2026-10-03 review (herdr) asked for a terminal answer here, and for what survives a restart to be written down.

Two facts limit what that answer can hold:

- **While a crew runs, agnostic holds none of its task results.** The engine keeps them in its runner until the crew ends; meanwhile its registry state carries an empty results vec. A `task_completed` event carries a task id and a status, with no output and no usage (`_agnosai_crew_completed_data`). So there are no finished-task results to keep under ADR 0012's rule, and no cost to report.
- **patra's limits.** It gives a table one index, fsyncs every write, and leaves an index tombstone for every deleted key until VACUUM.

## Decision

**A crew that was accepted and had no stored outcome when the process stopped is, from the next start, in the terminal state `interrupted`. It is stored, answered by `GET /api/v1/crews/{id}`, listed, and audited. Nothing non-terminal is ever read back from disk.**

- **Submit records an obligation, not a status.**
  - Once the engine has accepted the crew and the ledger holds it, `agnostic_crew_submit_owned` calls `agnostic_ledger_mark_inflight`.
  - That writes one row to a new table, `agnostic_crew_inflight`: id, scope, name, `submitted_at`, task count, engine mode and process.
  - The row has no status column. It says only "this crew has no outcome yet".
  - `agnostic_crews_mark_inflight` writes nothing when the crew already has a stored outcome. Because this happens under the store lock, a crew that finishes before its row is written leaves no row.
- **The outcome write discharges it.** `_agnostic_crews_save_row_locked` deletes the crew's in-flight row after writing the outcome and its listing row, in the same critical section. The cancel latch, the collector and a poll therefore all clear it, and no caller has to remember to.
- **Start-up turns what is left into `interrupted`.**
  - `agnostic_serve_mount` calls `agnostic_crews_interrupt_inflight` after the audit chain opens and before the server listens. Nothing — `/ready` included — is answered until it is done.
  - For each in-flight row it writes a terminal outcome through the ordinary write-once path (`agnostic_crews_interrupt_row`). The outcome has status `interrupted`, `results: []`, `task_count: 0`, zero `usage`, and an `error` saying the server restarted before the outcome was recorded. It carries the row's name, scope, engine mode, process, `tasks_submitted` and `submitted_at`, plus `interrupted_at`.
  - It then deletes the row and records `crew.interrupted` (WARNING, `crew_id=…`) in the audit chain.
  - A row whose crew already has an outcome — the process stopped between the two writes — is deleted, and the outcome stands.
- **`interrupted` is terminal and agnostic's own**, like UNKNOWN.
  - `AGNOSTIC_CREW_INTERRUPTED = 6` is the next number, never a renumbering, because `cstatus` is stored on disk.
  - `agnostic_status_is_terminal`, `agnostic_outcome_is_terminal` and `agnostic_crew_status_to_wire` know it.
  - `GET /api/v1/crews` accepts `?status=interrupted` and includes it unfiltered.
  - The ledger never holds it; only the start-up sweep writes it.
- **No `finished_at`, no `started_at`.** The crew did not finish, and when it stopped is not known. A finishing time of "when the server came back" would make every view show the downtime as run time. `interrupted_at` says when it was declared.
- **The views know it.** Swarm Command counts it as terminal; the Crews view has an Interrupted filter.
- **It is not resumable.** Resuming needs agnosai F4, a durable crew log. When agnosai's events carry a finished task's output and usage, an interrupted crew can keep them under ADR 0012's rule without changing this decision.
  *Note, 0.1.15:* [ADR 0019](0019-an-interrupted-crew-keeps-what-its-finished-tasks-answered.md) does, for the output: since agnosai 2.1.5 a `token` event carries it, and the sweep writes what was kept into the outcome's `results`. No event carries usage yet.

**This supersedes the 404 in the M4 roadmap note** ("a crew interrupted mid-flight 404s after a restart"). The note's objection is met by construction rather than guarded against:

- the in-flight table holds no status;
- nothing but the start-up sweep reads it;
- the ledger is never seeded from disk;
- the only status the sweep writes is terminal.

## Consequences

- **Positive**
  - Every crew id the server handed out answers after a restart: completed, failed, cancelled or interrupted. A client knows to resubmit.
  - Swarm Command records `interrupted`, not `lost`. An operator finds the interruption in the audit trail by crew id.
  - `docs/architecture/001-what-survives-a-restart.md` says what survives.
  - Tested in `tests/crewstore.tcyr` (`crewstore/sweep`, `crewstore/sweep-keeps-outcome`), `tests/crews_route.tcyr` (`crews/interrupted-not-404`), `tests/crew_tenancy.tcyr` (`tenancy/interrupted`) and `tests/restart.tcyr` (the real mount).
- **Negative**
  - Two more fsyncs per crew, both under the one store lock (ADR 0003). One is on the submitting worker, whose POST already pays one for its audit entry; the other comes when the outcome is written. Every other store user waits behind them.
  - Start-up pays about four fsyncs per interrupted crew.
  - A new status on the wire: a client with an exhaustive switch must learn it.
  - An interrupted crew reports no usage or cost, though its finished tasks may have spent money; agnostic never saw the metering.
  - A crew that ended in the engine within one collector interval (200 ms) of the crash is `interrupted`, and its results are lost.
  - The sweep assumes one process per database file, as the definition cache already does. A second process started on the same file would mark the first one's running crews interrupted, and write-once would then refuse their real outcomes.
    *Note, 0.1.15:* enforced. Mount claims `<db>.owner` with an exclusive, non-blocking `flock` before it touches the file, and a second process refuses to start ([architecture 001](../architecture/001-what-survives-a-restart.md)).
- **Neutral**
  - The in-flight table has no index. Its live rows are only the crews in flight, so a delete scans a few pages, where an index would keep a tombstone for every crew ever run.
  - Events and the plan stay in memory, so `/events`, `/plan` and cancel answer 404 for an interrupted crew, as for any crew from before a restart.
    *Note, 0.1.15:* cancel answers **409** for any stored crew of the caller's tenant, interrupted ones included, so it agrees with `GET /crews/{id}`'s 200. `/events` and `/plan` still answer 404.
  - A retry with the crew's `Idempotency-Key` after a restart starts a new crew (ADR 0008: keys do not survive one). That is what a client resubmitting lost work wants.

## Alternatives considered

- **Keep the 404 (M4).** Rejected: it is true but not actionable, and it collapses "lost" into "never existed", which the ledger exists to keep apart.
- **Write a PENDING row to `agnostic_crews` at submit and rewrite it at the end.** Rejected, for three reasons:
  - it ends write-once for every crew, not just the one cancelled case ADR 0012 allows;
  - it puts non-terminal documents where `GET /crews/{id}` serves stored bytes verbatim;
  - a crash between the outcome write and the listing write would leave two rows to reconcile.
- **Write the listing row (`agnostic_crew_index`) at submit and update it at the end.** Rejected: that table's one index is `scope`, so each crew's final update would scan every crew ever run.
- **Update the in-flight row when the crew starts.** Rejected: it costs an fsync per crew to record `started_at`, while nearly every crew starts the moment it is accepted, because agnostic has no admission queue. Revisit if agnosai F5 adds one.
- **Mark running crews interrupted at shutdown.** Rejected as the mechanism: a crash, an OOM kill or a power cut runs no shutdown code, and the start-up sweep covers a graceful stop as well.
- **Persist each task's output as `task_completed` arrives.** Not possible today, because the event carries none. Recorded against agnosai F3/F4.
- **Refuse a submit whose in-flight row cannot be written.** Rejected: an outcome that cannot be written is logged, not raised (`_agnostic_ledger_persist`), and the in-flight row follows the same rule. The crew runs; only a restart before it ends loses it, as before 0.1.13.
