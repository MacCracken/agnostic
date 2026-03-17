import asyncio
import json
import logging
import os
import socket
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import chainlit as cl
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Add config path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.agent_registry import AgentRegistry
from config.environment import config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add the project root to Python path
sys.path.append("/app")


_MAX_ACTIVE_SESSIONS = int(os.getenv("MAX_ACTIVE_SESSIONS", "1000"))


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
        """Submit requirements via the generic crew builder."""
        self._evict_old_sessions()
        try:
            from webgui.routes.crews import CrewRunRequest, run_crew

            crew_req = CrewRunRequest(
                preset="quality-standard",
                title=requirements.get("title", "WebGUI QA Task"),
                description=requirements.get("description", ""),
                target_url=requirements.get("target_url"),
                priority=requirements.get("priority", "high"),
            )

            # Create a minimal user dict for the crew builder
            user = {"user_id": requirements.get("submitted_by", "web_user")}
            crew_result = await run_crew(crew_req, user)

            result = {
                "session_id": crew_result.session_id,
                "crew_id": crew_result.crew_id,
                "task_id": crew_result.task_id,
                "status": crew_result.status,
                "agents": crew_result.agents,
                "test_plan": {
                    "scenarios": [
                        {"name": agent, "priority": "high", "assigned_to": agent}
                        for agent in crew_result.agents
                    ],
                },
            }

            # Update session
            self.active_sessions[session_id]["requirements"] = requirements
            self.active_sessions[session_id]["test_plan"] = result.get("test_plan")
            self.active_sessions[session_id]["status"] = "planning_completed"
            self.active_sessions[session_id]["crew_id"] = crew_result.crew_id

            return result

        except Exception as e:
            logger.error(f"Error submitting requirements: {e}")
            return {"error": str(e), "status": "failed"}

    async def get_session_status(self, session_id: str) -> dict[str, Any]:
        """Get current session status"""
        try:
            if session_id not in self.active_sessions:
                return {"status": "unknown", "session_id": session_id}

            session = self.active_sessions[session_id]

            # If we have a crew_id, check crew status
            crew_id = session.get("crew_id")
            if crew_id:
                try:
                    from webgui.routes.crews import get_crew_status

                    user = {"user_id": "web_user"}
                    crew_status = await get_crew_status(crew_id, user)
                    session["status"] = getattr(
                        crew_status, "status", session["status"]
                    )
                except Exception:
                    pass

            return session

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


@cl.on_chat_end
async def on_chat_end() -> dict[str, Any]:
    """Clean up when chat ends"""
    session_id = cl.user_session.get("session_id")
    if session_id:
        logger.info(f"Ending session: {session_id}")


from webgui.api import api_router  # noqa: E402
from webgui.realtime import realtime_manager, websocket_handler  # noqa: E402

# ---------------------------------------------------------------------------
# Lifespan — startup / shutdown
# ---------------------------------------------------------------------------


_HEARTBEAT_INTERVAL = int(os.getenv("AGNOS_HEARTBEAT_INTERVAL_SECONDS", "30"))


async def _agent_heartbeat_loop(registry_client: Any) -> None:
    """Periodically send heartbeats for all registered agents."""
    from config.agnos_agent_registration import AGNOSTIC_AGENTS

    while True:
        await asyncio.sleep(_HEARTBEAT_INTERVAL)
        for agent_key in AGNOSTIC_AGENTS:
            try:
                await registry_client.send_heartbeat(agent_key, status="idle")
            except Exception:
                pass  # heartbeat failures are logged inside send_heartbeat


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application startup and shutdown."""
    # --- startup ---

    # Apply AGNOS environment profile first (sets env var defaults for dev/staging/prod)
    try:
        from config.agnos_environment import apply_agnos_profile

        profile = apply_agnos_profile()
        if profile:
            logger.info("Applied AGNOS environment profile: %s", profile)
    except Exception as e:
        logger.debug("AGNOS profile not applied: %s", e)

    await realtime_manager.initialize()
    logger.info("Realtime manager initialized")

    scheduled_report_manager = None
    try:
        from webgui.scheduled_reports import scheduled_report_manager

        await scheduled_report_manager.initialize()
        logger.info("Scheduled reports initialized")
    except ImportError:
        logger.debug("Scheduled reports not available (missing pytz)")
    except Exception as e:
        logger.warning("Scheduled reports initialization failed: %s", e)

    if os.getenv("DATABASE_ENABLED", "false").lower() == "true":
        try:
            from shared.database.models import init_db

            await init_db()
            logger.info("Database initialized")
        except Exception as e:
            logger.warning(f"Database initialization failed: {e}")

    heartbeat_task = None
    if os.getenv("AGNOS_AGENT_REGISTRATION_ENABLED", "false").lower() == "true":
        try:
            from config.agnos_agent_registration import agent_registry_client

            await agent_registry_client.register_all_agents()
            logger.info("Registered agents with agnosticos")

            # Start periodic heartbeat loop
            heartbeat_task = asyncio.create_task(
                _agent_heartbeat_loop(agent_registry_client)
            )
        except Exception as e:
            logger.warning(f"Agent registration failed: {e}")

    # Auto-register AGNOSTIC as MCP server with SecureYeoman and daimon
    try:
        from shared.yeoman_mcp_server import (
            daimon_mcp_registration,
            yeoman_mcp_registration,
        )

        await yeoman_mcp_registration.register()
        await daimon_mcp_registration.register()
    except Exception as e:
        logger.warning(f"MCP auto-registration failed: {e}")

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
    if heartbeat_task is not None:
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass
        logger.info("Agent heartbeat loop stopped")

    await health_monitor.stop()
    logger.info("Health monitor stopped")
    await realtime_manager.cleanup()
    logger.info("Realtime manager cleaned up")

    if scheduled_report_manager is not None:
        await scheduled_report_manager.shutdown()
        logger.info("Scheduled reports shutdown")

    # Close webhook delivery httpx client
    try:
        from webgui.routes.tasks import _webhook_http_client

        if _webhook_http_client is not None and not _webhook_http_client.is_closed:
            await _webhook_http_client.aclose()
            logger.info("Webhook HTTP client closed")
    except Exception as e:
        logger.warning(f"Webhook HTTP client shutdown failed: {e}")

    # Close AGNOS clients
    for client_path, client_attr in [
        ("shared.agnos_rpc_client", "agnos_rpc"),
        ("shared.agnos_rag_client", "agnos_rag"),
        ("shared.agnos_screen_client", "agnos_screen"),
        ("shared.agnos_recording_client", "agnos_recording"),
        ("shared.agnos_memory", "agnos_memory"),
        ("shared.agnos_reasoning", "agnos_reasoning"),
        ("shared.yeoman_mcp_server", "daimon_mcp_registration"),
    ]:
        try:
            mod = __import__(client_path, fromlist=[client_attr])
            client = getattr(mod, client_attr)
            await client.close()
        except Exception as e:
            logger.debug("Failed to close %s.%s: %s", client_path, client_attr, e)
    logger.info("AGNOS clients closed")

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


# FastAPI application with health check and REST API (standalone mode)
app = FastAPI(lifespan=lifespan)


def _configure_app(target_app: FastAPI) -> None:
    """Add middleware, routes, and WebSocket endpoints to a FastAPI app."""
    _cors_origins_raw = os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:18789,http://localhost:3001",
    )
    target_app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in _cors_origins_raw.split(",")],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=[
            "Content-Type",
            "Authorization",
            "X-API-Key",
            "X-Correlation-ID",
        ],
    )

    target_app.include_router(api_router)


# Configure the standalone app (used by uvicorn.run in __main__)
_configure_app(app)

# Also configure Chainlit's app so routes work under `chainlit run`
# ---------------------------------------------------------------------------
# P6 — Enhanced health check
# ---------------------------------------------------------------------------


async def health_check() -> JSONResponse:
    """Return infrastructure and agent liveness status.

    Returns HTTP 200 for healthy, 503 for degraded or unhealthy so that
    monitoring systems and load balancers can detect problems.
    """
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
    rabbitmq_url = os.getenv("RABBITMQ_URL")
    rabbitmq_host = os.getenv("RABBITMQ_HOST")
    if rabbitmq_url or rabbitmq_host:
        rabbitmq_host = rabbitmq_host or "rabbitmq"
        rabbitmq_port = int(os.getenv("RABBITMQ_PORT", "5672"))
        try:
            sock = socket.create_connection((rabbitmq_host, rabbitmq_port), timeout=2)
            sock.close()
        except Exception as e:
            logger.warning(f"Health check: RabbitMQ error: {e}")
            status_details["rabbitmq"] = "error"
    else:
        status_details["rabbitmq"] = "not_configured"

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

    # 4. Database health (if enabled)
    if os.getenv("DATABASE_ENABLED", "false").lower() == "true":
        try:
            from sqlalchemy import text

            from shared.database.models import get_session

            session = await get_session()
            try:
                await session.execute(text("SELECT 1"))
                status_details["database"] = "ok"
            finally:
                await session.close()
        except Exception as e:
            logger.warning(f"Health check: database error: {e}")
            status_details["database"] = "error"

    # 5. YEOMAN A2A health (if enabled)
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

    # 6. AGNOS dashboard bridge health (if enabled)
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

    # 7. LLM gateway health (if enabled)
    if os.getenv("AGNOS_LLM_GATEWAY_ENABLED", "").lower() in ("true", "1", "yes"):
        try:
            from config.llm_integration import _llm_circuit

            status_details["llm_gateway"] = _llm_circuit.state.value
        except Exception:
            status_details["llm_gateway"] = "unknown"

    # Determine overall status
    # Redis is critical (webgui needs it); RabbitMQ is optional (workers profile)
    redis_ok = status_details["redis"] == "ok"
    rabbitmq_ok = status_details["rabbitmq"] in ("ok", "not_configured")
    db_ok = status_details.get("database", "ok") in ("ok",)
    any_alive = any(v == "alive" for v in status_details["agents"].values())

    if not redis_ok or not db_ok:
        overall = "unhealthy"
    elif not rabbitmq_ok or not any_alive:
        overall = "degraded"
    else:
        overall = "healthy"

    status_details["status"] = overall

    # Return proper HTTP status code for monitoring systems
    http_status = 503 if overall == "unhealthy" else 200
    return JSONResponse(content=status_details, status_code=http_status)


async def readiness_check() -> JSONResponse:
    """Readiness probe: is the app ready to accept traffic?

    Unlike /health (liveness), readiness checks that critical dependencies
    are initialized. Kubernetes uses this to decide whether to route
    traffic to the pod (vs. /health which decides whether to restart).
    """
    checks: dict[str, str] = {}

    # Redis must be reachable
    try:
        redis_client = config.get_redis_client()
        redis_client.ping()
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "error"

    # Database must be reachable (if enabled)
    if os.getenv("DATABASE_ENABLED", "false").lower() == "true":
        try:
            from sqlalchemy import text

            from shared.database.models import get_session

            session = await get_session()
            try:
                await session.execute(text("SELECT 1"))
                checks["database"] = "ok"
            finally:
                await session.close()
        except Exception:
            checks["database"] = "error"

    all_ok = all(v == "ok" for v in checks.values())
    checks["status"] = "ready" if all_ok else "not_ready"

    return JSONResponse(
        content=checks,
        status_code=200 if all_ok else 503,
    )


async def _websocket_endpoint(websocket):
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


# Register health + readiness + websocket on standalone app
app.get("/health")(health_check)
app.get("/ready")(readiness_check)
app.websocket("/ws/realtime")(_websocket_endpoint)

# Also register on Chainlit's app so routes work under `chainlit run`.
# Chainlit registers a catch-all ``GET /{full_path:path}`` for its SPA at import
# time, so routes added via ``include_router`` after that never match.  The fix
# is to insert our routes *before* the catch-all in the route list.
try:
    from chainlit.server import app as chainlit_app

    # Chainlit's OAuth2PasswordBearerWithCookie is missing the `model` attribute
    # that FastAPI ≥0.115 needs for OpenAPI schema generation, causing an
    # AttributeError on /openapi.json.  Patch it once at import time.
    try:
        from chainlit.auth import OAuth2PasswordBearerWithCookie
        from fastapi.openapi.models import OAuth2 as OAuth2Model
        from fastapi.openapi.models import OAuthFlowPassword, OAuthFlows

        if not hasattr(OAuth2PasswordBearerWithCookie, "model"):
            OAuth2PasswordBearerWithCookie.model = OAuth2Model(
                flows=OAuthFlows(
                    password=OAuthFlowPassword(tokenUrl="auth/login", scopes={})
                )
            )
            OAuth2PasswordBearerWithCookie.scheme_name = (
                "OAuth2PasswordBearerWithCookie"
            )
    except ImportError:
        pass

    _configure_app(chainlit_app)
    chainlit_app.router.lifespan_context = lifespan
    chainlit_app.get("/health")(health_check)
    chainlit_app.websocket("/ws/realtime")(_websocket_endpoint)

    # Move our routes before Chainlit's catch-all ``/{full_path:path}``
    _catchall_indices = [
        i
        for i, r in enumerate(chainlit_app.routes)
        if hasattr(r, "path") and r.path == "/{full_path:path}"
    ]
    if _catchall_indices:
        _catchall_idx = _catchall_indices[0]
        # Routes we just added are at the end — move them before the catch-all
        _our_routes = chainlit_app.routes[_catchall_idx + 1 :]
        del chainlit_app.routes[_catchall_idx + 1 :]
        for _r in reversed(_our_routes):
            chainlit_app.routes.insert(_catchall_idx, _r)
except Exception:
    pass  # Not running under Chainlit


if __name__ == "__main__":
    # Run Chainlit with FastAPI
    uvicorn.run(app, host="0.0.0.0", port=8000)  # nosec B104 — bind all interfaces for container deployment
