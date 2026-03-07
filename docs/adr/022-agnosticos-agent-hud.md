# ADR-022: AGNOS OS Phase 2 - Agent HUD Registration

**Status**: Proposed
**Date**: 2026-03-02
**Authors**: Agnostic team

---

## Context

Following [ADR-021](./021-agnosticos-integration.md) (Phase 1: LLM Gateway routing), this ADR covers Phase 2: registering Agnostic QA agents as native agnosticos agents in the AGNOS Agent HUD.

AGNOS OS provides an Agent Runtime (`akd`) that manages agent lifecycle and exposes an Agent HUD for viewing and controlling registered agents. By registering Agnostic's CrewAI agents with agnosticos, we enable:

- Agents appear in the AGNOS Agent HUD alongside other OS agents
- agnosticos orchestrator can manage agent lifecycle and resource limits
- Unified audit trail across all agents OS-wide
- Agent status visible in agnosticos security UI

---

## Decision

Agnostic will register its 6 QA agents with agnosticos using the `agnos-sys` SDK (or REST API as fallback). Registration is **opt-in** and controlled by environment flags.

### Implementation Approach

1. **Agent Registration via REST API**: Agnostic agents call the agnosticos Agent Registry API to register on startup
2. **Heartbeat Updates**: Agents send periodic heartbeats to update status in the HUD
3. **Graceful Deregistration**: Agents deregister on shutdown

### Registration Data

Each Agnostic agent registers with:

```json
{
  "agent_id": "agnostic-qa-manager",
  "agent_name": "QA Manager",
  "agent_type": "qa",
  "description": "Coordinates multi-agent QA workflows",
  "capabilities": ["test_planning", "task_coordination", "fuzzy_verification"],
  "version": "2026.3.6",
  "endpoint": "internal://agent-manager",
  "resource_limits": {
    "cpu": "2",
    "memory": "2Gi"
  }
}
```

### Environment Configuration

```env
AGNOS_AGENT_REGISTRATION_ENABLED=true
AGNOS_AGENT_REGISTRY_URL=http://localhost:8090
AGNOS_AGENT_API_KEY=agnos-local
```

---

## Files Modified

- `config/agent_registry.py` — Add agnosticos registration hooks
- `webgui/api.py` — Add endpoints for agent registration status
- `.env.example` — Add `AGNOS_AGENT_REGISTRATION_*` variables

---

## Consequences

### Positive
- QA agents visible in AGNOS Agent HUD
- Unified agent management across OS
- Resource limits enforced by agnosticos orchestrator

### Negative
- Dependency on agnosticos Agent Registry being available
- Additional network calls on agent startup/shutdown

### Neutral
- Disabled by default — existing deployments unaffected

---

## Implementation Checklist

- [ ] Add `agnos_agent_registration` module in `config/`
- [ ] Implement `AgentRegistryClient` for agnosticos REST API calls
- [ ] Add registration hooks to agent startup/shutdown
- [ ] Add `GET /api/agents/registration-status` endpoint
- [ ] Update `.env.example` with new variables
- [ ] Write unit tests
