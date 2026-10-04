# 001 — What survives a restart

**Since**: 0.1.13 · **Decided in**: [ADR 0013](../adr/0013-a-crew-interrupted-by-a-restart-is-interrupted.md)

A restart is a graceful stop (SIGTERM, SIGINT) or a crash (`kill -9`, an OOM kill, a power cut).
agnostic runs no shutdown code that saves anything, so the two are the same here: what is on disk
when the process stops is what the next one starts with.

The durable state is one patra database (`AGNOSTIC_DB_PATH`) and the audit chain, which is its own
file (`AGNOSTIC_AUDIT_PATH`). Everything else is in memory and is gone.

## The table

| State | Where it lives | After a restart |
|---|---|---|
| Agent definitions, users, API keys, tenants, settings and plugin switches, plugin documents | patra | Survive. |
| JWT signing secret | Memory, random at mount (`agnostic_serve_mount`) | Gone. Every token must be issued again, while API keys keep working. |
| Login rate buckets | Memory (`src/auth/ratelimit.cyr`) | Gone. Every bucket starts empty. |
| Audit chain | Its own patra file, verified at open | Survives. The next entry links to the last stored one (since 0.1.13; see below). The 1,024-entry read ring is re-seeded from the file ([ADR 0011](../adr/0011-audit-entries-are-read-from-a-bounded-copy.md)). |
| Crew that was completed, failed or cancelled | `agnostic_crews` (the outcome) and `agnostic_crew_index` (its listing row) | Survives. `GET /crews/{id}` serves the stored document verbatim, and the crew is listed. |
| Crew that was pending, running or `unknown` at the stop | `agnostic_crew_inflight`, a row with no status | Becomes **`interrupted`** at the next mount, before the server listens. It keeps its name, scope, engine mode, process, `tasks_submitted` and `submitted_at`. It loses its results, usage, cost, `started_at`, events and plan. |
| Crew that ended in the engine but had not been latched yet (the collector's 200 ms window) | `agnostic_crew_inflight` | **`interrupted`**. Its results are lost. |
| Cancelled crew whose running tasks had not reported yet | `agnostic_crews` (cancelled, written when the cancel latched) | Stays **cancelled**. The results those tasks would have brought are lost ([ADR 0012](../adr/0012-a-cancelled-crew-keeps-its-finished-results.md)). |
| Crew whose outcome write failed (disk full, I/O error) | `agnostic_crew_inflight`, still there | **`interrupted`**. |
| Crew whose in-flight write failed at submit | Nowhere | **404**, as every interrupted crew answered before 0.1.13. Logged at ERROR when it happened. |
| Event ring, plan, ledger timings | Memory (the ledger) | Gone. `/events`, `/plan` and cancel answer 404 for any crew from before the restart, while `GET /crews/{id}` answers from disk. |
| `Idempotency-Key`s | Memory (the ledger) | Gone. A retry with the same key starts a new crew ([ADR 0008](../adr/0008-crews-belong-to-the-submitting-tenant.md)). |
| Engine registry, and work the engine was doing | Memory (agnosai) | Gone, and not resumed. Resuming needs agnosai F4, a durable crew log. |

An interrupted crew reports no usage and no cost, even when some of its tasks finished and spent
money. agnostic never received that metering, because a `task_completed` event carries no output and
no usage. An `interrupted` document has no `finished_at` and no `started_at`. It has
`interrupted_at`, the time the next mount declared it.

## A crew named over 255 bytes (fixed in 0.1.13)

Found while writing this (2026-10-03), and older than 0.1.13. Until the fix, such a crew was never
durable. `agnostic_crews.cname` is a patra `STR` (255 bytes), and patra refuses a longer value
rather than cut it, while a request accepts names of up to 10,000 characters. So the crew's outcome
was not written and, with the in-flight table, neither was its `interrupted` outcome: its in-flight
row stayed and was retried, with an ERROR line, at every start, and it answered 404 after a
restart. The column is written but never read, so the store now writes at most the name's first 255
bytes there, cut on a character (`_agnostic_crews_save_locked`; `tests/crewstore.tcyr`,
`crewstore/long-name` and `crewstore/long-name-sweep`). The document and the listing keep the whole
name, so such a crew now follows the rows above like any other.

## The audit chain across a restart (fixed in 0.1.13)

Until 0.1.13 the chain did not link across a restart. `agnostic_audit_open` started a streaming
chain whose head was empty, and did not seed it from the last stored entry. So the first entry each
process appended recorded an empty predecessor, and the **next** start reported the chain altered
(`intact: false`). Any audited action after a restart triggered it, and the `crew.interrupted`
entries the sweep writes at mount would have triggered it at every start that found one. The open
now seeds the head from the last entry it loads (`_agnostic_audit_seed_head_locked`;
`tests/audit.tcyr`, `audit/durable-append`).

⚠ **A trail written before 0.1.13 keeps its breaks.** Nothing rewrites the file, because it is the
evidence. It holds an entry with an empty `prev_hash` after each restart that recorded something,
so it still answers `intact: false`. `bad_index` names the first such entry; before 0.1.13 it said 0
for every break. Verification stops at that break, so the verdict covers nothing after it, including
the entries the fixed binary adds. To start a trail that verifies, stop the server and move the
audit file aside; keep it. The CHANGELOG (0.1.13, Fixed) says what the log and the Audit view show
for such a trail.

## ⚠ One agnostic process per database file

The start-up sweep treats every in-flight row as a crew that a **dead** process left behind. A
second agnostic started on the same `AGNOSTIC_DB_PATH` (for example, a rolling update on a shared
volume) would sweep the first process's **live** crews to `interrupted`. Write-once would then refuse
their real outcomes, and the first process's ledger would disagree with the disk.

The definition cache already assumes one writer (`src/engine/definitions.cyr`). Nothing enforces this
yet; a guard is a separate roadmap item.

## Downgrading

A 0.1.12 binary opened on a database that 0.1.13 has written:

- ignores `agnostic_crew_inflight`, so crews in flight at the stop answer 404 again;
- hides `cstatus` 6 rows from the listing, because its bound in `_agnostic_crews_row_wanted` stops at
  `unknown`;
- still answers `GET /crews/{id}` for an interrupted crew, from the stored document.

When 0.1.13 or later starts again, its sweep finishes any rows left behind.
