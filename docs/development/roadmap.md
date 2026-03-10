# Roadmap

Pending development work for the Agentic QA Team System, ordered by priority. Completed work is tracked in the [Changelog](../project/changelog.md).

See [Dependency Watch](dependency-watch.md) for upstream blockers that affect timeline.

---

## Long-term / Blocked

| Item | Blocker |
|------|---------|
| Python 3.14 support | crewai 1.10.1 `requires-python <3.14` — sole remaining blocker. chromadb 1.1.1 is now unblocked (`>=3.9`). See [Dependency Watch](dependency-watch.md) |

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

*Last Updated: 2026-03-09 · Version: 2026.3.9 · Test count: 790 (unit) + 24 (e2e) · [Changelog](../project/changelog.md) · [Dependency Watch](dependency-watch.md)*
