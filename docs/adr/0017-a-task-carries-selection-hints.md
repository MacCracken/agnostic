# 0017 — A task carries the hints the engine selects its agent by, checked at the door

**Status**: Accepted
**Date**: 2026-10-04

## Context

agnosai assigns each task of a crew to one agent of its roster. `agnosai_rank_agents` scores every
agent against the task on five factors and folds them with fixed weights: tool coverage 0.35,
complexity alignment 0.25, GPU capability 0.10, domain match 0.15 and personality 0.15. Four of the
five read the **task's context** — `required_tools`, `complexity`, `gpu_required` and `domain` —
and agnostic's task request (`src/engine/request.cyr`) could set none of them. So for every crew
agnostic ran:

- tool coverage, GPU and domain scored 1.0 for every agent, and personality is a constant 0.5 until
  agnosai ports bhava;
- complexity was the only factor left, against a task that always read as `medium`;
- so the first agent whose own complexity is medium, or unset, won **every** task, whatever the
  roster. Ties go to the lowest index.

The roster an agent definition describes — its `tools`, `domain`, `complexity`, `gpu_required` —
therefore shaped nothing. ADR 0016's `?explain=selection` makes this visible, which is why the
decision was recorded with it ("Decision, not yet taken: per-task selection hints", roadmap,
0.1.13). It was open because it widens the public request ahead of the v1.0 freeze. The user took it
on 2026-10-04: add the hints in 0.1.14.

Two engine behaviours make a straight pass-through wrong:

- **The engine validates nothing a caller would see.** `required_tools` holding anything but strings
  is read as no requirement, which scores every agent full coverage: a malformed list makes every
  agent look *more* suitable, with a warning in the log as the only sign. An unrecognised
  `complexity` is read as medium. A non-boolean `gpu_required` is ignored.
- **The context is the prompt's preamble.** `_agnosai_crew_build_request` renders the whole context
  map into the model request, so whatever a task carries in its context, the model reads.

## Decision

**A task in `POST /api/v1/crews` may carry `required_tools`, `complexity`, `domain` and
`gpu_required`. agnostic checks each strictly, forwards it into the engine task's context under the
selector's own key, and the plan route shows it back.**

- **The fields, and what is refused.**
  - `required_tools`: an array of non-empty strings, at most 64 (`AGNOSTIC_REQ_MAX_TOOLS`, the
    agent's cap). An array with any non-string is a 422; an empty name or a 65th is a 400. An empty
    array is accepted and means what it says: no requirement. Names are carried verbatim, like an
    agent's `tools`: there is no tool registry to check them against until M6.
  - `complexity`: `low`, `medium` or `high`, the wire's lowercase spellings. Anything else is a 400
    naming the three, never the engine's silent medium. It is a closed vocabulary in the schema
    (`vocabularies.complexity`), walked through `agnostic_complexity_to_wire` like process,
    priority and risk.
  - `domain`: a non-empty string up to 10,000 bytes. The engine compares it with each agent's
    domain ignoring case, and an agent with no domain is never penalised.
  - `gpu_required`: a boolean; `"true"` is a 422, as everywhere here.
  - `null` is absent for all four.
- **Forwarded, not reinterpreted.** `_agnostic_task_spec_hints` writes each given hint with
  `agnosai_task_with_context`, as the JSON value the selector reads. A hint left out is not written,
  so the selector's default applies: no tool requirement, complexity medium, any domain, no GPU.
- **Shown back.** `GET /api/v1/crews/{id}/plan` lists each task's hints, read back from the engine
  task's context, so the plan says what selection was asked to weigh; `?explain=selection` says
  what it decided.
- **Documented for the client.** SKILL.md says that hints are shown to the model, so a client sends
  only what it would let the model read.

## Consequences

- **Positive**
  - The roster means something: a task that asks for `k6` and the `performance` domain goes to the
    agent that has them (`request/hints` and `crews/plan-hints` show each hint moving the winner).
  - Every way the engine would have misread a hint silently is a 4xx naming the task and the field.
  - Nothing changes for a request without hints: no context key is written, and the selection is
    exactly what 0.1.13 made.
- **Negative**
  - **The public request is wider**, four fields more to keep through the v1.0 freeze. They are the
    engine's own names, so a future engine that reads them differently is a re-pin decision, not a
    rename.
  - **The model reads the hints.** A hinted task's prompt gains a context preamble (the hints as
    pretty-printed JSON), which costs tokens and changes the request body that hoosh caches on. That
    is how agnosai treats task context, and keeping the hints out of the prompt would need an engine
    change; ADR 022 in agnosai rejected stamping a crew id into the context for exactly this reason.
  - `required_tools` names are not checked against anything, so a typo is a tool no agent has: every
    agent scores zero coverage and the ranking falls back to the other factors. The plan shows the
    names sent, and `explain` shows the zeros.
  - An agent definition's own `complexity` is still free text, which the engine reads as medium
    when it does not recognise it. Making it a closed vocabulary would refuse stored definitions, so
    it is recorded on the roadmap, not done here.
    *Note, 0.1.15:* closed at the door, not in the decoder. A crew's `agents` and a definition's
    `POST` and `PUT` refuse anything but `low`, `medium` or `high` with a 400, as a task's hint is;
    a definition stored earlier with another value is still read as it is, and has to be given one
    of the three before it can be saved again or sent in a crew. All 76 preset agents already use
    `high` or `medium`.
- **Neutral**
  - Swarm Command does not send hints yet; its roles carry tools that could become a task's
    `required_tools`. Recorded on the roadmap.
    *Note, 0.1.15:* it does since Swarm Command 0.5.1. With its role roster each agent's `domain` is
    its role and its `tools` the kinds the role uses, and each task asks for the same `domain` and
    `required_tools`. A coder and a reviewer use the same kinds, so the tools tie and the domain
    decides (`request/swarm-roles`). A preset roster gets no hints: its domains name no swarm role.

## Alternatives considered

- **Assign agents explicitly (`agent` on a task).** Not taken: the engine has no per-task
  assignment to forward it to — it picks by score in every process mode — and an assignment agnostic
  could not enforce would be a field that silently does nothing.
- **Pass the hints through unchecked.** Rejected: each of the engine's misreadings is silent, and one
  of them makes a malformed requirement score every agent full marks.
- **Accept the engine's case-insensitive complexity** (`"HIGH"`). Not taken: priority, risk and
  process are lowercase wire names here, and one spelling per value keeps the schema's vocabulary
  exact. The engine still compares case-insensitively for what it receives.
- **Keep hints out of the prompt.** Not possible from agnostic: the engine renders the whole context.
  If agnosai separates selection hints from prompt context, the forwarding changes and the wire does
  not.
