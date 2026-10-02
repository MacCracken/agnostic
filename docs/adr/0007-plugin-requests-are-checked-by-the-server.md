# 0007 — Plugin requests are checked by the server, against one permission vocabulary

**Status**: Accepted — amends [0005](0005-plugins-reach-the-server-through-the-host-bridge.md): the shell's gate is no longer the only wall, and the permission table has one source
**Date**: 2026-10-02

## Context

[ADR 0005](0005-plugins-reach-the-server-through-the-host-bridge.md) lets a plugin reach the API
only by asking the shell, which makes the request with the user's credential when the plugin's
manifest `permissions` allow it. At 0.1.8 that check lived in exactly one place: `permitted()` in
the shell's JavaScript. Three things were wrong with that:

- **The server could not tell a plugin's request from the user's own.** Every bridged request
  arrived as an ordinary authenticated call. A mistake in `permitted()` — a regex one character
  too loose — would have let a plugin make any call its user may, and nothing on the server would
  have noticed. The shell's code had no automated tests at all.
- **A switched-off plugin kept working.** The shell resolved a plugin once, when its view opened.
  An administrator switching it off elsewhere changed nothing for a user who already had it open:
  its requests went on being answered until that user reloaded.
- **The vocabulary was kept in four places** — `PERMISSIONS` in the generator, `permitted()` and
  `PERMISSION_WORDS` in the shell, and the tables in ADR 0005 and the guide — and agreed only by
  hand. The handoff listed "a new plugin permission is four edits" as a footgun.

## Decision

**The permission vocabulary is one file, and the server enforces it on every request the bridge
makes for a plugin.**

- **`src/webgui/permissions.json`** defines each permission: its name, the words Settings shows
  (`grants`), and the exact routes it grants (`"METHOD /path"`, `:name` for a path parameter,
  `:self` for the asking plugin's own id). `scripts/gen-webgui.sh` validates it and every
  manifest against it, and embeds it (`agnostic_webgui_permissions_json`); the server parses it
  once at mount and refuses to start if a manifest names a permission it does not hold.
- **`X-Agnostic-Plugin: <id>`** is set by the shell on every request it makes for a plugin. The
  router's **plugin rung** runs right after routing — before authentication: the plugin must be
  built in, switched on, and granted the route, or the answer is **403** with a machine-readable
  `code`: `plugin_unknown`, `plugin_off`, `plugin_forbidden`. A request without the header is not
  a plugin's and passes untouched — the header only ever narrows what a request may do.
- **`GET /api/v1/plugins` serves the vocabulary** as `catalogue`. The shell compiles its fast,
  local refusal from it (`AgnosticBridge.grantsFor`) and shows its words in Settings — so the
  shell's check and the server's are the same table, and the shell's is a convenience in front of
  the server's, never the only wall. On `plugin_off` or `plugin_unknown` the shell re-reads the
  plugin list and leaves the view.
- **The shell's gate is a pure script** (`window.AgnosticBridge`, the shell's first `<script>`),
  tested under Node with the real vocabulary (`tests/webgui/shell.test.mjs`). It also now drops a
  reply addressed to a page that has since been replaced (a reload, another plugin in the frame —
  the frame's window object does not change, so `e.source` cannot tell them apart), accepts
  messages only from an opaque origin (the frame is always sandboxed), and caps a plugin at 16
  requests in flight.

## Consequences

- **Positive** — A defect in the shell's check can no longer widen what a plugin may do: the server
  checks the same routes and refuses outside them, and its check is covered by `tests/webgui.tcyr`
  with mutations. Switching a plugin off takes effect on the next request every open copy makes.
  Adding a permission is one edit to `permissions.json` (and the docs); the generator, the server,
  the shell and Settings all follow. The rung runs before authentication, so a refused plugin
  request costs no user lookup.
- **Negative** — The server now knows about plugins on its request path: every request carrying the
  header pays a route-pattern match against the plugin's grants (a handful of matcher calls, well
  under a microsecond each). The shell's gate and the server's must both be kept to one table —
  which is now enforced by construction, not by care. A route renamed in the router but not in
  `permissions.json` stops being granted: that fails closed, which is the right direction.
- **Neutral** — Third-party plugins running outside the shell would still need their own credential
  model (ADR 0005's rejected "scoped token per plugin"); this ADR does not change that.

## Alternatives considered

- **Keep the check in the shell only, and test it.** Rejected: tests make the JavaScript more likely
  to be right; they do not make the server able to notice when it is not, nor make a switch-off
  take effect for an open view.
- **Check only on the server, drop the shell's gate.** Rejected for now: a forbidden request would
  cost a network round trip and an authentication attempt before being refused. With the catalogue
  served, keeping the local check costs nothing in consistency.
- **Encode permissions as route ids in Cyrius.** Rejected: the shell and the generator could not
  read them, and the four-copies problem would return in another shape. Route templates in JSON are
  readable by all three and match the router's own `:name` syntax.
- **Put the plugin id in the path or the body.** Rejected: it would change every route's shape. A
  header is outside the API's contract and is set by one line of the shell.
