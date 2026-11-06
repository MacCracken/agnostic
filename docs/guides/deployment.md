# Deploying agnostic

agnostic is one static binary and two data files. It needs no database server, no broker and no
container. It serves plain HTTP, so TLS belongs to a reverse proxy in front of it.

This guide sets up that pair on one Linux machine with systemd. [Configuration](configuration.md)
lists every setting.

## Get the binary

Each release publishes `agnostic` (x86_64), `agnostic-aarch64` and a `SHA256SUMS` file. Check the
binary before you run it:

```bash
TAG=0.3.1
curl -LO https://github.com/MacCracken/agnostic/releases/download/$TAG/agnostic
curl -LO https://github.com/MacCracken/agnostic/releases/download/$TAG/SHA256SUMS
```

`SHA256SUMS` lists it as `build/agnostic`, so compare the two hashes by eye or by script:

```bash
sha256sum agnostic
grep 'build/agnostic$' SHA256SUMS
```

Then install it, and make the user it runs as:

```bash
sudo install -m 755 agnostic /usr/local/bin/agnostic
sudo useradd --system --home-dir /var/lib/agnostic --shell /usr/sbin/nologin agnostic
```

## Write its settings

The settings hold secrets, so the file is readable only by root. systemd reads it before it drops to
the `agnostic` user.

```bash
sudo mkdir -p /etc/agnostic
sudo install -m 600 /dev/null /etc/agnostic/agnostic.env
sudoedit /etc/agnostic/agnostic.env
```

Start from this, with a value of your own for each `change-me`:

```ini
AGNOSTIC_AUTH=required
AGNOSTIC_ADDR=loopback
AGNOSTIC_PORT=8000

# `openssl rand -hex 32`. Without it, a restart signs everyone out.
AGNOSTIC_JWT_SECRET=change-me

# The first super administrator. Used once, on an empty database.
AGNOSTIC_BOOTSTRAP_EMAIL=you@example.com
AGNOSTIC_BOOTSTRAP_PASSWORD=change-me-to-12-or-more

# The proxy. Without this, every client shares the proxy's login limit.
AGNOSTIC_TRUSTED_PROXIES=127.0.0.1

# Your LLM gateway. Unset, crews run with placeholder output.
AGNOSTIC_LLM_URL=http://127.0.0.1:8088
AGNOSTIC_LLM_API_KEY=change-me

# A scraper's own credential. `openssl rand -hex 32`.
AGNOSTIC_METRICS_TOKEN=change-me
```

A value that cannot be read stops the server with a message, rather than falling back to a default.

## Run it under systemd

[`docs/examples/agnostic.service`](../examples/agnostic.service) is a unit file that keeps the
database in `/var/lib/agnostic` and gives the process no more than it needs.

```bash
sudo cp docs/examples/agnostic.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now agnostic
```

Check it from the machine:

```bash
curl -s localhost:8000/health
curl -s localhost:8000/ready
journalctl -u agnostic -n 20
```

`/health` says the process is up. `/ready` says it can do its work, and is what a load balancer
should ask. Each crew response also says whether it ran for real, in `engine_mode`.

A stop takes as long as the outcomes still to be written. The unit allows 120 s. A crew whose outcome
is not written reads `interrupted` after the restart, so shorten that with care.

## Put a proxy in front

The proxy does three jobs: it ends TLS, it tells agnostic who the client is, and it buffers requests,
which keeps a slow client from holding one of agnostic's workers for 15 seconds.

nginx:

```nginx
server {
    listen 443 ssl;
    server_name agnostic.example.com;
    ssl_certificate     /etc/letsencrypt/live/agnostic.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/agnostic.example.com/privkey.pem;

    # agnostic's own limit, AGNOSTIC_MAX_BODY_BYTES.
    client_max_body_size 1m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_request_buffering on;
    }
}
```

Caddy sets `X-Forwarded-For` itself. Check its reverse-proxy buffering options if you want it to hold a
slow client's request the way nginx does above:

```caddy
agnostic.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

### If the proxy is on another machine

Bind to every interface, name the proxy, and keep everything else off the port with a firewall:

```ini
AGNOSTIC_ADDR=any
AGNOSTIC_TRUSTED_PROXIES=10.0.0.5
```

`AGNOSTIC_TRUSTED_PROXIES` takes addresses and networks, such as `10.0.0.5,10.1.0.0/16`, up to 32 of
them. Name only what you run: anyone on the list can claim to be any client.

### How the client's address is found

agnostic reads `X-Forwarded-For` only when the connection comes from a listed proxy, and it reads
from the right, skipping listed addresses. The first address left is the client. A client's own
`X-Forwarded-For` ends up to the left of what your proxy adds, so it cannot choose its own login
limit. This holds whether your proxy adds to the header, as nginx does, or adds a second line, as
HAProxy does.

`Forwarded` and `X-Real-IP` are not read, so a proxy has to send `X-Forwarded-For`.

## First sign-in

Open `https://agnostic.example.com/ui` and sign in with the bootstrap address.

1. Change that password. It is in a file on disk.
2. Take `AGNOSTIC_BOOTSTRAP_PASSWORD` out of the settings file. It has no effect once a user exists.
3. In **Settings**, switch on the views you want. **Users** manages users and tenants, and every view
   starts switched off.

[Users and tenants](users-and-tenants.md) covers the rest, including keys for scripts.

## Watch it

`GET /api/v1/metrics` serves Prometheus text. A super administrator can read it, and so can a
scraper holding `AGNOSTIC_METRICS_TOKEN`, a credential that opens this one route and nothing else:

```yaml
scrape_configs:
  - job_name: agnostic
    metrics_path: /api/v1/metrics
    authorization:
      credentials_file: /etc/prometheus/agnostic.token
    static_configs:
      - targets: ["127.0.0.1:8000"]
```

Worth an alert:

- `agnostic_refusals_total{reason="unauthenticated"}` rising fast: someone is guessing.
- `agnostic_refusals_total{reason="argon_shed"}`: logins are being refused for want of capacity.
- `agnostic_audit_dropped_total` above 0: audit records could not be stored.
- `agnostic_http_responses_total{class="5xx"}` rising.

Refusals also reach the audit trail: at most 16 entries a minute with the details, then one entry
counting the rest, so a flood cannot fill the trail.

## Limit your tenants

Set a default for every tenant, and raise or lower it per tenant in the **Users** view or with
`PUT /api/v1/tenants/{key}`:

```ini
# Crews one tenant may submit in a minute.
AGNOSTIC_TENANT_RATE_LIMIT=60
# Crews of one tenant that may be unfinished at once.
AGNOSTIC_TENANT_MAX_CREWS=10
```

Over either limit a submission gets a 429 with `Retry-After`. Nothing else a tenant does is limited.

## Back up and upgrade

The database and the audit trail are `agnostic.patra` and `agnostic-audit.patra` in
`/var/lib/agnostic`. Copy them with the server stopped: a copy of a file in use is not a backup.

```bash
sudo systemctl stop agnostic
sudo tar -C /var/lib/agnostic -czf agnostic-backup.tar.gz agnostic.patra agnostic-audit.patra
sudo systemctl start agnostic
```

To upgrade, take that backup, stop the server, replace the binary and start it. Tables gain what the
new version needs when it starts. Read the release's `CHANGELOG` first, for anything marked as a
breaking change.

Only one process can use a database at a time. A second is refused at start-up, and that is what
keeps a restart from interrupting another process's crews.

## If you are locked out

Stop the server, then set a password from the machine that holds the database. This runs the
recovery command as the service does, with its user and its settings:

```bash
sudo systemctl stop agnostic
read -rs PW
printf '%s\n' "$PW" | sudo systemd-run --pipe --wait --collect -p User=agnostic \
  -p EnvironmentFile=/etc/agnostic/agnostic.env -p WorkingDirectory=/var/lib/agnostic \
  /usr/local/bin/agnostic admin reset-password you@example.com
sudo systemctl start agnostic
```

## Running without systemd

Nothing above needs it. The binary reads its settings from the environment, writes to the paths in
`AGNOSTIC_DB_PATH` and `AGNOSTIC_AUDIT_PATH`, and stops cleanly on SIGTERM. Under another supervisor,
send SIGTERM and allow it time.
