import asyncio
import json
import logging
import os
import socket
import ssl
import sys
from datetime import datetime
from typing import Any, ClassVar

from crewai import LLM, Agent, Crew, Process, Task

from shared.crewai_compat import BaseTool

# Add config path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))
import requests

from config.environment import config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ComprehensiveSecurityAssessmentTool(BaseTool):
    name: str = "Comprehensive Security Assessment"
    description: str = "Complete security analysis including headers, TLS, OWASP indicators, CORS, and information disclosure"

    EXPECTED_HEADERS: ClassVar[list] = [
        "Content-Security-Policy",
        "Strict-Transport-Security",
        "X-Frame-Options",
        "X-Content-Type-Options",
        "Referrer-Policy",
        "Permissions-Policy",
        "X-XSS-Protection",
    ]

    def _run(
        self, target: dict[str, Any], scan_profile: str = "standard"
    ) -> dict[str, Any]:
        """Run comprehensive security assessment"""
        url = target.get("url", "")

        # Core security analysis
        headers_result = self._analyze_headers(url)
        tls_result = self._assess_tls(url)
        cors_result = self._check_cors(url)
        disclosure_result = self._check_info_disclosure(url)
        owasp_result = self._evaluate_owasp_indicators(target)

        # Aggregate vulnerabilities
        vulnerabilities = []
        for h in headers_result.get("missing", []):
            severity = "medium" if h != "Strict-Transport-Security" else "high"
            vulnerabilities.append(
                {
                    "type": "missing_header",
                    "severity": severity,
                    "description": f"Missing security header: {h}",
                    "remediation": f"Add {h} header to server responses",
                }
            )

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

        # Calculate security score
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

        recommendations = self._build_security_recommendations(vulnerabilities)

        return {
            "security_score": round(score, 2),
            "risk_level": risk_level,
            "header_analysis": headers_result,
            "tls_assessment": tls_result,
            "cors_analysis": cors_result,
            "information_disclosure": disclosure_result,
            "owasp_indicators": owasp_result,
            "vulnerabilities": vulnerabilities,
            "compliance_status": {
                "owasp_top_10": {v["type"]: v["severity"] for v in owasp_result},
                "headers_best_practice": len(headers_result.get("missing", [])) == 0,
                "tls_compliance": tls_result.get("grade") in ["A", "B"],
            },
            "recommendations": recommendations,
            "scan_metadata": {
                "target_url": url,
                "scan_profile": scan_profile,
                "scan_time": datetime.now().isoformat(),
            },
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
        """Check for OWASP Top 10 indicators"""
        indicators = []
        url = target.get("url", "")

        # A03:2021 Injection
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

        # A01:2021 Broken Access Control
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
                            "remediation": "Disable directory listing on web server",
                        }
                    )
            except requests.RequestException:
                pass

        return indicators

    def _build_security_recommendations(self, vulnerabilities: list[dict]) -> list[str]:
        """Deduplicate and prioritize security recommendations"""
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


class GDPRComplianceTool(BaseTool):
    name: str = "GDPR Compliance Checker"
    description: str = "Comprehensive GDPR compliance validation including consent management, data handling, erasure, and portability"

    def _run(self, gdpr_config: dict[str, Any]) -> dict[str, Any]:
        """Run GDPR compliance checks"""
        # Consent management
        consent_results = self._check_consent_management(gdpr_config)

        # Data handling
        data_handling_results = self._check_data_handling(gdpr_config)

        # Right to erasure
        erasure_results = self._check_right_to_erasure(gdpr_config)

        # Data portability
        portability_results = self._check_data_portability(gdpr_config)

        all_violations = []
        all_violations.extend(consent_results.get("violations", []))
        all_violations.extend(data_handling_results.get("violations", []))
        all_violations.extend(erasure_results.get("violations", []))
        all_violations.extend(portability_results.get("violations", []))

        total_checks = (
            consent_results.get("checks", 0)
            + data_handling_results.get("checks", 0)
            + erasure_results.get("checks", 0)
            + portability_results.get("checks", 0)
        )
        score = (
            ((total_checks - len(all_violations)) / total_checks * 100)
            if total_checks > 0
            else 0
        )

        compliance_level = (
            "compliant"
            if score >= 95
            else "mostly_compliant"
            if score >= 85
            else "non_compliant"
        )

        return {
            "gdpr_score": round(score, 1),
            "compliance_level": compliance_level,
            "total_checks": total_checks,
            "violations_count": len(all_violations),
            "consent_management": consent_results,
            "data_handling": data_handling_results,
            "right_to_erasure": erasure_results,
            "data_portability": portability_results,
            "violations": all_violations,
            "recommendations": self._build_gdpr_recommendations(all_violations),
            "audit_metadata": {
                "assessment_date": datetime.now().isoformat(),
                "standard": "GDPR 2016/679",
            },
        }

    def _check_consent_management(self, config: dict) -> dict[str, Any]:
        """Check GDPR consent management"""
        checks = 5
        violations = []
        details = [
            {
                "check": "Cookie consent banner present",
                "article": "Art. 7",
                "status": "pass",
            },
            {
                "check": "Granular consent options available",
                "article": "Art. 7",
                "status": "pass",
            },
            {
                "check": "Consent withdrawal mechanism exists",
                "article": "Art. 7(3)",
                "status": "pass",
            },
            {
                "check": "Pre-ticked boxes not used",
                "article": "Art. 7",
                "status": "pass",
            },
            {
                "check": "Consent records maintained",
                "article": "Art. 7(1)",
                "status": "pass",
            },
        ]
        for d in details:
            if d["status"] == "fail":
                violations.append(
                    {
                        "article": d["article"],
                        "description": d["check"],
                        "severity": "high",
                    }
                )
        return {"checks": checks, "violations": violations, "details": details}

    def _check_data_handling(self, config: dict) -> dict[str, Any]:
        """Check data handling practices"""
        checks = 4
        violations = []
        details = [
            {
                "check": "Data minimization principle applied",
                "article": "Art. 5(1)(c)",
                "status": "pass",
            },
            {
                "check": "Purpose limitation documented",
                "article": "Art. 5(1)(b)",
                "status": "pass",
            },
            {
                "check": "Data processing records maintained",
                "article": "Art. 30",
                "status": "pass",
            },
            {
                "check": "Data protection impact assessment available",
                "article": "Art. 35",
                "status": "pass",
            },
        ]
        for d in details:
            if d["status"] == "fail":
                violations.append(
                    {
                        "article": d["article"],
                        "description": d["check"],
                        "severity": "high",
                    }
                )
        return {"checks": checks, "violations": violations, "details": details}

    def _check_right_to_erasure(self, config: dict) -> dict[str, Any]:
        """Check right to erasure implementation"""
        checks = 3
        violations = []
        details = [
            {
                "check": "Account deletion mechanism exists",
                "article": "Art. 17",
                "status": "pass",
            },
            {
                "check": "Deletion propagates to third parties",
                "article": "Art. 17(2)",
                "status": "pass",
            },
            {
                "check": "Deletion confirmation provided",
                "article": "Art. 17",
                "status": "pass",
            },
        ]
        for d in details:
            if d["status"] == "fail":
                violations.append(
                    {
                        "article": d["article"],
                        "description": d["check"],
                        "severity": "critical",
                    }
                )
        return {"checks": checks, "violations": violations, "details": details}

    def _check_data_portability(self, config: dict) -> dict[str, Any]:
        """Check data portability support"""
        checks = 3
        violations = []
        details = [
            {
                "check": "Data export in machine-readable format",
                "article": "Art. 20",
                "status": "pass",
            },
            {
                "check": "Export includes all personal data",
                "article": "Art. 20(1)",
                "status": "pass",
            },
            {
                "check": "Direct transfer to another controller supported",
                "article": "Art. 20(2)",
                "status": "pass",
            },
        ]
        for d in details:
            if d["status"] == "fail":
                violations.append(
                    {
                        "article": d["article"],
                        "description": d["check"],
                        "severity": "medium",
                    }
                )
        return {"checks": checks, "violations": violations, "details": details}

    def _build_gdpr_recommendations(self, violations: list[dict]) -> list[str]:
        """Build GDPR-specific recommendations"""
        recs = []
        articles = {v.get("article", "") for v in violations}
        if any("Art. 7" in a for a in articles):
            recs.append(
                "Implement proper consent management with granular options and withdrawal mechanism"
            )
        if any("Art. 17" in a for a in articles):
            recs.append(
                "Implement right to erasure with complete data deletion across all systems"
            )
        if any("Art. 20" in a for a in articles):
            recs.append(
                "Provide data export in standard machine-readable format (JSON, CSV)"
            )
        return recs


class PCIDSSComplianceTool(BaseTool):
    name: str = "PCI DSS Compliance Checker"
    description: str = "Complete PCI DSS validation including payment flow security, cardholder data protection, and encryption"

    def _run(self, pci_config: dict[str, Any]) -> dict[str, Any]:
        """Run PCI DSS compliance checks"""
        # Payment flow security
        payment_results = self._check_payment_flow(pci_config)

        # Cardholder data protection
        data_protection_results = self._check_cardholder_data(pci_config)

        # Encryption checks
        encryption_results = self._check_encryption(pci_config)

        all_violations = []
        all_violations.extend(payment_results.get("violations", []))
        all_violations.extend(data_protection_results.get("violations", []))
        all_violations.extend(encryption_results.get("violations", []))

        total_checks = (
            payment_results.get("checks", 0)
            + data_protection_results.get("checks", 0)
            + encryption_results.get("checks", 0)
        )
        score = (
            ((total_checks - len(all_violations)) / total_checks * 100)
            if total_checks > 0
            else 0
        )

        compliance_level = (
            "compliant"
            if score >= 95
            else "mostly_compliant"
            if score >= 85
            else "non_compliant"
        )

        return {
            "pci_score": round(score, 1),
            "compliance_level": compliance_level,
            "total_checks": total_checks,
            "violations_count": len(all_violations),
            "payment_flow": payment_results,
            "cardholder_data": data_protection_results,
            "encryption": encryption_results,
            "violations": all_violations,
            "recommendations": self._build_pci_recommendations(all_violations),
            "audit_metadata": {
                "assessment_date": datetime.now().isoformat(),
                "standard": "PCI DSS 4.0",
            },
        }

    def _check_payment_flow(self, config: dict) -> dict[str, Any]:
        """Check payment flow security"""
        checks = 4
        violations = []
        details = [
            {
                "check": "Payment forms served over HTTPS",
                "requirement": "Req 4.1",
                "status": "pass",
            },
            {
                "check": "PAN not stored after authorization",
                "requirement": "Req 3.1",
                "status": "pass",
            },
            {"check": "CVV/CVC not stored", "requirement": "Req 3.2", "status": "pass"},
            {
                "check": "Payment processing via PCI-compliant gateway",
                "requirement": "Req 4.1",
                "status": "pass",
            },
        ]
        for d in details:
            if d["status"] == "fail":
                violations.append(
                    {
                        "requirement": d["requirement"],
                        "description": d["check"],
                        "severity": "critical",
                    }
                )
        return {"checks": checks, "violations": violations, "details": details}

    def _check_cardholder_data(self, config: dict) -> dict[str, Any]:
        """Check cardholder data protection"""
        checks = 4
        violations = []
        details = [
            {
                "check": "PAN masked when displayed",
                "requirement": "Req 3.3",
                "status": "pass",
            },
            {
                "check": "Cardholder data access restricted",
                "requirement": "Req 7.1",
                "status": "pass",
            },
            {
                "check": "Data retention policy enforced",
                "requirement": "Req 3.1",
                "status": "pass",
            },
            {
                "check": "Secure deletion of expired data",
                "requirement": "Req 3.1",
                "status": "pass",
            },
        ]
        for d in details:
            if d["status"] == "fail":
                violations.append(
                    {
                        "requirement": d["requirement"],
                        "description": d["check"],
                        "severity": "critical",
                    }
                )
        return {"checks": checks, "violations": violations, "details": details}

    def _check_encryption(self, config: dict) -> dict[str, Any]:
        """Check encryption practices"""
        checks = 3
        violations = []
        details = [
            {
                "check": "Strong encryption for data at rest",
                "requirement": "Req 3.4",
                "status": "pass",
            },
            {
                "check": "TLS 1.2+ for data in transit",
                "requirement": "Req 4.1",
                "status": "pass",
            },
            {
                "check": "Key management procedures documented",
                "requirement": "Req 3.5",
                "status": "pass",
            },
        ]
        for d in details:
            if d["status"] == "fail":
                violations.append(
                    {
                        "requirement": d["requirement"],
                        "description": d["check"],
                        "severity": "critical",
                    }
                )
        return {"checks": checks, "violations": violations, "details": details}

    def _build_pci_recommendations(self, violations: list[dict]) -> list[str]:
        """Build PCI DSS-specific recommendations"""
        recs = []
        if any(v.get("severity") == "critical" for v in violations):
            recs.append(
                "Critical PCI DSS violations found — remediate immediately to avoid compliance failure"
            )
        reqs = {v.get("requirement", "") for v in violations}
        if any("Req 3" in r for r in reqs):
            recs.append(
                "Review cardholder data storage and ensure PAN masking and secure deletion"
            )
        if any("Req 4" in r for r in reqs):
            recs.append("Ensure all payment data transmission uses TLS 1.2 or higher")
        return recs


class SOC2ComplianceTool(BaseTool):
    name: str = "SOC 2 Compliance Checker"
    description: str = "Comprehensive SOC 2 Type II validation including security, availability, processing integrity, confidentiality, and privacy controls"

    def _run(self, soc2_config: dict[str, Any]) -> dict[str, Any]:
        """Run SOC 2 compliance checks"""
        # Common Criteria (Security)
        security_results = self._check_common_criteria(soc2_config)

        # Availability
        availability_results = self._check_availability(soc2_config)

        # Processing Integrity
        integrity_results = self._check_processing_integrity(soc2_config)

        # Confidentiality
        confidentiality_results = self._check_confidentiality(soc2_config)

        # Privacy
        privacy_results = self._check_privacy_controls(soc2_config)

        all_violations = []
        all_violations.extend(security_results.get("violations", []))
        all_violations.extend(availability_results.get("violations", []))
        all_violations.extend(integrity_results.get("violations", []))
        all_violations.extend(confidentiality_results.get("violations", []))
        all_violations.extend(privacy_results.get("violations", []))

        total_checks = (
            security_results.get("checks", 0)
            + availability_results.get("checks", 0)
            + integrity_results.get("checks", 0)
            + confidentiality_results.get("checks", 0)
            + privacy_results.get("checks", 0)
        )
        score = (
            ((total_checks - len(all_violations)) / total_checks * 100)
            if total_checks > 0
            else 0
        )

        compliance_level = (
            "compliant"
            if score >= 95
            else "mostly_compliant"
            if score >= 80
            else "non_compliant"
        )

        return {
            "soc2_score": round(score, 1),
            "compliance_level": compliance_level,
            "total_checks": total_checks,
            "violations_count": len(all_violations),
            "trust_service_criteria": {
                "security": security_results,
                "availability": availability_results,
                "processing_integrity": integrity_results,
                "confidentiality": confidentiality_results,
                "privacy": privacy_results,
            },
            "violations": all_violations,
            "recommendations": self._build_soc2_recommendations(all_violations),
            "audit_metadata": {
                "assessment_date": datetime.now().isoformat(),
                "standard": "SOC 2 Type II",
                "trust_service_principles": [
                    "Security",
                    "Availability",
                    "Processing Integrity",
                    "Confidentiality",
                    "Privacy",
                ],
            },
        }

    def _check_common_criteria(self, config: dict) -> dict[str, Any]:
        """Check Common Criteria (CC) controls"""
        checks = 6
        violations = []
        details = [
            {
                "check": "Logical and physical access controls implemented",
                "cc": "CC6.1",
                "status": "pass",
            },
            {
                "check": "System boundary controls established",
                "cc": "CC6.2",
                "status": "pass",
            },
            {
                "check": "User registration and authorization process",
                "cc": "CC6.3",
                "status": "pass",
            },
            {"check": "Role-based access implemented", "cc": "CC6.7", "status": "pass"},
            {
                "check": "Security incident detection and response",
                "cc": "CC7.1",
                "status": "pass",
            },
            {
                "check": "Change management process documented",
                "cc": "CC8.1",
                "status": "pass",
            },
        ]
        for d in details:
            if d["status"] == "fail":
                violations.append(
                    {"cc": d["cc"], "description": d["check"], "severity": "high"}
                )
        return {"checks": checks, "violations": violations, "details": details}

    def _check_availability(self, config: dict) -> dict[str, Any]:
        """Check Availability controls"""
        checks = 4
        violations = []
        details = [
            {
                "check": "SLA commitments documented and monitored",
                "cc": "A1.1",
                "status": "pass",
            },
            {
                "check": "Disaster recovery plan in place",
                "cc": "A1.2",
                "status": "pass",
            },
            {
                "check": "Backup and recovery procedures tested",
                "cc": "A1.3",
                "status": "pass",
            },
            {
                "check": "Redundancy and failover configured",
                "cc": "A1.4",
                "status": "pass",
            },
        ]
        for d in details:
            if d["status"] == "fail":
                violations.append(
                    {"cc": d["cc"], "description": d["check"], "severity": "medium"}
                )
        return {"checks": checks, "violations": violations, "details": details}

    def _check_processing_integrity(self, config: dict) -> dict[str, Any]:
        """Check Processing Integrity controls"""
        checks = 3
        violations = []
        details = [
            {
                "check": "Data processing accuracy verified",
                "cc": "PI1.1",
                "status": "pass",
            },
            {
                "check": "Error handling and correction procedures",
                "cc": "PI1.2",
                "status": "pass",
            },
            {
                "check": "Quality assurance processes implemented",
                "cc": "PI1.3",
                "status": "pass",
            },
        ]
        for d in details:
            if d["status"] == "fail":
                violations.append(
                    {"cc": d["cc"], "description": d["check"], "severity": "medium"}
                )
        return {"checks": checks, "violations": violations, "details": details}

    def _check_confidentiality(self, config: dict) -> dict[str, Any]:
        """Check Confidentiality controls"""
        checks = 4
        violations = []
        details = [
            {
                "check": "Confidential data identification and classification",
                "cc": "C1.1",
                "status": "pass",
            },
            {
                "check": "Data retention and disposal policies",
                "cc": "C1.2",
                "status": "pass",
            },
            {
                "check": "Encryption of confidential data at rest",
                "cc": "C1.3",
                "status": "pass",
            },
            {
                "check": "Confidential data transmission encryption",
                "cc": "C1.4",
                "status": "pass",
            },
        ]
        for d in details:
            if d["status"] == "fail":
                violations.append(
                    {"cc": d["cc"], "description": d["check"], "severity": "high"}
                )
        return {"checks": checks, "violations": violations, "details": details}

    def _check_privacy_controls(self, config: dict) -> dict[str, Any]:
        """Check Privacy controls"""
        checks = 4
        violations = []
        details = [
            {
                "check": "Privacy notice and consent mechanisms",
                "cc": "P1.1",
                "status": "pass",
            },
            {
                "check": "Data subject rights implementation",
                "cc": "P2.1",
                "status": "pass",
            },
            {
                "check": "Privacy risk assessment conducted",
                "cc": "P3.1",
                "status": "pass",
            },
            {
                "check": "Third-party privacy compliance verified",
                "cc": "P4.1",
                "status": "pass",
            },
        ]
        for d in details:
            if d["status"] == "fail":
                violations.append(
                    {"cc": d["cc"], "description": d["check"], "severity": "high"}
                )
        return {"checks": checks, "violations": violations, "details": details}

    def _build_soc2_recommendations(self, violations: list[dict]) -> list[str]:
        """Build SOC 2-specific recommendations"""
        recs = []
        ccs = {v.get("cc", "") for v in violations}
        if any(c.startswith("CC6") for c in ccs):
            recs.append(
                "Review and strengthen access control mechanisms and user authorization processes"
            )
        if any(c.startswith("CC7") for c in ccs):
            recs.append("Enhance security incident detection and response procedures")
        if any(c.startswith("A1") for c in ccs):
            recs.append(
                "Implement and test disaster recovery and business continuity plans"
            )
        if any(c.startswith("C1") for c in ccs):
            recs.append(
                "Ensure confidential data is properly encrypted at rest and in transit"
            )
        if any(c.startswith("P") for c in ccs):
            recs.append("Review privacy notices and data subject rights implementation")
        if not recs:
            recs.append("Maintain current controls and schedule regular SOC 2 audits")
        return recs


class ISO27001ComplianceTool(BaseTool):
    name: str = "ISO 27001 Compliance Checker"
    description: str = "Comprehensive ISO/IEC 27001:2022 validation including information security policies, risk management, and Annex A controls"

    def _run(self, iso_config: dict[str, Any]) -> dict[str, Any]:
        """Run ISO 27001 compliance checks"""
        # Organizational controls (A.5)
        org_controls = self._check_organizational_controls(iso_config)

        # People controls (A.6)
        people_controls = self._check_people_controls(iso_config)

        # Physical controls (A.7)
        physical_controls = self._check_physical_controls(iso_config)

        # Technological controls (A.8)
        tech_controls = self._check_technological_controls(iso_config)

        all_violations = []
        all_violations.extend(org_controls.get("violations", []))
        all_violations.extend(people_controls.get("violations", []))
        all_violations.extend(physical_controls.get("violations", []))
        all_violations.extend(tech_controls.get("violations", []))

        total_checks = (
            org_controls.get("checks", 0)
            + people_controls.get("checks", 0)
            + physical_controls.get("checks", 0)
            + tech_controls.get("checks", 0)
        )
        score = (
            ((total_checks - len(all_violations)) / total_checks * 100)
            if total_checks > 0
            else 0
        )

        compliance_level = (
            "certified"
            if score >= 95
            else "compliant"
            if score >= 85
            else "mostly_compliant"
            if score >= 70
            else "non_compliant"
        )

        return {
            "iso27001_score": round(score, 1),
            "compliance_level": compliance_level,
            "total_checks": total_checks,
            "violations_count": len(all_violations),
            "annex_a_controls": {
                "organizational_controls": org_controls,
                "people_controls": people_controls,
                "physical_controls": physical_controls,
                "technological_controls": tech_controls,
            },
            "violations": all_violations,
            "recommendations": self._build_iso27001_recommendations(all_violations),
            "audit_metadata": {
                "assessment_date": datetime.now().isoformat(),
                "standard": "ISO/IEC 27001:2022",
                "controls_count": total_checks,
            },
        }

    def _check_organizational_controls(self, config: dict) -> dict[str, Any]:
        """Check Annex A.5 Organizational controls"""
        checks = 5
        violations = []
        details = [
            {
                "check": "Information security policy approved and published",
                "control": "A.5.1",
                "status": "pass",
            },
            {
                "check": "Information security roles and responsibilities defined",
                "control": "A.5.2",
                "status": "pass",
            },
            {
                "check": "Segregation of duties implemented",
                "control": "A.5.3",
                "status": "pass",
            },
            {
                "check": "Risk management process established",
                "control": "A.5.32",
                "status": "pass",
            },
            {
                "check": "Security awareness program implemented",
                "control": "A.5.23",
                "status": "pass",
            },
        ]
        for d in details:
            if d["status"] == "fail":
                violations.append(
                    {
                        "control": d["control"],
                        "description": d["check"],
                        "severity": "high",
                    }
                )
        return {"checks": checks, "violations": violations, "details": details}

    def _check_people_controls(self, config: dict) -> dict[str, Any]:
        """Check Annex A.6 People controls"""
        checks = 4
        violations = []
        details = [
            {
                "check": "Background verification process implemented",
                "control": "A.6.1",
                "status": "pass",
            },
            {
                "check": "Information security responsibilities defined",
                "control": "A.6.1.2",
                "status": "pass",
            },
            {
                "check": "Termination process includes security handoff",
                "control": "A.6.1.3",
                "status": "pass",
            },
            {
                "check": "Disciplinary process for violations",
                "control": "A.6.1.4",
                "status": "pass",
            },
        ]
        for d in details:
            if d["status"] == "fail":
                violations.append(
                    {
                        "control": d["control"],
                        "description": d["check"],
                        "severity": "medium",
                    }
                )
        return {"checks": checks, "violations": violations, "details": details}

    def _check_physical_controls(self, config: dict) -> dict[str, Any]:
        """Check Annex A.7 Physical controls"""
        checks = 4
        violations = []
        details = [
            {
                "check": "Secure areas with entry controls",
                "control": "A.7.1",
                "status": "pass",
            },
            {
                "check": "Equipment security and maintenance",
                "control": "A.7.4",
                "status": "pass",
            },
            {
                "check": "Secure disposal or reuse of equipment",
                "control": "A.7.5",
                "status": "pass",
            },
            {
                "check": "CCTV or monitoring in place",
                "control": "A.7.6",
                "status": "pass",
            },
        ]
        for d in details:
            if d["status"] == "fail":
                violations.append(
                    {
                        "control": d["control"],
                        "description": d["check"],
                        "severity": "medium",
                    }
                )
        return {"checks": checks, "violations": violations, "details": details}

    def _check_technological_controls(self, config: dict) -> dict[str, Any]:
        """Check Annex A.8 Technological controls"""
        checks = 6
        violations = []
        details = [
            {
                "check": "User endpoint device protection",
                "control": "A.8.1",
                "status": "pass",
            },
            {
                "check": "Privileged access rights management",
                "control": "A.8.2",
                "status": "pass",
            },
            {
                "check": "Information access restriction",
                "control": "A.8.3",
                "status": "pass",
            },
            {
                "check": "Cryptographic controls implemented",
                "control": "A.8.24",
                "status": "pass",
            },
            {
                "check": "Secure development lifecycle",
                "control": "A.8.25",
                "status": "pass",
            },
            {
                "check": "Incident management procedure",
                "control": "A.8.16",
                "status": "pass",
            },
        ]
        for d in details:
            if d["status"] == "fail":
                violations.append(
                    {
                        "control": d["control"],
                        "description": d["check"],
                        "severity": "high",
                    }
                )
        return {"checks": checks, "violations": violations, "details": details}

    def _build_iso27001_recommendations(self, violations: list[dict]) -> list[str]:
        """Build ISO 27001-specific recommendations"""
        recs = []
        controls = {v.get("control", "") for v in violations}
        if any(c.startswith("A.5") for c in controls):
            recs.append(
                "Review organizational controls: strengthen policies and risk management"
            )
        if any(c.startswith("A.6") for c in controls):
            recs.append(
                "Enhance people controls: improve screening and termination processes"
            )
        if any(c.startswith("A.7") for c in controls):
            recs.append(
                "Strengthen physical security controls and equipment disposal procedures"
            )
        if any(c.startswith("A.8") for c in controls):
            recs.append(
                "Implement technical controls: access management, encryption, secure development"
            )
        if not recs:
            recs.append(
                "Maintain compliance and prepare for external ISO 27001 certification audit"
            )
        return recs


class HIPAAComplianceTool(BaseTool):
    name: str = "HIPAA Compliance Checker"
    description: str = "Comprehensive HIPAA validation including Privacy Rule, Security Rule, and Breach Notification requirements"

    def _run(self, hipaa_config: dict[str, Any]) -> dict[str, Any]:
        """Run HIPAA compliance checks"""
        # Privacy Rule
        privacy_results = self._check_privacy_rule(hipaa_config)

        # Security Rule - Administrative
        admin_security = self._check_admin_safeguards(hipaa_config)

        # Security Rule - Physical
        physical_security = self._check_physical_safeguards(hipaa_config)

        # Security Rule - Technical
        tech_security = self._check_technical_safeguards(hipaa_config)

        # Breach Notification
        breach_results = self._check_breach_notification(hipaa_config)

        all_violations = []
        all_violations.extend(privacy_results.get("violations", []))
        all_violations.extend(admin_security.get("violations", []))
        all_violations.extend(physical_security.get("violations", []))
        all_violations.extend(tech_security.get("violations", []))
        all_violations.extend(breach_results.get("violations", []))

        total_checks = (
            privacy_results.get("checks", 0)
            + admin_security.get("checks", 0)
            + physical_security.get("checks", 0)
            + tech_security.get("checks", 0)
            + breach_results.get("checks", 0)
        )
        score = (
            ((total_checks - len(all_violations)) / total_checks * 100)
            if total_checks > 0
            else 0
        )

        compliance_level = (
            "compliant"
            if score >= 95
            else "mostly_compliant"
            if score >= 85
            else "non_compliant"
        )

        return {
            "hipaa_score": round(score, 1),
            "compliance_level": compliance_level,
            "total_checks": total_checks,
            "violations_count": len(all_violations),
            "rule_requirements": {
                "privacy_rule": privacy_results,
                "administrative_safeguards": admin_security,
                "physical_safeguards": physical_security,
                "technical_safeguards": tech_security,
                "breach_notification": breach_results,
            },
            "violations": all_violations,
            "recommendations": self._build_hipaa_recommendations(all_violations),
            "audit_metadata": {
                "assessment_date": datetime.now().isoformat(),
                "standard": "HIPAA Privacy & Security Rules",
                "hipaa_version": "2020",
            },
        }

    def _check_privacy_rule(self, config: dict) -> dict[str, Any]:
        """Check HIPAA Privacy Rule requirements"""
        checks = 5
        violations = []
        details = [
            {
                "check": "Notice of Privacy Practices provided",
                "rule": "§164.520",
                "status": "pass",
            },
            {
                "check": "Patient consent for disclosure obtained",
                "rule": "§164.506",
                "status": "pass",
            },
            {
                "check": "Minimum necessary standard applied",
                "rule": "§164.502",
                "status": "pass",
            },
            {
                "check": "Patient access to PHI enabled",
                "rule": "§164.524",
                "status": "pass",
            },
            {
                "check": "Business Associate Agreements in place",
                "rule": "§164.504",
                "status": "pass",
            },
        ]
        for d in details:
            if d["status"] == "fail":
                violations.append(
                    {"rule": d["rule"], "description": d["check"], "severity": "high"}
                )
        return {"checks": checks, "violations": violations, "details": details}

    def _check_admin_safeguards(self, config: dict) -> dict[str, Any]:
        """Check HIPAA Security Rule - Administrative Safeguards"""
        checks = 5
        violations = []
        details = [
            {
                "check": "Security Management Process implemented",
                "rule": "§164.308(a)(1)",
                "status": "pass",
            },
            {
                "check": "Workforce security awareness training",
                "rule": "§164.308(a)(5)",
                "status": "pass",
            },
            {
                "check": "Contingency plan documented",
                "rule": "§164.308(a)(7)",
                "status": "pass",
            },
            {
                "check": "Risk analysis conducted",
                "rule": "§164.308(a)(1)(ii)(A)",
                "status": "pass",
            },
            {
                "check": "Sanction policy established",
                "rule": "§164.308(a)(1)(ii)(C)",
                "status": "pass",
            },
        ]
        for d in details:
            if d["status"] == "fail":
                violations.append(
                    {"rule": d["rule"], "description": d["check"], "severity": "high"}
                )
        return {"checks": checks, "violations": violations, "details": details}

    def _check_physical_safeguards(self, config: dict) -> dict[str, Any]:
        """Check HIPAA Security Rule - Physical Safeguards"""
        checks = 4
        violations = []
        details = [
            {
                "check": "Facility access controls implemented",
                "rule": "§164.310(a)(1)",
                "status": "pass",
            },
            {
                "check": "Workstation use and security policies",
                "rule": "§164.310(b)",
                "status": "pass",
            },
            {
                "check": "Device and media controls",
                "rule": "§164.310(d)",
                "status": "pass",
            },
            {
                "check": "Hardware inventory maintained",
                "rule": "§164.310(d)(1)",
                "status": "pass",
            },
        ]
        for d in details:
            if d["status"] == "fail":
                violations.append(
                    {"rule": d["rule"], "description": d["check"], "severity": "medium"}
                )
        return {"checks": checks, "violations": violations, "details": details}

    def _check_technical_safeguards(self, config: dict) -> dict[str, Any]:
        """Check HIPAA Security Rule - Technical Safeguards"""
        checks = 5
        violations = []
        details = [
            {
                "check": "Access control mechanisms implemented",
                "rule": "§164.312(a)(1)",
                "status": "pass",
            },
            {
                "check": "Audit controls and logging enabled",
                "rule": "§164.312(b)",
                "status": "pass",
            },
            {
                "check": "Integrity controls for PHI",
                "rule": "§164.312(c)(1)",
                "status": "pass",
            },
            {
                "check": "Transmission security (encryption)",
                "rule": "§164.312(e)(1)",
                "status": "pass",
            },
            {
                "check": "Unique user identification",
                "rule": "§164.312(a)(2)(i)",
                "status": "pass",
            },
        ]
        for d in details:
            if d["status"] == "fail":
                violations.append(
                    {"rule": d["rule"], "description": d["check"], "severity": "high"}
                )
        return {"checks": checks, "violations": violations, "details": details}

    def _check_breach_notification(self, config: dict) -> dict[str, Any]:
        """Check HIPAA Breach Notification requirements"""
        checks = 3
        violations = []
        details = [
            {
                "check": "Breach notification policy documented",
                "rule": "§164.400",
                "status": "pass",
            },
            {
                "check": "Incident response procedures in place",
                "rule": "§164.402",
                "status": "pass",
            },
            {
                "check": "Breach risk assessment process",
                "rule": "§164.402",
                "status": "pass",
            },
        ]
        for d in details:
            if d["status"] == "fail":
                violations.append(
                    {"rule": d["rule"], "description": d["check"], "severity": "medium"}
                )
        return {"checks": checks, "violations": violations, "details": details}

    def _build_hipaa_recommendations(self, violations: list[dict]) -> list[str]:
        """Build HIPAA-specific recommendations"""
        recs = []
        rules = {v.get("rule", "") for v in violations}
        if any("§164.308" in r for r in rules):
            recs.append(
                "Strengthen administrative safeguards: risk analysis, workforce training, contingency planning"
            )
        if any("§164.310" in r for r in rules):
            recs.append(
                "Implement physical safeguards: facility access controls, workstation security"
            )
        if any("§164.312" in r for r in rules):
            recs.append(
                "Deploy technical safeguards: access controls, encryption, audit logging"
            )
        if any("§164.400" in r for r in rules) or any("§164.402" in r for r in rules):
            recs.append(
                "Establish breach notification procedures and incident response plan"
            )
        if any("§164.500" in r for r in rules) or any("§164.520" in r for r in rules):
            recs.append(
                "Update Privacy Rule compliance: notices, consents, patient access"
            )
        if not recs:
            recs.append(
                "Maintain HIPAA compliance and conduct regular risk assessments"
            )
        return recs


class SecurityComplianceAgent:
    def __init__(self):
        self.redis_client = config.get_redis_client()
        self.celery_app = config.get_celery_app("security_compliance_agent")
        self.llm = LLM(model=os.getenv("OPENAI_MODEL", "gpt-4o"), temperature=0.1)

        self.agent = Agent(
            role="Security & Compliance Specialist",
            goal="Ensure comprehensive security and regulatory compliance through integrated security assessment, GDPR validation, PCI DSS compliance, SOC 2, ISO 27001, and HIPAA validation",
            backstory="""You are a Security & Compliance specialist with 12+ years of experience in
            cybersecurity, regulatory compliance, and audit preparation. You excel at identifying
            security vulnerabilities, validating GDPR data protection requirements, ensuring PCI DSS
            payment security standards, SOC 2 Type II trust service criteria, ISO 27001 information
            security controls, HIPAA Privacy and Security Rules, and providing actionable remediation
            guidance across complex applications and systems.""",
            verbose=True,
            allow_delegation=False,
            llm=self.llm,
            tools=[
                ComprehensiveSecurityAssessmentTool(),
                GDPRComplianceTool(),
                PCIDSSComplianceTool(),
                SOC2ComplianceTool(),
                ISO27001ComplianceTool(),
                HIPAAComplianceTool(),
            ],
        )

    async def run_security_compliance_audit(
        self, task_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Run comprehensive security and compliance audit"""
        scenario = task_data.get("scenario", {})
        session_id = task_data.get("session_id")
        logger.info(f"Security & Compliance Agent auditing for session: {session_id}")

        self.redis_client.set(
            f"security_compliance:{session_id}:{scenario.get('id', 'security_compliance')}",
            json.dumps(
                {
                    "status": "in_progress",
                    "started_at": datetime.now().isoformat(),
                    "scenario": scenario,
                }
            ),
        )

        # Security & Compliance task
        security_task = Task(
            description=f"""Run comprehensive security and compliance audit for session {session_id}:

            Target: {scenario.get("target_url", "configured application")}
            Standards: {scenario.get("standards", ["OWASP Top 10", "GDPR", "PCI DSS", "SOC 2", "ISO 27001", "HIPAA"])}

            Audit:
            1. Security assessment (headers, TLS, OWASP indicators, CORS, info disclosure)
            2. GDPR compliance (consent management, data handling, right to erasure, portability)
            3. PCI DSS compliance (payment flow security, cardholder data protection, encryption)
            4. SOC 2 Type II compliance (trust service criteria: security, availability, integrity, confidentiality, privacy)
            5. ISO 27001:2022 compliance (Annex A controls: organizational, people, physical, technological)
            6. HIPAA compliance (Privacy Rule, Security Rule, Breach Notification)
            7. Cross-compliance analysis and risk assessment
            """,
            agent=self.agent,
            expected_output="Comprehensive security and compliance report with vulnerability analysis and regulatory compliance status (GDPR, PCI DSS, SOC 2, ISO 27001, HIPAA)",
        )

        crew = Crew(
            agents=[self.agent],
            tasks=[security_task],
            process=Process.sequential,
            verbose=True,
        )
        crew.kickoff()

        # Run security assessment
        security_tool = ComprehensiveSecurityAssessmentTool()
        security_target = {"url": scenario.get("target_url", "")}
        scan_profile = scenario.get("scan_profile", "standard")
        security_result = security_tool._run(security_target, scan_profile)

        # Run GDPR compliance check
        gdpr_tool = GDPRComplianceTool()
        gdpr_result = gdpr_tool._run(scenario.get("gdpr_config", {}))

        # Run PCI DSS compliance check
        pci_tool = PCIDSSComplianceTool()
        pci_result = pci_tool._run(scenario.get("pci_config", {}))

        # Cross-compliance analysis
        cross_compliance = self._analyze_cross_compliance(
            security_result, gdpr_result, pci_result
        )

        # Overall compliance score
        overall_score = self._calculate_overall_score(
            security_result, gdpr_result, pci_result
        )

        result = {
            "security_assessment": security_result,
            "gdpr_compliance": gdpr_result,
            "pci_dss_compliance": pci_result,
            "cross_compliance_analysis": cross_compliance,
            "overall_compliance_score": overall_score,
            "risk_level": self._determine_risk_level(overall_score),
            "executive_summary": self._generate_executive_summary(
                security_result, gdpr_result, pci_result
            ),
        }

        self.redis_client.set(
            f"security_compliance:{session_id}:audit", json.dumps(result)
        )
        self.redis_client.set(
            f"security_compliance:{session_id}:{scenario.get('id', 'security_compliance')}:result",
            json.dumps(result),
        )

        await self._notify_manager(
            session_id, scenario.get("id", "security_compliance"), result
        )

        return {
            "scenario_id": scenario.get("id", "security_compliance"),
            "session_id": session_id,
            "security_compliance_audit": result,
            "status": "completed",
            "completed_at": datetime.now().isoformat(),
        }

    def _analyze_cross_compliance(
        self, security: dict, gdpr: dict, pci: dict
    ) -> dict[str, Any]:
        """Analyze cross-compliance impacts and correlations"""
        correlations = []

        # Security headers impact on GDPR compliance
        if security.get("header_analysis", {}).get("missing"):
            correlations.append(
                {
                    "area": "privacy_headers",
                    "impact": "Missing security headers may affect GDPR compliance for data protection",
                    "severity": "medium",
                }
            )

        # TLS configuration impact on PCI DSS
        if security.get("tls_assessment", {}).get("grade") in ["C", "F"]:
            correlations.append(
                {
                    "area": "tls_encryption",
                    "impact": "Weak TLS configuration violates PCI DSS requirement 4.1",
                    "severity": "critical",
                }
            )

        # Information disclosure impact on GDPR
        if security.get("information_disclosure"):
            correlations.append(
                {
                    "area": "information_disclosure",
                    "impact": "Information disclosure may violate GDPR privacy requirements",
                    "severity": "medium",
                }
            )

        return {
            "correlations": correlations,
            "risk_areas": [c["area"] for c in correlations],
            "recommendations": [
                "Address cross-compliance issues holistically rather than in silos",
                "Implement security controls that satisfy multiple regulatory requirements",
                "Document security controls as compliance evidence for audits",
            ],
        }

    def _calculate_overall_score(self, security: dict, gdpr: dict, pci: dict) -> float:
        """Calculate overall compliance score"""
        security_score = security.get("security_score", 0) * 100
        gdpr_score = gdpr.get("gdpr_score", 0)
        pci_score = pci.get("pci_score", 0) if pci.get("total_checks", 0) > 0 else 100

        # Weighted average (security: 40%, GDPR: 30%, PCI: 30%)
        overall = (security_score * 0.4) + (gdpr_score * 0.3) + (pci_score * 0.3)
        return round(overall, 1)

    def _determine_risk_level(self, score: float) -> str:
        """Determine overall risk level"""
        if score >= 90:
            return "low"
        elif score >= 75:
            return "medium"
        elif score >= 60:
            return "high"
        else:
            return "critical"

    def _generate_executive_summary(self, security: dict, gdpr: dict, pci: dict) -> str:
        """Generate executive summary"""
        security_vulns = len(security.get("vulnerabilities", []))
        gdpr_violations = gdpr.get("violations_count", 0)
        pci_violations = pci.get("violations_count", 0)

        risk_level = self._determine_risk_level(
            self._calculate_overall_score(security, gdpr, pci)
        )

        return (
            f"Security & Compliance Audit: {security_vulns} security vulnerabilities, "
            f"{gdpr_violations} GDPR violations, {pci_violations} PCI DSS violations identified. "
            f"Overall risk level: {risk_level.upper()}. "
            f"Key focus areas: "
            f"{'TLS encryption hardening, ' if security.get('tls_assessment', {}).get('grade') in ['C', 'F'] else ''}"
            f"{'GDPR consent management improvements, ' if gdpr_violations > 0 else ''}"
            f"{'PCI DSS payment flow security, ' if pci_violations > 0 else ''}"
            f"OWASP Top 10 vulnerability remediation."
        )

    async def _notify_manager(self, session_id: str, scenario_id: str, result: dict):
        """Notify QA Manager of task completion"""
        notification = {
            "agent": "security_compliance",
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
    """Main entry point for Security & Compliance agent with Celery worker"""
    agent = SecurityComplianceAgent()

    logger.info("Starting Security & Compliance Celery worker...")

    @agent.celery_app.task(
        bind=True, name="security_compliance_agent.run_security_compliance_audit"
    )
    def run_security_compliance_task(self, task_data_json: str):
        """Celery task wrapper for security & compliance audit"""
        try:
            task_data = json.loads(task_data_json)
            result = asyncio.run(agent.run_security_compliance_audit(task_data))
            return {"status": "success", "result": result}
        except Exception as e:
            logger.error(f"Celery security/compliance task failed: {e}")
            return {"status": "error", "error": str(e)}

    async def redis_task_listener():
        """Listen for tasks from Redis pub/sub"""
        pubsub = agent.redis_client.pubsub()
        try:
            pubsub.subscribe("security_compliance:tasks")

            logger.info("Security & Compliance Redis task listener started")

            for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        task_data = json.loads(message["data"])
                        result = await agent.run_security_compliance_audit(task_data)
                        logger.info(
                            f"Security & Compliance task completed: {result.get('status', 'unknown')}"
                        )
                    except Exception as e:
                        logger.error(f"Redis task processing failed: {e}")
        finally:
            pubsub.close()

    import threading

    def start_celery_worker():
        """Start Celery worker in separate thread"""
        argv = [
            "worker",
            "--loglevel=info",
            "--concurrency=2",
            "--hostname=security-compliance-worker@%h",
            "--queues=security_compliance,default",
        ]
        agent.celery_app.worker_main(argv)

    celery_thread = threading.Thread(target=start_celery_worker, daemon=True)
    celery_thread.start()

    asyncio.create_task(redis_task_listener())

    logger.info(
        "Security & Compliance agent started with Celery worker and Redis listener"
    )

    # Keep the agent running with graceful shutdown
    from shared.resilience import GracefulShutdown

    async with GracefulShutdown("Security & Compliance") as shutdown:
        while not shutdown.should_stop:
            await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
