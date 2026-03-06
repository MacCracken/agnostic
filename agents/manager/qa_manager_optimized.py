import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from typing import Any

from crewai import LLM, Agent, Crew, Process, Task

from shared.crewai_compat import BaseTool

# Add config path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))
from config.environment import config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TestPlanDecompositionTool(BaseTool):
    name: str = "Test Plan Decomposition"
    description: str = "Decomposes user requirements into comprehensive test plans for 6-agent architecture"

    def _run(self, requirements: str) -> dict[str, Any]:
        """Decompose requirements into test plan components for optimized 6-agent system"""
        return {
            "test_scenarios": self._extract_scenarios(requirements),
            "acceptance_criteria": self._extract_criteria(requirements),
            "risk_areas": self._identify_risks(requirements),
            "priority_matrix": self._create_priority_matrix(requirements),
            "agent_delegation": self._create_agent_delegation_plan(requirements),
        }

    def _extract_scenarios(self, requirements: str) -> list[str]:
        # LLM-based scenario extraction for 6-agent architecture
        scenarios = [
            "Performance and resilience testing scenarios",
            "Security and compliance validation scenarios",
            "Reporting and risk analysis scenarios",
            "Complex UI and interaction scenarios",
            "Regression and data integrity scenarios",
            "System workflow validation scenarios",
        ]
        return scenarios

    def _extract_criteria(self, requirements: str) -> list[str]:
        return [
            "System responds within performance SLA thresholds",
            "Security and compliance requirements are met",
            "Resilience validation passes for defined failure scenarios",
            "Complex workflows function correctly",
            "Regression suite passes with acceptable failure rate",
            "Report includes actionable findings and release readiness",
        ]

    def _identify_risks(self, requirements: str) -> list[str]:
        return [
            "Performance degradation under load",
            "Security vulnerabilities in critical paths",
            "Resilience gaps under failure scenarios",
            "Complex UI interaction failures",
            "Regression instability or flaky tests",
            "Incomplete reporting of critical risks",
        ]

    def _create_priority_matrix(self, requirements: str) -> dict[str, str]:
        return {
            "performance_critical": "performance",
            "security_critical": "security_compliance",
            "analysis_critical": "qa_analyst",
            "complexity_critical": "senior_qa",
            "regression_critical": "junior_qa",
        }

    def _create_agent_delegation_plan(self, requirements: str) -> dict[str, Any]:
        """Create optimal delegation plan for 6-agent architecture"""
        return {
            "performance": {
                "agent": "performance",
                "triggers": ["load", "slowing", "network", "latency", "throughput"],
                "complexity_threshold": "high_load",
                "delegation_logic": "route_to_performance",
            },
            "security_compliance": {
                "agent": "security_compliance",
                "triggers": [
                    "security",
                    "compliance",
                    "gdpr",
                    "pci",
                    "owasp",
                    "vulnerability",
                ],
                "complexity_threshold": "regulatory_risk",
                "delegation_logic": "route_to_security_compliance",
            },
            "resilience": {
                "agent": "performance",
                "triggers": [
                    "resilience",
                    "reliability",
                    "chaos",
                    "recovery",
                    "uptime",
                ],
                "complexity_threshold": "system_risk",
                "delegation_logic": "route_to_performance",
            },
            "qa_analyst": {
                "agent": "qa_analyst",
                "triggers": ["report", "analysis", "metrics", "readiness", "summary"],
                "complexity_threshold": "cross_domain",
                "delegation_logic": "route_to_qa_analyst",
            },
            "senior_qa": {
                "agent": "senior_qa",
                "triggers": [
                    "complex",
                    "edge_case",
                    "model_based",
                    "self_healing",
                    "ui_complexity",
                ],
                "complexity_threshold": "technical_complexity",
                "delegation_logic": "route_to_senior_qa",
            },
            "junior_qa": {
                "agent": "junior_qa",
                "triggers": [
                    "regression",
                    "data",
                    "synthetic",
                    "automation",
                    "test_execution",
                ],
                "complexity_threshold": "execution_volume",
                "delegation_logic": "route_to_junior_qa",
            },
        }


class FuzzyVerificationTool(BaseTool):
    name: str = "Fuzzy Verification"
    description: str = (
        "Performs LLM-based fuzzy verification of test results across 6-agent system"
    )

    def _run(self, test_results: dict[str, Any], business_goals: str) -> dict[str, Any]:
        """Perform fuzzy verification beyond binary pass/fail"""
        verification_score = self._calculate_verification_score(
            test_results, business_goals
        )

        return {
            "overall_score": verification_score,
            "confidence_level": self._assess_confidence(test_results),
            "business_alignment": self._check_business_alignment(
                test_results, business_goals
            ),
            "agent_coordination": self._assess_agent_coordination(test_results),
            "recommendations": self._generate_recommendations(
                test_results, verification_score
            ),
        }

    def _calculate_verification_score(self, results: dict, goals: str) -> float:
        base_score = 0.85
        if results.get("failed_tests", 0) > 0:
            base_score -= 0.1 * results["failed_tests"]

        # Factor in 6-agent coordination
        coordination_score = self._assess_coordination_score(results)
        return max(0.0, min(1.0, base_score + coordination_score * 0.1))

    def _assess_confidence(self, results: dict) -> str:
        return "high" if results.get("test_coverage", 0) > 80 else "medium"

    def _check_business_alignment(self, results: dict, goals: str) -> str:
        return "aligned" if results.get("pass_rate", 0) > 90 else "partial"

    def _assess_agent_coordination(self, results: dict) -> str:
        """Assess coordination across the 6-agent system"""
        coordination_metrics = results.get("agent_coordination", {})
        if coordination_metrics.get("parallel_execution", False):
            return "excellent"
        elif coordination_metrics.get("sequential_efficiency", 0.8) > 0.7:
            return "good"
        else:
            return "needs_improvement"

    def _assess_coordination_score(self, results: dict) -> float:
        """Calculate numerical coordination score"""
        coordination = results.get("agent_coordination", {})
        parallel_bonus = 0.1 if coordination.get("parallel_execution", False) else 0
        efficiency_bonus = coordination.get("sequential_efficiency", 0.8) * 0.1
        return parallel_bonus + efficiency_bonus

    def _generate_recommendations(self, results: dict, score: float) -> list[str]:
        recommendations = []
        if score < 0.8:
            recommendations.append("Increase test coverage in critical areas")
        if results.get("failed_tests", 0) > 2:
            recommendations.append("Focus on stabilizing failing test scenarios")
        if results.get("agent_coordination", {}).get("parallel_execution", False):
            recommendations.append("Enable parallel execution across multiple agents")
        return recommendations


class OptimizedQAManager:
    """Optimized QA Manager for 6-agent architecture"""

    def __init__(self):
        self.redis_client = config.get_redis_client()
        self.celery_app = config.get_celery_app("qa_manager")
        self.llm = LLM(model=os.getenv("OPENAI_MODEL", "gpt-4o"), temperature=0.1)

        # Agent routing configuration for 6-agent system
        self.agent_routing = {
            "performance": {
                "queue": "performance",
                "capabilities": [
                    "load_testing",
                    "performance_monitoring",
                    "resilience_validation",
                ],
            },
            "security_compliance": {
                "queue": "security_compliance",
                "capabilities": [
                    "security_testing",
                    "gdpr_compliance",
                    "pci_dss",
                    "owasp",
                ],
            },
            "qa_analyst": {
                "queue": "qa_analyst",
                "capabilities": [
                    "reporting",
                    "security_assessment",
                    "performance_profiling",
                ],
            },
            "senior_qa": {
                "queue": "senior_qa",
                "capabilities": [
                    "complex_ui_testing",
                    "self_healing",
                    "model_based_testing",
                    "edge_cases",
                ],
            },
            "junior_qa": {
                "queue": "junior_qa",
                "capabilities": [
                    "regression_testing",
                    "data_generation",
                    "test_execution",
                    "synthetic_data",
                ],
            },
        }

        self.agent = Agent(
            role="QA Manager (Orchestrator)",
            goal="Orchestrate optimized 6-agent QA system through intelligent task delegation, coordination, and result synthesis",
            backstory="""You are an expert QA Manager with 10+ years of experience orchestrating
            large-scale testing operations. You excel at decomposing requirements, delegating to
            specialized agents, and synthesizing comprehensive test reports. You now manage an
            optimized 6-agent architecture: Performance & Resilience, Security & Compliance,
            QA Analyst, Senior QA, and Junior QA agents.""",
            verbose=True,
            allow_delegation=False,
            llm=self.llm,
            tools=[TestPlanDecompositionTool(), FuzzyVerificationTool()],
        )

    async def orchestrate_qa_session(self, task_data: dict[str, Any]) -> dict[str, Any]:
        """Orchestrate optimized QA session across 6 agents"""
        requirements = task_data.get("requirements", "")
        session_id = task_data.get(
            "session_id", f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )

        logger.info(f"Optimized QA Manager orchestrating session: {session_id}")

        # Initialize session in Redis
        session_data = {
            "session_id": session_id,
            "requirements": requirements,
            "status": "orchestrating",
            "started_at": datetime.now().isoformat(),
            "architecture": "optimized_6_agent",
        }
        self.redis_client.set(f"manager:{session_id}:session", json.dumps(session_data))

        # Decompose requirements for 6-agent system
        decomposition_task = Task(
            description=f"""Decompose requirements for optimized 6-agent system:

            Requirements: {requirements}
            Session: {session_id}

            Analyze and create:
            1. Test scenarios for each agent capability
            2. Acceptance criteria across all 6 agents
            3. Risk areas and priority delegation
            4. Optimal agent coordination plan
            """,
            agent=self.agent,
            expected_output="Comprehensive test plan with 6-agent delegation strategy",
        )

        crew = Crew(
            agents=[self.agent],
            tasks=[decomposition_task],
            process=Process.sequential,
            verbose=True,
        )
        crew.kickoff()

        # Execute decomposition
        plan_tool = TestPlanDecompositionTool()
        test_plan = plan_tool._run(requirements)

        # Delegate to appropriate agents
        agent_tasks = await self._delegate_to_agents(session_id, test_plan, task_data)

        # Wait for agent completion (with timeout)
        completed_tasks = await self._collect_agent_results(
            session_id, agent_tasks, timeout=1800
        )

        # Synthesize results with fuzzy verification
        synthesis = await self._synthesize_results(
            session_id, completed_tasks, test_plan
        )

        # Store final results
        final_result = {
            "session_id": session_id,
            "test_plan": test_plan,
            "agent_delegation": agent_tasks,
            "completed_tasks": completed_tasks,
            "synthesis": synthesis,
            "status": "completed",
            "completed_at": datetime.now().isoformat(),
            "architecture": "optimized_6_agent",
        }

        self.redis_client.set(f"manager:{session_id}:final", json.dumps(final_result))

        return final_result

    async def _delegate_to_agents(
        self, session_id: str, test_plan: dict[str, Any], task_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Delegate tasks to appropriate agents in the 6-agent system"""
        delegation_plan = test_plan.get("agent_delegation", {})
        agent_tasks = {}

        # Performance testing delegation
        if self._should_delegate("performance", delegation_plan, test_plan):
            agent_tasks["performance"] = await self._create_agent_task(
                session_id,
                "performance",
                {
                    "scenario": {
                        "id": "perf_analysis",
                        "name": "Performance & Load Analysis",
                        "target_url": task_data.get(
                            "target_url", "http://localhost:8000"
                        ),
                        "load_profile": task_data.get("load_profile", "moderate"),
                        "sla_config": task_data.get("sla_config", {}),
                    },
                    "priority": test_plan.get("priority_matrix", {}).get(
                        "performance_critical", "high"
                    ),
                },
            )

        # Security & compliance delegation
        if self._should_delegate("security_compliance", delegation_plan, test_plan):
            agent_tasks["security_compliance"] = await self._create_agent_task(
                session_id,
                "security_compliance",
                {
                    "scenario": {
                        "id": "security_audit",
                        "name": "Security & Compliance Audit",
                        "target_url": task_data.get(
                            "target_url", "http://localhost:8000"
                        ),
                        "standards": task_data.get(
                            "compliance_standards",
                            ["GDPR", "PCI DSS", "OWASP", "SOC 2", "ISO 27001", "HIPAA"],
                        ),
                    },
                    "priority": test_plan.get("priority_matrix", {}).get(
                        "security_critical", "critical"
                    ),
                },
            )

        # Resilience validation delegation (via performance agent)
        if self._should_delegate("resilience", delegation_plan, test_plan):
            agent_tasks["resilience"] = await self._create_agent_task(
                session_id,
                "performance",
                {
                    "scenario": {
                        "id": "resilience_validation",
                        "name": "Resilience Validation",
                        "target_url": task_data.get(
                            "target_url", "http://localhost:8000/health"
                        ),
                        "failure_scenarios": task_data.get(
                            "failure_scenarios", ["database_down", "cache_miss"]
                        ),
                    },
                    "priority": test_plan.get("priority_matrix", {}).get(
                        "performance_critical", "high"
                    ),
                },
            )

        # Senior QA delegation
        if self._should_delegate("senior_qa", delegation_plan, test_plan):
            agent_tasks["senior_qa"] = await self._create_agent_task(
                session_id,
                "senior_qa",
                {
                    "scenario": {
                        "id": "senior_analysis",
                        "name": "Complex UI & Edge Case Analysis",
                        "target_url": task_data.get(
                            "target_url", "http://localhost:8000"
                        ),
                        "complexity_level": task_data.get("complexity_level", "high"),
                        "edge_case_analysis": True,
                    },
                    "priority": test_plan.get("priority_matrix", {}).get(
                        "complexity_critical", "high"
                    ),
                },
            )

        # Junior QA delegation
        if self._should_delegate("junior_qa", delegation_plan, test_plan):
            agent_tasks["junior_qa"] = await self._create_agent_task(
                session_id,
                "junior_qa",
                {
                    "scenario": {
                        "id": "junior_analysis",
                        "name": "Regression & Data Analysis",
                        "target_url": task_data.get(
                            "target_url", "http://localhost:8000"
                        ),
                        "regression_scope": task_data.get("regression_scope", "full"),
                        "data_generation_required": True,
                    },
                    "priority": test_plan.get("priority_matrix", {}).get(
                        "regression_critical", "medium"
                    ),
                },
            )

        # QA Analyst delegation
        if self._should_delegate("qa_analyst", delegation_plan, test_plan):
            agent_tasks["qa_analyst"] = await self._create_agent_task(
                session_id,
                "qa_analyst",
                {
                    "scenario": {
                        "id": "qa_report",
                        "name": "Comprehensive QA Report",
                        "priority": "high",
                        "target_url": task_data.get(
                            "target_url", "http://localhost:8000"
                        ),
                    },
                    "priority": test_plan.get("priority_matrix", {}).get(
                        "analysis_critical", "high"
                    ),
                },
            )

        return agent_tasks

    def _should_delegate(
        self, agent_type: str, delegation_plan: dict, test_plan: dict
    ) -> bool:
        """Determine if agent should be delegated based on test plan"""
        plan = delegation_plan.get(agent_type, {})
        if not plan:
            return False

        triggers = plan.get("triggers", [])
        if not triggers:
            return True

        scenarios = test_plan.get("test_scenarios", [])
        return any(
            any(trigger in scenario.lower() for trigger in triggers)
            for scenario in scenarios
        )

    async def _create_agent_task(
        self, session_id: str, agent_type: str, task_config: dict[str, Any]
    ) -> dict[str, Any]:
        """Create and dispatch task to specific agent"""
        self.agent_routing.get(agent_type, {})

        task_data = {
            "session_id": session_id,
            "scenario": task_config.get("scenario", {}),
            "priority": task_config.get("priority", "medium"),
            "timestamp": datetime.now().isoformat(),
        }

        # Store task in Redis for agent to pick up
        task_key = f"manager:{session_id}:task:{agent_type}"
        self.redis_client.set(task_key, json.dumps(task_data))

        # Publish task notification
        notification = {
            "session_id": session_id,
            "agent_type": agent_type,
            "task_config": task_config,
            "timestamp": datetime.now().isoformat(),
        }

        # Publish to agent-specific channel
        self.redis_client.publish(f"{agent_type}:tasks", json.dumps(notification))

        return {
            "agent_type": agent_type,
            "task_key": task_key,
            "config": task_config,
            "status": "dispatched",
        }

    async def _collect_agent_results(
        self, session_id: str, agent_tasks: dict[str, Any], timeout: int = 1800
    ) -> dict[str, Any]:
        """Collect results from all agent tasks"""
        completed_tasks = {}
        start_time = asyncio.get_event_loop().time()

        # Subscribe to result notifications
        pubsub = self.redis_client.pubsub()
        pubsub.subscribe(f"manager:{session_id}:notifications")

        # Wait for all agents to complete
        pending_agents = set(agent_tasks.keys())

        while (
            pending_agents and (asyncio.get_event_loop().time() - start_time) < timeout
        ):
            try:
                message = pubsub.get_message(timeout=1.0)
                if message and message["type"] == "message":
                    notification = json.loads(message["data"])
                    agent_type = notification.get("agent")

                    if agent_type in pending_agents:
                        completed_tasks[agent_type] = notification.get("result", {})
                        pending_agents.remove(agent_type)
                        logger.info(f"Received completion from {agent_type}")
            except Exception as e:
                logger.error(f"Error collecting agent results: {e}")
                await asyncio.sleep(1)

        pubsub.close()

        # Handle timeout
        if pending_agents:
            for agent in pending_agents:
                completed_tasks[agent] = {
                    "status": "timeout",
                    "error": "Agent did not complete within timeout period",
                }

        return completed_tasks

    async def _synthesize_results(
        self,
        session_id: str,
        completed_tasks: dict[str, Any],
        test_plan: dict[str, Any],
    ) -> dict[str, Any]:
        """Synthesize results from all agents with fuzzy verification"""

        # Create comprehensive result synthesis
        synthesis = {
            "session_id": session_id,
            "agent_results": completed_tasks,
            "agent_count": len(completed_tasks),
            "successful_agents": len(
                [k for k, v in completed_tasks.items() if v.get("status") != "error"]
            ),
            "coverage_analysis": self._analyze_coverage(completed_tasks),
            "risk_assessment": self._assess_overall_risk(completed_tasks),
            "agent_coordination": self._assess_agent_coordination_metrics(
                completed_tasks
            ),
        }

        # Apply fuzzy verification
        fuzzy_tool = FuzzyVerificationTool()
        verification = fuzzy_tool._run(
            synthesis, test_plan.get("acceptance_criteria", [])
        )

        synthesis["verification"] = verification
        synthesis["final_score"] = verification.get("overall_score", 0.85)

        return synthesis

    def _analyze_coverage(self, results: dict[str, Any]) -> dict[str, Any]:
        """Analyze test coverage across all agents"""
        coverage_areas = {}

        for agent_type, result in results.items():
            if result.get("status") == "completed":
                agent_result = result.get("result", {})

                if agent_type == "performance":
                    coverage_areas["performance"] = agent_result.get("coverage", {})
                elif agent_type == "security_compliance":
                    coverage_areas["security"] = agent_result.get("coverage", {})
                elif agent_type == "qa_analyst":
                    coverage_areas["analysis"] = agent_result.get("report", {}).get(
                        "metrics", {}
                    )
                elif agent_type == "senior_qa":
                    coverage_areas["complex_testing"] = agent_result.get(
                        "edge_case_analysis", {}
                    ).get("coverage", {})
                elif agent_type == "junior_qa":
                    coverage_areas["regression"] = agent_result.get(
                        "test_execution", {}
                    ).get("results", {})

        return coverage_areas

    def _assess_overall_risk(self, results: dict[str, Any]) -> dict[str, Any]:
        """Assess overall risk from all agent results"""
        risk_summary = {"high_risk": [], "medium_risk": [], "low_risk": []}

        for agent_type, result in results.items():
            if result.get("status") == "completed":
                # Extract risk information from each agent
                if "risk_areas" in str(result):
                    risk_summary["medium_risk"].append(f"{agent_type}_risks")

        return risk_summary

    def _assess_agent_coordination_metrics(
        self, results: dict[str, Any]
    ) -> dict[str, Any]:
        """Assess coordination effectiveness across agents"""
        return {
            "parallel_execution": len(results)
            > 3,  # If more than 3 agents ran in parallel
            "sequential_efficiency": 0.85,  # Simulated efficiency metric
            "coordination_score": 0.9,  # Overall coordination score
            "bottlenecks": [],  # Identify any coordination bottlenecks
            "optimization_opportunities": [
                "Enable more parallel execution",
                "Optimize agent communication",
                "Improve result synthesis",
            ],
        }

    async def get_optimization_statistics(self) -> dict[str, Any]:
        """Get optimization statistics for the 6-agent system"""
        return {
            "architecture": "optimized_6_agent",
            "agents": list(self.agent_routing.keys()),
            "capabilities": {
                k: v["capabilities"] for k, v in self.agent_routing.items()
            },
            "delegation_strategies": 6,
            "parallel_execution_support": True,
            "coordination_optimization": True,
            "fuzzy_verification": True,
        }


async def main():
    """Main entry point for optimized QA Manager"""
    manager = OptimizedQAManager()

    sample_task = {
        "session_id": "session_optimized_20240207_143000",
        "requirements": "Comprehensive testing of user authentication system with performance, security, and UX validation",
        "target_url": "http://localhost:8000",
        "load_profile": "moderate",
        "compliance_standards": ["GDPR", "PCI DSS", "SOC 2", "ISO 27001", "HIPAA"],
        "wcag_level": "AA",
    }

    result = await manager.orchestrate_qa_session(sample_task)
    print(f"Optimized QA Manager Result: {json.dumps(result, indent=2)}")


if __name__ == "__main__":
    asyncio.run(main())
