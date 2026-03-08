# Agent Documentation Index

## 6-Agent Architecture

### Quick Reference

| Agent | Capabilities | Primary Focus | Documentation |
|-------|--------------|---------------|---------------|
| **QA Manager** | Test planning, delegation, fuzzy verification | Orchestration | `agents/manager/qa_manager.py` |
| **Senior QA Engineer** | Self-healing UI, model-based testing, edge cases | Complex Testing | `agents/senior/senior_qa.py` |
| **Junior QA Worker** | Regression execution, data generation, optimization | Test Automation | `agents/junior/junior_qa.py` |
| **QA Analyst** | Reporting, security assessment, performance profiling | Analysis & Reporting | `agents/analyst/qa_analyst.py` |
| **Security & Compliance Agent** | OWASP, GDPR, PCI DSS, SOC 2, ISO 27001, HIPAA | Security & Compliance | `agents/security_compliance/qa_security_compliance.py` |
| **Performance & Resilience Agent** | Load testing, performance monitoring, resilience checks | Performance & Reliability | `agents/performance/README.md` |

---

## Agent Details

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

## Quick Deployment

```bash
# Production (on AGNOS host)
docker compose up -d

# Development (adds redis + postgres containers)
docker compose --profile dev up -d

# Standalone with distributed workers
docker compose -f docker-compose.old-style.yml --profile workers up -d
```

---

## Configuration Notes

```bash
# Required
OPENAI_API_KEY=your_api_key
REDIS_HOST=redis
RABBITMQ_HOST=rabbitmq

# Optional (URL-based override)
REDIS_URL=redis://redis:6379/0
RABBITMQ_URL=amqp://guest:guest@rabbitmq:5672/
```

---

*Last Updated: 2026-02-13*
*Architecture: 6-Agent with Extended Testing Tools*
