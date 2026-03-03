# Roadmap

Pending development work for the Agentic QA Team System, ordered by priority. Completed work is tracked in the [Changelog](../project/changelog.md).

See [Dependency Watch](dependency-watch.md) for upstream blockers that affect timeline.

---

## Near-term

*(No items — all high-priority features implemented)*

---

## Medium-term

*(No items — all medium-term features implemented)*

---

## Long-term / Blocked

### Python 3.14 Support
**Priority:** Low (blocked upstream)

The local dev environment uses Python 3.14, which cannot install crewai 1.x because `chromadb` uses `pydantic.v1.BaseSettings` (removed in Python 3.14). Production Docker containers run Python 3.11 and are unaffected.

Unblocked when chromadb migrates to `pydantic-settings`. See [Dependency Watch](dependency-watch.md).

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

---

*Last Updated: 2026-03-02 · [Changelog](../project/changelog.md) · [Dependency Watch](dependency-watch.md)*
