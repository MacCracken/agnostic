# 0022 — A finished crew leaves the engine's registry

**Status**: Accepted
**Date**: 2026-11-05

> **Update, 0.3.1.** agnosai 2.2.4 ships both halves of this. `agnosai_orchestrator_forget_crew` replaces
> the reach into the orchestrator's fields, and eviction is oldest-first (its ADR 026). The decision stands:
> eviction is a backstop for a reader that falls behind, so a crew the ledger holds still leaves at once.
> The sentences below on private fields describe 2.2.3.

## Context

agnosai keeps at most 1000 crews in its registry. At that size the next submit removes **every**
finished crew at once (`_agnosai_orch_evict_locked`), whether or not anyone has read it.

agnostic reads a crew's state from that registry, on a poll or from the collector's 200 ms sweep. A
crew that finished and was evicted before either arrived was simply gone: agnostic latched `unknown`,
its results were lost, and the next start called it `interrupted`, "restarted before this crew
finished", though it had completed. 1,300 unpolled crews at 190/s lost 885. At 20/s, 3 of 1,100 were
lost, and clients polling every crew to its end still lost 7 of 4,000.

## Decision

**Seeing that a crew finished is apart from writing it down.** A refresh has two halves:

- `agnostic_crew_collect_a` reads the engine, latches, and retires the crew. It is memory.
- `agnostic_ledger_flush_a` writes what the latch left owing, about 11.5 ms of fsync.

**A finished crew leaves the engine's registry as soon as the ledger holds all it will ever need.**
That is when the crew is terminal and its event subscription has closed, which the engine does only
after it has recorded the final state. The one thread that wins the claim looks at the registry once
more before it deletes, because a cancelled crew reads CANCELLED before it ends and an earlier look
can hold no results. The registry then holds only the crews still running or not yet read, so it does
not reach 1000 and the eviction does not fire.

**The collector's sweep runs both halves in turn, and its writes are time-boxed** to 150 ms, so a
backlog never stops it reading the engine. A poll writes its own crew's outcome. What is owed keeps an
entry live and past ledger eviction, and a graceful stop writes all of it.

agnosai 2.2.3 has no call for this, so `_agnostic_crew_retire_a` takes the engine's mutex and deletes
from its map directly, through the orchestrator's field offsets.

## Consequences

- **Positive** — a crew's outcome is no longer lost to eviction at any rate the server can sustain:
  6,000 crews at 219/s all completed, where the same load lost most of them before.
- **Negative** — agnostic depends on two private fields of agnosai's orchestrator. A rename is a
  build error, not a silent change, and the roadmap carries the upstream request.
- **Negative** — under sustained load the writes fall behind the crews, by about 200 against 86 a
  second here. A crash then loses the backlog's outcomes: those crews read `interrupted`, which is
  true of the run and not of the crew. The in-flight row was already what makes that honest. A
  graceful stop drains it: 1,500 crews took 10.6 s.
- **Neutral** — `UNKNOWN` now means the crew is gone for good, so it stopped being swept. Nothing is
  stored for it, so it stays in the ledger: evicted, it would read 404.

## Alternatives considered

- **Retire after the durable write.** The first version of this decision. The collector managed about
  50 crews a second, so at 200/s the eviction fired anyway, and a test that slept 1 ms per crew did
  not show it.
- **A transaction around the writes.** It costs 31.5 ms against 11.5 ms, on every crew.
- **Sweep before a submit near the cap.** It uses only public calls, but a crew that finishes between
  the sweep and the eviction is still lost.
- **Hold the engine's state pointer in the ledger.** The engine replaces the object when a crew
  finishes, so the pointer would hold no results.
- **Wait for agnosai to evict oldest first.** That is the right fix upstream, and it is filed. Crews
  were being lost until then.
