# 0008 — Crews belong to the tenant that submitted them, are listed by cursor, and a keyed submit is idempotent

**Status**: Accepted
**Date**: 2026-10-02

## Context

M5 gave agnostic tenants, and plugin documents (0.1.8) were scoped by them from the start. Crews
were not: no ledger entry, stored outcome or audit record said whose a crew was, the crew routes
never saw the principal, and authorisation was by role alone. Anyone holding a crew's id could read
it and its events and, with WRITE, cancel it. Unguessable v4 UUIDs were the only protection — and
ids leak: into logs, run records, shared links, a plugin's documents.

Three things M9 and Swarm Command needed sat on top of that gap:

- **A crew listing.** `GET /api/v1/crews` answered 405 on purpose since M2, because a listing
  "needs pagination and a tenancy scope to be worth anything". Without one, Swarm Command could
  show only the crews its own swarms had started, and a crew whose 202 was lost was lost to it.
- **A safe retry.** A client that never saw the 202 — a timeout, a closed tab, a bridge that gave
  up after 30 s — cannot tell whether its crew exists. Resubmitting may pay for the work twice;
  not resubmitting may drop it. Swarm Command reported every such case as "refused".
- **Binding without guessing.** A watcher matched engine events to its own tasks by description
  text, which two tasks may share.

## Decision

**A crew belongs to the scope it was submitted in — the principal's tenant, or `_` — and to no
other.**

- The scope is recorded with the crew from the moment the ledger holds it (set before the entry is
  published, so it is never visible unscoped), and in its stored outcome document.
- **Every crew route answers 404 for another scope's crew**, exactly as for one never submitted —
  not 403, which would confirm it exists. GET, cancel, events and plan alike. A document stored
  before 0.1.9 carries no scope and belongs to `_`.
- **`GET /api/v1/crews`** lists the caller's crews, newest first: those the ledger holds (running,
  and recently finished) and the durable ones it no longer does, from a small index table written
  beside each terminal outcome (`agnostic_crew_index`, indexed on scope). Each item says its name,
  status, times, task count, engine mode, and the tokens and cost it was metered for. Paging is by
  cursor — `next` names the last crew on the page, `?before=` continues strictly after it — so
  crews submitted between two pages never shift one into the next. `limit` is 1–200, default 50.
- **`Idempotency-Key`** on `POST /api/v1/crews` (8–128 of `[A-Za-z0-9._:-]`): a repeat with the
  same key **in the same scope** answers the crew the key started (202, `"replayed": true`); the
  same key over a different body is a 422. Keys are remembered while the ledger holds the crew, not
  across a restart. Keyed submissions are serialised by their own lock, so two racing retries
  cannot both submit.
- **The 202 carries `task_ids`**, the engine's id for each task in request order, and
  **`GET /api/v1/crews/{id}/plan`** describes any crew the ledger holds — its agents, and its tasks
  with those ids, descriptions and dependency indices — so a client binds progress events to tasks
  by id.

## Consequences

- **Positive** — Tenant isolation now covers the whole crew surface, checked by
  `tests/crew_tenancy.tcyr` with four mutations. A UI can list and watch every crew of its tenant.
  A client can retry a submission without risking a second bill. Live views bind tasks exactly.
- **Negative** — ⚠ **Breaking** for a deployment with tenants: a crew is no longer readable from
  another tenant, and a crew stored before 0.1.9 is readable only from `_`. Crews stored before
  0.1.9 have no index row, so they are not listed (`GET /crews/{id}` still answers them). The
  listing reads every index row of the caller's scope per call; patra answers a scope with 1024 or
  more rows by scanning rather than truncating, so a very large tenant costs a scan.
  Idempotency keys do not survive a restart: a retry with a key the restarted process never saw
  starts a new crew.
- **Neutral** — There is no cross-tenant view, even for a super-admin; one can be added as its own
  route when an operator needs it. The plan is held in memory only; a crew from before a restart
  has an outcome but no plan.

## Alternatives considered

- **403 for another tenant's crew.** Rejected: it confirms the crew exists, which is the leak.
- **Filter the listing by scope but leave the other routes role-only.** Rejected: the id routes are
  where the exposure actually was.
- **Offset pagination.** Rejected: an offset shifts under every new crew, so pages repeat or skip.
- **A client-chosen crew id instead of a key.** Rejected: agnostic mints no ids — every id is the
  engine's (`ORACLE-AUDIT.md` §3.2) — and the key needs no such change to the engine.
- **Persist keys.** Deferred: the window a retry needs is seconds, which the ledger already covers;
  a durable key table is a schema and a cleanup policy for a case nobody has measured.
