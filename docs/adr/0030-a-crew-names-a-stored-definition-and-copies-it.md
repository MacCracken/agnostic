# 0030 — A crew can name a stored definition, and copies it when it is accepted

**Status**: Accepted
**Date**: 2026-11-06

## Context

An agent definition is stored so that it can be reused, and a client reusing one has had to read it and
send it back (G4). The body had nowhere to name one.

## Decision

**An element of `agents` may be `{"definition": "<key>"}`**, alone, beside agents spelled out. An object,
not a bare string, so that a pinned revision can join it when definition versions land.

**It takes no other field.** A reference does not override: `{"definition": "x", "role": "y"}` is a 422.
Overrides would make a crew a new definition that exists nowhere, and the Library is where a definition
changes.

**Read at the door, and copied into the crew.** A crew runs what its definition said when it was accepted:
a later edit changes the next crew, not this one. From the door on, a named definition goes through the
same check and decoder as one spelled out, so there is still one agent model. One saved before 0.1.15
with another `complexity` is refused until it is given one of the three, as any door refuses it.

**In the caller's tenant.** Another tenant's definition is one that is not there, as every read of a
definition answers it: a 422 saying nothing is stored under that key. Not a 404, because the route exists.

**The decoder touches no store.** A step before it, `agnostic_crew_agents_resolve_a`, reads references into
an `agents` array and hands that over, so `src/engine/request.cyr` still compiles narrowly, which is
what proves it has no hidden dependency. Past the 100-agent cap it does nothing, and the decoder refuses
the body: a body of a million references must not cost a read of the store each.

**`unforwarded` moved onto the crew's entry.** A replay used to read it off the body, and a body no longer
says what its agents carry. Kept as bits, it says what the crew it replays carried, even if the
definition has changed since.

## Consequences

- **Positive** — a client sends a key, a Library edit reaches the next crew, and a stored crew's plan
  still says exactly what ran.
- **Negative** — `crews:write` can use a definition it cannot read. A plugin holding `crews:write` without
  `definitions:read` can run one and see its plan, within its own tenant. No role is in that position.
- **Negative** — a crew submitted with an `Idempotency-Key` replays by body, so a retry after an edit
  answers the crew that ran the old definition. That is what a replay is.
