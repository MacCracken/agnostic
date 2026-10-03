# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [0.1.12] — 2026-10-03

**Re-pin to agnosai 2.1.4.** The build prints no warning on code, down from five at 0.1.11:
agnosai 2.1.4 brings ai-hwaccel 2.4.1, which renames the three deprecated getter calls, and
`src/server/serve.cyr` declares its `body` local `: i64`. agnosai 2.1.4 also brings kavach 3.13.2,
whose sandbox behaviour changes reach agnostic's crews through agnosai. The one agnostic source
change is two lines in `serve.cyr`.

**29 suites, 1,885 assertions, 0 failed**, on x86_64 under the 6.6.14 pin and **natively on
aarch64** (a Raspberry Pi, Ubuntu 26.04).

### Changed

- **`[deps.agnosai]` 2.1.3 → 2.1.4.** It moves agnosai to kavach 3.13.2 and ai-hwaccel 2.4.1, both
  on cyrius 6.6.14, and changes no agnosai source but its version literal. Through it:
  - wasmtime runs under kavach's exec seccomp filter;
  - the process capture cuts a payload off at 1 MiB of stdout with SIGPIPE, keeps each result's
    stderr, and takes its payload down with it;
  - OCI runs take the config's deadline and stdin.
- **`src/server/serve.cyr`: `var body: i64 = str_from("")`.** `body` was typed `Str` by its
  initializer, then took `agnostic_response_body(resp)` and `rendered`, which return an untyped
  `i64` ("assigning non-pointer to typed pointer", twice). The values stored are the same; agnosai
  2.1.3 made the same fix.
- `lib/agnosai.cyr`, `lib/kavach.cyr` and `lib/ai-hwaccel.cyr` are byte-identical to their tags'
  dists, and nothing else in `lib/` moved. `cyrius.lock` holds 119 files and 9 commit pins:
  agnosai 2.1.4, kavach 3.13.2 and ai-hwaccel 2.4.1 are new, and libro stays at 2.10.6, its
  latest. The binary is 6,136,064 B, 4,144 B more than 0.1.11, which is kavach's new code.
- **Certified the CI way:** in a replica with no sibling checkouts and an empty dep cache,
  `lib sync --full` + `deps` from an empty `lib/` reproduced `lib/` and `cyrius.lock` byte for
  byte, and every CI step passed there.

### Docs

- **Roadmap.**
  - The five warnings found at 0.1.11 are fixed.
  - The 0.1.9 agnosai follow-ups point to agnosai's roadmap B17, and the sandhi chunk-send item
    to its filing with sandhi.
  - The libro ranged read points to libro's roadmap.
  - "Found at 0.1.12" records the kavach issue that reaches crews on a uutils host: Ubuntu's
    pinned exec of coreutils exits 1.
- **The 2026-10-03 review of directions and gaps.**
  - It adds `docs/development/research/2026-10-03-herdr-and-multi-agent-landscape.md` and the
    roadmap items it recorded: M6, M7, M9 and a section of its own.
  - Its next release, planned as 0.1.12, is renumbered 0.1.13, since 0.1.12 is this re-pin.

## [0.1.11] — 2026-10-03

**Re-pin to agnosai 2.1.3 and libro 2.10.6.** The 161 warnings agnosai's bundle printed in every
build here are gone, and every commit pin the lock records on a folded module now names the
bytes `lib/` holds. No agnostic source change.

**29 suites, 1,885 assertions, 0 failed** (x86_64, under the 6.6.14 pin).

### Changed

- **`[deps.agnosai]` 2.1.2 → 2.1.3**, which closes the three agnosai follow-ups recorded at
  0.1.10. Its bundle no longer calls the deprecated `bayan_json_v_obj_get` (153 sites). It no
  longer passes `str_data(path)` to `file_open`'s `cstring` (2 sites, where a path cut from a
  longer one opened the longer file). And it no longer assigns untyped values to `Str`-typed
  locals (6 sites). It declares sigil 3.13.7, the 6.6.14 fold, so the lock's sigil line now names
  the commit `lib/sigil.cyr` holds; at 0.1.10 it named 3.13.5. bote arrives through it at 3.3.16.
- **`[deps.libro]` 2.10.5 → 2.10.6**, libro's latest: sigil 3.13.7 and cyrius 6.6.14, with no
  source change. `dist/libro.cyr` differs from 2.10.5's only in its version header.
- `lib/agnosai.cyr`, `lib/bote-core.cyr` and `lib/libro.cyr` are byte-identical to their tags'
  dists, and nothing else in `lib/` moved. `cyrius.lock` holds 119 files and 9 commit pins.
- The build prints five warnings on code, none new: ai-hwaccel 2.4.0's three deprecated getter
  calls (in its own bundle) and two in `src/server/serve.cyr`, now recorded on the roadmap. The
  binary is 6,131,920 B, as at 0.1.10. The aarch64 cross-build compiles; the suites were not
  re-run natively on the Pi for this re-pin.
- **Certified the CI way**: in a replica with no sibling checkouts and an empty dep cache,
  `lib sync --full` + `deps` from an empty `lib/` reproduced `lib/` and `cyrius.lock` byte for
  byte, and every CI step passed there.

## [0.1.10] — 2026-10-02

**Views over the real surface, and aarch64 is back** — Crews, Library and Audit trail as first-party
plugins that link to each other and to Swarm Command, one bridge client every plugin carries, a
cancelled crew that keeps its finished work, and Cyrius 6.6.14 with the aarch64 release artifact
restored after every suite and the server ran natively on a Raspberry Pi 4.

**29 suites, 1,885 assertions, 0 failed** — on x86_64 and natively on aarch64 — plus **61 JavaScript
tests** under Node, and 41 checks in headless Chromium against a live server.

### Added — three views over the real surface (M9)

- **Crews** (`crews`, `data: live`): every crew in your tenant, newest first, a page at a time,
  filtered **All · Active · Completed · Failed · Cancelled** by the server. A crew opened shows its
  plan, its progress as it happens (by cursor, gaps said out loud), each task's result with the
  tokens, cost and time it used, and the crew's totals — tokens only when metered, cost only when
  priced, a placeholder run labelled as one. **Cancel**, for a role that may write; **Watch in Swarm
  Command** for the same crew on the map.
- **Library** (`library`, `data: live`): the preset crews built in (their agents, roles, goals,
  tools, backstories) and the agent definitions stored here — create, edit, delete, or **save a
  preset's agent as a definition**.
- **Audit trail** (`audit`, `data: live`, ADMIN): whether the hash chain verified at start-up, how many
  entries it holds and how many appends were dropped, and its newest entries — filterable by severity
  and text, each with its hash and whether it names the entry before it.
- Like every plugin they start **OFF** (ADR 0004); Settings switches them on.

### Added — views link to each other through the shell (ADR 0010)

- A view's state is in the shell's URL, **`#plugin/<id>?<params>`** — `/ui#plugin/crews?crew=<uuid>`
  is a link to a crew. `init` carries the view's `params` and the `views` switched on; a plugin asks
  the shell to open another view (or itself, with new params) with **`agnostic:navigate`**, and is
  told when its own params change with **`agnostic:params`**, without a reload. Feature `navigate`.
  The shell checks every navigate (`AgnosticBridge.checkNavigate`, tested under Node): only
  `overview`, `settings` or a plugin that is switched on; params at most 256 of `[A-Za-z0-9._~=&%:-]`.
- **Swarm Command 0.4.0** follows `#plugin/swarm?crew=<uuid>` — it watches that crew — and its Crews
  list links each crew to the Crews view (**DETAILS**).

### Added — one bridge client (ADR 0010)

- **`src/webgui/kit/host.js`** is the plugin side of the bridge — `class Host` and `errOf` — and every
  plugin page carries it verbatim between `agnostic-kit:host` markers. `scripts/gen-webgui.sh` refuses
  a page whose copy differs by a byte, or that asks the server for anything without carrying it;
  **`--sync-kit`** rewrites the copies. Swarm Command now carries it instead of its own.

### Added — server

- **`GET /api/v1/crews?status=`** — `pending`, `running`, `completed`, `failed`, `cancelled`,
  `unknown`, or `active` (pending or running) — applied before the page is cut, so a filtered page is
  full and its `next` continues the filter. Anything else is 422.
- **`GET /api/v1/audit/entries?limit=&before=`** (ADMIN): the trail's newest entries, newest first —
  `index` (position in the chain), `timestamp`, `severity`, `source`, `action`, `details`, `hash`,
  `prev_hash` — with `total`, `oldest_held` and a `next` cursor. Read from the newest 1024 entries,
  kept in fixed slots seeded at open and filled as each entry is persisted (ADR 0011): libro reads only
  the whole store, into a heap with no `free()`.
- **Two permissions** in `src/webgui/permissions.json`: `definitions:write` (create, replace, delete
  definitions) and `audit:read` (`GET /api/v1/audit` and its entries). A permission is the plugin's
  limit, never more than its user's role.

### Fixed — cancelling a crew no longer loses its finished work (ADR 0012)

- A crew cancelled while tasks ran was latched CANCELLED with no results, and the engine's later
  report — the results of the tasks that finished, and what they cost — was refused by the terminal
  latch. Now a stored CANCELLED with no results takes a terminal observation's results **once**
  (status, reason and finishing time unchanged), and the stored outcome and its listing row are
  rewritten once to carry them. The collector picks them up unwatched.

### Changed — Cyrius 6.6.12 → **6.6.14**, and the aarch64 release artifact is restored

- **aarch64 is released again.** Withheld since 0.1.7 because the binary died with SIGBUS at startup
  (cyrius did not align the global after a typed array); 6.6.13 aligns every global (I9, filed by
  0.1.7). Every suite (29, 1,885 assertions) and the DCE release binary itself — health, readiness,
  a crew submitted, listed (filtered) and read, the audit entries, the WebGUI and its four plugin
  pages — ran **natively on a Raspberry Pi 4**. `cross_bins`, the release step, the asset and
  checksum lines, and CI's upload are back.
- **Certified the CI way**: in a replica with no sibling checkouts and an **empty** dep cache,
  `lib sync --full` + `deps` from an empty `lib/` reproduced `lib/` and `cyrius.lock` byte for byte,
  and `check-symbols`, `check-clean` and both DCE builds passed. Every stdlib file is byte-identical to
  `git show 6.6.14:lib/<mod>`; the nine commit pins did not move.
- 6.6.14 folds **sigil 3.13.7** (6.6.12 folded 3.13.5); patra stays 1.15.1. `lib/` and the lock are
  re-provisioned (112 snapshot files, 119 locked, 9 commit pins); `lib/math.cyr` no longer defines the
  `f64_le` / `f64_ge` / `f64_trunc` builtins 6.6.13 reserved.
- `bayan_json_v_obj_get` is deprecated in bayan 1.5.11: agnostic's four calls (`src/auth/jwt.cyr`)
  and the suite's use `bayan_json_v_obj_get_by_cstr`.
- **sigil 3.13.6+ installs a crypto block only on a thread that has none**, so mount's
  `crypto_tls_main_init()` now leaves a main thread alone when `main` already gave it one — which
  agnostic's does. `serve/mount-crypto-main-thread` asserts the new contract (settled: sigil installed
  main's block, or can read the one main has) instead of the old flag value; the worker-keeps-its-TLS
  regression it guards still passes. The call stays, for x86 kernels before 5.9, where the thread
  pointer cannot be read.
- `cyrius.cyml` notes: a `[deps.X]` without `modules` now means `dist/X.cyr` or warns (I10, filed by
  0.1.7) — such a block is an override pin, which this repo does not carry.

### Recorded — agnosai follow-ups (release agnosai, then re-pin)

- agnosai 2.1.2's dist still calls the deprecated `bayan_json_v_obj_get` and passes `Str`s where 6.6.14
  wants a `cstring` (`file_open(str_data(...))` at `lib/agnosai.cyr` 8017 / 30392): warnings in every
  build here. And it declares sigil 3.13.5 where 6.6.14 folds 3.13.7 — harmless (the fold wins and
  `lib/` is the fold's bytes), but the lock's sigil line names a commit that is not what `lib/` holds.

## [0.1.9] — 2026-10-02

**The plugin platform is checked by the server, and Swarm Command runs on real numbers** — a crew's
real tokens and cost, its progress read by cursor and collected without a poller, crews that belong
to their tenant and can be listed and watched, document revisions, and idempotent submits.

**29 suites, 1,749 assertions, 0 failed**, plus **30 JavaScript tests** under Node
(`tests/webgui/`, new). Cyrius, agnosai and every dependency are unchanged from 0.1.8; `lib/` and
`cyrius.lock` are byte-identical to it.

### Added — real usage on every crew (the engine metered it; agnostic dropped it)

- Each result carries **`usage`** — `model`, `provider`, `prompt_tokens`, `completion_tokens`,
  `total_tokens`, `cost_micro_usd` (only when the gateway priced the call — an absent cost is never a
  zero one), `duration_ms` — and a failed call its **`error`**, picked by name out of the engine's
  result metadata. The crew carries the totals: `usage` with `metered_tasks` and `costed_tasks`, so a
  partial cost says it is partial. A placeholder task reports its duration and no tokens.
- `GET /api/v1/crews/{id}` and the stored outcome also carry `name`, `scope`, `process`,
  `tasks_submitted`, the `engine_mode` the crew **ran** under, and `submitted_at` / `started_at` /
  `finished_at` (epoch ms).
- The 202 carries **`task_ids`** — the engine's id for each task, in request order — and
  **`GET /api/v1/crews/{id}/plan`** (READ) describes any crew the ledger holds: its agents, and its
  tasks with ids, descriptions, priorities and dependency indices. A client binds events by id.

### Added — crew progress is collected by the server and read by cursor (ADR 0009)

- **A collector thread** keeps every live crew current every 200 ms — drains its events, reads the
  engine, latches, persists a terminal outcome. Before 0.1.9 a crew moved only when polled: an
  unwatched crew lost events past the engine's 256-event queue, and **a crew that finished unpolled
  was not durable** — a restart lost its outcome.
- **Every event is numbered (`seq`) and timed (`at_ms`)**; `GET /crews/{id}/events?after=N` answers
  only what is new, with `next`, `missed` (overwritten before you read it) and `lost_events` (dropped
  before it was numbered). Without `after`, the whole window, as before.
- **`running` is reported** once `crew_started` is collected — the engine's registry never says it.

### Added — crews belong to their tenant; a listing; idempotent submits (ADR 0008)

- **`GET /api/v1/crews`** (READ): the caller's crews, newest first — running ones from the ledger,
  finished ones from a durable index (`agnostic_crew_index`) — with status, times, task count, engine
  mode, tokens and cost. `?limit=` (1–200, default 50) and `?before=<next>` page by cursor.
- **`Idempotency-Key`** on `POST /api/v1/crews`: a repeat with the same key in the same scope answers
  the crew it started (202, `"replayed": true`); the same key over another body is a 422.

### Changed — ⚠ breaking: a crew is invisible to every other tenant

- GET, cancel, events and plan answer **404** for a crew of another scope, exactly as for one never
  submitted. Before 0.1.9 any user holding a crew's id could read it, and an operator cancel it. A crew
  stored before 0.1.9 has no scope and belongs to `_` (users without a tenant, or auth off); it is not
  listed, though `GET /crews/{id}` still answers it there.

### Added — the plugin platform, checked by the server (ADR 0007)

- **One permission vocabulary, `src/webgui/permissions.json`**: each permission's words and routes.
  The generator validates manifests against it and embeds it; the server parses it at mount; the shell
  reads it from `GET /api/v1/plugins` (`catalogue`). A new permission was four edits; it is one.
- **The plugin rung**: every request the shell makes for a plugin carries `X-Agnostic-Plugin`, and the
  server refuses it — before authentication — unless the plugin is built in, **switched on**, and
  granted the route: `403` with `code` `plugin_unknown`, `plugin_off` or `plugin_forbidden`. A plugin
  switched off elsewhere stops working in every open view on its next request, and the shell leaves it.
- **Plugin documents have revisions**: an `ETag` on GET and `etag` on PUT (the first 64 bits of the
  document's SHA-256); `If-Match` on PUT/DELETE and `If-None-Match: *` on PUT, checked under the store
  lock in the same step as the write — **412** otherwise.
- **The shell's bridge**: its gate is a pure script (`window.AgnosticBridge`) built from the catalogue
  and tested under Node; it answers only the page session that asked (a reply after a reload, or after
  another plugin took the frame, is dropped — the frame's window object does not change, so `e.source`
  could not tell them apart); it accepts messages only from an opaque origin; it caps a plugin at 16
  requests in flight (429); it carries query strings, `ifMatch` / `ifNoneMatch` (and answers `etag`)
  and `idempotencyKey`, announced in `init.features`; and `init` is sent once per `hello` (the plugin
  loaded its library twice).

### Changed — Swarm Command 0.3.0: a working plugin, not a demo

- **What a live crew really cost**: the summary shows the tokens agnostic metered and the cost the
  gateway reported (n/a when it reported none — never a simulated number), beside the simulator's
  estimate and how the two compare; the top bar shows ≈ tokens and n/a cost while the crew runs and
  the metered numbers when it ends. **Results** shows every task's output, with its model, tokens,
  cost and time, and downloads them as Markdown or JSON.
- **Crews**: the launcher lists every crew of your tenant and watches any of them — bound through the
  crew's own plan, titled from it, played at its real pace (`at_ms`). A crew from before the server's
  last restart is shown from its outcome.
- **Reading a crew**: by cursor, one poll at a time (two used to race and could double a crew's
  output), bound to tasks by engine id — duplicate titles and out-of-order waves no longer cross
  outputs; a parallel crew shows no more tasks at work than its concurrency limit. Losing contact
  (no answer, 401, 403) **pauses** the watch and a sign-in resumes it — it used to record the crew as
  *lost* after six misses. Polling slows to 5 s while the view is hidden.
- **Submitting safely**: the run is recorded on its swarm **before** the crew is submitted, with an
  `Idempotency-Key`; no answer is retried with the same key, and a submission never answered is
  *unconfirmed* — not *refused*, and not resubmitted. Leaving mid-submission asks first, and the crew
  is recorded either way.
- **Swarms that cannot be lost**: every save carries the swarm's revision. A background record (a run,
  an estimate) is applied to the latest copy and retried on a conflict; an editor save that would undo
  another tab's change asks — overwrite, save as a copy, or keep editing. Writes to one swarm queue.
  Editor saves keep 4 KB for run records; an oversize record trims old simulations first. Live runs and
  simulations are capped apart (20 and 10). Write failures are shown, not logged. A swarm from a newer
  Swarm Command is read-only; viewers can open, simulate and estimate, not change.
- Gone: the `WebSocketSource` stub, the "prototype" label, and every place that said agnostic does not
  report cost.

### Added — tests for the WebGUI's JavaScript

- `tests/webgui/` (`node --test`, Node 20+): the shell's bridge gate against the real vocabulary (8),
  and Swarm Command's simulator, specs, library and live crew source against a fake agnostic that
  answers as 0.1.9's server does (22). `scripts/check-webgui-js.sh`, run by `check-clean.sh`.
  Mutation-checked: a gate that grants everything, and binding a crew's tasks by text, each fail a named
  test. Until now this logic was tested once, by hand, and the tests were discarded.

### Fixed

- **The crew event window leaked.** Past 256 events every new event copied the other 255 into a new
  vec, never freed. It is a ring now; `tests/ledger.tcyr` asserts a drain allocates nothing (a per-event
  allocation fails it).

### Verified

- In headless Chromium over CDP, against servers running real crews through a stand-in LLM gateway that
  prices calls: auth off (29 checks — the bridge features, a live crew from submit to metered cost,
  results, the run record, watching it again, the Crews list and a crew from a script, a two-tab
  conflict, switching the plugin off under an open view) and auth required (13 — sign-in, the admin
  switch, catalogue words in Settings, the token out of the plugin's reach, a session invalidated
  mid-crew pausing and resuming the watch), and the standalone page (7). No uncaught exception in
  either frame. Over the socket with curl: every new route and header.
- `tests/agnostic.bcyr` benches what 0.1.9 adds: the plugin rung ~1.2 µs per bridged request; copying
  one new event out of the ring ~0.12 µs, a whole 256-event window ~5.7 µs; the route table (19 paths)
  ~0.10 µs first, ~0.87 µs last, ~0.73 µs miss, ~2.0 µs for the two-capture path.

### Known — recorded, not fixed here

- **Cancelling a crew loses the results its finished tasks already produced** (the ledger latches
  CANCELLED with none, and the engine's later state with them is refused by the latch). Outputs that
  arrived as events are still shown. Roadmap.
- agnosai: a parallel or DAG crew publishes `task_started` for a whole wave before it runs and
  `task_completed` only after every batch, with no `token` events; `agent_cost_usd` is always empty.
  Roadmap, as agnosai follow-ups.

## [0.1.8] — 2026-10-01

**Swarm Command becomes a working tool** — saved swarms with every capability editable, cost
estimates from headless simulations, and live runs as real crews — on a **plugin platform**: the
host bridge with manifest permissions, plugin documents per tenant, and transport hardening.

**28 suites, 1,522 assertions, 0 failed**. Cyrius, agnosai and every dependency are
unchanged from 0.1.7; `lib/` and `cyrius.lock` are byte-identical to it.

### Added — the plugin host bridge (ADR 0005)

- A plugin page has **no network of its own** (`connect-src 'none'`). It asks the shell by
  `postMessage` — protocol 1: `agnostic:hello` / `init` / `request` / `response` — and the shell
  answers only what the plugin's manifest **`permissions`** grant (`storage`, `presets:read`,
  `definitions:read`, `crews:read`, `crews:write`), with the signed-in user's credential, which
  the plugin never sees. Anything else is 403 from the shell, a malformed path 400; a 401 opens
  sign-in. `init` tells the plugin the auth mode, whether the user is signed in, and their role.
- `plugin.json` gains `permissions` — validated by `gen-webgui.sh` against that closed list,
  carried by `GET /api/v1/plugins`, and spelled out under each plugin in Settings — and `data`
  gains `"mixed"`: a view that labels each mission simulated or live itself.

### Added — plugin documents, per tenant

- `GET /api/v1/plugins/{id}/data` (READ: keys, update times, sizes) and
  `GET|PUT|DELETE /api/v1/plugins/{id}/data/{key}` (READ / WRITE / WRITE). A document is one JSON
  object of at most 32 KiB, stored and answered verbatim; at most 256 per plugin per tenant (507);
  keys `[a-z0-9][a-z0-9._-]*`, at most 64. `PUT` is an upsert (201 / 200, `created`); writes and
  deletes are audited. The tenant is the caller's, `_` with auth off. A plugin need not be switched
  on for its documents to be read or deleted. `src/engine/plugindata.cyr`,
  `src/routes/plugindata.cyr`; the router matches two path captures.
- Settings shows each plugin's stored documents, with **Delete all** for users who may write.
- `src/http/codec.cyr`: a non-allocating JSON validator (`agnostic_json_kind`; strict UTF-8,
  depth ≤ 64) decides whether a body is an object before anything is stored.

### Added — Swarm Command 0.2.0: swarms you keep, price and run

- **A launcher** in place of the scenario picker: your swarms (on the server, per tenant; in this
  browser when the view is opened in its own tab), the templates (a quick demo, or **Customize**
  into a new swarm), import and export as files, duplicate, delete.
- **An editor with a default for everything**: Mission (objective, seed, workload scale) · Agents
  (per-role caps, thinking speed, tool use, the goal a live crew gets; a swarm-wide cap, spawn rate,
  idle release) · Models & tools (a priced catalogue, per-role and on-Local models, tool latency and
  tokens, each role's tool mix) · Compute & budget (regions on or off, caps, $ per agent-second,
  speed, a compute price multiplier) · Tasks (generated by the template, or customized: keys,
  dependencies, work, kind, priority, fan-out, rework) · Failure model · Live run (one agent per role
  or a preset's agents, the process, model ids, and the exact request it will submit). Reset any tab
  to defaults; errors block saving, warnings explain.
- **Estimate**: the swarm simulated eight times, headless, on different seeds — cost p50 and range,
  duration, tokens, peak agents, failed tasks, runs over budget, stalls — stored on the swarm and
  marked stale when its settings change.
- **The simulator runs the spec**: its models and prices, tools, regions, caps and failure model.
  Role and swarm-wide caps cannot deadlock (a lead coordinating its sub-agents holds no slot, and
  waits for one to finish its own part); the orchestrator no longer takes one of Local's slots; a
  headless run that stops progressing is ended as stalled. With default settings the cost
  distribution matches 0.1.7's.
- **Run live**: the swarm's tasks submitted to this server as a crew, after a confirmation that says
  what that means; its events polled through the bridge and played onto the map (a unit per running
  task), its outcome read at the end; **Cancel crew**; leaving a running crew asks first. Runs are
  recorded on the swarm — and a crew left running is caught up from the server — and **Watch** plays
  an earlier crew again.
- **Every mission says what it is**: SIM or LIVE in the top bar and on the summary. A live crew's
  cost is shown as n/a — agnostic does not report it — never as a simulated number.

### Changed — ⚠ breaking: JSON-only writes, and a loopback Host when auth is off (ADR 0006)

- **Every POST and PUT must carry `Content-Type: application/json`** (or `application/<x>+json`),
  even with no body — **415** otherwise. Scripts: add `-H 'Content-Type: application/json'`.
- **With `AGNOSTIC_AUTH=off`, a request whose `Host` is not loopback** (`localhost`, `127.0.0.0/8`,
  `[::1]`) **is refused with 403**. Together they close cross-site request forgery and DNS
  rebinding against an auth-off developer server. Socket requests only; `tests/serve_mount.tcyr`
  exercises both through the server's socket handler.

### Fixed

- **`GET /api/v1/crews/{id}/events` reported a stale status.** It read the ledger's latch, which
  only `GET /api/v1/crews/{id}` refreshed, so a client polling events alone saw `pending` for a crew
  long finished. It now refreshes the latch first (`agnostic_crew_refresh_a`), and drains the bus
  again on a terminal state, so that snapshot ends with `crew_completed`.
  `tests/crews_route.tcyr` pins it — the old route fails the new assertion.

### Verified

- In headless Chromium, against scratch servers: auth off and auth required (sign-in through the
  shell, the role in `init`, sign-out removing the frame), the placeholder engine and a live engine
  behind a slow local stand-in gateway — the editor, saving, estimates, simulation, run records, live
  runs with real output, cancel, leave-and-catch-up, watch, presets, import, Settings and its
  Delete all, and the standalone page — 112 checks, no uncaught exception in either frame. The
  page's own logic (simulator, spec normalizer, estimator, crew request) was tested in Node: 225
  assertions, and with default settings it reproduces 0.1.7's cost distribution.
- `tests/agnostic.bcyr` benches what 0.1.8 adds per request: each transport guard ~0.15 µs, the
  two-capture document route ~2.1 µs, validating a full 32 KiB plugin document ~0.2 ms; the route
  table (now 18 paths) re-measured at ~0.12 µs first, ~0.93 µs last, ~0.78 µs miss.

### Unchanged — the aarch64 artifact is still withheld

It cross-builds (CI's compile gate). On the Pi 4, `codec` and `router` pass natively; the suites
that initialise sigil's crypto still die with the known SIGBUS (cyrius 6.6.13, bite I9) — the new
`plugindata` suite among them, at the same `ldaxr`, after its validator, guard, router, store and
limit groups have passed.

## [0.1.7] — 2026-10-01

Re-pin to **Cyrius 6.6.12** and **agnosai 2.1.2** (every dependency at its latest tag), and
the **WebGUI's first slice**: a shell at `/ui` with a Settings tab, and **Swarm Command** —
the RTS-style swarm view that was `index.html` — as its first native plugin.

**27 suites, 1,376 assertions, 0 failed** (1,240 at 0.1.6, plus `tests/webgui.tcyr`'s 136),
run the CI way: a clean copy resolved from the tags against an empty dep cache, then
re-resolved from a second empty cache with the lock check, a clean tree and every gate
green. `cyrius.lock`: 118 files, 9 commit pins, `cyrius 6.6.12`; the working tree's `lib/`
and lock are byte-identical to that resolution.

### Added — the WebGUI shell and compiled-in plugins (ADR 0004)

- `/ui`: Overview, a tab per switched-on plugin, Settings (plugin switches, session); signs
  in through `POST /api/v1/auth/login` when `AGNOSTIC_AUTH=required`.
- Swarm Command moved unchanged to `src/webgui/plugins/swarm/` with a `plugin.json`. It runs
  on its built-in simulator; its manifest says `"data": "simulated"` and the shell badges it.
- `GET /api/v1/plugins` (READ) and `PUT /api/v1/plugins/{id}` `{"enabled": bool}` (**ADMIN** —
  a deployment setting; an operator's WRITE is not enough). Idempotent, reports `changed`;
  only real changes are audited. Every plugin starts off; the switch survives a restart.
- `GET /ui/plugins/{id}`: 404 while switched off. Both page routes are public — a navigation
  cannot carry a bearer token, and the pages hold no data.
- `src/engine/settings.cyr` (durable settings on the shared handle), `src/webgui/plugins.cyr`,
  `src/routes/{plugins,webgui}.cyr`; the response record gains a media type and extra headers.
- `scripts/gen-webgui.sh` embeds each page verbatim as a raw multi-line literal with its
  SHA-256 and a generated CSP (`default-src 'none'`, scripts by hash), and refuses pages the
  CSP would break. `check-clean.sh` runs `--check`. Plugins are framed with
  `sandbox="allow-scripts allow-downloads"` — an opaque origin with no access to the token.
- `tests/webgui.tcyr`, 136 assertions; six mutations of the guards each fail a named one.
  Verified in headless Chromium, with auth off and with auth required.

### Changed — Cyrius 6.6.11 → 6.6.12, agnosai 2.1.1 → 2.1.2, libro declared directly

- agnosai 2.1.2 pins bote 3.3.15, majra 2.9.2 and sigil 3.13.5 (the fold).
- `[deps.libro]` 2.10.5 is declared directly, with `modules`, after agnosai — so both
  artifacts `cyrius deps` skips are now byte-identical to the folded copies it keeps.
- **The four bote/majra/ai-hwaccel/tyche "pre-pins" are removed: they never took effect.**
  `cyrius deps` clones a dep only when it lists `modules`. Filed upstream as
  `cyrius/docs/development/issues/2026-10-01-git-dep-without-modules-silently-inert.md`.

### Removed — the aarch64 release artifact, until cyrius aligns globals

`agnostic-aarch64` is no longer built by the release workflow, listed in `SHA256SUMS`, attached to
the release or uploaded by CI, and `cross_bins` is commented out in `cyrius.cyml` — the binary
cannot start (below). A deliberate, temporary exception to the first-party release checklist. CI
still cross-builds aarch64 as a compile gate, so it can return by re-enabling the artifact; the
restore steps are in `cyrius.cyml` and `release.yml`.

### Known issue — the aarch64 binary dies with SIGBUS at startup (since at least 0.1.3)

Root-caused on real hardware (Raspberry Pi 4) for this release; not a regression — 0.1.6 is
identical. 15 of 27 suites pass natively (717 assertions); the 12 that reach sigil's crypto init
crash, and so does the server's mount. A typed-array global (`var a: u8[N]`) occupies exactly `N`
bytes and cyrius does not re-align the next global; sankoch's `u8[363]` / `u8[217]` / `u8[50]`
(630 bytes) leave 1,101 of 1,962 globals off by 6, and an atomic on any of them — twelve, eleven of
them sigil's init flags — faults on aarch64. x86 tolerates it. Filed upstream:
`cyrius/docs/development/issues/2026-10-01-typed-array-globals-not-padded-aarch64-atomics-sigbus.md`.

### Fixed — `check-lib-symbols.py` read both arms of every `#ifdef`

- sigil 3.13.5 declares eight errno names under `#ifdef` / `#ifndef CYRIUS_TARGET_MACOS`; the
  gate failed against kavach on every shipped target. It now evaluates conditionals per
  `[release]` target (x86_64-linux, aarch64-linux). Mutation-checked in both directions.
- It ignored `CYRIUS_HOME` for dep sidecars, shrinking the compile set 53 → 49 modules in
  the empty-cache certification replica.

## [0.1.6] — 2026-09-30

Re-pin to **Cyrius 6.6.11** and **agnosai 2.1.1**. No `src/` change and no behaviour change.
**26 suites, 1,240 assertions, 0 failed**, the same totals as 0.1.5. Every gate is green and
aarch64 builds.

### Changed — Cyrius 6.6.6 → 6.6.11, agnosai 2.1.0 → 2.1.1

- **Why both move together.** Cyrius 6.6.11 checks the qualifier in `X.NAME`. Before 6.6.11 the
  compiler resolved only the member name, so the type name did nothing. kavach renamed
  `enum Backend` to `KavachBackend`, but agnosai 2.1.0's `dist/agnosai.cyr` still spelled
  `Backend.NOOP` / `.WASM` / `.PROCESS` / `.OCI`. 6.6.11 refuses each of those sites with
  `'Backend' is not an enum`, so this repo could not re-pin without a new agnosai. agnosai
  2.1.1 fixes the spelling. Its bote / majra / ai-hwaccel / tyche / kavach pins are unchanged,
  so the four direct pre-pins in `cyrius.cyml` stay where they were.
- **`lib/`** is re-synced from the 6.6.11 snapshot. Every snapshot file is byte-identical to
  `git show 6.6.11:lib/<mod>` in the cyrius repo. `lib/agnosai.cyr` is byte-identical to
  agnosai 2.1.1's `dist/agnosai.cyr`. **`cyrius.lock`**: 118 files and 9 commit pins, with
  agnosai at `1c1ea74d` and a trailing `cyrius 6.6.11` line.
- ⚠ **sigil and patra: the folded copies win.** 6.6.11 folds sigil **3.13.4** and patra
  **1.15.1**. The chain still declares sigil 3.12.18 and patra 1.14.3. `cyrius deps` refuses to
  overwrite a folded stdlib leaf and keeps the snapshot, so `lib/` still matches the snapshot
  exactly and the whole suite runs against the folded 3.13.4 / 1.15.1. The `cyrius.cyml` note
  that said the lockstep held because 6.6.6 folded the chain's exact tags is corrected.

### Fixed — `tests/deps_symbols.tcyr` asserted a spelling 6.6.11 refuses

`test_enum_members_still_resolve` asserted `Backend.WASM == KavachBackend.WASM`, "an enum qualifier
is cosmetic". Since 6.6.11 that is a compile error, and it would have broken the whole suite. The
assertion now compares the **bare** member `WASM` with `KavachBackend.WASM`. That comparison still
catches a later global named `WASM` colliding silently. The note now records when the qualifier
became checked. The suite still has 14 assertions. The patch was prepared and verified in the
cyrius 6.6.11 release (lane F, 14 passed / 0 failed on both compilers) and is applied here verbatim.

## [0.1.5] — 2026-09-26

The two server crashes 0.1.4 found and left open. Both were present since at least 0.1.3.
**26 suites, 1,240 assertions, 0 failed** (1,218 at 0.1.4); every gate green; aarch64 builds.

### Fixed — the first hash in the process killed the server a few requests later

**Mechanism.** sigil initializes its per-thread crypto state lazily: the first `cbank()` — every
`sha256`, `hmac_sha256`, Argon2 — runs `crypto_tls_main_init()`, which calls `thread_local_init()`,
which installs a FRESH TLS block on whichever thread got there first. In the server that was a pool
worker hashing on a request path, so the worker's own block was replaced and sandhi's per-request
arena slot went with it. On that worker's next request `sandhi_server_request_arena()` answered 0,
and `agnostic_serve_handler` passed the null straight into `agnostic_reqctx_new_a` → `alloc_via(0, …)`
→ SIGSEGV, whole process. Measured on 0.1.4: sixty `GET /health` — fine; one definition create, then
the **16th** `GET /health` died, the moment the 16 round-robin workers brought the poisoned one back.

⚠ **Why it hid.** A server whose audit trail was non-empty hashed on the main thread at mount —
chain verification — and was safe by accident. A fresh deployment with auth off, or one whose first
hash came from a request, was not.

**The fix, two halves.**

- `agnostic_crypto_main_init()` — sigil's `crypto_tls_main_init()` — is the **first thing**
  `agnostic_serve_mount` does, on the main thread, before any worker exists. That is sigil's own
  documented contract for threaded servers. ⚠ It must come first: `thread_local_init` is not
  idempotent on Linux (every call installs a new zeroed block), so called after `patra_init` it would
  wipe patra's main-thread parse state.
- **Defence in depth:** when sandhi hands the handler no arena, it now substitutes the global
  allocator (`_agnostic_serve_fallback_alloc`, logged once) instead of dereferencing a null. The
  module header has always said every `_a` site needs a fallback; the handler did not keep that.
  Other sandhi run modes (`run`, `run_async`, `run_pooled_tls`) have no arena at all.

**`tests/serve_mount.tcyr` (new, 7 assertions)** — its own process, calling the real
`agnostic_serve_mount` on fresh stores with auth off, the configuration the crash was measured in.
It asserts sigil is **uninitialised before mount and initialised by it**; that a worker's TLS slot —
a stand-in for sandhi's arena slot — **survives the worker's first hash**; and that the handler
answers `GET /health` and a full `POST` create through a socketpair with no arena. On 0.1.4 it
fails all three ways, the worker's slot reading 0 — the production mechanism itself. Mutation-verified:
dropping the mount call or emptying the helper fails the two named assertions; dropping the fallback
is a SIGSEGV.

### Fixed — strings read out of patra dangled: the definitions listing crashed, and a principal's tenant could change mid-request

**Root cause.** `str_new` / `str_new_a` **borrow** their bytes; they do not copy. Two sites wrapped a
`patra_result_get_str` pointer — which points into the result set — and kept it past
`patra_result_free`:

- **`agnostic_definitions_keys()`**, which the listing route iterates. A large result set is unmapped
  when freed, so with ~300 definitions `GET /api/v1/agents/definitions` segfaulted hashing the first
  key — one request, one thread. A small one is recycled instead, so a short listing could read
  another query's bytes and skip entries as "removed".
- ⛔ **`_agnostic_auth_str_a`**, whose own comment said *"Copy before freeing, always"* — and did not.
  `agnostic_users_tenant_a`, `agnostic_users_email_a` and `agnostic_tenant_name_a` all returned
  recycled memory. Measured: read user A's tenant (`acme`), then user B's (`globex`), and A's now reads
  B's bytes. **The principal built at authentication holds that tenant for the whole request, and
  tenant scoping keys off it** — so a later query in the same request could silently move the
  principal into another tenant.

**Fix:** copy — `str_from_buf` for the key snapshot, `alloc_via` + `memcpy` in the arena helper.
**Tests:** `agentdef` +7 (300 definitions: every key intact after the result set is freed and reused,
and the listing route answers 200 with `"total":300`), `authstore` +6 and `authz` +2 (two reads back
to back; the first must still be its own). All three fail on 0.1.4 — the first with a SIGSEGV — and
restoring either borrow fails them again.

**Gate:** `scripts/check-store-lock.py` gains **rule 3** — no patra result string may be handed to a
borrowing `Str` constructor, directly or through a variable. Restoring either site fails it by name.

### Verified live, against the running server

| | 0.1.4 | 0.1.5 |
|---|---|---|
| one create, then 40 × `GET /health` | died on the 16th | 40 × 200 |
| 2,000 creates, 32 at a time | died after 6 | 2,000 × 201 |
| listing 300 stored definitions | died on the first request | 200, `"total":300` |
| 32 threads × 150 listings and reads | died after 1–3 | 4,800 × 200, 0 wrong rows |
| `AGNOSTIC_AUTH=required`: 1,500 authenticated reads, 300 creates, 32 at a time | — | all 200 / 201, listing `"total":300` |

The arena fallback never fired in any of those runs — mount's crypto init is what keeps workers
whole; the fallback is there for what it does not cover.

⚠ **Still open:** the aarch64-under-qemu SIGBUS recorded at 0.1.4 (`audit`, `authstore`, any
multi-threaded workload, identical on 0.1.3) is untouched and needs real hardware.

## [0.1.4] — 2026-09-26

### Fixed — concurrent use of the shared patra handle crashed the server, and concurrent audit appends could fork the chain

**The defect.** Every pool worker (`AGNOSTIC_WORKERS`, default 16) shares ONE patra handle, and
patra's read path has taken no lock since 1.12.0. Its 1.14.0 README correction: *"Concurrent SELECTs
on one handle race the per-handle header buffer and the shared file offset — wrong rows, phantom
values, hangs."* Writers take patra's process mutex; readers do not, so a read also races a write,
and patra's per-statement `flock` cannot help — threads sharing a handle share its open file
description. Nothing here serialized the handle. **Measured on the 0.1.3 code with the new suite:
eight threads doing nothing but `agnostic_users_find_a` — the lookup behind every authenticated
request — killed the process with SIGBUS on 3 of 3 runs**, and so did eight threads writing and
reading crew outcomes. A single-threaded control of the same suite passed; eight threads doing only
the JSON decode did not crash, which rules the parser out. The audit trail had the same shape one
level up: libro's `chain_append` reads the head hash and links to it with no lock, so two concurrent
records could link to one predecessor — measured: the chain then fails verification, which reports
tampering nobody did.

**The fix — one re-entrant lock per handle, and the handle is unreachable without it.**

- `src/engine/rlock.cyr` (new): a re-entrant lock on top of the stdlib futex mutex. The owner is the
  kernel tid (`gettid`), so it needs no thread-local setup on any thread that can reach a store.
- `agnostic_store_lock()` / `agnostic_store_unlock()`. Every store operation — users, API keys,
  tenants, crew outcomes, definitions — is now a thin wrapper, `lock; var r = _x_locked(...); unlock;
  return r;`, around its unchanged body, so each runs as ONE critical section.
- ⛔ **`agnostic_store_db()` refuses the handle to a thread that does not hold the lock** — it returns
  0, "no persistence", which every caller already handles by failing, and logs at ERROR. A forgotten
  lock is a deterministic suite failure instead of a race under load. `agnostic_store_is_open()`
  answers "is persistence available?" and hands out nothing; the ledger, login verify and bootstrap
  use it.
- The audit trail has its own lock: link, persist and count are one step, and a re-verify sees a
  consistent chain.
- **Nothing slow runs under the store lock.** `agnostic_users_create_a` hashes (Argon2, ~244 ms)
  OUTSIDE it and re-checks the address under the lock immediately before its insert;
  `agnostic_users_verify_a` locks only its two lookups. The store and audit locks are never held at
  the same time.

**The same lock closes check-then-act races that were latent until now:**

- **definitions** — two concurrent creates of one key could both insert: two rows, two 201s. A `get`
  racing a `replace` could re-cache the superseded record, and one racing a `remove` could re-cache
  a deleted one — served until restart. The cache's separate mutex, "never held across a patra call"
  on the premise that "patra does its own flock arbitration", is gone: `flock` arbitrates between
  processes, not threads. The store lock now covers cache and table together.
- **users** — concurrent creates of one address each passed the existence check during their Argon2
  window; measured, with the re-check under the lock removed, **4 of 4** racing creates succeeded.
  Only the mount-time bootstrap creates users today, so this had no live trigger yet.
- **tenants** (check, insert), **API keys** (revoke = resolve + delete), **crew outcomes** (written
  once, however many threads race to write them).

**25 suites, 1,218 assertions, 0 failed** (1,175 at 0.1.3). **`tests/store_concurrency.tcyr` — 43
assertions**, and the first multi-threaded suite in the tree:
the lock's ownership rules; the accessor's refusal, including to a second thread while the first
holds the lock; 8 threads × 100 iterations of mixed definition, user and crew reads and writes;
8-way same-key races, 20 rounds each; a same-address race across the Argon2 window; 8 × 50
concurrent audit appends that must still verify. **Mutation-verified**: dropping the accessor's
owner check fails 3 named assertions; dropping the audit lock fails verification; dropping the
user re-check creates 4 users for one address; dropping the mutex fails, then SIGBUS; a
non-re-entrant lock deadlocks. ⚠ **One property is NOT mutation-proven**: splitting definitions'
check and insert into two critical sections passed all 20 rounds — that window is microseconds. The
Argon2 test is the deterministic version of the same property, and the suite says so.

⚠ **Three existing suites wrote raw SQL on the handle without the lock** — `authn`, `authstore` and
`authz` forge collision rows and a demotion directly. They are now refused, exactly as designed
(`authstore` segfaulted on the null statement), and take the lock like any other caller.

### Added — `scripts/check-store-lock.py`, wired into `check-clean.sh`

The runtime refusal only covers paths a suite exercises; this checks the same rule statically. The
raw handle global is private to `src/engine/store.cyr`; a function that fetches the handle is named
`*_locked` or takes `agnostic_store_lock()` first; a call to a store-locked function is made holding
the lock. It reports **46** violations on the 0.1.3 tree, and a wrapper that drops its lock, a body
without the lock or the name, and a direct use of the global each fail with the site named.
`_agnostic_def_row_exists` and `_agnostic_crews_exists` gained the `_locked` suffix their contract
already had.

### Cost, and why not a handle per worker

An uncontended enter/exit pair costs **~0.7 µs** — two `gettid` syscalls; the raw futex pair is 47 ns
(`tests/agnostic.bcyr` now benches both) — against **~48 µs** for a full user lookup and **~108 µs**
for a crew-outcome write. The real cost is that store access is now **serial**, a ceiling on the order
of 20,000 lookups a second. patra recommends a handle per worker for read parallelism; that
parallelizes reads only, leaves every check-then-act race open, and needs a handle lifecycle inside
threads sandhi owns. [ADR 0003](docs/adr/0003-one-store-lock-not-a-handle-per-worker.md) records the
decision and when to revisit it.

### Filed upstream — cycc skips a `defer` on `return f(...)`

Found while choosing how to release the lock: in cycc 6.6.6 a pending `defer` does not run when the
function returns through a direct call in tail position — for any callee, not only the value-form
`Result` pairs an open issue describes. A `defer { unlock(); }` would have left the lock held on
every such return, so the wrappers return a local instead. Filed with a repro as
`cyrius/docs/development/issues/2026-09-26-defer-skipped-on-any-tail-call-return.md`. In this tree's
vendored `lib/`, kavach's `security_apply_landlock` skips its deferred fd close on five exit paths
this way; nothing in `src/` uses `defer`.

### ⚠ Found while verifying this release — NOT fixed here, both present in 0.1.3 as well

Driving the real server with concurrent traffic, rather than the suites, turned up two more ways
to kill it. Neither involves the store lock, and both reproduce identically on the 0.1.3 binary, so
they are left for their own changes rather than bundled into this one. **0.1.4 does not make the
server crash-free.**

- ⛔ **The first request that does crypto poisons the worker that served it.** sigil initializes its
  crypto thread state lazily: the first `cbank()` in the process runs `crypto_tls_main_init()`, which
  calls `thread_local_init()` — installing a fresh TLS block on the CALLING thread. In the server that
  thread is a pool worker, so its own block is replaced and sandhi's per-request arena slot with it.
  Its next request gets no arena, `agnostic_serve_handler` hands the null to `agnostic_reqctx_new_a`
  unguarded, and `alloc_via(0, …)` takes the whole process down. Measured: 60 × `GET /health` —
  fine; one `POST /api/v1/agents/definitions`, then `GET /health` — the **16th** health check dies,
  i.e. the moment 16 round-robin workers bring the poisoned one back. sigil documents the contract
  agnostic misses: a threaded server calls `crypto_tls_main_init()` on the main thread before
  spawning workers. The login route's Argon2 goes through the same lazy path.
- ⛔ **`GET /api/v1/agents/definitions` kills the server with 300 definitions stored** — one request,
  one thread. SIGSEGV in `hash_str_v` ← `map_get` on the decode cache ← `agnostic_definitions_get` ←
  `agnostic_route_definitions_list_a`. `GET` of a single key works.

Also observed, and not attributable yet: as **aarch64** binaries under qemu-user, `audit`,
`authstore` and any 8-thread workload (even JSON decoding alone, no store) die with SIGBUS — on the
0.1.3 tree identically. CI cross-BUILDS aarch64 and never runs it. Whether this is qemu or the
aarch64 runtime needs real hardware.

## [0.1.3] — 2026-09-26

### Changed — Cyrius `6.6.3` → **`6.6.6`**, agnosai `2.0.9` → **`2.1.0`**, every pinned dep to its latest tag

No source change. Re-vendored, re-locked and rebuilt. **24 suites, 1,175 assertions,
0 failed — identical to the 6.6.3 baseline**, which was re-run on the 0.1.2 tree for
the comparison. Every CI gate green under the pin: lock-check, `check-symbols.sh`,
`check-clean.sh` (`deps --verify` 118/0; lib snapshot 111 files, **zero** differing),
DCE build (x86_64 **5,345,232 B**, was 5,078,792), aarch64 cross-build
(**6,487,552 B**), bench, and the fuzz harness.

| dep | 0.1.2 | 0.1.3 | how it arrives |
|---|---|---|---|
| `agnosai` | 2.0.9 | **2.1.0** | direct |
| `bote` | 3.3.8 | **3.3.13** | direct pin, matching agnosai 2.1.0's |
| `majra` | 2.7.2 | **2.9.1** | direct pin, matching agnosai 2.1.0's |
| `ai-hwaccel` | 2.3.22 | **2.4.0** | direct pin, matching agnosai 2.1.0's |
| `tyche` | 1.0.1 | **1.1.0** | direct pin, matching agnosai 2.1.0's |
| `kavach` | 3.12.5 | **3.13.1** | transitive via agnosai |
| `libro` | 2.10.0 | **2.10.3** | transitive via bote |
| `sigil` | 3.12.16 | **3.12.18** | folded stdlib; also declared by agnosai, kavach, libro |
| `patra` | 1.13.10 | **1.14.3** | folded stdlib; also declared by libro |

✅ **The lockstep holds with no hold and no allowance.** 6.6.6 folds sigil 3.12.18 and
patra 1.14.3 — exactly the tags the chain declares. ⚠ **"Latest" stops there for those
two, on purpose:** sigil 3.13.2 and patra 1.15.0 are tagged, but no Cyrius release folds
them yet, and pinning either here would make `lib/` diverge from the snapshot that
`check-clean.sh` requires. They move with the Cyrius release that folds them.

⚠ **Verified against the remote and against CI's shape, not the local cache.** All nine
dep tags and `cyrius` 6.6.6 were confirmed on GitHub through the API before any pin
moved. The whole resolution was then reproduced from scratch — a fresh copy of the tree,
an **empty** dep cache, no sibling checkouts — and it produced a `lib/` and
`cyrius.lock` byte-identical to the ones in this change, with `lock-check.sh` passing. The
6.6.6 release tarball CI installs was downloaded, checksum-verified, and its 111-file
stdlib compared to `lib/`: zero differ.

### What moved in the tree

- **`lib/alloc_cx.cyr` is new** — part of the 6.6.6 stdlib snapshot (the cx target's
  allocator variant). 118 files locked, up from 117; still 9 commit pins.
- **`cyrius.lock` gains a trailing `cyrius 6.6.6` line** (tab-separated): 6.6.x records which toolchain
  wrote the lock. `lock-check.sh` compares it as part of the file set, so a lock written
  under another toolchain now shows up there as a change.
- **`sys` joins the compile set** (52 → 53 modules): sigil 3.12.18 replaced a raw
  `syscall(63)` — `uname(2)` on x86_64, `read(2)` on aarch64 — with `lib/sys.cyr`'s
  `sys_uname`, and its sidecar now declares `sys`.

### Build warnings — duplicate `fn` definitions 19 → 1

All 19 at 0.1.2 were kavach's: the `syserr_*` / `agnosys_*` / `wrap_syscall` family it
redefined over sigil and bote-core, plus two derived `SpawnedProcess_*` accessors.
kavach 3.13.1 no longer carries them. The one left is `uname_release`, defined in both
`lib/sys.cyr` and `lib/sigil.cyr` with **identical** bodies (`return uts + UTS_RELEASE;`),
so which copy wins does not matter; `check-lib-symbols.py` confirms `UTS_RELEASE` does
not diverge.

Unchanged and pre-existing — present on the 6.6.3 build too:

- two `assigning non-pointer to typed pointer` in `src/server/serve.cyr`
  (`_agnostic_serve_send`'s `body`), **reported against `src/routes/crews.cyr`** — the
  diagnostic mis-attribution `handoff.md` §5 already records — and five in
  `lib/agnosai.cyr`;
- `cyrius deps`' `refusing to overwrite stdlib leaf 'sigil'` / `'patra'`. **Benign
  here:** each skipped dep artifact was hashed against its tag and against
  `git show 6.6.6:lib/<mod>`, and is byte-identical to the folded copy that is kept.

### Removed — the `STDIN` entry in `scripts/lib-symbol-allow.txt`

kavach 3.12.9 renamed `InjectionMethod`'s members to `KAVACH_INJECT_*`, so its `STDIN = 2`
no longer shadows `lib/io.cyr`'s `var STDIN = 0` — the collision that would have
injected a stdin-requested secret into the environment. That fix arrives here with
kavach 3.13.1, the divergence is gone from the compile set, and the line is deleted as
the file's own rule requires. The allow-list is now empty, so the gate protects `STDIN`
again.

### Arriving through the chain — checked against what `src/` actually calls

- ⛔→✅ **patra 1.14.0 fixes a B+ tree split that silently stranded index subtrees:**
  an indexed `SELECT` lost rows that a full scan still found. The trigger is a
  separator tie — duplicate keys straddling a split — reproduced upstream on the
  automatic first-INT-column index with no `CREATE INDEX` at all. **Not reachable from
  this tree's reads:** every key agnostic indexes (`uid`, `kid`, `tid`, `crew_id`,
  `dkey`) is unique by construction, and the one duplicate-keyed index — the audit
  store's `src`, which every agnostic entry sets to `"agnostic"` — is never read
  through: `patrastore_load_all` is a plain `SELECT *` scan, and `patrastore_by_source`
  is not called. A by-source audit query would have been the first thing to hit it.
  Upstream offers no repair for a file written before the fix.
- patra 1.14.0's contract changes — `patra_begin` can fail with `PATRA_ERR_IO`,
  `patrastore_close` rolls back an open transaction, `INSERT OR IGNORE` /
  AUTOINCREMENT / `ALTER … ADD COLUMN` semantics — touch no call `src/` makes: it uses
  prepare / bind / exec / query and never opens a transaction.
- **sigil 3.12.16 → 3.12.18 changes only `luks` and `sysinfo`** (aarch64 and macOS
  fixes). Argon2id, SHA-256 and HMAC-SHA256 — everything `src/auth/crypto.cyr` stands
  on — are untouched.
- **libro 2.10.3:** the audit-chain format and `PatraStore` are unchanged; `uuid_v4`
  now draws from `random_bytes`, and timestamps come from `clock_epoch_secs`.
- **agnosai 2.1.0:** crew submit / poll / cancel are unchanged. ⚠ **There is still no
  tool-registry handle** — the orchestrator never holds one; whoever builds the
  orchestrator builds the registry (`agnosai_tool_registry_new`, then
  `agnosai_app_state_new(orch, tools, …)`) — so M6's registry-ownership decision
  (`handoff.md` §8) stays open. The one breaking signature,
  `agnosai_agnos_http_transport` (new `detail_out`), is not called here. agnosai's own
  HTTP fixes (415 for non-JSON bodies, query-string stripping, `HEAD`) live in its serve
  loop and do not reach agnostic's sandhi server. Audit and pub/sub timestamps are now
  wall-clock rather than monotonic; nothing in `src/` reads one, and the crew events
  agnostic forwards carry only `event_type` and `data`.
- **kavach 3.12.8 – 3.13.1:** stricter seccomp (32-bit and x32 syscalls killed; `clone`
  with `CLONE_NEW*` and the new mount API killed; `clone3` answers `ENOSYS`),
  `config_stdin` / `config_env` / `config_workdir` honoured — a payload used to read the
  host's stdin — and `SANDBOX_POLICY_SIZE` 104 → 136. Nothing in `src/` calls kavach.
- **majra 2.9.0** breaks its encrypted-IPC handshake and signed-envelope wire formats
  (both ends must upgrade); 2.8.1 fixes IPC nonce reuse and a relay use-after-free, and
  stops `patra_queue_new` re-running `patra_init()` — which swapped patra's
  process-wide mutexes — on every open. Transitive only; `src/` does not call majra.
- **ai-hwaccel 2.4.0** lists a GPU seen by both Vulkan and a vendor API once (profile
  JSON schema v5 → v6); **tyche 1.1.0** makes `rng_normal` bit-identical across
  architectures, at 347 ns a draw instead of 92. Neither is called from `src/`.
- **bote 3.3.13:** `ping` answers `{}` instead of method-not-found; MCP `2025-06-18` is
  accepted.

### Docs

`docs/development/state.md` (Version, Toolchain, Dependencies, gate counts — it still
described 0.1.0 on 6.5.35) and `handoff.md` §1, §2 and §6 are refreshed. §2's
`CYRIUS_HOME` shim procedure is **retired**: the versioned-wrapper defect it worked
around was fixed upstream at v6.5.42, and the installed `cyrius` now re-execs the
toolchain the manifest pins — verified here with 6.6.6 current and a 6.6.3 pin.

## [0.1.2] - cyrius 6.6.3

`cyrius` 6.6.2 -> **6.6.3**. No source change; re-vendored and rebuilt.

6.6.3 makes `cyrius.lock` deterministic. `_deps_lock_dir` wrote its hash lines in
`dir_list` (readdir) order, so a fresh checkout on another machine produced the same
hashes in a different SEQUENCE — the defect `scripts/lock-check.sh` was written to
tolerate, and the reason its comparison is order-insensitive. The `lib/` names in the
lock are now emitted sorted; verified here.

⚠ **`scripts/lock-check.sh` STAYS.** It guards two things, and 6.6.3 fixes only one.
The other — a `path = "../<dep>"` override silently winning over that dep's `tag`, so a
locally-produced lock describes a sibling worktree CI will never see — is untouched by
any toolchain release and is the more dangerous half. Retiring the script because the
ordering half got fixed would drop that guard.

### Also — `lib/` refreshed to the 6.6.3 stdlib snapshot

CI runs `cyrius lib sync --full` before `cyrius deps`, which rewrites every vendored stdlib
leaf from the pinned toolchain. Six committed leaves were stale against 6.6.3 — `ganita`,
`mabda`, `niyama`, `vani`, `yantra`, `yukti` — so the lock-check step reported "the resolved FILE SET
changed" on the first push. They are refreshed here, and the lock re-resolved with the exact
CI sequence; a second run is byte-identical, so the committed lock is what CI computes.
(A local `cyrius deps` alone does NOT refresh them — only the `--full` sync does, which is
why the lock looked clean locally.)

## [0.1.1] - 2026-09-11

### Changed

- **Toolchain `6.5.35` → `6.6.2`.** No source change; the value form needed none.
  Build, tests, and any bench/fuzz/distlib target the repo ships re-verified at the new pin.

- **agnosai `2.0.8` → `2.0.9` — fixes the aarch64 cross-build.** agnosai's
  `sandbox/spawn.cyr` wired the child's stdio with raw `syscall(SYS_DUP2, fd, n)`.
  aarch64 Linux has **no `dup2` syscall at all** (only `dup3`), so the constant is
  undefined there and `Cross-build aarch64` failed on the vendored bundle with
  `undefined variable 'SYS_DUP2'`. The x86_64 build never touches that path, which is
  why it shipped green. 2.0.9 uses the stdlib's `sys_dup2()`, which exists on both
  targets. Verified here: aarch64 cross-build OK (6,086,136 bytes).

- **`scripts/lock-check.sh` replaces the inline `git diff --quiet -- cyrius.lock`.**
  `cyrius deps` does NOT emit the lock's entries in a stable ORDER across machines, so
  the byte-exact gate failed for every lock committed from another machine — it
  reported `98 insertions(+), 98 deletions(-)` while an order-insensitive compare of
  the same two files was EMPTY (identical hashes for all 117 entries, different
  sequence). The script — adopted verbatim from commandress, which hit this on its
  first CI run — compares the `commit` pins and the file set as sorted sets, so it
  still catches a changed hash, an added entry or a dropped pin. Upstream:
  cyrius `docs/development/issues/2026-09-12-cyrius-lock-unstable-order.md`.

- **`bote`, `majra`, `ai-hwaccel` and `tyche` are now pinned explicitly, ahead of
  `[deps.agnosai]`.** agnosai's own published manifest declares them with
  `path = "../<sibling>"` beside their tags; a path override makes the tag inert, so a
  machine with those siblings checked out resolves the working tree while CI resolves
  the tag. Declaring them here without a path removes the override from this repo's
  resolution.


### Changed — agnosai 2.0.4 → 2.0.5, Cyrius pin 6.5.32 → 6.5.34, and `[deps.agnosai]` loses its `path`

**These are one change, not three.** agnosai 2.0.5 carries bote 3.3.3 → libro 2.8.10,
which declares `[deps.patra] = 1.13.10`, and `cyrius deps` overlays a declared dep's
copy on top of the `lib sync --full` snapshot on every resolve. Only a Cyrius that
folds 1.13.10 — **6.5.34** — leaves `lib/` matching the pin, and
`scripts/check-clean.sh`'s lib-snapshot rule allows **no** file to differ.

⚠ Bumping either half alone leaves this repo red, in opposite directions: 2.0.4 pulls
libro 2.8.8 (patra 1.13.9), which would **downgrade** `lib/patra.cyr` against a 6.5.34
snapshot exactly as surely as 2.0.5 **upgraded** it against a 6.5.32 one. agnosai's
`main` was red for precisely this reason before 2.0.5.

**`path = "../agnosai"` is deleted, and that is the durable fix.** `path` beats `tag`
when a checkout is present, so every previous resolve here vendored whatever the
sibling working tree happened to hold — content corresponding to no tag, which CI
cannot fetch. The effect is measurable: **the lock went from 1 commit pin to 9.**
Every dependency now resolves from `git` + `tag` and carries a commit pin —
`agnosai` 2.0.5, `sigil` 3.12.9, `bote` 3.3.3, `majra` 2.6.7, `kavach` 3.12.2,
`ai-hwaccel` 2.3.18, `tyche` 1.0.1, `libro` 2.8.10, `patra` 1.13.10. Verified:
`lib/agnosai.cyr` is byte-identical to `git show 2.0.5:dist/agnosai.cyr`.

**What the chain actually delivers here.** libro 2.8.9 fixes `PatraStore` faulting when
read off the opening thread — **the defect this repo reported**, and the reason its audit
verification currently runs only once at open. patra 1.13.10 stops `patra_init` clobbering
the host's log level — the other work-around, in `src/engine/store.cyr`. ⚠ **Both
work-arounds are still in place and are now removable**; they are left for a separate
change rather than folded into a dependency bump.

Also arrives: kavach 3.12.2 (`config_env`, `config_workdir`, and a command-blocklist fix
that let a rootfs'd sandbox run a shell). Nothing here calls that surface yet.

### Added — a `lib/`↔`lib/` symbol gate, because nothing in the ecosystem had one

`scripts/check-lib-symbols.py`, wired in as **Rule 4** of `check-symbols.sh`.

Rules 1–3 all take `src/` as one side of the comparison, so none of them can see a
collision **between two dependencies** — and neither can the compiler, which warns on a
duplicate `fn` and is **silent** for `var` and for enum members. That blind spot is how
kavach's `var BACKEND_COUNT = 10` and ai-hwaccel's `= 18` both reached a binary through
agnosai, with the 18 winning: it admitted ids 0–17 into a 10-slot function-pointer table
and called whatever sat 224 bytes past its end. It was found by hand.

`lib/` here is ~1.6 MB of vendored dependency, most of it arriving **transitively**
through agnosai — kavach, ai-hwaccel, libro, bote-core, majra, tyche — so this repo
carries the exposure without declaring most of the deps that create it.

The check resolves the real compile set from `cyrius.cyml` (`[deps].stdlib`, each dist's
`.deps` sidecar, every dep dist in `lib/`), skips the per-platform stdlib variants that
define the same names on purpose, **fails** on any constant defined twice with differing
values, and reports the rest. **Validated against the historical defect**: with kavach
3.11.14 and ai-hwaccel 2.3.17 restored it reports `BACKEND_COUNT` 18-vs-10 and fails.

⚠ **One live divergence is allow-listed, not fixed:** `STDIN` is `var STDIN = 0` in
`lib/io.cyr` and `InjectionMethod.STDIN = 2` in `lib/kavach.cyr`. Under this repo's
ordering io.cyr wins, so kavach's member collapses onto `ENV_VAR` (both 0) and its two
credential guards alias — a secret requested on stdin would be injected into the
environment instead. **Unreachable here**: across the whole 52-module compile set `STDIN`
occurs exactly four times — io.cyr's definition and kavach's own three — and nothing reads
it as a file descriptor. Filed upstream with a repro; a consumer-side rename cannot fix it
because both definitions live in `lib/`.

### Changed — agnosai 2.0.5 → 2.0.6, Cyrius pin 6.5.34 → 6.5.35

**24 suites, 1,175 assertions, 0 failed — identical to before the bump**, which is
the expected result: agnosai 2.0.6 is a dependency-and-toolchain release whose only
`src/` change is a version-drift fix, and `git diff --stat 6.5.34 6.5.35 -- lib/`
is empty, so the folded stdlib does not move either. This bump changes the code
generator and the dependency chain, not behaviour.

Arriving through agnosai: **bote 3.3.3 → 3.3.7**, **majra 2.6.7 → 2.7.0**, and
**libro 2.8.10 → 2.8.12** transitively through bote. `sigil` 3.12.9, `kavach`
3.12.2, `ai-hwaccel` 2.3.18 and `tyche` 1.0.1 were already newest and did not move.

✅ **No `[deps.patra]` hold is needed at this pin.** 6.5.35 folds patra 1.13.10,
which is what libro 2.8.12 declares, so `lib/` matches the snapshot with **zero**
files differing — verified file by file, not inferred from a green gate. The hold
that 2.0.5 needed is not reintroduced here and must not be added back.

⚠ **Verified against the tags, not the install directory.** `lib/agnosai.cyr` is
byte-identical to `git show 2.0.6:dist/agnosai.cyr`, and every dep dist in `lib/`
was matched back to a tag by hash. That discipline exists because reading
`~/.cyrius/versions/<V>/lib/` produced a wrong diagnosis earlier in this port —
a concurrent session rewrites those files in place.

⚠ **The lock carries 8 commit pins, not 9: `agnosai` has none yet.** At the time
of this change `refs/tags/2.0.6` was **not on the remote** — the commit was pushed,
the tag was not — so `cyrius deps` could not fetch it and the dep was resolved from
a locally seeded cache of the tagged tree. The bytes are identical to the tag by
construction and were hash-checked against it. **A fresh `cyrius deps` after the
tag is pushed will add the missing commit pin**, and CI cannot resolve this
dependency until then. That is the one outstanding item on this change.

### Added — M6 (part 1), the tool viability gate: 2 of 38 resolve

**31 assertions** in `tests/tools.tcyr`; 1,175 total across 24 suites, 0 failed.
`src/engine/tools.cyr` turns the preset tool vocabulary from a comment into a
**checkable contract**, which is the thing the roadmap assigns M6 to own.

**The measured position, not an estimate.** The 18 presets name **38 distinct
tools**; the engine registers **14 builtins**; **zero of the 38 resolve by name**,
because the two vocabularies are in different forms — `LoadTestingTool` versus
`load_testing`. After this change **2 resolve and 36 do not**, and both numbers
are pinned by the suite so they can only move deliberately.

⚠ **A case transform was rejected, not overlooked.** `LoadTestingTool` →
`load_testing` happens to work; `RiskScoringTool` → `risk_scoring` resolves to
nothing at all. A transform makes those two indistinguishable — it reports
coverage for 38 names and fails at call time for 36 of them. An explicit alias
table is the only shape where an entry means something can actually run.

⚠ **`ComprehensiveSecurityAssessmentTool` is deliberately NOT aliased to
`security_audit`**, even though the backend is sitting right there and the names
are close. "Comprehensive" is a stronger claim than the backend makes, and
mapping it would book coverage this tree does not have. The suite asserts the
absence, so a later contributor has to argue for it rather than add it quietly.

⚠ **A miss returns 0, and callers must refuse.** That is the direct answer to
`ORACLE-AUDIT.md` §3.15 — the oracle's registry was never populated, so
`_resolve_tools` warned and built every agent with `tools=[]`. The defect was not
the empty registry; it was that a miss degraded silently. There is no
best-effort path in this module and none should be added.

⚠ **Resolution returns the ENGINE's tool object rather than wrapping it.** A
wrapper per QA name would record two GenAI spans per call — `agnosai_tool_execute`
instruments the vtable chokepoint — and would have to reproduce the backend's
schema callback, whose allocator convention is AgnosAI's to change.

**`ArtifactManagementTool` and `CIPipelineIntegrationTool`** are still named by
`quality-large.json` and still have no implementation anywhere — unlike the other
36, which at least had a class in the oracle. The roadmap requires them written
or struck; `tools/nonexistent` exists so that decision cannot be forgotten.

⚠ **What M6 part 2 has to decide first: who owns the tool registry.**
`agnostic_engine_init` exposes no registry handle — the orchestrator owns one
internally — so nothing here is wired into mount yet, and coverage is a library
question rather than a served one. Registering agnostic's QA tools somewhere the
orchestrator's agents actually read is the next decision, and guessing at it
would be the kind of narrow fix that has to be redone. The gate is deliberately
useful without it: the number is real, and it is the number that has to reach 0.

### Added — M5 (part 3), the login route and the first-administrator bootstrap

**35 assertions** in `tests/loginroute.tcyr`; 1,144 total across 23 suites, 0 failed.
Together these close the loop M5 part 2 left open: there was an auth rung and no
way to obtain a credential, and no way to create the account that would.

**`POST /api/v1/auth/login`** — `{email, password}` on the allow-list codec, so an
unknown field is a 422 rather than the oracle's silent discard. Answers a Bearer
token, its type, its TTL and the role.

⚠ **It is the only anonymous route on the authenticated surface**, exempted in
`agnostic_route_needs_auth` — a route that issues credentials cannot require one.
That exemption is the single hole in this API's fail-closed default, and what
stands in it is `agnostic_login_a`: the per-IP bucket and the Argon2 pool cap,
both already mutation-verified to run *before* any hashing.

⚠ **A wrong password and an unknown address are byte-identical responses.** Same
status, same rendered body — asserted by comparing the two, not by inspection.
`agnostic_users_verify_a` already spends a full Argon2 on the unknown path, so
the timing does not separate them either. The 429s are likewise
indistinguishable: bucket exhaustion and a saturated pool both answer "come back
later" without saying which limit was hit.

**`agnostic_auth_bootstrap_a`** creates the first administrator as a SUPER_ADMIN
— it has to be able to provision everything else. ⚠ **It refuses if ANY user
already exists**, which is what keeps a credential left in the environment from
being a standing backdoor. Not "no admin exists": a deployment holding a lone
viewer has already been bootstrapped. *Mutant: removing that guard mints a second
super-admin from the same environment variables.*

⚠ **`AGNOSTIC_AUTH=required` with no users and no bootstrap credential REFUSES TO
START.** The alternative is a server that is up, enforcing, and impossible to
authenticate against — locked shut with no message saying why.
`AGNOSTIC_BOOTSTRAP_PASSWORD` is read like `AGNOSTIC_LLM_API_KEY`: stored, never
logged, never in a response. The mount logs the email and uid, and WARNs to
rotate the credential.

### Changed — the dispatch ladder takes a request context, not a bare header

`agnostic_route_dispatch_a`'s sixth parameter is now an `agnostic_reqctx_new_a`
block carrying the credential *and* the peer address, which the login route needs
for its rate bucket. Threading each transport fact separately is how a dispatch
signature reaches nine parameters.

⚠ **`peer_ip` is the socket peer, deliberately not `X-Forwarded-For`.** Behind a
proxy every request shares one address and the bucket becomes a global limit —
a real deployment problem, but the alternative is worse: a caller-supplied
address lets an attacker mint a fresh bucket per request and removes the control
entirely. Trusted-proxy configuration is not carried yet.

⚠ **Two Cyrius hazards this change walked into, both worth knowing:**

- `ctx == 0` still means "nothing known", so the existing call sites kept
  compiling — but `tests/authn.tcyr` passed a **`Str` header** where a struct was
  now expected, and everything is `i64`, so nothing caught it. The suite
  **crashed** rather than failing an assertion, producing no output at all: it
  showed up only as `22 passed, 1 failed` with 23 suites present. Changing what a
  parameter *means* is not visible to the compiler here.
- `agnostic_serve_handler`'s first parameter is already named `ctx` (sandhi's
  server context). Shadowing it is a compile error whose diagnostic points at an
  **unrelated file** — `src/routes/crews.cyr`, at a column that line does not
  have.

⚠ **And one real bug the tests initially hid.** The login route first passed
`agnostic_encode_a(...)` to `agnostic_response_json_a`, but that helper takes the
bayan **object** — `_agnostic_serve_send` serialises it. Handing it a `Str` makes
it encode the encoding, so the client receives a JSON string containing escaped
JSON. The test missed it by reading the body directly instead of through the send
path; it now asserts the rendered body begins with `{`.

### Removed — both sibling-library work-arounds, now that their fixes have landed

Two guards in this tree existed only because upstream defects were live. Both
fixes arrived with agnosai 2.0.5 / Cyrius 6.5.34, so both guards are gone —
and each is replaced by an assertion, because both failures were **silent**.

**`patra_init` no longer clobbers the host's log level.** It used to end with an
unconditional `sakshi_set_level(SK_WARN)`, process-global, so opening the
database threw away whatever `AGNOSTIC_LOG_LEVEL` had set — including the
`listening` line. `src/engine/store.cyr` saved and restored the level around the
call. Fixed in **patra 1.13.10**; the save/restore is deleted from `store.cyr`
and from six test helpers that had copied it. `tests/crewstore.tcyr`'s
`store/log-level` group now asserts the level survives `patra_init` at INFO and
DEBUG — the downstream symptom is *missing log lines*, not an error, so it needs
a test rather than a reader's attention.

**A `PatraStore` read from another thread no longer kills the process.**
`patrastore_open` cached its `SELECT` and `COUNT` handles while patra's SQL parse
scratch is per-thread, so a statement parsed on the opening thread and executed
on a sandhi pool worker dereferenced absent TLS — no diagnostic, no unwind. This
tree found it as *"the first HTTP request to one endpoint takes the whole server
down while every other route keeps working"*, filed it, and worked around it by
reading **nothing** off the main thread: `agnostic_audit_count` was
`at_open + appended` arithmetic rather than a query, and verification could only
run at open.

Fixed in **libro 2.8.9**, so:

- `agnostic_audit_count` now **queries live**. The counter version was also wrong
  whenever this process was not the only writer — it under-reported silently.
- **`agnostic_audit_reverify` is new** and runs on any thread, which is the live
  re-verify endpoint the module header said would become possible. ⚠ It re-reads
  and re-hashes the whole chain, so it is an operator action, not a health check.
- The open-time verdict is still what `/api/v1/audit` reports by default — that
  part was a design preference, not the constraint, and it stays.

`tests/audit.tcyr`'s `audit/off-thread` group spawns a worker and has it both
count and re-verify. ⚠ **If that test ever dumps core instead of failing an
assertion, the upstream fix has been undone.** Worth knowing while reading it:
patra's own comment records that threads spawned via `lib/thread.cyr` inherit
their TLS block through `CLONE_SETTLS` and must **not** re-init — which is why a
pool worker can touch the store without any per-worker setup.

### Added — M5 (part 2), identity end to end: the auth rung is no longer a comment

**478 assertions across five new suites**; 1,103 total across 22 suites, 0 failed.
Every security claim below is backed by a **killed mutant**, not by a passing
assertion — the mutation is named with each one.

**`src/auth/store.cyr` — users and API keys.** patra auto-indexes column 0 when
it is `COL_INT`, so both tables put a 63-bit truncated SHA-256 there and issue
**zero `CREATE INDEX`**. ⚠ That makes a hit a *bucket*, not an identity: patra
re-checks its own STR index hits and gives no such re-check for an app-computed
INT key. Every lookup re-verifies the full value, the API-key path in constant
time. *Mutants: dropping either re-check returns an attacker's row — the user one
resolved a forged collision to somebody else's uid.* An over-long email is
**refused**, because a `COL_STR` is 256 fixed bytes and truncation would merge two
addresses into one row. An unknown address still costs a full Argon2 against a
decoy record, so login is not a user-enumeration oracle.

**`src/auth/jwt.cyr` — HS256 bearer tokens**, adapted from the SecureYeoman
probe the roadmap names. ⚠ **The token's own `alg` header is never read.**
Verification recomputes HS256 and compares; there is no branch that could select
an algorithm the caller named, so `{"alg":"none"}` and an RS256 swap both die at
the MAC. The signature is compared **encoded**, so attacker-controlled base64 is
never decoded before authentication. A missing `exp` is a reject, not "no
expiry". *Mutants: removing the compare breaks six assertions; treating an absent
`exp` as unlimited breaks one.*

⚠ **Correction to the reference:** its note that bayan's `base64url_decode` "did
not round-trip" does **not** reproduce against the folded bayan in `lib/`. Ours
exists for a different reason — bayan's encode/decode allocate on the
process-global no-free bump, and issue/verify run per request. The encoder is
cross-checked byte-for-byte against bayan's on every remainder class.

**`src/auth/perm.cyr` — a static role→permission table**, not `role >= N`. ⚠ An
ordering comparison makes the enum's numeric order load-bearing and grants
everything below an out-of-range value. *Mutant: the `>=` form grants READ to role
**-1** — which is exactly what `agnostic_users_role` and `agnostic_jwt_claim_role`
return for "no such identity".* A route nobody classified requires ADMIN.

**`src/auth/tenant.cyr` — tenancy.** Scoping is `"<tenant>:<key>"`, which is a
cross-tenant collision primitive unless the tenant key cannot contain the
separator: `acme` + `x:y` and `acme:x` + `y` would both produce `acme:x:y`.
Tenant keys are `[a-z0-9][a-z0-9-]*`, so the ambiguous tenant cannot be named —
asserted directly. *Mutant: letting `unscope` trust the first colon lets one
tenant read another's object.*

**`src/auth/authn.cyr` + the dispatch ladder — the rung itself.** Two schemes,
named explicitly (`Bearer`, `ApiKey`) and never sniffed from the credential's
shape. ⚠ **A verified JWT proves *who*, not *what*: the role and tenant are
re-read from the user row on every request.** That costs one indexed lookup and
buys instant revocation. *Mutant: trusting the role claim leaves a demoted user a
SUPER_ADMIN and lets a deleted account keep authenticating.*

⚠ **401 and 403 are kept distinct.** 401 is "I do not know who you are"; 403 is
"I know, and you may not". Collapsing them — a common hardening reflex — tells a
valid user with the wrong role to re-authenticate, which cannot help them.
*Mutant: disabling the rung turns a 401 into a 200 and a 403 into a 422, the
latter proving the handler had parsed a body it should never have seen.*

**Auth is off by default, and that is bounded rather than fail-open.** Nothing can
authenticate before an operator has provisioned a user and there is no bootstrap
route yet. What stops it being a hole: `agnostic_serve_mount` **refuses to start**
with `AGNOSTIC_AUTH` off on any bind but loopback, and says so on loopback.
`state.md` recorded loopback as the only thing standing in front of the crew
routes; that is now structural rather than incidental.

**`src/auth/ratelimit.cyr` — login-abuse controls.** Argon2id at ~244 ms makes
login a request-amplification lever. Two independent controls: the pool slot count
caps *concurrent* hashes, and a per-IP token bucket caps the *rate*. ⚠ **The
bucket is checked before any Argon2 work** — a limiter that sheds after hashing
has already paid the cost it exists to avoid. *Mutant: moving the check after the
verify is caught by asserting the Argon2 shed counter does not move, which a test
on the returned 429 alone would have missed.* The table is fixed-size, so memory
is bounded; the honest cost — an attacker rotating addresses evicts legitimate
entries — is stated in the module rather than glossed.

**`src/auth/webhook.cyr` — HMAC-SHA256 callbacks.** The signature covers
`"<ts>.<body>"`, not the body alone, because a bare body signature is replayable
forever. The timestamp is **inside** the MAC, so an old signature cannot be
re-stamped with a fresh one. *Mutant: signing the body alone lets exactly that
forgery through.* Freshness is checked before the MAC is computed.

**External IdP verification is additive, and enforced to be.** The validator runs
**only after local verification fails**, returns a **uid rather than a principal**
(so it cannot grant a role this deployment did not assign), and a uid with no
local row authenticates nobody. All three are asserted.

⚠ **A Cyrius note worth keeping:** `secret` is a **reserved keyword** and cannot
be a parameter name. The diagnostic attributes it to the previously-included
file, which sent the first search to the wrong module.

### Added — M5 (part 1), credential primitives on sigil

**54 assertions** in `tests/crypto.tcyr` across six groups (hex, digest, password,
malformed-record, pool, api-key); 825 total across 17 suites, 0 failed.

`src/auth/crypto.cyr` — Argon2id password hashing at the roadmap's parameters
(m=19456 KiB, t=2, p=1), API-key digests, and the cost budget.

- **The Argon2 buffer pool IS the concurrency cap.** sigil's convenience form allocates
  its own scratch and rules itself out (`fl_alloc` is not thread-safe), so
  `argon2id_into` with a caller-supplied buffer is the only correct entry point here —
  handlers run on sandhi pool workers. At 19.0 MiB per concurrent hash, one buffer per
  worker would be 304 MiB resident. A small fixed pool bounds the memory *and* sheds
  excess logins with 429 having done no Argon2 work — the amplification SecureYeoman
  measured was 8 concurrent attempts pushing `GET /health` from 6 ms to 942 ms.
- **The stored form carries its parameters** — `v1$<t>$<m>$<p>$<salt-hex>$<hash-hex>` —
  so raising `m_cost` later does not silently invalidate every existing password.
- Malformed records are **refused, not partially decoded**; the API-key path parses
  attacker-supplied hex.

### Added — M4 (part 2), a durable tamper-evident audit chain on libro

**35 assertions** in `tests/audit.tcyr`; 746 total across 15 suites, 0 failed.
Proven live: three events recorded, the process restarted, one byte of a recorded
detail edited on disk, and the restart reported `"intact": false, "bad_index": 1`
with an ERROR naming the entry.

`GET /api/v1/audit` reports the trail's state. Crew submit/cancel and definition
create/replace/delete each record an entry.

- **A streaming chain, not a retaining one.** libro's own comment is the reason:
  for a write-through consumer the retaining chain's entry vec "is pure
  accumulation ... A long-lived writer grew forever." Linkage is byte-identical,
  so the durable chain verifies the same.
- **Hash-linked, and not signature-backed — stated rather than implied.** libro's
  `audit_entries` table is `(id, ts, sev, src, act, det, aid, phash, hash, halg)`:
  there is **no signature column**, so `sign_entry` would compute a signature and
  `patrastore_append` would discard it. Computing security theatre is worse than
  not computing it. What that leaves undetected is named in the module header: an
  attacker who can write the file *and* recompute every hash forward.
- Still strictly better than the engine's own trail, which mints its key with
  `random_bytes` per start and keeps entries in memory — unverifiable across a
  restart, and gone when the process is.
- **Gaps are counted, because verification cannot see them.** A failed append
  leaves no hole to find, so `dropped` is on the endpoint beside `intact`. A
  chain reporting `intact: true` with a non-zero drop count has not told you
  everything.
- **A broken chain is loud, not fatal.** Refusing to start would let an attacker
  deny service by corrupting one byte and would take the evidence offline with it.

### Fixed — `patra_init` was silently resetting the log level

`patra_init`'s last line is an unconditional `sakshi_set_level(SK_WARN)`
(`lib/patra.cyr:4472`), so opening the database threw away whatever
`AGNOSTIC_LOG_LEVEL` had set — every INFO line in the process, including
`listening`. agnosai hit this, avoided patra entirely, and left a note for
"whoever does reach for patra later" (`lib/agnosai.cyr:29933`).

Saved and restored around the call in `agnostic_definitions_open`, so the wart
stays in the one module that triggers it. ⚠ **Worth fixing upstream** — a library
has no business setting its host's log level.

### Changed — audit verification runs at open, not per request

⚠ **A libro thread-safety limitation, found by it crashing the server.**
`patrastore_open` prepares its `SELECT` and `COUNT` statements once and caches
them in the store struct, and patra's SQL parse scratch is **per-thread**
(`patra_init`: "Install this (main/foreign) thread's TLS block so the per-thread
SQL parse scratch resolves"). Using those cached statements from a sandhi pool
worker kills the process — reproduced directly: `agnostic_audit_count()` succeeds
on the main thread and takes the worker down.

`src/engine/definitions.cyr` is unaffected because it calls `patra_prepare` on
the calling thread every time; libro's store does not.

So verification happens once, at open, on the main thread — which is also simply
the right moment, since the question a tamper-evident chain answers is "was this
altered while I was not running". Entry counts are maintained in-process rather
than queried. `GET /api/v1/audit` reports `"verified": "open"` so a client reading
`intact` knows *when* it was true. A live re-verify needs libro to stop sharing
prepared statements across threads.

### Added — M4 (part 1), agent definitions are durable in patra

**106 assertions** in `tests/agentdef.tcyr`; 711 total across 14 suites, 0 failed.
Verified live: a definition created in one process is served by a *different*
process after a restart, with its retained fields intact.

`patra` joins `[deps].stdlib` — it is folded into the toolchain stdlib rather
than being a `[deps.*]` block. New config: **`AGNOSTIC_DB_PATH`**, defaulting to
`agnostic.patra` relative to the working directory, with the resolved path logged
at mount.

- **The nine store functions kept their signatures**, so
  `src/routes/definitions.cyr` was not touched. That rule existed for exactly
  this moment. The one thing that moved on the wire is the `storage` literal:
  `"memory"` → `"patra"`.
- **The stored document is the wire form.** A definition is persisted as the JSON
  `agnostic_agent_def_to_value_a` renders and read back through
  `agnostic_agent_def_decode_a` — the same decoder that validates a client
  request. So there is no second serialiser to drift, a row that no longer
  decodes is caught rather than half-read, and `focus` / `allow_delegation`
  persist for free because they are in the wire form. The restart test asserts
  exactly that: `focus`, which the engine has no slot for, survives.
- **A decode cache, because there is still no `free()`.** Decoding per `GET`
  would leak from the global bump on every read. patra is authoritative for
  existence, `count` and `keys`; the cache only avoids re-decoding a document
  already read. ⚠ It assumes this process is the only writer — patra is
  flock-arbitrated and genuinely multi-process, so if that stops being true the
  cache has to go rather than be patched.
- **`AGNOSTIC_DEFINITIONS_MAX` changed meaning** from a store ceiling to a cache
  bound. M3 refused a create past it because memory had no `free()`; patra has no
  such limit, so creates now succeed past it and only caching stops. The suite
  asserts the new behaviour rather than the old.
- **A store that cannot open is a startup failure.** Accepting a definition
  against a database that is not there would lose it, which is worse than
  refusing to start.

⚠ **Two patra constraints confirmed by reading it, both real.** Exactly **one
index per table** — `SCH_IDX_COL` is a single slot in the schema page, and a
second `CREATE INDEX` replaces the first. And `COL_STR` is a fixed 256-byte slot,
so long values need `COL_TEXT`, which is chain-paged and **cannot be indexed or
used in `WHERE`**. Neither binds M4: definitions index on `dkey` and carry the
document as TEXT. The single-index limit will bind **M5**, where users need
lookup by both id and email.

Durability is configurable, contrary to the roadmap's shorthand:
`PATRA_SYNC_FULL` (fdatasync per mutating exec) is the default, but
`PATRA_SYNC_BATCH`, `patra_flush` and explicit `patra_begin`/`patra_commit`
transactions all exist.

### Added — M3 (part 2), agent definitions: one model, three dispositions

**97 assertions** in `tests/agentdef.tcyr`; 702 total across 14 suites, 0 failed.

A crew's `agents` array and a stored agent definition are the **same model**,
decoded by `agnostic_agent_def_decode_a` and by nothing else. `request.cyr` had a
second copy; two decoders for one concept is how the two ends drift, which is
`ORACLE-AUDIT.md` §3.3 restated at the level of a field.

`ORACLE-AUDIT.md` §2.2 lists fourteen fields the oracle dropped in translation.
Nothing here is dropped — every key a client can send has exactly one of three
fates, and the client can tell which:

- **FORWARDED** (12) — the engine has a slot that acts on it.
- **RETAINED** (2) — `focus` and `allow_delegation`, kept and round-tripped
  verbatim and **named in an `unforwarded` array** on every response carrying the
  definition. Membership was decided by one test: does the canonical preset
  library carry it? All 76 preset agents carry `focus`, 18 carry
  `allow_delegation`, and neither reaches the engine.
- **REFUSED** (12) — a 422 naming the missing capability, checked *before* the
  generic unknown-field arm so a real capability request never reads as a typo.
  `agent_key` is refused with a message pointing at `key`, because the oracle and
  the engine both spell it the other way. `hardware` is the one field refused
  despite the engine having a slot — the record is `ai-hwaccel`-shaped and
  Agnostic has no decoder for it.

Five CRUD routes, **201** for a definition against M2's 202 for a crew: a crew is
accepted work that is not finished, a definition is complete when the call
returns. **No upsert** in either direction — `POST` to an existing key is 409,
`PUT` to an absent one is 404 — because an upsert turns a typo'd key into a
second silently-created definition. **507**, not 503, when the store is full: 503
means the engine cannot act, and one of those faults is retriable after a delete.

The store is memory-resident, capped at 256, and **never evicts** — evicting a
definition the user named would 404 something they created. Disclosed by
`"storage": "memory"` on all five responses and a WARN at mount.

### Fixed — an unset GPU memory floor became a concrete 0

Found by live testing, not by the suite. The three GPU fields share one engine
setter, so `gpu_required` alone still writes all three — and passing 0 for the
unspecified floor overwrote the engine's `AGNOSAI_NO_LIMIT` sentinel, putting
`"gpu_memory_min_mb": 0` on the wire for a field the caller never sent. An
unspecified value acquiring a concrete one is the same class of defect as a
dropped field, in the opposite direction. Pinned by a regression assertion.

### Added — M3 (part 1), the canonical preset library

**71 assertions** in `tests/presets.tcyr`; 581 total across 13 suites, 0 failed.

18 documents, 76 agents, 38 distinct tool names. Checked in at `src/presets/*.json`
and embedded into `src/presets_data.cyr` by `scripts/gen-presets.sh` — Cyrius has
no `include_str!`, so a data file must be turned into source first. The generated
file is committed so a clone builds without the generator, and `check-clean.sh`
runs `--check` so that copy cannot go stale.

- **Parsed once at mount.** `agnosai_builtin_presets()` re-parses all eighteen on
  every call, `agnosai_preset_from_value` allocates from the no-`free()` global
  bump, and the engine has no name lookup at all — no `agnosai_preset_find`,
  `_get` or `_by_name` exists. A parse shortfall **refuses to start**.
- **`GET /api/v1/presets` returns summaries**, and `GET /api/v1/presets/{name}` the
  whole document, served as parsed rather than copied. The library is 61,412 bytes
  against a 65,536-byte arena that spills into the global bump, so a full-document
  listing would leak on every call. Measured live: listing 4,416 B, largest
  document 7,064 B — the default arena was left unchanged on that evidence.
- **Read-only.** A write earns a 405 naming the mismatch, not a 404 claiming the
  collection does not exist. Durable presets are M4's.

### Added — `src/app.cyr`, so adding a route stops breaking every suite

The include order lived in `src/main.cyr` and every suite reaching the router
reproduced it — so a new route module failed them all with "undefined function"
rather than "missing include", three times across M2 and M3. `main.cyr` cannot
serve that role itself: its two trailing top-level statements run at include time
and would start a server inside a suite.

### Changed — `check-clean.sh` skips lint for files marked `GENERATED FILE`

Exactly one file qualifies. `src/presets_data.cyr` has lines over 120 characters
that cannot be avoided: a single JSON atom — a `backstory` — runs to 442
characters, and the wrapper must not split inside one because a Cyrius line
continuation **keeps the newline** (verified: `"abc\<newline>def"` is 7 bytes, not
6) and a raw newline inside a JSON string is illegal JSON. Cyrius has no C-style
adjacent-literal concatenation to split it with, and `#skip-lint` is scoped to a
line, so it cannot be placed on an offending line that sits inside a literal.

The length is a property of the documents, not of anyone's style. The file is
still covered by `fmt`, `doc`, the compiler, `gen-presets.sh --check`, and
`tests/presets.tcyr` — 17 human-authored files are still linted.

### Fixed — `gpu_strict` is refused by name, and it is not `gpu_required`

A correction to M2's own comments, found while opening M3. `gpu_strict` and `gpu_required` are
**different fields**: the oracle declares both (`agents/base.py:61-62`) and hard-fails only on
`gpu_required AND gpu_strict` (`config/gpu_scheduler.py:196`). `required` asks for a GPU; `strict`
says fail rather than fall back to CPU. M2's comments claimed `gpu_required` was `gpu_strict`'s
counterpart — it is not, and believing that would leave a reader thinking hard-fail was covered.

⚠ **The Cyrius engine cannot express strictness at all** — `gpu_strict` appears zero times in
`lib/agnosai.cyr`, `agnosai_agent_with_gpu` takes only (required, preferred, memory_min_mb), and
`agnosai_agent_hardware_requirement` builds accelerators plus a memory floor with no fallback flag.

So it is refused, and now refused **with its own message** naming the missing capability rather than
falling to the generic "unknown field", which reads like a typo. A caller who needs hard-fail learns
the platform cannot do it. The alternative — mapping it onto `gpu_required` — would reinstate exactly
the silent CPU fallback `ORACLE-AUDIT.md` §3.11 records.

### Added — M2, the crew surface: submit, poll, cancel, progress

**267 new assertions across 4 suites** (496 total across 12), 0 failed. All three gates green.
Verified live over a socket, not only under test.

AgnosAI is linked **in-process**, so there is no transport here — no client, no URL, no retry
policy. That removes a whole class of the oracle's defects by construction and leaves the ones that
were never about transport.

- **`src/engine/outcome.cyr`** — the result type the milestone turns on. Carries status **and**
  error **and** the engine-assigned crew id **and** the result set. The oracle's `BackendResult`
  had a `.status` that **no caller anywhere in the codebase read**.
- **`src/engine/ledger.cyr`** — what Agnostic remembers about the crews it submitted, and where a
  terminal status is latched.
- **`src/engine/request.cyr`** — one task model, allow-list decoded, dependency graph validated.
- **`src/engine/crew.cyr`** — the orchestrator bridge: submit, poll, cancel.
- **`src/routes/crews.cyr`** — `POST /api/v1/crews` (**202**), `GET /api/v1/crews/{id}`,
  `POST /api/v1/crews/{id}/cancel`, `GET /api/v1/crews/{id}/events`.

**202-then-poll**, not the engine's inline shape. `agnosai_route_create_crew_a` calls the blocking
`agnosai_orchestrator_run_crew` to keep parity with its Rust oracle, so a `POST` holds a worker for
the whole run. Agnostic submits and returns the id.

### Fixed — the four `ORACLE-AUDIT.md` §3 defects, designed out rather than avoided

- **§3.1 — a failed crew reported as completed.** `_agnostic_outcome_normalise` demotes a
  COMPLETED-with-no-results to FAILED *before* the record exists, so the vacuous success is never
  observable. ⚠ **This is not a Python-ism.** `agnosai_crew_runner_run` sets `COMPLETED` and only
  downgrades inside a loop over `results` — over an empty set the loop body never runs and the
  status stands. `all([])` in Cyrius, one dependency away.
- **§3.2 — cancel addressing an id the engine never saw.** Every id originates in
  `agnosai_crew_new`. Agnostic mints none, so there is no local UUID to substitute. A refusal from
  the engine is **returned, not discarded**, and the ledger is not relabelled.
- **§3.3 — two structurally different task models.** `tasks` is required and non-empty, there is no
  fallback path, and an unlisted key is a 422 naming it. The oracle's fallback fired on every
  request because its model declared no `tasks` field at all.
- **§3.4 — a terminal state overwritten by a later, wronger one.** `agnostic_ledger_latch` refuses
  to write over a terminal status — in one guard, at the only place a status is stored.

### Fixed — two engine behaviours that only bite the async path

Neither is in the 86 audited oracle defects; both were found building M2.

- **A cyclic DAG submitted asynchronously reports `pending` forever.**
  `agnosai_crew_runner_run` returns 0 on exactly one arm, and `_agnosai_orch_finish_err` then
  returns **without touching the crew map** — which `_agnosai_orch_register` has already seeded with
  PENDING. The blocking caller sees the 0; `_agnosai_orch_submit_thread` discards it. Closed at the
  front door: `agnostic_crew_req_has_cycle` rejects the graph before submission, so the arm is
  unreachable through Agnostic.
- **A finished crew can be evicted and then 404.** `_agnosai_orch_evict_locked` drops **every**
  finished crew once the registry holds 1000, so a successful run becomes indistinguishable from a
  typo'd id. The ledger answers from its own latched outcome; `AGNOSTIC_LEDGER_MAX` is deliberately
  above the engine's cap, and a suite asserts that ordering.

### Added — placeholder mode is disclosed, because nothing else can distinguish it

With no `AGNOSTIC_LLM_URL`, `agnosai_execute_task` takes its `client == 0` arm and
`_agnosai_crew_placeholder_result` echoes the task description back as output with status
`COMPLETED`. A crew of echoes therefore normalises to `completed`, every task complete — and **no
property of the result type can tell it from real model output**.

Closed by disclosure rather than by type: `engine_mode` is on every submit and poll response, and
mount logs a WARN.

### Removed — `AGNOSTIC_CREW_MAX_CONCURRENT_TASKS`, a knob that did nothing

Verified against the bundle: `agnosai_resource_budget_max_concurrent_tasks` has no reader outside
its own accessor and the budget serialiser, and `agnosai_orchestrator_budget` has **zero** call
sites. The field is stored, serialised, and enforced by nothing. Shipping it would have sold an
operator a concurrency ceiling that does not exist. `AGNOSTIC_CREW_TIMEOUT_SECS` is kept because
`max_duration_secs` genuinely *is* read, by `agnosai_orchestrator_timeout_secs`.

The ceiling that does work is per-request `max_concurrency` on process `parallel` — which is
accepted only alongside `parallel`, because a field that is accepted and then has no effect is the
same defect in miniature.

### Added — `scripts/check-log-lengths.py`, after two silent miscounts shipped

sakshi takes `(pointer, length)` pairs, so every log message's byte count is hand-written and
nothing checked it. Both failure modes are silent, and both were in one commit: one call declared
76 for a 75-byte message and shipped the **NUL terminator inside a JSON string**; another declared
45 for 46 and **truncated** the message by a character. Not a compile error, not a lint warning, and
invisible to suites that assert on handler behaviour rather than log text.

Wired into `check-clean.sh`. Mutation-verified: changing any declared length by one fails it.

### Changed — `check-symbols.sh` rule 3 now scans enum members on both sides

It compared only `^(fn|var)` against `lib/`. Cyrius enum qualifiers are **cosmetic** — `Backend.WASM`
and `KavachBackend.WASM` both resolve to the bare member `WASM` — so a `src/` enum member colliding
with a `lib/` one silently replaced it for the whole program, with no diagnostic from compiler or
linter. That is the same mechanism as the `BACKEND_COUNT` memory-safety defect below, in the one
declaration kind the gate did not cover. M2 adds ~50 enum members; all verified collision-free.

Mutation-verified: injecting a member named `AGN_CREW_ID` fails the gate, naming both sites.

### Added — a mount-time warning where the two size ceilings interact

A request body is parsed into the per-request arena, whose exhaustion policy is `ARENA_FULL_SPILL` —
overflow is satisfied from the global bump, which has **no `free()`**. The defaults make this
reachable (64 KiB arena, 1 MiB body limit), and the engine's own caps admit several megabytes of
entirely legal crew request. Not a startup failure, since the safe configuration depends on the
deployment; an operator gets a warning naming the arena size.


### Changed — agnosai 2.0.3 → 2.0.4, closing a memory-safety defect in this binary

Agnostic is the binary where the defect actually lived, because Agnostic is what links kavach and
ai-hwaccel together — transitively, through agnosai.

Both libraries defined `var BACKEND_COUNT`, 10 and 18. Cyrius has one flat symbol namespace with
last-definition-wins and is **silent** on a duplicate `var`, so the constant resolved to **18** while
kavach used it as the bounds check in `_backend_fp` over a **10-slot** table (`_backend_table[320]`
at `BACKEND_SLOT_SIZE = 32`). The guard admitted ids 0–17; `_backend_slot(17)` sits at byte 544, 224
bytes past the end, and `backend_dispatch_exec` then calls the result as a function pointer.
Renamed upstream to `KAVACH_BACKEND_COUNT` / `AIHW_BACKEND_COUNT` in kavach 3.11.15 and
ai-hwaccel 2.3.18, which agnosai 2.0.4 folds.

### Added — `tests/deps_symbols.tcyr`, a guard for the class rather than the instance

**14 assertions.** The instance is fixed upstream; this suite exists because *nothing caught it*.
The compiler warns on a duplicate `fn` and is silent for `var`, and every `check-symbols.sh` in the
ecosystem — including this repo's — scans `src/` only. A collision between two dependencies inside
`lib/` is therefore invisible to the compiler and the linter simultaneously, and Agnostic is the
repo where such a collision lands.

The suite pins both counts as distinct values, ties kavach's guard to its table's real slot count,
and records the out-of-bounds arithmetic the old value produced. Mutation-tested: three mutants —
restoring 18, resizing the table to 18 slots, and drifting an enum member — each killed.

⚠ It also pins the enum *members* (`PROCESS`, `WASM`, `OCI`, `NOOP`), because in Cyrius an enum
qualifier is **cosmetic** — `Backend.WASM` and `KavachBackend.WASM` both resolve to the member
`WASM`, asserted here directly. The upstream type rename therefore protected nothing on its own;
those members remain generic and unprefixed, and a future library defining `WASM` would collide the
same silent way.

### Fixed — `lib/vani.cyr` did not match the pinned toolchain snapshot

Pre-existing and unrelated to the dep bump: the vendored copy matched **no** installed toolchain, so
`scripts/check-clean.sh` failed at HEAD. `vani` is not in `[deps].stdlib` and `src/` has zero
references to it, but the snapshot check requires every file in the pinned snapshot to be present
*and* byte-identical, so removing it would fail too. Re-synced from the 6.5.32 snapshot.

⚠ Provisioning was done with the **pinned** toolchain binary rather than the PATH wrapper, which had
drifted to 6.5.33. `lib sync` and `deps` provision from the *installed* toolchain, not the manifest
pin, so syncing under drift is how a lock that CI cannot reproduce gets written.

### Added — M1, the HTTP foundation

The first milestone where untrusted bytes reach a buffer. **215 assertions across 7 suites**, 0
failed; all CI gates green. Verified live over a socket, not only under test.

- **`src/config.cyr`** — environment config, strictly parsed. A malformed value **refuses to start**
  rather than silently defaulting, because an operator discovering in production that
  `AGNOSTIC_PORT` never applied is worse than a startup failure that names the problem.
- **`src/strcase.cyr`** — ASCII case folding. The stdlib has no case-insensitive compare and
  `str_lower_cstr` allocates; comparing an env value to a literal should not.
- **`src/trace.cyr`** — thread-local W3C trace ids. sakshi's is a process global, so under a worker
  pool concurrent requests would overwrite each other's id and misattribute every log line.
- **`src/log.cyr`** — sakshi emit hook rendering one JSON object per event, formatter split out as a
  pure function so tests assert bytes without a pipe.
- **`src/http/{status,response,codec,router}.cyr`** — status vocabulary, handler return type,
  allow-list decoding, route table with a `:name` matcher.
- **`src/routes/health.cyr`** — `/health` liveness and `/ready` readiness with a check registry.
- **`src/server/serve.cyr`** — the sandhi adapter: arena/SPILL wiring, cstring→`Str` boundary,
  `signalfd` graceful shutdown.

### Decisions

- **ADR 0001** — health and readiness are separate probes. The oracle's `/health` pings Redis and
  RabbitMQ and 503s when they are down; under an orchestrator that manufactures an outage, since one
  Redis blip fails liveness on every replica and restarting cannot fix a dependency.
- **ADR 0002** — Daimon Tier 1 deferred. It cannot be implemented as written: daimon serves no agent
  heartbeat route, and registration for an externally-started process keys supervisor maps to pid 0.
  Zero first-party projects perform it at runtime, including the one the standard names as canonical.
- All six open port decisions closed — identity (own it thin, adapted from SecureYeoman's Cyrius
  probe), preset canon (Agnostic's is canonical), PDF (wait for `bayan_pdf_*`), release shape (one
  total release), Daimon (deferred), MCP transports (both shapes stand, on merit).

### Fixed — three oracle defect classes designed out, each locked by a mutation-tested assertion

- **Silent config fallback.** The oracle reused its u16 port parser for a rate limit, so any value
  above 65535 fell back to the default with no error. `parse_bounded` is deliberately a separate
  function; aliasing it back to `parse_port` fails two named assertions.
- **`extra='ignore'` field dropping.** Pydantic silently discarded 14 fields including `gpu_strict`,
  turning a hard-fail GPU requirement into a silent CPU fallback, and elsewhere ate an entire
  `tasks` array. Replacing the allow-list check with `return 1` fails
  *"an unlisted field is rejected, not silently dropped"*.
- **Liveness conflated with readiness.** See ADR 0001. The suite asserts `/health` stays 200 with a
  failing dependency registered.

### Fixed — two upstream defects avoided that the reference implementation still has

- `GET /health?probe=1` returns 200. AgnosAI never strips the query string, so its own health
  endpoint 404s for any caller appending a cache-buster.
- `/ready` reports a version **derived** from `${file:VERSION}`. AgnosAI hardcodes its equivalent and
  has reported 1.1.0 since shipping 2.0.x.

### Filed upstream

- `cyrius 2026-08-20-pkgver-not-visible-in-included-files` — `CYRIUS_PKG_VERSION` resolves only in
  the entry file's own text; any `include`d file referencing it fails to compile. That is where the
  symbol is least useful, since `/version` and `/ready` handlers live in modules. Worked around by
  threading it from `main.cyr` at mount, so the version stays derived rather than hardcoded.

## [0.1.0]

### Hardening — P(-1) pass complete

`first-party-standards.md:817` requires the audit-and-tighten pass before any feature work: *"Build
features on an unaudited foundation and every feature inherits the foundation's shortcuts."*
Exit criteria per `:869` all met — audit-clean, fmt/lint/vet/deny clean, security clean, baseline
benchmarks captured.

- `docs/audit/2026-08-20-audit.md` — the eight-point security process worked against the code that
  exists rather than the code that is planned. **0 CRITICAL / 0 HIGH / 0 MEDIUM / 2 LOW**, both LOW
  closed in the pass. Six of the eight points are N/A on a 34-line scaffold with no external input,
  no buffers, no file handling and no subprocess execution — so each N/A row records **which
  milestone re-opens it**, making the document a checklist for M1–M9 rather than a one-time
  clearance.
- `scripts/bench-history.sh` — written to the full four-clause contract at
  `first-party-standards.md:443-447`. The sibling implementation drops two of them: it records no
  commit hash (so a row cannot be attributed to code, defeating the point of a history trail) and
  emits no Markdown table. This one writes `date,version,commit,branch,benchmark,time_ns` and
  regenerates `BENCHMARKS.md` with human-readable units.
- Baseline captured — `noop` at 2 ns. This is the starting line for the 3-point
  baseline → optimized → current trend.

### Fixed — LOW-1, unprefixed globals in the generated harnesses

`cyrius init` emitted `var r = main();` into the bench and fuzz harnesses and `var exit_code` into
the test suite. Cyrius has one flat symbol table with last-definition-wins, and a test binary links
all of `lib/`, which exports ~180 unprefixed names.

Verified *not* currently exploitable — `lib/` declares no single-letter or `exit_code` globals — so
this was latent, not live. But the dependency set is about to grow by six packages, and the same
class caused a real upstream incident (four duplicated enum constants, three with different values,
three of them struct sizes passed straight to `alloc()`). Renamed to `_agnostic_{bench,fuzz,test}_exit_code`.

LOW-2 (exit-code masking in `.bcyr`/`.fcyr`, which do not clamp `& 0xFF` the way the `.tcyr` does)
was assessed and **accepted without a code change**: neither harness returns a failure count, so no
path to a value ≥256 exists. Recorded so the first harness returning a count adds the clamp.

### Added — roadmap through v1.0

`docs/development/roadmap.md` replaced its placeholder milestones with M0–M9 in dependency order,
each carrying its gates, its prerequisite repos, and the audit points it re-opens. Three decisions
are marked open and one milestone (M5, identity) is explicitly **blocked** on the user answering
it — per `cyrius/CLAUDE.md:66`, that is settled before the milestone opens rather than discovered
inside it.

### Added
- Initial project scaffold, generated by `cyrius init --language=none .` against
  the Cyrius 6.5.32 toolchain. The Python implementation is retained at
  `python-port/` as a behavioural oracle and is never built or shipped —
  see `ORACLE-AUDIT.md` for the 86 verified defects in it.
- Root docs the scaffolder does not emit: `CONTRIBUTING.md`,
  `CODE_OF_CONDUCT.md`, `SECURITY.md`. `SECURITY.md` is written for Agnostic's
  own surface (inbound API, delegated execution, targets under test, stored
  artefacts, credentials) rather than adapted from a sibling.
- `scripts/check-symbols.sh` and `scripts/check-clean.sh`, adapted from AgnosAI.
  Two inherited assumptions had to be removed: a `gen-presets.sh` generated-source
  check for a file this repo does not have, and a `deps --verify` step that
  assumed a lockfile — Agnostic declares no git deps yet, and
  `first-party-standards.md:135` makes "no lockfile" the documented default. The
  lock check re-arms automatically once a `[deps.NAME]` block appears.
- `[release]` manifest section declaring `bins` and `cross_bins`.

### Changed — CI raised to the first-party standard

The scaffolded `ci.yml` had a single 4-step job. It now carries the three jobs
`first-party-standards.md:364-386` requires — `build`, `security`, `docs` — with
fmt/lint/vet/deny via `check-clean.sh`, the symbol gate, a DCE build, ELF
verification, an aarch64 cross-build, and `cyrius bench` behind
`continue-on-error`.

`release.yml` gained the aarch64 build, made fatal rather than skipped: the
standard's DON'T list (`:963`) names "release without aarch64 builds" explicitly,
and a tagged release that silently ships one architecture is the failure that
guards against. Both binaries are now checksummed and attached, along with
benchmark results per `:419`.

⭐ **New gate: toolchain drift is fatal.** `cyrius lib sync --full` and
`cyrius deps` provision from the *installed* toolchain, not the manifest pin, so
a developer whose wrapper has drifted ahead writes a `lib/` and `cyrius.lock`
describing a version CI will never install — and every local build stays green
because the polluted lib agrees with the polluted lock. This is exactly how
AgnosAI 2.0.2 reached main with a 6.5.30-shaped lock under a 6.5.27 pin and lost
the entire stdlib in CI. The CLI already prints
`manifest-pin: X (drift — wrapper is Y)`; this treats that line as fatal in both
workflows. Mutation-verified in both directions: injecting a pin mismatch fails
the gate, restoring it passes.

Relatedly, the lockfile step **fails** on a mismatch rather than emitting a
`::notice` and continuing, which is what let the bad lock through upstream.

### Fixed
- The scaffolder's generated entry point declared `var r = main();` — a bare
  unprefixed top-level global in Cyrius's single flat symbol table.
  `check-symbols.sh` failed on it immediately; renamed `_agnostic_exit_code`.
  Filed against the toolchain rather than patched, together with the missing
  scaffold files and the absent `--language=python` port mode:
  `cyrius/docs/development/issues/2026-08-20-cyrius-port-language-python.md`.
