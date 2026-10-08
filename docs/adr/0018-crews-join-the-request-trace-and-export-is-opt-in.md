# 0018 — A crew joins its request's trace, and OTLP span export is switched on by the OpenTelemetry environment

**Status**: Accepted
**Date**: 2026-10-04

## Context

Since M1 every request agnostic serves has a W3C trace id. `agnostic_trace_begin_a`
(`src/trace.cyr`) honours an inbound `traceparent` header, mints one when there is none, and keeps
it thread-locally so every log line of the request carries it. Nothing past the log lines used it:

- **agnosai's spans never left agnostic's process.** agnosai exports OTLP spans only once its
  exporter is started, and the only starter, `agnosai_telemetry_init_tracing`, also sets sakshi's
  level and replaces its emit hook. agnostic installs its own JSON hook, so it could not call it.
- **No span shared a trace with the request.** Until agnosai 2.1.5 each of its spans was a
  one-span trace. agnosai's ADR 023 (2.1.5) fixed that: the four OTel GenAI operations —
  `invoke_workflow` per crew, `invoke_agent` per task, `chat` per inference attempt, `execute_tool`
  per tool call — now nest under one trace, which joins a caller's `traceparent` given through
  `agnosai_crew_with_trace_parent`. It also added `agnosai_telemetry_init_export`, which starts the
  exporter and touches nothing else.
- **agnostic's check on an inbound traceparent was its length.** Any 55 bytes were accepted and
  carried into logs. agnosai parses strictly (W3C Trace Context Level 1, version `00`) and starts a
  *new* trace for a value it refuses. A value only agnostic accepted would leave a request's log
  lines in one trace and its crew's spans in another.

This is the consumer half of agnosai's ADR 023 (F6 on agnosai's roadmap): one trace from request
to tool.

## Decision

**Every crew joins the trace of the request that submitted it; agnostic honours exactly the
traceparents the engine does; and span export starts when `OTEL_EXPORTER_OTLP_ENDPOINT` is set.**

- **Join.** `agnostic_crew_submit_owned` calls
  `agnosai_crew_with_trace_parent(spec, agnostic_trace_current())` right after the spec is built.
  agnosai stores a copy, because the request's arena is reset before an asynchronous crew runs, and
  serialises none of it. A crew submitted on a thread with no request (a suite) is its own root
  trace.
- **One rule for both.** `agnostic_trace_valid_a` asks agnosai's parser,
  `agnosai_otlp_span_context_parse_a`, rather than restating its rule, so "agnostic accepted it" and
  "the crew joined it" are the same fact. A refused value is replaced by a minted one, as before.
  Minted ids are forced non-zero, the one case the generator could produce that the parser refuses.
- **Export, configured as OpenTelemetry is** (needs agnosai 2.1.6, which this release pins).
  - `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`, a complete URL, is posted to as-is. Otherwise
    `OTEL_EXPORTER_OTLP_ENDPOINT` is a **base URL**, and agnosai appends `v1/traces` to its path, as
    the OTel exporter specification has it (`https://gw/otlp` → `/otlp/v1/traces`). A base that
    already ends in `/v1/traces` is used as given, agnosai's leniency for the commonest mistake.
    Both unset or empty: export is off, and no span is built.
  - The one set must be `http://` or `https://` (any case), with no userinfo, query, fragment,
    space or control byte, at most 2048 bytes, and it must parse with sandhi's own URL parser
    (`sandhi_url_parse_a`), which the exporter posts through: no host, or a port that is not a
    number, fails there. Otherwise agnostic **refuses to start**, like a malformed `AGNOSTIC_*`
    value, because the exporter posts best-effort and ignores every answer, so a typo would lose
    every span in silence. A collector's token goes in `OTEL_EXPORTER_OTLP_HEADERS`, never in the
    URL.
  - `OTEL_SERVICE_NAME` names the service, `agnostic` when unset or empty. The OTel specification
    reads an empty variable as unset. agnosai's own default would file the spans under the library.
  - `OTEL_EXPORTER_OTLP_HEADERS` is read by agnosai's exporter on every batch, for hosted
    collectors that authenticate by header.
  - **The export is bounded** (agnosai 2.1.6): each batch is posted from the exporter's own arena
    under a 10 s ceiling, and flushes are serialised. 2.1.5's exporter left ~258 KiB of RSS per
    batch on the never-freed global bump and could block forever on a collector that never
    answered; this release does not turn export on over that.
- **Lifecycle.** `agnostic_serve_telemetry_start` calls `agnosai_telemetry_init_export` after the
  signal mask is installed, as the collector does: a thread created earlier would take SIGTERM
  itself. `agnostic_serve_telemetry_stop` calls `agnosai_telemetry_shutdown` once the server stops,
  flushing the last batch, which is the one most likely to explain the stop.

## Consequences

- **Positive**
  - A crew submitted by a traced client is one trace: the client's span, then the crew's workflow,
    its agents, their model calls and tools. A client that sends no `traceparent` still gets a trace
    whose id is the one on every log line of its request.
  - Export needs nothing agnostic-specific: the variables an OTel deployment already sets.
  - The off path costs nothing: agnosai builds no span, draws no random bytes and reads no clock
    while the exporter is off (its ADR 023).
- **Negative**
  - **agnostic exports no span of its own.** When agnostic minted the traceparent, the crew's
    workflow span names a parent span that is never exported, so a backend shows the trace's root
    as missing. The trace id still joins the spans to the request's logs. Exporting an HTTP server
    span per request is recorded on the roadmap. *Since 0.1.16 ([ADR 0020](0020-each-request-records-an-http-server-span.md)) each
    request records one, and a crew sits under it; with an inbound header the crew's parent is
    agnostic's span, a child of the caller's.*
  - **The inbound context is trusted as it is**, which is agnosai's recorded trust boundary
    (its ADR 023 and threat-model surface 7). An authenticated caller can choose the trace id a crew's
    spans join, and a `-00` flag (not sampled) switches off span export for its own crews. Only spans
    are lost: logs, the audit trail and results are not. An operator switch to restart an untrusted
    context is an agnosai follow-up.
  - agnosai logs the endpoint it exports to at INFO. Userinfo in the URL is refused at start-up
    for that reason (and because sandhi cannot send it); credentials go in
    `OTEL_EXPORTER_OTLP_HEADERS`.
  - **Export still costs a little memory for good:** ~480 B per batch stays on the global bump,
    inside sandhi's own dispatch path (16 B of it the stdlib's `sockaddr_in`). At one batch a
    second under continuous load that is ~41 MB a day. Filed upstream (agnosai's roadmap, C).
  - The `traceparent` check is stricter than 0.1.13's. A header 0.1.13 carried (uppercase hex, a
    non-`00` version, a zero id) is now replaced by a minted one. No conforming sender produces
    them.
- **Neutral**
  - `OTEL_SDK_DISABLED` and the sampler variables are not read. Unsetting the endpoint is how
    export is turned off.

## Alternatives considered

- **Call `agnosai_telemetry_init_tracing`.** Rejected: it replaces agnostic's log hook and level,
  and switches stderr to text whenever OTLP is on.
- **Restate the W3C rule in `src/trace.cyr`.** Rejected: two copies of one rule drift, and the drift
  is exactly the split-trace failure this decision removes.
- **Ignore a malformed endpoint, or log it and serve.** Rejected: the exporter never reports a failed
  post, so a misconfigured deployment would look healthy and export nothing, indefinitely.
- **Turn export on over agnosai 2.1.5's exporter.** Rejected at review: its per-batch leak and
  missing timeouts were found before this release, and fixed at the source (agnosai 2.1.6) rather
  than shipped behind a warning.
- **Pass no parent when agnostic minted the id**, so the crew starts a clean root trace. Rejected:
  the crew's spans would then carry a trace id no log line has, and the request and its crew could
  only be joined by time.
