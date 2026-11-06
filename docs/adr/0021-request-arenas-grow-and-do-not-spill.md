# 0021 — Request arenas grow, and do not spill

**Status**: Accepted
**Date**: 2026-11-05

## Context

Each pool worker has one arena, reset after each request, and a full arena answers 0, which is a
fault several frames later. So the arena needs a policy for running out.

Since M1 it was `ARENA_FULL_SPILL`: the overflow came from the global bump allocator, which never
gives anything back. The reasoning was that `ARENA_FULL_GROW` keeps its chunks across a reset, so each
worker would hold its worst request forever, times the worker count, and that a spill only costs
"the overflow alone".

The 2026-11-05 audit measured what that costs. bayan's builder takes about three times its output in
the arena, so JSON of about 16 KB spills. A sustained, ordinary mix grew 367 MB in 180 s and was
accelerating. `GET /crews` at 6,000 stored crews kept 1.4 MB per call, so one open Crews view cost
gigabytes a day, for a client with READ permission. A 1 MiB `[1,1,…]` at the login route kept 20 MiB
per request, for a client with no credentials, and a server under `ulimit -v 700000` died on the 22nd
request. The cost was never the overflow alone: it was the overflow of every request, for good.

## Decision

Request arenas use `ARENA_FULL_GROW`, and so does the collector's. The stdlib describes this as the
policy's purpose: "a request loop converges on its high-water mark and then allocates nothing at
all".

**A worker's arena, and each chunk it grows by, is at least the body cap plus 4 KiB**
(`agnostic_serve_arena_bytes`). The convergence depends on it. An allocation larger than the chunk
size gets a chunk of its own, linked in front of the next, and a chunk too small for what comes next
is not looked at again. With a 64 KiB chunk, bodies that each grew by 16 B kept a whole chunk per
request: 880 KB each, from 75 to 340 MB in a test of one worker. With a chunk larger than any body,
no such allocation arises, and the same run holds flat.

The login route takes at most 4 KiB, so its parse tree stays small before the rate limit can refuse.

## Consequences

- **Positive** — memory held for requests has a bound, and reads cannot exhaust the process. The rule
  that a request path keeps nothing on the global heap (0.1.15) now holds past 64 KiB.
- **Positive** — mount no longer warns, on every default start, about a body limit larger than the
  arena.
- **Negative** — each worker keeps its largest request for the life of the process. The worst case is
  the parse tree of `AGNOSTIC_MAX_BODY_BYTES` times `AGNOSTIC_WORKERS`: about 20 MiB times 16 at the
  defaults, if every worker meets such a body.
- **Negative** — each worker holds about 1 MiB from the start, 16 MB at the defaults, and an operator
  who raises `AGNOSTIC_MAX_BODY_BYTES` pays for it twice per worker: the read buffer and the arena.
- **Negative** — the chunk size bounds what a *body* can do. A response is not capped: a single
  allocation over the chunk size still gets a chunk of its own, so response sizes that keep rising
  past 1 MiB can keep a chunk each. That takes a tenant's crews growing in step, and each such crew
  costs far more than the chunk. The stdlib's behaviour is filed with cyrius.

## Alternatives considered

- **Raise the arena and keep SPILL.** It moves the spill to larger requests without removing it, and
  a 1 MiB body still spills.
- **A per-request spill budget that answers 413 or 503.** A real bound, but it refuses valid reads
  of large crews, which GROW simply serves.
- **Reclaim spilled blocks at reset.** That needs a change to the allocator, and GROW is already
  what the allocator offers for this.
