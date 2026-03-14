# ADR-029: Expansion from QA-Only to General-Purpose Agent Platform

**Status**: Accepted
**Date**: 2026-03-14
**Authors**: Agnostic team

## Context

Agnostic was originally built as a 6-agent QA platform (QA Manager, Senior QA, Junior QA, QA Analyst, Security & Compliance, Performance & Resilience). All agent definitions, task routing, MCP tools, A2A capabilities, AGNOS registration, and database models were hardcoded to the QA domain.

SecureYeoman and other AGNOS ecosystem consumers requested the ability to create and orchestrate agents for any domain — data engineering, DevOps, SRE, custom workflows — without forking the platform or maintaining parallel agent infrastructure.

## Decision

Expand Agnostic into **AAS (Agnostic Agentics Systems)** — a general-purpose agent platform where:

1. **Agents are defined declaratively** via JSON/YAML definitions, not hardcoded Python classes
2. **Crews are assembled dynamically** from presets, agent keys, or inline definitions via API
3. **QA remains a first-class preset** — all existing QA functionality is preserved as the `qa-standard` preset
4. **The platform is domain-agnostic** — new domains (data-engineering, devops, custom) can be added without code changes

### Architecture

```
AgentDefinition (JSON/YAML)
    ↓
AgentFactory.from_preset() / from_dict() / from_file()
    ↓
BaseAgent (Redis + Celery + LLM + CrewAI)
    ↓
handle_task() → Crew execution → Redis state → Manager notification
```

### Implementation Phases

- **Phase 1**: BaseAgent + AgentFactory + AgentDefinition schema + tool registry
- **Phase 2**: CRUD API for definitions/presets + crew builder endpoint + A2A crew delegation
- **Phase 3**: DB model aliases (AgentSession/TaskResult) + dynamic MCP/AGNOS/dashboard
- **Phase 4**: .agpkg packaging + versioning + inter-crew delegation + custom tool upload

### Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| JSON definitions over YAML-only | No PyYAML dependency required; YAML supported optionally |
| Aliases over DB renames | `AgentSession = TestSession` avoids migrations; table names unchanged |
| Tool registry with `@register_tool` | Decouples tool definitions from agent classes |
| Sandboxed `load_tool_from_source()` | Custom tools compiled with restricted builtins for safety |
| `BaseAgent.delegate_to()` | Cross-domain delegation without shared crew membership |
| `.agpkg` as ZIP with manifest | Standard format, self-describing, portable |
| Built-in preset protection | `qa-standard` cannot be deleted via API |

## Consequences

### Positive

- Any AGNOS/SY consumer can create domain-specific agents without forking
- QA functionality fully preserved — 922 unit tests still pass
- Agent definitions are portable (.agpkg bundles)
- A2A protocol extended for crew delegation and dynamic agent creation
- MCP tool count grew from 27 to 32 (Agnostic) + 5 new tools in both Agnosticos and SecureYeoman

### Negative

- Larger API surface to maintain (17 new endpoints)
- Custom tool upload (`load_tool_from_source`) introduces code execution risk (mitigated by sandboxed exec + admin-only access)
- Dynamic agents may have unpredictable resource usage (mitigated by existing circuit breaker + token budget)

### Neutral

- Container/artifact names stay `agnostic` (no rename needed)
- Existing QA agents in `agents/{type}/` are unchanged — they can optionally subclass BaseAgent but don't have to
- Database schema is additive only (new nullable columns, no migrations for existing deployments)

## Files Added

| File | Purpose |
|------|---------|
| `agents/base.py` | BaseAgent + AgentDefinition |
| `agents/factory.py` | AgentFactory |
| `agents/tool_registry.py` | Global tool registry |
| `agents/packaging.py` | .agpkg export/import |
| `agents/versioning.py` | Definition versioning + rollback |
| `agents/definitions/presets/*.json` | qa-standard, data-engineering, devops presets |
| `webgui/routes/definitions.py` | Definition + preset CRUD + versioning + packaging + tool upload API |
| `webgui/routes/crews.py` | Crew builder + execution |
| `tests/unit/test_base_agent.py` | 32 tests |
| `tests/unit/test_definitions_api.py` | 27 tests |
| `tests/unit/test_crews_api.py` | 12 tests |
| `tests/unit/test_phase4.py` | 18 tests |
