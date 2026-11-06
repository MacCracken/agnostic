# 0029 — A crew's target is checked at the door, and the operator lists the hosts it may name

**Status**: Accepted
**Date**: 2026-11-06

## Context

The parity review's second question was settled on 2026-11-05: a target is a checked field on the crew,
which a task may override. A target is where load and security tools point, so whoever may submit a crew
would otherwise choose any host the server can reach, or someone else's site.

## Decision

**`"target": {"url": "…"}` on a crew, and on a task to override it.** An object, so that a target that
is not a URL can add a key without a break.

**`AGNOSTIC_TARGET_HOSTS` lists the hosts a deployment may test.** With no list, every target is
refused. A crew with no target is unaffected. An entry is a host, compared whole and without regard to
case: no ports, no wildcards and no subdomains. A wrong list refuses to start, because running with fewer
hosts than an operator wrote is how a deployment comes to test nothing, or something nobody meant.

**A host off the list is a 403, and it goes in the audit trail** as `crew.target_refused`, within the
budget of [ADR 0025](0025-a-refusal-always-counts-and-is-written-within-a-budget.md). The body was
well-formed and this deployment will not act on it, and someone aiming the server at a host is what an
operator wants to read about. The refusal does not echo the host.

**One spelling, and the rest refused rather than normalised.** A tool will read the URL with a parser of
its own, and an allow-list is worth what those two parsers agree on. `http://listed.example\@other.example/`
is the classic: one reads the host before the `\`, another after the `@`. So a target is a lowercase
`http` or `https` scheme, printable ASCII with no backslash, no user name or password, and a host of
letters, digits, `-`, `_` and `.`, or a bracketed IPv6 address. A trailing dot, percent-encoding and raw
non-ASCII all fail.

**User info is refused for a second reason:** the URL reaches the model and is stored with the crew.

**Forwarded into each task's context,** as [ADR 0017](0017-a-task-carries-selection-hints.md)'s hints are,
so agnosai renders it into the prompt with no change there. A crew with no target gets no key, so its
prompt and hoosh's cache key do not move. It is measured with the hints against the engine's cap.

**It is on the entry before the entry is published.** A placeholder crew ends in under a millisecond, and
the collector can store its outcome the moment the entry appears, so a target set afterwards could go
missing from the record of what was tested. That is the reason the scope is set first too.

**Kept where a report will read it:** the plan, the outcome, the listing, the in-flight row and
`agnostic_crew_index`, in TEXT columns added at mount. A target runs to 2048 bytes and a patra STR to 255.

## Consequences

- **Positive** — WRITE alone chooses no host, and every crew says what it was pointed at, past a restart.
- **Negative** — a host's name is compared, not its address. A listed name resolves to whatever DNS says
  when a tool calls it. What holds a tool's calls to the target is agnosai's gate, which waits on its
  tool loop (roadmap, M6), and that is also where private addresses get decided.
- **Negative** — the first start on an existing database rewrites `agnostic_crew_index`, because patra's
  `ADD COLUMN` does, once.
- **Negative** — `localhost` and `127.0.0.1` are two hosts, and a deployment lists whichever its targets
  spell. Parsing them as one is the kind of cleverness this ADR refuses.
- **Not done** — a target behind a login. Its credential must enter neither the body, the context nor the
  store, and its form is decided with the first tool that needs one.
