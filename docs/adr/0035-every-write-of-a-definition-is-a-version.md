# 0035 — Every write of a definition is a version, and a delete keeps them

**Status**: Accepted
**Date**: 2026-11-06

## Context

agnostic has revisions: an ETag per definition, so that two editors cannot overwrite each other unseen. It had
no history. Whatever a definition said before its last `PUT` was gone, and an agent definition decides what a
crew does. agnosai has a version store, in memory, so it is no use across a restart.

The former code had `POST /definitions/{key}/versions`, which saved a snapshot when someone remembered to, and
kept them as files.

## Decision

**Every write of a definition is a version, on a table here**: `agnostic_definition_versions`, keyed like the
definitions and numbered from 1 per key, never reused. Nobody saves one, so there is no route to. History holds
what was there and not what someone thought to keep before they needed it.

**A rollback is a write, so it is a new version.** History only grows at the end, and a rollback can be undone.

**A write that changes nothing adds nothing**, so a client that PUTs what it read does not push a real version
off the end.

**`AGNOSTIC_MAX_VERSIONS` keeps the newest of each key**, 50 by default. A version past the cap is gone, and a
rollback to it is a 404.

**Deleting a definition keeps its versions, and a rollback brings it back.** That is the accident history is
for. The cost is that a delete does not erase what a definition said, which `SECURITY.md` says.

**A rollback takes today's door.** A version was accepted under the rules of its day and would run crews under
today's. One the door would refuse now is a 409, and nothing changes.

**The version is written first, then the definition.** A stop between the two leaves a version that was never
current, which a list shows and nothing minds. The other order leaves a definition no version holds. Not a
transaction, for the reasons crew writes are not.

**A definition from before 0.4.2 has no versions.** Its first replace saves what the row held as version 1, with
no `saved_at`, as nobody knows when it was written.

## Consequences

- **Positive**: an edit can be read back and undone, by anyone who could have made it. Rollback is WRITE, as `PUT`
  is, and audited at WARNING, as a delete is, because it undoes someone's work.
- **Positive**: an import goes through the same write, so what a package replaced can be got back
  ([ADR 0036](0036-a-package-is-json-and-all-of-itself.md)).
- **Negative**: each definition write is two fsynced writes, about 23 ms against 11.5. Definitions are written
  by people.
- **Negative**: at the caps, a key holds 50 documents of up to about 60 KB each. Across a tenant that is real
  space, and nothing but the cap bounds it.
- **Negative**: a tenant deleted and made again reads its old versions, as it reads its old definitions.
- **Limit**: a crew that named a definition records what it ran, not which version it was.
