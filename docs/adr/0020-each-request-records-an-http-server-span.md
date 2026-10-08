# 0020 — Each request records an HTTP SERVER span, and an inbound traceparent gets a child

**Status**: Accepted
**Date**: 2026-10-08

## Context

[ADR 0018](0018-crews-join-the-request-trace-and-export-is-opt-in.md) made a crew join the trace
of the request that submitted it, and switched OTLP export on through the OpenTelemetry
environment. It recorded one negative it could not fix: **agnostic exported no span of its own.**
When agnostic minted a request's traceparent, the crew's `invoke_workflow` span named a parent span
id that nothing exported, so a backend showed the trace's root as missing.

agnosai's exporter carried only the four GenAI operations, and a second exporter in agnostic
would have meant a second ring, thread and OTLP encoder per process. agnosai 2.1.7 (its ADR 024)
added an HTTP server span to the same exporter, `agnosai_http_server_span_a`, built in the
caller's allocator. agnostic re-pins to 2.1.7 for it.

One more thing follows from recording a span: with an inbound `traceparent`, 0.1.15 handed the
crew the caller's own span as its parent. A crew's spans then sat beside agnostic's request,
not under it.

## Decision

**The serve adapter records one SERVER span per request through agnosai's exporter. Its span id
is the request's trace id's: the one its crews name as parent and its log lines carry. A request
that brings a traceparent gets a child of it, and the crews nest under agnostic's span.**

- **Identity.** With no inbound header, `agnostic_trace_begin_a` mints a root traceparent, as
  before, and the span is that root. With a valid one, it now mints a **child**
  (`agnostic_trace_child_a`): the same trace id and flags, a fresh span id. The child is the
  request's current id, and the header is kept as `agnostic_trace_parent()`, the span's parent.
  The log lines and the crews read the current id, so both sit under agnostic's span.
- **What it says.** It is named `<method> <route>`, with `http.request.method`, `http.route`,
  `http.response.status_code`, `url.path` and `url.scheme` (`http`; agnostic serves no TLS).
  - The route is the matched row's pattern (`/api/v1/crews/:id`): dispatch writes it into the
    request context (`agnostic_reqctx_set_route`) once the route resolves. A request no row
    answered (404, 405, a refusal before routing) is named by its method alone and has no
    `http.route`, as the HTTP semantic conventions have it. The path never becomes the name.
  - A method agnostic does not serve is `_OTHER`, so a client cannot mint span names.
  - `url.path` drops the query, which can carry anything.
  - The status is ERROR for a 5xx, and unset otherwise: a 4xx is the client's error, and the
    conventions leave a SERVER span's status unset for it. It is the status actually sent:
    `_agnostic_serve_send` answers it, including the 500 that replaces a body that would not
    encode.
- **When.** After the response is sent, so the span covers the whole answer, and before the trace
  id is cleared. It starts when the handler is entered.
- **What it costs.** Nothing with export off but one load (`agnosai_telemetry_exporter()`). With
  it on, everything is built in the request's arena: the two span contexts are parsed there, the
  span is built there, and the ring encodes it into its own arena and keeps nothing. A recorded
  request keeps nothing more on the global heap. Measured at 12.0–12.2 µs per
  request (`server_span_record`), and 1.7 µs for a child (`trace_child`).
- **Sampling.** The child copies the caller's flags, so a `-00` caller gets no span from agnostic,
  as it gets none from its crews (ADR 0018's ParentBased rule).

## Consequences

- **Positive**
  - A trace has a root a backend can find: agnostic's SERVER span when agnostic minted the id, or
    the caller's span over agnostic's when it did not. The crew's `invoke_workflow` sits under the
    request that submitted it.
  - Every request is a span, so a backend shows request rates, latency and errors per route with
    no other instrumentation.
  - Tested in `tests/server_span.tcyr` (a new suite, through the real handler on a worker-style
    request arena): the root and child cases, the crew's parent, `_OTHER`, a 404's name, the query,
    the status mapping, an unsampled caller and the global heap. Eight mutations each fail it by
    name. `tests/trace.tcyr` covers the child and the parent slot, `tests/router.tcyr` the pattern.
- **Negative**
  - **The log lines' traceparent changes for an inbound header.** It now carries agnostic's span id,
    not the caller's. The trace id is unchanged, which is what joins logs to a trace. A caller
    matching its own span id against agnostic's logs no longer finds it.
  - The span's instrumentation scope is agnosai's: agnosai's batch names one scope for all its
    spans. A backend shows agnostic's spans under the `agnostic` service and the `agnosai` scope.
  - The span carries no `server.address`, `server.port` or `user_agent.original`: agnosai's span
    record has no slot for them. They are recommended, not required.
  - The inbound context is still trusted as it is (ADR 0018).
- **Neutral**
  - The id a request gets with no header is minted exactly as before.

## Alternatives considered

- **Record the span with the caller's span id as its own** (no child). Rejected: two spans with
  one id in one trace, the caller's and agnostic's, which a backend cannot tell apart.
- **Keep handing the crew the caller's span.** Rejected: the crew would sit beside the request
  that submitted it, and a request's latency would not contain its crew's start.
- **`agnosai_otlp_span_context_child` for the child.** Rejected: it allocates its context on the
  global heap, 32 B per request for good. `src/trace.cyr` already mints ids in the request's arena.
- **Name the span by its path when no route matched.** Rejected: a path is unbounded, and a
  scanner's 404s would mint a span name each.
