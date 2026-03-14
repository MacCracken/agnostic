# Roadmap

Pending development work for the Agnostic Agent Platform, ordered by priority. Completed work is tracked in the [Changelog](../project/changelog.md).

See [Dependency Watch](dependency-watch.md) for upstream blockers that affect timeline.

---

## General-Purpose Agent Platform Expansion

Expand Agnostic from QA-only to a platform that can create and run **any kind of agent crew** via SY request, API, or preset definitions. QA remains a first-class preset.

### Phase 0: Documentation & Branding Update

| Item | Status | Notes |
|------|--------|-------|
| Update README.md | Done | Rebrand from "Agentic QA Team System" to "Agnostic Agentics" general-purpose platform |
| Update docs/README.md | Done | Documentation index reflects multi-domain agent platform |
| Update docs/agents/index.md | Done | Agent docs cover BaseAgent framework + QA preset + custom agents |
| Update docker/README.md | Pending | Docker docs reflect general agent platform |
| ADR for platform expansion | Pending | ADR-029: Expansion from QA-only to general-purpose agent platform |

### Phase 1: Foundation (complete)

| Item | Status | Notes |
|------|--------|-------|
| `BaseAgent` class | Done | `agents/base.py` — generic agent with Redis/Celery/LLM/CrewAI init |
| `AgentDefinition` schema | Done | Runtime-loadable definition (JSON/YAML/API dict) |
| `AgentFactory` | Done | `agents/factory.py` — create agents from files, dicts, or presets |
| Tool registry | Done | `agents/tool_registry.py` — global name→class lookup for BaseTool subclasses |
| QA preset (`qa-standard`) | Done | `agents/definitions/presets/qa-standard.json` — original 6-agent QA crew |
| Example presets | Done | `data-engineering`, `devops` presets as templates |
| Unit tests | Done | `tests/unit/test_base_agent.py` |

### Phase 2: Generic Workflow Engine & API (complete)

| Item | Status | Notes |
|------|--------|-------|
| Agent CRUD API endpoints | Done | `webgui/routes/definitions.py` — POST/GET/PUT/DELETE `/api/v1/definitions` |
| Crew builder endpoint | Done | `webgui/routes/crews.py` — POST `/api/v1/crews` + GET `/api/v1/crews/{id}` |
| Generic workflow orchestrator | Done | `_run_crew_async()` — builds agents from preset/keys/inline defs, runs sequentially |
| SY agent creation via A2A | Done | `a2a:create_agent` message type creates definitions on disk |
| Preset management API | Done | GET/POST/DELETE `/api/v1/presets` — list, create, delete crew presets |
| A2A crew delegation | Done | `a2a:delegate` with `preset`/`agent_definitions` routes to crew builder |
| Dynamic A2A capabilities | Done | `/a2a/capabilities` returns loaded presets dynamically |
| Unit tests | Done | `test_definitions_api.py` (27 tests) + `test_crews_api.py` (12 tests) |

### Phase 3: Database & Integration Updates

| Item | Status | Notes |
|------|--------|-------|
| DB model renames | Pending | TestSession→AgentSession, TestResult→TaskResult, etc. + migration |
| Dynamic MCP registration | Pending | MCP tools derived from loaded agent definitions, not hardcoded |
| Dynamic A2A capabilities | Done | Moved to Phase 2 — `/a2a/capabilities` now returns loaded presets |
| AGNOS capability registration | Pending | Register capabilities from definitions, not static dict |
| Multi-domain dashboard | Pending | Dashboard supports QA + non-QA agent metrics |

### Phase 4: Advanced Features

| Item | Status | Notes |
|------|--------|-------|
| Agent marketplace / sharing | Pending | Import/export agent definitions as `.agpkg` bundles |
| Inter-crew delegation | Pending | Agents from different domains can delegate to each other |
| Custom tool upload | Pending | Users can upload BaseTool implementations at runtime |
| Agent versioning | Pending | Version agent definitions, rollback support |

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
| Agent preset count | 3+ domain presets (QA, data-eng, devops, ...) |
| Dynamic agent creation latency | < 5s from definition to running agent |

---

*Last Updated: 2026-03-14 · Version: 2026.3.14 · Test count: 904 (unit) + 24 (e2e) · [Changelog](../project/changelog.md) · [Dependency Watch](dependency-watch.md)*
