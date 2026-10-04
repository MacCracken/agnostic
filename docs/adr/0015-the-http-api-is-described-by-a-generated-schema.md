# 0015 — The HTTP API is described by a schema generated from the server's own tables, and a snapshot freezes it

**Status**: Accepted
**Date**: 2026-10-04

## Context

The v1.0 criterion "public API frozen" (roadmap) was a promise nothing checked. The surface it
covers was spread across the code, and parts of it were not data at all:

- **Routes.** Until 0.1.13 the resolver, `agnostic_route_resolve_a`, was an if-chain of 21 literal
  patterns, though its header called it "a flat table". Nothing outside it could list the routes.
- **Permissions.** The role and permission table is in `src/auth/perm.cyr`.
- **Request fields.** Five request allow-lists live in four modules, and the agent definition has
  12 refused fields, which were an if-chain.
- **Error codes.** Four machine-readable codes were string literals at five call sites.
- **Plugin vocabulary.** `src/webgui/permissions.json` holds a third copy of the route strings.
- **Responses.** About twenty handlers assemble their bodies by hand from about 119 interned keys.

The human-readable descriptions are the route table in `state.md` and each route module's
"Route | Codes" header. People keep them, and they agree only through care. ADR 0007 already
records one place where the copies drift silently: a route renamed in the router but not in
`permissions.json` stops being granted, and nothing says so.

herdr's `api schema --json` (research note 2026-10-03, item H5) shows the alternative: the binary
describes itself, and a snapshot test turns "frozen" into a diff.

## Decision

**`agnostic api schema` prints a JSON description of the HTTP API, built from the same tables the
server dispatches, authorises and decodes with. `docs/api/generated/schema.json` is that output,
committed. `tests/api_schema.tcyr` fails when the two differ, and CI checks the shipped binary
against it too.**

It landed in four changes, all in 0.1.13.

1. **The route table is data** (no behaviour change). Rows of a pattern and the route id it
   resolves to for GET, POST, PUT and DELETE, walked in the same order with the same 404/405 split
   and captures. The schema reads the same rows (`agnostic_route_row_pattern` / `_row_id`).
2. **The catalogues are closed** (no wire change). The error codes are `AgnosticErrorCode`, and
   `agnostic_response_error_code_a` takes a member: a value the catalogue does not list answers 500
   with no `code`, so the server cannot send a code the schema does not list. The refused agent
   fields are a table of rows. `agnostic_method_name` and `agnostic_perm_name` name what the schema
   emits.
3. **The generator, the command, the snapshot and its checks.**
   - `src/http/schema.cyr` builds the document; `src/cli.cyr` is the binary's first argument
     handling.
   - **Generated, so it cannot drift:** each route's method and path, whether it needs
     authentication, its permission, the first role that holds it, and which plugin permissions
     grant it — each with the path parameters it pins to the requesting plugin's own id
     (`"self"`; `storage` pins `:id`, which `permissions.json` writes `:self`), so the schema
     never says a grant reaches further than the gate lets it; the request allow-lists, read
     from the decoders' own functions; the refused agent fields; the error-code catalogue; and
     the vocabularies — roles, permissions, process, priority, risk, crew status and its filter,
     plugin permission names. A vocabulary is walked
     through its `*_to_wire` until the spelling repeats, so a value appended with its own arm
     (crew status `interrupted`, ADR 0013) is listed without touching the generator.
   - **Declared beside the generator, and checked by probes:** which body each route takes, its
     query parameters, its route-specific headers, the headers any request may carry, and the
     dispatch ladder's rungs. `tests/api_schema.tcyr` drives each declaration through the
     dispatcher: an unknown key and each declared field per body; an invalid value per query
     parameter and header; each rung it can reach without a stored identity, and their order.
   - **Excluded on purpose:** the binary's version (it would change the snapshot every release),
     anything read from `AGNOSTIC_*`, the permissions' `grants` wording, plugin manifests,
     per-handler 4xx statuses and messages, field types and required-ness, and nested response
     shapes.
   - **The document is whole or it is not printed.** Every builder answers its container or 0, so
     a failed allocation or a name a lookup lacks fails the command (exit 1) rather than printing
     a plausible `null`.
4. **What each route answers.** Each route gains `ok`, the statuses it answers with its own body,
   and `response`, `{"kind", "keys"}`: `json` with the object's top-level keys in the order the
   handler writes them, `html` for a WebGUI page, or `document` for a plugin's stored document sent
   back verbatim with its `ETag`. A trailing `?` marks a key a success can leave out; a key left out
   only when the request could not be served at all is not marked. `/ready` lists 503: "not ready"
   is its answer, in the same body (ADR 0001).
   - **Declared, because no table holds them.** About twenty handlers build their bodies by hand
     from interned keys. Routing every body through a table the schema could read would rewrite
     each handler — a larger and riskier change than the surface it describes. So the keys are
     declared beside the generator, and a route with no declaration fails the document (exit 1)
     rather than printing an empty one.
   - **Checked both ways, on the real mount.** `api/responses` runs `agnostic_serve_mount` with
     auth required and a bootstrap administrator, logs in, and drives every route's success path:
     each answer must have a status `ok` lists, be of its kind, hold every key not marked optional,
     and hold no key undeclared. Then the other way: every route must have been driven, and every
     status and every key it declares — optional ones included — seen at least once. The sweep
     reaches the rarer answers on purpose: a replayed submit, a second page, a parallel crew's
     plan, every preset, a crew a restart interrupted (seeded before mount), a trail altered on
     disk (`bad_index`), and a failing readiness check (`/ready`'s 503).

**The binary reads its arguments**, for the first time, before the environment:

- no arguments: it serves, exactly as before;
- `api schema`: it prints the schema and exits 0 — an invalid `AGNOSTIC_PORT` neither changes it
  nor stops it;
- `help`, `--help`, `-h`: usage, exit 0;
- anything else: usage on stderr, exit 2. Exit codes are 0 ok, 1 failure, 2 usage error (herdr's).
  `api/cli` runs each command against two files and checks the code and what went where; CI runs
  `help` and an unknown argument on the binary, which alone has `main`'s dispatch.

**Updating the snapshot is a deliberate step**, `scripts/gen-api-schema.sh`, which never builds.
Before 1.0 a snapshot change is an ordinary change with a CHANGELOG line. From 1.0, removing or
renaming anything in it needs an ADR and a Breaking entry (first-party documentation standard,
`docs/api/`).

**Three checks, each reaching what the others cannot:**

- `api/snapshot` compiles the generator fresh and compares its text with the snapshot re-printed
  through the same bayan — a stale binary cannot fool it, and key order counts.
- `gen-api-schema.sh --check` runs a binary — the real argument path — and compares parsed JSON, so
  a bayan formatting change arriving with a toolchain bump is not reported as an API change. CI
  runs it on the DCE binary right after the build. It stops the binary after 60 seconds: one that
  does not answer `api schema` serves instead, and would otherwise hang CI.
- `scripts/check-clean.sh` runs the same when `build/agnostic` is newer than src/. It never builds,
  and it runs before Build in CI, so there it skips.

## Consequences

- **Positive**
  - Every API change appears as a diff in review, in one file.
  - A route nobody classified shows up as `admin` in that diff, not only in a refusal.
  - Every route `permissions.json` grants is now checked against the router
    (`api/plugin-vocabulary`), which closes ADR 0007's silent rename from both sides.
  - Consumers get a machine-readable surface they can ask the binary for: the SKILL.md (H6), M7's
    MCP work, scripts.
  - The four error codes are a closed set the server cannot step outside.
- **Negative**
  - Every API change must regenerate the snapshot (`./scripts/gen-api-schema.sh`) in the same change.
  - The declared parts are hand-written. The request side is verified in one direction only: a
    query parameter or header a handler reads but the schema omits is not caught — except that
    every GET route is driven with each known parameter it does not declare and must answer the
    same. Response keys are verified both ways, but only on the answers the sweep drives.
  - The binary now has an argument surface. An invocation that passed arguments it relied on being
    ignored exits 2; none is documented.
  - `args_init` reserves 2 MiB of bump memory at start (the stdlib reads `/proc/self/cmdline` into
    `ARG_MAX`); only the pages it touches are committed.
- **Neutral**
  - An OpenAPI document could be generated from this one later.
  - Field types, nested response shapes, a machine code for the 422 refusals and per-handler 4xx
    statuses are recorded as roadmap follow-ups.
  - One refusal carries more than `error` and `code`: a crew accepted but unable to start answers 503
    with its `crew_id` and `status`. `docs/api/README.md` says so; the schema's error body does not.

## Alternatives considered

- **A hand-written schema or OpenAPI file.** Rejected: a fourth copy of the surface, kept in step by
  care — the problem this ADR exists to remove.
- **OpenAPI 3.1 now.** Rejected: field types and required-ness are not in any table, so emitting them
  would mean declaring them by hand.
- **A test-only generator with no command.** Rejected: the shipped binary should be able to describe
  itself, to agents and to CI, and a CI step on the binary exercises the real argument path.
- **Leave the resolver an if-chain and list the patterns separately for the schema.** Rejected: that
  is the duplicate again.
- **Response keys from a table the handlers build their bodies with.** Not now: it would rewrite
  every handler, and an optional key's condition would still live in handler code. The declaration
  is a copy, but `api/responses` checks it against the handlers in both directions, so it cannot
  drift unnoticed on any answer the sweep drives.
- **Index the router, as agnosai's two-level prefix index does.** Not needed: the flat table is
  measured cheap (router header), and an index is a separate decision.
- **Compare the snapshot byte for byte everywhere.** Rejected for the binary check: a bayan
  formatting change would fail it with no API change. The suite re-prints both sides through the
  same bayan instead, which keeps key order significant without depending on formatting.
- **Bound each vocabulary by its highest constant.** Rejected: an appended value would need the
  generator edited too, and forgetting it would drop the value from the schema silently. The walk
  stops where the wire function repeats, and gives up (failing the document) after 64.
