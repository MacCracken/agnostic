# 0009 — Crew progress is collected by the server and read by cursor, not streamed

**Status**: Accepted
**Date**: 2026-10-02

> **Note (2026-10-04, 0.1.14 — agnosai 2.1.5, its ADR 022).** The engine's registry now stores
> RUNNING when it hands a crew to its runner, so the last bullet of the context below is history:
> `running` appears without help. The ledger still latches RUNNING on a collected `crew_started`,
> and now also records the start (`started_at`) the first time the registry says RUNNING —
> which can come before the event is collected (`agnostic_ledger_note_started`). Because a
> recorded start reads an engine PENDING as RUNNING, the registry's new RUNNING → PENDING edge
> (its error arm) never reaches agnostic's wire. That arm is unreachable through agnostic's front
> door since agnosai 2.1.6; in 2.1.5 a DAG with a failed branch beside a successful one reached it
> and read `running` here forever, which 0.1.14's review found and 2.1.6 fixed upstream. The
> same release makes the events say what happened: a parallel or DAG task is announced when its
> batch starts and completed as it is joined, every task the model answers sends a `token`
> event, and a timed-out crew's `crew_completed` says `failed`.

## Context

agnostic subscribes to each crew's engine events when it submits the crew, and keeps a bounded
window of them in the ledger. Until 0.1.9 the window moved only when a client asked: every crew
route drained the bus and read the engine's state on a GET, and nothing else did. That had five
consequences, all found while making Swarm Command's live view real:

- **Events were lost for crews nobody watched.** The engine's per-subscriber queue holds 256 events
  and drops the oldest beyond that.
- **Outcomes were not durable without a poller.** A terminal outcome is persisted when the ledger
  latches it, and the ledger latched only on a GET: a crew that finished while no one asked was
  lost to a restart.
- **The window leaked.** Past 256 events, every new event copied the other 255 into a fresh vec,
  and nothing is ever freed.
- **No event had a number or a time.** A reader re-read the whole window on every poll and matched
  it against the last one by JSON signature to find what was new — fragile under repeated events
  and blind to how much it had missed. Replays had no real timing.
- **`running` never appeared.** The engine's registry goes from PENDING straight to a terminal
  state.

The natural answer — a stream (SSE) — does not fit this server today: sandhi's pooled server
dedicates a worker to a connection, so each open stream would hold one of 16 workers for a crew's
whole life, and a handful of watchers would starve every other request, `/health` included.
agnosai's own SSE route accepts exactly that cost (its ADR 014); agnostic does not.

## Decision

**A collector thread keeps every live crew's ledger entry current, and readers read it with a
cursor.**

- **The collector** (`src/engine/collector.cyr`), started after the signal mask, sweeps every
  200 ms: for each crew not yet terminal (or whose channel is still open) it does what a poll does
  — drains the bus into the window, reads the engine, latches, persists a terminal outcome. Each
  sweep runs in its own arena, rewound before the next, and walks the ledger without the global
  allocator; a sweep takes each lock it needs in turn, never two at once.
- **The window is a ring** allocated once per crew, and **every event is numbered** (`seq`, from 1)
  and **timed** (`at_ms`, when agnostic collected it, since the crew was accepted).
  `GET /crews/{id}/events?after=N` answers the events numbered above N; `next` is the cursor to send
  back; `missed` says how many above N the ring had already overwritten; `lost_events` how many the
  bus dropped before they were numbered. Without `after`, the whole window, as before.
- **RUNNING is latched** once `crew_started` has been collected and the engine still says PENDING.
- **Results carry what the engine metered** — tokens, the gateway's cost, model, duration — under
  agnostic's own key names, and the crew carries their totals (`usage`), so a watcher shows real
  numbers instead of estimating them.

## Consequences

- **Positive** — Unwatched crews keep their progress (up to the ring) and their outcome survives a
  restart without anyone polling. A reader polls cheaply (~0.1 µs to copy one new event under the
  lock; ~6 µs for a whole window) and sees each event once, knows exactly what it missed, and can
  replay a crew at its real pace. The per-event leak is gone (`tests/ledger.tcyr` asserts a drain
  allocates nothing). No worker is ever held open.
- **Negative** — One more thread in the server. Latency is the poll interval (Swarm Command polls
  every second, slower when hidden), not push. `at_ms` is when agnostic collected an event, at the
  collector's 200 ms resolution, not when the engine published it — the engine's events carry no
  time. The ring keeps 256 events; a long crew's earliest are still overwritten, now counted.
- **Neutral** — Streaming remains M7's: when a transport exists that does not hold a pooled worker
  per watcher (a dedicated streaming thread, or sandhi reporting a closed client from
  `send_chunk`), the cursor is what it would stream from.

## Alternatives considered

- **SSE from a pooled handler.** Rejected: one worker per watcher for a crew's lifetime is a
  denial-of-service lever, and sandhi's `send_chunk` discards write errors, so a departed client is
  not noticed until the crew ends.
- **Long-polling (`?wait=`).** Deferred: it bounds the hold, but still occupies a worker per watcher
  almost continuously, and it needs a timed wait the stdlib does not offer; cursor polling at 1 Hz is
  cheap enough that the latency it would save is not yet worth the pool pressure.
- **Drain on every request of any crew.** Rejected: it ties one crew's durability to another's
  traffic, and still leaves an idle server collecting nothing.
- **A subscription per request.** Rejected at M2 and still wrong: it grows the sender's subscriber
  list without bound and leaks a channel per call.
