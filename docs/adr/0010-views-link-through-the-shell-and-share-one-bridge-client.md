# 0010 — Views link to each other through the shell, and every plugin carries one bridge client

**Status**: Accepted
**Date**: 2026-10-02

## Context

M9 owes views over the real surface — crews, agent definitions and presets, the audit trail — and
0.1.10 builds them as first-party plugins (Crews, Library, Audit trail) beside Swarm Command, under
ADR 0004 (compiled in, switched on per deployment, starting OFF), ADR 0005 (a plugin reaches the
server only through the shell's bridge) and ADR 0007 (the server checks every bridged request
against one permission vocabulary). Two things those decisions did not cover became real the moment
there was more than one view:

- **Views need to point at each other.** The Crews view shows a crew's plan and results; Swarm
  Command shows the same crew on its map; each wants a link to the other, and a link to a crew
  should be something a user can bookmark or paste. But a plugin runs sandboxed in an opaque origin
  — it cannot change the shell's URL, and it cannot know which other views are switched on.
- **Every plugin needs the same client for the bridge.** A plugin page is one self-contained file
  (ADR 0004), so the client side of the bridge — `class Host`: the hello/init handshake, request ids
  that cannot collide across reloads, timeouts, the features a shell carries — cannot be shared by
  reference. Swarm Command carried its own; three more views would mean four copies, and copies of
  security-relevant code drift.

## Decision

**The shell owns navigation, and plugins ask it to navigate; every plugin carries the one canonical
bridge client, byte for byte, and the generator refuses a copy that differs.**

- **A view's state is in the shell's URL**: `#plugin/<id>?<params>`. `params` is the view's own —
  `crew=<uuid>`, `status=active`, `tab=definitions&item=<key>` — kept to the characters a fragment
  needs no escaping for, `[A-Za-z0-9._~=&%:-]`, at most 256 (a value is percent-encoded). Params
  outside that are dropped, never passed on.
- **`init` carries them, and the views that will open**: `params`, and `views: [{id, name}]` — the
  plugins switched on — so a page offers a link only to a view that exists. A shell lists the
  feature as `navigate`.
- **A plugin asks**, `{type: 'agnostic:navigate', to, params}`, to open `overview`, `settings` or a
  plugin that is switched on; the shell checks it (`AgnosticBridge.checkNavigate`, pure, tested under
  Node) and sets the hash. A view that navigates to ITSELF with new params is how it puts its own
  state in the URL — and the back button walks it.
- **When the params of the open view change**, the shell does not reload it: it posts
  `{type: 'agnostic:params', params}`. A deep link followed while the view is open, and a view's own
  navigate, both arrive this way.
- **One bridge client**: `src/webgui/kit/host.js`, between `agnostic-kit:host begin` / `end`
  markers. Every plugin page carries that block verbatim; `scripts/gen-webgui.sh` refuses a page whose
  copy differs by a byte, and a page that asks the server for anything without carrying it.
  `./scripts/gen-webgui.sh --sync-kit` rewrites the copies. `tests/webgui/kit.test.mjs` tests the
  file, which tests every copy.

## Consequences

- **Positive** — Views link to each other and to a crew without any of them gaining a way out of
  the sandbox: navigation is a request the shell may refuse, like every other. A crew's page is a URL
  (`/ui#plugin/crews?crew=…`) that survives a reload and can be shared. A fix to the bridge client is
  made once and reaches every plugin through the generator, which also makes a hand-edited copy a
  build failure rather than a silent fork.
- **Negative** — Every plugin page now carries ~140 lines it did not write, and changing the client
  means regenerating every page (and their CSP hashes) — by design, but it touches files that did not
  otherwise change. Params are a small, unescaped-free alphabet; a view that wants richer state must
  percent-encode it.
- **Neutral** — The views are plugins that start OFF (ADR 0004 stands): a deployment that wants the
  Crews view switches it on in Settings, and a link to a view that is off is refused with a toast.

## Alternatives considered

- **Views built into the shell.** Rejected: ADR 0004 decided views are plugins, switched per
  deployment, and the shell stays the frame — not a fifth view.
- **Plugins navigating with `target="_top"` links.** Rejected: the sandbox has no
  `allow-top-navigation`, and granting it would let a plugin send the shell anywhere, not only to
  another view.
- **Query strings on the plugin's own URL instead of the shell's fragment.** Rejected: a reload of
  the frame would lose them, the shell could not see them, and the plugin's URL is the shell's to
  set.
- **A shared script served once and loaded by every page.** Rejected: ADR 0004's pages are
  self-contained and admit only their own inline scripts by hash; a shared `src=` script is an
  external resource the CSP refuses, and making it an exception would weaken every page's policy for
  the sake of saving bytes.
