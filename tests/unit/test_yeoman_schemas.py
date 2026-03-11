"""Unit tests for Structured Result Schemas (YEOMAN integration)."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from shared.yeoman_schemas import (
    Finding,
    FindingCategory,
    FindingSeverity,
    PerformanceResult,
    QAReport,
    SecurityResult,
    TestExecutionResult,
    TestStatus,
)


class TestEnums:
    """Tests for enum definitions."""

    def test_finding_severity_values(self):
        assert FindingSeverity.CRITICAL.value == "critical"
        assert FindingSeverity.HIGH.value == "high"
        assert FindingSeverity.MEDIUM.value == "medium"
        assert FindingSeverity.LOW.value == "low"
        assert FindingSeverity.INFO.value == "info"

    def test_finding_category_values(self):
        assert FindingCategory.SECURITY.value == "security"
        assert FindingCategory.PERFORMANCE.value == "performance"
        assert FindingCategory.FUNCTIONAL.value == "functional"
        assert FindingCategory.ACCESSIBILITY.value == "accessibility"
        assert FindingCategory.COMPLIANCE.value == "compliance"
        assert FindingCategory.REGRESSION.value == "regression"

    def test_test_status_values(self):
        assert TestStatus.PASSED.value == "passed"
        assert TestStatus.FAILED.value == "failed"
        assert TestStatus.SKIPPED.value == "skipped"
        assert TestStatus.ERROR.value == "error"

    def test_severity_is_str_enum(self):
        assert isinstance(FindingSeverity.CRITICAL, str)
        assert FindingSeverity("critical") == FindingSeverity.CRITICAL

    def test_category_is_str_enum(self):
        assert isinstance(FindingCategory.SECURITY, str)
        assert FindingCategory("security") == FindingCategory.SECURITY


class TestFinding:
    """Tests for Finding dataclass."""

    def test_basic_finding(self):
        f = Finding(
            finding_id="f-001",
            title="SQL Injection",
            description="Input not sanitized",
            severity=FindingSeverity.CRITICAL,
            category=FindingCategory.SECURITY,
            component="login",
        )
        assert f.finding_id == "f-001"
        assert f.severity == FindingSeverity.CRITICAL
        assert f.category == FindingCategory.SECURITY

    def test_finding_optional_fields_default_none(self):
        f = Finding(
            finding_id="f-002",
            title="Test",
            description="Desc",
            severity=FindingSeverity.LOW,
            category=FindingCategory.FUNCTIONAL,
            component="api",
        )
        assert f.test_id is None
        assert f.line_number is None
        assert f.evidence is None
        assert f.remediation is None
        assert f.cwe_id is None
        assert f.cvss_score is None

    def test_finding_with_all_fields(self):
        f = Finding(
            finding_id="f-003",
            title="XSS",
            description="Reflected XSS in search",
            severity=FindingSeverity.HIGH,
            category=FindingCategory.SECURITY,
            component="search",
            test_id="test-xss-001",
            line_number=42,
            evidence={"payload": "<script>alert(1)</script>"},
            remediation="Sanitize user input",
            cwe_id="CWE-79",
            cvss_score=7.5,
        )
        assert f.cwe_id == "CWE-79"
        assert f.cvss_score == 7.5
        assert f.evidence["payload"] == "<script>alert(1)</script>"


class TestSecurityResult:
    """Tests for SecurityResult and its to_yeoman_action method."""

    def _make_finding(self, severity: FindingSeverity, fid: str = "f-1") -> Finding:
        return Finding(
            finding_id=fid,
            title=f"{severity.value} finding",
            description=f"A {severity.value} issue",
            severity=severity,
            category=FindingCategory.SECURITY,
            component="test",
        )

    def _make_result(self, findings: list[Finding] | None = None) -> SecurityResult:
        return SecurityResult(
            scan_id="scan-1",
            session_id="sess-1",
            scan_type="comprehensive",
            timestamp="2026-03-05T00:00:00",
            overall_score=85.0,
            risk_level="medium",
            findings=findings or [],
        )

    def test_no_findings_no_actions(self):
        result = self._make_result()
        action = result.to_yeoman_action()

        assert action["scan_id"] == "scan-1"
        assert action["actions"] == []
        assert action["critical_count"] == 0
        assert action["high_count"] == 0

    def test_critical_finding_creates_issue(self):
        findings = [self._make_finding(FindingSeverity.CRITICAL)]
        result = self._make_result(findings)
        action = result.to_yeoman_action()

        assert action["critical_count"] == 1
        assert len(action["actions"]) == 1
        assert action["actions"][0]["type"] == "create_issue"
        assert action["actions"][0]["priority"] == "highest"
        assert "CRITICAL" in action["actions"][0]["title"]
        assert "security" in action["actions"][0]["labels"]

    def test_high_finding_blocks_merge(self):
        findings = [self._make_finding(FindingSeverity.HIGH)]
        result = self._make_result(findings)
        action = result.to_yeoman_action()

        assert action["high_count"] == 1
        block_actions = [a for a in action["actions"] if a["type"] == "block_merge"]
        assert len(block_actions) == 1
        assert "f-1" in block_actions[0]["findings"]

    def test_critical_and_high_generate_both_actions(self):
        findings = [
            self._make_finding(FindingSeverity.CRITICAL, "f-c1"),
            self._make_finding(FindingSeverity.HIGH, "f-h1"),
        ]
        result = self._make_result(findings)
        action = result.to_yeoman_action()

        types = [a["type"] for a in action["actions"]]
        assert "create_issue" in types
        assert "block_merge" in types

    def test_low_findings_no_actions(self):
        findings = [
            self._make_finding(FindingSeverity.LOW),
            self._make_finding(FindingSeverity.INFO, "f-2"),
        ]
        result = self._make_result(findings)
        action = result.to_yeoman_action()

        assert action["actions"] == []
        assert action["findings_count"] == 2

    def test_score_and_risk_in_output(self):
        result = self._make_result()
        action = result.to_yeoman_action()

        assert action["score"] == 85.0
        assert action["risk_level"] == "medium"


class TestPerformanceResult:
    """Tests for PerformanceResult and its to_yeoman_action method."""

    def _make_result(self, **kwargs) -> PerformanceResult:
        defaults = {
            "test_id": "perf-1",
            "session_id": "sess-1",
            "test_type": "load",
            "timestamp": "2026-03-05T00:00:00",
            "duration_seconds": 60.0,
            "response_times": {"avg": 200, "p95": 400, "p99": 800},
            "throughput": 100.0,
            "error_rate": 0.5,
        }
        defaults.update(kwargs)
        return PerformanceResult(**defaults)

    def test_no_issues_no_actions(self):
        result = self._make_result()
        action = result.to_yeoman_action()

        assert action["actions"] == []
        assert action["avg_response_time"] == 200
        assert action["throughput"] == 100.0

    def test_regression_creates_issue(self):
        result = self._make_result(
            regression_detected=True,
            previous_score=100.0,
        )
        action = result.to_yeoman_action()

        issue_actions = [a for a in action["actions"] if a["type"] == "create_issue"]
        assert len(issue_actions) == 1
        assert "REGRESSION" in issue_actions[0]["title"]

    def test_severe_degradation_blocks_merge(self):
        result = self._make_result(
            response_times={"avg": 500},
            previous_score=200.0,  # 500 > 200 * 2 = 400
        )
        action = result.to_yeoman_action()

        block_actions = [a for a in action["actions"] if a["type"] == "block_merge"]
        assert len(block_actions) == 1
        assert ">100%" in block_actions[0]["reason"]

    def test_no_block_if_degradation_under_threshold(self):
        result = self._make_result(
            response_times={"avg": 350},
            previous_score=200.0,  # 350 < 200 * 2 = 400
        )
        action = result.to_yeoman_action()

        block_actions = [a for a in action["actions"] if a["type"] == "block_merge"]
        assert len(block_actions) == 0

    def test_high_error_rate_creates_issue(self):
        result = self._make_result(error_rate=8.5)
        action = result.to_yeoman_action()

        issue_actions = [a for a in action["actions"] if a["type"] == "create_issue"]
        assert len(issue_actions) == 1
        assert "ERROR RATE" in issue_actions[0]["title"]
        assert "8.5%" in issue_actions[0]["title"]

    def test_error_rate_below_threshold_no_action(self):
        result = self._make_result(error_rate=4.9)
        action = result.to_yeoman_action()

        assert action["actions"] == []

    def test_output_includes_key_metrics(self):
        result = self._make_result()
        action = result.to_yeoman_action()

        assert action["test_id"] == "perf-1"
        assert action["session_id"] == "sess-1"
        assert action["p95_response_time"] == 400
        assert action["error_rate"] == 0.5
        assert action["regression_detected"] is False


class TestTestExecutionResult:
    """Tests for TestExecutionResult and its to_yeoman_action method."""

    def _make_result(self, **kwargs) -> TestExecutionResult:
        defaults = {
            "execution_id": "exec-1",
            "session_id": "sess-1",
            "test_type": "automated",
            "timestamp": "2026-03-05T00:00:00",
            "status": TestStatus.PASSED,
            "total_tests": 100,
            "passed": 95,
            "failed": 3,
            "skipped": 2,
            "coverage_percentage": 85.0,
        }
        defaults.update(kwargs)
        return TestExecutionResult(**defaults)

    def test_pass_rate_calculation(self):
        result = self._make_result(total_tests=100, passed=95)
        assert result.pass_rate == 95.0

    def test_pass_rate_zero_total(self):
        result = self._make_result(total_tests=0, passed=0)
        assert result.pass_rate == 0.0

    def test_failures_block_merge(self):
        result = self._make_result(
            failed=3,
            failed_tests=[
                {"name": "test_login"},
                {"name": "test_checkout"},
                {"name": "test_payment"},
            ],
        )
        action = result.to_yeoman_action()

        block_actions = [a for a in action["actions"] if a["type"] == "block_merge"]
        assert len(block_actions) == 1
        assert "3 tests failed" in block_actions[0]["reason"]
        assert "test_login" in block_actions[0]["failed_tests"]

    def test_no_failures_no_block(self):
        result = self._make_result(failed=0)
        action = result.to_yeoman_action()

        block_actions = [a for a in action["actions"] if a["type"] == "block_merge"]
        assert len(block_actions) == 0

    def test_flaky_tests_create_issue(self):
        result = self._make_result(
            flaky_tests=["test_timeout_edge", "test_race_condition"],
        )
        action = result.to_yeoman_action()

        issue_actions = [
            a
            for a in action["actions"]
            if a["type"] == "create_issue" and "FLAKY" in a["title"]
        ]
        assert len(issue_actions) == 1
        assert "2 flaky tests" in issue_actions[0]["title"]

    def test_low_coverage_creates_issue(self):
        result = self._make_result(coverage_percentage=65.0, failed=0)
        action = result.to_yeoman_action()

        issue_actions = [
            a
            for a in action["actions"]
            if a["type"] == "create_issue" and "COVERAGE" in a["title"]
        ]
        assert len(issue_actions) == 1
        assert "65.0%" in issue_actions[0]["title"]

    def test_adequate_coverage_no_issue(self):
        result = self._make_result(coverage_percentage=90.0, failed=0)
        action = result.to_yeoman_action()

        coverage_actions = [
            a for a in action["actions"] if a.get("title", "").startswith("[COVERAGE]")
        ]
        assert len(coverage_actions) == 0

    def test_output_includes_key_fields(self):
        result = self._make_result()
        action = result.to_yeoman_action()

        assert action["execution_id"] == "exec-1"
        assert action["session_id"] == "sess-1"
        assert action["status"] == "passed"
        assert action["total_tests"] == 100
        assert action["passed"] == 95
        assert action["failed"] == 3
        assert action["coverage"] == 85.0


class TestQAReport:
    """Tests for QAReport aggregation."""

    def _make_security(self, critical_count=0, high_count=0) -> SecurityResult:
        findings = []
        for i in range(critical_count):
            findings.append(
                Finding(
                    finding_id=f"f-c{i}",
                    title="Critical",
                    description="Critical issue",
                    severity=FindingSeverity.CRITICAL,
                    category=FindingCategory.SECURITY,
                    component="test",
                )
            )
        for i in range(high_count):
            findings.append(
                Finding(
                    finding_id=f"f-h{i}",
                    title="High",
                    description="High issue",
                    severity=FindingSeverity.HIGH,
                    category=FindingCategory.SECURITY,
                    component="test",
                )
            )
        return SecurityResult(
            scan_id="scan-1",
            session_id="sess-1",
            scan_type="comprehensive",
            timestamp="2026-03-05T00:00:00",
            overall_score=80.0,
            risk_level="medium",
            findings=findings,
        )

    def _make_performance(self, error_rate=1.0) -> PerformanceResult:
        return PerformanceResult(
            test_id="perf-1",
            session_id="sess-1",
            test_type="load",
            timestamp="2026-03-05T00:00:00",
            duration_seconds=60.0,
            error_rate=error_rate,
        )

    def _make_test_exec(self, failed=0) -> TestExecutionResult:
        return TestExecutionResult(
            execution_id="exec-1",
            session_id="sess-1",
            test_type="automated",
            timestamp="2026-03-05T00:00:00",
            status=TestStatus.FAILED if failed > 0 else TestStatus.PASSED,
            total_tests=100,
            passed=100 - failed,
            failed=failed,
            coverage_percentage=90.0,
        )

    def test_empty_report_no_actions(self):
        report = QAReport(
            report_id="r-1",
            session_id="sess-1",
            report_type="comprehensive",
            generated_at="2026-03-05T00:00:00",
            summary="Test",
        )
        action = report.to_yeoman_action()

        assert action["report_id"] == "r-1"
        assert action["actions"] == []

    def test_aggregates_security_actions(self):
        report = QAReport(
            report_id="r-1",
            session_id="sess-1",
            report_type="comprehensive",
            generated_at="2026-03-05T00:00:00",
            summary="Test",
            security=self._make_security(critical_count=1),
        )
        action = report.to_yeoman_action()
        assert len(action["actions"]) == 1  # create_issue for critical

    def test_aggregates_all_result_types(self):
        report = QAReport(
            report_id="r-1",
            session_id="sess-1",
            report_type="comprehensive",
            generated_at="2026-03-05T00:00:00",
            summary="Full report",
            security=self._make_security(critical_count=1, high_count=1),
            performance=self._make_performance(error_rate=10.0),
            test_execution=self._make_test_exec(failed=2),
        )
        action = report.to_yeoman_action()

        # Security: create_issue (critical) + block_merge (high)
        # Performance: create_issue (error rate)
        # Test: block_merge (failures)
        assert len(action["actions"]) >= 4

        action_types = [a["type"] for a in action["actions"]]
        assert "create_issue" in action_types
        assert "block_merge" in action_types

    def test_report_output_structure(self):
        report = QAReport(
            report_id="r-1",
            session_id="sess-1",
            report_type="security",
            generated_at="2026-03-05T00:00:00",
            summary="Security report",
        )
        action = report.to_yeoman_action()

        assert set(action.keys()) == {
            "report_id",
            "session_id",
            "report_type",
            "actions",
        }
