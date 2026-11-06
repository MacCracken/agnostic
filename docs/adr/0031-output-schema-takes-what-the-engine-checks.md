# 0031 — `output_schema` takes what the engine checks, and a result says whether it was met

**Status**: Accepted
**Date**: 2026-11-06

## Context

agnosai can hold a task's answer to a shape, and the reviewer preset and M8's structured result both need
that. Three things in agnosai 2.2.4 shape what forwarding it can honestly mean, all read from its source:

- It is called a schema and agnosai checks two things of one: the top-level `type`, and that each name in
  `required` is present. The rest of the object does nothing.
- It re-asks twice, and never checks the last answer, so a task that never meets the shape reads
  `completed`.
- The model first sees the schema in the retry prompt, after it has already failed.

The last two are agnosai's to fix, and are filed there
(`2026-11-06-agnostic-output-schema-is-not-held-to.md`).

## Decision

**A task's `output_schema` takes `type` and `required`, and refuses anything else by name.** `properties`
would be accepted and enforce nothing, and the caller would believe it had: that is a field silently doing
nothing, which this port refuses, and it is refused the way `gpu_strict` is. A refusal can be relaxed the
day the engine acts on a key. A key accepted before then cannot be taken back after the freeze.

**Shapes that could never pass are refused too:** a `type` agnosai does not know, such as `integer`, which
it would never match; `required` under any `type` but `object`; and a `required` of non-strings, which it
would skip.

**`output_valid` on a task's result says whether the answer met the shape.** Only a completed task that
declared one has it. agnostic runs agnosai's own check, so a fenced answer passes as it does there. This
stays useful whatever agnosai decides, and if agnosai comes to fail such a task, nothing here changes.

**It is read once per crew, by the first reader, and kept on the ledger entry.** The engine's check
allocates on the global heap, so a poll that ran it would keep a little every time. The engine's result
objects are not marked instead: a poll and the collector read them at once, and writing to their
metadata would race both.

**A parse that fails is not a verdict.** Parsing runs in the reader's arena, because a parse tree runs to
twenty times its text and the engine's own parser would keep it for life. bayan answers 0 for text that is
not JSON and for an arena that ran out, so a parse that fails on text the no-allocation scanner calls
well-formed leaves `output_valid` out, rather than say `false` of an answer that may be right.

**agnostic does not copy the schema into the task's context** to reach the first prompt. It would work, in
one line, and it would be a way round a fix that belongs in agnosai. The documentation says to describe
the shape in `expected_output` meanwhile.

## Consequences

- **Positive** — a caller can tell a `completed` task that met its shape from one that did not.
- **Negative** — `completed` and `output_valid: false` can stand together. That is the truth: the model
  answered, and the answer was not in the shape.
- **Negative** — until agnosai's fix, a task with a schema and no description of the shape pays for a first
  call that could not pass.
- **Not done** — field types inside the object. M8's structured result needs them, and they wait on
  agnosai checking them.
