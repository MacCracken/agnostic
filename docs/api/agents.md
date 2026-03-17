# Agent API Reference

## Overview

AAS supports multi-domain agent crews assembled from presets or custom team specifications. All task submission flows through the crew builder at `POST /api/v1/crews`.

## Presets

18 built-in presets across 5 domains, each with lean/standard/large sizes:

| Domain | Lean | Standard | Large | Specialty |
|--------|------|----------|-------|-----------|
| **quality** | 3 agents | 6 agents | 9 agents | `quality-security` (2), `quality-performance` (2) |
| **software-engineering** | 2 agents | 5 agents | 8 agents | |
| **design** | 2 agents | 4 agents | 7 agents | |
| **data-engineering** | 2 agents | 3 agents | 6 agents | |
| **devops** | 2 agents | 3 agents | 6 agents | |
| **complete** | 4 agents (cross-domain) | | | |

## Quality Agents (quality-standard)

### QA Manager
- **Tools**: `TestPlanDecompositionTool`, `FuzzyVerificationTool`
- **Focus**: Test plan decomposition, delegation, fuzzy verification

### Senior QA Engineer
- **File**: `agents/senior/senior_qa.py`
- **Tools**: `SelfHealingTool`, `ModelBasedTestingTool`, `EdgeCaseAnalysisTool`, `AITestGenerationTool`, `CodeAnalysisTestGeneratorTool`, `AutonomousTestDataGeneratorTool`

### Junior QA Worker
- **File**: `agents/junior/junior_qa.py`
- **Tools**: `RegressionTestingTool`, `SyntheticDataGeneratorTool`, `TestExecutionOptimizerTool`, `FlakyTestDetectionTool`, `VisualRegressionTool`

### QA Analyst
- **File**: `agents/analyst/qa_analyst.py`
- **Tools**: `DataOrganizationReportingTool`, `SecurityAssessmentTool`, `PerformanceProfilingTool`, `TestTraceabilityTool`, `DefectPredictionTool`, `QualityTrendAnalysisTool`, `RiskScoringTool`, `ReleaseReadinessTool`

### Security & Compliance Agent
- **File**: `agents/security_compliance/qa_security_compliance.py`
- **Tools**: `ComprehensiveSecurityAssessmentTool`, `GDPRComplianceTool`, `PCIDSSComplianceTool`, `SOC2ComplianceTool`, `ISO27001ComplianceTool`, `HIPAAComplianceTool`

### Performance & Resilience Agent
- **File**: `agents/performance/qa_performance.py`
- **Tools**: `PerformanceMonitoringTool`, `LoadTestingTool`, `ResilienceValidationTool`, `AdvancedProfilingTool`

## REST Endpoints

### Task Submission
- `POST /api/v1/tasks` — Submit a quality task (default: `quality-standard` crew)
- `POST /api/v1/tasks/security` — Security-focused crew (`quality-security`)
- `POST /api/v1/tasks/performance` — Performance-focused crew (`quality-performance`)
- `POST /api/v1/tasks/regression` — Regression crew (`quality-lean`)
- `POST /api/v1/tasks/full` — Full crew (`quality-large`)

### Crew Builder
- `POST /api/v1/crews` — Run a crew from preset, agent keys, inline definitions, or team spec
- `GET /api/v1/crews/{id}` — Poll crew status

### Presets & Definitions
- `GET /api/v1/presets` — List presets (filter by `domain`, `size`)
- `GET /api/v1/presets/{name}` — Get preset details with agent list
- `GET /api/v1/definitions` — List agent definitions
- `POST /api/v1/definitions` — Create agent definition

### MCP Tools
- `agnostic_run_crew` — Run a crew (accepts `domain`+`size`, `preset`, `team`, or `agent_definitions`)
- `agnostic_preset_recommend` — Recommend a preset from a task description
- `agnostic_list_presets` — List presets with agent details
- `agnostic_submit_task` — Submit a quality task
- `agnostic_crew_status` — Poll crew status

## Configuration

Each agent supports environment-based configuration:
- `REDIS_HOST`, `REDIS_PORT` — Redis connection
- `OPENAI_API_KEY` — LLM integration
- `QA_TEAM_SIZE` — Default team size (`lean`, `standard`, `large`)
- `AGNOS_LLM_GATEWAY_URL` — LLM gateway (optional)
