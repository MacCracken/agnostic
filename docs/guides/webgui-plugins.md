# WebGUI plugins — switching one on, and adding one

The WebGUI is served at **`/ui`** (`http://127.0.0.1:8000/ui` on the default bind). It has an
Overview, a tab for each plugin that is switched on, and Settings. Why plugins are compiled in rather
than loaded is [ADR 0004](../adr/0004-webgui-plugins-compiled-in-switched-at-run-time.md); how they
reach the server is [ADR 0005](../adr/0005-plugins-reach-the-server-through-the-host-bridge.md).

## Switch a plugin on

Every plugin starts **off**. Switching one needs the **admin** role, applies to the whole
deployment, survives a restart, and is recorded in the audit trail.

- **From the WebGUI:** Settings → Plugins → flip the switch. With `AGNOSTIC_AUTH=required` the shell
  asks you to sign in first.
- **From the API:**

```bash
curl -X PUT -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"enabled": true}' http://127.0.0.1:8000/api/v1/plugins/swarm
```

⚠ Every `POST` and `PUT` must say `Content-Type: application/json` — without it the answer is
**415** ([ADR 0006](../adr/0006-loopback-host-and-json-only-writes.md)). With `AGNOSTIC_AUTH=off`,
address the server as `127.0.0.1`, `localhost` or `[::1]`: any other `Host` is refused with 403.

`GET /api/v1/plugins` lists every plugin with its state and its permissions. A switched-off plugin's
page, `/ui/plugins/<id>`, answers 404. Switching a plugin off keeps its stored documents; Settings
shows them under the plugin, with a **Delete all** for anyone who may write.

⚠ **Read the `data` field.** `"simulated"` means the view runs on its own simulator and shows no real
crew activity; the shell badges it SIMULATED. `"mixed"` means the view shows both, and labels each
mission itself — Swarm Command is `mixed`: SIM on a simulation, LIVE on a real crew.

## Add a plugin

1. **Create `src/webgui/plugins/<id>/`.** The id is `[a-z0-9][a-z0-9-]*`, at most 32 characters,
   and is also the directory name.
2. **Write `plugin.json`** with exactly these keys — an unknown or missing key fails the generator:

   ```json
   {
     "id": "my-view",
     "name": "My View",
     "description": "What it shows, in a sentence or two.",
     "version": "0.1.0",
     "data": "simulated",
     "entry": "index.html",
     "permissions": []
   }
   ```

   `data` is `simulated`, `live` or `mixed`. Say `live` only when every number on screen comes from
   this server, and `mixed` only when the page labels each view as one or the other.
   `permissions` lists what the page may ask the server for — see below; ask for the least you
   need, because Settings shows the list to whoever switches the plugin on.
3. **Write `index.html`: one self-contained page.** The generator refuses a page that its CSP would
   break, so these are build errors, not browser surprises:
   - no external scripts, stylesheets, images or fonts — inline everything (`default-src 'none'`);
   - no inline event handlers (`onclick=`) and no `javascript:` URLs — use `addEventListener`;
     inline `<script>` blocks are fine, and are admitted by hash;
   - LF line endings, and no NUL bytes;
   - no line that starts with `fn`, `var`, `enum`, `struct` or `include` at column 0 — the gates
     that scan `src/` read such a line as a Cyrius definition. Indent it.
4. **Add the id to `PLUGINS` in `scripts/gen-webgui.sh`.** The list is the order plugins are listed
   and tabbed in; a directory missing from it fails the generator.
5. **Regenerate, build, test:**

```bash
./scripts/gen-webgui.sh && cyrius build src/main.cyr build/agnostic && cyrius test
```

## What a plugin page can and cannot do

The shell frames a plugin in `<iframe sandbox="allow-scripts allow-downloads">`. The page runs in an
**opaque origin**, under `connect-src 'none'`, so:

- it **can** run scripts, draw, take keyboard and mouse input, and save files the user downloads;
- it **cannot** read the shell's session token, reach the network, or touch the shell's DOM —
  `localStorage` and `sessionStorage` throw, so wrap them in `try`/`catch`; `window.confirm()` and
  `alert()` are blocked too (no `allow-modals`), so draw your own dialogs;
- it **can ask the shell** to call the API for it, within its `permissions` — below;
- opened directly at `/ui/plugins/<id>` (the shell's "Open in a new tab"), it runs unsandboxed, under
  its CSP, in a tab holding no session: the link is `noopener`, so the shell's `sessionStorage` —
  where its token lives — is not copied into it. There is no shell there, so no bridge: a page should
  notice (no `agnostic:init` arrives) and degrade.

## Reaching the server: the host bridge

A plugin asks; the shell checks the request against the plugin's `permissions`, makes it with the
signed-in user's credential, and posts the answer back. The server still checks the user's role, so
a permission is the most a plugin can do, never more than its user can.

| Permission | The plugin may call |
|---|---|
| `storage` | `GET /api/v1/plugins/<own id>/data` · `GET`, `PUT`, `DELETE /api/v1/plugins/<own id>/data/<key>` |
| `presets:read` | `GET /api/v1/presets` · `GET /api/v1/presets/<name>` |
| `definitions:read` | `GET /api/v1/agents/definitions` · `GET /api/v1/agents/definitions/<key>` |
| `crews:read` | `GET /api/v1/crews/<uuid>` · `GET /api/v1/crews/<uuid>/events` |
| `crews:write` | `POST /api/v1/crews` · `POST /api/v1/crews/<uuid>/cancel` |

Anything else is answered **403 by the shell** without reaching the network; a malformed path
(`..`, `//`, characters outside `[A-Za-z0-9/._-]`) or a body on a GET or DELETE is **400**, and a
body over 256 KB is **413**. A 401 from the server opens the shell's sign-in.

The protocol (version 1), from the page's side:

```js
// 1. Say hello; the shell answers with who the user is — never their token.
window.parent.postMessage({ type: 'agnostic:hello', protocol: 1 }, '*');
// ← { type: 'agnostic:init', protocol: 1, plugin: { id, name, version }, permissions: [...],
//     user: { auth: 'off' | 'required' | 'unknown', signedIn, role } }   — re-sent on sign-in/out

// 2. Ask. `id` correlates the answer; `body` is JSON (≤ 256 KB), never on GET or DELETE.
window.parent.postMessage({ type: 'agnostic:request', id: 'q1', method: 'GET', path: '/api/v1/presets' }, '*');
// ← { type: 'agnostic:response', id: 'q1', status: 200, data: {...} }   — status 0: never reached the server
```

Accept messages only from `window.parent` (`event.source === window.parent`). Swarm Command's
`Host` class (`src/webgui/plugins/swarm/index.html`, section 1b) is a complete client to copy.

### Keeping documents: `storage`

A plugin's documents live on the server **in the user's tenant** (`_` with authentication off), and
outlive the plugin being switched off.

| Call | Answer |
|---|---|
| `GET /api/v1/plugins/<id>/data` | `{documents: [{key, updated, bytes}], total, scope}` — never the documents |
| `GET /api/v1/plugins/<id>/data/<key>` | the document, byte for byte as it was stored · 404 |
| `PUT /api/v1/plugins/<id>/data/<key>` | **201** created / 200 replaced, `{key, updated, bytes, created}` · 400 not JSON · 413 · 422 not an object or bad key · **507** full |
| `DELETE /api/v1/plugins/<id>/data/<key>` | `{key, status: "deleted"}` · 404 |

A key is `[a-z0-9][a-z0-9._-]*`, at most 64 characters; a document is one JSON object of at most
**32 KiB**; a plugin keeps at most **256** documents per tenant. Reading is READ, writing is WRITE;
writes and deletes are audited.

## Swarm Command

Swarm Command keeps **swarms**: a mission, its tasks (generated by a template, or your own), and
every capability with a default — roles and their caps, models and prices, tools, regions with their
caps and per-second prices, the budget, and the failure model. From a swarm's card you can:

- **Simulate** it, on screen, deterministically (same seed, same run);
- **Estimate** it — eight headless simulations on different seeds, reporting the spread of cost and
  duration and how often it overspends — to price a swarm before running anything;
- **Run it live** — its tasks submitted to this server as a crew (one agent per role, or a preset's
  agents), watched as it runs, cancellable; and **watch** an earlier crew again.

Swarms are this plugin's documents (`swarm-<id>`), so they are per tenant. Opened in its own tab,
Swarm Command keeps them in that browser instead, and cannot run live crews.
