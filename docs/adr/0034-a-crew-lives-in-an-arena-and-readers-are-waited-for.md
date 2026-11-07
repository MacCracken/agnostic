# 0034 — A crew lives in an arena, and goes back when no reader can hold it

**Status**: Accepted
**Date**: 2026-11-06

## Context

The global heap has no `free`, so everything a crew allocated stayed for the life of the process. Audit P2
measured about 16 KB per crew at 0.2.2, 11,080 B after 0.3.1 gave the event rings back: 11 GB per million crews,
and only a restart returned it. agnostic filed that with agnosai, and agnosai 2.2.5 answered with
`agnosai_crew_new_in` and `agnosai_orchestrator_release_crew` (its ADR 028). Its note said "agnostic has to
adopt this": a crew built with `agnosai_crew_new` runs on the global heap as it always did.

Adopting it has one hard part. After a release nothing of the crew is valid: spec, id, tasks, state, results,
events. It is scrubbed and reused. And the ledger hands out pointers. `agnostic_ledger_entry` looks a crew up
and lets go of its lock, and the request then reads the entry and everything behind it for as long as it
takes to answer, on a thread nothing is watching. Until now that was safe because nothing was ever freed. A
release under such a reader is a read of another crew's memory: one tenant's output in another's answer.

## Decision

**Everything agnostic allocates for a crew goes in the crew's arena**, from its decoded request to its ledger
entry and the key the ledger finds it by. The arena is taken once a body has passed everything but the
graph check, and given back if the body is then refused.

**A crew leaves in three steps.** Eviction takes it out of the ledger's map, under the ledger lock, so nothing
new can find it. It then waits in limbo. Then `agnosai_orchestrator_release_crew` gives it back, with no lock
held. That is the only place a crew's memory goes.

**What it waits for is one bracket, not a count on each entry.** `agnostic_ledger_read_begin` and `_end` go
around each request and each collector sweep. Every pointer to an entry comes out of the map and goes no further
than the bracket it was found in, so nothing has to be counted at the thirty places that read an entry, and a
route added later cannot forget. Brackets join one of two generations, and limbo has two lists: this is the
two-counter form of RCU.

**A bracket covers the encode and stops before the write.** `bayan_json_v_str_new_a` keeps a pointer, so a
response points into the entry until its bytes exist. A client that stops reading can hold a write for as long
as it likes, which must not hold every finished crew's memory with it.

**Every request takes a bracket**, `/health` too. A route that forgot would read a crew being scrubbed, seen by
nobody. Two lock operations cost less than that, and the benchmarks do not show them.

## Consequences

- **Positive**: on one placeholder task, what a crew keeps on the global heap for life went from 11,080 B to
  **0**, held by `crew-arena/flat` over a thousand crews past the cap. Audit P2 is closed. The two `str_from("")`
  a crew with no target left behind were the last of it.
- **Positive**: resident memory stops growing. Seen from outside, 7,000 crews with 16 readers read 972 B a crew
  between 3,000 and 7,000, which is the audit trail and the store's cache.
- **Negative**: memory held is now the ledger's size times a crew's size, whatever that is, and it does not fall.
  An arena keeps the largest it has grown to. The ledger holds 768 to 1,024 finished crews plus those running, and
  about 512 more can wait in limbo. A write backlog keeps crews in the ledger past its cap, and their arenas with
  them. That is bounded by the backlog, and the same crews were kept for life before.
- **Negative**: a request stuck in its bracket holds back every crew evicted since. `agnostic_ledger_readers`
  shows it, and `agnostic_crew_arenas` shows what it costs.
- **Negative**: nothing may keep a pointer to an entry past its bracket. Nothing does, and no tool checks that.
- **Limit**: what the suites prove is the bookkeeping. The race itself is `load-test.py` step 8, with 16 readers
  aimed at the crews about to go. Removing the limbo crashes the server there. Removing a bracket does not show:
  limbo alone waits about two evictions, some seconds, far longer than a request. So the brackets are held by
  `serve/ledger-bracket` and `crew-arena/sweep`, which see that one is open, and not by the race. The handler closing
  its bracket just before it calls `_agnostic_serve_send` passes both, and the race does not show it either, so that
  one line is held by reading.
- **Not done**: libro's audit entry (about 250 B per record) and sandhi's 480 B per exchange are still on the
  global heap. Both are filed with their owners.

## Alternatives considered

**Copy what a reader needs out of the arena at eviction.** agnosai's ADR 028 turned this down for the same
reason: it pays for what the consumer already has, and it does not end the race, only move it.

**A reference count on each entry.** Thirty call sites, each able to forget, and a listing that pins a thousand
entries at once.

**Time.** Release a crew some seconds after its eviction. It is what limbo amounts to in practice, and it is
wrong in exactly the case that matters: a thread descheduled on a loaded machine.
