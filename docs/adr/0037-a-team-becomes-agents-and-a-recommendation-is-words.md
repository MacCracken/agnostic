# 0037 — A team becomes agents at the door, and a recommendation is a table of words

**Status**: Accepted
**Date**: 2026-11-06

## Context

Two things the former code had that no route offered: describing a crew by the roles it needs, and asking which
preset fits a description. agnosai has `agnosai_assemble_team`, which drops any member nothing matches. Its
`recommend_preset` had no owner, and agnostic's library is the canonical one.

## Decision

**`team` stands where `agents` would, and becomes `agents` before the crew body is decoded.** So a team takes every
check a spelled-out crew does, and nothing past `src/engine/team.cyr` knows a team was asked for. `agents` and
`team` together are a 400, and `agents` is no longer `required` in the schema: the schema says `one_of`.

**A member takes the best of what is known**, the caller's stored definitions before the preset library's agents,
by agnosai's `agnosai_assembler_match_score`. Failing that, it is **written from the role**, so that what was asked
for is never dropped. The plan route shows who it became.

**A match needs a score of 5**: a role, or two tools. The engine calls anything over 0 a match, so one tool that a
QA engineer also lists would turn a Game Designer into a QA engineer.

**The first member leads when none is named**, and a lead has high complexity if it was written from its role.

**A recommendation is a table of words**, `POST /api/v1/preset-recommendations`, with no model: the same words
give the same answer, it costs nothing, and `matched` says what it went on. It is a POST because a description can
run to 10,000 bytes.

**A word matches at the start of a word.** The former code looked anywhere, so "ui" found "build" and "guide", and
"lake" found "flake". "test" finds "testing" and not "contest".

**It offers only what the library holds.** The table is hand-kept, so `recommend/library` walks every domain and
size, and a name that does not resolve is never offered.

## Consequences

- **Positive**: a client can ask for a team without knowing a key, and see who it got.
- **Positive**: a team crew keeps nothing on the global heap. `agnosai_team_member_new` has no `_a` form, so the
  member record is built here from its enum offsets. That reaches into agnosai's layout, and an `_a` form is the fix.
- **Negative**: each team crew builds an engine record for all 76 preset agents, in the request's arena: 96 µs for
  three members, on a path a person starts.
- **Negative**: `context` and `project_context` reach the model. So does a stored definition, which is why only the
  caller's own are read.
- **Negative**: a recommendation reads a description, not a mind. It has no way to know it is wrong, and says what
  it went on so that a person can.
