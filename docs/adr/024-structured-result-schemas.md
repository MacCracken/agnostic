# ADR-024: Structured Result Schemas for YEOMAN

**Status**: Accepted
**Date**: 2026-03-05
**Authors**: Agnostic team

---

## Context

YEOMAN needs to parse Agnostic QA results programmatically to take automated actions: create GitHub issues for critical security findings, block PR merges on test failures, and alert on performance regressions. Previously, results were returned as unstructured JSON blobs that required YEOMAN-side parsing logic for every result type.

---

## Decision

Introduce typed dataclass schemas in `shared/yeoman_schemas.py` that provide structured, actionable results. Each result type includes a `to_yeoman_action()` method that converts findings into a list of actions YEOMAN can execute directly.

### Schema Hierarchy

```
Finding (individual QA finding)
  - finding_id, title, description, severity, category, component
  - Optional: cwe_id, cvss_score, evidence, remediation

SecurityResult
  - findings: list[Finding]
  - to_yeoman_action() -> create_issue (critical), block_merge (high)

PerformanceResult
  - response_times, throughput, error_rate, regression_detected
  - to_yeoman_action() -> create_issue (regression/error), block_merge (severe degradation)

TestExecutionResult
  - total_tests, passed, failed, coverage_percentage, flaky_tests
  - to_yeoman_action() -> block_merge (failures), create_issue (flaky/low coverage)

QAReport (aggregation)
  - security, performance, test_execution
  - to_yeoman_action() -> aggregates all sub-result actions
```

### Action Types

| Action | Trigger | Priority |
|--------|---------|----------|
| `create_issue` | Critical security finding | highest |
| `create_issue` | Performance regression | high |
| `create_issue` | High error rate (>5%) | high |
| `create_issue` | Flaky tests detected | medium |
| `create_issue` | Coverage below 80% | medium |
| `block_merge` | High security findings | - |
| `block_merge` | Response time >2x previous | - |
| `block_merge` | Test failures | - |

### API Endpoint

`GET /api/results/structured/{session_id}?result_type=security|performance|test_execution`

Fetches raw data from Redis, constructs typed schema objects, and returns the `to_yeoman_action()` output.

---

## Files Modified

- `shared/yeoman_schemas.py` — `Finding`, `SecurityResult`, `PerformanceResult`, `TestExecutionResult`, `QAReport` dataclasses
- `webgui/api.py` — `GET /api/results/structured/{session_id}` endpoint
- `tests/unit/test_yeoman_schemas.py` — 35+ unit tests

---

## Consequences

### Positive
- YEOMAN can parse results without custom logic per result type
- Action thresholds are centralized in Agnostic (not spread across YEOMAN tools)
- Type-safe: dataclasses catch structural errors at construction time
- Labels and priorities are standardized across all result types

### Negative
- Schema changes require coordination with YEOMAN MCP tool consumers
- Thresholds (e.g., 80% coverage, 5% error rate) are hardcoded — may need configuration later

### Neutral
- Raw Redis data format remains unchanged — schemas are a presentation layer
