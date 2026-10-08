# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [0.1.15] — 2026-10-08

**Every agnostic-only item on the roadmap that needs no dependency move, and what the work found.**
No toolchain or dependency change: Cyrius 6.6.14, agnosai 2.1.6 and libro 2.10.6, with `lib/` and
`cyrius.lock` byte-identical to 0.1.14's.
- **One agnostic process per database file**, enforced at mount (ADR 0013's assumption).
- **The audit verdict says what it found over the whole trail** — `intact`, `restarts`, `altered`
  or `unverified` — and neither a failed write nor a failed read can break or fake it any more.
- **An interrupted crew keeps what its finished tasks answered** (ADR 0019).
- **Agent definitions have revisions** (`ETag`, `If-Match`, 412), and an agent's `complexity` is one
  of `low`, `medium`, `high`.
- **Request paths keep nothing on the global heap** of agnostic's own (libro's audit entry aside),
  held by a new suite.
- Smaller: a 405 names its methods; cancel answers 409 for a stored crew; results name their agent;
  `engine_mode` is sent once; Swarm Command 0.5.1 sends selection hints; the suites keep their
  stores under `TMPDIR`; `defer` may pair a lock again.

⚠ Wire-visible: new keys on `GET /api/v1/audit` (`verdict`, `breaks`, `break_count`) and on a
single definition (`etag`); `Allow` on a 405; 409 instead of 404 for cancelling a stored crew; 412
on a stale `If-Match`; 400 for an agent `complexity` outside the three; an interrupted crew's
`results` may be non-empty and its `error` text changed. ⚠ Operators: a second process on one
database refuses to start.

**32 suites, 2,701 assertions, 0 failed**, plus **80 JavaScript tests**; 0.1.14 had 31, 2,543 and 77.
Every suite also passed natively on aarch64 (Raspberry Pi 4) with the same per-suite counts.
Found on the way and filed or recorded, not worked around: cyrius resolves `CYRIUS_PKG_VERSION` one
include deep, not two (filed); patra reports an INSERT whose page write failed as stored, and libro
builds an audit entry per append on the global heap (both on the roadmap, upstream); and the
landscape review's "reviewer preset, no engine change" is wrong — agnosai's DAG hands a dependent
task nothing (roadmap, M6).

### Fixed

- **`GET /api/v1/crews/{id}` sent `engine_mode` twice for a crew this process holds** (0.1.9 to
  0.1.14). The route set this process's mode, then the ledger's description set the mode the crew
  ran under, and bayan's object set appends. The route now sets its own only when the ledger
  recorded none. `api/responses` (`tests/api_schema.tcyr`) now refuses a key written twice in any
  answer it drives; it compared keys as a set before. Mutation-checked: restoring the old line
  fails it by name.
- **A 405 names the methods its path takes** (`Allow`, RFC 9110 §15.5.6, which makes it a MUST).
  The router ORs the arms of every row whose path matched into the match record
  (`agnostic_route_match_allow`), and the 405 arm writes `Allow: GET, PUT, DELETE` from it, in the
  table's column order (`agnostic_route_allow_header_a`). The send path forwarded extra header
  lines only for a `Str` body, so it now forwards them for JSON too
  (`agnostic_response_set_headers`); a response that fails to encode drops them with its body.
  `router/table` holds every row's own path, sent each method it lacks and an unknown verb, to
  exactly its arms (78 probes); `serve/allow-on-405` (`tests/serve_mount.tcyr`) checks the header on
  the socket path, and that a 404 and a 200 carry none. Two mutations — the router not collecting
  the arms, the send path forwarding headers for text only — each fail by name.
- **Cancel answers 409, not 404, for a crew stored before a restart** (H4 follow-up). Cancel looked
  only at the ledger, so a crew from an earlier run — an `interrupted` one included — answered 404
  while `GET /crews/{id}` answered 200. A stored outcome is terminal, so cancel now answers 409 from
  the store, through the same scope check `GET` uses (`_agnostic_crew_stored_a`): another tenant's
  stored crew stays 404. `crews/interrupted-not-404` and `tenancy/interrupted` pin both; dropping
  the store check, or the scope check, fails a named assertion. ⚠ Wire-visible: a client that read
  404 as "from before a restart" now gets 409.

- **A failed audit write no longer breaks the chain.** `chain_append` moves the chain's head to the
  new entry before the store write; a write that failed left it there, so the next entry named a
  hash the store never got and the next start reported the trail altered. The head now goes back to
  the failed entry's predecessor. That is exact: every error `patrastore_append` can return comes
  before its row is written (libro refuses an over-long field before patra; patra's INSERT errors
  precede its page write — read in `lib/patra.cyr` 1.15.1). `audit/failed-write` (+9) refuses one
  write on an open store, then reopens: intact, every link in place. Mutation-checked.
- **An audit trail that could not be read was reported intact.** The open read it with libro's
  legacy `patrastore_load_all`, which answers an empty vec for a failed query, and an empty vec
  verifies clean: `intact: true` with nothing checked, and no head to link to. It reads with
  `patrastore_load_all_or_err` now; a failed read is `verdict: "unverified"`, `intact: false`, an
  ERROR line, and no head seeded (`audit/unverified`, +8, driven with the load's error object,
  since no suite can make patra's SELECT fail on an open store).

- **Request paths kept bytes on the global heap, which never frees.** Measured with `alloc_used()`
  around single dispatches, each from its own arena, on a mounted server with auth required: every
  refusal the router makes (413, 403, 404, 405, 401, 415) kept 16 bytes, its message's `str_from`
  header; a failed login 96 more — the password record split with `str_sub`, six headers; a
  successful login 344 — the JWT's five claim keys, the response's keys and values, the audit action
  and detail; an audited plugin-document write ~150 beyond libro's entry; and listing the
  definitions 152 — a global vec and a copy of every key. All of it now lives in the request's
  arena: the router's arms, `_agnostic_pw_field_a`, the login route and `agnostic_jwt_issue_a`'s
  keys, `agnostic_audit_detail_a` and `_agnostic_pdata_detail_a` (libro binds the detail into its
  write and the kept ring copies it, so nothing holds it past the request), and
  `agnostic_definitions_keys_a`. What an audited request still keeps is libro's: `chain_append`
  builds an entry per append (~250 B), which agnostic must have in hand to store, and libro 2.9.0's
  `chain_append_nokeep` returns none (roadmap, Upstream). A new suite, `tests/request_alloc.tcyr`
  (16), holds each of those paths to 0 bytes of agnostic's own, the second time each request is
  made; three mutations (the 404 arm, the record split, the key listing) each fail by name. The
  same sweep through the request decoders: the shared optional-field readers looked each key up
  through `str_from(key)` (16 B per read), the refusal messages and `agents[i]:` / `tasks[i]:`
  prefixes were built on the global heap, and the process and complexity wire names were
  `str_from`'d on every call; they use the C string, the arena, or a name interned at load now. A
  crew or definition body refused part-way still keeps the engine objects the decoder had built
  (roadmap, Memory).

### Added

- **The audit verdict says what it found, over the whole trail** (`GET /api/v1/audit`). libro's
  `verify_chain` stops at the first failure, so a broken trail reported one index and nothing after
  it: an alteration later in the file went unreported, and a trail written before 0.1.13 — one
  break after each restart that recorded something — could never say it was only that. The open
  (and `agnostic_audit_reverify`) now walk every entry and name each break: a **restart** (the
  entry hashes correctly and names no predecessor) or an **alteration** (a hash that does not match
  its content, a first entry naming a predecessor, a link to anything but the entry before it).
  New keys, always present: `verdict` — `intact`, `restarts`, `altered` or `unverified` —
  `break_count`, and `breaks`, the first 32 as `{index, kind}`. `intact` and `bad_index` keep their
  meaning (`bad_index` is the first break of either kind). A restart-only trail logs one WARN line
  instead of "the store was altered". ⚠ A restart break cannot show whether the entries just before
  it were deleted; `src/engine/audit.cyr` and architecture 001 say so. `audit/restart-breaks` (+18)
  writes a trail the way a release before 0.1.13 did, then alters an entry after its break: the
  walk finds both. Three mutations — no head restore, a walk that stops at the first break, no
  restart kind — each fail by name. The schema snapshot gained the three keys.
- **The Audit view 0.1.1** reads the verdict: **RESTART BREAKS** as a warning that names the first
  and says no alteration was found; **BROKEN** naming the first *altered* entry and how many breaks
  there are in all; **UNVERIFIED** when the server could not read the trail. Against a server
  before 0.1.15 it reads `intact` and `bad_index` as before, and no longer says "altered" about a
  break it cannot classify. (`chainVerdict`, `audit.test.mjs` +1.)
- **One agnostic process per database file, enforced** (H4 follow-up; ADR 0013, architecture 001).
  Since 0.1.13 a second process on one `AGNOSTIC_DB_PATH` was destructive, not merely racy: its
  start-up sweep would mark the first process's live crews `interrupted`. Mount now claims the file
  first, before the engine starts or anything opens: an exclusive, non-blocking `flock` on a
  `<db>.owner` sidecar (`agnostic_store_claim`), opened `O_CLOEXEC` and held until the store closes
  or the process ends. A second process logs `another agnostic process holds this database; refusing
  to start` and exits; a sidecar that cannot be created refuses to start too. `restart/one-process`
  (`tests/restart.tcyr`, +13) holds a claim from a separate open, as another process would, and
  checks that mount refuses, opens nothing and sweeps nothing; that the claim is idempotent,
  exclusive, close-on-exec and given up by closing the store. Three mutations — no claim in mount, no
  `O_CLOEXEC`, no release on close — each fail by name. ⚠ Operators: a rolling update on one volume
  must stop the old process before starting the new one. The `.owner` file is left in place on
  purpose.
- **A task result names its agent: `agent_key`** (found at 0.1.14). Since agnosai 2.1.5 every
  result the model answered carries its agent's key in the engine's metadata (agnosai ADR 022);
  agnostic picks result fields by name and did not take it. It is `agent_key`, the name the plan's
  `selection.winner` uses (ADR 0016), so a watcher can check the choice against the outcome. Absent
  on a placeholder, failed or cancelled task, and on one the engine assigned no agent; never the
  engine's own key name, and never a non-string. `outcome/agent` (`tests/outcome.tcyr`, +6);
  mutation-checked. Stored outcomes carry it from now on. Additive on the wire.
- **Agent definitions have revisions** (found at 0.1.10). The Library edited a definition with a
  last-writer-wins `PUT`, so of two editors the second silently undid the first. A single
  definition now answers its revision — `etag` in the body and an `ETag` header, on `GET`, `POST`
  and `PUT` — in the plugin documents' format (`"` + the first 16 hex digits of the SHA-256 of the
  canonical document + `"`), so the shell's bridge carries it unchanged. `PUT` and `DELETE` honour
  `If-Match` (`*` means "it exists"): a stale one is **412** with code `revision`, checked before the
  body is read (RFC 9110 §13.2.1; an absent definition is still 404) and again under the store lock
  with the write (`agnostic_definitions_replace_if_a`, `_remove_if_a`). The revision is defined over
  the canonical rendering, so a row an older release wrote with other spacing reads the same.
  `router/definition-revisions` (+18); the schema's header probes now cover six headers, and the
  probe phase opens the definitions table. Two mutations — a precondition that always holds, no
  check before the body — each fail by name. Additive on the wire.
- **The Library view 0.1.1** sends the revision it read as `If-Match` when it saves or deletes a
  definition, and on a 412 keeps the edits in the editor and says someone else changed it
  (`library.test.mjs`, +1 test).
- **An agent's `complexity` is one of `low`, `medium` or `high`** (ADR 0017's follow-up). It was
  free text, which agnosai's selector reads as medium when it does not recognise it — the silent
  default a task's hint has refused since 0.1.14. A crew's `agents` and a definition's `POST` and
  `PUT` now refuse any other value with a 400 naming the three (`agnostic_agent_def_complexity_ok`).
  The decoder still accepts one, because stored definitions are decoded by the same path: a
  definition written earlier with another value is read as it is, and must be given one of the
  three before it is saved again or sent in a crew. All 76 preset agents use `high` or `medium`, and
  the Library's editor already offers the three. `request/agent-complexity` (+7),
  `router/definition-complexity` (+7, including a stored legacy value read after a restart). Each
  door mutation-checked. ⚠ Wire-visible: a value outside the three is now refused.
- **Swarm Command 0.5.1 sends selection hints** (ADR 0017's follow-up, M9). A live swarm's crew
  gave the engine nothing to choose agents by, so the first agent took every task whatever its
  role. With the role roster each agent now carries `domain` (its role) and `tools` (the kinds the
  role uses, most-used first, only those switched on), and each task the matching `domain` and
  `required_tools` (`roleTools`, `specToCrewRequest`). Coder and reviewer use the same kinds, so the
  tools tie and the domain decides. A preset roster sends none: its domains name no swarm role, and
  an agent with no domain would win every hinted task. `swarm.test.mjs` +1 (mutation-checked);
  `request/swarm-roles` (`tests/crew_request.tcyr`, +4) runs the same shape through the engine's
  own ranking: the review goes to the reviewer, the code to the coder, the plan to the planner. The
  simulator is untouched, so every estimate is what it was.
- **The Crews view 0.1.2** takes a result's `agent_key`, so a finished crew, or one whose events are
  no longer held, says which agent did each task (`crews.test.mjs`, +2 assertions).

- **An interrupted crew keeps what its finished tasks answered**
  ([ADR 0019](docs/adr/0019-an-interrupted-crew-keeps-what-its-finished-tasks-answered.md); H4
  follow-up). Since agnosai 2.1.5 every task the model answers sends one `token` event with its
  whole output, and agnostic kept none of it, so a crash after three of five tasks lost all three.
  The ledger's drain now collects those events (`agnostic_ledger_drain_a`,
  `agnostic_ledger_is_final_token`), the refresh keeps each output once the ledger lock is released
  (`_agnostic_crew_keep_finals`), into a new table, `agnostic_crew_partial` (no index, as the
  in-flight one has none), only for a crew with an in-flight row and no stored outcome. The outcome
  write deletes them beside the in-flight row; the start-up sweep writes them into the interrupted
  crew's `results` (each `completed`, its output, no usage) and `task_count`. Its `error` now says
  "the server restarted before this crew finished; tasks still in progress were lost". One more
  fsync per answered task. `crewstore/partials` (+23) and `crewstore/refresh-keeps` (+4); three
  mutations — no fold into the outcome, no clearing on the outcome write, a token not checked for
  `complete` — each fail by name. The Crews view and Swarm Command already settle tasks from an
  outcome's results, so neither changed. ⚠ Wire-visible: an interrupted crew's `results` may be
  non-empty, and its `error` text changed.

### Changed — tests and tooling

- **The suites' stores live under `$TMPDIR`, one set per run.** 16 suites named 23 fixed
  `/tmp/agnostic-*.patra` paths, and the benchmarks two more: two runs at once (two worktrees, two
  sessions) shared each file, `TMPDIR` was ignored, and most suites unlinked only before use, so a
  full run left 17 files behind. `tests/support/tmp.cyr` (new, shared by every suite and the bench)
  builds `$TMPDIR/agnostic-<tag>.<pid>.patra`, `/tmp` when `TMPDIR` is unset, and each suite removes
  its stores, and a mount's `.owner` claim, at the end of `main` (`_tt_unlink_store`).
  `tests/api_schema.tcyr`'s own helper, the shape this follows, now calls it. `check-clean.sh`'s fmt
  and lint sweeps cover `tests/**/*.cyr`. ⚠ The bench's in-flight store follows `TMPDIR` too, so its
  fsync half measures whatever filesystem that is; compare figures from the same one.
- **`defer` may pair a lock's enter and exit again.** cycc 6.6.6 dropped a pending `defer` on
  `return f(...)` (filed 2026-09-26), so the rule was never to pair them; cyrius 6.6.7 fixed it.
  `rlock/ownership` (`tests/store_concurrency.tcyr`, +5) now defers an exit and leaves through two
  tail-call shapes, pinning the fix at the pin; `src/engine/rlock.cyr` and handoff §5 lift the rule.
  The store wrappers keep their explicit shape, which `check-store-lock.py` reads.
- **The `CYRIUS_PKG_VERSION` setter stays, for a new reason.** cyrius 6.5.34 made the constant
  resolve in a file the entry includes, but not one include deeper, which is where
  `src/routes/health.cyr` is (via `src/app.cyr`); measured at 6.6.14, 6.6.19, 6.7.2 and 6.7.3. Filed
  with cyrius as `2026-10-07-pkgver-not-visible-in-nested-includes.md`, with a reproduction. The
  comments that said "only in the entry file" now say this.
- **`docs/development/handoff.md` §1 is a short orientation that no longer grows per release** — a
  milestone table and the standing warnings, linking the CHANGELOG for history and `state.md` for
  figures — and its header's per-release refresh log is gone.
- **No warning on our own code, suites included.** `tests/jwt.tcyr`'s `sig` was typed `Str` by its
  initialiser and then assigned an untyped result ("assigning non-pointer to typed pointer"); it is
  declared `: i64`, as `serve.cyr` did at 0.1.12.

## [0.1.14] — 2026-10-05

**Re-pin to agnosai 2.1.6 — 2.1.5's three consumer halves, plus selection hints on a task, and the
fixes an adversarial review of all of it found, five of them in agnosai itself.**
- **The plan explains each task's agent** (F7, ADR 0016): `GET /api/v1/crews/{id}/plan?explain=selection[&task=N]`.
- **A task can say what its agent needs** (ADR 0017): `required_tools`, `complexity`, `domain` and
  `gpu_required` on each task of `POST /api/v1/crews`. Before this, agnosai's selector could tell
  agents apart only by complexity, and the first medium agent won every task.
- **A crew joins its request's trace, and spans can leave the process** (F6, ADR 0018): each crew
  carries the request's `traceparent`, and `OTEL_EXPORTER_OTLP_ENDPOINT` switches on OTLP export.
- **Crew status and events say what happened** (B17, agnosai ADR 022), and agnostic's status never
  goes backward even where agnosai's now can.
- **Inference calls and span export are bounded** (agnosai 2.1.6): each posts from a reused arena
  under finite timeouts, where 2.1.5 left ~256 KiB on the never-freed heap per call and could wait
  forever. `AGNOSTIC_LLM_TIMEOUT_SECS` sets the inference ceiling.

⚠ Wire-visible, all additive except the traceparent check: two query parameters and two optional
keys on the plan route; four optional fields on a task, which also appear in the plan; a
`complexity` vocabulary in the schema; a stricter inbound `traceparent` (a value agnosai would
refuse is now replaced, as a malformed one always was); `token` events for every LLM-answered task,
and parallel/DAG events per batch (agnosai's change). ⚠ A malformed `OTEL_EXPORTER_OTLP_ENDPOINT`
now refuses to start.

**31 suites, 2,543 assertions, 0 failed** — on x86_64 under the 6.6.14 pin and natively on aarch64
(the Raspberry Pi, Ubuntu 26.04.1) — plus **77 JavaScript tests**; 0.1.13 had 31, 2,347 and 77.
Cyrius 6.6.14 and libro 2.10.6 are unchanged; the lock moved by agnosai's line alone.

### Changed — re-pin to agnosai 2.1.6

- **`[deps.agnosai]` 2.1.4 → 2.1.6.** Neither 2.1.5 nor 2.1.6 changed a dependency: their
  `cyrius.cyml` and `cyrius.lock` are byte-identical to 2.1.4's, so `cyrius.lock` moved by exactly
  two lines — the agnosai commit pin and `lib/agnosai.cyr`'s hash, which is byte-identical to the
  tag's `dist/agnosai.cyr`. 119 files, 9 commit pins. The work was first done and tested against
  2.1.5 (tag `5855060`); 2.1.6 was released from what the review below found.
- agnosai 2.1.5 renamed its GenAI span functions (its *Breaking*); agnostic called none of them.
- Two stale lines the roadmap scheduled for this re-pin: the `cyrius.cyml` paragraph about which
  sigil the chain declares (all of it declares the 3.13.7 fold since 0.1.12), and `CONTRIBUTING.md`
  asking for `rustc --version` (now `cyrius --version`).

### Changed — crew status and events say what happened (B17, agnosai ADR 022)

What agnosai 2.1.5 changed, as an agnostic client sees it:

- A `parallel` or `dag` task's `task_started` arrives when its batch starts, and its
  `task_completed` as it is joined, in dispatch order — so a `task_started` can follow a
  `task_completed`. Before, a whole wave was announced up front and completed after its last batch.
- Every task the model answers sends its `token` event in every process (before: sequential only),
  and `token` events name their crew.
- A timed-out crew's `crew_completed` says `failed`, as its outcome always did.
- The engine's registry now says RUNNING while a crew runs, and on one error arm goes back to
  PENDING.

What agnostic changed for it:

- **`agnostic_ledger_note_started`.** The registry stores RUNNING just before the runner publishes
  `crew_started`, so a poll could see `running` before the event is collected — `running` with no
  `started_at`. The start is now recorded at whichever comes first. And since a recorded start
  reads an engine PENDING as RUNNING (`agnostic_crew_live_status`, 0.1.9), the registry's new
  RUNNING → PENDING edge never reaches agnostic's wire: agnostic's status only moves forward. The
  edge is unreachable through agnostic anyway — dependencies are range-checked indices and cycles
  are refused — and `ledger/registry-running` holds the ledger to it regardless.
- Comments that said "the registry never reports RUNNING" or "returns 0 on exactly one arm"
  (`crew.cyr`, `ledger.cyr`, `request.cyr`, `crew_request.tcyr`, `ledger.tcyr`), and two
  `lib/agnosai.cyr` line citations, now say what 2.1.5 does. ADR 0009 has a dated note.
- **Swarm Command** (comments only, still 0.5.0): its event map no longer says the engine announces
  a whole wave at once or that parallel crews send no tokens. Its queued-unit fallback stays, for a
  crew whose `task_completed` events were missed.
- **SKILL.md** §6: tokens come from every task the model answers; a `task_started` can follow a
  `task_completed`; the timeout caveat is gone.

### Added — why each task got its agent: `/plan?explain=selection` (F7, ADR 0016)

- **`GET /api/v1/crews/{id}/plan?explain=selection`.** Each task gains `selection`, agnosai's
  rendering of its ranking: `winner` (`index`, `agent_key`), `candidate_count`, and `candidates`,
  best first, each with its `total` and the five `scores` it folds — `tool_coverage`, `complexity`,
  `gpu`, `domain`, `personality`. The answer gains `scorer` (the five `weights`, and `unmeasured`:
  personality, until agnosai ports bhava) and `candidate_limit`. The floats are agnosai's raw f64s:
  Σ weight × score in the listed order is `total` exactly.
- **`&task=N`** explains only task `N` (its `index`), over the whole roster.
- **Recomputed, not recorded.** agnosai keeps only each task's winner; selection is a pure function
  of the roster and the task, so recomputing it is exact, and `candidates[0]` is the agent the task
  ran with — `crews/plan-explain` checks each task's winner against the agent its `task_started`
  event named. agnosai names the changes that would end this (hierarchical delegation,
  learning-driven selection, a stateful personality); ADR 0016 says what then replaces it.
- **Bounded.** Scoring every agent against every task is up to 5.6 MB at the request caps, and the
  request arena spills to memory that is never freed. So scoring runs in one 32 KiB scratch built at
  mount, reset per task under its own mutex, and only the rendered candidates go into the request's
  arena: 256 per answer (`AGNOSTIC_EXPLAIN_MAX_CANDIDATES`), shared equally between the explained
  tasks and never fewer than the winner — so one answer explains at most 256 tasks, and a larger
  crew is explained a task at a time (`&task=N`; without it, a 422 saying so). Fifty explanations
  allocate nothing on the global bump.
- **Refused, 422:** `explain` other than `selection` (empty included), a `task` that is not a
  non-negative integer, `task` without `explain`, a `task` past the crew's last, and a whole crew of
  more than 256 tasks without `task`. Another tenant's
  crew is 404, explained or not.
- The router hands the plan route its raw path, as it does the events route. The schema declares
  `explain` and `task` and the keys `scorer?` and `candidate_limit?`; `api/probes` now knows eight
  query parameters and checks six names the other way.

### Added — a task says what its agent needs: selection hints (ADR 0017)

The user's decision of 2026-10-04, open since 0.1.13.

- **Four optional task fields**, each checked strictly, because agnosai reads each one silently:
  - `required_tools` — an array of tool names of 1 to 256 bytes, at most 64. Anything but strings in
    it is a 422 (the engine would read it as no requirement and score every agent full coverage).
    `[]` is no requirement.
  - `complexity` — `low`, `medium` or `high`; anything else is a 400 (the engine would read it as
    medium). A new schema vocabulary, `vocabularies.complexity`.
  - `domain` — 1 to 256 bytes, compared with each agent's ignoring case.
  - `gpu_required` — a boolean.
- **Forwarded into the engine task's context** under the selector's own keys
  (`_agnostic_task_spec_hints`); a hint left out writes nothing, so a request without hints selects
  exactly as 0.1.13 did. `request/hints` shows each hint alone moving a task to the agent that
  matches it.
- **Shown back** on `GET /api/v1/crews/{id}/plan`, each task with the hints it was given.
- ⚠ **The model reads the hints.** agnosai renders a task's whole context into its prompt, so a
  hinted task's prompt carries them (and hoosh caches on that request body). SKILL.md says so.

### Added — one trace from request to tool, and OTLP export (F6, ADR 0018)

- **Each crew joins the trace of the request that submitted it**: `agnostic_crew_submit_owned`
  calls `agnosai_crew_with_trace_parent(spec, agnostic_trace_current())`, so the crew's
  `invoke_workflow`, `invoke_agent`, `chat` and `execute_tool` spans are children of the request's
  `traceparent`, under the trace id every log line of the request carries.
- **OTLP span export** starts when `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` (a complete URL, as-is) or
  `OTEL_EXPORTER_OTLP_ENDPOINT` (a base URL, `v1/traces` appended — agnosai 2.1.6) is set;
  `OTEL_SERVICE_NAME` names the service, `agnostic` by default; `OTEL_EXPORTER_OTLP_HEADERS` is read
  by agnosai's exporter. It uses `agnosai_telemetry_init_export`, which leaves agnostic's log hook
  and level alone; it starts after the signal mask and is flushed and stopped when the server stops.
  Off, nothing is built.
- ⚠ **A malformed endpoint refuses to start**, like a malformed `AGNOSTIC_*` value: the exporter
  ignores every answer, so a typo would otherwise lose every span silently. The check is sandhi's
  own URL parser, plus no userinfo, query or fragment.
- ⚠ **The inbound `traceparent` is checked by agnosai's own parser**
  (`agnosai_otlp_span_context_parse_a`: W3C Trace Context Level 1, version `00`, lowercase hex,
  non-zero ids), where 0.1.13 checked its length. A value agnosai would refuse is replaced by a
  minted one, so a request's logs and its crew's spans never land in different traces. Minted ids
  are forced non-zero.

### Fixed at review — and in agnosai 2.1.6

An adversarial review of the work above (five lenses — B17, F7, hints, F6, docs — each finding
re-derived by an independent skeptic: 15 confirmed, 0 refuted) found:

- **In agnosai 2.1.5, fixed at the source as 2.1.6:**
  - its OTLP exporter left ~258 KiB of RSS per batch on the never-freed global bump and had no
    timeouts, so a collector that never answered blocked it — and the server's stop — for good;
    its two flushers could share one batch's memory; and it read a generic endpoint with a path
    as a complete URL, so `https://gw/otlp` posted to `/otlp`;
  - its inference call had the same leak (~256 KiB per call, plus five parse trees of the answer)
    and no timeout at all — a hung gateway held a task forever;
  - a `dag` crew with a failed branch beside a successful one took its deadlock arm, so in
    agnostic it read `running` forever — never finished, never stored, swept every 200 ms;
  - cancelling a crew that had just finished relabelled it `cancelled`, and agnostic then reported
    its completed results under that status.
- **In agnostic:**
  - `?explain=selection` on a crew of more than 256 tasks rendered past its budget: the whole crew
    is now a 422 naming `&task=N`, and any one task still answers;
  - an agent's `"domain": ""` made it lose every task that named a domain: it is read as no domain;
  - a task's hints could exceed the engine's 50,000-byte prompt-context cap, which agnosai cuts
    silently: tool names and the domain are capped at 256 bytes, and the rendered hints are
    measured exactly as the engine renders them (failing closed when they cannot be);
  - the OTLP endpoint check let through URLs the exporter cannot use (no host, userinfo, a query,
    an upper-case scheme with no path): it now also refuses userinfo, query and fragment and asks
    sandhi's own URL parser;
  - a concurrent refresh could latch a stale `pending` over `running`: the latch itself reads a
    PENDING over a recorded start as RUNNING;
  - a start collected after a crew was cancelled was stamped after its finish (a negative run time
    in both views): no start is stamped once a crew has finished;
  - a cancel could land on a crew the engine had already finished, inside the collector's 200 ms:
    the cancel refreshes first, and answers 409 if the engine got there first;
  - `serve_mount` read `OTEL_EXPORTER_OTLP_ENDPOINT` from the shell running it: its "off" case is
    off by construction.
- **Configuration that came with 2.1.6:** `AGNOSTIC_LLM_TIMEOUT_SECS` (1–86400; 0 or malformed refuses
  to start) sets the inference call's whole-exchange ceiling and bounds its connect (10 s) and
  per-read (300 s) ceilings by it; unset keeps agnosai's 600 s. `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`,
  a complete URL, is read as-is and wins over the generic base.


### Tests

**+196 assertions, all in existing suites** (2,347 → 2,543; 31 suites).

- `tests/crews_route.tcyr` +70: `crews/plan-explain` (every task's winner is the agent its
  `task_started` named; the scores fold to `total`; `&task=N`; each refusal), `plan-explain-limit`,
  `plan-explain-budget` (fifty explanations allocate nothing on the global bump; a crew past 256
  tasks is a 422 without `task`, and any one task still answers), `plan-hints`, `trace-parent`
  (the crew carries the request's own traceparent, copied out of the request's arena; a crew
  submitted outside a request is a root trace), `cancel-refreshes` (a crew the engine finished
  before the ledger saw it is refused, stays completed, and its start is no later than its
  finish), `llm-timeout`.
- `tests/crew_request.tcyr` +44: `request/hints` (each hint alone moves a task to the agent that
  matches it; each malformed one refused, 400 or 422, never read as a default), `request/empty-domain`, and the hint bounds,
  including rendered hints past the engine's prompt-context cap and an arena too small to measure
  them (refused, never let through).
- `tests/config.tcyr` +33: `config/otlp_endpoint` (scheme in any case, a host required, userinfo,
  query and fragment refused, the per-signal endpoint winning and used as-is) and
  `AGNOSTIC_LLM_TIMEOUT_SECS` (1–86400; 0 or malformed refuses to start).
- `tests/ledger.tcyr` +17: `ledger/registry-running` (RUNNING before `crew_started`, and an engine
  PENDING after a recorded start, both read as `running` with `started_at`), a stale `pending`
  never latched over `running`, and no start stamped after a finish.
- `tests/trace.tcyr` +14: `trace/valid`, agnosai's parser on the W3C shape, and minted ids non-zero.
- `tests/serve_mount.tcyr` +11: `serve/telemetry` — with no endpoint nothing is built and no span
  recorded; a generic endpoint is a base (`v1/traces` appended) and a per-signal one is used as-is;
  stopping clears the process's exporter; the "off" case no longer reads the caller's shell.
- `tests/api_schema.tcyr` +3 (eight query parameters, six checked by name both ways; the
  `complexity` vocabulary; the explained plan in the responses sweep — its cancel probe now holds a
  1,000-task crew, since 2.1.6 refuses to cancel a crew that has finished), `tests/router.tcyr` +2
  (the plan route resolves with a query and is handed the raw path), `tests/crew_tenancy.tcyr` +2
  (another tenant's crew is 404, explained or not).

### Verified

- **Live, with the release binary** (DCE, x86_64), a stub OpenAI-compatible gateway and a stub OTLP
  collector on loopback:
  - A two-task crew submitted with `traceparent: 00-4bf92f35…-00f067aa0ba902b7-01`, one task hinted
    `required_tools: ["scanner"]`, `domain: "Security"`, `complexity: "high"`, completed with both
    results and metered usage. `/plan` showed the hints back; `?explain=selection` named
    `sec-auditor` for the hinted task (0.925 against 0.342) and `web-tester`, the first medium
    agent, for the other — the agents each `task_started` event named.
  - `explain=nope`, `task` without `explain` and a `task` past the last each answered 422.
  - Cancelling the finished crew answered 409; a crew held in its inference call answered `running`,
    was cancelled (200, `cancelled`, with `started_at` and `finished_at`), and a second cancel
    answered 409.
  - With `OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:<port>/otlp` the collector received
    `POST /otlp/v1/traces`, `application/json`, `service.name` from `OTEL_SERVICE_NAME`. The crew's
    `invoke_workflow` span carried the inbound trace id with the inbound span id as its parent, and
    its `invoke_agent` and `chat` spans descended from it. A crew sent an all-zero trace id ran in a
    minted trace instead.
  - With `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=…/custom/traces` beside a generic endpoint, every span
    went to `/custom/traces`, as-is.
  - SIGTERM drained, flushed the exporter and exited 0. An endpoint with userinfo, and
    `AGNOSTIC_LLM_TIMEOUT_SECS=0`, each refused to start (exit 1, naming `AGNOSTIC_*` and
    `OTEL_EXPORTER_OTLP_*`).
- **Natively on aarch64** (the Pi): every suite, cross-built from this tree, with the counts above;
  the server binary answers `help` 0 and a usage error 2.
- **Certified** in a sibling-free replica with an empty dep cache, CI's steps in CI's order: `lib/`
  and the lock reproduced byte for byte, `lock-check.sh --no-resolve`, symbols, the DCE build, the
  API schema on the binary, `check-clean.sh`, the command line's exit codes and the aarch64
  cross-build. agnosai 2.1.6 was certified the same way before its tag (99 suites, 8,611
  assertions, coverage 99%).

### Docs

- ADRs **0016** (a selection explanation is recomputed at read time), **0017** (a task carries
  selection hints) and **0018** (crews join the request trace; export is opt-in); a dated note on
  **0009** for agnosai's B17.
- `skills/agnostic/SKILL.md`: events (§6), `?explain=selection` (§7), the four hints and that the
  model reads them.
- `docs/api/README.md`'s Known gaps; `docs/api/generated/schema.json` regenerated.
- `docs/development/roadmap.md` is forward-facing only from this release (1,058 lines to 633):
  shipped items are removed rather than ticked (they are in this file), settled decisions are kept
  in one section, and open items, grouped by area, keep their reproduce steps and fix direction.
  The comments and docs that pointed at its removed sections now point at where each item lives:
  `request.cyr`, `audit.cyr`, `presets.cyr`, Swarm Command's estimator comment (with
  `src/webgui_data.cyr` regenerated), `check-skill.py`, `check-clean.sh`, `handoff.md`,
  `CONTRIBUTING.md` and ADR 0018.
- `docs/development/handoff.md` §1 gained 0.1.11–0.1.14 and §6 the 2.1.6 pin; `state.md` refreshed;
  `CONTRIBUTING.md` asks for `cyrius --version`.

### Known

- agnostic exports no span of its own, so when it mints the traceparent the crew's workflow span
  names a parent that is never exported (ADR 0018). Recorded on the roadmap.
- An exporter batch still leaves ~480 B, and an inference call ~2.6 KB including the reply it keeps,
  on the global bump: sandhi's own dispatch path (16 B is the stdlib's `sockaddr_in`). Recorded on
  agnosai's roadmap, to be filed with sandhi.
- An agent definition's `complexity` is still free text (ADR 0017). Recorded.
- cyrius **6.6.15** is tagged, with TLS 1.3 fixes (CVE-70, CVE-71) that reach agnostic's outbound
  HTTPS. It needs kavach, libro, bote and agnosai released on it first; the plan is on the roadmap.

## [0.1.13] — 2026-10-04

**A crew a restart cut short is `interrupted`, and the binary describes its own HTTP API** — a crew
accepted and never finished when the process stopped is, from the next start, in the terminal status
`interrupted` instead of a 404 (H4, ADR 0013; ⚠ a new status value on the wire, and one agnostic
process per database file is now load-bearing); `agnostic api schema` prints the HTTP API as one JSON
document built from the server's own tables, and a committed snapshot the suite and CI check freezes
it (H5, ADR 0015; ⚠ the binary now reads its arguments, and one it does not know exits 2 where 0.1.12
ignored it and served); `skills/agnostic/SKILL.md` teaches a coding agent to drive agnostic, checked
against that schema (H6); and Swarm Command 0.5.0 prices one agent at the swarm's own token spend
beside every estimate, labelled SIM, with every existing estimate unchanged bit for bit (B3, ADR
0014). H3 is closed with no wire change: 0.1.9 already delivered the event cursor's gap as `missed`,
now pinned over HTTP and in both views. Two older defects H4 found are fixed: the audit chain links
across a restart, where each process's first entry named no predecessor and the next start reported
an untouched trail as altered (⚠ a trail written before 0.1.13 keeps its breaks); and a crew named
over 255 bytes stores its outcome, where none was stored and it answered 404 after a restart.

**31 suites, 2,347 assertions, 0 failed** — on x86_64 under the 6.6.14 pin and natively on aarch64
(a Raspberry Pi, Ubuntu 26.04.1) — plus **77 JavaScript tests** under Node; 0.1.12 had 29, 1,885 and
61. Cyrius 6.6.14, agnosai 2.1.4 and libro 2.10.6 are unchanged from 0.1.12, and `lib/` and
`cyrius.lock` are byte-identical to it.

### Added — a crew a restart interrupted answers `interrupted`, not 404 (H4, ADR 0013)

- **Status `interrupted`.** A crew that was accepted and had no stored outcome when the process
  stopped is, from the next start, in the terminal status `interrupted`. `GET /api/v1/crews/{id}`
  answers it with 200, the listing shows it, and the audit trail records it. It is
  `AGNOSTIC_CREW_INTERRUPTED` = 6. The number is stored in `cstatus`, so it was appended, and no
  status is ever renumbered. `agnostic_status_is_terminal`, `agnostic_outcome_is_terminal` and
  `agnostic_crew_status_to_wire` know it. The ledger never holds it.
- **`agnostic_crew_inflight`, the ninth table.** Submit writes one row per accepted crew: its id,
  scope, name, `submitted_at`, task count, engine mode and process. The row has **no status
  column** and **no index**.
  - `_agnostic_crews_save_row_locked` deletes the row in the critical section that writes the
    crew's outcome, so the cancel latch, the collector and a poll all clear it.
  - `agnostic_crews_mark_inflight` writes nothing for a crew whose outcome is already stored, so a
    crew that finishes before it is marked leaves no row.
  - If the mark cannot be written, it is logged at ERROR and the crew still runs, the same rule
    `_agnostic_ledger_persist` follows.
- **The start-up sweep (`agnostic_crews_interrupt_inflight`).** `agnostic_serve_mount` runs it after
  the audit chain opens and before the server listens, so no request (`/ready` included) is
  answered until it is done. For each row left, it writes a terminal outcome through the ordinary
  write-once path (`agnostic_crews_interrupt_row`), with a listing row and a **`crew.interrupted`**
  audit entry (WARNING, `crew_id=…`), and logs the count at WARN.
  - A crew whose outcome was already written keeps it, and only its row is deleted.
  - A write that fails keeps its row for the next start.
- **What an interrupted crew says.** Its document has `results: []`, `task_count` 0, zero `usage`,
  and an `error`: "the server restarted before this crew's outcome was recorded; its work was
  lost". It keeps `name`, `scope`, `engine_mode`, `process`, `tasks_submitted` and `submitted_at`,
  and adds **`interrupted_at`**. It has **no `started_at` and no `finished_at`**, because the
  downtime is not run time. There are no finished-task results to keep: while a crew runs,
  agnostic holds none.
- **`GET /api/v1/crews?status=interrupted`**, and the 422 text lists it.

### Added — Swarm Command 0.5.0: one agent at the same token spend, beside every estimate (B3, ADR 0014)

- **A one-agent baseline in every estimate.** On each of the estimator's seeds, `estimateSpec` now
  also runs `soloRun`: one agent working the swarm's own plan for that seed — the same tasks and
  fan-out counts, built by the same `sc.build` on the same RNG — one task at a time. Each task gets
  its role's model, rate, tools and region, under the same failure model. There is no orchestrator,
  no coordination and nothing in parallel.
  - **Its budget is the tokens the swarm spent on that seed**, paired run by run. A work step, or a
    tool result larger than what is left, is cut where they run out, for its share of the work, so
    a run that ran out spent all of them. What is left counts as unreached. Ratios to the swarm are
    taken per seed, then the p50.
  - It is **its own model, not the Sim with one agent allowed** (`maxActive = 1` is still a swarm:
    an orchestrator, coordinating leads, a fresh agent per sub-task). Every number it restates from
    the Sim's agent — 34, in 20 entries, from eleven Sim methods — is in one `SOLO` block, each
    entry naming its method; a test fails, naming the entry, when the Sim's own number changes.
  - A fan-out lead that fails before its split never makes its parts, as in the Sim, which creates
    them at the split: one task failed, as the swarm counts it.
- **Stored as `estimate.solo`**: tokens, cost and time (p50; cost also min and max, time also max),
  the ratios to the swarm, failed and unreached tasks per run, and how many runs ran out of tokens
  or were cut off. `normalizeEstimate` reads it back, clamped. An estimate saved by 0.4 reads back
  with `solo: null`. There is no spec version change, and it adds about 330 bytes to a swarm.
- **Shown, labelled SIM.**
  - The library card adds a line: "1 agent, same tokens: ≈ $X · mm:ss (N× the swarm's time)", and
    "out of tokens in k (x.x tasks left / run)" when that happened, since such a run's time and
    cost cover only the work it did. That last part is not coloured as a warning: it is the
    baseline's own outcome.
  - The editor adds a **ONE AGENT, SAME TOKENS** box: cost, duration and tokens against the
    swarm's, failed tasks, runs out of tokens, tasks left, and a fixed note. The note says what it
    assumes and what it does not model: the quality of an answer, and the context each new agent
    reads in; and that a run that ran out stops there. The heading's tooltip states the evidence.
    The box is built by `soloBox`, a pure function the tests reach.
  - An estimate without a baseline shows "No one-agent baseline in this estimate — Σ Estimate
    again."
- **Why.** Tran & Kiela (2026): at equal thinking-token budgets, one agent matches or beats a
  multi-agent system on multi-hop reasoning. Anthropic (2025): token spend explains about 80% of
  the variance in multi-agent results.
- **What it shows**, p50 over eight seeds on the templates: one agent spends 88–98% of the swarm's
  tokens and 73–93% of its cost, and takes 2.5–8.9× its time. Custom is $0.96 vs $1.33 at 2.5×,
  refactor $5.28 vs $5.70 at 8.9×, research $4.34 vs $5.22 at 7.6×, incident $3.90 vs $4.83 at
  6.3×. In this simulator tokens track the work, not the number of agents: orchestration plus
  coordination is 7–13% of a swarm's tokens. So the token gap shown is a floor, and a per-agent
  context cost (default 0) is recorded on the roadmap.
- **Existing estimates are unchanged.** `Sim` is not touched. Every estimate's swarm figures are the
  same simulations on the same seeds, bit for bit; a test recomputes them, and another pins every
  template's eight-run estimate to 0.4's.
- **Swarm Command 0.5.0** also carries H4's change (under Changed below, where it was first
  numbered 0.4.1; no 0.4.1 was released). The manifest's description names the baseline.
  `src/webgui_data.cyr` is regenerated: the page is 451,093 bytes, up from 434,017 at 0.1.12
  (434,503 with H4's change).

### Added — `agnostic api schema`: the binary describes its own HTTP API (H5, ADR 0015)

- **`./build/agnostic api schema`** prints the HTTP API as one JSON document and exits 0. It is
  built from the tables the server dispatches, authorises and decodes with, so it cannot list a
  route, field or code the server does not have:
  - `routes` — 27, one per method of each of the router's 21 rows, in resolution order: method,
    path, `auth`, `permission`, `min_role`, the `plugin_permissions` that grant it (parsed from
    the embedded `permissions.json`), the declared `body`, `query` and `headers`, and what the
    route answers, `ok` and `response` (below). Each grant
    is `{"name", "self"}`: `self` lists the path parameters it pins to the requesting plugin's own
    id, so `storage` on the four plugin-data routes says `"self": ["id"]` — the gate's `:self` —
    rather than claiming every plugin's documents;
  - `bodies` — the crew, task, agent-definition, login and plugin-switch allow-lists, read from
    the decoders' own functions, the twelve refused agent fields, and the plugin document's
    32,768-byte object;
  - `headers` — the five any request may carry; `errors` — the error body's keys, the four codes
    from the closed catalogue with their statuses, and the eight rungs of the dispatch ladder;
  - `vocabularies` — roles, permissions, process, priority, risk, crew status (`interrupted`
    included, from H4) and its filter, and the plugin permission names. Each wire vocabulary is
    walked through its `*_to_wire` until the spelling repeats, so a value appended with its own
    arm is listed with no change to the generator.
  - Left out on purpose: the version, anything from `AGNOSTIC_*`, `grants` wording, plugin
    manifests, per-handler 4xx statuses and messages, field types, nested shapes, and response
    headers other than a document's `ETag`.
  - It reads no environment, opens no store and starts nothing, and is read before the
    environment: an invalid `AGNOSTIC_PORT` neither changes it nor stops it. A document that cannot
    be built whole, or written, exits 1 rather than printing a partial one.
- **`docs/api/generated/schema.json`**, the output committed, and **`scripts/gen-api-schema.sh`**,
  which regenerates it (`--check` compares parsed JSON and exits 1 with the diff; `--bin PATH`;
  it never builds; it stops the binary after 60 seconds, since one that does not answer `api
  schema` serves instead and would hang CI). [`docs/api/README.md`](docs/api/README.md) says what
  each part means, what is generated, declared or left out, and the stability rule.
- **What each route answers** (H5's fourth change). Each route entry ends with `ok`, the statuses it
  answers with its own body — 202 for a submit, 201 for a new definition, 201 then 200 for a
  plugin document's upsert, 200 elsewhere, and for `/ready` also 503, since "not ready" is its
  answer in the same body (ADR 0001) — and `response`, `{"kind", "keys"}`. `kind` is `json` (an
  object), `html` (the three WebGUI routes) or `document` (a plugin's stored document, verbatim,
  with its `ETag`). For `json`, `keys` are the object's top-level keys in the order the handler
  writes them; `key?` marks one a success can leave out (`next` on a last page, `replayed` on a
  first submit, a crew's `started_at` before it starts, `bad_index` on an intact trail). A crew's
  `GET` declares five keys every answer has and ten it may carry, since it answers from the ledger,
  the store, or the record of a crew a restart interrupted. Declared beside the generator, as the
  handlers build their bodies by hand; a route with no declaration fails the document, so a new
  route cannot print an empty answer. Cost: +4,306 bytes of code on x86_64 (the file +4,920) and
  +4,978 on aarch64 (the file +816), against a copy of the tree with only this change reverted,
  both `CYRIUS_DCE=1`; nothing on the request path calls it.
- **Three checks.** `tests/api_schema.tcyr` (new, 148) compiles the generator fresh and fails when
  it differs from the snapshot. CI runs `gen-api-schema.sh --check` on the DCE binary after
  "Verify ELF" (new step "API schema matches the snapshot"). `scripts/check-clean.sh` runs it too
  when `build/agnostic` is newer than `src/` — it never builds, so in CI, where it runs before the
  build, it skips. A second new CI step, "Command line exit codes", runs `help` (0, usage on
  stdout) and an unknown argument (2, usage on stderr, nothing on stdout) on the binary, which
  alone has `main`'s dispatch.
- ⭐ **Every route `permissions.json` grants is now checked against the router**
  (`api/plugin-vocabulary`). A route renamed in one but not the other used to stop being granted
  with nothing saying so (ADR 0007); it now fails a named assertion from either side.
- New modules `src/http/schema.cyr` (the generator) and `src/cli.cyr` (the command line).
  `agnostic_login_fields_a` and `agnostic_plugin_fields_a` lose their leading `_`: the schema reads
  them.

### Added — `skills/agnostic/SKILL.md`: driving agnostic from a coding agent (H6)

- **`skills/agnostic/SKILL.md`** is an Agent Skill (frontmatter `name: agnostic` and a
  `description` saying when to use it) for Claude Code, Codex or any SKILL.md-aware agent. It covers
  readiness, finding the auth mode, credentials (login, its 429 with no `Retry-After`, API keys no
  route issues), the Host and JSON-only rules (ADR 0006), submitting a crew with an
  `Idempotency-Key`, following it with `events?after=` and `missed` (ADR 0009), its outcome, usage
  and cost, `interrupted` after a restart (ADR 0013), listing, cancelling, presets and agent
  definitions, and the refusals: 400 for a value (`hierarchical` included), 422 for a shape or a
  refused field, `unforwarded`, and placeholder `engine_mode`. Its eight guardrails follow herdr's
  skill: stop when `/ready` fails, cancel only a crew it submitted, fix what an error names instead
  of guessing, always send an `Idempotency-Key`, and spend only what the user asked for.
- **`scripts/check-skill.py`**, run by `check-clean.sh` (so in CI's "Cleanliness check"). It checks
  the skill against `docs/api/generated/schema.json` (H5), which the suite keeps equal to the
  server's tables, so it needs no build and parses no Cyrius:
  - the frontmatter is valid Agent Skills frontmatter, and the body is under 500 lines;
  - every route, method, query parameter and curl header the skill uses is one the schema has for
    that route. The server ignores a query parameter it does not read, so a misspelled cursor would
    otherwise fail nowhere;
  - each response example after a `<!-- schema: response METHOD /path -->` line has only keys the
    route answers with, and every key it always answers with;
  - each block after a `<!-- schema: a.b -->` line names every value of that schema list: the crew,
    agent and task fields, the refused fields, the roles, the crew statuses and their filter, and
    the process, priority and risk words. A status or field the server gains fails it until the
    skill says what it means.
  - Mutation-verified: 22 mutations, each alone, fail by name and the unmutated copy passes —
    `?since=` for `?after=`, `/cancel` renamed, `POST` for `GET /api/v1/presets`, a curl cancel with
    no `-X POST`, a misspelled `Idempotency-Key`, `?status=` on the events route, an extra key in
    the 202 example, `crew_id` missing from the cancel example, a response example that is not JSON,
    a marker naming a missing route or list, `interrupted` dropped from the filter, a refused field
    dropped, an uppercase `name`, `<` in the description, the frontmatter's closing `---` gone, an
    unknown frontmatter key, a body over 500 lines; and against a changed copy of the schema, a new
    crew status, a new refused field, a renamed cursor and a new always-present key in the 202.

### Fixed — the audit chain links across a restart

Both defects are older than 0.1.13. The first has been there since the trail landed at M4.

- **Each process's first entry now names the entry before it.** `_agnostic_audit_open_locked`
  started libro's streaming chain with an empty head and never seeded it from the trail it had just
  loaded. So the first entry each process appended recorded `""`, the genesis link, as its
  predecessor. The next start's `verify_chain` failed there: the log said "verify: linkage broken"
  and "audit chain failed verification at open; the store was altered", and `GET /api/v1/audit`
  answered `intact: false` for a file nobody had touched. Any audited action after a restart did
  this, and the sweep's `crew.interrupted` entries (H4, above) would have done it at every start
  that found one. The open now sets the head to the last loaded entry's hash
  (`chain_set_prev_hash`). It does this on a broken chain
  too, so new entries continue the file as it is.
- **`bad_index` names the entry that broke.** It was read from offset 24 of libro's error object.
  libro 2.8.11 put a magic word at offset 0, which moved the index to 32 and left `field_name` at
  24. So every broken chain was reported broken at entry 0: on `GET /api/v1/audit`, in the Audit
  view's "first at entry #", and in the ERROR line's `entry=`. It is now read with libro's
  `error_index` accessor, at open and on a re-verify. The reproduction for the first fix found it:
  its break was at entry 1, and the server said 0.
- ⚠ **A trail written before 0.1.13 keeps its breaks, and nothing rewrites it.** The file is the
  evidence. A trail that recorded anything after a restart holds an entry with an empty
  `prev_hash` at each such restart, so it still answers `intact: false`. `bad_index` is now the
  real index: the first entry written after the first such restart. In a trail from a released
  binary that is a `crew.submit`, `crew.cancel`, `auth.login`, `definition.*` or `plugin.*`
  entry; no released binary wrote `crew.interrupted`.
  - The log says "verify: linkage broken" just before the ERROR line. An edited entry says "verify:
    hash mismatch" instead.
  - While the break is among the newest 1,024 entries, the Audit view shows that entry's
    `prev_hash` empty and marks it ✗. Its banner still says the trail "was altered while the
    server was not running", which is wrong for this kind of break.
  - Entries the upgraded binary writes link correctly. But verification stops at the first
    break, so the verdict says nothing about any entry after it, and a later real alteration would
    be hidden behind the old break.
  - To get a verdict that means something again: stop the server, move the audit file
    (`AGNOSTIC_AUDIT_PATH`, default `agnostic-audit.patra`) aside and keep it, then start. The new
    trail begins at a genesis entry and verifies. The old file stays readable with libro, but
    agnostic no longer serves it.
  - A verdict that can tell this break from a tamper is a roadmap item.

### Fixed — a crew named over 255 bytes is durable

Older than 0.1.13: it has been there since the outcome table landed at M4. H4 found it.

- **Its outcome is stored.** `agnostic_crews.cname` is a patra `STR`, which holds 255 bytes, and
  patra refuses a longer value (`PATRA_ERR_ROWSZ`) rather than cut it. A request accepts a `name`
  of up to 10,000 characters. So `_agnostic_crews_save_locked` failed for every crew named in more
  than 255 bytes. Its outcome was never stored and it was not listed, and after a restart, or once
  the ledger forgot it, `GET /api/v1/crews/{id}` answered 404. With H4's in-flight table (above),
  its `interrupted` outcome would have failed the same way: the row stayed, and every start logged
  "could not record an interrupted crew; it is retried at the next start" at ERROR.
- The column is written but never read. The listing reads `agnostic_crew_index.cname` (TEXT), and
  the stored document carries the whole name. So the store now binds at most the name's first 255
  bytes, cut on a UTF-8 character boundary (`_agnostic_crews_fit_utf8`, the rule
  `_agnostic_audit_fit_utf8` applies to the trail's kept copies). The schema does not change. The
  document, the listing row and the in-flight row keep the whole name.
- A crew that hit this before the upgrade has no stored outcome, and nothing can recover one.

### Changed

- ⚠ **The binary reads its arguments (H5).** Run bare it serves, exactly as before. `api schema`
  prints the API; `help`, `--help` and `-h` print usage and exit 0; **any other argument prints
  usage on stderr and exits 2, where 0.1.12 ignored it and served.** No documented invocation
  passes one. Exit codes are 0 ok, 1 failure, 2 usage error. The arguments are read before the
  environment, through the stdlib's `args` (already a declared dependency), which reserves 2 MiB
  of bump memory once at start; only the pages it reads are committed.
  - **Cost:** +13,888 bytes of code and +696 of data on x86_64 (the file +17,080, a page of
    alignment), +16,288 and +696 on aarch64 (the file +696), against a copy of the tree with only
    this change reverted, both `CYRIUS_DCE=1`. The request path is unchanged: nothing in it calls
    the new modules.
- ⚠ **A new value on the wire.** A crew interrupted by a restart answers 200 `interrupted`, where
  it answered 404 until now. A client with an exhaustive switch on `status` must learn it.
  `/events`, `/plan` and cancel still answer 404 for it, as for any crew from before a restart.
- **The listing no longer hides a status past `unknown`.** `AGNOSTIC_CREWS_ANY` was the literal
  63, and `_agnostic_crews_row_wanted` dropped any status above UNKNOWN. Either one would have hidden
  every interrupted crew, even unfiltered. ANY is now derived from the highest status, and the
  bound is INTERRUPTED.
- **Crews 0.1.1.** It adds an **Interrupted** filter, the pill in the warning colour, and an
  "Interrupted" fact from `interrupted_at`. A crew whose watch ends this way is settled, not
  waited on.
- **Swarm Command, H4's part of 0.5.0** (first numbered 0.4.1, never released on its own).
  `CREW_TERMINAL` includes `interrupted`. Without it, `finalize()`
  followed an interrupted crew's status forever as a crew still running. Each task the crew had
  not finished resolves "Interrupted by a server restart", the result reads **CREW INTERRUPTED**,
  and the crew list and run chips mark it as bad. The 404 message also names a crew a restart cut
  short before 0.1.13. `src/webgui_data.cyr` is regenerated.
- **Cost:** two more fdatasyncs per crew, both under the one store lock: the mark at submit and
  the delete with the outcome. Start-up pays about four per interrupted crew. `tests/agnostic.bcyr`
  gains `crew_inflight_mark_clear`: 159 µs for both at the cut, on tmpfs, which under-reports fsync.
- ⚠ **One agnostic process per database file is now load-bearing.** A second process on the same
  `AGNOSTIC_DB_PATH` would sweep the first one's live crews to `interrupted`. This is documented,
  not enforced; the guard is a roadmap follow-up. A 0.1.12 binary opened on a 0.1.13 database
  ignores the new table, hides `cstatus` 6 from its listing, and still serves the document on GET.
- **The router resolves from a table of rows (H5, the first of its four changes), with no
  behaviour change.** `agnostic_route_resolve_a` was an if-chain of 21 literal patterns. The routes
  are now data: 21 rows of a pattern and the route id for GET, POST, PUT and DELETE, built once at
  load into static storage, in the same order. The resolver walks them; every row goes through the
  two-capture matcher, which leaves `param2` 0 for a one-parameter route as before; the 404/405
  split is unchanged. `agnostic_route_row_pattern(i)` and `agnostic_route_row_id(i, method)` read
  the same rows, so the API schema (a later H5 change) can list the routes without a copy.
  - **Cost: none; slightly cheaper.** `tests/agnostic.bcyr`, x86_64, three interleaved runs each
    side against a copy of the tree with the if-chain restored (the first if-chain run, ~5% high on
    every bench, left out): first entry 108–109 → 107 ns, last 919–922 → 868–873 ns, a miss 781 →
    723–726 ns, the two-capture document path 2.19 → 2.14–2.16 µs. The walk calls
    `_agnostic_path_matches_at` directly; through the `agnostic_path_matches2_a` wrapper, as first
    written, it measured ~4% slower than the if-chain on a miss (774–782 → 809–812 ns), one call
    more per row.
- **The error codes are a closed catalogue (H5, the second of its four changes), with no wire
  change.** The four machine-readable `code`s were string literals at five call sites, each with its
  status beside it. `enum AgnosticErrorCode` (`src/http/response.cyr`) now lists them, and a table
  of rows built at load holds each one's name and status on a single line: `plugin_unknown`,
  `plugin_off` and `plugin_forbidden` are 403, `revision` is 412. `agnostic_response_error_code_a(a,
  ec, message)` takes a member where it took a status and a string, so no handler can send a code
  the catalogue does not list; a value it does not list answers 500 "unknown error code" with no
  `code`. `agnostic_error_code_name` and `agnostic_error_code_status` list the codes for the API
  schema (Change 3). The bytes on the wire are unchanged, and now pinned in full.
  - **No gap, by construction.** Code `ec` is row `ec - 1`. A row is written only as the next one,
    so a code added out of sequence (a fifth at 6, say) is refused a row and counted, and every
    lookup is bounds-checked against the row count. So the codes run 1, 2, 3 … with nothing
    between or past them, and anything that lists them by stopping at the first unlisted value —
    Change 3's schema generator — reaches every code the server can send. The rule is the table's
    shape, not a range a test scans.
  - **The agent definition's twelve refused fields are a table of rows** (name, message) in
    `src/engine/agentdef.cyr`, built at load like the route table.
    `agnostic_agent_def_refused_reason` walks the rows, and `agnostic_agent_def_refused_name(i)`
    lists them, so the decoder and the schema read one list. Until now they were an if-chain
    nothing could enumerate. Same names, same messages, same order.
  - `agnostic_method_name` (`src/http/router.cyr`) and `agnostic_perm_name` (`src/auth/perm.cyr`)
    name a method and a permission, for the schema to emit. Nothing dispatches or authorises by
    them.
  - **Cost.** +344 bytes of DCE binary on x86_64 and +352 on aarch64, against a copy of the tree
    with only this change reverted. A scratch program (not in the tree) timed the refused-field
    lookup both ways over a million keys, four runs each: a key that is not refused, which every
    agent key costs, 303–306 → 313–315 ns; the last row 325–328 → 337–353 ns. That is about 10 ns
    more per key, both making the same twelve string compares, and the two agreed on every row and
    on the probe keys. The coded refusals have no bench; `plugin_gate_granted` measured 1.24 µs.

### Tests

**31 suites, 2,347 assertions, 0 failed** (`cyrius test`, under the 6.6.14 pin, on x86_64 and
natively on aarch64), up from 29 and 1,885 at 0.1.12, and **77 JavaScript tests**
(`./scripts/check-webgui-js.sh`), up from 61. Two suites are new, `tests/restart.tcyr` and
`tests/api_schema.tcyr`.

- **The event cursor's gap, over HTTP and in both views that read it (H3).** Until now only the
  ledger suite asserted a non-zero `missed`; over HTTP, and in either view, only zero was.
  - `tests/crews_route.tcyr` gains `crews/events-gap` (20 assertions). A crew's ring is fed 300
    events, so it holds 45 to 300. Read from `after=10`, it answers 256 events from seq 45 to 300,
    `next` 300, `missed` 34, `lost_events` 0 and `dropped_events` 44. `after=0` and no `after`
    report `missed` 44, `after=43` misses 1 and `after=44` none. A cursor at or past the newest
    reads nothing and gets `next` back unchanged.
  - `tests/webgui/crews.test.mjs`: the fake answers `missed` as the server's ring does, and a new
    test has the Crews view count a gap of 3 once, read on from the window, and settle the task
    whose events were missed from the crew's outcome.
  - `tests/webgui/swarm.test.mjs` +1, the same for Swarm Command, whose `missed` path only a
    zero-missed fake reached: its fake now answers `missed` and `dropped_events` as the server
    does, and a live watch that falls three events behind counts them once in `missed` and in
    EVENTS MISSED (`dropped`), reads on from the window, and still settles every task, the one
    whose events were missed included, from the outcome. Mutation-checked on a copy of the page:
    `missed` assigned rather than added, `missed` ignored, or left out of `dropped`, each fails a
    named assertion, and so does the fake answering `missed` 0.

- **H4 (`interrupted`).** Every guard was mutation-checked: dropping it fails a named assertion.
  - `tests/outcome.tcyr` +3: the wire arm, INTERRUPTED = 6, terminal.
  - `tests/ledger.tcyr` +1: terminal.
  - `tests/crewstore.tcyr` +58: INTERRUPTED stored; `crewstore/inflight` (the outcome clears the
    row); `inflight-after-outcome` (a finished crew is never marked); ⭐ `sweep` (two crews,
    reopened: every field of the document, the listing row, idempotent on a second start);
    `sweep-keeps-outcome`; `cancel-then-restart` (ADR 0012's cancel stays cancelled); no store.
  - `tests/crews_route.tcyr` +20: `crews/inflight-mark`; ⭐ `crews/interrupted-not-404` (POST,
    restart, sweep, then GET 200 `interrupted`, and `/events`, `/plan` and cancel 404, listed, new
    POST 202); and `crews/collector` ends with the row cleared.
  - `tests/crew_tenancy.tcyr` +18: ⭐ `tenancy/interrupted` (acme reads and lists it, globex and
    `_` get 404, `?status=interrupted` finds it, `active` does not); `list-status` takes the filter.
  - **New suite `tests/restart.tcyr`** (14): the real `agnostic_serve_mount` on a database seeded
    the way a killed process leaves one. The crew that never finished is `interrupted` and listed,
    with exactly one `crew.interrupted` entry at warning naming it. The crew that finished stays
    completed.
  - JavaScript: `crews.test.mjs` +1 (a watched crew ends interrupted: filtered,
    settled, not waited on), and `swarm.test.mjs` +1 (⭐ the watch ends INTERRUPTED and does not
    poll forever). `drive()` now stops a source that never finished, so a failing test ends
    instead of hanging the run.

- **B3 (the one-agent baseline).** `tests/webgui/swarm.test.mjs` +12:
  - deterministic: one seed and one budget, one outcome; another seed, another;
  - every number `SOLO` restates is still in its Sim method's source; a change there fails, naming
    the entry to change;
  - the swarm's own plan on each seed: every task and part counted, and refactor's fan-out count
    follows the seed;
  - never past its budget: paired with the swarm's tokens, at 2,000 and at 0. With nothing failing
    everything is done, and with every tool off it still finishes. A step is cut exactly where the
    tokens run out; tool results far larger than what is left still leave a run out of tokens at
    its budget, not short of it; and a fan-out lead that fails before its split is one failure, as
    the Sim counts it;
  - ⭐ an estimate paired seed by seed. The swarm's figures are recomputed from the Sim alone and
    pinned to what 0.4 reported for the same swarm. The baseline is rebuilt from the same seeds and
    per-seed budgets;
  - ⭐ every template's estimate at the estimator's eight runs, pinned to 0.4's bit for bit;
  - ⭐ every template's baseline at the estimator's eight runs, pinned bit for bit, and each one's
    row of ADR 0014's table checked against it. The paired test rebuilds the baseline from `soloRun`
    itself, so only this one sees `soloRun`'s own pricing and timing;
  - a 0.4 estimate still reads, with `solo: null`; a baseline round-trips; a hostile one is clamped;
  - the card's line is labelled SIM, absent without a baseline, and says "out of tokens", with the
    tasks left, only when that happened;
  - the editor's box is labelled SIM, never LIVE, and carries the note; the share of a swarm that
    cost nothing is not shown; tasks left and cut off appear only when they happened; without a
    baseline it says to estimate again;
  - ⭐ where they are shown, rendered through the page's own `Launcher.card` and
    `Editor.renderSide` against a stand-in for the few elements they touch: the card's estimate
    ends with the SIM line, stale or not, and has none while estimating or without a baseline; the
    editor's side panel holds the SIM box once, under the cost estimate and above the checks, none
    while estimating or with no estimate, and the "estimate again" note for an estimate without
    one. Unwiring either, or showing the box while estimating, fails a named test.

- **H5, the route table.** `tests/router.tcyr` gains `router/table` (67 assertions); every earlier
  router, route and dispatch assertion passes unchanged.
  - 21 rows, nothing before the first or past the last, and room left for another row (a row
    that does not fit is refused rather than written past the storage, so a full table fails here).
  - ⭐ Every one of the 27 arms round-trips: its own pattern, with `x1` and `x2` for its
    parameters, resolves to its own id and carries exactly those captures. A row that shadowed a
    later one fails here.
  - Every route id has an arm, and only the shell has two (`/ui`, `/ui/`).
  - An unknown verb on a known path is a method mismatch and answers 405; on an unknown path it
    is a miss.

- **H5, the closed catalogues.** 63 assertions across six suites; every earlier assertion passes
  unchanged.
  - `tests/health.tcyr` gains `http/error-codes` (28): exactly four codes, numbered from 1, each
    name and status pinned and every name distinct; 0, the value past the last and a negative value
    are not codes; ⭐ the build refused no code, and a code past a gap, a code repeating the last
    and a row past the storage are each refused a row and counted, so a code placed past a gap
    (sent, but never listed) cannot be written; the lookup gives no row for 0 or for the value
    past the last; ⭐ no value outside 1 through 4 answers at any power of two, either side of one
    or negated, so a lookup that truncates or wraps a value (2^32 + 1 read as 1) fails here; a
    coded refusal is `{error, code}`, in that order, with the catalogue's status; ⭐ an unlisted
    value, 0, and the value just past the last code answer 500 with no `code` and without the
    caller's message.
    `http/response-exhaustion` +1: the coded constructor answers 0 on a full arena.
  - ⭐ The wire, byte for byte, asserted against the old code first and passing unchanged after it:
    `tests/webgui.tcyr` `plugins/rung` +3 (each plugin refusal's whole body) and
    `tests/plugindata.tcyr` `plugindata/revisions` +2 (the stale PUT's and the stale DELETE's). Until
    now no assertion read the `revision` code; the suite checked only the 412.
  - `tests/agentdef.tcyr` gains `agentdef/refuse-rows` (16): the twelve names in order, nothing past
    the last row or before the first, and each name refused by the decoder's own lookup with the
    message that quotes it. `agentdef/refuse` +1 (`role` is not refused). `celery_task` was the one
    refused field no assertion named.
  - `tests/authz.tcyr` gains `perm/names` (8), and `tests/router.tcyr` `router/method` +4: each
    method round-trips through its name, and NONE and the value past DELETE have none.

- **The audit chain across a restart.** `tests/audit.tcyr` gains 24 assertions, for 112.
  `audit/durable` reopened the trail and verified it, but never appended after the reopen, which
  is where the chain broke.
  - ⭐ `audit/durable-append` (18). One entry is recorded, the trail reopened, two more recorded,
    and the trail reopened again. It is intact with no bad index, and it records. Then the file is
    read straight through libro: four entries from three processes, the first the genesis, each
    `prev_hash` the hash of the entry before it across both restarts, and `verify_chain` clean.
  - `audit/tamper` asserts the edited entry is entry 1. It asserted `>= 0`, which the wrong
    offset passed. A re-verify names the same entry (+2).
  - `audit/tamper` then records on the altered trail, closes, and reads the file through libro:
    the new entry's `prev_hash` is the last stored entry's hash, not `""` (+4). That pins seeding
    a broken chain too, which keeps an old trail from gaining a new break at every restart.
  - Mutation checks, each made alone and restored afterwards:
    - without the seed, 6 assertions fail: the verdict, the bad index, three links and libro's pass;
    - seeding only when the chain verified fails 1, the link after the altered trail's reopen;
    - seeding from the first loaded entry instead of the last fails 3;
    - either `error_index` read put back to `load64(err + 24)` fails a named assertion ("and the
      failing entry is named", "at the same entry").

- **A crew named over 255 bytes.** `tests/crewstore.tcyr` gains 26 assertions, for 123. Before the
  fix, 12 of them failed, and the suite logged the sweep's ERROR line for both of its crews.
  - `crewstore/long-name` (12). Four names are stored: 300 ASCII bytes, exactly 255 bytes, 80
    four-byte characters (320 bytes) and 100 three-byte characters (300 bytes). Each document
    reads back byte for byte. `cname`, read straight from the table, holds the first 255 bytes;
    all 255; ⭐ 252, which is 63 whole characters, where a cut at 255 would split the 64th; and
    255, where the cut falls between characters.
  - ⭐ `crewstore/long-name-sweep` (14). Two crews are marked in flight, one named in 300 ASCII
    bytes and one in 150 two-byte characters. After a reopen the sweep interrupts both, the
    in-flight count reaches 0, both documents and the listing row keep the whole name, and a
    second start has nothing to retry.
  - Mutation checks, each made alone and restored afterwards:
    - binding the whole name again (the defect) fails 12;
    - cutting at 255 with no back-off fails 1, the 63 whole characters;
    - backing off one byte too many fails 2;
    - a cap of 256 fails 10.

- **H5, `agnostic api schema`.** New suite `tests/api_schema.tcyr`, 148 assertions; every earlier
  assertion passes unchanged.
  - ⭐ `api/snapshot` (6): the generator's text is the same every time, ends in a newline, and is
    exactly `docs/api/generated/schema.json` re-printed through the same bayan. On a difference it
    prints the first differing line from both sides and the command that regenerates the snapshot.
    The snapshot is read relative to the working directory (`cyrius test` runs at the repo root);
    unreadable, it names the path and the command.
  - `api/routes` (16): 27 routes, each with the eleven keys in order, each resolving through the
    router to an id whose `agnostic_route_needs_auth` and `agnostic_perm_for_route` are what it
    states; `min_role` viewer for read, operator for write, admin for admin; no duplicate; exactly
    six public routes, and the audit trail and the plugin switch are admin.
  - ⭐ `api/plugin-vocabulary` (10): every route in `permissions.json` matches exactly one schema
    route (`:self` as any parameter), which lists the permission with `self` the route's parameters
    the grant writes `:self` (worked out in the suite from the two paths), and the router resolves
    it made concrete; the routes list exactly the grants the vocabulary holds, each `{name, self}`,
    four of them pinning a parameter; the names in its order.
  - `api/bodies` (13): each `fields` is its decoder's allow-list element by element; the twelve
    refused fields are the decoder's table rows and each is refused; the plugin document's kind
    and `AGNOSTIC_PLUGINDATA_DOC_MAX`; `items`; every body named exists and every body is used.
  - `api/vocabularies` (22): each value round-trips through the real parser — `agnostic_role_parse`,
    `agnostic_process_from_wire`, `agnostic_priority_from_wire`, `agnostic_risk_from_wire`,
    `agnostic_crews_status_mask` (`1 << status`, and `active` is pending|running) — and each
    parser refuses a probe value; status 6 is `interrupted`.
  - `api/errors` (23): the codes are the catalogue's, with their statuses; the ladder's eight rungs
    in order; and ⭐ seven of them driven through the dispatcher — body size, host, route, method,
    plugin (with `plugin_unknown`), authn and media type — each answering its listed status, with
    five pairs proving the order (a request two rungs would refuse is answered by the earlier one).
    `authz` needs a stored identity; `tests/authz.tcyr` drives it.
  - `api/cli` (24): no arguments and an unreadable command line serve; `api schema`; `help`,
    `--help`, `-h`; `api` alone, a misspelling, an extra argument, `serve` and a missing argument
    are usage errors. ⭐ Then each command is run against two capture files
    (`agnostic_cli_run_on`, `agnostic_cli_run` with the streams passed in): a usage error exits 2
    with usage on the complaints and nothing on the output; `help` exits 0 with usage on the output
    and no complaint; `api schema` exits 0 with the whole document, byte for byte, and no
    complaint; `api schema` and `help` on an output that cannot be written exit 1, the first saying
    so.
  - ⭐ `api/probes` (20), on throwaway stores under `$TMPDIR` named for the process and removed
    after: each of the five routes taking an allow-listed body refuses `{"__probe__":1}` as an
    unknown field and knows every field its declared body lists; the same inside a crew's
    `agents[0]` and `tasks[0]`; a plugin document that is not an object is 422, one of exactly
    `max_bytes` is stored and one byte more is 413; each of the six declared query parameters,
    given an invalid value, is the handler's 422; every GET route answers the same with each of the
    four known parameters it does not declare set; each of the four declared headers is read (an
    invalid `Idempotency-Key` 422; a stale `If-Match` and `If-None-Match: *` 412 `revision`); and
    ⭐ each grant with a `self`, driven through the plugin gate as the built-in `swarm` (which holds
    `storage`), passes for its own id and is `plugin_forbidden` for `crews`'s, on all four
    plugin-data routes.
  - ⭐ `api/responses` (14), H5's fourth change. It runs the real `agnostic_serve_mount` with auth
    required and a bootstrap administrator, on a fresh database where a "dead process" left one
    crew in flight, so mount's start-up sweep interrupts it. It logs in, then drives every route's
    success path: a submit and its replay under one `Idempotency-Key`, a parallel crew, plan, events
    and polls until both finish, the interrupted crew, a cancel (submitted and cancelled at once
    until one answers 200 — the placeholder engine can finish first, 409), both listing pages, all
    18 presets, a definition's five routes, the trail and two pages of entries, the plugins and the
    switch, a plugin document put twice (201, then 200), listed, read and deleted, and the three
    WebGUI pages. Last, the trail is reopened after one byte of an entry is changed on disk
    (`bad_index`), and a readiness check that always fails is registered (`/ready` 503).
    - Every answer is checked as it comes: a status `ok` lists; a body of its kind (a `json`
      object, an `html` page, or a `document` sent as `application/json` with an `ETag`); every key
      not marked optional present; no key undeclared.
    - ⭐ Then the other way: every route was driven, answered every status its `ok` lists, and
      wrote every key it declares, optional ones included. A declaration nothing produces fails.

### Verified

- **Live, with the real binary, on x86_64 and natively on aarch64 (the Pi, Ubuntu).**
  `AGNOSTIC_LLM_URL` pointed at a local listener that accepts connections and never answers, so a
  crew hangs. A two-task crew was POSTed and seen `running`, then the server was killed with `kill -9`
  and restarted.
  - The restart logged "crews in flight at the last stop are now interrupted crews=1".
  - `GET /api/v1/crews/{id}` answered 200 `interrupted` with its name, scope, engine mode, process,
    `tasks_submitted` 2, `submitted_at` and `interrupted_at`, and no `started_at` or `finished_at`.
  - The listing, and `?status=interrupted`, showed it; `?status=active` did not.
  - `/api/v1/audit/entries` held `crew.interrupted` at warning, `crew_id=<id>`.
  - `/events`, `/plan` and cancel answered 404.
- **H4 in a browser.** Headless Chromium drove the real binary's WebGUI over CDP, after the same
  `kill -9` and restart, with Crews and Swarm Command switched on.
  - Crews 0.1.1, deep-linked to the crew, listed it with the INTERRUPTED pill in the warning colour
    and offered the Interrupted filter. Its detail showed the error and the facts Submitted,
    Interrupted, Process, Tasks "0 / 2 done", Tokens "not metered" and Cost "not priced", with no
    Took.
  - Swarm Command 0.5.0, following `#plugin/swarm?crew=<id>`, ended the watch **CREW INTERRUPTED**
    with the error. No task line said "Interrupted by a server restart", because a crew from before
    the restart has no plan to name its tasks; `swarm.test.mjs` covers a watch that began before it.
  - No exception and no console error.
- **Mutation checks.** Each of these, made alone, fails a named assertion, and the source was
  restored byte for byte afterwards:
  - INTERRUPTED dropped from `agnostic_status_is_terminal`: `crewstore/sweep`;
  - the wire arm dropped: `crews/interrupted-not-404` reads `pending`;
  - the in-flight DELETE dropped: `crewstore/inflight` and `crews/collector`;
  - the outcome-exists branch in `interrupt_row` dropped: `crewstore/sweep-keeps-outcome`;
  - ANY left at 63, or the listing bound left at UNKNOWN: `tenancy/interrupted`;
  - `CREW_TERMINAL` without `interrupted`: the Swarm Command test ends with no summary;
  - the sweep not called from `agnostic_serve_mount`: `restart/mount`;
  - the in-flight mark skipped at submit: `crews/inflight-mark` and `crews/interrupted-not-404`
    (GET answers 404).
- **B3: existing estimates are bit-identical.** In Node, against the page as it was before the
  change, `estimateSpec` returns byte-for-byte the same swarm fields for all four templates, at
  four and at eight runs each; the eight-run figures are now pinned by a test. Against 0.1.12's
  committed page (Swarm Command 0.4.0), 32 eight-run estimates — four templates, scales 1 and 2,
  four seeds each — give the same swarm fields and `sig`. Moving the restated numbers into `SOLO`
  left `soloRun` bit-identical over 5,768 runs (four templates, three scales, 60 seeds, six
  budgets, and a harsher failure model).
- **B3 mutation checks.** Each of these, made alone, fails a named test, and the page was restored
  byte for byte afterwards:
  - the baseline's RNG seeded without the template's hash: the plan test;
  - the work step not cut at the budget, or a tool result taken past it: the budget test;
  - every seed given the first run's budget: the ⭐ estimate test;
  - the Sim's orchestrator rate nudged from 0.6 to 0.61: the ⭐ estimate test's pin;
  - `normalizeEstimate` dropping `solo`, or its `out` not clamped to the run count: the store test;
  - the card always saying "out of tokens", or not saying the tasks left: the line test;
  - a fan-out lead that fails before its split counting its parts failed, or keeping them in the
    total; a tool result that does not fit not taken, or taken whole: the budget test;
  - a millisecond more same-region travel in the Sim, which left custom's four-run pin as it was:
    the eight-run pins and the `SOLO` check; a `SOLO` number changed, or its Sim counterpart (the
    retry share, a new agent's health, spawning, the lead's share, a phase's compute factor): the
    `SOLO` check, and the pins where the Sim changed;
  - the editor's box labelled LIVE, or without its hint, its note, the guard on a zero-cost
    share, or its tasks-left and cut-off rows: the box test;
  - in `soloRun`, a work step's tokens or a tool result's left unpriced, no token priced at all, the
    compute multiplier dropped, or the region's speed dropped from a step's length or from its
    progress: the ⭐ baseline pin, alone. Each of these passed every other test.
- **B3 in a browser, inside agnostic.** Headless Chromium 153 drove the real binary's `/ui` over
  CDP, with `AGNOSTIC_AUTH=required`, an administrator and a viewer, and Swarm Command switched on.
  So the page ran in the shell's sandboxed iframe and kept its swarms on the server through the
  host bridge. Both frames were watched.
  - **As the administrator**, each template was customized, saved, and estimated with Σ ESTIMATE on
    its card. Every card showed the SIM line under the swarm's figures. Every EDIT showed the ONE
    AGENT, SAME TOKENS box, tagged SIM, with its note and the evidence tooltip. For research: $4.34
    · 84% of the swarm, 17:45 · 7.6×, 749k · 98%, 4 of 8 out of tokens, 0.5 tasks left per run;
    the card read "out of tokens in 4 (0.5 tasks left / run)".
  - **Stored as computed.** Each template's stored estimate, the swarm's figures and `solo` alike,
    equals Node's `estimateSpec` on the same stored swarm bit for bit, and its `sig` matches. The
    four baselines are the ones the ⭐ test pins.
  - **An estimate from 0.4.** One stored estimate was stripped of `solo` through the API and the
    library reloaded. The card had no line, and EDIT said "No one-agent baseline in this estimate
    — Σ Estimate again."
  - **As the viewer**, NEW SWARM and EDIT were disabled. Σ ESTIMATE on that card showed the SIM
    line and the same baseline on screen. The stored document was not written: its ETag and its
    estimate were unchanged, still without `solo`.
  - No uncaught exception and no console error or warning in either frame. The only logged errors
    were the shell's two 401s for `/api/v1/plugins` while signed out.
  - An earlier run drove the standalone page (file://, swarms in browser storage) through the same
    estimate, save and strip, with the same figures and no exception.
- **H5 route-table mutation checks.** Each of these, made alone, fails `router/table` (the first
  also `router/definitions` and `router/definition-dispatch`), and `src/http/router.cyr` was
  restored byte for byte afterwards:
  - an arm dropped (DELETE on `/api/v1/agents/definitions/:key`): 26 arms, id 13 has none;
  - the storage too small for every row: 20 rows, no room left, id 19 has no arm;
  - the `/ui/` row dropped: the shell has one arm;
  - the resolver on the one-capture matcher: the document routes (21, 22, 23) lose `param2`;
  - a shadowing row (`/api/v1/crews/:id/:verb`, POST) inserted before cancel: cancel's path
    resolves to the crew GET.
- **H5 catalogue mutation checks.** Each of these, made alone, fails a named assertion, and the
  source was restored byte for byte afterwards:
  - `plugin_off` sent as 412: `http/error-codes` (2) and `plugins/rung` ("a switched-off plugin is
    refused");
  - an unlisted code answered 403 with the caller's message: `http/error-codes` (5);
  - a fifth code: `http/error-codes` ("exactly four codes", and the value past the last);
  - a fifth code past a gap (6, leaving 5 unlisted), and one at 70000: `http/error-codes` ("the
    build refused no code"; each is refused a row, so never sent). The catalogue's first form, an
    if-chain the suite probed from -256 to 65535, passed every assertion with a code at 70000
    returned from the chain; the table has no way to write one;
  - the table's next-row rule dropped: "a code past a gap is refused a row"; its storage bound
    dropped: "and a row past the storage"; a refusal left uncounted: "each refusal counted"; the
    storage one row short of the four: "4 is revision, 412" and "the build refused no code";
  - the lookup bounded one row late: "nor for the value past the last code"; its lower bound
    dropped: "no row for 0" (the suite then faults reading that row, so it reaches no verdict);
    the lookup truncating to 32 bits: "no value but 1 through n is a code, at any power of two or
    beside one";
  - two refused rows given each other's messages: `agentdef/refuse-rows` ("each is refused, with
    the message that names it");
  - the `celery_task` row dropped: `agentdef/refuse-rows` (7), and nothing else;
  - the refused table's storage one row short: `agentdef/refuse` ("workflow_mode refused") and
    `agentdef/refuse-rows` (2);
  - `agnostic_perm_name` answering `super_admin`: `perm/names`; `agnostic_method_name` answering
    `PATCH` for PUT: `router/method`.
- **H5's catalogues natively on aarch64 (the Pi).** The six suites this change touched, cross-built
  with `CYRIUS_DCE=1 cyrius build --aarch64`, pass with the same counts as on x86_64: `agentdef` 130,
  `authz` 69, `health` 74 (re-run once the error codes became a table), `plugindata` 144, `router`
  151, `webgui` 203.
- **H5, the route table against the if-chain it replaced.** A scratch program (not in the tree)
  compiled 0.1.12's `agnostic_route_resolve_a`, renamed, beside the table walk and compared the
  two on 4,299,876 (method, path) probes: GET, POST, PUT, DELETE, an unknown method and a
  non-method value, over every path of up to four segments drawn from the route vocabulary and an
  empty segment, with and without a leading slash, a trailing slash, `?`, a query string and a
  fragment, and deeper paths under `/api/v1`, the plugin documents and `/ui/plugins`. Every
  probe gave the same id, the same 404/405 flag and the same captures; all 26 route ids and the
  miss were reached. With one row's POST arm dropped it reports 38 differences, so it can fail.
  - Live, the shipped DCE binary against one built from the same tree with the if-chain restored,
    on x86_64 and natively on aarch64 (the Pi): 35 paths × GET, POST, PUT, DELETE, PATCH and
    OPTIONS, 210 requests each, gave the same status and content type every time, on both
    machines. The table costs 1,344 bytes of binary on each architecture.
- **The audit chain across restarts, live, with the DCE binary on x86_64 and natively on aarch64
  (the Pi).** Two sequences ran on each machine. Each runs four processes on one trail, stopped
  twice with `kill -9` and once with SIGTERM.
  - Crews, with `AGNOSTIC_LLM_URL` at a listener that never answers. A crew is submitted. After the
    restart, the sweep records `crew.interrupted`, then a definition is created and a second crew
    submitted. After the next restart, the sweep records the second crew's `crew.interrupted` and
    a definition is created.
  - Definitions only: create; then replace and delete; then create.
  - Every start answered `intact: true` and logged no linkage error. `/api/v1/audit/entries`
    showed each start's first entry naming, as `prev_hash`, the hash of the last entry before the
    restart.
  - The crew sequence on a binary built from the same tree with `audit.cyr` as at HEAD: the third
    start answered `intact: false, bad_index: 0`. Entries 1 and 4, each start's
    `crew.interrupted`, had an empty `prev_hash`.
  - That trail, opened by the fixed binary twice with a definition created each time, answered
    `intact: false, bad_index: 1` both times. The two new entries linked to the entries before
    them.

- **H5 schema mutation checks.** Each of these, made alone, fails `api/snapshot` and — all but the
  first — a named assertion in another group of `tests/api_schema.tcyr`. Each was run against the
  final suite, and the source was restored byte for byte afterwards (checksums compared):
  - a field added to the login allow-list: `api/snapshot` alone, as intended — the schema reads the
    list, so only the snapshot can see the API changed;
  - `/api/v1/audit/entries` renamed in the router only: `api/plugin-vocabulary` (3: no single
    route, the router does not resolve it, 18 grants listed against 19);
  - the same route renamed in `permissions.json` only: `api/plugin-vocabulary` (the same 3);
  - the plugin switch declared as taking a `login` body: `api/probes` ("accepts every field its
    declared body lists as known", 2) and `api/bodies` (the switch body unused);
  - the events route declaring a `limit` it does not read: `api/probes` (the count, and "an
    invalid value is a 422");
  - the crew listing no longer declaring `status`: `api/probes` (the count, and "every GET route
    answers the same with each known parameter it does not declare set");
  - a plugin-document GET declaring `if-match`: `api/probes` (the count, and the 412);
  - the ladder declaring `route` before `host`: `api/errors` (the order);
  - `agnostic_crew_status_to_wire` losing its `interrupted` arm: `api/vocabularies` (seven
    statuses; status 6). The first form of the suite crashed here on a missing element instead of
    failing; its accessors now read a missing string as empty, so a damaged document gets a verdict.
  - One changed value in the snapshot: `gen-api-schema.sh --check` exits 1 with the diff, and
    `check-clean.sh` fails on it; and `api/snapshot` prints the differing line from both sides and
    the command that regenerates it.
- **H5 response mutation checks.** Each of these, made alone, fails a named assertion in
  `api/responses` (and `api/snapshot`, where the declaration moved); the source was restored byte for
  byte afterwards (checksums compared):
  - a handler dropping a key (the definitions listing's `total`): "left out a key it declares" and
    "never wrote a key it declares";
  - a handler writing an undeclared key (the plugin switch): "wrote a key it does not declare";
  - a declaration dropping a key (`changed`): the same;
  - a declaration adding a key nothing writes (`nope?`): "never wrote a key it declares";
  - an optional key declared required (the listing's `next`): "left out a key it declares";
  - a new definition declared as answering 200: "answered a status its ok does not list";
  - `/ready` without 503: the same;
  - a status declared and never answered (201 on a definition's `GET`): "never answered a status
    its ok lists";
  - a plugin document declared `html`: "is not an html page";
  - a document sent without its `ETag`: "sends no ETag";
  - a route with no key declaration (cancel): the whole document fails, so `api/snapshot` and every
    group reading it fail.
- **H5 command and grant mutation checks.** Each, made alone, fails what it names; the source was
  restored byte for byte afterwards (compared with `cmp`):
  - A usage error answering 0 rather than 2 — a mutant every gate let through before `api/cli`
    ran the commands: "a usage error exits 2". `help` answering 2: "help exits 0". A failed write
    answering 0: "api schema that cannot write its output exits 1". Usage for a usage error
    written to the output: `api/cli` (2, the output not empty and the complaints without usage).
  - Every grant's `self` emitted empty: `api/snapshot`, `api/plugin-vocabulary` (2: the grant's
    `self` on four routes, and the count of pinning grants) and `api/probes` (the count).
  - The plugin gate no longer putting the plugin's id in place of `:self`
    (`src/webgui/plugins.cyr`): `api/probes` ("the gate agrees", naming the four routes on which
    `swarm` reached `crews`'s documents).
  - `gen-api-schema.sh --check --bin` a stand-in binary that never exits, as a serving one would:
    exit 1 after 60 seconds, saying so; one that ignores SIGTERM is killed 5 seconds later, exit 1.
- **H5, the command, live.** The DCE binary run bare with no `AGNOSTIC_*` but a port and two store
  paths served `/health` and `/api/v1/presets` 200 and shut down gracefully on SIGTERM; with
  `AGNOSTIC_PORT=bad` it still refuses to start (exit 1). `api schema` printed the same bytes with
  `AGNOSTIC_PORT=notaport` set; `help`, `--help`, `-h` exited 0; `serve`, `api` and `api schema
  extra` exited 2; `api schema > /dev/full` exited 1 with "could not write the API schema".
- **H5 natively on aarch64 (the Pi).** `tests/api_schema.tcyr`, cross-built with `CYRIUS_DCE=1
  cyrius build --aarch64`, passed 134 of 134 after the third change and 148 of 148 after the fourth
  (`api/responses` mounting, logging in and driving every route there, in 7.5 s). Each time the
  aarch64 DCE binary's `api schema` was byte for byte the committed snapshot. After the third
  change, CI's "Command line exit codes" step, run there as written, passed (`help` 0 with usage on
  stdout, an unknown argument 2 with usage on stderr only); after the fourth, `help` exited 0 and
  an unknown argument 2.
- **H6, every call in the skill, live.** The 0.1.13 binary on loopback, with its stores under
  `~/.cache`, in three passes, each assertion against the bytes the skill shows:
  - Placeholder, auth off (60 checks): `/ready`, the auth probe (200), the section 4 crew (202 with
    exactly the eight keys, `placeholder`), its replay (`replayed: true`), the same key over the
    same JSON re-serialised (422), a malformed key, `hierarchical` (400, "must be one of"),
    `agent_key`, `task`, `tasks[1].agent` and `agents[0].x` (422 with the skill's messages), missing
    `name`, `max_concurrency` without `parallel`, a cycle and non-JSON (400), `"gpu_required":
    "false"` (422), `focus` in `unforwarded`; the events cursor (`after=0`, then `next` reads
    nothing), `?since=` returning the same whole window as no parameter, `after=-1` (422); the
    outcome (no `token` events and `usage.metered_tasks` 0 in placeholder), an uppercase id, the plan,
    the listing with `?status=active`, `completed`, `interrupted` and `before=next`; cancel of a
    finished crew (409), without `Content-Type` (415), of an unknown id (404); a non-loopback `Host`
    (403) and `localhost` (200); 405 and 404; a preset's agents verbatim (422 on `agent_key`) and
    through the skill's four steps (202); a definition's round trip, and its `definition` object
    submitted as an agent (202).
  - `AGNOSTIC_AUTH=required` with a bootstrap login: the probe 401, login 200 as `super_admin`,
    a Bearer submit 202, a garbage Bearer and an unknown `ApiKey` 401, 401 before 415, and the sixth
    login attempt in a row, the first having succeeded, answered 429 with no `Retry-After`.
  - A live engine whose gateway accepts and never answers: a crew `running` with `results: []` and
    `task_count` 0; a running crew cancelled (200, then 409); `kill -9` and a restart on the same
    store, after which the running crew answered `interrupted` exactly as the skill's example shows,
    was listed under `?status=interrupted`, and its events, plan and cancel answered 404, while the
    cancelled crew still answered `cancelled`.
- **The release's changes together (2026-10-04), from a clean state, in CI's order** with
  `TMPDIR` under `~/.cache`: the toolchain matches the 6.6.14 pin; `lib sync --full`, `deps`,
  `lock-check.sh --no-resolve`, `check-symbols.sh` (1,063 definitions across 50 files) and
  `check-clean.sh` pass; the DCE build is 6,186,712 bytes on x86_64 (6,136,064 at 0.1.12) and
  7,443,720 on aarch64 (7,356,208); CI's two new steps pass on it; `cyrius test` passes 31 suites,
  2,347 assertions; and `cyrius bench` gives every one of 0.1.12's benchmarks at or below its
  0.1.12 figure (the routes 108 / 851 / 715 ns and 2.11 µs, the plugin rung 1.23 µs, a 50-entry
  audit page 27.1 µs). `cyrius.lock` and `lib/` were byte for byte as before the run.
  - Every suite, cross-built with `CYRIUS_DCE=1 cyrius build --aarch64`, passed natively on the Pi
    (Ubuntu 26.04.1) with the x86_64 counts: 31 suites, 2,347 assertions.
  - The DCE binary, live on loopback against a gateway that never answers: two crews submitted
    (one named in 150 two-byte characters), `kill -9`, restart. Both answered `interrupted`, the
    long name whole (300 bytes); `?status=interrupted` listed both; events, plan and cancel
    answered 404; the start logged `crews=2` and no ERROR. The trail answered `intact: true` at
    the second start, and again at a third, after a definition was created and the server stopped
    with SIGTERM.
- **The cut (2026-10-04)**, after `scripts/version-bump.sh 0.1.13`, every CI step again in CI's order
  with `TMPDIR` under `~/.cache`, with the same results: no toolchain drift; `lock-check.sh
  --no-resolve` matched a clean tag resolution (9 commit pins); `check-symbols.sh` 1,063 definitions
  across 50 files; `check-clean.sh` clean, with 77 JavaScript tests; the DCE builds 6,186,712 bytes
  (x86_64) and 7,443,720 (aarch64), byte counts unchanged; `gen-api-schema.sh --check` and the exit
  codes on the binary; `cyrius test` 31 suites, 2,347 assertions, 0 failed; and `cyrius bench`'s 16
  benchmarks (the routes 109 / 864 / 720 ns and 2.12 µs, the plugin rung 1.24 µs, a 50-entry audit
  page 28.5 µs). CI's security scan and docs checks pass. `cyrius.lock` and `lib/` are byte for
  byte 0.1.12's. `/ready` answers `"version":"0.1.13"` on x86_64 and, from the aarch64 DCE binary,
  natively on the Pi, where `help` exits 0, an unknown argument 2 with nothing on stdout, and `api
  schema` prints the committed snapshot.
- **The release verification (2026-10-04)**, after the cut, which changed only docs and test
  comments: every suite, cross-built again from this tree with `CYRIUS_DCE=1 cyrius build
  --aarch64`, passed natively on the Pi (Ubuntu 26.04.1), 31 suites and 2,347 assertions, 0 failed,
  each exiting 0. The x86_64 DCE build is again 6,186,712 bytes; `check-clean.sh` passes, with 77
  JavaScript tests; `/ready` answers `"version":"0.1.13"`; and `agnostic --version` exits 2.

### Known — found during this release, older than it, not fixed here

Each is an open item on the roadmap ("Found at 0.1.13", and H4's and H5's follow-ups), with where it
is and, where it applies, how to reproduce it and the fix direction. H4 found three older defects; two of them, the audit
chain not linking across a restart and a crew named over 255 bytes never being durable, are fixed in
this release (see Fixed above).

- **`GET /api/v1/crews/{id}` for a crew this process holds carries `engine_mode` twice.** The route
  sets it and `agnostic_ledger_describe_a` sets it again: bayan's object set appends a second key
  rather than replacing the first. Stored documents, and the interrupted one, carry it once.
- **The audit chain** (found fixing its restart link): a trail written before 0.1.13 keeps its
  breaks, and verification stops at the first one (see Fixed above); a failed read at open
  verifies as intact; a failed write leaves the chain's head on the entry it did not save, so the
  next start reports tampering.
- **Request paths still allocate from the global bump**, which has no `free()`: 16 bytes for a 404,
  a 401 or any authenticated request, 696 for a successful login, 416 per audited write (H5).
- **A 405 carries no `Allow` header** (H5).
- **`cyrius test` still prints one warning on our code**, `tests/jwt.tcyr:93` "assigning
  non-pointer to typed pointer".
- **The suites write their stores to fixed `/tmp` paths and ignore `TMPDIR`**; a full run leaves 17
  files there.
- **One agnostic process per database file is assumed, not enforced** (H4, see Changed above).
- **`CONTRIBUTING.md` names a coverage gate CI does not run, and the tree does not meet it.**
  `cyrius coverage --min 80` fails at 69% (330 of 476 functions; 67% at 0.1.12): it counts
  references, and the route handlers the suites reach through the dispatcher count as unreferenced.
- **Stale lines and pages from earlier releases.** `cyrius.cyml`'s comment on the folded sigil
  still describes the chain declaring 3.13.5; `CONTRIBUTING.md` asks an issue for the Rust version;
  `BENCHMARKS.md` was last generated at 0.1.0, with one benchmark of today's 16; and
  `docs/development/handoff.md` §1 stops at 0.1.10.

### Docs

- **ADR 0014** (the swarm estimator's one-agent baseline is its own model, at the swarm's token
  spend), indexed. The roadmap ticks B3 and records a follow-up under "Later": a per-agent context
  cost in the simulator, default 0 so no estimate changes, because the simulator's 7–13% swarm
  overhead understates real systems': Anthropic measured a multi-agent system at about 15× a
  chat's tokens against about 4× for a single agent, roughly 3–4× one agent. `docs/development/state.md`, the
  plugins guide (the Estimate bullet) and the README describe the baseline. The page's header
  comments and `soloRun`'s comment say what it is, and why it is not the Sim with one agent.
- **ADR 0013** (a crew a restart interrupted answers `interrupted`, not 404) and **architecture
  note 001** (what survives a restart: every kind of state, where it lives, what the next start does
  with it; one process per database file; downgrading). The architecture index lists it.
- **Roadmap.** The M4 note "a crew interrupted mid-flight 404s after a restart" is marked superseded
  by ADR 0013, its text kept. H4 is ticked, with two corrections: the mechanism is a status-less
  in-flight table, not a crew row at submit, and there are no finished-task results to keep. Its
  three follow-ups are recorded as open items: the one-process-per-database guard, cancel answering
  409 for a stored terminal crew, and keeping finished results once agnosai F3/F4 carry them.
  "Found at 0.1.13" records the three older defects H4 found; the audit chain's and the crew
  name's are now ticked (Fixed above).
- `docs/development/state.md` (nine tables, the persistence rule, the route table, the plugins),
  `docs/guides/webgui-plugins.md` (the Interrupted filter, and what Swarm Command shows) and the
  README say the same.
  Source comments in `crewstore.cyr`, `crew.cyr`, `ledger.cyr`, `outcome.cyr`, `routes/crews.cyr`
  and `serve.cyr` describe the new rule.
- **H3 is closed with no wire change: 0.1.9 delivered it as `missed`.** Since 0.1.9, an `after`
  older than the oldest of a crew's 256 held events gets every event still held, from the oldest,
  and `missed`. The roadmap's `events_lost: true` would restate `missed > 0` under a name that
  collides with `lost_events`, and the re-read it proposed (`GET /crews/{id}`) carries no task
  results until the crew ends.
  - The roadmap marks H3 closed with those reasons, and its F3 entry names the per-task snapshot
    a reader past the ring could resync from mid-run.
  - The 2026-10-03 research note carries a dated correction: the parameter is `after=`, not
    `since=`, and the gap is not silent.
  - The events handler's comment (`src/routes/crews.cyr`) says what a reader does with
    `missed` > 0, and how a cursor past the newest is answered.
  - The README names `missed`, and state.md's route row names the gap signal.
- **H5, the route table.** The router's header says the table is now literally one, with the
  re-measured costs, and that the next route added should re-measure. The comment on
  `agnostic_method_from` said an unknown verb 404s; on a known path it answers 405, as the new test
  pins. `src/auth/perm.cyr` cited `router.cyr:323`, which had gone stale; it names the function
  instead. `docs/development/state.md` records the 0.1.13 measurement beside the earlier ones.
- **H5, the closed catalogues.** `src/http/response.cyr` gains a section on why the codes are an
  enum, appended and never renumbered, and how the table of rows makes "no gap" its shape rather
  than a rule; `agnostic_plugin_gate_a` and the plugin-data handlers name catalogue members. The roadmap's H5 entry records Change 2 as done, and
  `docs/development/state.md` counts its tests.
- **H5, `agnostic api schema`.**
  - **ADR 0015** (the HTTP API is described by a schema generated from the server's own tables,
    and a snapshot freezes it), indexed.
  - **`docs/api/README.md`** (new): every key of the document, what is generated, declared and left
    out, the three checks, the known gaps, and the stability rule — before 1.0 a snapshot change is
    an ordinary change with a CHANGELOG line; from 1.0 a removal or rename needs an ADR and a
    Breaking entry.
  - The README's API section and `docs/guides/getting-started.md` name the command.
  - The roadmap ticks H5, pointing to ADR 0015 and `docs/api/`, with what each of the four changes
    did. The v1.0 criterion "Public API frozen" now says how the HTTP half is checked — the snapshot
    in the suite and on the shipped binary in CI, every declared request part driven through the
    dispatcher, and every route's response statuses and keys checked both ways on the real mount —
    and what is still open for it. "Later" records what the schema leaves out (field types and
    required-ness, nested shapes, a code for the 422 refusals, per-handler statuses, and the
    reverse of the declared request parts).
  - The fourth change: ADR 0015's Decision describes it, why the keys are declared rather than read
    (a table the handlers build with would rewrite each one), and the alternative; `docs/api/README.md`
    gains `ok`, `response`, the three kinds, what `?` means, the one refusal carrying more than
    `error` and `code` (a crew accepted but unable to start: 503 with `crew_id` and `status`), and
    the new gaps (keys a handler writes only in a state the sweep does not reach; a key written
    twice, which a set comparison cannot see). The duplicate-`engine_mode` roadmap item says its
    fix should add that check.
  - Found while measuring for the fourth change and recorded on the roadmap, not fixed here: request
    paths still allocate from the global bump. A 404, a 401 and every authenticated request keep 16
    bytes each, a successful login 696 and each audited write 416, against `response.cyr`'s own
    rule (router refusal arms, authn, login, JWT claims, audit details; file:line there).
  - `docs/development/state.md`: the two modules in the source table, the schema as the
    machine-readable surface above the route table, the suite, and a Hardening row.
  - `src/main.cyr`'s doubled "Entry point." comment is replaced by one that says it reads its
    arguments first.
- **The audit chain across a restart.**
  - Architecture note 001's audit row says the next entry links to the last stored one, and a new
    section says what the audit defect was and what a trail written before 0.1.13 shows.
  - The roadmap ticks the item. It records three follow-ups as open items: a verdict that can tell
    an old restart break from a tamper, a failed read at open that verifies as intact, and a failed
    write that leaves the chain's head on the entry it did not save, so the next start reports
    tampering (older than 0.1.13, found reviewing this fix).
  - `src/engine/audit.cyr`'s header and the seed's comment say why the head is seeded and what
    the value's lifetime is. The header's "a failed append leaves no hole to find" now carries a ⚠
    that a failed write is the exception, and the failure branch points to it. The comment on `agnostic_audit_bad_index` said the index was at offset
    24, and now says why it is read with the accessor.
  - ADR 0011 is unchanged: it decides how the newest entries are read, not how the chain links.
- **A crew named over 255 bytes.**
  - Architecture note 001's known-defect section becomes a section saying what the defect was and
    that it is fixed. The roadmap ticks the item. `src/engine/crewstore.cyr`'s header and the
    save's comment say what `cname` holds and why.
  - `docs/development/handoff.md` §5 said patra's `COL_STR` truncates silently. patra has refused
    a longer value since its 2026-08-18 audit, which is how this defect lost whole outcomes rather
    than cutting names. The note now says so and how to bind a `STR`. The comments in
    `src/engine/settings.cyr`, `src/engine/plugindata.cyr` and `tests/webgui.tcyr` that repeated
    the old claim are corrected; their door checks were right either way.
- **H6, the skill.**
  - The README's API section links `skills/agnostic/SKILL.md` and says how to install it (a
    symlink into the agent's skills folder); `docs/guides/getting-started.md` points to it.
  - The roadmap ticks H6, with what its own wording had wrong (`hierarchical` is a 400; `name` is
    required; only login is rate-limited; no route issues API keys; a preset is not a crew body),
    and the M7 bullet that names the skill. The 2026-10-03 research note carries a dated correction.
  - Three src comments contradicted the skill and are corrected, no behaviour change:
    `src/engine/crew.cyr` and `src/config.cyr` said `/ready` reports the engine mode, which only
    crew responses carry; `src/engine/presets.cyr` said a preset's agents can be posted as a crew's,
    which needs `agent_key` renamed and `celery_queue`/`redis_prefix` dropped first.
  - `docs/development/state.md`: the gate list, a line under the crew-surface table, and a Hardening
    row.
- **The release as a whole.** `docs/development/state.md` is refreshed for 0.1.13: its header,
  Version, Toolchain and Dependencies (nothing moved), and the Source, Tests and Hardening totals
  re-measured at the cut (31 suites, 2,347 assertions, 77 JavaScript tests, 1,063 definitions
  across 50 files, 27,314 lines), each beside 0.1.12's; 0.1.12's source was 25,572 lines,
  re-measured from its tag, where state.md had said 25,570. The roadmap's 0.1.13 tranche is marked
  shipped, its open follow-ups kept. Architecture note 001 and `docs/development/handoff.md` (now
  fifteen ADRs) no longer call 0.1.13 unreleased or count twelve. This entry's Known section lists
  every older defect the release recorded rather than fixed. H4's Swarm Command change is named as
  part of 0.5.0 here and on the roadmap, since no 0.4.1 was released.
  - The roadmap records two more "Found at 0.1.13" sections: the integration pass's (the coverage
    gate `CONTRIBUTING.md` names, and stale lines in `cyrius.cyml` and `CONTRIBUTING.md`) and the
    release verification's (`BENCHMARKS.md`, and `docs/development/handoff.md` §1). Known above
    lists all four.
  - The roadmap gains "Next re-pin — agnosai 2.1.5 (agnostic 0.1.14)": the re-pin, and the
    consumer halves of agnosai's B17 (crew events and status; its registry stores RUNNING), F7
    (`/plan?explain=selection`) and F6 (one trace from request to tool), with an open decision on
    per-task selection hints.
  - From the release verification. `SECURITY.md` asked a reporter for `agnostic --version`, which
    since this release prints usage and exits 2; it now asks for `cat VERSION` or the `version`
    field of `GET /ready`. `docs/development/handoff.md`'s version line named 0.1.10 and now
    points to `VERSION`, its M5 figures say they are M5's and point to `state.md`, and its refresh
    log records 0.1.13. The roadmap's file:line references for the 405 and for B17's comments are
    re-derived from this tree. `state.md`'s gate list names `gen-api-schema.sh --check` and no
    longer reads as if `gen-webgui.sh --check` ran `check-skill.py`; its Node line, and the header
    of `tests/webgui/swarm.test.mjs`, say the fakes answer as 0.1.13's server does; that file's
    pinned-estimate test names the page its figures were read from, Swarm Command 0.4.0's.

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
