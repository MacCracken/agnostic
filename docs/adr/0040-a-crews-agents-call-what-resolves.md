# 0040 — A crew's agents call what resolves, held to its target and written down first

**Status**: Accepted
**Date**: 2026-11-08

## Context

Through 0.4.4 an agent's `tools` were words in its prompt. agnosai 2.3.0 gave it a tool loop, in which a model calls the
tools its agent names until it answers, and left three things to the consumer: the registry
(`agnosai_orchestrator_with_tools`, option 1 of `handoff.md` §8), a gate on what a tool may reach, and a journal that
writes each call down before it runs.

Turning that on changes what a name means. agnosai fails a task whose agent names a tool the registry does not hold, so
that a model is never told it holds something it cannot call, and writes down what the tool would have said. Five presets
named 38 tools, and 36 of those have nothing behind them. Some cannot be written yet: the browser and device tools wait on
yantra (D4).

## Decision

**agnostic's registry is the orchestrator's, and every call is held and journaled.** `agnostic_qa_catalog_init` builds it
at mount, `crews_call_tools` is `true`, and the registry holds `echo`, `json_transform`, `load_testing` and
`security_audit`.

**A preset names only what runs, and a name goes back when its tool is written.** Settled with the user on 2026-11-08.
An agent told it holds tools it cannot call invites invented findings, so the unwritten names came out of the documents. The
38 stay in `src/engine/tools.cyr` as a ledger, and `GET /api/v1/tools` still counts all of them, so M6's number, 36, is
still the honest one. Emptying the presets did not bring it down.

**A name resolves or the crew is refused,** at the door with a 400 naming the tool, before a crew exists or a token is
spent. That covers an agent's `tools` and a task's `required_tools`, which no agent could otherwise hold. A stored
definition is a document and may name what is not written, so it is checked when a crew uses it. A name is the ledger's
with a backend, or the engine's own. No case transform: `LoadTestingTool` works by a row in a table, and a tool goes to the
engine under the engine's name, so a model and a report read the same word.

**A tool may point only at the host its task runs against.** The registry's gate reads the task's `target`, compares its
host with the URL's, and answers for the first request and every redirect hop. A declared host is admitted even when it is
private, because the operator listed it (ADR 0029). Anything else is refused, and so is any URL at all for a task with no
target. The system under test writes what the model reads, so "now scan this other host" has to be refused here and not
hoped against in a prompt. A tool that takes no URL is not affected. No batch rule yet: nothing here reads a secret.

**Every call goes on the audit trail before it runs, and its result after.** `tool.call`, then `tool.result` with its
effect, naming the crew, the task and the tool, never the arguments, as the trail is kept for good. A call the trail cannot
take does not start. A crash leaves an intent with no result, which reads as an unknown effect.

**One thread writes those entries, and a task waits for it.** patra keeps a page slab per thread that writes, and a crew's
threads are new each time, so writing from the task left about 18 KB for good: 21.7 KB a crew with one tool call, against
3.5 KB through one writer. The entry is on the waiting task's stack, so the handoff allocates nothing and stays write-ahead.

**A task's result says what its tools did:** `tool_calls`, each with its id, tool, arguments, effect, success, `result` or
`error`, and `flagged`, `held_back` or `asked_for` when they apply. Picked field by field, as `usage` is. What a tool
measured is now told apart from what a model claimed, which is what reports will read (M8).

**Swarm Command's tool kinds stay in the simulator.** It sent `llm` and `fs` as `tools`, which steered agent selection and
named nothing a crew can call. `domain` decides the agent, and the kinds are no longer sent.

## Consequences

- **Positive** — The tool loop is on, and a load test's measurements reach a crew's result. An agent is never told of a
  tool it cannot call.
- **Positive** — Each new tool is one row in the table and the name back in its presets, and nothing else moves.
- **Negative** — A request naming a tool that does not exist was accepted through 0.4.4 and is now a 400.
- **Negative** — The quality presets' agents hold far fewer tools until M6 writes them, and their list reads short. It says
  what they can do.
- **Negative** — A crew with no `llm_model` now needs a gateway catalog or an `AGNOSAI_MODEL_*` override: agnosai 2.3.1
  fails it, by name, where it used to send a guessed id.
- **Negative** — Each entry goes through one writer thread, so a call waits for a context switch before it runs.
- **Neutral** — `load_testing` lets a model choose up to 500 users against a listed host. The operator listed it.

## Alternatives considered

- **Keep the loop off until all 38 are written or struck.** Nothing would run until yantra lands, and agents would go on
  being told of tools they cannot call.
- **Leave the presets alone and let them fail.** Five quality presets would refuse to run until the last tool is written.
- **Register a stub for each unwritten name.** The ledger would read 0 and a model would call a tool that does nothing.
  That is the oracle's failure with better bookkeeping.
- **Translate names at the engine.** agnosai's grant reads the registry's name, so a translation belongs at agnostic's door.
- **Write the journal from each task.** Simplest, and it kept 18 KB for every crew, for the life of the server.
- **A batch gate now.** Two tools that each pass and leak together need something secret to leak. None exists here yet.
