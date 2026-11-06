# 0027 — A scraper has a credential of its own, and metrics stay in the request's arena

**Status**: Accepted
**Date**: 2026-11-06

## Context

Nothing served `agnosai_metrics_gather` (G7), and traces are not a counter a dashboard can alert on. The
counts cover every tenant, so they are SUPER, as the audit trail is (ADR 0023). A scraper's config is a
plain file on another machine, and a super administrator's API key in it could do anything.

`agnosai_metrics_gather` builds its text on the global heap and returns it, which has no `free`. A scrape
every 15 s would keep about 1 KB each time, for ever, and `tests/request_alloc.tcyr` holds every request
path to 0.

## Decision

**`GET /api/v1/metrics` is SUPER, and `AGNOSTIC_METRICS_TOKEN` opens that one route and nothing else.**
At least 32 bytes, compared over SHA-256 digests so that neither its length nor a prefix can be read from
the timing. Unset, only a super administrator can read it.

**agnosai's six families are rendered here, under agnosai's names, from its accessors**, in the request's
arena, beside agnostic's own. A dashboard keyed on those names reads the same.

**Every label value is a word in the source.** A tenant, a path or a status code as a label is a series per
distinct value, which is a memory bound a caller sets in the scraper.

## Consequences

- **Positive** — a scraper holds a credential that can read counts and do nothing else.
- **Negative** — one more secret for an operator to rotate, and the family names are written in two
  places. A family agnosai adds does not appear until it is added here.
- **Neutral** — no per-tenant figures, and no latency histogram. A route's latency is in the traces
  (ADR 0020).

## Alternatives considered

- **A READ user's key.** The counts cross tenants, which is why the audit trail moved to SUPER.
- **An open route.** Crew counts and refusal rates are worth something to an attacker.
- **A new agnosai call taking an allocator.** It would save the copy of six names and move nothing else,
  and it would make this release wait on another.
