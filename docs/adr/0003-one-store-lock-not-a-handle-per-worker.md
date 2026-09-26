# 0003 — One store lock, not a patra handle per worker

**Status**: Accepted
**Date**: 2026-09-26

## Context

The server runs up to `AGNOSTIC_WORKERS` (default 16) sandhi pool workers, and every one of them
reaches the database through **one** patra handle, opened once at mount (`src/engine/store.cyr`).
The audit trail has a second handle of its own, plus a hash chain, likewise shared.

patra does not make a shared handle safe. Its read path has taken no lock since 1.12.0, and its
1.14.0 README correction says why that matters: *"Concurrent SELECTs on one handle race the
per-handle header buffer and the shared file offset — wrong rows, phantom values, hangs."* Writers
take patra's process-wide mutex, readers do not, so a read also races a write — and the `flock` patra
takes per statement does not help, because threads sharing one handle share one open file
description, which `flock` does not arbitrate between.

Until 0.1.4 nothing in agnostic serialized either handle. The per-request authentication lookup,
crew-outcome writes and definition reads all ran concurrently on the store handle; audit appends ran
concurrently on the chain. Measured on the 0.1.3 code (`tests/store_concurrency.tcyr`): eight
threads doing nothing but `agnostic_users_find_a` **killed the process with SIGBUS, every run**,
while a single-threaded control of the same suite passed. Unlocked concurrent audit appends fork the
chain, which the next verification reports as tampering.

patra's own guidance is the obvious candidate fix — *"Migration for read parallelism: open one
handle per worker thread instead of sharing one."* That makes this a real choice.

## Decision

**Keep one handle per database, and serialize every use of it under a re-entrant lock** —
`agnostic_store_lock()` for the store, a second lock for the audit trail. Each store operation runs
as one critical section.

It is enforced, not documented:

- `agnostic_store_db()` returns the handle only to a thread that holds the store lock; any other
  caller gets 0 ("no persistence") and an ERROR line. A forgotten lock fails deterministically in the
  suites instead of racing under load.
- `scripts/check-store-lock.py` (run by `check-clean.sh`) checks the same rule statically, so a path
  no suite exercises cannot carry it either.

The lock is **re-entrant** (`src/engine/rlock.cyr`, owner = kernel tid) because store operations
compose — `revoke` resolves before it deletes, `create` checks before it inserts — and each of those
must be one critical section while the inner operation stays callable on its own.

**Out of scope, deliberately:** anything slow. Argon2 (~244 ms by design) runs outside the store
lock in both `agnostic_users_create_a` and `agnostic_users_verify_a`; creation re-checks the address
under the lock immediately before its insert, which is what keeps it unique.

## Consequences

- **Positive** — the crash is gone, and so is a class of logical races the shared lock closes for
  free: check-then-insert is atomic for users, tenants, definitions and crew outcomes; a definition
  `get` can no longer re-cache a record a concurrent `replace` superseded or a `remove` deleted; audit
  appends link, persist and count as one step, so the chain cannot fork. The definition cache's own
  mutex is gone — one lock where there were two with an ordering question between them.
- **Negative** — store access is **serial**. An uncontended enter/exit pair costs **~0.7 µs**
  (two `gettid` syscalls; the raw futex pair is 47 ns), against **~48 µs** for a full user lookup and
  **~108 µs** for a crew-outcome write — about 2 % of a lookup. The real cost is the ceiling: database
  work cannot exceed one operation at a time, on the order of **20,000 lookups a second** here.
- **Neutral** — nothing may be called under the store lock that can block for long or take a lock
  that is itself held while taking this one. The two locks here (store, audit) are never held
  together. Every new store function must follow the wrapper shape — `lock; var r = body(); unlock;
  return r;` — which the gate checks. ⚠ **Not `defer`**: cycc 6.6.6 skips a `defer` when a function
  returns through `return f(...)`, which would leave the lock held forever (filed upstream,
  `cyrius/docs/development/issues/2026-09-26-defer-skipped-on-any-tail-call-return.md`).

## Alternatives considered

- **One patra handle per worker** (patra's recommendation). Rejected *for now*, on four counts.
  (1) It parallelizes only READS: patra writers still serialize on its process mutex, and every
  handle adds `flock` contention on the file. (2) It does nothing for the logical races — two
  workers on two handles can still both see "absent" and both insert; closing that needs explicit
  transactions and retry on conflict, which patra's own docs say it does not make atomic across
  threads. (3) sandhi owns the worker threads, so per-worker handles need lazy opening from a
  thread-local slot, with no hook to close them — a lifecycle this tree does not otherwise need.
  (4) The definition decode cache assumes one writer, and would need rethinking. Revisit when
  measured store-lock contention — not the possibility of it — limits throughput.
- **Lock only each patra call (a leaf lock), not the operation.** Fixes the crash, but leaves every
  check-then-act race above in place. The re-entrant, operation-level lock costs the same and closes
  both.
- **A readers-writer lock.** Does not apply: on a single handle, concurrent READS are the unsafe
  case, so readers must exclude each other too.
- **`defer`-based unlock.** Rejected — see the cycc defect above.
