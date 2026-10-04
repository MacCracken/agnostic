# WebGUI plugins — switching one on, and adding one

The WebGUI is served at **`/ui`** (`http://127.0.0.1:8000/ui` on the default bind). It has an
Overview, a tab for each plugin that is switched on, and Settings. Why plugins are compiled in rather
than loaded is [ADR 0004](../adr/0004-webgui-plugins-compiled-in-switched-at-run-time.md); how they
reach the server is [ADR 0005](../adr/0005-plugins-reach-the-server-through-the-host-bridge.md); how
they link to each other is [ADR 0010](../adr/0010-views-link-through-the-shell-and-share-one-bridge-client.md).

This build carries four:

| Plugin | Shows | `data` |
|---|---|---|
| **Swarm Command** (`swarm`) | an RTS-style map of a swarm — simulated, estimated, or a live crew | `mixed` |
| **Crews** (`crews`) | every crew in your tenant: filter by status, a crew's plan, live progress, results and cost; cancel | `live` |
| **Library** (`library`) | the preset crews built in, and the agent definitions stored here — create, edit, delete, or save a preset's agent as one | `live` |
| **Audit trail** (`audit`) | whether the audit chain verified, what was dropped, and its newest entries — administrators only | `live` |

A view's state is in the URL — `/ui#plugin/crews?crew=<uuid>` opens that crew — so a link to it can
be bookmarked or shared; it opens only where that view is switched on.

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

`GET /api/v1/plugins` lists every plugin with its state and its permissions, and the permission
vocabulary itself (`catalogue`). A switched-off plugin's page, `/ui/plugins/<id>`, answers 404 — and
since 0.1.9 a copy of it already open somewhere stops working on its next request: the server refuses
it (`403`, `code: plugin_off`) and the shell leaves the view. Switching a plugin off keeps its stored
documents; Settings shows them under the plugin, with a **Delete all** for anyone who may write.

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
   `permissions` lists what the page may ask the server for — names from
   `src/webgui/permissions.json`, see below; ask for the least you need, because Settings shows the
   list to whoever switches the plugin on. A name the vocabulary does not hold fails the generator.
3. **Write `index.html`: one self-contained page.** The generator refuses a page that its CSP would
   break, so these are build errors, not browser surprises:
   - no external scripts, stylesheets, images or fonts — inline everything (`default-src 'none'`);
   - no inline event handlers (`onclick=`) and no `javascript:` URLs — use `addEventListener`;
     inline `<script>` blocks are fine, and are admitted by hash;
   - LF line endings, and no NUL bytes;
   - no line that starts with `fn`, `var`, `enum`, `struct` or `include` at column 0 — the gates
     that scan `src/` read such a line as a Cyrius definition. Indent it.
4. **Carry the bridge client.** If `permissions` is not empty, the page must carry
   `src/webgui/kit/host.js` — put an empty pair of markers at the top of an inline script and let
   the generator fill it (step 6):

   ```js
   /* agnostic-kit:host begin */
   /* agnostic-kit:host end */
   ```

   The copy is verified byte for byte on every build: edit `src/webgui/kit/host.js`, never a page's
   copy, and run `--sync-kit` again.
5. **Add the id to `PLUGINS` in `scripts/gen-webgui.sh`.** The list is the order plugins are listed
   and tabbed in; a directory missing from it fails the generator.
6. **Fill in the client, regenerate, build, test:**

```bash
./scripts/gen-webgui.sh --sync-kit && cyrius build src/main.cyr build/agnostic && cyrius test
```

7. **Test the page's logic under Node.** Put `tests/webgui/<id>.test.mjs` beside the others:
   `tests/webgui/harness.mjs` evaluates your page's inline scripts in a `vm` context, so a test calls
   your own functions on the exact bytes that are embedded and served. Keep top-level code free of
   DOM access (start the app behind a `document` check) so it loads there.

```bash
./scripts/check-webgui-js.sh
```

## What a plugin page can and cannot do

The shell frames a plugin in `<iframe sandbox="allow-scripts allow-downloads">`. The page runs in an
**opaque origin**, under `connect-src 'none'`, so:

- it **can** run scripts, draw, take keyboard and mouse input, and save files the user downloads;
- it **cannot** read the shell's session token, reach the network, or touch the shell's DOM —
  `localStorage` and `sessionStorage` throw, so wrap them in `try`/`catch`; `window.confirm()` and
  `alert()` are blocked too (no `allow-modals`), so draw your own dialogs; and a `<form>` never fires
  `submit` (no `allow-forms`) — save on a button's click instead;
- it **can ask the shell** to call the API for it, within its `permissions` — below — with at most
  16 requests in flight (the 17th is answered 429 by the shell);
- opened directly at `/ui/plugins/<id>` (the shell's "Open in a new tab"), it runs unsandboxed, under
  its CSP, in a tab holding no session: the link is `noopener`, so the shell's `sessionStorage` —
  where its token lives — is not copied into it. There is no shell there, so no bridge: a page should
  notice (no `agnostic:init` arrives) and degrade.

## Reaching the server: the host bridge

A plugin asks; the shell checks the request against the plugin's `permissions`, makes it with the
signed-in user's credential and an `X-Agnostic-Plugin: <id>` header, and posts the answer back. The
**server checks the same permissions again** on every such request (ADR 0007) and refuses outside them
with `403` and a `code` — `plugin_forbidden`, `plugin_off`, `plugin_unknown` — and it still checks the
user's role, so a permission is the most a plugin can do, never more than its user can.

The vocabulary lives in **one file, `src/webgui/permissions.json`**: each permission's name, the words
Settings shows for it, and the routes it grants. The generator validates manifests against it, the
server enforces it, and the shell reads it from `GET /api/v1/plugins` (`catalogue`). Today:

| Permission | The plugin may call |
|---|---|
| `storage` | `GET /api/v1/plugins/<own id>/data` · `GET`, `PUT`, `DELETE /api/v1/plugins/<own id>/data/<key>` |
| `presets:read` | `GET /api/v1/presets` · `GET /api/v1/presets/<name>` |
| `definitions:read` | `GET /api/v1/agents/definitions` · `GET /api/v1/agents/definitions/<key>` |
| `definitions:write` | `POST /api/v1/agents/definitions` · `PUT`, `DELETE /api/v1/agents/definitions/<key>` |
| `crews:read` | `GET /api/v1/crews` · `GET /api/v1/crews/<uuid>` · `…/events` · `…/plan` |
| `crews:write` | `POST /api/v1/crews` · `POST /api/v1/crews/<uuid>/cancel` |
| `audit:read` | `GET /api/v1/audit` · `GET /api/v1/audit/entries` — ADMIN routes: the user must be an administrator too |

Anything else is answered **403 by the shell** without reaching the network; a malformed path (`..`,
`//`, characters outside `[A-Za-z0-9/._-]`, or a query string outside `[A-Za-z0-9._~=&%-]`) or a body
on a GET or DELETE is **400**, and a body over 256 KB is **413**. A 401 from the server opens the
shell's sign-in.

The protocol (version 1), from the page's side:

```js
// 1. Say hello; the shell answers with who the user is — never their token — and what its bridge carries.
window.parent.postMessage({ type: 'agnostic:hello', protocol: 1 }, '*');
// ← { type: 'agnostic:init', protocol: 1, features: ['query', 'revisions', 'idempotency', 'navigate'],
//     plugin: { id, name, version }, permissions: [...],
//     user: { auth: 'off' | 'required' | 'unknown', signedIn, role },
//     params: 'crew=…',                  — this view's part of the URL: #plugin/<id>?<params>
//     views: [{ id, name }] }            — the plugins switched on   — init is re-sent on sign-in/out

// 2. Ask. `id` correlates the answer (a short string or a number); `body` is JSON (≤ 256 KB), never
//    on GET or DELETE. The path may carry a query string ('query').
window.parent.postMessage({ type: 'agnostic:request', id: 'q1', method: 'GET', path: '/api/v1/presets' }, '*');
// ← { type: 'agnostic:response', id: 'q1', status: 200, data: {...}, etag? }   — status 0: never reached the server

// Optional, by feature: `ifMatch` (an etag) on a PUT or DELETE and `ifNoneMatch: '*'` on a PUT
// ('revisions' — the answer then carries `etag`); `idempotencyKey` on a POST ('idempotency').

// 3. Navigate ('navigate', 0.1.10): open 'overview', 'settings' or a plugin that is switched on, with
//    params for it — or this view itself, to put its own state in the URL.
window.parent.postMessage({ type: 'agnostic:navigate', to: 'crews', params: 'crew=6ba7b810-…' }, '*');
// ← { type: 'agnostic:params', params }   — when THIS view's params change while it is open
```

Params are at most 256 of `[A-Za-z0-9._~=&%:-]` (percent-encode a value); the shell drops any
others. A navigate the shell refuses — a view that is off — is told to the user, not the page.

You do not write this by hand: **`src/webgui/kit/host.js`** is the client every plugin carries
(`class Host` — `request`, `can`, `has`, `role`, `mayWrite`, `param`, `onParams`, `hasView`,
`navigate` — and `errOf`). It accepts messages only from `window.parent`, gives request ids a random
prefix per page load (the shell also answers only the page that asked), times out a request the shell
never answers, and falls back to `mode: 'standalone'` when no shell answers its hello.

### Keeping documents: `storage`

A plugin's documents live on the server **in the user's tenant** (`_` with authentication off), and
outlive the plugin being switched off.

| Call | Answer |
|---|---|
| `GET /api/v1/plugins/<id>/data` | `{documents: [{key, updated, bytes}], total, scope}` — never the documents |
| `GET /api/v1/plugins/<id>/data/<key>` | the document, byte for byte as it was stored, with its `ETag` · 404 |
| `PUT /api/v1/plugins/<id>/data/<key>` | **201** created / 200 replaced, `{key, updated, bytes, created, etag}` · 400 not JSON · **412** · 413 · 422 not an object or bad key · **507** full |
| `DELETE /api/v1/plugins/<id>/data/<key>` | `{key, status: "deleted"}` · 404 · **412** |

A key is `[a-z0-9][a-z0-9._-]*`, at most 64 characters; a document is one JSON object of at most
**32 KiB**; a plugin keeps at most **256** documents per tenant. Reading is READ, writing is WRITE;
writes and deletes are audited.

**Revisions (0.1.9).** Every document has an ETag (`"<16 hex>"`, from its bytes). Send it back as
`ifMatch` with a PUT or DELETE and the write happens only if nobody changed the document since you read
it — otherwise **412** and nothing changes. Send `ifNoneMatch: '*'` with a PUT to create a key only if
it is new. That is how two tabs editing one document find out about each other instead of the second
save silently undoing the first; apply a background change to the latest copy and retry on a 412.

## Swarm Command

Swarm Command keeps **swarms**: a mission, its tasks (generated by a template, or your own), and
every capability with a default — roles and their caps, models and prices, tools, regions with their
caps and per-second prices, the budget, and the failure model. From a swarm's card you can:

- **Simulate** it, on screen, deterministically (same seed, same run);
- **Estimate** it — eight headless simulations on different seeds, reporting the spread of cost and
  duration and how often it overspends — to price a swarm before running anything. Beside each
  estimate is what **one agent** would do with the same tokens (since 0.1.13, Swarm Command 0.5.0,
  [ADR 0014](../adr/0014-the-estimators-one-agent-baseline-is-its-own-model.md)): the same tasks one
  at a time, on each seed limited to the tokens the swarm spent there — its cost, its time, how
  often it ran out, and the tasks it left when it did (a run that runs out stops there, so its time
  and cost cover only the work it did). It is labelled **SIM**: a simulation of time, tokens and
  cost, not of the quality of an answer, and the simulator charges no context per new agent, so a
  real swarm's extra tokens are likely higher than it shows. An estimate made before 0.5.0 has no
  baseline until you estimate again;
- **Run it live** — its tasks submitted to this server as a crew (one agent per role, or a preset's
  agents), watched as it runs, cancellable. When the crew ends Swarm Command shows **what it really
  cost**: the tokens agnostic metered for every task and the cost the LLM gateway reported — beside
  the simulator's estimate, never mixed with it. Each task's output is under **Results**, and can be
  downloaded as Markdown or JSON;
- **Watch** an earlier crew again, at its real pace.

The **Crews** section lists every crew of your tenant — run from a swarm, from a script, from
anywhere — and can watch any of them on the map, or open one in the Crews view (**DETAILS**, when that
view is switched on). A link to `#plugin/swarm?crew=<uuid>` watches that crew on the map.

A live run is recorded on its swarm **before** its crew is submitted, with the `Idempotency-Key` the
submission carries, so closing the tab, a dropped answer or a timeout never loses track of a crew that
may be costing money; a submission that was never answered is marked *unconfirmed*, never *refused*.
Signing out mid-crew pauses the watch; signing in resumes it. A crew that a server restart cut short
ends the watch as **INTERRUPTED** (since 0.1.13), each task it had not finished marked *Interrupted by
a server restart*.

Swarms are this plugin's documents (`swarm-<id>`), so they are per tenant, and every save carries the
swarm's revision: if another tab saved it first, you are asked whether to overwrite it, keep both, or
keep editing. A **viewer** can open, simulate and estimate swarms but not change them. Opened in its
own tab, Swarm Command keeps swarms in that browser instead, and cannot run live crews.

## Crews

Every crew in your tenant, newest first, a page at a time: **All**, **Active** (pending or running),
**Completed**, **Failed**, **Cancelled**, **Interrupted** — the filter is applied by the server
(`GET /api/v1/crews?status=`), so every page is full. Running crews are re-listed every few seconds.

An **interrupted** crew was running when the server stopped (since 0.1.13,
[ADR 0013](../adr/0013-a-crew-interrupted-by-a-restart-is-interrupted.md)): it shows when it was
accepted and when the restart declared it interrupted, says its work was lost, and has no results,
tokens or cost — submit it again. What else a restart keeps or loses is
[architecture 001](../architecture/001-what-survives-a-restart.md).

Open one to see its **plan** (the tasks in request order, what each waits for), its **progress** as
it happens (read by cursor — each event once, and any gap said out loud), each task's **result** with
the tokens, cost and time it used, and the crew's totals. Tokens are shown only when the engine
metered a task, and cost only when the gateway priced one — an unpriced crew says *not priced*, never
$0. A placeholder run (no LLM configured) says so above everything.

**Cancel** stops new tasks starting; tasks already running finish, and since 0.1.10 their results are
kept on the cancelled crew ([ADR 0012](../adr/0012-a-cancelled-crew-keeps-its-finished-results.md)) —
the view stays on the crew until they arrive. Cancelling needs `crews:write` and a role that may
write; a viewer sees everything else. **Watch in Swarm Command** opens the same crew on the map.

## Library

**Presets** are the crews compiled into the server (read-only): a preset's agents, with their roles,
goals, tools and backstories. **Save as a definition** stores one of those agents as an agent
definition, under its own key.

**Agent definitions** are the agents stored on this server: create one, edit it (its key is fixed
once created), or delete it — each audited by the server. A key that exists is refused rather than
overwritten; a field the engine keeps but does not use (`focus`, `allow_delegation`) is labelled so.
Changing definitions needs `definitions:write` and a role that may write.

## Audit trail

Whether the hash-linked trail **verified when the server started**, how many entries it holds, and how
many appends **failed** — the one gap verification cannot see. Below, its newest entries (the server
keeps the newest 1024 for reading — [ADR 0011](../adr/0011-audit-entries-are-read-from-a-bounded-copy.md)),
filterable by severity and text, with each entry's hash and whether it names the entry before it. The
routes are ADMIN: the trail records every user's actions, so other roles are told it is for
administrators.
