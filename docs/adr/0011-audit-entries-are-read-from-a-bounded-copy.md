# 0011 — The audit trail's newest entries are read from a bounded copy, not the store

**Status**: Accepted
**Date**: 2026-10-02

## Context

`GET /api/v1/audit` reports the trail's state — its count, whether the hash chain verified when the
server started, how many appends failed — but nothing could READ an entry. The Audit view (0.1.10)
needs the newest entries, paged, with each one's hash and its predecessor's.

libro's patra store offers one read: `patrastore_load_all`, every row of the trail, each copied into
the global allocator — which has no `free()`. Serving a page that way would leak the size of the
whole trail on every request, and the trail only grows. There is no ranged read (`LIMIT`/`OFFSET`
or a by-index lookup) in libro to page with. (Reading on a pool worker is no longer the hazard it
was: libro 2.8.9 made both read paths parse on the calling thread — see `src/engine/audit.cyr`.)

## Decision

**The newest 1024 entries are kept in memory, copied into fixed slots, and
`GET /api/v1/audit/entries?limit=&before=` reads them, newest first, by index. ADMIN.**

- **Seeded at open from the load that verifies the chain** — the only full read the process makes —
  and **filled as each entry is persisted**, under the audit lock, in the same step that links and
  writes it. The slots are allocated once (680 bytes each, ~0.7 MB) and reused.
- **An entry's `index` is its position in the chain**, from 0; `next` is the index to send back as
  `?before=`; `oldest_held` is the lowest index the route can answer and `total` the chain's length.
  Older entries stay in the store, covered by verification, and are not served here.
- **A field too long for its slot is cut at a UTF-8 boundary and marked `cut: true`.** Agnostic's own
  entries always fit (a detail is at most 255 bytes); the cut exists for a trail another writer
  shares. The stored entry — the evidence — is never touched.
- **`hash` and `prev_hash` are served**, so a reader can see each entry name the one before it. The
  Audit view checks those links for the entries it shows — a reading aid, stated as such; the
  verification is still the server's pass at start-up, which re-hashes every entry.

## Consequences

- **Positive** — A page costs a copy of at most `limit` entries into the request's arena, with no
  global allocation and no store read, whatever the trail's size. The view sees entries the moment
  they are persisted.
- **Negative** — Only the newest 1024 entries are readable over HTTP; the rest need the store file.
  ~0.7 MB is resident for the life of the process. Entries written by another process sharing the
  store after this one opened are not seen until a restart (agnostic is the trail's only writer).
- **Neutral** — When libro offers a ranged, allocator-aware read, this copy can go, and the route's
  shape — index, cursor, `oldest_held` — can stay.

## Alternatives considered

- **`patrastore_load_all` per request.** Rejected: an unbounded, permanent leak per page view, and a
  cost that grows with the trail.
- **A SQL query of our own against libro's table.** Rejected: the table and its encoding are
  libro's; reading it behind libro's back couples agnostic to a schema it does not own, the trap this
  repo has avoided everywhere else (one store lock, one owner per table).
- **Exporting the chain to a file and serving that.** Rejected: an operator's export already exists
  for the whole trail; the view wants the newest entries now, not a file.
