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

### Phase 3: Database & Integration Updates (complete)

| Item | Status | Notes |
|------|--------|-------|
| DB model aliases | Done | `AgentSession`, `TaskResult`, `TaskMetrics`, `TaskReport` aliases + `domain`/`crew_preset` columns |
| Dynamic MCP tools | Done | 5 new crew MCP tools (`agnostic_run_crew`, `agnostic_crew_status`, `agnostic_list_presets`, `agnostic_list_definitions`, `agnostic_create_agent`) + dispatch |
| Dynamic A2A capabilities | Done | Phase 2 — `/a2a/capabilities` returns loaded presets |
| AGNOS dynamic registration | Done | `get_all_agents()` / `get_all_capabilities()` merge static QA agents with preset-loaded agents |
| Multi-domain dashboard | Done | `_get_session_timeline()` discovers dynamic agent prefixes via Redis SCAN |

### Phase 4: Advanced Features (complete)

| Item | Status | Notes |
|------|--------|-------|
| Agent packaging (.agpkg) | Done | `agents/packaging.py` — export/import ZIP bundles with manifest, definitions, presets |
| Inter-crew delegation | Done | `BaseAgent.delegate_to()` — agents can delegate to any other agent across domains |
| Custom tool upload | Done | `load_tool_from_source()` in tool_registry + POST `/api/v1/tools/upload` endpoint |
| Agent versioning | Done | `agents/versioning.py` — save/list/get/rollback versions + API endpoints on `/definitions/{key}/versions` |
| Package export/import API | Done | POST `/api/v1/packages/export` (returns .agpkg ZIP) |
| Tool listing API | Done | GET `/api/v1/tools` — list all registered tools |
| Unit tests | Done | `tests/unit/test_phase4.py` (18 tests) |

---

## Downstream Integration (post-generalization)

After all generalization phases are complete, the following work is needed in **Agnosticos** and **SecureYeoman** to consume the new AAS capabilities.

### Agnosticos (AGNOS OS)

| Item | Effort | Status | Notes |
|------|--------|--------|-------|
| Daimon agent registry: `domain` field | Small | Done | `RegisterAgentRequest` + `AgentDetail` now accept `domain`; registry indexes by domain with `find_by_domain()` / `list_domains()` |
| AgnosticBridge crew tools | Small | Done | 5 new bridge handlers: `handle_agnostic_run_crew`, `_crew_status`, `_list_presets`, `_list_definitions`, `_create_agent` |
| MCP manifest: 5 new tools | Small | Done | `agnostic_run_crew`, `agnostic_crew_status`, `agnostic_list_presets`, `agnostic_list_definitions`, `agnostic_create_agent` (100 total) |
| Dispatch wiring | Small | Done | All 5 new tools wired in `dispatch_tool_call()` |
| Hoosh `X-Agent-Domain` header | Small | Done | LLM gateway extracts/echoes `X-Agent-Domain` + logs it; echoed on response |
| Agent HUD multi-domain UI | Medium | Pending | Group agents by domain in the HUD. Add domain filter/tabs |
| RPC method registration for crew agents | Medium | Pending | Dynamic agents from presets need RPC methods registered on-the-fly |

### SecureYeoman

| Item | Effort | Status | Notes |
|------|--------|--------|-------|
| MCP bridge: 5 new crew tools | Medium | Done | `agnostic_run_crew`, `agnostic_crew_status`, `agnostic_list_presets`, `agnostic_list_definitions`, `agnostic_create_agent` in `agnostic-tools.ts` |
| A2A delegate: crew support | Small | Done | `agnostic_delegate_a2a` now accepts `preset` and `agent_definitions` fields |
| A2A `create_agent` tool | Small | Done | New `agnostic_create_agent` MCP tool sends `a2a:create_agent` message |
| Dashboard widget: multi-domain | Small | Done | `AgnosticMetricsWidget.tsx` shows preset domain tags, task domain labels |
| Branding update | Small | Done | "AGNOSTIC QA" → "Agnostic" in widget, file header updated to AAS |
| Preset selector UI | Medium | Pending | Connections > Agnostic panel should show presets and allow crew selection |
| MCP auto-discovery integration test | Small | Pending | Verify the 5 new tools auto-appear in SY's MCP discovery |

### Shared / Cross-project

| Item | Effort | Notes |
|------|--------|-------|
| E2E test: SY → Agnostic crew delegation | Medium | End-to-end test that SY can delegate a non-QA crew task to Agnostic and poll status |
| E2E test: dynamic agent creation via A2A | Small | SY creates an agent definition on Agnostic via A2A, then runs a crew with it |
| Documentation: cross-project API contract | Small | Document the new API surface (crew endpoints, preset endpoints, A2A message types) as a shared contract |

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

*Last Updated: 2026-03-14 · Version: 2026.3.14 · Test count: 922 (unit) + 24 (e2e) · [Changelog](../project/changelog.md) · [Dependency Watch](dependency-watch.md)*
