"""Structured results endpoint for YEOMAN integration."""

import json
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException

from webgui.routes.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/results/structured/{session_id}")
async def get_structured_results(
    session_id: str,
    result_type: str | None = None,
    user: dict = Depends(get_current_user),
):
    """Get structured results for YEOMAN integration.

    Returns typed results that YEOMAN can parse to take programmatic actions:
    - Auto-create issues for critical security findings
    - Block PRs on regression failures
    - Alert on flaky tests
    """
    try:
        from config.environment import config
        from shared.yeoman_schemas import (
            PerformanceResult,
            QAReport,
            SecurityResult,
            TestExecutionResult,
        )

        redis_client = config.get_redis_client()

        results = {}

        if result_type in (None, "security"):
            security_data = redis_client.get(f"security_compliance:{session_id}:audit")
            if security_data:
                sec = json.loads(security_data)
                findings = []
                for v in sec.get("vulnerabilities", []):
                    from shared.yeoman_schemas import (
                        Finding,
                        FindingCategory,
                        FindingSeverity,
                    )

                    findings.append(
                        Finding(
                            finding_id=v.get("id", f"sec-{len(findings)}"),
                            title=v.get("description", "Unknown vulnerability"),
                            description=v.get("description", ""),
                            severity=FindingSeverity(v.get("severity", "medium")),
                            category=FindingCategory.SECURITY,
                            component=v.get("component", "unknown"),
                            cwe_id=v.get("cwe_id"),
                            cvss_score=v.get("cvss_score"),
                        )
                    )
                results["security"] = SecurityResult(
                    scan_id=f"scan-{session_id}",
                    session_id=session_id,
                    scan_type="comprehensive",
                    timestamp=datetime.now(UTC).isoformat(),
                    overall_score=sec.get("security_score", 0),
                    risk_level=sec.get("risk_level", "unknown"),
                    findings=findings,
                    compliance_scores=sec.get("compliance_scores", {}),
                )

        if result_type in (None, "performance"):
            perf_data = redis_client.get(f"analyst:{session_id}:performance")
            if perf_data:
                perf = json.loads(perf_data)
                results["performance"] = PerformanceResult(
                    test_id=f"perf-{session_id}",
                    session_id=session_id,
                    test_type=perf.get("test_type", "load"),
                    timestamp=datetime.now(UTC).isoformat(),
                    duration_seconds=perf.get("duration", 0),
                    response_times=perf.get("response_times", {}),
                    throughput=perf.get("throughput", {}).get("rps", 0),
                    error_rate=perf.get("error_rate", 0),
                    regression_detected=perf.get("regression_detected", False),
                )

        if result_type in (None, "test_execution"):
            test_data = redis_client.get(f"junior:{session_id}:test_results")
            if test_data:
                test = json.loads(test_data)
                results["test_execution"] = TestExecutionResult(
                    execution_id=f"exec-{session_id}",
                    session_id=session_id,
                    test_type="automated",
                    timestamp=datetime.now(UTC).isoformat(),
                    status="passed"
                    if test.get("passed", 0) > test.get("failed", 0)
                    else "failed",
                    total_tests=test.get("total", 0),
                    passed=test.get("passed", 0),
                    failed=test.get("failed", 0),
                    skipped=test.get("skipped", 0),
                    coverage_percentage=test.get("coverage", 0),
                )

        if not results:
            return {"session_id": session_id, "message": "No results found"}

        report = QAReport(
            report_id=f"report-{session_id}",
            session_id=session_id,
            report_type=result_type or "comprehensive",
            generated_at=datetime.now(UTC).isoformat(),
            summary="Structured results for YEOMAN integration",
            security=results.get("security"),
            performance=results.get("performance"),
            test_execution=results.get("test_execution"),
        )

        return report.to_yeoman_action()

    except Exception as e:
        logger.error(f"Error generating structured results: {e}")
        raise HTTPException(status_code=500, detail="Internal server error") from e
