# The HTTP API, described by the binary

[`generated/schema.json`](generated/schema.json) is the output of

```sh
./build/agnostic api schema
```

committed. The binary builds it from the same tables the server dispatches, authorises and decodes
with ([ADR 0015](../adr/0015-the-http-api-is-described-by-a-generated-schema.md)), so it cannot
describe a route, a field or a code the server does not have. **Never edit it by hand.** It needs no
configuration: it reads no `AGNOSTIC_*` variable, opens no store and starts nothing.

## Regenerating it

An API change regenerates the snapshot in the same change, with a CHANGELOG line:

```sh
cyrius build src/main.cyr build/agnostic
./scripts/gen-api-schema.sh            # writes generated/schema.json
./scripts/gen-api-schema.sh --check    # 0 when the snapshot matches the binary, 1 with the diff
```

The script never builds (a build re-provisions `lib/` and may rewrite the lock). `--bin PATH` asks
another binary. It gives the binary 60 seconds: one that does not know `api schema` (from before
0.1.13, or unable to read its arguments) serves instead, and is stopped rather than left to hang CI.
Exit codes: 0 ok, 1 the snapshot differs or the binary failed, 2 usage or no binary.

## What it holds

Top-level keys, in this order:

| Key | What it is |
|---|---|
| `schema` | The document's own format, `1`. Bumped only when the document's shape changes — not the binary's version. |
| `routes` | One entry per method of each route, in the router's resolution order. |
| `bodies` | The request bodies routes take, by name. |
| `headers` | The request headers any request may carry. |
| `errors` | How an error is shaped, the machine-readable codes, and the dispatch ladder. |
| `vocabularies` | Every closed set of words the API reads or writes. |

Each route:

| Key | Meaning | Source |
|---|---|---|
| `method`, `path` | `:name` marks a path parameter. `/ui` and `/ui/` are both listed. | the router's rows |
| `auth` | Whether the route needs a credential when `AGNOSTIC_AUTH=required`. | `agnostic_route_needs_auth` |
| `permission` | `read`, `write`, `admin`, or `null` when it needs none. | `agnostic_perm_for_route` |
| `min_role` | The first role, in the role vocabulary's order, that holds the permission. | `agnostic_role_can` |
| `plugin_permissions` | The plugin permissions that grant the route to a WebGUI plugin (ADR 0007), each `{"name", "self"}` — see below. | `src/webgui/permissions.json` |
| `body` | A key of `bodies`, or `null`. | declared |
| `query` | The query parameters the handler reads, in its order. Any other is ignored. | declared |
| `headers` | Request headers this route's handler reads, beyond the global ones. | declared |
| `ok` | The statuses the route answers with its own body: its successes, and for `/ready` also 503. | declared |
| `response` | `{"kind", "keys"}`: what kind of body it answers with, and an object's top-level keys — see below. | declared |

Each grant in `plugin_permissions` is `{"name": ..., "self": [...]}`. `self` lists the route's path
parameters that the grant pins to **the requesting plugin's own id**, and is `[]` when it pins none.
A plugin holding `storage` may call `GET /api/v1/plugins/:id/data` only with `:id` its own id
(`"self": ["id"]`) — `permissions.json` writes that segment `:self`, and the gate puts the plugin's id
there. Any other parameter of a granted route takes any value. A grant does not reach a disabled
plugin, and auth and the role check still apply after it.

`bodies.<name>.fields` is the decoder's own allow-list, in its order: a key outside it is a 422 that
names it. `bodies.crew.items` says what each element of a crew's `agents` and `tasks` is decoded as.
`bodies.agent_definition.refused` lists fields that are refused with a reason of their own rather
than as unknown. `bodies.plugin_document` is any JSON object of at most `max_bytes`.

`response.kind` is one of three:

| Kind | Body |
|---|---|
| `json` | a JSON object; `keys` are its top-level keys, in the order the handler writes them |
| `html` | a WebGUI page, `text/html; charset=utf-8`; `keys` is `[]` |
| `document` | a plugin's stored JSON document, sent back byte for byte as `application/json` with its revision as `ETag`; `keys` is `[]` |

A trailing `?` on a key marks one a success can leave out: a crew that has not started has no
`started_at`, and a listing's last page has no `next`. A key left out only when the request could not
be served at all — an exhausted arena, a server that never mounted — is not marked. `GET
/api/v1/crews/:id` answers a crew stored by an earlier release exactly as that release wrote it, so
such a crew can lack keys the current server always writes. `/ready` lists 503 in `ok` because "not
ready" is its answer, in the same body, not a refused request (ADR 0001); `GET /api/v1/audit` answers
200 for a broken chain for the same reason, with `bad_index`.

`errors.body.keys` is `["error", "code?"]`: every error has `error`, a message for people; a refusal a
client acts on also has `code`. A trailing `?` marks a key that is not always present. One refusal
carries more: a crew that was accepted but could not start answers `POST /api/v1/crews` with 503
and its `crew_id` and `status` (`failed`) beside `error`, so it can still be polled.
`errors.codes` is the whole code catalogue with each code's status — the server cannot send a code
outside it. `errors.ladder` lists, in order, the refusals made before any handler runs; the first
that applies answers:

| Rung | Status | When |
|---|---|---|
| `body_size` | 413 | the body is over `AGNOSTIC_MAX_BODY_BYTES` |
| `host` | 403 | auth is off and a socket request names a non-loopback `Host` (ADR 0006) |
| `route` | 404 | no route has this path |
| `method` | 405 | the path exists but not with this method |
| `plugin` | 403 + `code` | a request made for a plugin (`X-Agnostic-Plugin`) that is unknown, off, or not granted the route (ADR 0007) |
| `authn` | 401 | auth is on and there is no valid credential |
| `authz` | 403 | the caller's role lacks the route's permission |
| `media_type` | 415 | a socket `POST` or `PUT` that does not declare JSON (ADR 0006) |

## Generated, declared, and left out

- **Generated** — read from a table the server uses, so it cannot drift: routes, auth, permissions,
  roles, plugin permissions and the parameters each pins to the plugin, request allow-lists,
  refused fields, the error codes, and every vocabulary. A vocabulary is walked through its wire
  function until the spelling repeats, so a value appended with its own wire spelling appears
  without the generator being touched.
- **Declared** — written beside the generator in `src/http/schema.cyr`, because the server keeps it in
  handler code rather than in a table: which body a route takes, its query parameters, its headers,
  the global headers, the ladder, and what each route answers — its success statuses, and its
  response's kind and top-level keys. `tests/api_schema.tcyr` drives each declaration through the
  dispatcher (`api/probes`, `api/errors`), and every route's success path through the real mount
  (`api/responses`).
- **Left out on purpose** — the binary's version (the snapshot would change every release), anything
  read from `AGNOSTIC_*`, the permissions' `grants` wording, plugin manifests, per-handler 4xx
  statuses and messages (the route modules' "Route | Codes" headers and `state.md` keep those),
  field types and required-ness, nested response shapes, and response headers other than a
  document's `ETag`.

## How it is checked

| Check | What it runs | Catches |
|---|---|---|
| `tests/api_schema.tcyr`, `api/snapshot` | the generator compiled fresh from `src/` | any API change not regenerated into the snapshot; key order counts |
| the rest of `tests/api_schema.tcyr` | the dispatcher, the decoders, the parsers, the plugin gate | a declaration that is not true; a `permissions.json` route the router does not have; a grant's `self` the gate does not enforce; a command's exit code or stream (`api/cli`) |
| `tests/api_schema.tcyr`, `api/responses` | `agnostic_serve_mount` with auth required, and every route's success path | a status outside `ok`, a body of another kind, a key missing or not declared — and the other way, a declared status or key the sweep never sees |
| `gen-api-schema.sh --check` in CI | the shipped DCE binary, `agnostic api schema` | a broken argument path; compares parsed JSON, so formatting does not count |
| "Command line exit codes" in CI | the shipped DCE binary, `help` and an unknown argument | `src/main.cyr`'s dispatch: 0 with usage on stdout, 2 with usage on stderr and nothing on stdout |
| `scripts/check-clean.sh` | the same, when `build/agnostic` is newer than `src/` | the same, locally; it never builds, so before CI's build it skips |

The suite reads the snapshot relative to the working directory: `cyrius test` runs at the
repository root, as CI does.

The snapshot also has a reader: `scripts/check-skill.py` (in `check-clean.sh`, 0.1.13) holds
[`skills/agnostic/SKILL.md`](../../skills/agnostic/SKILL.md), the Agent Skill for driving this API,
to it — every route, method, query parameter and header the skill uses, its response examples' keys,
and the lists it marks. A snapshot change that fails there means the skill needs the same change.

## Known gaps

- The declared parts are checked one way: a declaration that is false fails, but a query parameter
  or header a handler starts reading without declaring it is caught only when it is one of the six
  parameter names the suite knows (`limit`, `status`, `before`, `after`, `explain`, `task`) on a GET
  route.
- No field types or required-ness, no nested response shapes, and no machine-readable code for the
  422 refusals (unknown or refused field): they live in decoder code, not in a table. So the shape of the
  plan's per-task `selection` and the types of a task's selection hints (0.1.14) are documented in
  SKILL.md and ADRs 0016–0017; the schema lists the hints' names and `complexity`'s values.
- Response keys are declared, not read from the handlers. `api/responses` checks them both ways, but
  only on the answers it drives: a key a handler writes only in a state the sweep does not reach
  would not be seen.
- It compares a body's keys as a set, so it does not see a key written twice. A live crew's `GET`
  carries `engine_mode` twice today (roadmap).

## Stability

Before 1.0, a snapshot change is an ordinary change with a CHANGELOG line. From 1.0, removing or
renaming anything in the snapshot needs an ADR and a **Breaking** CHANGELOG entry; adding is a
minor change.
