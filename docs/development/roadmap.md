# Roadmap

Pending development work for the Agentic QA Team System, ordered by priority. Completed work is tracked in the [Changelog](../project/changelog.md).

See [Dependency Watch](dependency-watch.md) for upstream blockers that affect timeline.

---

## AGNOS — Dockerfile Migration (Q3 2026, blocked)

Blocked on AGNOS base image availability.

| Item | Effort | Priority | Description |
|------|--------|----------|-------------|
| Migrate per-agent Dockerfiles | 3 days | P2 | Replace 6 per-agent Dockerfiles + `docker/Dockerfile.base` with AGNOS base image |
| Remove redundant middleware | 2 days | P3 | Post-migration: remove `RateLimitMiddleware`, `CorrelationIdMiddleware`, docker-compose resource limits (AGNOS handles these) |

---

## Long-term / Blocked

| Item | Blocker |
|------|---------|
| Python 3.14 support | crewai `requires-python <3.14`, chromadb pydantic v1 — see [Dependency Watch](dependency-watch.md) |

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Test execution time reduction | > 50% via optimisation |
| Defect detection rate | > 95% automated |
| System uptime | > 99.9% |
| Test coverage (agents) | > 90% automated |
| Defect escape rate | < 1% to production |
| Compliance score | > 95% (GDPR, PCI DSS, SOC 2, ISO 27001, HIPAA) |
| Mean time to resolution | < 30 min for QA issues |
| Cross-project trace coverage | > 80% of requests traced end-to-end |
| AGNOS audit chain coverage | 100% of QA actions forwarded |

---

*Last Updated: 2026-03-07 · Test count: 726 (unit) + 25 (e2e) · Backlog: 0 items · [Changelog](../project/changelog.md) · [Dependency Watch](dependency-watch.md)*
