# ADR-011: Scalable Team Architecture with Lean/Standard/Large Presets

## Status
Accepted

## Context
The Agentic QA Team System needs to support different team sizes based on project requirements - from small MVP projects to large enterprise deployments. We need a flexible configuration system that allows dynamic team sizing while maintaining backward compatibility with the current 6-agent architecture.

## Decision
We will implement a three-tier team configuration system:

1. **Lean Team (3 agents)**: For small projects/MVP - consolidated roles
   - QA Manager (orchestration)
   - QA Executor (execution, data, UX, localization, security, performance)
   - QA Analyst (reporting, traceability)

2. **Standard Team (6 agents)**: For most projects - current architecture
   - QA Manager, Senior QA, Junior QA, QA Analyst, Security & Compliance, Performance

3. **Large Team (9+ agents)**: For enterprise - full specialization
   - QA Manager, Senior Test Architect, Test Execution Engine, Quality Intelligence Analyst, Security & Privacy Guardian, Performance Guardian, UX Researcher, Localization Specialist, DevOps Integration Specialist

## Rationale
- **Cost efficiency**: Lean teams reduce LLM API costs for smaller projects
- **Scalability**: Large teams provide full specialization for complex enterprise needs
- **Backward compatibility**: Standard preset maintains current 6-agent behavior
- **Dynamic scaling**: System can adapt team size based on project complexity
- **Best practices**: Aligns with industry QA role specialization (ISTQB/IREB standards)

## Implementation
- `agents/definitions/presets/qa-lean.json` - Lean 3-agent preset
- `agents/definitions/presets/qa-standard.json` - Standard 6-agent preset
- `agents/definitions/presets/qa-large.json` - Large 9-agent preset
- `config/agent_registry.py` - Loads presets, provides agent lookup and task routing
- Environment variable `QA_TEAM_SIZE` controls team size (lean/standard/large)
- QA Manager routes tasks based on team configuration
- All new tools added to appropriate agent roles

## Consequences
- Agents must be aware of team configuration for proper routing
- Some tools may need to be available in multiple agent roles for lean teams
- Documentation must clearly map tools to roles per team size
- Docker Compose must support optional agent services

## Configuration Example

```bash
# For lean team
QA_TEAM_SIZE=lean

# For standard team (default)
QA_TEAM_SIZE=standard

# For large enterprise team
QA_TEAM_SIZE=large
```

## Team Workflow Mapping

| Workflow | Team Size | Description |
|----------|-----------|-------------|
| consolidated | lean | Agents handle multiple responsibilities |
| specialized | standard | Clear role separation |
| full | large | Maximum specialization |

---

*Created: 2026-02-13*
*Status: Accepted*
