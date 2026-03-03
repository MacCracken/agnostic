"""
Structured Result Schemas for YEOMAN MCP Integration

These schemas provide typed results for QA findings so YEOMAN can parse
and act on results programmatically — e.g., auto-open issues for critical
security findings, block PRs on regression failures.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class FindingSeverity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class FindingCategory(str, Enum):
    SECURITY = "security"
    PERFORMANCE = "performance"
    FUNCTIONAL = "functional"
    ACCESSIBILITY = "accessibility"
    COMPLIANCE = "compliance"
    REGRESSION = "regression"


class TestStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class Finding:
    """Represents a single QA finding."""
    finding_id: str
    title: str
    description: str
    severity: FindingSeverity
    category: FindingCategory
    component: str
    test_id: str | None = None
    line_number: int | None = None
    evidence: dict[str, Any] | None = None
    remediation: str | None = None
    cwe_id: str | None = None
    cvss_score: float | None = None


@dataclass
class SecurityResult:
    """Structured security scan results for YEOMAN integration."""
    scan_id: str
    session_id: str
    scan_type: str
    timestamp: str
    overall_score: float
    risk_level: str
    findings: list[Finding] = field(default_factory=list)
    compliance_scores: dict[str, float] = field(default_factory=dict)
    summary: str = ""

    def to_yeoman_action(self) -> dict[str, Any]:
        """Convert to YEOMAN-actionable format."""
        critical_findings = [f for f in self.findings if f.severity == FindingSeverity.CRITICAL]
        high_findings = [f for f in self.findings if f.severity == FindingSeverity.HIGH]

        actions = []

        # Auto-create issues for critical findings
        if critical_findings:
            actions.append({
                "type": "create_issue",
                "priority": "highest",
                "title": f"[CRITICAL] Security scan found {len(critical_findings)} critical issues",
                "body": "\n\n".join(f"- {f.title}: {f.description}" for f in critical_findings),
                "labels": ["security", "critical", "auto-generated"],
            })

        # Block PRs if high+ findings exist
        if high_findings:
            actions.append({
                "type": "block_merge",
                "reason": f"Found {len(high_findings)} high-severity security issues",
                "findings": [f.finding_id for f in high_findings],
            })

        return {
            "scan_id": self.scan_id,
            "session_id": self.session_id,
            "score": self.overall_score,
            "risk_level": self.risk_level,
            "findings_count": len(self.findings),
            "critical_count": len(critical_findings),
            "high_count": len(high_findings),
            "actions": actions,
        }


@dataclass
class PerformanceResult:
    """Structured performance test results for YEOMAN integration."""
    test_id: str
    session_id: str
    test_type: str  # load, stress, spike, endurance
    timestamp: str
    duration_seconds: float
    response_times: dict[str, float] = field(default_factory=dict)  # p50, p95, p99, avg
    throughput: float = 0.0  # requests per second
    error_rate: float = 0.0
    resource_usage: dict[str, float] = field(default_factory=dict)
    bottlenecks: list[str] = field(default_factory=list)
    regression_detected: bool = False
    previous_score: float | None = None

    def to_yeoman_action(self) -> dict[str, Any]:
        """Convert to YEOMAN-actionable format."""
        actions = []

        # Alert on regression
        if self.regression_detected and self.previous_score:
            actions.append({
                "type": "create_issue",
                "priority": "high",
                "title": f"[REGRESSION] Performance degradation detected",
                "body": f"Response time increased from {self.previous_score}ms to {self.response_times.get('avg', 0)}ms",
                "labels": ["performance", "regression", "auto-generated"],
            })

        # Block on severe degradation
        if self.previous_score and self.response_times.get("avg", 0) > self.previous_score * 2:
            actions.append({
                "type": "block_merge",
                "reason": f"Response time degraded by >100% (was {self.previous_score}ms, now {self.response_times.get('avg', 0)}ms)",
            })

        # Alert on error rate
        if self.error_rate > 5.0:
            actions.append({
                "type": "create_issue",
                "priority": "high",
                "title": f"[HIGH ERROR RATE] {self.error_rate:.1f}% errors during load test",
                "body": f"Error rate exceeds 5% threshold. Throughput: {self.throughput} req/s",
                "labels": ["performance", "errors", "auto-generated"],
            })

        return {
            "test_id": self.test_id,
            "session_id": self.session_id,
            "avg_response_time": self.response_times.get("avg", 0),
            "p95_response_time": self.response_times.get("p95", 0),
            "throughput": self.throughput,
            "error_rate": self.error_rate,
            "regression_detected": self.regression_detected,
            "actions": actions,
        }


@dataclass
class TestExecutionResult:
    """Structured test execution results for YEOMAN integration."""
    execution_id: str
    session_id: str
    test_type: str
    timestamp: str
    status: TestStatus
    total_tests: int
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    duration_seconds: float = 0.0
    coverage_percentage: float = 0.0
    failed_tests: list[dict[str, Any]] = field(default_factory=list)
    flaky_tests: list[str] = field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        if self.total_tests == 0:
            return 0.0
        return (self.passed / self.total_tests) * 100

    def to_yeoman_action(self) -> dict[str, Any]:
        """Convert to YEOMAN-actionable format."""
        actions = []

        # Block on test failures
        if self.failed > 0:
            actions.append({
                "type": "block_merge",
                "reason": f"{self.failed} tests failed",
                "failed_tests": [t.get("name", "unknown") for t in self.failed_tests[:5]],
            })

        # Alert on flaky tests
        if self.flaky_tests:
            actions.append({
                "type": "create_issue",
                "priority": "medium",
                "title": f"[FLAKY] {len(self.flaky_tests)} flaky tests detected",
                "body": "These tests have inconsistent results:\n" + "\n".join(f"- {t}" for t in self.flaky_tests),
                "labels": ["testing", "flaky", "auto-generated"],
            })

        # Alert on low coverage
        if self.coverage_percentage < 80.0:
            actions.append({
                "type": "create_issue",
                "priority": "medium",
                "title": f"[COVERAGE] Test coverage below threshold: {self.coverage_percentage:.1f}%",
                "body": f"Current coverage is {self.coverage_percentage}%, target is 80%",
                "labels": ["testing", "coverage", "auto-generated"],
            })

        return {
            "execution_id": self.execution_id,
            "session_id": self.session_id,
            "status": self.status.value,
            "total_tests": self.total_tests,
            "passed": self.passed,
            "failed": self.failed,
            "pass_rate": self.pass_rate,
            "coverage": self.coverage_percentage,
            "flaky_count": len(self.flaky_tests),
            "actions": actions,
        }


@dataclass
class QAReport:
    """Comprehensive QA report with structured results."""
    report_id: str
    session_id: str
    report_type: str
    generated_at: str
    summary: str

    security: SecurityResult | None = None
    performance: PerformanceResult | None = None
    test_execution: TestExecutionResult | None = None
    compliance: dict[str, Any] = field(default_factory=dict)

    def to_yeoman_action(self) -> dict[str, Any]:
        """Convert to YEOMAN-actionable format."""
        all_actions = []

        if self.security:
            all_actions.extend(self.security.to_yeoman_action()["actions"])

        if self.performance:
            all_actions.extend(self.performance.to_yeoman_action()["actions"])

        if self.test_execution:
            all_actions.extend(self.test_execution.to_yeoman_action()["actions"])

        return {
            "report_id": self.report_id,
            "session_id": self.session_id,
            "report_type": self.report_type,
            "actions": all_actions,
        }
