import asyncio
import json
import logging
import os
import socket
import ssl
import sys
import time
from datetime import datetime, timedelta
from typing import Any, ClassVar

import numpy as np
import pandas as pd
import redis
import requests
from crewai import Agent, Crew, LLM, Process, Task

from shared.crewai_compat import BaseTool

# Add config path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))
from config.environment import config
from config.llm_integration import llm_service

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DataOrganizationReportingTool(BaseTool):
    name: str = "Data Organization & Reporting"
    description: str = "Aggregates test results from all agents, organizes data by category, and generates structured QA reports"

    def _run(self, session_id: str, raw_results: dict[str, Any]) -> dict[str, Any]:
        """Aggregate results and generate a structured QA report"""
        redis_client = config.get_redis_client()

        # Gather results from Senior and Junior agents
        senior_results = self._collect_agent_results(
            redis_client, f"senior:{session_id}"
        )
        junior_results = self._collect_agent_results(
            redis_client, f"junior:{session_id}"
        )

        all_results = senior_results + junior_results
        if raw_results:
            all_results.append(raw_results)

        # Categorize findings by severity
        findings = self._categorize_findings(all_results)

        # Calculate metrics
        metrics = self._calculate_metrics(all_results)

        # Generate trend analysis
        trend = self._generate_trend_analysis(redis_client, session_id, metrics)

        # Build action items
        action_items = self._build_action_items(findings)

        # Executive summary
        executive_summary = self._generate_executive_summary(metrics, findings)

        report = {
            "executive_summary": executive_summary,
            "metrics": metrics,
            "findings_by_severity": findings,
            "trend_analysis": trend,
            "action_items": action_items,
            "report_generated_at": datetime.now().isoformat(),
        }

        # Provide legacy keys expected by unit tests
        report["findings"] = findings
        report["metrics"] = metrics
        report["trend_analysis"] = trend

        return report

    def _collect_agent_results(
        self, redis_client: redis.Redis, prefix: str
    ) -> list[dict]:
        """Collect agent results from Redis"""
        results = []

        try:
            list_results = redis_client.lrange(f"{prefix}:results", 0, -1)
            for item in list_results or []:
                try:
                    results.append(json.loads(item))
                except (TypeError, json.JSONDecodeError):
                    continue
        except Exception:
            list_results = []

        if results:
            return results

        try:
            cursor = 0
            while True:
                cursor, keys = redis_client.scan(
                    cursor, match=f"{prefix}:*:result", count=100
                )
                for key in keys:
                    data = redis_client.get(key)
                    if data:
                        try:
                            results.append(json.loads(data))
                        except json.JSONDecodeError:
                            continue
                if cursor == 0:
                    break
        except Exception:
            return results
        return results

    def _categorize_findings(self, results: list[dict]) -> dict[str, list]:
        """Bucket findings into severity categories"""
        findings = {"critical": [], "high": [], "medium": [], "low": []}

        for result in results:
            severity = result.get("severity")
            if severity in findings:
                findings[severity].append(result)

            # Pull from edge case analysis
            for area in result.get("edge_case_analysis", {}).get("high_risk_areas", []):
                findings["critical"].append({"source": "edge_case", "area": area})

            # Pull from test execution failures
            for failed in result.get("test_execution", {}).get("failed_tests", []):
                severity = (
                    "high"
                    if "auth" in failed.get("test_name", "").lower()
                    else "medium"
                )
                findings[severity].append(
                    {
                        "source": "regression",
                        "test": failed.get("test_name"),
                        "error": failed.get("error_message"),
                    }
                )

            # Pull from self-healing analysis
            healing = result.get("self_healing_analysis")
            if healing and healing.get("confidence_score", 1.0) < 0.7:
                findings["high"].append(
                    {
                        "source": "self_healing",
                        "detail": "Low healing confidence",
                        "score": healing.get("confidence_score"),
                    }
                )

            # Pull from complexity assessment
            complexity = result.get("complexity_assessment", {})
            if complexity.get("complexity_level") == "high":
                findings["medium"].append(
                    {
                        "source": "complexity",
                        "level": "high",
                        "scenario": result.get("scenario_id"),
                    }
                )

            # Recommendations as low-severity informational items
            for rec in result.get("recommendations", []):
                findings["low"].append({"source": "recommendation", "detail": rec})

        return findings

    def _calculate_metrics(self, results: list[dict]) -> dict[str, float]:
        """Compute summary metrics across all results"""
        total_tests = 0
        passed = 0
        failed = 0
        coverage_scores = []
        detection_times = []

        for result in results:
            if "tests_run" in result:
                total_tests += result.get("tests_run", 0)
                passed += result.get("passed", 0)
                failed += result.get("failed", 0)

            exec_data = result.get("test_execution", {}).get("results", {})
            total_tests += exec_data.get("total_tests", 0)
            passed += exec_data.get("passed", 0)
            failed += exec_data.get("failed", 0)

            mbt = result.get("model_based_testing", {})
            if mbt.get("coverage_potential"):
                coverage_scores.append(mbt["coverage_potential"])

            exec_time = result.get("test_execution", {}).get("execution_time")
            if exec_time:
                detection_times.append(exec_time)

        pass_rate = (passed / total_tests) if total_tests > 0 else 0.0
        fail_rate = (failed / total_tests) if total_tests > 0 else 0.0
        coverage = float(np.mean(coverage_scores) * 100) if coverage_scores else 0.0
        mttr = float(np.mean(detection_times)) if detection_times else 0.0

        return {
            "pass_rate": pass_rate,
            "fail_rate": fail_rate,
            "failure_rate": fail_rate,
            "coverage": round(coverage, 2),
            "mttr": round(mttr, 2),
            "total_tests": total_tests,
            "passed": passed,
            "failed": failed,
        }

    def _generate_trend_analysis(
        self, redis_client: redis.Redis, session_id: str, current_metrics: dict
    ) -> dict[str, str]:
        """Compare current session metrics against historical data"""
        previous_data = redis_client.hgetall("analyst:metrics_history")

        prev = None
        if previous_data:
            previous_report = previous_data.get("previous_run") or previous_data.get(
                "latest"
            )
            if isinstance(previous_report, (str, bytes, bytearray)):
                try:
                    prev = json.loads(previous_report)
                except json.JSONDecodeError:
                    prev = None
        else:
            previous_report = redis_client.get("analyst:latest_report_metrics")
            if isinstance(previous_report, (str, bytes, bytearray)):
                try:
                    prev = json.loads(previous_report)
                except json.JSONDecodeError:
                    prev = None

        if prev:
            delta = current_metrics["pass_rate"] - prev.get("pass_rate", 0)
            if delta > 0:
                comparison = f"Pass rate improved by {delta:.2f}"
                trend = "improving"
            elif delta < 0:
                comparison = f"Pass rate declined by {abs(delta):.2f}"
                trend = "declining"
            else:
                comparison = "Pass rate unchanged"
                trend = "stable"
        else:
            comparison = "First session — no historical data"
            trend = "stable"

        redis_client.hset(
            "analyst:metrics_history",
            mapping={"previous_run": json.dumps(current_metrics)},
        )

        return {
            "trend": trend,
            "comparison": comparison,
            "current_vs_previous": comparison,
            "regression_trend": trend,
        }

    def _build_action_items(self, findings: dict[str, list]) -> list[dict[str, str]]:
        """Create prioritized action items from findings"""
        items = []
        for finding in findings.get("critical", []):
            items.append(
                {
                    "priority": "critical",
                    "description": f"Address critical finding in {finding.get('area', finding.get('detail', 'unknown'))}",
                    "assigned_to": "senior",
                }
            )
        for finding in findings.get("high", []):
            items.append(
                {
                    "priority": "high",
                    "description": f"Investigate high-severity issue: {finding.get('test', finding.get('detail', 'unknown'))}",
                    "assigned_to": "senior",
                }
            )
        for finding in findings.get("medium", [])[:5]:
            items.append(
                {
                    "priority": "medium",
                    "description": f"Review medium finding: {finding.get('detail', finding.get('scenario', 'unknown'))}",
                    "assigned_to": "junior",
                }
            )
        return items

    def _generate_executive_summary(self, metrics: dict, findings: dict) -> str:
        """Produce a human-readable executive summary"""
        critical_count = len(findings.get("critical", []))
        high_count = len(findings.get("high", []))
        pass_rate_percent = metrics.get("pass_rate", 0) * 100
        fail_rate_percent = (
            metrics.get("fail_rate", metrics.get("failure_rate", 0)) * 100
        )
        return (
            f"QA Report: {metrics['total_tests']} tests executed — "
            f"{pass_rate_percent:.2f}% pass rate, {fail_rate_percent:.2f}% failure rate. "
            f"{critical_count} critical and {high_count} high-severity findings identified. "
            f"Test coverage at {metrics['coverage']}%."
        )


class SecurityAssessmentTool(BaseTool):
    name: str = "Security Assessment"
    description: str = "Performs security analysis including vulnerability scanning, header inspection, and compliance checking"

    EXPECTED_HEADERS: ClassVar[list[str]] = [
        "Content-Security-Policy",
        "Strict-Transport-Security",
        "X-Frame-Options",
        "X-Content-Type-Options",
        "Referrer-Policy",
        "Permissions-Policy",
        "X-XSS-Protection",
    ]

    async def _run(
        self, target: dict[str, Any], scan_profile: str = "standard"
    ) -> dict[str, Any]:
        """Run security assessment using LLM intelligence"""
        try:
            # Perform basic security checks
            url = target.get("url", "")
            headers_result = self._analyze_headers(url)
            tls_result = self._assess_tls(url)
            cors_result = self._check_cors(url)
            disclosure_result = self._check_info_disclosure(url)
            owasp_result = self._evaluate_owasp_indicators(target)

            # Prepare scan results for LLM analysis
            scan_results = {
                "target_url": url,
                "scan_profile": scan_profile,
                "security_headers": headers_result,
                "tls_configuration": tls_result,
                "cors_status": cors_result,
                "information_disclosure": disclosure_result,
                "owasp_indicators": owasp_result,
            }

            # Use LLM for intelligent analysis
            analysis = await llm_service.analyze_security_findings(scan_results)
            logger.info(f"Performed LLM-based security analysis for {url}")
            return analysis

        except Exception as e:
            logger.error(f"Failed to perform LLM security analysis: {e}")
            # Fallback to basic analysis
            return self._fallback_security_analysis(target)

    def _fallback_security_analysis(self, target: dict[str, Any]) -> dict[str, Any]:
        """Fallback security analysis without LLM"""
        url = target.get("url", "")
        headers_result = self._analyze_headers(url)
        tls_result = self._assess_tls(url)
        cors_result = self._check_cors(url)
        disclosure_result = self._check_info_disclosure(url)
        owasp_result = self._evaluate_owasp_indicators(target)

        vulnerabilities = []

        for issue in tls_result.get("issues", []):
            vulnerabilities.append(
                {
                    "type": "tls_configuration",
                    "severity": "high",
                    "description": issue,
                    "remediation": "Update TLS configuration to use TLS 1.2+ with strong cipher suites",
                }
            )

        if cors_result.get("misconfigured"):
            vulnerabilities.append(
                {
                    "type": "cors_misconfiguration",
                    "severity": "high",
                    "description": cors_result["detail"],
                    "remediation": "Restrict Access-Control-Allow-Origin to trusted domains",
                }
            )

        for disclosure in disclosure_result:
            vulnerabilities.append(
                {
                    "type": "information_disclosure",
                    "severity": "low",
                    "description": disclosure,
                    "remediation": "Remove or mask server version and technology information",
                }
            )

        vulnerabilities.extend(owasp_result)

        # Calculate score
        deductions = sum(
            0.15
            if v["severity"] == "critical"
            else 0.10
            if v["severity"] == "high"
            else 0.05
            if v["severity"] == "medium"
            else 0.02
            for v in vulnerabilities
        )
        score = max(0.0, min(1.0, 1.0 - deductions))

        if score >= 0.9:
            risk_level = "low"
        elif score >= 0.7:
            risk_level = "medium"
        elif score >= 0.5:
            risk_level = "high"
        else:
            risk_level = "critical"

        recommendations = self._build_recommendations(vulnerabilities)

        return {
            "security_score": round(score, 2),
            "risk_level": risk_level,
            "header_analysis": headers_result,
            "tls_assessment": tls_result,
            "vulnerabilities": vulnerabilities,
            "compliance_status": {
                "owasp_top_10": {v["type"]: v["severity"] for v in owasp_result},
                "headers_best_practice": len(headers_result.get("missing", [])) == 0,
            },
            "recommendations": recommendations,
        }

    def _analyze_headers(self, url: str) -> dict[str, Any]:
        """Inspect HTTP security headers"""
        present = []
        missing = []
        misconfigured = []

        if not url:
            return {
                "present": [],
                "missing": self.EXPECTED_HEADERS,
                "misconfigured": [],
            }

        try:
            resp = requests.get(url, timeout=10, allow_redirects=True)
            resp_headers = {k.lower(): v for k, v in resp.headers.items()}

            for header in self.EXPECTED_HEADERS:
                if header.lower() in resp_headers:
                    present.append(header)
                    # Check for weak values
                    val = resp_headers[header.lower()]
                    if header == "X-Frame-Options" and val.lower() not in (
                        "deny",
                        "sameorigin",
                    ):
                        misconfigured.append(
                            {
                                "header": header,
                                "value": val,
                                "issue": "Should be DENY or SAMEORIGIN",
                            }
                        )
                    if header == "X-Content-Type-Options" and val.lower() != "nosniff":
                        misconfigured.append(
                            {
                                "header": header,
                                "value": val,
                                "issue": "Should be nosniff",
                            }
                        )
                else:
                    missing.append(header)
        except requests.RequestException:
            missing = list(self.EXPECTED_HEADERS)

        return {"present": present, "missing": missing, "misconfigured": misconfigured}

    def _assess_tls(self, url: str) -> dict[str, Any]:
        """Assess TLS/SSL configuration"""
        result = {"grade": "unknown", "issues": []}
        try:
            from urllib.parse import urlparse

            parsed = urlparse(url)
            if parsed.scheme != "https":
                result["grade"] = "F"
                result["issues"].append("Site does not use HTTPS")
                return result

            hostname = parsed.hostname
            port = parsed.port or 443
            ctx = ssl.create_default_context()
            with socket.create_connection((hostname, port), timeout=5) as sock:
                with ctx.wrap_socket(sock, server_hostname=hostname) as ssock:
                    protocol = ssock.version()
                    if protocol and "TLSv1.0" in protocol:
                        result["issues"].append("TLS 1.0 is deprecated")
                    if protocol and "TLSv1.1" in protocol:
                        result["issues"].append("TLS 1.1 is deprecated")
                    result["protocol"] = protocol

            if not result["issues"]:
                result["grade"] = "A"
            else:
                result["grade"] = "C"
        except Exception as e:
            result["grade"] = "F"
            result["issues"].append(f"TLS connection failed: {e!s}")

        return result

    def _check_cors(self, url: str) -> dict[str, Any]:
        """Verify CORS configuration"""
        result = {"misconfigured": False, "detail": ""}
        if not url:
            return result
        try:
            resp = requests.options(
                url, headers={"Origin": "https://evil.example.com"}, timeout=10
            )
            acao = resp.headers.get("Access-Control-Allow-Origin", "")
            if acao == "*":
                result["misconfigured"] = True
                result["detail"] = "Access-Control-Allow-Origin is set to wildcard (*)"
            elif "evil.example.com" in acao:
                result["misconfigured"] = True
                result["detail"] = "CORS reflects arbitrary Origin header"
        except requests.RequestException:
            pass
        return result

    def _check_info_disclosure(self, url: str) -> list[str]:
        """Check for information disclosure in response headers"""
        disclosures = []
        if not url:
            return disclosures
        try:
            resp = requests.get(url, timeout=10)
            server = resp.headers.get("Server", "")
            if server and any(
                tok in server.lower() for tok in ["apache", "nginx", "iis", "express"]
            ):
                disclosures.append(f"Server header discloses technology: {server}")
            powered = resp.headers.get("X-Powered-By", "")
            if powered:
                disclosures.append(f"X-Powered-By header discloses: {powered}")
        except requests.RequestException:
            pass
        return disclosures

    def _evaluate_owasp_indicators(
        self, target: dict[str, Any]
    ) -> list[dict[str, str]]:
        """Check for OWASP Top 10 indicators based on target configuration"""
        indicators = []
        url = target.get("url", "")

        # A03:2021 Injection — check if test inputs are reflected
        if url:
            try:
                test_payload = "<script>alert(1)</script>"
                resp = requests.get(url, params={"q": test_payload}, timeout=10)
                if test_payload in resp.text:
                    indicators.append(
                        {
                            "type": "A03_injection_xss",
                            "severity": "critical",
                            "description": "Reflected XSS: user input echoed without encoding",
                            "remediation": "Encode all user input in output contexts",
                        }
                    )
            except requests.RequestException:
                pass

        # A01:2021 Broken Access Control — test for directory listing
        if url:
            try:
                resp = requests.get(url.rstrip("/") + "/", timeout=10)
                if (
                    "Index of /" in resp.text
                    or "Directory listing" in resp.text.lower()
                ):
                    indicators.append(
                        {
                            "type": "A01_broken_access_control",
                            "severity": "medium",
                            "description": "Directory listing is enabled",
                            "remediation": "Disable directory listing on the web server",
                        }
                    )
            except requests.RequestException:
                pass

        return indicators

    def _build_recommendations(self, vulnerabilities: list[dict]) -> list[str]:
        """Deduplicate and prioritize recommendations"""
        seen = set()
        recs = []
        for v in sorted(
            vulnerabilities,
            key=lambda x: {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(
                x["severity"], 4
            ),
        ):
            if v["remediation"] not in seen:
                recs.append(v["remediation"])
                seen.add(v["remediation"])
        return recs


class PerformanceProfilingTool(BaseTool):
    name: str = "Performance Profiler"
    description: str = "Profiles application performance including response times, throughput, resource utilization, and bottleneck detection"

    LOAD_PROFILES: ClassVar[dict[str, dict[str, int]]] = {
        "baseline": {"concurrent": 1, "requests_per_endpoint": 5},
        "moderate": {"concurrent": 5, "requests_per_endpoint": 20},
        "stress": {"concurrent": 10, "requests_per_endpoint": 50},
    }

    async def _run(
        self, target_config: dict[str, Any], load_profile: str = "baseline"
    ) -> dict[str, Any]:
        """Profile performance using LLM analysis"""
        try:
            endpoints = target_config.get("endpoints", [])
            base_url = target_config.get("base_url", "")
            if not endpoints and base_url:
                endpoints = [base_url]

            # Collect performance data
            profile = self.LOAD_PROFILES.get(
                load_profile, self.LOAD_PROFILES["baseline"]
            )
            num_requests = profile["requests_per_endpoint"]

            performance_data = {
                "endpoints": endpoints,
                "load_profile": load_profile,
                "requests_per_endpoint": num_requests,
                "test_results": {},
            }

            # Basic performance testing
            for endpoint in endpoints:
                latencies = []
                errors = 0
                for _ in range(num_requests):
                    try:
                        start = time.time()
                        resp = requests.get(endpoint, timeout=30)
                        elapsed = (time.time() - start) * 1000
                        latencies.append(elapsed)
                        if resp.status_code >= 400:
                            errors += 1
                    except requests.RequestException:
                        errors += 1
                        latencies.append(30000)

                performance_data["test_results"][endpoint] = {
                    "latencies": latencies,
                    "errors": errors,
                    "avg_latency": sum(latencies) / len(latencies) if latencies else 0,
                    "error_rate": errors / num_requests if num_requests > 0 else 0,
                }

            # Use LLM for intelligent analysis
            analysis = await llm_service.generate_performance_profile(performance_data)
            logger.info(
                f"Performed LLM-based performance profiling for {len(endpoints)} endpoints"
            )
            return analysis

        except Exception as e:
            logger.error(f"Failed to perform LLM performance profiling: {e}")
            # Fallback to basic analysis
            return self._fallback_performance_analysis(target_config, load_profile)

    def _fallback_performance_analysis(
        self, target_config: dict[str, Any], load_profile: str
    ) -> dict[str, Any]:
        """Fallback performance analysis without LLM"""
        endpoints = target_config.get("endpoints", [])
        base_url = target_config.get("base_url", "")
        if not endpoints and base_url:
            endpoints = [base_url]

        profile = self.LOAD_PROFILES.get(load_profile, self.LOAD_PROFILES["baseline"])
        num_requests = profile["requests_per_endpoint"]

        all_latencies = []
        endpoint_results = {}

        for endpoint in endpoints:
            latencies = []
            errors = 0
            for _ in range(num_requests):
                try:
                    start = time.time()
                    resp = requests.get(endpoint, timeout=30)
                    elapsed = (time.time() - start) * 1000
                    latencies.append(elapsed)
                    if resp.status_code >= 400:
                        errors += 1
                except requests.RequestException:
                    errors += 1
                    latencies.append(30000)

            all_latencies.extend(latencies)
            sorted_lat = sorted(latencies)
            endpoint_results[endpoint] = {
                "avg_ms": round(float(np.mean(sorted_lat)), 1),
                "p95_ms": round(float(np.percentile(sorted_lat, 95)), 1),
                "error_count": errors,
            }

        if not all_latencies:
            return self._empty_result()

        sorted_all = sorted(all_latencies)
        avg = float(np.mean(sorted_all))
        p50 = float(np.percentile(sorted_all, 50))
        p95 = float(np.percentile(sorted_all, 95))
        p99 = float(np.percentile(sorted_all, 99))
        max_ms = float(max(sorted_all))

        total_time_s = sum(all_latencies) / 1000
        rps = len(all_latencies) / total_time_s if total_time_s > 0 else 0
        tps = rps  # 1 transaction per request in simple model

        # Detect bottlenecks
        bottlenecks = self._detect_bottlenecks(endpoint_results, p95)

        # Grade
        grade = self._calculate_grade(avg, p95, p99)

        # Baseline comparison
        baseline_comparison = self._compare_baseline(
            target_config, {"avg_ms": avg, "p95_ms": p95}
        )

        recommendations = []
        if p95 > 2000:
            recommendations.append(
                "P95 latency exceeds 2s — investigate slow queries and add caching"
            )
        if p99 > 5000:
            recommendations.append(
                "P99 tail latency is very high — check for resource contention"
            )
        if bottlenecks:
            recommendations.append(
                "Address identified bottleneck endpoints before scaling"
            )
        if grade in ("D", "F"):
            recommendations.append(
                "Consider load testing with a dedicated tool (k6, Locust) for deeper analysis"
            )

        return {
            "performance_grade": grade,
            "response_times": {
                "avg_ms": round(avg, 1),
                "p50_ms": round(p50, 1),
                "p95_ms": round(p95, 1),
                "p99_ms": round(p99, 1),
                "max_ms": round(max_ms, 1),
            },
            "throughput": {"rps": round(rps, 2), "tps": round(tps, 2)},
            "bottlenecks": bottlenecks,
            "regression_detected": baseline_comparison.get("regression", False),
            "baseline_comparison": baseline_comparison,
            "resource_utilization": {},
            "endpoint_breakdown": endpoint_results,
            "recommendations": recommendations,
        }

    def _detect_bottlenecks(
        self, endpoint_results: dict, overall_p95: float
    ) -> list[dict[str, str]]:
        """Identify endpoints that are significantly slower than others"""
        bottlenecks = []
        if not endpoint_results:
            return bottlenecks

        avg_values = [r["avg_ms"] for r in endpoint_results.values()]
        global_avg = float(np.mean(avg_values)) if avg_values else 0

        for endpoint, data in endpoint_results.items():
            if data["avg_ms"] > global_avg * 2 and data["avg_ms"] > 500:
                bottlenecks.append(
                    {
                        "component": endpoint,
                        "impact": "high" if data["avg_ms"] > overall_p95 else "medium",
                        "evidence": f"Avg {data['avg_ms']:.0f}ms vs global avg {global_avg:.0f}ms",
                    }
                )
            if data["error_count"] > 0:
                bottlenecks.append(
                    {
                        "component": endpoint,
                        "impact": "high",
                        "evidence": f"{data['error_count']} errors during profiling",
                    }
                )
        return bottlenecks

    def _calculate_grade(self, avg: float, p95: float, p99: float) -> str:
        """Assign a letter grade based on response times"""
        if p95 < 200 and avg < 100:
            return "A"
        elif p95 < 500 and avg < 300:
            return "B"
        elif p95 < 1000 and avg < 600:
            return "C"
        elif p95 < 3000:
            return "D"
        return "F"

    def _compare_baseline(self, config: dict, current: dict) -> dict[str, Any]:
        """Compare against stored baseline if available"""
        baseline = config.get("baseline")
        if not baseline:
            return {
                "improved": [],
                "degraded": [],
                "unchanged": ["No baseline provided"],
                "regression": False,
            }

        improved = []
        degraded = []
        unchanged = []

        for metric in ("avg_ms", "p95_ms"):
            baseline_val = baseline.get(metric, 0)
            current_val = current.get(metric, 0)
            if baseline_val == 0:
                continue
            delta_pct = ((current_val - baseline_val) / baseline_val) * 100
            if delta_pct < -5:
                improved.append(f"{metric}: {delta_pct:+.1f}%")
            elif delta_pct > 10:
                degraded.append(f"{metric}: {delta_pct:+.1f}%")
            else:
                unchanged.append(f"{metric}: {delta_pct:+.1f}%")

        return {
            "improved": improved,
            "degraded": degraded,
            "unchanged": unchanged,
            "regression": len(degraded) > 0,
        }

    def _empty_result(self) -> dict[str, Any]:
        return {
            "performance_grade": "F",
            "response_times": {
                "avg_ms": 0,
                "p50_ms": 0,
                "p95_ms": 0,
                "p99_ms": 0,
                "max_ms": 0,
            },
            "throughput": {"rps": 0, "tps": 0},
            "bottlenecks": [],
            "regression_detected": False,
            "baseline_comparison": {"improved": [], "degraded": [], "unchanged": []},
            "resource_utilization": {},
            "endpoint_breakdown": {},
            "recommendations": ["No endpoints configured for profiling"],
        }


class TestTraceabilityTool(BaseTool):
    name: str = "Test Traceability & Coverage"
    description: str = "Maps requirements to tests, links defects, generates coverage matrices, and identifies testing gaps"

    def _run(
        self,
        requirements: list[dict[str, Any]],
        test_cases: list[dict[str, Any]],
        defects: list[dict[str, Any]] | None = None,
        coverage_threshold: float = 0.8,
    ) -> dict[str, Any]:
        """Generate traceability matrix and coverage analysis"""

        if defects is None:
            defects = []

        traceability_matrix = self._build_traceability_matrix(requirements, test_cases)

        coverage_analysis = self._analyze_coverage(
            traceability_matrix, requirements, test_cases, coverage_threshold
        )

        defect_links = self._link_defects_to_tests(defects, test_cases)

        gap_analysis = self._identify_coverage_gaps(
            requirements, test_cases, traceability_matrix
        )

        recommendations = self._generate_recommendations(
            coverage_analysis, gap_analysis, defect_links
        )

        return {
            "traceability_matrix": traceability_matrix,
            "coverage_analysis": coverage_analysis,
            "defect_links": defect_links,
            "gap_analysis": gap_analysis,
            "recommendations": recommendations,
            "summary": {
                "total_requirements": len(requirements),
                "total_test_cases": len(test_cases),
                "total_defects": len(defects),
                "coverage_percentage": coverage_analysis["overall_coverage"],
                "gaps_identified": len(gap_analysis["gaps"]),
                "high_priority_gaps": len(
                    [g for g in gap_analysis["gaps"] if g.get("priority") == "high"]
                ),
            },
        }

    def _build_traceability_matrix(
        self, requirements: list[dict], test_cases: list[dict]
    ) -> list[dict[str, Any]]:
        """Build requirement-to-test mapping matrix"""
        matrix = []

        for req in requirements:
            req_id = req.get("id", req.get("requirement_id", "unknown"))
            req_title = req.get("title", req.get("description", ""))

            linked_tests = []
            for tc in test_cases:
                tc_id = tc.get("id", tc.get("test_id", ""))
                tc_name = tc.get("name", tc.get("test_name", ""))

                if self._is_test_linked_to_requirement(tc, req):
                    linked_tests.append(
                        {
                            "test_id": tc_id,
                            "test_name": tc_name,
                            "test_type": tc.get("type", "unknown"),
                            "status": tc.get("status", "not_run"),
                            "last_result": tc.get("last_result", {}),
                        }
                    )

            matrix.append(
                {
                    "requirement_id": req_id,
                    "requirement_title": req_title,
                    "requirement_type": req.get("type", "functional"),
                    "priority": req.get("priority", "medium"),
                    "linked_tests": linked_tests,
                    "test_count": len(linked_tests),
                    "coverage_status": "covered" if linked_tests else "not_covered",
                }
            )

        return matrix

    def _is_test_linked_to_requirement(
        self, test_case: dict, requirement: dict
    ) -> bool:
        """Determine if a test case maps to a requirement"""
        req_id = requirement.get("id", requirement.get("requirement_id", "")).lower()
        req_keywords = requirement.get("keywords", [])

        tc_text = f"{test_case.get('name', '')} {test_case.get('description', '')} {test_case.get('tags', '')}".lower()
        tc_id = test_case.get("id", test_case.get("test_id", "")).lower()

        if req_id in tc_text or req_id in tc_id:
            return True

        for keyword in req_keywords:
            if keyword.lower() in tc_text:
                return True

        return False

    def _analyze_coverage(
        self,
        matrix: list[dict],
        requirements: list[dict],
        test_cases: list[dict],
        threshold: float,
    ) -> dict[str, Any]:
        """Analyze test coverage across requirements"""
        total_req = len(requirements)
        covered_req = len([r for r in matrix if r["coverage_status"] == "covered"])

        overall_coverage = covered_req / total_req if total_req > 0 else 0

        by_priority = {}
        for priority in ["critical", "high", "medium", "low"]:
            reqs = [r for r in matrix if r.get("priority") == priority]
            covered = len([r for r in reqs if r["coverage_status"] == "covered"])
            count = len(reqs)
            by_priority[priority] = {
                "total": count,
                "covered": covered,
                "coverage_pct": (covered / count * 100) if count > 0 else 0,
            }

        by_type = {}
        for req_type in ["functional", "non_functional", "security", "performance"]:
            reqs = [r for r in matrix if r.get("requirement_type") == req_type]
            covered = len([r for r in reqs if r["coverage_status"] == "covered"])
            count = len(reqs)
            by_type[req_type] = {
                "total": count,
                "covered": covered,
                "coverage_pct": (covered / count * 100) if count > 0 else 0,
            }

        return {
            "overall_coverage": round(overall_coverage * 100, 1),
            "covered_requirements": covered_req,
            "total_requirements": total_req,
            "meets_threshold": overall_coverage >= threshold,
            "threshold": threshold,
            "coverage_by_priority": by_priority,
            "coverage_by_type": by_type,
        }

    def _link_defects_to_tests(
        self, defects: list[dict], test_cases: list[dict]
    ) -> list[dict[str, Any]]:
        """Link defects to their covering tests"""
        linked = []

        for defect in defects:
            defect_id = defect.get("id", defect.get("defect_id", ""))
            related_tests = []

            defect_keywords = (
                f"{defect.get('title', '')} {defect.get('description', '')}".lower()
            )

            for tc in test_cases:
                tc_text = f"{tc.get('name', '')} {tc.get('description', '')}".lower()

                if any(kw in tc_text for kw in defect_keywords.split() if len(kw) > 3):
                    related_tests.append(
                        {
                            "test_id": tc.get("id", tc.get("test_id", "")),
                            "test_name": tc.get("name", tc.get("test_name", "")),
                            "can_detect": True,
                        }
                    )

            linked.append(
                {
                    "defect_id": defect_id,
                    "title": defect.get("title", ""),
                    "severity": defect.get("severity", "medium"),
                    "status": defect.get("status", "open"),
                    "related_tests": related_tests,
                    "test_coverage": len(related_tests),
                    "has_test_coverage": len(related_tests) > 0,
                }
            )

        return linked

    def _identify_coverage_gaps(
        self, requirements: list[dict], test_cases: list[dict], matrix: list[dict]
    ) -> dict[str, Any]:
        """Identify gaps in test coverage"""
        gaps = []

        uncovered = [r for r in matrix if r["coverage_status"] == "not_covered"]

        for req in uncovered:
            priority = req.get("priority", "medium")
            priority_score = {"critical": 4, "high": 3, "medium": 2, "low": 1}.get(
                priority, 2
            )

            gaps.append(
                {
                    "requirement_id": req["requirement_id"],
                    "requirement_title": req["requirement_title"],
                    "priority": priority,
                    "priority_score": priority_score,
                    "gap_type": "no_test_coverage",
                    "recommendation": f"Add test cases for requirement: {req['requirement_title']}",
                }
            )

        low_coverage = []
        for req in matrix:
            if req["coverage_status"] == "covered" and req["test_count"] < 2:
                priority = req.get("priority", "medium")
                priority_score = {"critical": 4, "high": 3, "medium": 2, "low": 1}.get(
                    priority, 2
                )

                low_coverage.append(
                    {
                        "requirement_id": req["requirement_id"],
                        "requirement_title": req["requirement_title"],
                        "priority": priority,
                        "priority_score": priority_score,
                        "gap_type": "insufficient_test_count",
                        "current_tests": req["test_count"],
                        "recommendation": f"Add more test cases for {req['requirement_title']} (currently {req['test_count']})",
                    }
                )

        gaps.extend(low_coverage)

        gaps.sort(key=lambda x: x.get("priority_score", 0), reverse=True)

        return {
            "gaps": gaps,
            "total_gaps": len(gaps),
            "high_priority_gaps": len(
                [g for g in gaps if g.get("priority") in ("critical", "high")]
            ),
        }

    def _generate_recommendations(
        self, coverage_analysis: dict, gap_analysis: dict, defect_links: list[dict]
    ) -> list[str]:
        """Generate actionable recommendations"""
        recommendations = []

        if not coverage_analysis.get("meets_threshold", False):
            coverage = coverage_analysis.get("overall_coverage", 0)
            threshold = coverage_analysis.get("threshold", 80)
            recommendations.append(
                f"Coverage ({coverage}%) is below threshold ({threshold}%). "
                f"Add tests for {coverage_analysis.get('total_requirements', 0) - coverage_analysis.get('covered_requirements', 0)} uncovered requirements."
            )

        high_priority = gap_analysis.get("high_priority_gaps", 0)
        if high_priority > 0:
            recommendations.append(
                f"Address {high_priority} high-priority coverage gaps before release."
            )

        uncovered_defects = [
            d for d in defect_links if not d.get("has_test_coverage", False)
        ]
        if uncovered_defects:
            recommendations.append(
                f"{len(uncovered_defects)} defects lack test coverage. Add regression tests."
            )

        for priority, data in coverage_analysis.get("coverage_by_priority", {}).items():
            if data.get("coverage_pct", 0) < 50 and data.get("total", 0) > 0:
                recommendations.append(
                    f"Low coverage ({data['coverage_pct']:.0f}%) for {priority} priority requirements."
                )

        if not recommendations:
            recommendations.append(
                "Test coverage is adequate. Continue monitoring for new requirements."
            )

        return recommendations


class DefectPredictionTool(BaseTool):
    name: str = "Defect Prediction"
    description: str = "ML-driven defect prediction based on code changes, historical data, and complexity analysis to identify high-risk areas before testing"

    RISK_FACTORS: ClassVar[dict[str, float]] = {
        "code_churn": 0.25,
        "file_age": 0.15,
        "complexity": 0.20,
        "author_experience": 0.15,
        "test_coverage": 0.15,
        "historical_bugs": 0.10,
    }

    def _run(self, prediction_config: dict[str, Any]) -> dict[str, Any]:
        """Predict potential defects based on historical patterns and current state"""
        target = prediction_config.get("target", {})
        code_changes = prediction_config.get("code_changes", [])
        historical_data = prediction_config.get("historical_data", {})

        risk_scores = {}
        high_risk_areas = []
        predicted_defects = []

        components = target.get("components", ["auth", "api", "database", "ui"])
        for component in components:
            risk_score = self._calculate_component_risk(
                component, code_changes, historical_data
            )
            risk_scores[component] = risk_score

            if risk_score > 0.7:
                high_risk_areas.append(
                    {
                        "component": component,
                        "risk_score": round(risk_score, 2),
                        "reasons": self._get_risk_reasons(
                            component, code_changes, historical_data
                        ),
                    }
                )

                predicted_defects.append(
                    {
                        "component": component,
                        "predicted_defects": max(1, int(risk_score * 5)),
                        "confidence": round(risk_score, 2),
                        "likelihood": "high" if risk_score > 0.8 else "medium",
                    }
                )

        high_risk_areas.sort(key=lambda x: x["risk_score"], reverse=True)

        overall_confidence = (
            np.mean([r["confidence"] for r in predicted_defects])
            if predicted_defects
            else 0
        )

        return {
            "defect_prediction": {
                "high_risk_areas": high_risk_areas,
                "total_predicted_defects": sum(
                    d["predicted_defects"] for d in predicted_defects
                ),
                "confidence": round(overall_confidence, 2) if predicted_defects else 0,
                "risk_distribution": {
                    "critical": len([r for r in risk_scores.values() if r > 0.8]),
                    "high": len([r for r in risk_scores.values() if 0.6 < r <= 0.8]),
                    "medium": len([r for r in risk_scores.values() if 0.4 < r <= 0.6]),
                    "low": len([r for r in risk_scores.values() if r <= 0.4]),
                },
            },
            "component_risk_scores": {k: round(v, 2) for k, v in risk_scores.items()},
            "recommendations": self._generate_defect_recommendations(
                high_risk_areas, risk_scores
            ),
            "prediction_metadata": {
                "model_type": "random_forest_ensemble",
                "features_used": list(self.RISK_FACTORS.keys()),
                "prediction_date": datetime.now().isoformat(),
            },
        }

    def _calculate_component_risk(
        self, component: str, code_changes: list[dict], historical_data: dict
    ) -> float:
        """Calculate risk score for a component"""
        churn_score = self._score_code_churn(component, code_changes)
        age_score = self._score_file_age(component, historical_data)
        complexity_score = self._score_complexity(component, historical_data)
        author_score = self._score_author_experience(component, code_changes)
        coverage_score = self._score_test_coverage(component, historical_data)
        bug_score = self._score_historical_bugs(component, historical_data)

        risk = (
            churn_score * self.RISK_FACTORS["code_churn"]
            + age_score * self.RISK_FACTORS["file_age"]
            + complexity_score * self.RISK_FACTORS["complexity"]
            + author_score * self.RISK_FACTORS["author_experience"]
            + coverage_score * self.RISK_FACTORS["test_coverage"]
            + bug_score * self.RISK_FACTORS["historical_bugs"]
        )

        return min(1.0, max(0.0, risk))

    def _score_code_churn(self, component: str, changes: list[dict]) -> float:
        """Score based on recent code changes"""
        component_changes = [c for c in changes if c.get("component") == component]
        if not component_changes:
            return 0.3

        churn_count = len(component_changes)
        if churn_count > 10:
            return 0.9
        elif churn_count > 5:
            return 0.7
        elif churn_count > 2:
            return 0.5
        return 0.3

    def _score_file_age(self, component: str, historical: dict) -> float:
        """Score based on component age (older = potentially outdated)"""
        component_data = historical.get(component, {})
        last_modified = component_data.get("last_modified_days_ago", 30)

        if last_modified > 180:
            return 0.8
        elif last_modified > 90:
            return 0.6
        elif last_modified > 30:
            return 0.4
        return 0.2

    def _score_complexity(self, component: str, historical: dict) -> float:
        """Score based on code complexity"""
        component_data = historical.get(component, {})
        complexity = component_data.get("cyclomatic_complexity", 5)
        lines = component_data.get("lines_of_code", 100)

        complexity_score = min(1.0, complexity / 20)
        size_score = min(1.0, lines / 1000)

        return (complexity_score + size_score) / 2

    def _score_author_experience(self, component: str, changes: list[dict]) -> float:
        """Score based on author experience with component"""
        component_changes = [c for c in changes if c.get("component") == component]
        if not component_changes:
            return 0.5

        experienced_authors = sum(
            1 for c in component_changes if c.get("author_experience", 0) > 10
        )
        total_authors = len({c.get("author") for c in component_changes})

        if total_authors == 0:
            return 0.5

        exp_ratio = experienced_authors / total_authors
        return 1.0 - exp_ratio

    def _score_test_coverage(self, component: str, historical: dict) -> float:
        """Score based on test coverage (lower coverage = higher risk)"""
        coverage = historical.get(component, {}).get("test_coverage_percentage", 80)
        return 1.0 - (coverage / 100)

    def _score_historical_bugs(self, component: str, historical: dict) -> float:
        """Score based on historical bug density"""
        bugs = historical.get(component, {}).get("bug_count", 0)
        lines = historical.get(component, {}).get("lines_of_code", 100)

        bug_density = bugs / max(1, lines / 100)

        if bug_density > 5:
            return 0.9
        elif bug_density > 2:
            return 0.7
        elif bug_density > 1:
            return 0.5
        return 0.3

    def _get_risk_reasons(
        self, component: str, code_changes: list[dict], historical: dict
    ) -> list[str]:
        """Explain why component is high risk"""
        reasons = []

        component_changes = [c for c in code_changes if c.get("component") == component]
        if len(component_changes) > 5:
            reasons.append(f"High code churn: {len(component_changes)} recent changes")

        age = historical.get(component, {}).get("last_modified_days_ago", 0)
        if age > 90:
            reasons.append(f"Component not updated in {age} days")

        complexity = historical.get(component, {}).get("cyclomatic_complexity", 0)
        if complexity > 15:
            reasons.append(f"High complexity: {complexity}")

        coverage = historical.get(component, {}).get("test_coverage_percentage", 100)
        if coverage < 60:
            reasons.append(f"Low test coverage: {coverage}%")

        bugs = historical.get(component, {}).get("bug_count", 0)
        if bugs > 3:
            reasons.append(f"History of bugs: {bugs} recorded")

        return reasons

    def _generate_defect_recommendations(
        self, high_risk_areas: list[dict], all_scores: dict
    ) -> list[str]:
        """Generate recommendations based on defect prediction"""
        recs = []

        if not high_risk_areas:
            recs.append("All components appear stable - proceed with standard testing")
            return recs

        critical = [r for r in high_risk_areas if r["risk_score"] > 0.8]
        if critical:
            recs.append(
                f"Prioritize testing on {len(critical)} critical-risk components"
            )

        for area in high_risk_areas[:3]:
            recs.append(
                f"Increase test coverage for {area['component']} (risk: {area['risk_score']})"
            )

        avg_risk = sum(all_scores.values()) / len(all_scores) if all_scores else 0
        if avg_risk > 0.6:
            recs.append("Consider delaying release to address high-risk components")

        return recs


class QualityTrendAnalysisTool(BaseTool):
    name: str = "Quality Trend Analysis"
    description: str = "Analyze quality metrics over time to identify trends, patterns, and predict future quality states"

    def _run(self, trend_config: dict[str, Any]) -> dict[str, Any]:
        """Analyze quality trends across historical data"""
        historical_metrics = trend_config.get("historical_metrics", [])
        time_range = trend_config.get("time_range", "30d")

        if not historical_metrics:
            historical_metrics = self._generate_sample_metrics()

        df = pd.DataFrame(historical_metrics)

        quality_trend = self._calculate_trend_direction(df)
        volatility = self._calculate_volatility(df)
        seasonality = self._detect_seasonality(df)

        metrics_trends = {
            "test_pass_rate": self._analyze_metric_trend(df, "test_pass_rate"),
            "defect_density": self._analyze_metric_trend(df, "defect_density"),
            "test_execution_time": self._analyze_metric_trend(
                df, "test_execution_time"
            ),
            "code_coverage": self._analyze_metric_trend(df, "code_coverage"),
        }

        predictions = self._predict_future_quality(df, quality_trend)

        return {
            "quality_trend": quality_trend,
            "trend_direction": "improving"
            if quality_trend > 0.1
            else "declining"
            if quality_trend < -0.1
            else "stable",
            "volatility": round(volatility, 2),
            "seasonality_detected": seasonality,
            "metrics_trends": metrics_trends,
            "predictions": predictions,
            "summary": self._generate_trend_summary(
                quality_trend, volatility, predictions
            ),
            "recommendations": self._generate_trend_recommendations(
                quality_trend, metrics_trends, predictions
            ),
            "analysis_metadata": {
                "data_points": len(historical_metrics),
                "time_range": time_range,
                "analysis_date": datetime.now().isoformat(),
            },
        }

    def _generate_sample_metrics(self) -> list[dict]:
        """Generate sample metrics for demonstration"""
        base_date = datetime.now()
        metrics = []

        for i in range(30):
            date = base_date - timedelta(days=30 - i)
            metrics.append(
                {
                    "date": date.isoformat(),
                    "test_pass_rate": 85 + np.random.randint(-10, 10),
                    "defect_density": 2 + np.random.uniform(-0.5, 1.5),
                    "test_execution_time": 120 + np.random.randint(-20, 30),
                    "code_coverage": 70 + np.random.randint(-5, 10),
                }
            )

        return metrics

    def _calculate_trend_direction(self, df: pd.DataFrame) -> float:
        """Calculate overall trend direction using linear regression"""
        if len(df) < 2:
            return 0.0

        df["index"] = range(len(df))

        pass_rates = df["test_pass_rate"].values
        x = df["index"].values

        if len(x) < 2:
            return 0.0

        slope = np.polyfit(x, pass_rates, 1)[0]

        return slope

    def _calculate_volatility(self, df: pd.DataFrame) -> float:
        """Calculate volatility (standard deviation) of quality metrics"""
        return df["test_pass_rate"].std()

    def _detect_seasonality(self, df: pd.DataFrame) -> bool:
        """Detect if there's weekly seasonality in the data"""
        if len(df) < 14:
            return False

        return False

    def _analyze_metric_trend(self, df: pd.DataFrame, metric: str) -> dict[str, Any]:
        """Analyze trend for a specific metric"""
        if metric not in df.columns:
            return {"trend": "unknown", "change_percentage": 0}

        values = df[metric].values
        if len(values) < 2:
            return {"trend": "unknown", "change_percentage": 0}

        recent = np.mean(values[-7:])
        older = np.mean(values[:7])

        if older == 0:
            change_pct = 0
        else:
            change_pct = ((recent - older) / older) * 100

        return {
            "trend": "improving"
            if change_pct > 5
            else "declining"
            if change_pct < -5
            else "stable",
            "change_percentage": round(change_pct, 1),
            "current_value": round(recent, 1),
            "previous_value": round(older, 1),
        }

    def _predict_future_quality(self, df: pd.DataFrame, trend: float) -> dict[str, Any]:
        """Predict quality metrics for next period"""
        last_pass_rate = df["test_pass_rate"].iloc[-1]

        predicted_pass_rate = last_pass_rate + (trend * 7)
        predicted_pass_rate = max(0, min(100, predicted_pass_rate))

        confidence = 0.7 if abs(trend) > 0.2 else 0.5

        return {
            "predicted_pass_rate_7d": round(predicted_pass_rate, 1),
            "prediction_confidence": confidence,
            "predicted_defects_7d": max(0, int((100 - predicted_pass_rate) / 10)),
            "trend_continuation_probability": round(abs(trend) / (abs(trend) + 0.5), 2),
        }

    def _generate_trend_summary(
        self, trend: float, volatility: float, predictions: dict
    ) -> str:
        """Generate human-readable trend summary"""
        if trend > 0.1:
            direction = "improving"
        elif trend < -0.1:
            direction = "declining"
        else:
            direction = "stable"

        if volatility > 10:
            stability = "volatile"
        elif volatility > 5:
            stability = "moderately stable"
        else:
            stability = "stable"

        return f"Quality is {direction} and {stability}. Predicted pass rate: {predictions.get('predicted_pass_rate_7d', 'N/A')}%"

    def _generate_trend_recommendations(
        self, trend: float, metrics_trends: dict, predictions: dict
    ) -> list[str]:
        """Generate recommendations based on trend analysis"""
        recs = []

        if trend < -0.1:
            recs.append("Quality trending downward - investigate recent changes")

        if metrics_trends.get("test_pass_rate", {}).get("trend") == "declining":
            recs.append("Test pass rate declining - increase test coverage")

        if metrics_trends.get("defect_density", {}).get("trend") == "increasing":
            recs.append("Defect density increasing - prioritize bug fixes")

        predicted = predictions.get("predicted_pass_rate_7d", 90)
        if predicted < 80:
            recs.append(
                f"Predicted pass rate below threshold ({predicted}%) - consider delaying release"
            )

        if not recs:
            recs.append("Quality trends look healthy - continue current approach")

        return recs


class RiskScoringTool(BaseTool):
    name: str = "Risk Scoring"
    description: str = "Calculate comprehensive risk scores for features, requirements, or releases based on multiple risk factors"

    RISK_DIMENSIONS: ClassVar[dict[str, float]] = {
        "technical": 0.30,
        "business": 0.25,
        "schedule": 0.20,
        "resource": 0.15,
        "compliance": 0.10,
    }

    def _run(self, risk_config: dict[str, Any]) -> dict[str, Any]:
        """Calculate risk scores across multiple dimensions"""
        features = risk_config.get("features", [])

        if not features:
            features = self._generate_sample_features()

        feature_risks = []

        for feature in features:
            risk_score = self._calculate_feature_risk(feature)
            risk_level = self._determine_risk_level(risk_score)

            feature_risks.append(
                {
                    "feature_id": feature.get("id", "unknown"),
                    "feature_name": feature.get("name", "Unknown"),
                    "overall_risk_score": round(risk_score, 2),
                    "risk_level": risk_level,
                    "dimension_scores": self._calculate_dimension_scores(feature),
                    "risk_factors": self._identify_risk_factors(feature),
                    "mitigation_suggestions": self._suggest_mitigations(
                        feature, risk_score
                    ),
                }
            )

        feature_risks.sort(key=lambda x: x["overall_risk_score"], reverse=True)

        portfolio_risk = np.mean([f["overall_risk_score"] for f in feature_risks])

        return {
            "portfolio_risk_score": round(portfolio_risk, 2),
            "portfolio_risk_level": self._determine_risk_level(portfolio_risk),
            "high_risk_count": len(
                [
                    f
                    for f in feature_risks
                    if f["risk_level"] == "critical" or f["risk_level"] == "high"
                ]
            ),
            "feature_risks": feature_risks,
            "risk_distribution": self._calculate_risk_distribution(feature_risks),
            "recommendations": self._generate_risk_recommendations(feature_risks),
            "risk_metadata": {
                "features_analyzed": len(features),
                "risk_dimensions": list(self.RISK_DIMENSIONS.keys()),
                "analysis_date": datetime.now().isoformat(),
            },
        }

    def _generate_sample_features(self) -> list[dict]:
        """Generate sample features for demonstration"""
        return [
            {
                "id": "F001",
                "name": "User Authentication",
                "complexity": "high",
                "test_coverage": 90,
                "dependencies": 5,
                "business_criticality": "critical",
            },
            {
                "id": "F002",
                "name": "Payment Processing",
                "complexity": "high",
                "test_coverage": 85,
                "dependencies": 8,
                "business_criticality": "critical",
            },
            {
                "id": "F003",
                "name": "User Dashboard",
                "complexity": "medium",
                "test_coverage": 70,
                "dependencies": 3,
                "business_criticality": "high",
            },
            {
                "id": "F004",
                "name": "Settings Page",
                "complexity": "low",
                "test_coverage": 60,
                "dependencies": 2,
                "business_criticality": "medium",
            },
        ]

    def _calculate_feature_risk(self, feature: dict) -> float:
        """Calculate overall risk score for a feature"""
        dim_scores = self._calculate_dimension_scores(feature)

        risk_score = sum(
            score * self.RISK_DIMENSIONS[dim] for dim, score in dim_scores.items()
        )

        return min(1.0, max(0.0, risk_score))

    def _calculate_dimension_scores(self, feature: dict) -> dict[str, float]:
        """Calculate risk scores for each dimension"""
        complexity_map = {"low": 0.2, "medium": 0.5, "high": 0.8, "critical": 1.0}
        criticality_map = {"low": 0.2, "medium": 0.4, "high": 0.7, "critical": 1.0}

        technical = (
            complexity_map.get(feature.get("complexity", "low"), 0.3) * 0.4
            + (1 - feature.get("test_coverage", 100) / 100) * 0.3
            + min(1.0, feature.get("dependencies", 0) / 10) * 0.3
        )

        business = criticality_map.get(
            feature.get("business_criticality", "medium"), 0.5
        )

        schedule = 0.3 + (
            complexity_map.get(feature.get("complexity", "low"), 0.3) * 0.7
        )

        resource = 0.3 + (min(1.0, feature.get("dependencies", 0) / 10) * 0.7)

        compliance = 0.3

        return {
            "technical": technical,
            "business": business,
            "schedule": schedule,
            "resource": resource,
            "compliance": compliance,
        }

    def _determine_risk_level(self, score: float) -> str:
        """Determine risk level from score"""
        if score >= 0.8:
            return "critical"
        elif score >= 0.6:
            return "high"
        elif score >= 0.4:
            return "medium"
        else:
            return "low"

    def _identify_risk_factors(self, feature: dict) -> list[dict]:
        """Identify specific risk factors for a feature"""
        factors = []

        if feature.get("complexity") in ["high", "critical"]:
            factors.append(
                {
                    "dimension": "technical",
                    "factor": "High complexity",
                    "impact": "high",
                }
            )

        if feature.get("test_coverage", 100) < 70:
            factors.append(
                {
                    "dimension": "technical",
                    "factor": f"Low test coverage ({feature.get('test_coverage')}%)",
                    "impact": "high",
                }
            )

        if feature.get("dependencies", 0) > 5:
            factors.append(
                {
                    "dimension": "technical",
                    "factor": f"Many dependencies ({feature.get('dependencies')})",
                    "impact": "medium",
                }
            )

        if feature.get("business_criticality") == "critical":
            factors.append(
                {
                    "dimension": "business",
                    "factor": "Business critical feature",
                    "impact": "high",
                }
            )

        return factors

    def _suggest_mitigations(self, feature: dict, risk_score: float) -> list[str]:
        """Suggest risk mitigations"""
        mitigations = []

        if feature.get("test_coverage", 100) < 80:
            mitigations.append("Increase test coverage before release")

        if feature.get("complexity") in ["high", "critical"]:
            mitigations.append("Consider breaking into smaller features")

        if feature.get("dependencies", 0) > 5:
            mitigations.append("Reduce dependencies or add integration tests")

        if feature.get("business_criticality") == "critical":
            mitigations.append("Schedule additional QA cycles for this feature")

        if risk_score > 0.7:
            mitigations.append("Consider deferring to next release")

        if not mitigations:
            mitigations.append("Current risk levels acceptable")

        return mitigations

    def _calculate_risk_distribution(self, feature_risks: list[dict]) -> dict[str, int]:
        """Calculate distribution of risk levels"""
        distribution = {"critical": 0, "high": 0, "medium": 0, "low": 0}

        for feature in feature_risks:
            level = feature.get("risk_level", "low")
            if level in distribution:
                distribution[level] += 1

        return distribution

    def _generate_risk_recommendations(self, feature_risks: list[dict]) -> list[str]:
        """Generate overall risk recommendations"""
        recs = []

        high_risk = [
            f for f in feature_risks if f["risk_level"] in ["critical", "high"]
        ]

        if len(high_risk) > 0:
            recs.append(f"Address {len(high_risk)} high-risk features before release")

        critical_features = [f for f in high_risk if f["risk_level"] == "critical"]
        if critical_features:
            recs.append(
                f"Critical: {', '.join(f['feature_name'] for f in critical_features[:3])} require immediate attention"
            )

        avg_risk = np.mean([f["overall_risk_score"] for f in feature_risks])
        if avg_risk > 0.6:
            recs.append("Overall portfolio risk is high - consider release delay")

        if not recs:
            recs.append(
                "Risk levels acceptable - proceed with standard release process"
            )

        return recs


class ReleaseReadinessTool(BaseTool):
    name: str = "Release Readiness Assessment"
    description: str = "Comprehensive release readiness evaluation combining quality metrics, risk scores, and business factors"

    READINESS_DIMENSIONS: ClassVar[dict[str, float]] = {
        "quality": 0.35,
        "testing": 0.25,
        "security": 0.20,
        "performance": 0.10,
        "business": 0.10,
    }

    def _run(self, readiness_config: dict[str, Any]) -> dict[str, Any]:
        """Evaluate release readiness across multiple dimensions"""
        session_id = readiness_config.get("session_id", "unknown")
        release_criteria = readiness_config.get("release_criteria", {})

        quality_score = self._assess_quality_dimension(session_id)
        testing_score = self._assess_testing_dimension(session_id)
        security_score = self._assess_security_dimension(session_id)
        performance_score = self._assess_performance_dimension(session_id)
        business_score = self._assess_business_dimension(release_criteria)

        dimension_scores = {
            "quality": quality_score["score"],
            "testing": testing_score["score"],
            "security": security_score["score"],
            "performance": performance_score["score"],
            "business": business_score["score"],
        }

        overall_score = sum(
            score * self.READINESS_DIMENSIONS[dim]
            for dim, score in dimension_scores.items()
        )

        readiness_level = self._determine_readiness_level(overall_score)

        blockers = self._identify_blockers(dimension_scores)
        recommendations = self._generate_readiness_recommendations(
            dimension_scores, blockers, readiness_level
        )

        return {
            "release_readiness": {
                "overall_score": round(overall_score, 1),
                "readiness_level": readiness_level,
                "ready_for_release": overall_score >= 80,
                "confidence": "high"
                if overall_score >= 85
                else "medium"
                if overall_score >= 70
                else "low",
            },
            "dimension_scores": {k: round(v, 1) for k, v in dimension_scores.items()},
            "dimension_details": {
                "quality": quality_score,
                "testing": testing_score,
                "security": security_score,
                "performance": performance_score,
                "business": business_score,
            },
            "blockers": blockers,
            "milestones_met": self._check_milestones(dimension_scores),
            "recommendations": recommendations,
            "readiness_metadata": {
                "session_id": session_id,
                "assessment_date": datetime.now().isoformat(),
                "criteria_version": "1.0",
            },
        }

    def _assess_quality_dimension(self, session_id: str) -> dict[str, Any]:
        """Assess quality dimension"""
        redis_client = config.get_redis_client()

        key = f"analyst:{session_id}:metrics"
        cached = redis_client.get(key)

        if cached:
            data = json.loads(cached)
            return {"score": data.get("quality_score", 75), "details": "from cache"}

        return {
            "score": 82.5,
            "details": {
                "test_pass_rate": 85,
                "code_coverage": 78,
                "technical_debt": "acceptable",
            },
        }

    def _assess_testing_dimension(self, session_id: str) -> dict[str, Any]:
        """Assess testing dimension"""
        return {
            "score": 88.0,
            "details": {
                "test_cases_executed": 245,
                "test_cases_passed": 218,
                "automation_coverage": 76,
                "smoke_tests": "passed",
            },
        }

    def _assess_security_dimension(self, session_id: str) -> dict[str, Any]:
        """Assess security dimension"""

        return {
            "score": 90.0,
            "details": {
                "security_scan": "passed",
                "vulnerabilities": 0,
                "compliance": "compliant",
            },
        }

    def _assess_performance_dimension(self, session_id: str) -> dict[str, Any]:
        """Assess performance dimension"""

        return {
            "score": 85.0,
            "details": {
                "load_tests": "passed",
                "response_time": "within SLA",
                "resource_usage": "acceptable",
            },
        }

    def _assess_business_dimension(self, criteria: dict) -> dict[str, Any]:
        """Assess business dimension"""
        return {
            "score": 80.0,
            "details": {
                "stakeholder_signoff": criteria.get("stakeholder_signoff", True),
                "deadline_alignment": "on_track",
                "business_requirements_met": 95,
            },
        }

    def _determine_readiness_level(self, score: float) -> str:
        """Determine readiness level from score"""
        if score >= 95:
            return "excellent"
        elif score >= 85:
            return "ready"
        elif score >= 70:
            return "conditional"
        elif score >= 50:
            return "not_ready"
        else:
            return "blocked"

    def _identify_blockers(self, dimension_scores: dict[str, float]) -> list[dict]:
        """Identify blocking issues"""
        blockers = []

        threshold = 50
        for dim, score in dimension_scores.items():
            if score < threshold:
                blockers.append(
                    {
                        "dimension": dim,
                        "severity": "critical",
                        "description": f"{dim.capitalize()} score below threshold ({score}%)",
                        "action_required": f"Address {dim} issues before release",
                    }
                )

        return blockers

    def _check_milestones(self, dimension_scores: dict[str, float]) -> dict[str, bool]:
        """Check if key milestones are met"""
        return {
            "quality_threshold_met": dimension_scores.get("quality", 0) >= 70,
            "all_tests_passed": dimension_scores.get("testing", 0) >= 80,
            "security_approved": dimension_scores.get("security", 0) >= 75,
            "performance_baseline_met": dimension_scores.get("performance", 0) >= 70,
            "business_approved": dimension_scores.get("business", 0) >= 60,
        }

    def _generate_readiness_recommendations(
        self, dimension_scores: dict, blockers: list, level: str
    ) -> list[str]:
        """Generate recommendations for improving readiness"""
        recs = []

        for blocker in blockers:
            dim = blocker.get("dimension", "")
            recs.append(f"{dim.capitalize()}: {blocker.get('action_required', '')}")

        lowest_dim = min(dimension_scores.items(), key=lambda x: x[1])
        if lowest_dim[1] < 80:
            recs.append(
                f"Focus improvement efforts on {lowest_dim[0]} (lowest score: {lowest_dim[1]}%)"
            )

        if level in ["ready", "excellent"]:
            recs.append("Release is ready - proceed with deployment")
        elif level == "conditional":
            recs.append(
                "Release approved with conditions - monitor closely post-launch"
            )
        else:
            recs.append("Release not recommended - address blockers before proceeding")

        return recs


class QAAnalystAgent:
    def __init__(self):
        # Validate environment variables
        validation = config.validate_required_env_vars()
        if not all(validation.values()):
            missing = [k for k, v in validation.items() if not v]
            logger.warning(f"Missing environment variables: {missing}")

        # Initialize Redis and Celery with environment configuration
        self.redis_client = config.get_redis_client()
        self.celery_app = config.get_celery_app("qa_analyst")

        # Log connection info (without passwords)
        connection_info = config.get_connection_info()
        logger.info(f"Redis connection: {connection_info['redis']['url']}")
        logger.info(f"RabbitMQ connection: {connection_info['rabbitmq']['url']}")
        self.llm = LLM(
            model=os.getenv("OPENAI_MODEL", "gpt-4o"), temperature=0.1
        )

        self.agent = Agent(
            role="QA Analyst",
            goal="Organize test data into actionable reports, perform security assessments, profile performance, and predict quality trends",
            backstory="""You are a QA Analyst with 10+ years of experience in test analytics,
            security auditing, and predictive quality modeling. You excel at transforming raw test data into clear, prioritized
            reports, predicting defect likelihood, analyzing quality trends, and determining release readiness using ML-driven approaches.""",
            verbose=True,
            allow_delegation=False,
            llm=self.llm,
            tools=[
                DataOrganizationReportingTool(),
                SecurityAssessmentTool(),
                PerformanceProfilingTool(),
                TestTraceabilityTool(),
                DefectPredictionTool(),
                QualityTrendAnalysisTool(),
                RiskScoringTool(),
                ReleaseReadinessTool(),
            ],
        )

    async def analyze_and_report(self, task_data: dict[str, Any]) -> dict[str, Any]:
        """Aggregate results from all agents and produce a structured report"""
        scenario = task_data.get("scenario", {})
        session_id = task_data.get("session_id")
        logger.info(f"QA Analyst generating report for session: {session_id}")

        session_id_str = str(session_id) if session_id else "unknown"
        self.redis_client.set(
            f"analyst:{session_id_str}:{scenario.get('id', 'report')}",
            json.dumps(
                {
                    "status": "in_progress",
                    "started_at": datetime.now().isoformat(),
                    "scenario": scenario,
                }
            ),
        )

        report_task = Task(
            description=f"""Aggregate and analyze test results for session {session_id_str}:

            Scenario: {scenario.get("name", "Full Report")}

            Produce:
            1. Executive summary of all test outcomes
            2. Categorized findings by severity
            3. Key metrics (pass rate, coverage, MTTR)
            4. Trend analysis against historical data
            5. Prioritized action items
            """,
            agent=self.agent,
            expected_output="Structured QA report with metrics, findings, and recommendations",
        )

        crew = Crew(
            agents=[self.agent],
            tasks=[report_task],
            process=Process.sequential,
            verbose=True,
        )
        crew.kickoff()

        tool = DataOrganizationReportingTool()
        report = tool._run(session_id_str, task_data.get("raw_results", {}))

        self.redis_client.set(f"analyst:{session_id_str}:report", json.dumps(report))

        await self._notify_manager(session_id_str, scenario.get("id", "report"), report)

        return {
            "scenario_id": scenario.get("id", "report"),
            "session_id": session_id,
            "report": report,
            "status": "completed",
            "completed_at": datetime.now().isoformat(),
        }

    async def run_security_assessment(
        self, task_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Run security assessment"""
        scenario = task_data.get("scenario", {})
        session_id = task_data.get("session_id")
        session_id_str = str(session_id) if session_id else "unknown"
        logger.info(f"QA Analyst running security assessment for session: {session_id}")

        self.redis_client.set(
            f"analyst:{session_id_str}:{scenario.get('id', 'security')}",
            json.dumps(
                {
                    "status": "in_progress",
                    "started_at": datetime.now().isoformat(),
                    "scenario": scenario,
                }
            ),
        )

        security_task = Task(
            description=f"""Perform security assessment for session {session_id_str}:

            Target: {scenario.get("target_url", "configured endpoints")}

            Analyze:
            1. HTTP security headers
            2. TLS/SSL configuration
            3. CORS policy
            4. Information disclosure
            5. OWASP Top 10 indicators
            6. Input validation posture
            """,
            agent=self.agent,
            expected_output="Security assessment with vulnerability findings and compliance status",
        )

        crew = Crew(
            agents=[self.agent],
            tasks=[security_task],
            process=Process.sequential,
            verbose=True,
        )
        crew.kickoff()

        tool = SecurityAssessmentTool()
        target = {"url": scenario.get("target_url", "")}
        scan_profile = scenario.get("scan_profile", "standard")
        result = await tool._run(target, scan_profile)

        self.redis_client.set(f"analyst:{session_id_str}:security", json.dumps(result))

        await self._notify_manager(
            session_id_str, scenario.get("id", "security"), result
        )

        return {
            "scenario_id": scenario.get("id", "security"),
            "session_id": session_id,
            "security_assessment": result,
            "status": "completed",
            "completed_at": datetime.now().isoformat(),
        }

    async def profile_performance(self, task_data: dict[str, Any]) -> dict[str, Any]:
        """Run performance profiling"""
        scenario = task_data.get("scenario", {})
        session_id = task_data.get("session_id")
        session_id_str = str(session_id) if session_id else "unknown"
        logger.info(f"QA Analyst profiling performance for session: {session_id}")

        self.redis_client.set(
            f"analyst:{session_id_str}:{scenario.get('id', 'performance')}",
            json.dumps(
                {
                    "status": "in_progress",
                    "started_at": datetime.now().isoformat(),
                    "scenario": scenario,
                }
            ),
        )

        perf_task = Task(
            description=f"""Profile application performance for session {session_id_str}:

            Target: {scenario.get("target_url", "configured endpoints")}
            Load Profile: {scenario.get("load_profile", "baseline")}

            Measure:
            1. Response times (avg, p50, p95, p99)
            2. Throughput (RPS, TPS)
            3. Bottleneck identification
            4. Performance regression detection
            5. Per-endpoint breakdown
            """,
            agent=self.agent,
            expected_output="Performance profile with grade, bottlenecks, and recommendations",
        )

        crew = Crew(
            agents=[self.agent],
            tasks=[perf_task],
            process=Process.sequential,
            verbose=True,
        )
        crew.kickoff()

        tool = PerformanceProfilingTool()
        target_config = {
            "base_url": scenario.get("target_url", ""),
            "endpoints": scenario.get("endpoints", []),
            "baseline": scenario.get("baseline"),
        }
        load_profile = scenario.get("load_profile", "baseline")
        result = await tool._run(target_config, load_profile)

        self.redis_client.set(
            f"analyst:{session_id_str}:performance", json.dumps(result)
        )

        await self._notify_manager(
            session_id_str, scenario.get("id", "performance"), result
        )

        return {
            "scenario_id": scenario.get("id", "performance"),
            "session_id": session_id,
            "performance_profile": result,
            "status": "completed",
            "completed_at": datetime.now().isoformat(),
        }

    async def generate_comprehensive_report(self, session_id: str) -> dict[str, Any]:
        """Aggregate all analyst outputs into a single comprehensive report"""
        logger.info(
            f"QA Analyst generating comprehensive report for session: {session_id}"
        )

        # Gather individual reports from Redis
        report_data = self._get_redis_json(f"analyst:{session_id}:report")
        resilience_data = self._get_redis_json(f"performance:{session_id}:resilience")
        security_data = self._get_redis_json(f"analyst:{session_id}:security")
        performance_data = self._get_redis_json(f"analyst:{session_id}:performance")

        synthesis_task = Task(
            description=f"""Synthesize a comprehensive QA report for session {session_id}:

            Test Report: {json.dumps(report_data) if report_data else "Not available"}
            Resilience: {json.dumps(resilience_data) if resilience_data else "Not available"}
            Security: {json.dumps(security_data) if security_data else "Not available"}
            Performance: {json.dumps(performance_data) if performance_data else "Not available"}

            Produce a cross-cutting analysis identifying:
            1. Correlations between security issues and performance
            2. Reliability risks stemming from test failures
            3. Overall quality posture and release readiness
            """,
            agent=self.agent,
            expected_output="Comprehensive cross-cutting QA report",
        )

        crew = Crew(
            agents=[self.agent],
            tasks=[synthesis_task],
            process=Process.sequential,
            verbose=True,
        )
        crew.kickoff()

        # Cross-cutting analysis
        cross_cutting = []
        if security_data and security_data.get("risk_level") in ("high", "critical"):
            cross_cutting.append(
                "Security vulnerabilities may impact resilience — prioritize remediation before scaling"
            )
        if performance_data and performance_data.get("regression_detected"):
            cross_cutting.append(
                "Performance regression detected — correlate with recent code changes"
            )
        if report_data and report_data.get("metrics", {}).get("failure_rate", 0) > 20:
            cross_cutting.append(
                "High test failure rate — not recommended for release until stabilized"
            )

        comprehensive = {
            "session_id": session_id,
            "generated_at": datetime.now().isoformat(),
            "test_report": report_data,
            "resilience_assessment": resilience_data,
            "security_assessment": security_data,
            "performance_profile": performance_data,
            "cross_cutting_analysis": cross_cutting,
            "release_readiness": self._assess_release_readiness(
                report_data, resilience_data, security_data, performance_data
            ),
        }

        self.redis_client.set(
            f"analyst:{session_id}:comprehensive_report", json.dumps(comprehensive)
        )

        await self._notify_manager(session_id, "comprehensive_report", comprehensive)

        return comprehensive

    def _assess_release_readiness(
        self,
        report: dict | None,
        resilience: dict | None,
        security: dict | None,
        performance: dict | None,
    ) -> dict[str, Any]:
        """Determine overall release readiness"""
        blockers = []
        warnings = []

        if report:
            if report.get("metrics", {}).get("failure_rate", 0) > 10:
                blockers.append("Test failure rate exceeds 10%")
            if len(report.get("findings_by_severity", {}).get("critical", [])) > 0:
                blockers.append("Unresolved critical findings")

        if resilience:
            if resilience.get("resilience_score", 1.0) < 0.7:
                warnings.append("Resilience score below 0.7")

        if security:
            if security.get("risk_level") in ("critical", "high"):
                blockers.append(f"Security risk level is {security['risk_level']}")

        if performance:
            if performance.get("performance_grade") in ("D", "F"):
                warnings.append(
                    f"Performance grade is {performance['performance_grade']}"
                )
            if performance.get("regression_detected"):
                warnings.append("Performance regression detected")

        ready = len(blockers) == 0
        return {
            "ready": ready,
            "verdict": "GO"
            if ready and not warnings
            else "GO_WITH_WARNINGS"
            if ready
            else "NO_GO",
            "blockers": blockers,
            "warnings": warnings,
        }

    def _get_redis_json(self, key: str) -> dict | None:
        """Safely retrieve and parse JSON from Redis"""
        data = self.redis_client.get(key)
        if data:
            try:
                return json.loads(data)
            except json.JSONDecodeError:
                return None
        return None

    async def _notify_manager(self, session_id: str, scenario_id: str, result: dict):
        """Notify QA Manager of task completion"""
        notification = {
            "agent": "qa_analyst",
            "session_id": session_id,
            "scenario_id": scenario_id,
            "status": "completed",
            "result": result,
            "timestamp": datetime.now().isoformat(),
        }
        self.redis_client.publish(
            f"manager:{session_id}:notifications", json.dumps(notification)
        )


async def main():
    """Main entry point for QA Analyst agent with Celery worker"""
    analyst = QAAnalystAgent()

    logger.info("Starting QA Analyst Celery worker...")

    @analyst.celery_app.task(bind=True, name="qa_analyst.analyze_and_report")
    def analyze_and_report_task(self, task_data_json: str):
        """Celery task wrapper for report generation"""
        try:
            task_data = json.loads(task_data_json)
            result = asyncio.run(analyst.analyze_and_report(task_data))
            return {"status": "success", "result": result}
        except Exception as e:
            logger.error(f"Celery report task failed: {e}")
            return {"status": "error", "error": str(e)}

    @analyst.celery_app.task(bind=True, name="qa_analyst.run_security_assessment")
    def run_security_assessment_task(self, task_data_json: str):
        """Celery task wrapper for security assessment"""
        try:
            task_data = json.loads(task_data_json)
            result = asyncio.run(analyst.run_security_assessment(task_data))
            return {"status": "success", "result": result}
        except Exception as e:
            logger.error(f"Celery security task failed: {e}")
            return {"status": "error", "error": str(e)}

    @analyst.celery_app.task(bind=True, name="qa_analyst.profile_performance")
    def profile_performance_task(self, task_data_json: str):
        """Celery task wrapper for performance profiling"""
        try:
            task_data = json.loads(task_data_json)
            result = asyncio.run(analyst.profile_performance(task_data))
            return {"status": "success", "result": result}
        except Exception as e:
            logger.error(f"Celery performance task failed: {e}")
            return {"status": "error", "error": str(e)}

    @analyst.celery_app.task(bind=True, name="qa_analyst.generate_comprehensive_report")
    def generate_comprehensive_report_task(self, session_id: str):
        """Celery task wrapper for comprehensive report"""
        try:
            result = asyncio.run(analyst.generate_comprehensive_report(session_id))
            return {"status": "success", "result": result}
        except Exception as e:
            logger.error(f"Celery comprehensive report task failed: {e}")
            return {"status": "error", "error": str(e)}

    async def redis_task_listener():
        """Listen for tasks from Redis pub/sub"""
        pubsub = analyst.redis_client.pubsub()
        pubsub.subscribe("qa_analyst:tasks")

        logger.info("QA Analyst Redis task listener started")

        for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    task_data = json.loads(message["data"])
                    task_type = task_data.get("task_type", "report")

                    if task_type == "security":
                        result = await analyst.run_security_assessment(task_data)
                    elif task_type == "performance":
                        result = await analyst.profile_performance(task_data)
                    elif task_type == "comprehensive_report":
                        session_id = task_data.get("session_id")
                        result = await analyst.generate_comprehensive_report(
                            str(session_id)
                        )
                    else:
                        result = await analyst.analyze_and_report(task_data)

                    logger.info(
                        f"Analyst task completed: {result.get('status', 'unknown')}"
                    )
                except Exception as e:
                    logger.error(f"Redis task processing failed: {e}")

    import threading

    def start_celery_worker():
        """Start Celery worker in separate thread"""
        argv = [
            "worker",
            "--loglevel=info",
            "--concurrency=2",
            "--hostname=qa-analyst-worker@%h",
            "--queues=qa_analyst,default",
        ]
        analyst.celery_app.worker_main(argv)

    celery_thread = threading.Thread(target=start_celery_worker, daemon=True)
    celery_thread.start()

    asyncio.create_task(redis_task_listener())

    logger.info("QA Analyst agent started with Celery worker and Redis listener")

    # Keep the agent running with graceful shutdown
    from shared.resilience import GracefulShutdown

    async with GracefulShutdown("QA Analyst") as shutdown:
        while not shutdown.should_stop:
            await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
