# agnostic

Written in [Cyrius](https://github.com/MacCracken/cyrius).

## Build

```sh
cyrius deps                              # resolve stdlib deps
cyrius build src/main.cyr build/agnostic    # compile
cyrius test                              # run [build].test + tests/*.tcyr
```

## WebGUI

`./build/agnostic` serves the WebGUI at `http://127.0.0.1:8000/ui`. Its views are compiled-in plugins
that an administrator switches on in its Settings tab — see
[`docs/guides/webgui-plugins.md`](docs/guides/webgui-plugins.md):

- **Crews** — every crew of your tenant by status; a crew's plan, live progress, results and real
  cost; cancel one that is running.
- **Library** — the preset crews built in, and the agent definitions stored here, which it can write.
- **Audit trail** — whether the tamper-evident chain verified, and its newest entries (administrators).
- **Swarm Command** — keeps swarms on the server, per tenant, prices them with headless simulations
  beside one agent given the same tokens, runs them as live crews and reports what they really
  cost, and watches any crew on its map.

A view's state is in the URL (`/ui#plugin/crews?crew=<uuid>`), so a link to a crew can be shared.

## API

`./build/agnostic api schema` prints the HTTP API as JSON — every route with its method,
authentication, permission and the plugin permissions that grant it, its success statuses and the
top-level keys of what it answers, the request bodies' fields, the error codes and the wire
vocabularies. Its output is committed as
[`docs/api/generated/schema.json`](docs/api/generated/schema.json); [`docs/api/`](docs/api/README.md)
says what it covers and what it leaves out ([ADR 0015](docs/adr/0015-the-http-api-is-described-by-a-generated-schema.md)).

Every `POST` and `PUT` must send `Content-Type: application/json` — **415** otherwise. With
`AGNOSTIC_AUTH=off` (loopback only), address the server as `127.0.0.1`, `localhost` or `[::1]`; any
other `Host` is refused (**403**). Both are in [ADR 0006](docs/adr/0006-loopback-host-and-json-only-writes.md).

Crews belong to the tenant that submitted them, and `GET /api/v1/crews` lists yours; send an
`Idempotency-Key` header with `POST /api/v1/crews` to make a retry safe
([ADR 0008](docs/adr/0008-crews-belong-to-the-submitting-tenant.md)). Read a crew's progress with
`GET /api/v1/crews/{id}/events?after=N` — every event is numbered, and a reader that falls more
than 256 events behind is told how many it missed (`missed`)
([ADR 0009](docs/adr/0009-crew-progress-is-collected-by-the-server.md)). A crew that was still
running when the server stopped answers `interrupted` after it restarts, not 404 — submit it again
([ADR 0013](docs/adr/0013-a-crew-interrupted-by-a-restart-is-interrupted.md); what else survives a
restart is [architecture 001](docs/architecture/001-what-survives-a-restart.md)).

**Driving it from a coding agent.** [`skills/agnostic/SKILL.md`](skills/agnostic/SKILL.md) is an
Agent Skill that teaches Claude Code, Codex or any SKILL.md-aware agent this API: checking readiness
and the auth mode, submitting a crew with an `Idempotency-Key`, following it with `events?after=`,
reading its outcome, usage and cost, and cancelling it. Its guardrails stop the agent when `/ready`
fails and let it cancel only crews it submitted. `scripts/check-skill.py` checks it against
`docs/api/generated/schema.json`. To install it, symlink the directory into the agent's skills
folder so it stays current with this checkout. For Claude Code that is
`ln -s "$PWD/skills/agnostic" ~/.claude/skills/agnostic`, or a project's `.claude/skills/`.

## Tests

```sh
cyrius test                      # the Cyrius suites
./scripts/check-webgui-js.sh     # the WebGUI's JavaScript, under Node 20+
```

## License

GPL-3.0-only
