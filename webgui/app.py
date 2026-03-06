import json
import logging
import os
import socket
import sys
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

import chainlit as cl
import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

# Correlation ID context var — available to all code in the request
correlation_id_ctx: ContextVar[str | None] = ContextVar("correlation_id", default=None)

# Add config path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.agent_registry import AgentRegistry  # noqa: E402
from config.environment import config  # noqa: E402

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add the project root to Python path
sys.path.append("/app")


_MAX_ACTIVE_SESSIONS = 1000


class AgenticQAGUI:
    def __init__(self) -> None:
        self.redis_client = config.get_redis_client()
        self.active_sessions: dict[str, dict[str, Any]] = {}

    def _evict_old_sessions(self) -> None:
        """Remove oldest sessions when exceeding the cap."""
        if len(self.active_sessions) <= _MAX_ACTIVE_SESSIONS:
            return
        # Sort by created_at and keep the newest
        sorted_ids = sorted(
            self.active_sessions,
            key=lambda k: self.active_sessions[k].get("created_at", ""),
        )
        to_remove = len(self.active_sessions) - _MAX_ACTIVE_SESSIONS
        for sid in sorted_ids[:to_remove]:
            del self.active_sessions[sid]

    async def start_new_session(self) -> str:
        """Start a new testing session"""
        session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.active_sessions[session_id] = {
            "status": "created",
            "created_at": datetime.now().isoformat(),
            "requirements": None,
            "test_plan": None,
            "results": None,
        }
        self._evict_old_sessions()
        return session_id

    async def submit_requirements(
        self, session_id: str, requirements: dict[str, Any]
    ) -> dict[str, Any]:
        """Submit requirements to QA Manager"""
        try:
            # Import here to avoid circular imports
            from agents.manager.qa_manager import QAManagerAgent

            manager = QAManagerAgent()
            result = await manager.process_requirements(requirements)

            # Update session
            self.active_sessions[session_id]["requirements"] = requirements
            self.active_sessions[session_id]["test_plan"] = result.get("test_plan")
            self.active_sessions[session_id]["status"] = "planning_completed"

            return result

        except Exception as e:
            logger.error(f"Error submitting requirements: {e}")
            return {"error": str(e), "status": "failed"}

    async def get_session_status(self, session_id: str) -> dict[str, Any]:
        """Get current session status"""
        try:
            # Get status from Redis if not in active sessions
            if session_id not in self.active_sessions:
                from agents.manager.qa_manager import QAManagerAgent

                manager = QAManagerAgent()
                status = manager.get_session_status(session_id)
                return status

            return self.active_sessions[session_id]

        except Exception as e:
            logger.error(f"Error getting session status: {e}")
            return {"error": str(e), "status": "unknown"}

    async def get_reasoning_trace(self, session_id: str) -> list[dict[str, Any]]:
        """Get reasoning trace for a session"""
        try:
            trace = []

            # Get manager notifications
            manager_notifications = self.redis_client.lrange(
                f"manager:{session_id}:notifications", 0, -1
            )
            for notification in manager_notifications:
                try:
                    data = json.loads(notification)
                    trace.append(
                        {
                            "timestamp": data.get("timestamp"),
                            "agent": data.get("agent"),
                            "type": "notification",
                            "message": f"Agent {data.get('agent')} completed task {data.get('scenario_id')}",
                            "data": data,
                        }
                    )
                except json.JSONDecodeError:
                    continue

            # Sort by timestamp
            trace.sort(key=lambda x: x.get("timestamp", ""))

            return trace

        except Exception as e:
            logger.error(f"Error getting reasoning trace: {e}")
            return []


# Initialize GUI and agent registry
gui = AgenticQAGUI()
_agent_registry = AgentRegistry()


@cl.on_chat_start
async def on_chat_start() -> dict[str, Any]:
    """Initialize chat session"""
    agents = _agent_registry.get_agents_for_team()
    agent_lines = "\n".join(f"• **{a.name}**: {a.focus}" for a in agents)
    await cl.Message(
        content="🤖 Welcome to the Agentic QA Team System!\n\n"
        "I'm your interface to a team of AI-powered QA agents:\n"
        f"{agent_lines}\n\n"
        "To get started, please:\n"
        "1. Upload a PR/feature document, or\n"
        "2. Describe your testing requirements\n\n"
        "What would you like to test today?"
    ).send()

    # Store session in user session
    session_id = await gui.start_new_session()
    cl.user_session.set("session_id", session_id)
    cl.user_session.set("gui", gui)


@cl.on_message
async def on_message(message: cl.Message) -> dict[str, Any]:
    """Handle incoming messages"""
    session_id = cl.user_session.get("session_id")
    gui_instance = cl.user_session.get("gui")

    if not session_id or not gui_instance:
        await cl.Message(content="❌ Session error. Please restart the chat.").send()
        return

    # Process the message
    user_input = message.content

    # Check if this is a requirements submission
    if user_input.lower().startswith(("test", "verify", "check", "validate")):
        await cl.Message(content="🔄 Processing your requirements...").send()

        # Parse requirements from user input
        requirements = {
            "title": f"Testing Request - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "description": user_input,
            "business_goals": "Ensure quality and functionality",
            "constraints": "Standard testing environment",
            "priority": "high",
            "submitted_by": "web_user",
            "submitted_at": datetime.now().isoformat(),
        }

        # Submit to QA Manager
        result = await gui_instance.submit_requirements(session_id, requirements)

        if "error" in result:
            await cl.Message(content=f"❌ Error: {result['error']}").send()
        else:
            # Display test plan
            test_plan = result.get("test_plan", {})

            response = "✅ **Test Plan Created!**\n\n"
            response += f"**Session ID**: {result.get('session_id')}\n"
            response += f"**Status**: {result.get('status')}\n\n"

            if test_plan.get("scenarios"):
                response += "**📋 Test Scenarios:**\n"
                for scenario in test_plan["scenarios"]:
                    priority_emoji = {
                        "critical": "🔴",
                        "high": "🟠",
                        "medium": "🟡",
                        "low": "🟢",
                    }.get(scenario.get("priority"), "⚪")
                    assigned_agent = {"senior": "👨‍💼", "junior": "👩‍💼"}.get(
                        scenario.get("assigned_to"), "🤖"
                    )
                    response += f"{priority_emoji} {assigned_agent} **{scenario.get('name')}** ({scenario.get('priority')})\n"

            if test_plan.get("acceptance_criteria"):
                response += "\n**✅ Acceptance Criteria:**\n"
                for i, criteria in enumerate(test_plan["acceptance_criteria"], 1):
                    response += f"{i}. {criteria}\n"

            response += "\n**🔄 Next Steps:**\n"
            for step in result.get("next_steps", []):
                response += f"• {step}\n"

            await cl.Message(content=response).send()

            # Start monitoring progress
            await cl.Message(content="⏳ Monitoring test execution progress...").send()

    elif user_input.lower() in ("status", "progress", "how's it going?"):
        # Get session status
        status = await gui_instance.get_session_status(session_id)

        response = "📊 **Session Status**\n\n"
        response += f"**Session ID**: {session_id}\n"
        response += f"**Status**: {status.get('status', 'unknown')}\n"

        if status.get("test_plan"):
            test_plan = status["test_plan"]
            total_scenarios = len(test_plan.get("scenarios", []))
            response += f"**Total Scenarios**: {total_scenarios}\n"

        if status.get("verification"):
            verification = status["verification"]
            response += (
                f"**Verification Score**: {verification.get('overall_score', 'N/A')}\n"
            )
            response += f"**Business Alignment**: {verification.get('business_alignment', 'N/A')}\n"

        await cl.Message(content=response).send()

    elif user_input.lower() in ("trace", "reasoning", "log"):
        # Get reasoning trace
        trace = await gui_instance.get_reasoning_trace(session_id)

        if not trace:
            await cl.Message(content="📝 No reasoning trace available yet.").send()
        else:
            response = "📝 **Reasoning Trace**\n\n"

            for event in trace[-10:]:  # Show last 10 events
                agent_emoji = {"manager": "👔", "senior": "👨‍💼", "junior": "👩‍💼"}.get(
                    event.get("agent"), "🤖"
                )
                response += f"{agent_emoji} **{event.get('agent', 'unknown')}** - {event.get('message', 'No message')}\n"
                response += f"   _{event.get('timestamp', 'No timestamp')}_\n\n"

            await cl.Message(content=response).send()

    elif user_input.lower() in ("report", "qa report"):
        # Get analyst comprehensive report
        report_data = gui_instance.redis_client.get(
            f"analyst:{session_id}:comprehensive_report"
        )
        if not report_data:
            report_data = gui_instance.redis_client.get(f"analyst:{session_id}:report")

        if report_data:
            try:
                report = json.loads(report_data)
                response = "📊 **QA Analyst Report**\n\n"

                if report.get("executive_summary"):
                    response += (
                        f"**Executive Summary:** {report['executive_summary']}\n\n"
                    )
                elif report.get("test_report", {}).get("executive_summary"):
                    response += f"**Executive Summary:** {report['test_report']['executive_summary']}\n\n"

                metrics = report.get("metrics") or report.get("test_report", {}).get(
                    "metrics"
                )
                if metrics:
                    response += "**Metrics:**\n"
                    response += f"• Pass Rate: {metrics.get('pass_rate', 'N/A')}%\n"
                    response += (
                        f"• Failure Rate: {metrics.get('failure_rate', 'N/A')}%\n"
                    )
                    response += f"• Coverage: {metrics.get('coverage', 'N/A')}%\n\n"

                readiness = report.get("release_readiness")
                if readiness:
                    verdict_emoji = {
                        "GO": "✅",
                        "GO_WITH_WARNINGS": "⚠️",
                        "NO_GO": "🚫",
                    }.get(readiness.get("verdict"), "❓")
                    response += f"**Release Readiness:** {verdict_emoji} {readiness.get('verdict', 'Unknown')}\n"
                    for b in readiness.get("blockers", []):
                        response += f"  🔴 {b}\n"
                    for w in readiness.get("warnings", []):
                        response += f"  🟡 {w}\n"

                await cl.Message(content=response).send()
            except json.JSONDecodeError:
                await cl.Message(content="❌ Could not parse report data.").send()
        else:
            await cl.Message(content="📝 No analyst report available yet.").send()

    elif user_input.lower() in ("security", "security report"):
        security_data = gui_instance.redis_client.get(
            f"security_compliance:{session_id}:audit"
        )
        source = "security_compliance"
        if not security_data:
            security_data = gui_instance.redis_client.get(
                f"analyst:{session_id}:security"
            )
            source = "analyst"

        if security_data:
            try:
                sec = json.loads(security_data)
                sec_report = (
                    sec.get("security_assessment", sec)
                    if source == "security_compliance"
                    else sec
                )

                response = "🔒 **Security Assessment**\n\n"
                response += f"**Score:** {sec_report.get('security_score', 'N/A')} | **Risk Level:** {sec_report.get('risk_level', 'N/A')}\n\n"

                vulns = sec_report.get("vulnerabilities", [])
                if vulns:
                    response += f"**Vulnerabilities ({len(vulns)}):**\n"
                    for v in vulns[:10]:
                        sev_emoji = {
                            "critical": "🔴",
                            "high": "🟠",
                            "medium": "🟡",
                            "low": "🟢",
                        }.get(v.get("severity"), "⚪")
                        response += f"  {sev_emoji} {v.get('description', 'Unknown')}\n"

                recs = sec_report.get("recommendations", [])
                if recs:
                    response += "\n**Recommendations:**\n"
                    for r in recs[:5]:
                        response += f"  • {r}\n"

                await cl.Message(content=response).send()
            except json.JSONDecodeError:
                await cl.Message(content="❌ Could not parse security data.").send()
        else:
            await cl.Message(content="📝 No security assessment available yet.").send()

    elif user_input.lower() in ("performance", "perf", "performance report"):
        perf_data = gui_instance.redis_client.get(f"analyst:{session_id}:performance")
        perf_source = "analyst"
        if not perf_data:
            perf_data = gui_instance.redis_client.get(
                f"performance:{session_id}:load"
            ) or gui_instance.redis_client.get(f"performance:{session_id}:monitoring")
            perf_source = "performance_agent"

        if perf_data:
            try:
                perf = json.loads(perf_data)
                if perf_source == "analyst":
                    response = "⚡ **Performance Profile**\n\n"
                    response += f"**Grade:** {perf.get('performance_grade', 'N/A')}\n\n"

                    rt = perf.get("response_times", {})
                    response += "**Response Times:**\n"
                    response += f"  • Avg: {rt.get('avg_ms', 'N/A')}ms | P50: {rt.get('p50_ms', 'N/A')}ms\n"
                    response += f"  • P95: {rt.get('p95_ms', 'N/A')}ms | P99: {rt.get('p99_ms', 'N/A')}ms\n\n"

                    tp = perf.get("throughput", {})
                    response += f"**Throughput:** {tp.get('rps', 'N/A')} req/s\n\n"

                    bottlenecks = perf.get("bottlenecks", [])
                    if bottlenecks:
                        response += "**Bottlenecks:**\n"
                        for b in bottlenecks:
                            response += f"  🔴 {b.get('component', 'Unknown')} — {b.get('evidence', '')}\n"

                    if perf.get("regression_detected"):
                        response += "\n⚠️ **Performance regression detected**\n"
                else:
                    suite_type = perf.get("suite_type", "performance")
                    response = "⚡ **Performance Results**\n\n"

                    if suite_type == "load":
                        results = perf.get("test_results", {})
                        response += f"**Load Test:** {results.get('concurrent_users', 'N/A')} users\n"
                        response += f"**Avg Response:** {results.get('response_time_avg', 'N/A')}ms\n"
                        response += (
                            f"**Error Rate:** {results.get('error_rate', 'N/A')}\n"
                        )
                        response += f"**Peak Throughput:** {results.get('throughput_peak', 'N/A')}\n"
                    else:
                        metrics = perf.get("metrics", {})
                        response += (
                            f"**Latency:** {metrics.get('latency_ms', 'N/A')}ms\n"
                        )
                        response += f"**Throughput:** {metrics.get('throughput_rps', 'N/A')} rps\n"
                        response += f"**CPU:** {metrics.get('cpu_usage', 'N/A')}%\n"
                        response += (
                            f"**Memory:** {metrics.get('memory_usage', 'N/A')}%\n"
                        )

                await cl.Message(content=response).send()
            except json.JSONDecodeError:
                await cl.Message(content="❌ Could not parse performance data.").send()
        else:
            await cl.Message(content="📝 No performance profile available yet.").send()

    elif user_input.lower() in ("resilience", "reliability", "resilience report"):
        rel_data = gui_instance.redis_client.get(f"performance:{session_id}:resilience")
        if rel_data:
            try:
                rel = json.loads(rel_data)
                response = "🛡️ **Resilience Validation**\n\n"
                response += (
                    f"**Resilience Score:** {rel.get('resilience_score', 'N/A')}\n"
                )
                response += (
                    f"**Recovery Time:** {rel.get('recovery_time_seconds', 'N/A')}s\n\n"
                )

                scenarios = rel.get("failure_scenarios_tested", [])
                if scenarios:
                    response += "**Scenarios Tested:**\n"
                    for s in scenarios:
                        response += f"  • {s}\n"

                await cl.Message(content=response).send()
            except json.JSONDecodeError:
                await cl.Message(content="❌ Could not parse resilience data.").send()
        else:
            await cl.Message(
                content="📝 No resilience validation available yet."
            ).send()

    elif user_input.lower() in (
        "compliance",
        "gdpr",
        "pci",
        "compliance report",
        "soc2",
        "iso27001",
        "hipaa",
    ):
        comp_data = gui_instance.redis_client.get(
            f"security_compliance:{session_id}:audit"
        )
        if comp_data:
            try:
                comp = json.loads(comp_data)
                response = "📋 **Security & Compliance Audit**\n\n"
                response += f"**Overall Score:** {comp.get('overall_compliance_score', 'N/A')}\n\n"

                gdpr = comp.get("gdpr_compliance", {})
                response += f"**GDPR:** {gdpr.get('gdpr_score', 'N/A')}% ({gdpr.get('violations_count', 0)} violations)\n"

                pci = comp.get("pci_dss_compliance", {})
                response += f"**PCI DSS:** {pci.get('pci_score', 'N/A')}% ({pci.get('violations_count', 0)} violations)\n"

                soc2 = comp.get("soc2_score", {})
                if soc2:
                    response += f"**SOC 2:** {soc2.get('soc2_score', 'N/A')}% ({soc2.get('violations_count', 0)} violations)\n"

                iso = comp.get("iso27001_score", {})
                if iso:
                    response += f"**ISO 27001:** {iso.get('iso27001_score', 'N/A')}% ({iso.get('violations_count', 0)} violations)\n"

                hipaa = comp.get("hipaa_score", {})
                if hipaa:
                    response += f"**HIPAA:** {hipaa.get('hipaa_score', 'N/A')}% ({hipaa.get('violations_count', 0)} violations)\n"

                await cl.Message(content=response).send()
            except json.JSONDecodeError:
                await cl.Message(content="❌ Could not parse compliance data.").send()
        else:
            await cl.Message(content="📝 No compliance audit available yet.").send()

    elif user_input.lower() in (
        "predict",
        "prediction",
        "defect prediction",
        "predictive",
    ):
        pred_data = gui_instance.redis_client.get(f"analyst:{session_id}:prediction")
        if not pred_data:
            pred_data = gui_instance.redis_client.get(
                f"analyst:{session_id}:defect_prediction"
            )
        if pred_data:
            try:
                pred = json.loads(pred_data)
                response = "🔮 **Defect Prediction & Risk Analysis**\n\n"

                if "defect_prediction" in pred:
                    dp = pred["defect_prediction"]
                    response += f"**Predicted Defects:** {dp.get('total_predicted_defects', 'N/A')}\n"
                    response += f"**Confidence:** {dp.get('confidence', 'N/A')}\n\n"

                    high_risk = dp.get("high_risk_areas", [])
                    if high_risk:
                        response += "**High Risk Areas:**\n"
                        for area in high_risk[:5]:
                            response += f"  • {area.get('component', 'N/A')} - Risk: {area.get('risk_score', 'N/A')}\n"

                if "component_risk_scores" in pred:
                    response += "\n**Component Risk Scores:**\n"
                    for comp, score in pred["component_risk_scores"].items():
                        response += f"  • {comp}: {score}\n"

                await cl.Message(content=response).send()
            except json.JSONDecodeError:
                await cl.Message(content="❌ Could not parse prediction data.").send()
        else:
            await cl.Message(
                content="📝 No predictive analytics available yet. Run a full QA session first."
            ).send()

    elif user_input.lower() in ("trend", "quality trend", "trends"):
        trend_data = gui_instance.redis_client.get(
            f"analyst:{session_id}:quality_trend"
        )
        if trend_data:
            try:
                trend = json.loads(trend_data)
                response = "📈 **Quality Trend Analysis**\n\n"
                response += (
                    f"**Trend Direction:** {trend.get('trend_direction', 'N/A')}\n"
                )
                response += f"**Quality Score:** {trend.get('quality_trend', 'N/A')}\n"
                response += f"**Volatility:** {trend.get('volatility', 'N/A')}\n\n"

                if "predictions" in trend:
                    pred = trend["predictions"]
                    response += "**7-Day Predictions:**\n"
                    response += (
                        f"  • Pass Rate: {pred.get('predicted_pass_rate_7d', 'N/A')}%\n"
                    )
                    response += f"  • Predicted Defects: {pred.get('predicted_defects_7d', 'N/A')}\n"

                await cl.Message(content=response).send()
            except json.JSONDecodeError:
                await cl.Message(content="❌ Could not parse trend data.").send()
        else:
            await cl.Message(content="📝 No quality trend data available yet.").send()

    elif user_input.lower() in ("risk", "risk score"):
        risk_data = gui_instance.redis_client.get(f"analyst:{session_id}:risk_scoring")
        if risk_data:
            try:
                risk = json.loads(risk_data)
                response = "⚠️ **Risk Scoring**\n\n"
                response += f"**Portfolio Risk Score:** {risk.get('portfolio_risk_score', 'N/A')}\n"
                response += (
                    f"**Risk Level:** {risk.get('portfolio_risk_level', 'N/A')}\n"
                )
                response += (
                    f"**High Risk Features:** {risk.get('high_risk_count', 'N/A')}\n\n"
                )

                if "feature_risks" in risk:
                    response += "**Top Risk Features:**\n"
                    for feature in risk["feature_risks"][:5]:
                        response += f"  • {feature.get('feature_name', 'N/A')} - {feature.get('risk_level', 'N/A')}\n"

                await cl.Message(content=response).send()
            except json.JSONDecodeError:
                await cl.Message(content="❌ Could not parse risk data.").send()
        else:
            await cl.Message(content="📝 No risk scoring data available yet.").send()

    elif user_input.lower() in ("release", "release readiness", "ready"):
        readiness_data = gui_instance.redis_client.get(
            f"analyst:{session_id}:release_readiness"
        )
        if readiness_data:
            try:
                readiness = json.loads(readiness_data)
                rr = readiness.get("release_readiness", {})
                response = "🚀 **Release Readiness Assessment**\n\n"
                response += f"**Overall Score:** {rr.get('overall_score', 'N/A')}/100\n"
                response += f"**Readiness Level:** {rr.get('readiness_level', 'N/A')}\n"
                response += f"**Ready for Release:** {'✅ Yes' if rr.get('ready_for_release') else '❌ No'}\n"
                response += f"**Confidence:** {rr.get('confidence', 'N/A')}\n\n"

                if "dimension_scores" in readiness:
                    response += "**Dimension Scores:**\n"
                    for dim, score in readiness["dimension_scores"].items():
                        response += f"  • {dim.capitalize()}: {score}\n"

                blockers = readiness.get("blockers", [])
                if blockers:
                    response += "\n**🚫 Blockers:**\n"
                    for b in blockers:
                        response += f"  • {b.get('description', 'N/A')}\n"

                await cl.Message(content=response).send()
            except json.JSONDecodeError:
                await cl.Message(content="❌ Could not parse readiness data.").send()
        else:
            await cl.Message(
                content="📝 No release readiness data available yet."
            ).send()

    elif user_input.lower() in (
        "mobile",
        "desktop",
        "cross-platform",
        "cross platform",
    ):
        cross_data = gui_instance.redis_client.get(
            f"junior:{session_id}:cross_platform"
        )
        if cross_data:
            try:
                cross = json.loads(cross_data)
                response = "📱 **Cross-Platform Testing Results**\n\n"
                response += (
                    f"**Overall Score:** {cross.get('overall_score', 'N/A')}\n\n"
                )

                if "platform_results" in cross:
                    for platform, result in cross["platform_results"].items():
                        response += f"**{platform.capitalize()}:** {result.get('score', result.get('mobile_score', result.get('desktop_score', 'N/A')))}%\n"

                await cl.Message(content=response).send()
            except json.JSONDecodeError:
                await cl.Message(
                    content="❌ Could not parse cross-platform data."
                ).send()
        else:
            await cl.Message(
                content="📝 No cross-platform testing data available yet."
            ).send()

    elif user_input.lower() in ("ai test", "ai generated", "test generation"):
        ai_data = gui_instance.redis_client.get(
            f"senior:{session_id}:ai_test_generation"
        )
        if ai_data:
            try:
                ai = json.loads(ai_data)
                response = "🤖 **AI-Enhanced Test Generation**\n\n"

                if "total_test_cases" in ai:
                    response += f"**Test Cases Generated:** {ai.get('total_test_cases', 'N/A')}\n"

                if "coverage_analysis" in ai:
                    cov = ai["coverage_analysis"]
                    response += "\n**Coverage Analysis:**\n"
                    response += (
                        f"  • Functional: {cov.get('functional_coverage', 'N/A')}%\n"
                    )
                    response += (
                        f"  • Edge Case: {cov.get('edge_case_coverage', 'N/A')}%\n"
                    )
                    response += (
                        f"  • Negative: {cov.get('negative_coverage', 'N/A')}%\n"
                    )
                    response += (
                        f"  • Boundary: {cov.get('boundary_coverage', 'N/A')}%\n"
                    )

                await cl.Message(content=response).send()
            except json.JSONDecodeError:
                await cl.Message(content="❌ Could not parse AI test data.").send()
        else:
            await cl.Message(
                content="📝 No AI test generation data available yet."
            ).send()

    else:
        # General help message
        await cl.Message(
            content="💡 **Available Commands:**\n\n"
            "• **Describe your testing requirements** - Start a new test plan\n"
            "• **'status'** - Check current session status\n"
            "• **'trace'** - View reasoning trace and agent collaboration\n"
            "• **'report'** - View comprehensive QA analyst report\n"
            "• **'security'** - View security assessment\n"
            "• **'performance'** - View performance profile\n"
            "• **'resilience'** - View resilience validation\n"
            "• **'compliance'** - View compliance (GDPR/PCI/SOC2/ISO27001/HIPAA)\n"
            "• **'predict'** - View defect prediction & risk analysis\n"
            "• **'trend'** - View quality trend analysis\n"
            "• **'risk'** - View risk scoring\n"
            "• **'release'** - View release readiness assessment\n"
            "• **'mobile'** - View cross-platform mobile testing\n"
            "• **'ai test'** - View AI-generated test cases\n"
            "• **'help'** - Show this help message\n\n"
            "You can also upload a PR or feature document to get started!"
        ).send()


# @cl.on_file_upload - Commented out due to Chainlit compatibility issue
# async def on_file_upload(files: List[cl.File]) -> Dict[str, Any]:
#     """Handle file uploads"""
#     session_id = cl.user_session.get("session_id")
#     gui_instance = cl.user_session.get("gui")
#
#     if not session_id or not gui_instance:
#         await cl.Message(
#             content="❌ Session error. Please restart the chat."
#         ).send()
#         return
#
#     for file in files:
#         try:
#             # Read file content
#             content = file.content.decode('utf-8')
#
#             await cl.Message(
#                 content=f"📄 Processing uploaded file: {file.name}"
#             ).send()
#
#             # Parse requirements from file content
#             requirements = {
#                 "title": f"Testing from {file.name}",
#                 "description": content[:1000] + "..." if len(content) > 1000 else content,
#                 "business_goals": "Ensure quality based on uploaded document",
#                 "constraints": "Requirements from uploaded file",
#                 "priority": "high",
#                 "submitted_by": "web_upload",
#                 "file_name": file.name,
#                 "submitted_at": datetime.now().isoformat()
#             }
#
#             # Submit to QA Manager
#             result = await gui_instance.submit_requirements(session_id, requirements)
#
#             if "error" in result:
#                 await cl.Message(
#                     content=f"❌ Error processing file: {result['error']}"
#                 ).send()
#             else:
#                 await cl.Message(
#                     content=f"✅ Successfully processed {file.name} and created test plan!"
#                 ).send()
#
#                 # Show summary (similar to text input)
#                 test_plan = result.get("test_plan", {})
#                 response = f"📋 **Test Plan from {file.name}**\n\n"
#
#                 if test_plan.get("scenarios"):
#                     response += "**Test Scenarios:**\n"
#                     for scenario in test_plan["scenarios"][:5]:  # Show first 5
#                         priority_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(scenario.get("priority"), "⚪")
#                         response += f"{priority_emoji} **{scenario.get('name')}**\n"
#
#                 await cl.Message(content=response).send()
#
#         except Exception as e:
#             await cl.Message(
#                 content=f"❌ Error processing {file.name}: {str(e)}"
#             ).send()


@cl.on_chat_end
async def on_chat_end() -> dict[str, Any]:
    """Clean up when chat ends"""
    session_id = cl.user_session.get("session_id")
    if session_id:
        logger.info(f"Ending session: {session_id}")


# ---------------------------------------------------------------------------
# Correlation ID middleware
# ---------------------------------------------------------------------------

_CORRELATION_HEADER = "X-Correlation-ID"


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Propagate or generate a correlation ID for every request.

    - Reads ``X-Correlation-ID`` from the incoming request (or generates a UUID).
    - Stores the ID in :data:`correlation_id_ctx` so any code in the call
      chain can access it (including structlog via ``merge_contextvars``).
    - Attaches the header to the response.
    """

    async def dispatch(self, request: Request, call_next):
        cid = request.headers.get(_CORRELATION_HEADER) or uuid.uuid4().hex
        correlation_id_ctx.set(cid)

        # Bind to structlog contextvars so JSON logs include correlation_id
        try:
            import structlog

            structlog.contextvars.clear_contextvars()
            structlog.contextvars.bind_contextvars(correlation_id=cid)
        except ImportError:
            pass

        response = await call_next(request)
        response.headers[_CORRELATION_HEADER] = cid
        return response


# ---------------------------------------------------------------------------
# Rate limiting middleware
# ---------------------------------------------------------------------------

# Paths exempt from global rate limiting (health, metrics, static assets)
_RATE_LIMIT_EXEMPT = frozenset({"/health", "/api/metrics", "/docs", "/openapi.json"})


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Global per-client rate limiter for all API endpoints.

    Uses the in-memory :class:`~shared.rate_limit.RateLimiter` keyed by
    client IP.  Exempt paths (health, metrics) are not counted.
    Configurable via ``RATE_LIMIT_MAX_REQUESTS`` and
    ``RATE_LIMIT_WINDOW_SECONDS`` env vars.
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Skip non-API and exempt paths
        if not path.startswith("/api") or path in _RATE_LIMIT_EXEMPT:
            return await call_next(request)

        from shared.rate_limit import default_rate_limiter

        client_ip = request.client.host if request.client else "unknown"
        if not await default_rate_limiter.is_allowed(client_ip):
            remaining = default_rate_limiter.get_remaining(client_ip)
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Please try again later."},
                headers={
                    "Retry-After": str(default_rate_limiter.window_seconds),
                    "X-RateLimit-Limit": str(default_rate_limiter.max_requests),
                    "X-RateLimit-Remaining": str(remaining),
                },
            )

        return await call_next(request)


# ---------------------------------------------------------------------------
# Security headers middleware
# ---------------------------------------------------------------------------
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add OWASP-recommended security headers to every response."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; font-src 'self'; connect-src 'self' wss: ws:; "
            "frame-ancestors 'none'"
        )
        response.headers["Strict-Transport-Security"] = (
            "max-age=63072000; includeSubDomains; preload"
        )
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=()"
        )
        return response


from webgui.api import api_router  # noqa: E402
from webgui.realtime import realtime_manager, websocket_handler  # noqa: E402

# ---------------------------------------------------------------------------
# Lifespan — startup / shutdown
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application startup and shutdown."""
    # --- startup ---
    await realtime_manager.initialize()
    logger.info("Realtime manager initialized")

    from webgui.scheduled_reports import scheduled_report_manager

    await scheduled_report_manager.initialize()
    logger.info("Scheduled reports initialized")

    if os.getenv("DATABASE_ENABLED", "false").lower() == "true":
        try:
            from shared.database.models import init_db

            await init_db()
            logger.info("Database initialized")
        except Exception as e:
            logger.warning(f"Database initialization failed: {e}")

    if os.getenv("AGNOS_AGENT_REGISTRATION_ENABLED", "false").lower() == "true":
        try:
            from config.agnos_agent_registration import agent_registry_client

            await agent_registry_client.register_all_agents()
            logger.info("Registered agents with agnosticos")
        except Exception as e:
            logger.warning(f"Agent registration failed: {e}")

    # Auto-register AGNOSTIC as MCP server with SecureYeoman
    try:
        from shared.yeoman_mcp_server import yeoman_mcp_registration

        await yeoman_mcp_registration.register()
    except Exception as e:
        logger.warning(f"YEOMAN MCP auto-registration failed: {e}")

    # Start outbound event push to SecureYeoman
    try:
        from shared.yeoman_event_stream import yeoman_event_push

        await yeoman_event_push.start()
    except Exception as e:
        logger.warning(f"YEOMAN event push startup failed: {e}")

    # Start health monitor for alerts
    from shared.alerts import health_monitor

    await health_monitor.start()

    yield

    # --- shutdown ---
    await health_monitor.stop()
    logger.info("Health monitor stopped")
    await realtime_manager.cleanup()
    logger.info("Realtime manager cleaned up")

    await scheduled_report_manager.shutdown()
    logger.info("Scheduled reports shutdown")

    # Close AGNOS dashboard bridge (httpx client + periodic task)
    try:
        from shared.agnos_dashboard_bridge import agnos_dashboard_bridge

        await agnos_dashboard_bridge.stop()
        logger.info("AGNOS dashboard bridge stopped")
    except Exception as e:
        logger.warning(f"AGNOS dashboard bridge shutdown failed: {e}")

    # Deregister AGNOSTIC MCP server from SecureYeoman
    try:
        from shared.yeoman_mcp_server import yeoman_mcp_registration

        await yeoman_mcp_registration.deregister()
        await yeoman_mcp_registration.close()
        logger.info("YEOMAN MCP server deregistered")
    except Exception as e:
        logger.warning(f"YEOMAN MCP deregistration failed: {e}")

    # Stop outbound event push to SecureYeoman
    try:
        from shared.yeoman_event_stream import yeoman_event_push

        await yeoman_event_push.stop()
        logger.info("YEOMAN event push stopped")
    except Exception as e:
        logger.warning(f"YEOMAN event push shutdown failed: {e}")

    # Close YEOMAN A2A client (httpx client)
    try:
        from shared.yeoman_a2a_client import yeoman_a2a_client

        await yeoman_a2a_client.close()
        logger.info("YEOMAN A2A client closed")
    except Exception as e:
        logger.warning(f"YEOMAN A2A client shutdown failed: {e}")

    # Flush and close AGNOS audit forwarder (buffer + httpx client)
    try:
        from shared.agnos_audit import agnos_audit_forwarder

        await agnos_audit_forwarder.close()
        logger.info("AGNOS audit forwarder closed")
    except Exception as e:
        logger.warning(f"AGNOS audit forwarder shutdown failed: {e}")

    # Close AGNOS token budget client
    try:
        from config.agnos_token_budget import agnos_token_budget

        await agnos_token_budget.close()
        logger.info("AGNOS token budget client closed")
    except Exception as e:
        logger.warning(f"AGNOS token budget client shutdown failed: {e}")

    # Close AGNOS vector store client
    try:
        from shared.agnos_vector_client import agnos_vector_client

        await agnos_vector_client.close()
        logger.info("AGNOS vector client closed")
    except Exception as e:
        logger.warning(f"AGNOS vector client shutdown failed: {e}")

    # Close alert manager HTTP client
    try:
        from shared.alerts import alert_manager

        await alert_manager.close()
        logger.info("Alert manager HTTP client closed")
    except Exception as e:
        logger.warning(f"Alert manager shutdown failed: {e}")

    # Close model manager provider sessions
    try:
        from config.model_manager import model_manager

        await model_manager.close()
        logger.info("Model manager sessions closed")
    except Exception as e:
        logger.warning(f"Model manager shutdown failed: {e}")

    if os.getenv("DATABASE_ENABLED", "false").lower() == "true":
        try:
            from shared.database.models import close_db

            await close_db()
            logger.info("Database connection pool closed")
        except Exception as e:
            logger.warning(f"Database shutdown failed: {e}")

    if os.getenv("AGNOS_AGENT_REGISTRATION_ENABLED", "false").lower() == "true":
        try:
            from config.agnos_agent_registration import agent_registry_client

            await agent_registry_client.deregister_all_agents()
            logger.info("Deregistered agents from agnosticos")
        except Exception as e:
            logger.warning(f"Agent deregistration failed: {e}")


# FastAPI application with health check and REST API
app = FastAPI(lifespan=lifespan)

# ---------------------------------------------------------------------------
# P7 — CORS middleware
# ---------------------------------------------------------------------------
_cors_origins_raw = os.getenv(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:18789,http://localhost:3001",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins_raw.split(",")],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key", "X-Correlation-ID"],
)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(CorrelationIdMiddleware)

app.include_router(api_router)


@app.websocket("/ws/realtime")
async def websocket_endpoint(websocket):
    """WebSocket endpoint for real-time dashboard updates."""
    from webgui.auth import auth_manager

    # Authenticate via token query param
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=1008, reason="Missing authentication token")
        return

    payload = await auth_manager.verify_token(token)
    if not payload:
        await websocket.close(code=1008, reason="Invalid or expired token")
        return

    user_id = payload.get("user_id", "anonymous")
    await websocket_handler.handle_websocket(websocket, user_id)


# ---------------------------------------------------------------------------
# P6 — Enhanced health check
# ---------------------------------------------------------------------------


@app.get("/health")
async def health_check() -> dict[str, Any]:
    """Return infrastructure and agent liveness status."""
    status_details: dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "redis": "ok",
        "rabbitmq": "ok",
        "agents": {},
    }

    # 1. Redis ping
    try:
        redis_client = config.get_redis_client()
        redis_client.ping()
    except Exception as e:
        logger.warning(f"Health check: Redis error: {e}")
        status_details["redis"] = "error"

    # 2. RabbitMQ TCP connect (lightweight — avoids heavy pika import)
    rabbitmq_host = os.getenv("RABBITMQ_HOST", "rabbitmq")
    rabbitmq_port = int(os.getenv("RABBITMQ_PORT", "5672"))
    try:
        sock = socket.create_connection((rabbitmq_host, rabbitmq_port), timeout=2)
        sock.close()
    except Exception as e:
        logger.warning(f"Health check: RabbitMQ error: {e}")
        status_details["rabbitmq"] = "error"

    # 3. Agent liveness via Redis heartbeats
    stale_threshold = int(os.getenv("AGENT_STALE_THRESHOLD_SECONDS", "300"))
    now_ts = datetime.now(UTC).timestamp()

    try:
        agent_defs = _agent_registry.get_agents_for_team()
        agent_names = [a.name.lower().replace(" ", "-") for a in agent_defs]
    except Exception:
        agent_names = [
            "qa-manager",
            "senior-qa",
            "junior-qa",
            "qa-analyst",
            "security-compliance",
            "performance",
        ]

    try:
        redis_client = config.get_redis_client()
        for agent_name in agent_names:
            heartbeat_raw = redis_client.get(f"agent:{agent_name}:status")
            if heartbeat_raw:
                agent_info = json.loads(heartbeat_raw)
                last_hb = agent_info.get("last_heartbeat")
                if last_hb:
                    try:
                        hb_ts = datetime.fromisoformat(last_hb).timestamp()
                        if now_ts - hb_ts <= stale_threshold:
                            status_details["agents"][agent_name] = "alive"
                        else:
                            status_details["agents"][agent_name] = "stale"
                    except ValueError:
                        status_details["agents"][agent_name] = "stale"
                else:
                    status_details["agents"][agent_name] = "offline"
            else:
                status_details["agents"][agent_name] = "offline"
    except Exception as e:
        logger.warning(f"Health check: agent status error: {e}")
        for agent_name in agent_names:
            if agent_name not in status_details["agents"]:
                status_details["agents"][agent_name] = "offline"

    # 4. YEOMAN A2A health (if enabled)
    try:
        from shared.yeoman_a2a_client import yeoman_a2a_client

        if yeoman_a2a_client.enabled:
            breaker = getattr(yeoman_a2a_client, "_breaker", None)
            if breaker:
                status_details["yeoman"] = breaker.state.value
            else:
                status_details["yeoman"] = "enabled"
        else:
            status_details["yeoman"] = "disabled"
    except ImportError:
        status_details["yeoman"] = "unavailable"

    # 5. AGNOS dashboard bridge health (if enabled)
    try:
        from shared.agnos_dashboard_bridge import agnos_dashboard_bridge

        if agnos_dashboard_bridge.enabled:
            breaker = getattr(agnos_dashboard_bridge, "_circuit_breaker", None)
            if breaker:
                status_details["agnos_bridge"] = breaker.state.value
            else:
                status_details["agnos_bridge"] = "enabled"
        else:
            status_details["agnos_bridge"] = "disabled"
    except ImportError:
        status_details["agnos_bridge"] = "unavailable"

    # Determine overall status
    infra_ok = status_details["redis"] == "ok" and status_details["rabbitmq"] == "ok"
    any_alive = any(v == "alive" for v in status_details["agents"].values())

    if not infra_ok:
        overall = "unhealthy"
    elif any_alive:
        overall = "healthy"
    else:
        overall = "degraded"

    status_details["status"] = overall
    return status_details


if __name__ == "__main__":
    # Run Chainlit with FastAPI
    uvicorn.run(app, host="0.0.0.0", port=8000)
