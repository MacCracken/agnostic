# 0028 — A field's row says what it holds, and one check reads it

**Status**: Accepted
**Date**: 2026-11-06

## Context

The API schema listed each body's fields and said nothing of their types: those were decoder code,
one `if` per field, in five modules. M7's tools mirror the routes and each needs a JSON input schema, so
without the types as data M7 would hand-write a copy of them, which is what
[ADR 0015](0015-the-http-api-is-described-by-a-generated-schema.md) exists to prevent.

## Decision

**An allow-list row is a name, a kind and whether the field is required**, and the rows are the only
place those facts live. Kinds are string, integer, boolean, object, array, array of strings and array
of integers. The last two check every element, because agnosai reads an array holding anything but
strings as no requirement at all.

**One check reads them, `agnostic_field_bad`, at every door.** It runs after the allow-list and before
a field is read, and decoders hold no type check of their own: about 25 branches came out. So a
schema entry cannot disagree with its door, because the door reads the same row.

**The schema gains `types`, beside `fields`.** `bodies.<name>.types` maps a field to its `type`, `items`
and `required`. `fields` stays as it was, so the document's format does not change and nothing that
reads it breaks.

**Each door keeps the status it has always answered.** Crew, task and agent bodies answer 400 for a
required field and 422 for an optional one of the wrong type; the identity, login and plugin bodies
answer 422 for both. Unifying them would have been a break made for tidiness.

**`null` in an optional field is the field left out**, as `agnostic_opt_str` always read it, and in a
required field it is the field missing. `rate_limit` and `max_crews` used to refuse `null`, and now
follow the rule.

**The identity routes check fields only for a principal.** With authentication off they answer 409,
and a 422 about a body they will never read would hide that.

## Consequences

- **Positive** — M7 reads its input schemas from the document, and `tests/api_schema.tcyr` proves each
  claim by sending every field of every body the wrong type through its real route, and leaving out
  each required one.
- **Negative** — a body naming two faults reports the first in row order, which is not always the
  first it reported before. Several messages changed too: `email and password are required` now reads
  `'email' is required and must be a string`. Statuses did not.
- **Neutral** — the agent and task rows are built once at load, because a crew reads them per element, and
  built per read they took a crew's decode from 43 to 60 µs. The rarer bodies build theirs per request.
- **Not done** — bounds, such as a length or a range, are not in the rows. They are still decoder code,
  and `types` says nothing of them.
