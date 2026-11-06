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
| `AGNOSTIC_TRUSTED_PROXIES` | none | Who may say who the client is: IPv4 addresses and networks, comma-separated, up to 32. Unset, `X-Forwarded-For` is ignored. `/0` and host bits under a mask are refused. See [below](#behind-a-reverse-proxy). |
| `AGNOSTIC_TARGET_HOSTS` | none | The hosts a crew's `target` may name, comma-separated, up to 64. Unset, every target is refused, and a crew with no target is unaffected. See [below](#what-crews-may-test). |
| `AGNOSTIC_GPU_TOOLS` | `off` | `off` or `on`. `on` runs vendor tools such as `nvidia-smi` once at start, and is how an NVIDIA GPU is seen. Off, nothing is spawned. See [below](#what-the-gpu-route-says). |
| `AGNOSTIC_METRICS_TOKEN` | none | A scraper's bearer token, at least 32 bytes. It opens `GET /api/v1/metrics` and nothing else. Unset, only a super administrator can read it. It is read and never logged. |
| `AGNOSTIC_TENANT_RATE_LIMIT` | `0` | Crews one tenant may submit in a minute, unless its own limit says otherwise. 0 is no limit. |
| `AGNOSTIC_TENANT_MAX_CREWS` | `0` | Crews of one tenant that may be unfinished at once, unless its own limit says otherwise. 0 is no limit. |

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

## What crews may test

A crew can name a `target`, the system it tests, and that is where its load and security tools will
point. So the hosts are the operator's to name, not the caller's: permission to submit a crew does not
choose one.

```sh
AGNOSTIC_TARGET_HOSTS=staging.example.com,10.0.0.5,[::1]
```

- An entry is a host, and a target must name exactly that host, ignoring case. `example.com` does not
  cover `www.example.com`, and `localhost` is not `127.0.0.1`. List what your targets spell.
- There are no ports and no wildcards. An entry with either stops the server from starting, as does
  anything else it cannot read, because a server with fewer hosts than you wrote is worse than one that
  says so.
- A refused target answers 403, and the audit trail records `crew.target_refused`.
- Today this bounds what a crew says it is testing: no crew calls a tool yet. It is on the list now
  so that a tool, when one runs, has a list to be held to.

## What the GPU route says

`GET /api/v1/gpu` lists the accelerators this host had when the server started, read once.

- **It sees what sysfs shows by default:** AMD, Intel, Vulkan and NPUs, and not NVIDIA, whose source is
  `nvidia-smi`. Set `AGNOSTIC_GPU_TOOLS=on` to run the vendor tools. Each runs under a deadline, and one that
  hangs holds up the start by about 20 seconds before it is killed. `vendor_tools` on the answer says which it
  was, so an empty list on an NVIDIA host does not read as no GPU.
- **It is a snapshot, so it has no free memory, utilization or temperature.** It says when it was taken in
  `detected_at`. A card added later is seen after a restart.
- **`warnings` counts what went wrong:** a tool that failed or hung, or a read that failed. The words are in the
  log. A tool that is not installed is not counted.
- **A crew is not held to this.** `gpu_required` chooses among a crew's agents. It does not look at the
  host, and inference happens at the gateway, usually on another machine. `gpu_required_enforced` says so.

[Deployment](deployment.md#list-a-gpu) has what an NVIDIA card needs under the example unit.

## Behind a reverse proxy

agnostic serves plain HTTP, so TLS belongs to a proxy in front of it. [Deployment](deployment.md) has a
working setup. Two things follow.

- Every client arrives from the proxy's address, and the login rate limit is per source. Set
  `AGNOSTIC_TRUSTED_PROXIES` to the proxy's address, or five bad attempts from anyone lock out everyone
  for that window. agnostic then reads `X-Forwarded-For` from the right, skipping listed addresses, so a
  client cannot pick its own limit by sending that header. `Forwarded` and `X-Real-IP` are not read.
- A proxy that buffers requests also protects the worker pool: one connection holds one worker while
  it is read, and 16 idle sockets stall the server for `AGNOSTIC_REQUEST_MS`.
