# Security Policy

## Scope

Agnostic is a multi-agent QA platform. It accepts untrusted job definitions over
HTTP, drives browsers and target systems under test, executes tools, and stores
results. Its security surface is therefore wider than a typical library:

- **Inbound API** — REST under `/api/v1`, an MCP surface, and the A2A callback
  endpoint. Anything reachable before authentication is in scope.
- **Delegated execution** — crews run through the linked
  [AgnosAI](https://github.com/maccracken/agnosai) engine, which owns tool
  sandboxing. A sandbox escape is an AgnosAI issue; a failure to *ask* for the
  right sandbox tier is an Agnostic issue.
- **Targets under test** — Agnostic drives browsers and issues requests at
  systems named in a job. Anything that lets a job reach a host it was not
  authorised for (SSRF, redirect following, DNS rebinding) is in scope.
- **Stored artefacts** — reports, baselines, session records and audit entries.
- **Credentials** — API keys, tenant tokens, and any provider credentials passed
  through configuration.

Out of scope: vulnerabilities in a system Agnostic was legitimately pointed at by
an authorised job, and issues in `python-port/`, which is a frozen behavioural
oracle that is never built or shipped.

## Reporting a Vulnerability

Report privately through
[GitHub Security Advisories](https://github.com/maccracken/agnostic/security/advisories/new).

Please do **not** open a public issue for anything exploitable.

Include what you have: the version (`cat VERSION` in the source tree, or the
`version` field of a running server's `GET /ready`), configuration relevant to
the finding, a reproduction, and the impact you believe it has. A minimal
reproduction is worth more than a long report.

You should get an acknowledgement within a few days. Fixes ship in the next
patch release; anything actively exploitable gets an out-of-band release.

## What Gets Treated as a Vulnerability

- Authentication or authorisation bypass on any `/api/v1` route, the MCP
  surface, or the A2A endpoint
- Tenant isolation failure — one tenant reading, altering, or cancelling
  another's crews, results, or configuration
- Credential disclosure through logs, error messages, reports, or API responses
- Server-side request forgery, including via job-supplied target URLs
- Injection into a stored artefact that executes when a report is later viewed
- Any path that causes a tool to run at a weaker sandbox tier than its
  definition requires
- Denial of service reachable without authentication

## What Does Not

- Missing hardening headers on a response that carries no sensitive data
- Rate-limit thresholds you consider too generous — these are configurable
- Findings that require an already-privileged operator account
- Reports from an automated scanner with no demonstrated impact

## Hardening Notes

- **Authentication is off by default in development and must be enabled for any
  networked deployment.** A default-open configuration reachable from a network
  is a deployment error, not a product default to rely on.
- Provide credentials through the environment, never in a job definition or a
  committed file.
- Terminate TLS in front of Agnostic, or configure it explicitly. Do not assume
  a plain-HTTP listener is private because it binds a private address.
- Treat every job definition as untrusted input, including ones that arrive from
  an orchestrator you control.

## Supply Chain

Dependencies are pinned by tag in `cyrius.cyml` and resolved by `cyrius deps`;
the toolchain itself is pinned via `[package].cyrius`. There are no transitive
package-manager dependencies. A dependency's own security policy governs its
code — report there, and tell us so we can move the pin.
