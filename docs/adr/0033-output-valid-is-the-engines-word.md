# 0033 — `output_valid` is the engine's word, and a placeholder has none

**Status**: Accepted
**Date**: 2026-11-06

## Context

[ADR 0031](0031-output-schema-takes-what-the-engine-checks.md) ran agnosai's check itself, because
agnosai 2.2.4 said `completed` of an answer it had never checked. That needed a parse per task, a map kept
per crew on the global heap, a three-way result for a parse that ran out of memory, and a lock around a
pointer on aarch64.

agnosai 2.2.5 repaired both of agnostic's reports. Every answer is checked, the last included. A task that
never meets its schema is `failed`, with the model's last words as `output` and `validation_attempts` in its
metadata. A fenced answer that passes is returned as the block. The schema is in the first prompt.

So the check agnostic ran can no longer disagree with the status beside it: a completed task has passed it.

## Decision

**`output_valid` is read from what the engine says, and agnostic's own check is gone.** On a task of a live
crew that declared a shape:

| The task | `output_valid` |
|---|---|
| `completed` | `true` |
| `failed`, with `validation_attempts` | `false` |
| `failed` for any other reason | left out: it has no answer to judge |

**A placeholder crew has none.** With no gateway the engine echoes the task's description as `completed` and
checks nothing. `true` would be false, and `false` would judge an answer no model gave. Until now such a task
read `false`, which told a caller something about a model that was never asked. `engine_mode` says which this
was.

The field stays, and now says something new: `false` tells an answer in the wrong shape from a gateway that
failed, which `status` alone cannot.

## Consequences

- **Positive**: about 90 lines and a per-crew map are gone, and with them the last thing the ledger allocated
  on the global heap per crew. Reading it allocates only in the reader's arena, and only for a crew with a
  shape.
- **Behaviour**: a crew with a task that never meets its shape is now `failed`, where it read `completed`, and
  a DAG's dependents do not run. Its `tokens` and `cost` count every call. Its `output` loses a code fence.
- **Behaviour**: a placeholder crew's task no longer carries `output_valid: false`. A client that read its
  absence as `true` was already wrong, as ADR 0031 said a failed task has none.
- **Negative**: a crew's stored outcome from before 0.4.2 may say `completed` beside `output_valid: false`.
  Stored outcomes are write-once, so it keeps saying that, which is what was true of it.
- **Not done**: field types inside the object wait, as they did, on agnosai checking them.
