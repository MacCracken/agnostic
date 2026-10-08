# Architecture Decision Records

Decisions about agnostic — what we chose, the context, and the consequences we accept. Use these when a future reader would reasonably ask *"why did we do it this way?"*

## Conventions

- **Filename**: `NNNN-kebab-case-title.md`, zero-padded to four digits. Never renumber.
- **One decision per ADR.** If a decision supersedes a prior one, add a new ADR and set the old one's status to `Superseded by NNNN`.
- **Status lifecycle**: `Proposed` → `Accepted` → (optionally) `Superseded` or `Deprecated`.
- Use [`template.md`](template.md) as the starting point.

## ADR vs. architecture note vs. guide

| Kind | Lives in | Answers |
|---|---|---|
| ADR | `docs/adr/` | *Why did we choose X over Y?* |
| Architecture note | `docs/architecture/` | *What non-obvious constraint is true about the code?* |
| Guide | `docs/guides/` | *How do I do X?* |

## Index

| ADR | Decision |
|---|---|
| [0001](0001-health-and-readiness-are-separate.md) | Health and readiness are separate probes |
| [0002](0002-daimon-tier-1-deferred.md) | Daimon Tier 1 registration is deferred |
| [0003](0003-one-store-lock-not-a-handle-per-worker.md) | One store lock, not a patra handle per worker |
| [0004](0004-webgui-plugins-compiled-in-switched-at-run-time.md) | WebGUI plugins are compiled in and switched at run time |
| [0005](0005-plugins-reach-the-server-through-the-host-bridge.md) | Plugins reach the server only through the shell's host bridge, under their manifest's permissions |
| [0006](0006-loopback-host-and-json-only-writes.md) | With authentication off the server answers only a loopback Host, and every POST and PUT must declare JSON |
| [0007](0007-plugin-requests-are-checked-by-the-server.md) | Plugin requests are checked by the server, against one permission vocabulary |
| [0008](0008-crews-belong-to-the-submitting-tenant.md) | Crews belong to the tenant that submitted them, are listed by cursor, and a keyed submit is idempotent |
| [0009](0009-crew-progress-is-collected-by-the-server.md) | Crew progress is collected by the server and read by cursor, not streamed |
| [0010](0010-views-link-through-the-shell-and-share-one-bridge-client.md) | Views link to each other through the shell, and every plugin carries one bridge client |
| [0011](0011-audit-entries-are-read-from-a-bounded-copy.md) | The audit trail's newest entries are read from a bounded copy, not the store |
| [0012](0012-a-cancelled-crew-keeps-its-finished-results.md) | A cancelled crew keeps the results its finished tasks produced |
| [0013](0013-a-crew-interrupted-by-a-restart-is-interrupted.md) | A crew a restart interrupted answers `interrupted`, not 404 |
| [0014](0014-the-estimators-one-agent-baseline-is-its-own-model.md) | Swarm Command's estimator prices one agent at the swarm's own token spend, with its own model, not the Sim's |
| [0015](0015-the-http-api-is-described-by-a-generated-schema.md) | The HTTP API is described by a schema generated from the server's own tables (`agnostic api schema`), and a committed snapshot freezes it |
| [0016](0016-a-selection-explanation-is-recomputed-at-read-time.md) | A crew's agent selection is explained by recomputing it when asked (`/plan?explain=selection`), within a fixed budget and a shared scratch |
| [0017](0017-a-task-carries-selection-hints.md) | A task carries the hints the engine selects its agent by (`required_tools`, `complexity`, `domain`, `gpu_required`), checked at the door and forwarded into its context |
| [0018](0018-crews-join-the-request-trace-and-export-is-opt-in.md) | A crew joins the trace of the request that submitted it, inbound traceparents are checked by the engine's own parser, and OTLP span export is switched on by `OTEL_EXPORTER_OTLP_ENDPOINT` |
| [0019](0019-an-interrupted-crew-keeps-what-its-finished-tasks-answered.md) | An interrupted crew keeps the output its finished tasks answered, and the start-up sweep reports it |
| [0020](0020-each-request-records-an-http-server-span.md) | Each request records an HTTP SERVER span through agnosai's exporter, and an inbound traceparent gets a child, so crews nest under the request |
