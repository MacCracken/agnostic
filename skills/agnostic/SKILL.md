---
name: agnostic
description: "Drive an agnostic server over its HTTP API: check readiness, submit a crew of agents and tasks, follow its progress with the event cursor, read its results, token usage and cost, list or cancel crews, and look up presets and agent definitions. Use whenever the user asks to run, watch, inspect, cost or cancel an agnostic crew, or to script against an agnostic server (AGNOSTIC_URL, by default http://127.0.0.1:8000). Not for building or changing agnostic's own source code."
license: GPL-3.0-only
compatibility: "Needs curl or another HTTP client, and network access to the agnostic server. Describes the /api/v1 crew API of the agnostic 0.1 line, from 0.1.13."
---

# Driving agnostic

agnostic runs **crews**: a named set of agents and tasks that its engine executes in the
background. You submit a crew, get `202` and a `crew_id`, and poll. Everything is JSON over HTTP.

## Guardrails

Read these first. The rest of this file is how to keep them.

1. **Stop when `GET /ready` is not 200.** Tell the user what it said. Do not start, restart or
   reconfigure the server yourself: a restart invalidates every login token, and every crew still
   running stops for good (it then answers `interrupted`, and its work is lost).
2. **Cancel only crews you submitted** in this session, or one the user names and asks you to
   cancel. A listing shows every crew in your tenant, including other people's and the WebGUI's.
3. **Do not guess fields.** Every error names what is wrong. Change exactly that and resubmit once.
   Never drop something the user asked for just to get past an error; tell them instead.
4. **Send an `Idempotency-Key` with every submit**, and retry only with the same key and the same
   bytes.
5. **Say when the engine is in `placeholder` mode.** Its "results" are the task descriptions echoed
   back, not work.
6. **Spend only what the user asked for.** A `live` crew calls the user's LLM gateway, and nothing
   asks for approval once it is running. Resubmitting an `interrupted` crew spends again: ask first.
7. **Keep credentials out of output and out of tasks.** Never print a token or password, and never
   put one in a task description: task text goes to the model and is stored.
8. **Stay on the crew surface.** Writing agent definitions, switching WebGUI plugins and reading the
   audit trail affect every user; do them only when asked. Never send an `X-Agnostic-Plugin`
   header, which is for WebGUI plugins only.

## 1. Find the server and check it

The base URL is `$AGNOSTIC_URL` if it is set, else `http://127.0.0.1:8000`. `AGNOSTIC_URL` and
`AGNOSTIC_TOKEN` are this skill's convention; the server reads neither.

```sh
AGNOSTIC_URL=${AGNOSTIC_URL:-http://127.0.0.1:8000}
curl -sS "$AGNOSTIC_URL/ready"
```

<!-- schema: response GET /ready -->
```json
{"status":"ready","version":"0.1.13","checks":{"engine":"ok"}}
```

A 503 says `"status":"not_ready"` and names the failing check with `"error"`: stop (guardrail 1).
`GET /health` answers 200 whenever the process is up. It is not a go signal.

Then learn the authentication mode by asking without a credential:

```sh
curl -sS -o /dev/null -w '%{http_code}\n' "$AGNOSTIC_URL/api/v1/crews?limit=1"
```

- **200**: `AGNOSTIC_AUTH=off`, so no credential is needed. The server then listens on loopback
  only and answers only a loopback `Host`; use `127.0.0.1` or `localhost`.
- **401**: `AGNOSTIC_AUTH=required`. Get a credential (section 2).
- **403** "only a loopback Host is answered": you reached it by another name. Use `127.0.0.1`.

## 2. Credentials, when authentication is required

Send one of these on every `/api/v1` request:

- `Authorization: Bearer $AGNOSTIC_TOKEN`, a token from login. If `AGNOSTIC_TOKEN` is unset, ask
  the user for an email and password. Never guess them and never go looking for them. Then:

  ```sh
  curl -sS -X POST "$AGNOSTIC_URL/api/v1/auth/login" -H 'Content-Type: application/json' \
    -d '{"email":"ops@example.com","password":"…"}'
  ```

  <!-- schema: response POST /api/v1/auth/login -->
  ```json
  {"token":"…","token_type":"Bearer","expires_in":3600,"role":"operator"}
  ```

  A token lasts an hour and does not survive a server restart. A 401 with a token that used to work
  means log in again, once. Login allows 5 quick attempts per address, failed or not, and then one
  every 12 seconds; beyond that it answers **429** "too many attempts; retry later" with no
  `Retry-After`. Wait instead of retrying.
- `Authorization: ApiKey …` (64 hex characters), only if an operator gave you one. No HTTP route
  issues keys.

<!-- schema: vocabularies.roles -->
Roles: `viewer` reads; `operator` also submits and cancels crews and writes agent definitions;
`admin` and `super_admin` also read the audit trail and switch plugins. **401** means the
credential is missing or bad. **403** "insufficient permissions" means your role is too low: do not
retry, tell the user.

With authentication off an `Authorization` header is ignored, so the examples below work either way.

Crews belong to your tenant. Another tenant's crew answers **404** on every route, exactly like a
crew that never existed. With authentication off, everyone shares one tenant, `_`.

## 3. Rules for every request

- Every **POST and PUT** sends `Content-Type: application/json`, including cancel, which has no
  body. Without it the answer is **415**.
- A body is at most 1 MiB by default (**413**).
- Every error is `{"error":"…"}`, and the message names the field or rule. (A few WebGUI plugin
  refusals add a `code`.) **405** means the path exists but not with that method.
- Crew ids are UUIDs, matched case-insensitively. A malformed one is **422**.
- The server ignores query parameters it does not know, silently. Spell them exactly as here.

## 4. Submit a crew

```sh
KEY=$(uuidgen 2>/dev/null || cat /proc/sys/kernel/random/uuid)   # keep it: a retry must send the same key
curl -sS -X POST "$AGNOSTIC_URL/api/v1/crews" \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $AGNOSTIC_TOKEN" \
  -H "Idempotency-Key: $KEY" \
  --data-binary @crew.json
```

`crew.json`:

```json
{
  "name": "auth-module-review",
  "process": "dag",
  "agents": [
    {"key": "writer", "role": "Software engineer", "goal": "Write a correct, minimal change"},
    {"key": "reviewer", "role": "Code reviewer", "goal": "Find defects before they ship",
     "backstory": "Reads every diff adversarially."}
  ],
  "tasks": [
    {"description": "Propose a fix for the token-expiry bug in auth.py",
     "expected_output": "A unified diff"},
    {"description": "Review the proposed fix and list every defect", "dependencies": [0],
     "expected_output": "PASS or FAIL, then the defects"}
  ]
}
```

**Crew**, these keys and no others:

<!-- schema: bodies.crew.fields vocabularies.process -->
| key | | |
|---|---|---|
| `name` | required | 1 to 10,000 bytes |
| `agents` | required | 1 to 100 agent objects |
| `tasks` | required | 1 to 1,000 task objects |
| `process` | optional | `sequential` (the default), `parallel` or `dag` |
| `max_concurrency` | optional | 1 to 64, only with `parallel` (default 4) |

<!-- schema: bodies.agent_definition.fields -->
**Agent**: `key`, `role` and `goal` are required. `key` matches `[a-z0-9][a-z0-9-]*`, at most 100
characters. Optional: `name`, `backstory`, `domain`, `complexity`, `llm_model`, `tools` (an array of
names, at most 64), `gpu_required` and `gpu_preferred` (booleans), `gpu_memory_min_mb` (an integer
of 0 or more), `focus`, `allow_delegation` (a boolean).

- `focus` and `allow_delegation` are kept but shape nothing; the 202 names them in `unforwarded`.
- `tools` are names only. The engine does not call tools yet.
- You do not assign agents to tasks. The engine picks an agent for each task by scoring every agent
  against the task's hints (below): tools, complexity, domain and GPU. Without hints the agents tie
  on everything but complexity, and the first agent whose complexity is medium (or unset) wins
  every task.
  `GET /api/v1/crews/{id}/plan?explain=selection` (section 7) shows the scores.

<!-- schema: bodies.task.fields vocabularies.priority vocabularies.risk vocabularies.complexity -->
**Task**: `description` is required. Optional: `expected_output`, `priority` (`background`, `low`,
`normal`, `high`, `critical`), `risk` (`low`, `medium`, `high`), `dependencies` (indices into
`tasks`, at most 64, never itself, no cycles; `dag` runs a task after the tasks it depends on).
Hints for choosing its agent: `required_tools` (an array of tool names, at most 64), `complexity`
(`low`, `medium`, `high`), `domain` (compared with each agent's, ignoring case) and `gpu_required`
(a boolean).

- Hints are also shown to the model: they go into the task's context, which the engine puts in the
  prompt. Send only what you would let the model read.

**The 202:**

<!-- schema: response POST /api/v1/crews -->
```json
{"crew_id":"0b6c1d5e-2f43-4a8e-9c71-5d2e8f3a9b10","status":"pending","name":"auth-module-review",
 "engine_mode":"live","unforwarded":[],"task_ids":["…","…"],"submitted_at":1791100000000,
 "scope":"_"}
```

- Keep `crew_id`. It is the crew you may cancel.
- `task_ids` are the engine's ids **in request order**. Events and results name tasks by these ids,
  so match by position, never by description.
- `"replayed": true` appears when your key had already started this crew. Nothing ran twice.

**Idempotency-Key** is 8 to 128 of `[A-Za-z0-9._:-]`; a UUID works. If a submit times out or you
never saw the answer, send the **same bytes** with the **same key**: you get the original crew back
with `"replayed": true`. The same key with a different body, even the same JSON re-serialised, is
**422**. A key is remembered while the server holds its crew, not across a restart: after one, the
same key starts a new crew.

**When a submit is refused**, read `error`; it names the problem.

- **400**: a required field missing or empty, a value out of range or not in its list, a dependency
  cycle, `max_concurrency` without `parallel`, or a body that is not JSON.
- **422**: a key not in the lists above (`unknown field 'task'`, `tasks[2] has unknown field
  'agent'`, `agents[0]: unknown field 'x'`), a value of the wrong JSON type (`"gpu_required":
  "false"`), a refused field (below), a malformed `Idempotency-Key`, or a key reused with a
  different body.
<!-- schema: bodies.agent_definition.refused -->
- **Refused agent fields**, each a 422 that says why: `agent_key` (use `key`), `gpu_strict`,
  `llm_temperature`, `verbose`, `metadata`, `personality`, `hardware`, `tool_instances`,
  `workflow_mode`, `celery_queue`, `celery_task`, `redis_prefix`.

- **`"process": "hierarchical"` is refused** with a 400, because the engine does not implement it.
  Do not switch modes quietly. Tell the user, and offer `dag` with an explicit coordinating task.
- **503** "engine is not available": stop (guardrail 1).
- **503** with a `crew_id` and `"status":"failed"`: the crew was accepted but could not start.
  Report it, and do not resubmit without asking.

## 5. engine_mode

The 202, every poll and every listed crew carry `engine_mode`:

- `live`: an LLM gateway is configured, and tasks are real model calls.
- `placeholder`: no gateway. Every task "completes" with its own description as its output, and no
  tokens or cost are recorded. **This is not work.** Tell the user, and never present the output as
  an answer.

## 6. Follow progress

```sh
curl -sS "$AGNOSTIC_URL/api/v1/crews/$CREW/events?after=0" -H "Authorization: Bearer $AGNOSTIC_TOKEN"
```

<!-- schema: response GET /api/v1/crews/:id/events -->
```json
{"crew_id":"…","status":"running",
 "events":[
   {"seq":1,"at_ms":158,"type":"crew_started","data":{"name":"auth-module-review","task_count":2}},
   {"seq":2,"at_ms":158,"type":"task_started",
    "data":{"task_id":"…","description":"Propose a fix …","agent":"writer"}}],
 "next":2,"missed":0,"lost_events":0,"dropped_events":0}
```

- **The cursor is `after`.** Send `next` back as `after` each time and you read every event once.
  The server ignores query parameters it does not know, so `since` would silently return the whole
  window on every call.
- `status` is the crew's status now; this call refreshes it.
- `type` is `crew_started`, `task_started` (with the agent's key, or null), `token` (a task's whole
  text in one event, for each task the model answered: none in a `placeholder` crew),
  `task_completed` (with `task_id` and `status`) or `crew_completed`.
- `missed` above 0 means more than 256 events arrived after your cursor and the oldest were
  overwritten. You were still given everything held, oldest first: do not reconstruct the rest,
  carry on from `next`, and let the outcome (section 7) settle every task once the crew ends.
  `lost_events` were dropped before they were numbered, and `dropped_events` counts both kinds.
- Events are progress, not the outcome. A `parallel` or `dag` crew announces its tasks as each batch
  starts and reports a batch's `task_completed` in the order its tasks were dispatched, so a
  `task_started` can come after a `task_completed`: track each task by its `task_id`. The outcome
  is section 7.
- Poll at most once a second, since the server collects events every 200 ms, and slower for a long
  crew. Run one poller per crew.
<!-- schema: vocabularies.crew_status -->
- When to stop: `completed`, `failed`, `cancelled` and `interrupted` are final; `pending` and
  `running` are not. `unknown` means the server lost track of the crew: try a few more times, then
  report it. A **404** here for a crew you submitted means the server restarted: its events, plan
  and cancel are gone, and `GET /api/v1/crews/{id}` answers `interrupted` (section 7).
- If the WebGUI's Crews view is switched on, the user can watch at
  `$AGNOSTIC_URL/ui#plugin/crews?crew=$CREW`.

## 7. The outcome

```sh
curl -sS "$AGNOSTIC_URL/api/v1/crews/$CREW" -H "Authorization: Bearer $AGNOSTIC_TOKEN"
```

<!-- schema: response GET /api/v1/crews/:id -->
```json
{"crew_id":"…","status":"completed","task_count":2,
 "results":[
   {"task_id":"…","status":"completed","output":"…",
    "usage":{"model":"…","provider":"…","prompt_tokens":812,"completion_tokens":240,
             "total_tokens":1052,"cost_micro_usd":3150,"duration_ms":4210}},
   {"task_id":"…","status":"completed","output":"…",
    "usage":{"model":"…","provider":"…","prompt_tokens":818,"completion_tokens":272,
             "total_tokens":1090,"cost_micro_usd":3250,"duration_ms":3890}}],
 "usage":{"prompt_tokens":1630,"completion_tokens":512,"total_tokens":2142,
          "metered_tasks":2,"costed_tasks":2,"cost_micro_usd":6400},
 "engine_mode":"live","name":"auth-module-review","scope":"_","process":"dag",
 "tasks_submitted":2,"submitted_at":1791100000000,"started_at":1791100000150,
 "finished_at":1791100009800}
```

- Success is `status` equal to `completed`, which always means every task completed. Do not judge
  by the absence of `error`.
- While a crew runs, `results` is `[]` and `task_count` is 0: the engine hands over results when
  the crew ends.
- A `failed` crew may carry `error`; "a task failed or the crew timed out" means the engine gave no
  reason. Read each result's `status` and `error` as well. A crew times out after an hour by
  default.
- A `cancelled` crew keeps the results of the tasks that had finished.
- `submitted_at`, `started_at` and `finished_at` are epoch milliseconds. An event's `at_ms` is
  milliseconds since the crew was accepted.
- **`interrupted`**: the server restarted while the crew was in flight. Its work is lost and it
  cannot be resumed. It has `results: []`, zero usage, an `error`, and `interrupted_at` (when the
  restarted server declared it) instead of `started_at` and `finished_at`:

  <!-- schema: response GET /api/v1/crews/:id -->
  ```json
  {"crew_id":"…","status":"interrupted","task_count":0,"results":[],
   "usage":{"prompt_tokens":0,"completion_tokens":0,"total_tokens":0,"metered_tasks":0,"costed_tasks":0},
   "error":"the server restarted before this crew's outcome was recorded; its work was lost",
   "name":"auth-module-review","scope":"_","engine_mode":"live","process":"dag",
   "tasks_submitted":2,"submitted_at":1791100000000,"interrupted_at":1791100042000}
  ```

  Tell the user, and resubmit only if they ask (guardrail 6).
- **404** means no crew with that id in your tenant.
- `GET /api/v1/crews/{id}/plan` gives the agents and tasks the engine holds, each task with its
  `task_id`, `index` and `dependencies`. It answers 404 for a crew from before a restart, even when
  the outcome above still answers.
- `GET /api/v1/crews/{id}/plan?explain=selection` also says why each task got its agent. Each task
  gains `selection`: `winner` (`index`, `agent_key`), `candidate_count`, and `candidates`, best
  first, each with its `total` and five `scores` (`tool_coverage`, `complexity`, `gpu`, `domain`,
  `personality`). The answer gains `scorer` (the five `weights`, and the factors it cannot measure
  yet) and `candidate_limit`, how many candidates each task lists: a large crew lists fewer, never
  fewer than the winner. Add `&task=N` (a task's `index`) to explain one task over the whole roster.
  `explain` other than `selection`, or `task` without it, is a 422.

## 8. Usage and cost

- `cost_micro_usd` is millionths of a US dollar: `6400` is $0.0064.
- **An absent cost is not a zero cost.** Call a crew's total complete only when it is `completed`
  and `costed_tasks` equals `task_count`. Otherwise say what it covers: `costed_tasks` of
  `tasks_submitted` tasks.
- `metered_tasks` of 0 means nothing was measured: placeholder mode, a crew still running, or every
  call failed. An `interrupted` crew reports nothing, though its finished tasks may have spent money.
- Each result's `usage` has `model`, `provider`, the token counts, `cost_micro_usd` when the gateway
  priced the call, and `duration_ms`.

## 9. List and cancel

```sh
curl -sS "$AGNOSTIC_URL/api/v1/crews?status=active&limit=50" -H "Authorization: Bearer $AGNOSTIC_TOKEN"
```

<!-- schema: vocabularies.crew_status_filter -->
This returns your tenant's crews, newest first, as `{"crews":[…],"scope":"_","next":"…"}`. Each row
has `crew_id`, `status` and `submitted_at`, and when known `name`, `started_at`, `finished_at`,
`tasks_submitted`, `engine_mode`, `total_tokens` and `cost_micro_usd`. `limit` is 1 to 200
(default 50). `status` is `pending`, `running`, `completed`, `failed`, `cancelled`, `interrupted`,
`unknown`, or `active` for pending and running together. `next` is absent on the last page; send it
back as `before` to read the next one.

```sh
curl -sS -X POST "$AGNOSTIC_URL/api/v1/crews/$CREW/cancel" \
  -H 'Content-Type: application/json' -H "Authorization: Bearer $AGNOSTIC_TOKEN"
```

<!-- schema: response POST /api/v1/crews/:id/cancel -->
```json
{"crew_id":"…","status":"cancelled"}
```

- **200**: cancelled.
- **409**: it had already finished. Read its outcome instead; this is not a case to retry.
- **404**: no such crew in your tenant, or one from before a restart, which cannot be cancelled.
  **503**: the engine no longer holds it, and it was **not** cancelled.
- Guardrail 2 applies: only your own crews, or one the user named.

## 10. Presets and agent definitions

**Presets** are built-in agent rosters, read-only.
`GET /api/v1/presets` returns `{"presets":[…],"total":…}`, each with `name`, `description`,
`domain`, `size`, `version`, `agent_count` and sometimes `workflow_mode`.
`GET /api/v1/presets/{name}` returns the whole document.

A preset is **not** a crew body. Its agents posted as they are get a 422 (`agent_key`). To run one,
build the crew yourself:

1. Take its `agents` and rename `agent_key` to `key`.
2. Drop `celery_queue` and `redis_prefix`, which are refused.
3. Keep `name`, `role`, `goal`, `backstory`, `domain`, `complexity`, `tools`, `focus` and
   `allow_delegation`.
4. Write the crew's `name` and its `tasks`; a preset has no tasks.

**Agent definitions** are stored agents, shared by the whole deployment rather than per tenant.
`GET /api/v1/agents/definitions` returns `{"definitions":[…],"total":…,"storage":"patra"}` with
`key`, `name`, `role` and, when set, `domain` for each. `GET /api/v1/agents/definitions/{key}`
returns `{"definition":{…},"unforwarded":[…],"storage":"patra"}`. A crew cannot name a definition
by key: copy the `definition` object into `agents`, where it is already in the right shape. Writing
one (`POST /api/v1/agents/definitions` answers 201, or 409 when the key exists;
`PUT /api/v1/agents/definitions/{key}` answers 200, or 404 when it is absent, and the body's `key`
must match the path; `DELETE /api/v1/agents/definitions/{key}` answers 200) changes what every user
sees. Do it only when asked (guardrail 8).

## 11. Limits

- Only login is rate-limited. The crew routes are not, but every client shares a small worker pool
  (16 by default) with the WebGUI, so poll gently and never run two pollers for one crew.
- A crew has at most 100 agents and 1,000 tasks, 10,000 bytes per string, 64 dependencies per
  task and 64 tools per agent.

## Where these rules come from

In the agnostic repository, `docs/api/generated/schema.json` is the API as the server itself
describes it (`agnostic api schema` prints the same): every route, body field, query parameter and
vocabulary. Where it and this file disagree, it is right. The decisions are `docs/adr/0006` (the
loopback Host and JSON-only writes), `0008` (tenancy, the cursor listing and the idempotent submit),
`0009` (the event cursor), `0012` (a cancelled crew keeps its results) and `0013` (a crew a restart
interrupted); `docs/architecture/001` says what survives a restart. `scripts/check-skill.py` checks
this file against the schema: every route, method, query parameter and header it uses, every
response example, and each list marked `<!-- schema: … -->`.
