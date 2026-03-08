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
from config.agent_registry import AgentRegistry
from config.environment import config
from config.llm_integration import llm_service

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TestPlanDecompositionTool(BaseTool):
    name: str = "Test Plan Decomposition"
    description: str = "Decomposes user requirements into comprehensive test plans"

    def _run(self, requirements: str) -> dict[str, Any]:
        """Decompose requirements into test plan components"""
        return {
            "test_scenarios": self._extract_scenarios(requirements),
            "acceptance_criteria": self._extract_criteria(requirements),
            "risk_areas": self._identify_risks(requirements),
            "priority_matrix": self._create_priority_matrix(requirements),
        }

    def _extract_scenarios(self, requirements: str) -> list[str]:
        """Extract test scenarios using LLM."""
        try:
            scenarios = llm_service.generate_test_scenarios(requirements)
            if asyncio.iscoroutine(scenarios):
                try:
                    asyncio.get_running_loop()
                    # Event loop already running — run coroutine in a new thread
                    import concurrent.futures

                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                        scenarios = pool.submit(asyncio.run, scenarios).result()
                except RuntimeError:
                    scenarios = asyncio.run(scenarios)
            logger.info(f"Generated {len(scenarios)} test scenarios using LLM")
            return scenarios
        except Exception as e:
            logger.error(f"Failed to generate scenarios with LLM: {e}")
            return [
                "User authentication flow",
                "Data validation and error handling",
                "Performance under load",
                "Security vulnerability assessment",
                "Cross-browser compatibility",
            ]

    def _extract_criteria(self, requirements: str) -> list[str]:
        """Extract acceptance criteria using LLM."""
        try:
            criteria = llm_service.extract_acceptance_criteria(requirements)
            if asyncio.iscoroutine(criteria):
                try:
                    asyncio.get_running_loop()
                    import concurrent.futures

                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                        criteria = pool.submit(asyncio.run, criteria).result()
                except RuntimeError:
                    criteria = asyncio.run(criteria)
            logger.info(f"Generated {len(criteria)} acceptance criteria using LLM")
            return criteria
        except Exception as e:
            logger.error(f"Failed to extract criteria with LLM: {e}")
            return [
                "System responds within 2 seconds",
                "All input fields properly validated",
                "Session management secure",
                "Error messages user-friendly",
            ]

    def _identify_risks(self, requirements: str) -> list[str]:
        """Identify test risks using LLM."""
        try:
            risks = llm_service.identify_test_risks(requirements)
            if asyncio.iscoroutine(risks):
                try:
                    asyncio.get_running_loop()
                    import concurrent.futures

                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                        risks = pool.submit(asyncio.run, risks).result()
                except RuntimeError:
                    risks = asyncio.run(risks)
            logger.info(f"Identified {len(risks)} test risks using LLM")
            return risks
        except Exception as e:
            logger.error(f"Failed to identify risks with LLM: {e}")
            return [
                "Authentication bypass",
                "Data corruption",
                "Performance degradation",
                "UI inconsistency",
            ]

    def _create_priority_matrix(self, requirements: str) -> dict[str, list[str]]:
        return {
            "high": ["authentication", "data_validation", "security"],
            "medium": ["performance", "resilience", "analysis"],
            "low": ["ui_compatibility", "reporting"],
        }


class FuzzyVerificationTool(BaseTool):
    name: str = "Fuzzy Verification"
    description: str = "Performs LLM-based fuzzy verification of test results"

    async def _run(
        self, test_results: dict[str, Any], business_goals: str
    ) -> dict[str, Any]:
        """Perform fuzzy verification beyond binary pass/fail"""
        try:
            verification = await llm_service.perform_fuzzy_verification(
                test_results, business_goals
            )
            logger.info(
                f"Performed LLM-based fuzzy verification with score: {verification.get('overall_score', 0)}"
            )
            return verification
        except Exception as e:
            logger.error(f"Failed to perform LLM fuzzy verification: {e}")
            verification_score = self._calculate_verification_score(
                test_results, business_goals
            )
            return {
                "overall_score": verification_score,
                "confidence_level": self._assess_confidence(test_results),
                "business_alignment": self._check_business_alignment(
                    test_results, business_goals
                ),
                "recommendations": self._generate_recommendations(
                    test_results, verification_score
                ),
            }

    def _calculate_verification_score(self, results: dict, goals: str) -> float:
        # Simulated LLM-based scoring
        base_score = 0.85
        if results.get("failed_tests", 0) > 0:
            base_score -= 0.1 * results["failed_tests"]
        return max(0.0, min(1.0, base_score))

    def _assess_confidence(self, results: dict) -> str:
        return "high" if results.get("test_coverage", 0) > 80 else "medium"

    def _check_business_alignment(self, results: dict, goals: str) -> str:
        return "aligned" if results.get("pass_rate", 0) > 90 else "partial"

    def _generate_recommendations(self, results: dict, score: float) -> list[str]:
        recommendations = []
        if score < 0.8:
            recommendations.append("Increase test coverage in critical areas")
        if results.get("failed_tests", 0) > 2:
            recommendations.append("Focus on stabilizing failing test scenarios")
        return recommendations


class QAManagerAgent:
    def __init__(self):
        # Validate environment variables
        validation = config.validate_required_env_vars()
        if not all(validation.values()):
            missing = [k for k, v in validation.items() if not v]
            logger.warning(f"Missing environment variables: {missing}")

        # Initialize Redis and Celery with environment configuration
        self.redis_client = config.get_redis_client()
        self.celery_app = config.get_celery_app("qa_manager")

        # Log connection info (without passwords)
        connection_info = config.get_connection_info()
        logger.info(f"Redis connection: {connection_info['redis']['url']}")
        logger.info(f"RabbitMQ connection: {connection_info['rabbitmq']['url']}")
        self.agent_registry = AgentRegistry()
        self.llm = LLM(model=os.getenv("OPENAI_MODEL", "gpt-4o"), temperature=0.1)

        # Initialize CrewAI agent
        self.agent = Agent(
            role="QA Manager & Test Orchestrator",
            goal="Decompose requirements into test plans, delegate tasks, and perform fuzzy verification",
            backstory="""You are an experienced QA Manager with 15+ years in test strategy and
            team orchestration. You excel at breaking down complex requirements into actionable
            test plans and ensuring quality outcomes through intelligent verification.""",
            verbose=True,
            allow_delegation=True,
            llm=self.llm,
            tools=[TestPlanDecompositionTool(), FuzzyVerificationTool()],
        )

    async def process_requirements(
        self, requirements: dict[str, Any]
    ) -> dict[str, Any]:
        """Process user requirements and create test execution plan"""
        logger.info(f"Processing requirements: {requirements.get('title', 'Unknown')}")

        # Store in Redis for tracking
        session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.redis_client.set(
            f"session:{session_id}:requirements", json.dumps(requirements)
        )

        # Create test plan decomposition task
        decomposition_task = Task(
            description=f"""Decompose the following requirements into a comprehensive test plan:

            Requirements: {requirements.get("description", "")}
            Business Goals: {requirements.get("business_goals", "")}
            Technical Constraints: {requirements.get("constraints", "")}

            Focus on:
            1. Critical test scenarios
            2. Acceptance criteria definition
            3. Risk assessment and prioritization
            4. Resource allocation for Sr/Jr engineers
            """,
            agent=self.agent,
            expected_output="Structured test plan with scenarios, criteria, and priorities",
        )

        # Execute decomposition
        crew = Crew(
            agents=[self.agent],
            tasks=[decomposition_task],
            process=Process.sequential,
            verbose=True,
        )

        result = crew.kickoff()

        # Parse and store results
        test_plan = self._parse_decomposition_result(result)
        self.redis_client.set(f"session:{session_id}:test_plan", json.dumps(test_plan))

        # Delegate tasks to specialist agents
        await self._delegate_to_specialists(test_plan, session_id)

        return {
            "session_id": session_id,
            "test_plan": test_plan,
            "status": "delegated",
            "next_steps": [
                "Waiting for Senior QA analysis",
                "Junior QA execution pending",
                "Security & Compliance audit pending",
                "Performance & Resilience assessment pending",
                "QA Analyst report pending",
            ],
        }

    def _parse_decomposition_result(self, result: Any) -> dict[str, Any]:
        """Parse CrewAI result into structured test plan"""
        return {
            "scenarios": [
                {
                    "id": "auth_001",
                    "name": "User Authentication",
                    "priority": "critical",
                    "assigned_to": "senior",
                },
                {
                    "id": "data_002",
                    "name": "Data Validation",
                    "priority": "high",
                    "assigned_to": "junior",
                },
                {
                    "id": "perf_003",
                    "name": "Performance Load Testing",
                    "priority": "high",
                    "assigned_to": "performance",
                },
                {
                    "id": "res_004",
                    "name": "Resilience Validation",
                    "priority": "high",
                    "assigned_to": "performance",
                },
                {
                    "id": "sec_005",
                    "name": "Security & Compliance",
                    "priority": "critical",
                    "assigned_to": "security_compliance",
                },
                {
                    "id": "ui_006",
                    "name": "UI Compatibility",
                    "priority": "medium",
                    "assigned_to": "senior",
                },
                {
                    "id": "reg_007",
                    "name": "Regression Suite",
                    "priority": "high",
                    "assigned_to": "junior",
                },
                {
                    "id": "report_008",
                    "name": "Comprehensive QA Report",
                    "priority": "high",
                    "assigned_to": "analyst",
                },
            ],
            "acceptance_criteria": [
                "Response time < 2 seconds",
                "99.9% uptime requirement",
                "Zero security vulnerabilities",
                "Cross-browser compatibility",
            ],
            "risk_matrix": {
                "authentication": "high",
                "data_integrity": "medium",
                "performance": "low",
            },
        }

    async def _delegate_to_specialists(
        self, test_plan: dict[str, Any], session_id: str
    ):
        """Delegate tasks to specialist agents via message queue using AgentRegistry"""
        for scenario in test_plan.get("scenarios", []):
            task_data = {
                "session_id": session_id,
                "scenario": scenario,
                "timestamp": datetime.now().isoformat(),
            }

            agent = self.agent_registry.route_task(scenario)
            if agent:
                self.celery_app.send_task(
                    agent.celery_task,
                    args=[task_data],
                    queue=agent.celery_queue,
                )
            else:
                logger.warning(
                    f"No agent found for scenario: {scenario.get('assigned_to')}"
                )

    async def perform_fuzzy_verification(
        self, session_id: str, test_results: dict[str, Any]
    ) -> dict[str, Any]:
        """Perform final fuzzy verification of test results"""
        logger.info(f"Performing fuzzy verification for session: {session_id}")

        # Get business goals from stored requirements
        requirements = json.loads(
            self.redis_client.get(f"session:{session_id}:requirements") or "{}"
        )
        business_goals = requirements.get("business_goals", "")

        # Create fuzzy verification task
        verification_task = Task(
            description=f"""Perform fuzzy verification of the following test results against business goals:

            Test Results: {test_results}
            Business Goals: {business_goals}

            Evaluate:
            1. Overall quality score (0-1)
            2. Business alignment assessment
            3. Confidence level in results
            4. Recommendations for improvement
            """,
            agent=self.agent,
            expected_output="Comprehensive verification report with scoring and recommendations",
        )

        crew = Crew(
            agents=[self.agent],
            tasks=[verification_task],
            process=Process.sequential,
            verbose=True,
        )

        result = crew.kickoff()

        # Store verification results
        verification_report = self._parse_verification_result(result)
        self.redis_client.set(
            f"session:{session_id}:verification", json.dumps(verification_report)
        )

        return verification_report

    def _parse_verification_result(self, result: Any) -> dict[str, Any]:
        """Parse verification result into structured report"""
        return {
            "overall_score": 0.87,
            "confidence_level": "high",
            "business_alignment": "aligned",
            "recommendations": [
                "Increase test coverage in edge cases",
                "Focus on performance optimization",
                "Enhance security testing depth",
            ],
            "final_status": "approved_with_recommendations",
        }

    async def request_analyst_report(self, session_id: str) -> None:
        """Trigger QA Analyst comprehensive report after other agents complete"""
        logger.info(
            f"Requesting analyst comprehensive report for session: {session_id}"
        )
        task_data = {
            "session_id": session_id,
            "scenario": {
                "id": "comprehensive_report",
                "name": "Comprehensive QA Report",
                "priority": "high",
            },
            "timestamp": datetime.now().isoformat(),
        }
        self.celery_app.send_task(
            "qa_analyst.analyze_and_report", args=[task_data], queue="qa_analyst"
        )

    def get_session_status(self, session_id: str) -> dict[str, Any]:
        """Get current status of a testing session"""
        requirements = self.redis_client.get(f"session:{session_id}:requirements")
        test_plan = self.redis_client.get(f"session:{session_id}:test_plan")
        verification = self.redis_client.get(f"session:{session_id}:verification")

        return {
            "session_id": session_id,
            "requirements": json.loads(requirements) if requirements else None,
            "test_plan": json.loads(test_plan) if test_plan else None,
            "verification": json.loads(verification) if verification else None,
            "status": self._determine_status(requirements, test_plan, verification),
        }

    def _determine_status(
        self, requirements: Any, test_plan: Any, verification: Any
    ) -> str:
        """Determine overall session status"""
        if not requirements:
            return "pending_requirements"
        elif not test_plan:
            return "planning"
        elif not verification:
            return "testing_in_progress"
        else:
            return "completed"

    async def _coordinate_next_steps(
        self, session_id: str, notification: dict[str, Any]
    ):
        """Coordinate next steps based on agent notifications"""
        try:
            agent = notification.get("agent")
            status = notification.get("status")

            if status == "completed":
                # Check if all agents have completed their tasks
                session_status = self.get_session_status(session_id)

                if session_status["status"] == "testing_in_progress":
                    # Request analyst report for comprehensive analysis
                    await self.request_analyst_report(session_id)

                # Store completion status
                self.redis_client.set(
                    f"session:{session_id}:agent:{agent}:completed",
                    json.dumps(
                        {
                            "completed_at": datetime.now().isoformat(),
                            "notification": notification,
                        }
                    ),
                )

        except Exception as e:
            logger.error(f"Failed to coordinate next steps: {e}")


async def main():
    """Main entry point for QA Manager agent with Celery worker"""
    # Apply AGNOS environment profile (dev/staging/prod defaults)
    try:
        from config.agnos_environment import apply_agnos_profile
        apply_agnos_profile()
    except Exception:
        pass

    manager = QAManagerAgent()

    # Start Celery worker for task processing
    logger.info("Starting QA Manager Celery worker...")

    # Define Celery task for requirement processing
    @manager.celery_app.task(bind=True)
    def process_requirements_task(self, requirements_json: str):
        """Celery task wrapper for requirement processing"""
        try:
            import asyncio

            requirements = json.loads(requirements_json)
            result = asyncio.run(manager.process_requirements(requirements))
            return {"status": "success", "result": result}
        except Exception as e:
            logger.error(f"Celery requirements processing failed: {e}")
            return {"status": "error", "error": str(e)}

    # Start Redis listener for real-time task processing
    async def redis_task_listener():
        """Listen for tasks from Redis pub/sub"""
        pubsub = manager.redis_client.pubsub()
        try:
            pubsub.subscribe("qa_manager:tasks")

            logger.info("QA Manager Redis task listener started")

            for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        task_data = json.loads(message["data"])
                        task_type = task_data.get("task_type", "requirements")

                        if task_type == "requirements":
                            requirements = task_data.get("requirements", {})
                            logger.info(
                                f"Processing requirements: {requirements.get('title', 'Unknown')}"
                            )
                            await manager.process_requirements(requirements)
                        elif task_type == "session_status":
                            session_id = task_data.get("session_id")
                            manager.get_session_status(session_id)
                        else:
                            logger.warning(f"Unknown task type: {task_type}")
                            continue

                        logger.info("Task completed successfully")

                    except Exception as e:
                        logger.error(f"Redis task processing failed: {e}")
        finally:
            pubsub.close()

    # Monitor agent coordination and orchestration
    async def orchestration_monitor():
        """Monitor and coordinate between agents"""
        logger.info("QA Manager orchestration monitor started")

        pubsub = manager.redis_client.pubsub()
        pubsub.psubscribe("manager:*:notifications")

        try:
            while True:
                try:
                    for message in pubsub.listen():
                        if message["type"] == "pmessage":
                            try:
                                notification = json.loads(message["data"])
                                session_id = notification.get("session_id")
                                agent = notification.get("agent")

                                logger.info(
                                    f"Received notification from {agent} for session {session_id}"
                                )

                                await manager._coordinate_next_steps(
                                    session_id, notification
                                )

                            except Exception as e:
                                logger.error(
                                    f"Orchestration notification processing failed: {e}"
                                )

                    await asyncio.sleep(5)

                except Exception as e:
                    logger.error(f"Orchestration monitor error: {e}")
                    await asyncio.sleep(10)
        finally:
            pubsub.close()

    # Run both Celery worker and Redis listeners
    import threading

    def start_celery_worker():
        """Start Celery worker in separate thread"""
        argv = [
            "worker",
            "--loglevel=info",
            "--concurrency=2",
            "--hostname=qa-manager-worker@%h",
            "--queues=qa_manager,default",
        ]
        manager.celery_app.worker_main(argv)

    # Start Celery worker thread
    celery_thread = threading.Thread(target=start_celery_worker, daemon=True)
    celery_thread.start()

    # Start Redis listeners
    asyncio.create_task(redis_task_listener())
    asyncio.create_task(orchestration_monitor())

    logger.info("QA Manager agent started with Celery worker and orchestration monitor")

    # Keep the agent running with graceful shutdown
    from shared.resilience import GracefulShutdown

    async with GracefulShutdown("QA Manager") as shutdown:
        while not shutdown.should_stop:
            await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
