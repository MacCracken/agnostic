# Configuration

agnostic is configured by its environment. A value that cannot be read stops the server at start-up
with a message on stderr; nothing falls back to a default in silence. `src/config.cyr` is the source
of truth.

## The server

| Variable | Default | What it does |
|---|---|---|
| `AGNOSTIC_ADDR` | `loopback` | Where to bind: `any` for 0.0.0.0, or `loopback`, `localhost` or `127.0.0.1`. Anything else is refused. |
| `AGNOSTIC_PORT` | `8000` | The port, 1 to 65535. Falls back to `PORT` when unset. |
| `AGNOSTIC_WORKERS` | `16` | Pool workers. One connection holds one worker while it is read and answered. |
| `AGNOSTIC_BACKLOG` | `128` | The listen backlog. |
| `AGNOSTIC_MAX_BODY_BYTES` | `1048576` | The largest request. Each worker keeps a buffer this size. |
| `AGNOSTIC_REQUEST_MS` | `15000` | How long a connection has from accept to a complete request. Past it the server answers 408 and closes. |
| `AGNOSTIC_IDLE_MS` | `30000` | The limit on one socket read. |
| `AGNOSTIC_REQUEST_ARENA_BYTES` | `65536` | A worker's request arena, and each chunk it grows by. Raised at start-up to `AGNOSTIC_MAX_BODY_BYTES` plus 4 KiB, so at the defaults it is about 1 MiB per worker. A worker keeps what its largest request took. |

`AGNOSTIC_REQUEST_MS` also sets how long a client that sends nothing can hold a worker, so lower is
safer. A slow link needs at least `AGNOSTIC_MAX_BODY_BYTES` divided by this budget: the defaults ask
for about 70 KB/s.

## Identity

| Variable | Default | What it does |
|---|---|---|
| `AGNOSTIC_AUTH` | `off` | `off` or `required`. Anything else is refused. With `off`, any bind but loopback is refused too. |
| `AGNOSTIC_BOOTSTRAP_EMAIL` | none | The first administrator, created once, on an empty store with `AGNOSTIC_AUTH=required`. |
| `AGNOSTIC_BOOTSTRAP_PASSWORD` | none | At least 12 characters. It is read, never logged, and has no effect once any user exists. Change it with `PUT /api/v1/auth/password` and unset it ([Users and tenants](users-and-tenants.md)). |
| `AGNOSTIC_JWT_SECRET` | random per process | At least 32 bytes, or the server refuses to start. It is read and never logged. Unset, a restart ends every session. Set it, and tokens survive a restart. Anyone who holds it can forge a token for any user. Changing it ends every session. |

## Storage

| Variable | Default | What it does |
|---|---|---|
| `AGNOSTIC_DB_PATH` | `agnostic.patra` | The database. One process per file. Set to mode 0600 at start-up. |
| `AGNOSTIC_AUDIT_PATH` | `agnostic-audit.patra` | The audit chain. A separate file, also 0600. |

[What survives a restart](../architecture/001-what-survives-a-restart.md) says what each holds.

## The engine

| Variable | Default | What it does |
|---|---|---|
| `AGNOSTIC_LLM_URL` | none | The gateway. Unset, crews run with placeholder output, and each response says so in `engine_mode`. A URL holding `user:pass@` is refused. |
| `AGNOSTIC_LLM_API_KEY` | none | The gateway's key. Read, never logged. |
| `AGNOSTIC_LLM_TIMEOUT_SECS` | agnosai's 600 s | The ceiling on one inference call, 1 to 86400. |
| `AGNOSTIC_CREW_TIMEOUT_SECS` | `3600` | The ceiling on a crew's wall clock, up to 86400. |

## Logging and tracing

| Variable | Default | What it does |
|---|---|---|
| `AGNOSTIC_LOG_LEVEL` | `info` | `error`, `warn`, `info`, `debug` or `trace`. |
| `AGNOSTIC_LOG_FORMAT` | text | `json` for structured output. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | none | A base URL for OTLP span export. Unset, nothing is exported. |
| `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` | none | A complete traces URL, used as it is. It wins over the base URL. |
| `OTEL_SERVICE_NAME` | `agnostic` | The service name on exported spans. |

## Behind a reverse proxy

agnostic serves plain HTTP, so TLS belongs to a proxy in front of it. Two things follow.

- Every client arrives from the proxy's address, and the login rate limit is per source. Five bad
  attempts from anyone then lock out everyone for that window. There is no trusted-proxy setting yet
  (roadmap, 0.3.x).
- A proxy that buffers requests also protects the worker pool: one connection holds one worker while
  it is read, and 16 idle sockets stall the server for `AGNOSTIC_REQUEST_MS`.
