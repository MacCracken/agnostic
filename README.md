# agnostic

Written in [Cyrius](https://github.com/MacCracken/cyrius).

## Build

```sh
cyrius deps                              # resolve stdlib deps
cyrius build src/main.cyr build/agnostic    # compile
cyrius test                              # run [build].test + tests/*.tcyr
```

## WebGUI

`./build/agnostic` serves the WebGUI at `http://127.0.0.1:8000/ui`. Views such as Swarm Command are
compiled-in plugins that an administrator switches on in its Settings tab — see
[`docs/guides/webgui-plugins.md`](docs/guides/webgui-plugins.md). Swarm Command keeps swarms on the
server, per tenant, prices them with headless simulations, and runs them as live crews.

## API

Every `POST` and `PUT` must send `Content-Type: application/json` — **415** otherwise. With
`AGNOSTIC_AUTH=off` (loopback only), address the server as `127.0.0.1`, `localhost` or `[::1]`; any
other `Host` is refused (**403**). Both are in [ADR 0006](docs/adr/0006-loopback-host-and-json-only-writes.md).

## License

GPL-3.0-only
