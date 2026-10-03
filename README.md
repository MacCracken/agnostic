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
- **Swarm Command** — keeps swarms on the server, per tenant, prices them with headless simulations,
  runs them as live crews and reports what they really cost, and watches any crew on its map.

A view's state is in the URL (`/ui#plugin/crews?crew=<uuid>`), so a link to a crew can be shared.

## API

Every `POST` and `PUT` must send `Content-Type: application/json` — **415** otherwise. With
`AGNOSTIC_AUTH=off` (loopback only), address the server as `127.0.0.1`, `localhost` or `[::1]`; any
other `Host` is refused (**403**). Both are in [ADR 0006](docs/adr/0006-loopback-host-and-json-only-writes.md).

Crews belong to the tenant that submitted them, and `GET /api/v1/crews` lists yours; send an
`Idempotency-Key` header with `POST /api/v1/crews` to make a retry safe
([ADR 0008](docs/adr/0008-crews-belong-to-the-submitting-tenant.md)). Read a crew's progress with
`GET /api/v1/crews/{id}/events?after=N` — every event is numbered
([ADR 0009](docs/adr/0009-crew-progress-is-collected-by-the-server.md)).

## Tests

```sh
cyrius test                      # the Cyrius suites
./scripts/check-webgui-js.sh     # the WebGUI's JavaScript, under Node 20+
```

## License

GPL-3.0-only
