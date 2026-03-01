"""
Report Export Module
Generates PDF, JSON, and CSV reports with charts and comprehensive data analysis.
"""

import json
import logging
import os
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

# Add config path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.environment import config

logger = logging.getLogger(__name__)


class ReportFormat(Enum):
    PDF = "pdf"
    JSON = "json"
    CSV = "csv"
    HTML = "html"


class ReportType(Enum):
    EXECUTIVE_SUMMARY = "executive_summary"
    TECHNICAL_REPORT = "technical_report"
    COMPLIANCE_REPORT = "compliance_report"
    COMPARISON_REPORT = "comparison_report"
    AGENT_PERFORMANCE = "agent_performance"


@dataclass
class ReportRequest:
    session_id: str
    report_type: ReportType
    format: ReportFormat
    template: str | None = None
    custom_filters: dict[str, Any] | None = None
    include_charts: bool = True
    branding: dict[str, str] | None = None


@dataclass
class ReportMetadata:
    report_id: str
    generated_at: datetime
    generated_by: str
    session_id: str
    report_type: ReportType
    format: ReportFormat
    file_size: int
    page_count: int | None = None


class ReportGenerator:
    """Generates reports in various formats"""

    def __init__(self):
        self.redis_client = config.get_redis_client()
        self.reports_dir = Path("/app/reports")
        self.reports_dir.mkdir(exist_ok=True)

    async def generate_report(
        self, request: ReportRequest, user_id: str
    ) -> ReportMetadata:
        """Generate a report based on the request"""
        try:
            # Collect session data
            session_data = await self._collect_session_data(request.session_id)

            # Generate content based on report type
            if request.report_type == ReportType.EXECUTIVE_SUMMARY:
                content = await self._generate_executive_summary(session_data, request)
            elif request.report_type == ReportType.TECHNICAL_REPORT:
                content = await self._generate_technical_report(session_data, request)
            elif request.report_type == ReportType.COMPLIANCE_REPORT:
                content = await self._generate_compliance_report(session_data, request)
            elif request.report_type == ReportType.COMPARISON_REPORT:
                content = await self._generate_comparison_report(session_data, request)
            elif request.report_type == ReportType.AGENT_PERFORMANCE:
                content = await self._generate_agent_performance_report(
                    session_data, request
                )
            else:
                raise ValueError(f"Unsupported report type: {request.report_type}")

            # Generate file in requested format
            file_path, file_size = await self._generate_file(
                content, request.format, request
            )

            # Create metadata
            metadata = ReportMetadata(
                report_id=f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{request.session_id}",
                generated_at=datetime.now(),
                generated_by=user_id,
                session_id=request.session_id,
                report_type=request.report_type,
                format=request.format,
                file_size=file_size,
                page_count=self._count_pages(file_path)
                if request.format == ReportFormat.PDF
                else None,
            )

            # Save metadata
            await self._save_report_metadata(metadata, file_path)

            return metadata

        except Exception as e:
            logger.error(f"Error generating report: {e}")
            raise

    async def _collect_session_data(self, session_id: str) -> dict[str, Any]:
        """Collect all data for a session"""
        session_data = {
            "session_id": session_id,
            "info": {},
            "test_plan": {},
            "verification": {},
            "agent_results": {},
            "metrics": {},
            "timeline": [],
        }

        try:
            # Session info
            info_key = f"session:{session_id}:info"
            info_data = self.redis_client.get(info_key)
            if info_data:
                session_data["info"] = json.loads(info_data)

            # Test plan
            plan_key = f"manager:{session_id}:test_plan"
            plan_data = self.redis_client.get(plan_key)
            if plan_data:
                session_data["test_plan"] = json.loads(plan_data)

            # Verification
            verify_key = f"manager:{session_id}:verification"
            verify_data = self.redis_client.get(verify_key)
            if verify_data:
                session_data["verification"] = json.loads(verify_data)

            # Agent results
            agents = [
                "manager",
                "senior",
                "junior",
                "analyst",
                "security_compliance",
                "performance",
            ]
            for agent in agents:
                agent_key = f"{agent}:{session_id}:comprehensive_report"
                if agent == "manager":
                    agent_key = f"{agent}:{session_id}:report"

                agent_data = self.redis_client.get(agent_key)
                if agent_data:
                    session_data["agent_results"][agent] = json.loads(agent_data)

                # Also get specific data types
                if agent == "analyst":
                    for data_type in [
                        "security",
                        "performance",
                        "comprehensive_report",
                    ]:
                        data_key = f"analyst:{session_id}:{data_type}"
                        type_data = self.redis_client.get(data_key)
                        if type_data:
                            session_data["agent_results"][f"analyst_{data_type}"] = (
                                json.loads(type_data)
                            )

                elif agent == "security_compliance":
                    data_key = f"security_compliance:{session_id}:audit"
                    type_data = self.redis_client.get(data_key)
                    if type_data:
                        session_data["agent_results"]["security_compliance_audit"] = (
                            json.loads(type_data)
                        )

                elif agent == "performance":
                    for data_type in ["monitoring", "load", "resilience"]:
                        data_key = f"performance:{session_id}:{data_type}"
                        type_data = self.redis_client.get(data_key)
                        if type_data:
                            session_data["agent_results"][
                                f"performance_{data_type}"
                            ] = json.loads(type_data)

            # Timeline
            for agent in agents:
                notif_key = f"{agent}:{session_id}:notifications"
                notifications = self.redis_client.lrange(notif_key, 0, -1)
                for notif in notifications:
                    try:
                        data = json.loads(notif)
                        data["agent"] = agent
                        session_data["timeline"].append(data)
                    except json.JSONDecodeError:
                        continue

            # Sort timeline
            session_data["timeline"].sort(key=lambda x: x.get("timestamp", ""))

            # Calculate metrics
            session_data["metrics"] = self._calculate_session_metrics(session_data)

        except Exception as e:
            logger.error(f"Error collecting session data: {e}")

        return session_data

    def _calculate_session_metrics(
        self, session_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Calculate comprehensive metrics for the session"""
        metrics = {
            "total_agents": len(session_data["agent_results"]),
            "timeline_events": len(session_data["timeline"]),
            "duration_minutes": 0,
            "overall_score": None,
            "agent_scores": {},
            "test_coverage": 0,
            "error_count": 0,
            "warning_count": 0,
        }

        try:
            # Duration
            if session_data["info"].get("created_at"):
                start_time = datetime.fromisoformat(session_data["info"]["created_at"])
                end_time = datetime.now()
                if session_data["info"].get("completed_at"):
                    end_time = datetime.fromisoformat(
                        session_data["info"]["completed_at"]
                    )
                metrics["duration_minutes"] = int(
                    (end_time - start_time).total_seconds() / 60
                )

            # Overall score from verification
            verification = session_data.get("verification", {})
            metrics["overall_score"] = verification.get("overall_score")

            # Agent scores
            for agent, results in session_data["agent_results"].items():
                if "score" in results:
                    metrics["agent_scores"][agent] = results["score"]
                elif "overall_score" in results:
                    metrics["agent_scores"][agent] = results["overall_score"]
                elif "security_score" in results:
                    metrics["agent_scores"][agent] = results["security_score"]
                elif "performance_grade" in results:
                    # Convert grade to numeric score
                    grade = results["performance_grade"]
                    grade_scores = {"A": 95, "B": 85, "C": 75, "D": 65, "F": 50}
                    metrics["agent_scores"][agent] = grade_scores.get(grade.upper(), 70)

            # Test coverage from test plan
            test_plan = session_data.get("test_plan", {})
            if test_plan.get("scenarios"):
                total_scenarios = len(test_plan["scenarios"])
                completed_scenarios = len(
                    [s for s in test_plan["scenarios"] if s.get("completed", False)]
                )
                if total_scenarios > 0:
                    metrics["test_coverage"] = int(
                        (completed_scenarios / total_scenarios) * 100
                    )

            # Error and warning counts
            for agent, results in session_data["agent_results"].items():
                if isinstance(results, dict):
                    if "errors" in results:
                        metrics["error_count"] += len(results["errors"])
                    if "warnings" in results:
                        metrics["warning_count"] += len(results["warnings"])
                    if "violations" in results:
                        metrics["warning_count"] += len(results["violations"])
                    if "vulnerabilities" in results:
                        metrics["error_count"] += len(
                            [
                                v
                                for v in results["vulnerabilities"]
                                if v.get("severity") in ["critical", "high"]
                            ]
                        )
                        metrics["warning_count"] += len(
                            [
                                v
                                for v in results["vulnerabilities"]
                                if v.get("severity") in ["medium", "low"]
                            ]
                        )

        except Exception as e:
            logger.error(f"Error calculating metrics: {e}")

        return metrics

    async def _generate_executive_summary(
        self, session_data: dict[str, Any], request: ReportRequest
    ) -> dict[str, Any]:
        """Generate executive summary content"""
        content = {
            "title": "Executive Summary",
            "session_id": session_data["session_id"],
            "generated_at": datetime.now().isoformat(),
            "overview": {},
            "key_findings": [],
            "recommendations": [],
            "charts": {},
        }

        try:
            # Overview
            metrics = session_data["metrics"]
            info = session_data["info"]

            content["overview"] = {
                "session_title": info.get(
                    "title", f"Session {session_data['session_id']}"
                ),
                "duration": f"{metrics['duration_minutes']} minutes",
                "agents_deployed": metrics["total_agents"],
                "overall_score": f"{metrics['overall_score'] or 'N/A'}%",
                "test_coverage": f"{metrics['test_coverage']}%",
                "status": info.get("status", "unknown"),
            }

            # Key findings
            findings = []

            if metrics["overall_score"] and metrics["overall_score"] >= 90:
                findings.append("Excellent test results with high quality assurance")
            elif metrics["overall_score"] and metrics["overall_score"] >= 70:
                findings.append("Good test coverage with room for improvement")
            else:
                findings.append("Significant issues identified requiring attention")

            if metrics["test_coverage"] >= 90:
                findings.append("Comprehensive test coverage achieved")
            elif metrics["test_coverage"] >= 70:
                findings.append("Adequate test coverage")
            else:
                findings.append(
                    "Limited test coverage - consider expanding test scenarios"
                )

            # Agent-specific findings
            if "analyst_security" in session_data["agent_results"]:
                security = session_data["agent_results"]["analyst_security"]
                if security.get("security_score", 0) >= 80:
                    findings.append(
                        "Strong security posture with minimal vulnerabilities"
                    )
                else:
                    findings.append(
                        f"Security concerns identified (Score: {security.get('security_score', 0)}%)"
                    )

            if "performance_resilience" in session_data["agent_results"]:
                resilience = session_data["agent_results"]["performance_resilience"]
                score = resilience.get("resilience_score", "unknown")
                findings.append(f"Resilience validation score: {score}")

            content["key_findings"] = findings[:5]  # Limit to top 5

            # Recommendations
            recommendations = []

            if metrics["error_count"] > 0:
                recommendations.append(
                    f"Address {metrics['error_count']} critical issues found during testing"
                )

            if metrics["warning_count"] > 5:
                recommendations.append(
                    f"Review and resolve {metrics['warning_count']} warnings and recommendations"
                )

            if metrics["test_coverage"] < 80:
                recommendations.append(
                    "Expand test coverage to improve quality assurance"
                )

            # Get specific recommendations from agents
            for results in session_data["agent_results"].values():
                if isinstance(results, dict) and "recommendations" in results:
                    agent_recs = results["recommendations"][:2]  # Top 2 from each agent
                    for rec in agent_recs:
                        if rec not in recommendations:
                            recommendations.append(rec)

            content["recommendations"] = recommendations[:8]  # Limit to top 8

            # Charts data
            content["charts"] = {
                "agent_scores": metrics["agent_scores"],
                "timeline_events": len(session_data["timeline"]),
                "error_distribution": {
                    "errors": metrics["error_count"],
                    "warnings": metrics["warning_count"],
                },
            }

        except Exception as e:
            logger.error(f"Error generating executive summary: {e}")
            content["error"] = str(e)

        return content

    async def _generate_technical_report(
        self, session_data: dict[str, Any], request: ReportRequest
    ) -> dict[str, Any]:
        """Generate detailed technical report"""
        content = {
            "title": "Technical Report",
            "session_id": session_data["session_id"],
            "generated_at": datetime.now().isoformat(),
            "session_info": session_data["info"],
            "test_plan": session_data["test_plan"],
            "verification": session_data["verification"],
            "agent_results": session_data["agent_results"],
            "metrics": session_data["metrics"],
            "timeline": session_data["timeline"][:50],  # Limit timeline events
        }

        return content

    async def _generate_compliance_report(
        self, session_data: dict[str, Any], request: ReportRequest
    ) -> dict[str, Any]:
        """Generate compliance-focused report"""
        content = {
            "title": "Compliance Report",
            "session_id": session_data["session_id"],
            "generated_at": datetime.now().isoformat(),
            "compliance_results": {},
            "audit_trail": [],
            "violations": [],
            "recommendations": [],
        }

        try:
            # Collect compliance data
            compliance_sources = [
                ("analyst_security", "Security Compliance"),
                ("analyst_comprehensive_report", "QA Compliance"),
                ("security_compliance_audit", "Regulatory Compliance"),
            ]

            for source, title in compliance_sources:
                if source in session_data["agent_results"]:
                    content["compliance_results"][title] = session_data[
                        "agent_results"
                    ][source]

            # Extract violations
            for title, results in content["compliance_results"].items():
                if isinstance(results, dict):
                    if "violations" in results:
                        for violation in results["violations"]:
                            content["violations"].append(
                                {
                                    "category": title,
                                    "severity": violation.get("severity", "unknown"),
                                    "description": violation.get("description", ""),
                                    "recommendation": violation.get(
                                        "recommendation", ""
                                    ),
                                }
                            )
                    if "vulnerabilities" in results:
                        for vuln in results["vulnerabilities"]:
                            content["violations"].append(
                                {
                                    "category": title,
                                    "severity": vuln.get("severity", "unknown"),
                                    "description": vuln.get("description", ""),
                                    "recommendation": vuln.get("recommendation", ""),
                                }
                            )

            # Sort violations by severity
            severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
            content["violations"].sort(
                key=lambda x: severity_order.get(x["severity"], 4)
            )

            # Collect recommendations
            for title, results in content["compliance_results"].items():
                if isinstance(results, dict) and "recommendations" in results:
                    for rec in results["recommendations"]:
                        content["recommendations"].append(
                            {"category": title, "recommendation": rec}
                        )

        except Exception as e:
            logger.error(f"Error generating compliance report: {e}")
            content["error"] = str(e)

        return content

    async def _generate_comparison_report(
        self, session_data: dict[str, Any], request: ReportRequest
    ) -> dict[str, Any]:
        """Generate session comparison report"""
        content = {
            "title": "Session Comparison Report",
            "session_id": session_data["session_id"],
            "generated_at": datetime.now().isoformat(),
            "comparison_data": {},
            "trends": {},
            "benchmarking": {},
        }

        # For now, return basic structure
        # TODO: Implement comparison with historical sessions
        return content

    async def _generate_agent_performance_report(
        self, session_data: dict[str, Any], request: ReportRequest
    ) -> dict[str, Any]:
        """Generate agent performance analysis"""
        content = {
            "title": "Agent Performance Report",
            "session_id": session_data["session_id"],
            "generated_at": datetime.now().isoformat(),
            "agent_performance": {},
            "efficiency_metrics": {},
            "collaboration_analysis": {},
        }

        try:
            # Analyze each agent's performance
            for agent, results in session_data["agent_results"].items():
                agent_perf = {
                    "tasks_completed": 0,
                    "success_rate": 0,
                    "average_duration": 0,
                    "quality_score": 0,
                }

                # Extract performance metrics from results
                if isinstance(results, dict):
                    if "tasks_completed" in results:
                        agent_perf["tasks_completed"] = results["tasks_completed"]

                    if "success_rate" in results:
                        agent_perf["success_rate"] = results["success_rate"]
                    elif "pass_rate" in results:
                        agent_perf["success_rate"] = results["pass_rate"]

                    if "score" in results:
                        agent_perf["quality_score"] = results["score"]
                    elif "overall_score" in results:
                        agent_perf["quality_score"] = results["overall_score"]

                content["agent_performance"][agent] = agent_perf

            # Calculate efficiency metrics
            total_tasks = sum(
                perf["tasks_completed"]
                for perf in content["agent_performance"].values()
            )
            total_score = sum(
                perf["quality_score"]
                for perf in content["agent_performance"].values()
                if perf["quality_score"]
            )

            content["efficiency_metrics"] = {
                "total_tasks_completed": total_tasks,
                "average_quality_score": total_score / len(content["agent_performance"])
                if content["agent_performance"]
                else 0,
                "most_productive_agent": max(
                    content["agent_performance"].items(),
                    key=lambda x: x[1]["tasks_completed"],
                )[0]
                if content["agent_performance"]
                else "none",
                "highest_quality": max(
                    content["agent_performance"].items(),
                    key=lambda x: x[1]["quality_score"],
                )[0]
                if content["agent_performance"]
                else "none",
            }

        except Exception as e:
            logger.error(f"Error generating agent performance report: {e}")
            content["error"] = str(e)

        return content

    async def _generate_file(
        self, content: dict[str, Any], format: ReportFormat, request: ReportRequest
    ) -> tuple[str, int]:
        """Generate file in specified format"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Sanitize session_id to prevent path traversal characters in the filename
        safe_session_id = re.sub(r"[^a-zA-Z0-9_\-]", "_", request.session_id)[:64]
        filename = f"{request.report_type.value}_{safe_session_id}_{timestamp}.{format.value}"
        file_path = self.reports_dir / filename

        try:
            if format == ReportFormat.JSON:
                # Simple JSON export
                with open(file_path, "w") as f:
                    json.dump(content, f, indent=2, default=str)

            elif format == ReportFormat.CSV:
                # CSV export for tabular data
                import pandas as pd

                # Flatten data for CSV
                flattened_data = self._flatten_for_csv(content)
                df = pd.DataFrame(flattened_data)
                df.to_csv(file_path, index=False)

            elif format == ReportFormat.HTML:
                # HTML report with styling
                html_content = self._generate_html_report(content, request)
                with open(file_path, "w") as f:
                    f.write(html_content)

            elif format == ReportFormat.PDF:
                try:
                    from reportlab.lib import colors
                    from reportlab.lib.pagesizes import letter
                    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
                    from reportlab.lib.units import inch
                    from reportlab.platypus import (
                        Paragraph,
                        SimpleDocTemplate,
                        Spacer,
                        Table,
                        TableStyle,
                    )

                    doc = SimpleDocTemplate(str(file_path), pagesize=letter)
                    styles = getSampleStyleSheet()
                    story = []

                    # Title
                    title_style = ParagraphStyle(
                        "ReportTitle", parent=styles["Heading1"], fontSize=18, spaceAfter=12
                    )
                    story.append(Paragraph(content.get("title", "Report"), title_style))
                    story.append(Spacer(1, 0.2 * inch))

                    # Session info
                    story.append(
                        Paragraph(
                            f"Session: {content.get('session_id', 'N/A')}", styles["Normal"]
                        )
                    )
                    story.append(
                        Paragraph(
                            f"Generated: {content.get('generated_at', 'N/A')}",
                            styles["Normal"],
                        )
                    )
                    story.append(Spacer(1, 0.3 * inch))

                    # Overview section
                    if "overview" in content:
                        story.append(Paragraph("Overview", styles["Heading2"]))
                        table_data = [["Metric", "Value"]]
                        for key, value in content["overview"].items():
                            table_data.append(
                                [key.replace("_", " ").title(), str(value)]
                            )
                        table = Table(table_data, colWidths=[3 * inch, 4 * inch])
                        table.setStyle(
                            TableStyle(
                                [
                                    ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                                    ("GRID", (0, 0), (-1, -1), 1, colors.black),
                                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                                ]
                            )
                        )
                        story.append(table)
                        story.append(Spacer(1, 0.2 * inch))

                    # Key findings
                    if "key_findings" in content:
                        story.append(Paragraph("Key Findings", styles["Heading2"]))
                        for finding in content["key_findings"]:
                            story.append(
                                Paragraph(f"\u2022 {finding}", styles["Normal"])
                            )
                        story.append(Spacer(1, 0.2 * inch))

                    # Recommendations
                    if "recommendations" in content:
                        story.append(Paragraph("Recommendations", styles["Heading2"]))
                        for rec in content["recommendations"]:
                            story.append(
                                Paragraph(f"\u2022 {rec}", styles["Normal"])
                            )
                        story.append(Spacer(1, 0.2 * inch))

                    # Metrics table
                    if "metrics" in content and isinstance(content["metrics"], dict):
                        story.append(Paragraph("Metrics", styles["Heading2"]))
                        table_data = [["Metric", "Value"]]
                        for key, value in content["metrics"].items():
                            if not isinstance(value, dict):
                                table_data.append(
                                    [key.replace("_", " ").title(), str(value)]
                                )
                        if len(table_data) > 1:
                            table = Table(
                                table_data, colWidths=[3 * inch, 4 * inch]
                            )
                            table.setStyle(
                                TableStyle(
                                    [
                                        ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                                        ("GRID", (0, 0), (-1, -1), 1, colors.black),
                                        ("FONTSIZE", (0, 0), (-1, -1), 9),
                                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                                    ]
                                )
                            )
                            story.append(table)

                    doc.build(story)

                except ImportError:
                    logger.warning(
                        "reportlab not installed — falling back to HTML format for PDF. "
                        "Install with: pip install reportlab>=4.0"
                    )
                    html_content = self._generate_html_report(content, request)
                    with open(file_path, "w") as f:
                        f.write(html_content)

            # Get file size
            file_size = file_path.stat().st_size

            return str(file_path), file_size

        except Exception as e:
            logger.error(f"Error generating file {format}: {e}")
            raise

    def _flatten_for_csv(self, content: dict[str, Any]) -> list[dict[str, Any]]:
        """Flatten nested data for CSV export"""
        rows = []

        # Basic session info
        if "session_id" in content:
            rows.append(
                {
                    "metric": "session_id",
                    "value": content["session_id"],
                    "category": "info",
                }
            )

        if "overview" in content:
            for key, value in content["overview"].items():
                rows.append({"metric": key, "value": value, "category": "overview"})

        if "metrics" in content:
            for key, value in content["metrics"].items():
                if isinstance(value, dict):
                    for sub_key, sub_value in value.items():
                        rows.append(
                            {
                                "metric": f"{key}_{sub_key}",
                                "value": sub_value,
                                "category": "metrics",
                            }
                        )
                else:
                    rows.append({"metric": key, "value": value, "category": "metrics"})

        return rows

    def _generate_html_report(
        self, content: dict[str, Any], request: ReportRequest
    ) -> str:
        """Generate HTML report with styling"""
        html_template = """
<!DOCTYPE html>
<html>
<head>
    <title>{title}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; }}
        .header {{ background-color: #f5f5f5; padding: 20px; border-radius: 5px; }}
        .section {{ margin: 20px 0; }}
        .metric {{ display: inline-block; margin: 10px; padding: 10px; background-color: #e9ecef; border-radius: 3px; }}
        .finding {{ margin: 10px 0; padding: 10px; border-left: 4px solid #007bff; }}
        .recommendation {{ margin: 10px 0; padding: 10px; border-left: 4px solid #28a745; }}
        .error {{ color: red; }}
        .success {{ color: green; }}
        table {{ border-collapse: collapse; width: 100%; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f2f2f2; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>{title}</h1>
        <p>Session ID: {session_id}</p>
        <p>Generated: {generated_at}</p>
    </div>

    {body_content}
</body>
</html>
        """

        # Generate body content based on report type
        body_content = ""

        if request.report_type == ReportType.EXECUTIVE_SUMMARY:
            body_content = self._generate_executive_html(content)
        else:
            body_content = f"<pre>{json.dumps(content, indent=2)}</pre>"

        return html_template.format(
            title=content.get("title", "Report"),
            session_id=content.get("session_id", "unknown"),
            generated_at=content.get("generated_at", datetime.now().isoformat()),
            body_content=body_content,
        )

    def _generate_executive_html(self, content: dict[str, Any]) -> str:
        """Generate HTML for executive summary"""
        html = ""

        # Overview
        if "overview" in content:
            html += "<h2>Overview</h2>"
            for key, value in content["overview"].items():
                html += f'<div class="metric"><strong>{key.replace("_", " ").title()}:</strong> {value}</div>'

        # Key Findings
        if "key_findings" in content:
            html += "<h2>Key Findings</h2>"
            for finding in content["key_findings"]:
                html += f'<div class="finding">• {finding}</div>'

        # Recommendations
        if "recommendations" in content:
            html += "<h2>Recommendations</h2>"
            for rec in content["recommendations"]:
                html += f'<div class="recommendation">• {rec}</div>'

        return html

    def _count_pages(self, file_path: str) -> int:
        """Count pages in PDF file"""
        # Placeholder - would need PDF library to count actual pages
        return 1

    async def _save_report_metadata(self, metadata: ReportMetadata, file_path: str):
        """Save report metadata to Redis"""
        try:
            metadata_key = f"report:{metadata.report_id}:metadata"
            metadata_json = json.dumps(
                {
                    **asdict(metadata),
                    "generated_at": metadata.generated_at.isoformat(),
                    "file_path": file_path,
                }
            )

            self.redis_client.set(
                metadata_key, metadata_json, ex=86400 * 30
            )  # 30 days expiry

            # Also add to user's reports list
            user_reports_key = f"user:{metadata.generated_by}:reports"
            self.redis_client.lpush(user_reports_key, metadata.report_id)
            self.redis_client.expire(user_reports_key, 86400 * 30)

        except Exception as e:
            logger.error(f"Error saving report metadata: {e}")


# Singleton instance
report_generator = ReportGenerator()
