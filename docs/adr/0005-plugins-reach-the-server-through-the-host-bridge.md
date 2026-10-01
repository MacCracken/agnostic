# 0005 — Plugins reach the server only through the shell's host bridge, under their manifest's permissions

**Status**: Accepted
**Date**: 2026-10-01

## Context

[ADR 0004](0004-webgui-plugins-compiled-in-switched-at-run-time.md) runs every plugin in an
`<iframe sandbox="allow-scripts allow-downloads">`: an opaque origin with no session token, no
access to the shell, and no browser storage. It named the gap that left — a plugin that needs data
from this server cannot fetch it — as future work.

0.1.8 makes Swarm Command useful beyond a demo, and that needs three things the sandbox forbids:

- **Keep swarms**, per tenant on the server — not per browser, and not lost with the tab.
- **Read the preset library**, to offer a preset's agents as a crew roster.
- **Submit, watch and cancel real crews.**

The constraints are the ones 0004 was written around, and they still hold:

- **The token must never reach plugin code.** A script-injection bug in a plugin must not become
  "anything the user can do".
- **The server is the authority on roles.** Nothing a plugin is allowed may exceed what its user
  may do, and nothing in the browser may be trusted to enforce that.
- **Least privilege should be visible and reviewable.** Plugins are compiled in and reviewed
  (0004); what each may do should be part of what is reviewed, not an accident of its code.
- **An opaque origin cannot carry credentials safely.** Every sandboxed frame, `data:` URL and
  `file:` page shares `Origin: null`; a server that trusted it would trust them all.

## Decision

**A plugin talks to the server only by asking the shell, over `postMessage`. The shell makes the
request, with the user's own credential, when — and only when — the plugin's manifest permits that
method and path. A plugin's own documents are kept on the server, in the user's tenant.**

- **No network of its own.** A plugin page's CSP is now `connect-src 'none'` (it was `'self'`);
  the shell keeps `connect-src 'self'`.
- **Protocol 1.** The page posts `{type:'agnostic:hello'}`; the shell answers
  `{type:'agnostic:init', protocol, plugin:{id,name,version}, permissions, user:{auth, signedIn,
  role}}` — who the user is, never their token — and re-sends it after a sign-in or sign-out. A
  request is `{type:'agnostic:request', id, method, path, body?}`; the answer is
  `{type:'agnostic:response', id, status, data}`, status 0 when the server was never reached.
- **The shell's gate**, in order: the message must come from the plugin frame on screen
  (`e.source`); the method is GET, POST, PUT or DELETE; the path is `/api/v1/` followed by
  `[A-Za-z0-9/._-]`, with no `..` and no `//`; the method and path match one of the plugin's
  permissions; a GET or DELETE carries no body, and a body is JSON of at most 256 KB. A refusal is
  answered 400, 403 or 413 by the shell, before anything reaches the network. A 401 from the server opens
  the shell's sign-in.
- **Permissions are a closed list**, checked by `scripts/gen-webgui.sh` against each manifest,
  carried by `GET /api/v1/plugins`, and spelled out under each plugin in Settings:

  | Permission | Grants |
  |---|---|
  | `storage` | `GET /api/v1/plugins/<own id>/data`, and `GET`/`PUT`/`DELETE …/data/<key>` — its own documents only |
  | `presets:read` | `GET /api/v1/presets` and `GET /api/v1/presets/<name>` |
  | `definitions:read` | `GET /api/v1/agents/definitions` and `GET …/definitions/<key>` |
  | `crews:read` | `GET /api/v1/crews/<uuid>` and `GET /api/v1/crews/<uuid>/events` |
  | `crews:write` | `POST /api/v1/crews` and `POST /api/v1/crews/<uuid>/cancel` |

- **A permission is the plugin's ceiling, never a grant.** The server checks the user's role on
  every bridged request exactly as on any other.
- **Plugin documents** (`src/engine/plugindata.cyr`, `src/routes/plugindata.cyr`):
  `GET /api/v1/plugins/{id}/data` (READ) lists keys, update times and sizes;
  `GET|PUT|DELETE /api/v1/plugins/{id}/data/{key}` are READ, WRITE and WRITE. A key is
  `[a-z0-9][a-z0-9._-]*`, at most 64; a document is one JSON object of at most 32 KiB, stored and
  answered verbatim; a plugin keeps at most 256 per tenant (507 beyond). The tenant is the
  principal's, or `_` with authentication off or for a user without one. `PUT` is an upsert —
  201 or 200, and `created` says which — and writes and deletes are audited. The plugin must exist
  but need not be switched on, so switching one off loses nothing; Settings shows what each keeps
  and lets a user who may write delete it.
- **`data` gains `mixed`**: a view that shows both simulated and live missions, and labels each one
  itself. Swarm Command is `mixed` from 0.2.0.

## Consequences

- **Positive** — What a plugin may do is in its manifest, reviewed with its code, and shown to the
  people who switch it on. A compromised plugin can make only its granted calls, and only as far as
  its user may: Swarm Command can start crews, which is its purpose, but cannot read the audit
  trail, users or settings, or switch plugins. No token ever enters plugin code. Tenant isolation is
  enforced by the store, under the server's own principal. Saved state survives restarts and follows
  the user from browser to browser.
- **Negative** — Every request is asynchronous and makes an extra hop through the shell; there is
  no streaming, so live crews are polled. The permission table is a contract kept in two places —
  the shell's `permitted()` and the generator's `PERMISSIONS` — plus this ADR and the guide. A plugin
  opened in its own tab has no shell and so no bridge: it must degrade (Swarm Command keeps swarms in
  that browser and cannot run live crews there). Documents are capped at 32 KiB and 256 per tenant.
- **Neutral** — Streaming (SSE or WebSocket, M7) would replace polling without changing the gate.
  Per-user preferences can be keyed documents. A new permission is a change to the shell, the
  generator, the guide and this table.

## Alternatives considered

- **Hand the plugin the token** (post it into the frame, or add `allow-same-origin`). Rejected: the
  plugin would be exactly as powerful as its user — what 0004 exists to prevent.
- **A server-minted, scoped token per plugin.** Rejected for now: it needs issuance, expiry,
  revocation and a scope model in `src/auth/`, to achieve what the shell's gate already achieves for
  compiled-in plugins without a new credential. It becomes worth it if third-party plugins ever run
  outside the shell.
- **CORS for the sandboxed origin.** Rejected: that origin is `null`, shared by every sandboxed frame
  and `data:` URL; admitting it with credentials would admit them all.
- **The shell pushes data into the frame** (the sketch in 0004's consequences). Rejected in favour of
  plugin-driven requests: the shell stays one generic gate instead of a data pump written per plugin.
- **Browser storage for plugin state.** Unavailable in an opaque origin, and per browser rather than
  per tenant — it is only Swarm Command's fallback when opened standalone.
