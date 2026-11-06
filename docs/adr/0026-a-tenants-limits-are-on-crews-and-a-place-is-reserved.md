# 0026 — A tenant's limits are on crews, and a place is reserved before the crew is built

**Status**: Accepted
**Date**: 2026-11-06

## Context

`src/auth/ratelimit.cyr` limits login and nothing else (G11), so one tenant could take every worker. The
former code limited task submission per tenant per minute, and stored quotas for sessions, agents and
storage that nothing enforced.

## Decision

**Two limits, both on crews**, because a crew is what spends: model tokens, a worker, memory for life.

- **`rate_limit`:** crews a tenant may submit in a minute, from a full bucket.
- **`max_crews`:** crews of a tenant that may be unfinished at once. Crews that run for an hour are few a
  minute and still hold every worker.

**Both come from the tenant's row, then from `AGNOSTIC_TENANT_RATE_LIMIT` and
`AGNOSTIC_TENANT_MAX_CREWS`.** 0 on a row means the server's default, and 0 there means no limit, so a
deployment that sets nothing behaves as it did. A super administrator sets them, with
`PUT /api/v1/tenants/{key}`. An administrator cannot raise their own.

**A place is reserved, not counted.** Counting a tenant's crews and then submitting is a race: 16 workers
each read 9 of 10 and each submit. So admission takes a place under a lock, and the ledger gives it back
at the one point a crew becomes terminal (`agnostic_ledger_latch_unwritten`).

**Admission comes before the crew is built.** Building one keeps parts of it on the global heap, so a
refusal after that step would leak, and a tenant at its limit could spend memory faster than one under
it. A body that then fails gets its place and its token back, so a typo does not cost the minute.

**A replay is not a crew.** A keyed retry that answers an existing crew admits nothing.

## Consequences

- **Positive** — one tenant cannot take the workers, and a refusal costs nothing lasting.
- **Negative** — limits live in memory, so a restart fills every bucket. Its crews are interrupted, so
  the place count starts right at 0.
- **Negative** — a full table of 256 tenants each with crews running admits a further tenant uncounted. A
  limiter must not be able to refuse everyone by failing.
- **Neutral** — a tenant's token and cost budgets are agnosai's half (F5), where a call's cost is known.

## Alternatives considered

- **A limit on every request.** Reads are cheap, and a client polling a crew would be told it is over a
  limit by watching its own work.
- **Reading the running count from the ledger.** O(entries) per submit, and the race above.
- **Quotas on sessions and agents,** as the former tables held. Nothing enforced them, and neither is
  what spends.
