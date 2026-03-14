# Agent Documentation

AAS (Agnostic Agentics Systems) is a general-purpose agent platform. Agents are defined via JSON/YAML definitions, assembled into crews via `AgentFactory`, and executed on shared infrastructure (Redis, Celery, CrewAI, LLM).

## Agent Framework

### Core Components

| Component | File | Purpose |
|-----------|------|---------|
| **BaseAgent** | `agents/base.py` | Generic agent base class — handles Redis, Celery, LLM, and CrewAI Agent construction |
| **AgentDefinition** | `agents/base.py` | Runtime-loadable agent schema (from JSON, YAML, or API dict) |
| **AgentFactory** | `agents/factory.py` | Create agents from files, dicts, presets, or definitions |
| **Tool Registry** | `agents/tool_registry.py` | Global name-to-class lookup for BaseTool subclasses |
| **Presets** | `agents/definitions/presets/` | Pre-built crew configurations (QA, data-eng, devops) |

### Creating a Custom Agent

1. **Define the agent** in JSON or YAML:

```json
{
  "agent_key": "my-analyst",
  "name": "My Domain Analyst",
  "role": "Domain Analysis Expert",
  "goal": "Analyse domain-specific data and produce actionable insights",
  "backstory": "You are an expert analyst with 10+ years in this domain...",
  "domain": "my-domain",
  "focus": "Data analysis, pattern detection, reporting",
  "tools": ["MyCustomTool"],
  "complexity": "medium"
}
```

2. **Register custom tools** (optional):

```python
from agents.tool_registry import register_tool
from shared.crewai_compat import BaseTool

@register_tool
class MyCustomTool(BaseTool):
    name: str = "my_custom_tool"
    description: str = "Does something domain-specific"

    def _run(self, input_data: dict) -> dict:
        return {"result": "analysis complete"}
```

3. **Create and run the agent**:

```python
from agents.factory import AgentFactory

# From a file
agent = AgentFactory.from_file("agents/definitions/my-analyst.json")

# Run a task
result = await agent.handle_task({
    "scenario": {"id": "task-1", "name": "Analyse Q1 data"},
    "session_id": "sess-123",
})
```

### Creating a Crew Preset

Group related agents into a preset JSON file at `agents/definitions/presets/`:

```json
{
  "name": "my-crew",
  "description": "Three-agent crew for my domain",
  "domain": "my-domain",
  "version": "1.0.0",
  "agents": [
    { "agent_key": "lead", "name": "Lead", "role": "...", "goal": "...", "backstory": "..." },
    { "agent_key": "worker", "name": "Worker", "role": "...", "goal": "...", "backstory": "..." },
    { "agent_key": "reporter", "name": "Reporter", "role": "...", "goal": "...", "backstory": "..." }
  ]
}
```

```python
crew = AgentFactory.from_preset("my-crew")  # returns list[BaseAgent]
```

### Subclassing BaseAgent

For agents that need domain-specific orchestration beyond the default `handle_task()`:

```python
from agents.base import AgentDefinition, BaseAgent

class MySpecialisedAgent(BaseAgent):
    def __init__(self):
        defn = AgentDefinition(
            agent_key="specialised",
            name="Specialised Agent",
            role="Domain Specialist",
            goal="Handle complex domain workflows",
            backstory="...",
            domain="my-domain",
        )
        super().__init__(defn)

    async def handle_task(self, task_data):
        # Custom orchestration logic
        ...
```

---

## Built-in Presets

### QA Crew (`qa-standard`)

The original 6-agent QA team — the default preset.

| Agent | Capabilities | Primary Focus | Source |
|-------|--------------|---------------|--------|
| **QA Manager** | Test planning, delegation, fuzzy verification | Orchestration | `agents/manager/qa_manager.py` |
| **Senior QA Engineer** | Self-healing UI, model-based testing, edge cases | Complex Testing | `agents/senior/senior_qa.py` |
| **Junior QA Worker** | Regression execution, data generation, optimization | Test Automation | `agents/junior/junior_qa.py` |
| **QA Analyst** | Reporting, security assessment, performance profiling | Analysis & Reporting | `agents/analyst/qa_analyst.py` |
| **Security & Compliance** | OWASP, GDPR, PCI DSS, SOC 2, ISO 27001, HIPAA | Security & Compliance | `agents/security_compliance/qa_security_compliance.py` |
| **Performance & Resilience** | Load testing, performance monitoring, resilience checks | Performance | `agents/performance/qa_performance.py` |

### Data Engineering Crew (`data-engineering`)

| Agent | Primary Focus |
|-------|---------------|
| **Pipeline Architect** | Pipeline design, DAG orchestration, schema management |
| **Data Quality Engineer** | Validation, anomaly detection, SLA monitoring |
| **DataOps Engineer** | Infrastructure monitoring, incident response, backfills |

### DevOps Crew (`devops`)

| Agent | Primary Focus |
|-------|---------------|
| **Deployment Manager** | CI/CD orchestration, canary analysis, rollback planning |
| **Infrastructure Monitor** | Monitoring, alerting, SLA tracking, anomaly detection |
| **Incident Responder** | Incident triage, RCA, post-mortems, runbook creation |

---

## QA Agent Details

### QA Manager
**Focus**: Orchestration, test plan decomposition, delegation, fuzzy verification.

**Key tools**:
- TestPlanDecompositionTool
- FuzzyVerificationTool

### Senior QA Engineer
**Focus**: Self-healing UI, model-based testing, edge case analysis, AI-driven test generation.

**Key tools**:
- SelfHealingTool
- ModelBasedTestingTool
- EdgeCaseAnalysisTool
- AITestGenerationTool
- CodeAnalysisTestGeneratorTool
- AutonomousTestDataGeneratorTool

### Junior QA Worker
**Focus**: Regression execution, synthetic data, test ordering optimization, UX testing, localization, cross-platform testing.

**Key tools**:
- RegressionTestingTool
- SyntheticDataGeneratorTool
- TestExecutionOptimizerTool
- VisualRegressionTool
- FlakyTestDetectionTool
- UXUsabilityTestingTool
- LocalizationTestingTool
- MobileAppTestingTool
- DesktopAppTestingTool
- CrossPlatformTestingTool

### QA Analyst
**Focus**: Aggregation, reporting, security and performance analysis, traceability, predictive analytics.

**Key tools**:
- DataOrganizationReportingTool
- SecurityAssessmentTool
- PerformanceProfilingTool
- TestTraceabilityTool
- DefectPredictionTool
- QualityTrendAnalysisTool
- RiskScoringTool
- ReleaseReadinessTool

### Security & Compliance Agent
**Focus**: OWASP, GDPR, PCI DSS, SOC 2, ISO 27001, HIPAA.

**Key tools**:
- ComprehensiveSecurityAssessmentTool
- GDPRComplianceTool
- PCIDSSComplianceTool
- SOC2ComplianceTool
- ISO27001ComplianceTool
- HIPAAComplianceTool

### Performance & Resilience Agent
**Focus**: Performance monitoring, load testing, resilience validation, advanced profiling.

**Key tools**:
- PerformanceMonitoringTool
- LoadTestingTool
- ResilienceValidationTool
- AdvancedProfilingTool

---

## Configuration

```bash
# Required
OPENAI_API_KEY=your_api_key
REDIS_HOST=redis
RABBITMQ_HOST=rabbitmq

# Optional (URL-based override)
REDIS_URL=redis://redis:6379/0
RABBITMQ_URL=amqp://guest:guest@rabbitmq:5672/
```

## Quick Deployment

```bash
# Production (on AGNOS host)
docker compose up -d

# Development (adds redis + postgres containers)
docker compose --profile dev up -d

# Standalone (same compose file handles everything)
docker compose up -d
```

---

*Last Updated: 2026-03-14*
*Architecture: AAS — General-purpose agent platform with QA, Data Engineering, and DevOps presets*
