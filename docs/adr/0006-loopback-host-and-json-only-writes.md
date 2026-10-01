# 0006 — With authentication off the server answers only a loopback Host, and every POST and PUT must declare JSON

**Status**: Accepted
**Date**: 2026-10-01

## Context

`AGNOSTIC_AUTH=off` is allowed only on a loopback bind, and there every route is open "to this
machine". Since 0.1.7 the server also serves a browser UI — and a web page the same user opens in
the same browser is on this machine too:

- **Cross-site request forgery.** Any site can make the browser send a *simple* request — a form
  post, or `fetch` with `mode: 'no-cors'` and a `text/plain` body — to `http://127.0.0.1:8000`.
  No preflight is involved, the server's JSON parser does not care what the body was labelled, and
  `POST /api/v1/crews` would start a crew that calls a paid model; `PUT /api/v1/plugins/{id}` would
  switch a plugin.
- **DNS rebinding.** A hostile domain that resolves to `127.0.0.1` becomes *same-origin* with the
  API, so its page can read the responses too, not only fire requests.

With authentication required, a bearer token stops both: a browser never attaches one by itself.

## Decision

**Two transport rules, applied only to requests that arrived on a socket** (the in-process ladder
the suites call directly is unaffected):

1. **With authentication off, the `Host` header must name a loopback host** — `localhost`, an
   address in `127.0.0.0/8`, or `[::1]`, with an optional port — or the answer is **403**, before
   routing. A request without `Host` (HTTP/1.0) passes. Rebinding cannot forge this: the browser
   sends the attacker's hostname. (`src/http/guard.cyr`, the router's Host rung.)
2. **Every POST and PUT must carry `Content-Type: application/json`** — or `application/<x>+json`;
   case-insensitive; parameters such as `charset` ignored — or the answer is **415**, even when there
   is no body (`POST /api/v1/crews/{id}/cancel`). A page can send that header cross-site only after a
   CORS preflight, which this server never grants. The rung runs after authentication, so an
   unauthenticated caller still learns nothing beyond 401.

## Consequences

- **Positive** — Closes request forgery and DNS rebinding against a developer's auth-off server for
  the cost of two header compares. Applies to every route, current and future, with no per-route
  work.
- **Negative** — **Breaking for scripts**: a `curl` or client that posts without
  `-H 'Content-Type: application/json'` now gets 415. A reverse proxy that forwards a public `Host`
  to an auth-off server gets 403 — which is right: anything reachable through a proxy needs
  `AGNOSTIC_AUTH=required`.
- **Neutral** — Bodiless POSTs must send the header too; the shell's `api()` and the plugin bridge
  always do.

## Alternatives considered

- **CSRF tokens.** Rejected: they need a session to bind to, and the API is bearer-token by design.
- **Checking `Origin` or `Referer`.** Rejected as the defence: both are absent on some requests, and
  sandboxed frames and privacy settings send `null` or nothing, so a rule would have to choose
  between refusing legitimate callers and admitting forged ones. The media type is decided by the
  request itself.
- **Requiring authentication everywhere.** Rejected: an auth-off loopback server is a supported
  developer setup, and these two rules make it safe without taking it away.
- **Allowing `text/plain` for compatibility.** Rejected: `text/plain` is precisely the content type a
  cross-site form or `no-cors` fetch can send without a preflight.
