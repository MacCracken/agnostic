# 0025 — A refusal always counts, and is written within a budget

**Status**: Accepted
**Date**: 2026-11-06

## Context

A failed login is audited since 0.2.2. A 401, a 403 and a rate-limit hit left nothing, so an operator
could not see a credential being guessed or a role being probed (G12). An audit append is a chained hash
and a store write, and a 401 needs no credential. One entry per refusal lets an anonymous caller turn a
cheap request into a durable write, and push the record of what they did past the 1024 newest entries
the route serves.

## Decision

**Counting and writing are separate** (`src/engine/refusal.cyr`).

- **Every refusal counts**, in memory, and `GET /api/v1/metrics` serves the counts.
- **In any 60 s window the first 16 refusals of any kind get entries of their own**, with the peer, the
  route's pattern and the user: `auth.denied`, `auth.forbidden`, `auth.throttled`, `auth.shed`,
  `tenant.throttled` and `tenant.crews_full`.
- **The rest are held as counts, and one `audit.refusals_held` entry writes them** when the window ends:
  on the next refusal, on the collector's tick, or at a graceful stop.

So a refusal costs at most 17 durable writes a minute whoever is sending, and what is withheld is the
detail, never the fact.

## Consequences

- **Positive** — an operator sees who was refused and where, and a flood shows up as a number in the
  trail. `agnostic_rl_shed_count` and `agnostic_argon_shed_count` have a reader.
- **Negative** — past the budget the peer and route are gone. A second caller inside a flood is only a
  number.
- **Neutral** — each of the 16 keeps libro's ~250 B on the global heap, as every audited request does
  (roadmap, *Memory*). The budget bounds that too, at about 6 MB a day under constant attack.

## Alternatives considered

- **A pool per kind.** It multiplies the bound by six and protects nothing: the second kind's count is in
  the summary anyway.
- **Logging only.** Logs are not chained, and a refusal is what a tamper-evident trail is for.
- **Only the summary.** It says that someone was refused, and not who.
