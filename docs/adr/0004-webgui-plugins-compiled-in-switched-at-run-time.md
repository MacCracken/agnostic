# 0004 — WebGUI plugins are compiled in and switched at run time

**Status**: Accepted
**Date**: 2026-10-01

## Context

Swarm Command — an RTS-style view of an agent swarm, prototyped as one self-contained
`index.html` with its own simulator — had to become part of Agnostic as a *plugin*: a view that
ships with the product and that an operator turns on from a Settings tab, without touching code.

Nothing in the port could host it yet. The WebGUI is M9, and the roadmap describes it only as "a
static HTML/CSS/JS bundle served through sandhi", with a static-file handler and mime map still to
write. So this decision sets the shape M9 grows from, under constraints already in force:

- **Cyrius has no `include_str!`.** A page reaches the binary only by being turned into source, the
  way `scripts/gen-presets.sh` embeds the preset library.
- **No filesystem call in `src/` takes request input** (audit point 6, answered for M4 and due to
  re-open at M8). A handler that maps a URL to a file on disk would re-open it now.
- **Authentication is a bearer token.** A browser cannot attach one to a navigation, so a page
  behind the auth rung could never be opened.
- **A page runs code in the user's browser next to their session**, so a plugin is a cross-site
  scripting surface for whatever the shell can do — sign in, switch settings, run crews.
- **A simulation reads like real work.** Placeholder LLM mode is disclosed (`engine_mode`) for this
  reason; a view driven by a simulator needs the same treatment.

## Decision

**A plugin is compiled into the binary and switched on or off at run time by a deployment-wide
setting. It starts off.**

- A plugin is `src/webgui/plugins/<id>/` — a `plugin.json` manifest (`id`, `name`, `description`,
  `version`, `data`, `entry`) and one self-contained page. `scripts/gen-webgui.sh` embeds every
  page verbatim into `src/webgui_data.cyr` with its byte count and SHA-256, and refuses a page its
  CSP would break (external resources, inline handlers, `javascript:` URLs). `check-clean.sh` runs
  its `--check`; `tests/webgui.tcyr` re-hashes the embedded bytes against the source.
- The switch is `plugin.<id>.enabled` in a settings table on the shared patra handle
  (`src/engine/settings.cyr`). `PUT /api/v1/plugins/{id}` with `{"enabled": bool}` changes it —
  **ADMIN**, because it changes what every user of the deployment is shown — and each real change
  is recorded in the audit trail. Listing is READ.
- The pages — the shell at `/ui` and each plugin at `/ui/plugins/{id}` — are **public**, like
  `/health`: they are the same compiled-in bytes for every caller and hold no data. Everything a
  page shows comes from API calls that carry the caller's credential. A switched-off plugin's page
  is a 404.
- Each page is served with a Content-Security-Policy the generator computes: `default-src 'none'`,
  its own inline scripts admitted **by hash**, `connect-src 'self'`; the shell may frame plugins and
  nothing may frame the shell; a plugin may be framed only by its own origin.
- The shell hosts a plugin in an `<iframe sandbox="allow-scripts allow-downloads">` — **no
  `allow-same-origin`** — so a plugin runs in an opaque origin: it cannot read the shell's session
  token, call the API as the user, or touch the shell's DOM.
- A manifest says whether the view's data is `simulated` or `live`; the API carries it and the shell
  badges a simulated view on its tab and its frame.

## Consequences

- **Positive** — one binary carries everything; nothing to deploy beside it, and no drift between a
  binary and an assets directory. No request input ever becomes a filesystem path, so serving pages
  adds no traversal surface: a plugin id is `[a-z0-9][a-z0-9-]*`, looked up in a compiled-in table.
  The bytes served are proven to be the bytes reviewed. A plugin's mistakes stay inside its frame:
  even a script-injection bug in a plugin cannot act as the signed-in user. Switching is durable,
  audited, and works the same with authentication off (loopback) or required.
- **Negative** — adding or changing a plugin is a build and a release, not a drop-in. Each page adds
  its size to the binary (Swarm Command is ~251 KB of the ~290 KB the WebGUI adds). A plugin is one
  page: no separate script or image files, everything inline. Styles use `'unsafe-inline'`, because
  the prototype styles elements from script and from markup; scripts do not. The sandbox means a
  plugin that wants LIVE data cannot just call the API — it has to be handed the data.
- **Neutral** — Swarm Command still runs on its built-in simulator; that is what `data: simulated`
  says. Driving it from real crews needs a live event source: the shell (which holds the token) would
  read the crew event stream and pass events into the frame by `postMessage`, translated into the
  view's event schema. That bridge is future work, as is any per-user or per-tenant preference, which
  could be layered over the deployment switch later.

## Alternatives considered

- **Pages loaded from disk at run time** (a `webgui/` or `plugins/` directory beside the binary).
  Rejected: it puts request input on a filesystem path — the exact surface audit point 6 keeps
  closed — lets the binary and its pages drift apart between deploys, and gives up build-time proof
  of the bytes and of each page's CSP. A drop-in plugin is not a requirement anyone has stated.
- **Native code plugins** (`dlopen` through `dynlib` / `fdlopen`). Rejected: arbitrary native code
  in the server process, an ABI between independently built binaries, and no sandbox at all — for
  what is, today, a browser view.
- **An environment variable** (`AGNOSTIC_PLUGINS=swarm`). Rejected as the mechanism: it needs a
  restart, it is not the Settings tab that was asked for, and it is invisible to the audit trail. An
  operator override could still be added on top later.
- **Serving a plugin same-origin, without the sandbox.** Rejected: the plugin would share the shell's
  origin and could read the session token from storage and call the API as the user, making every
  plugin's code as trusted as the shell's.
- **Plugin pages behind the auth rung.** Rejected: a browser navigation cannot carry a bearer token,
  so the page could never load; and it would protect nothing, since the page holds no data.
