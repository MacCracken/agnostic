"""QA Manager tools — TestPlanDecompositionTool and FuzzyVerificationTool.

These tools are used by quality crew presets (quality-lean, quality-standard, quality-large).
The legacy QAManagerAgent class has been removed — all orchestration
now flows through the generic crew builder (webgui/routes/crews.py).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from shared.crewai_compat import BaseTool

try:
    from config.llm_integration import llm_service
except ImportError:
    llm_service = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


class TestPlanDecompositionTool(BaseTool):
    __test__ = False  # Not a pytest test class
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
            if llm_service is None:
                raise RuntimeError("llm_service not available")
            scenarios_result: Any = llm_service.generate_test_scenarios(requirements)
            if asyncio.iscoroutine(scenarios_result):
                try:
                    asyncio.get_running_loop()
                    import concurrent.futures

                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                        scenarios_result = pool.submit(
                            asyncio.run, scenarios_result
                        ).result()
                except RuntimeError:
                    scenarios_result = asyncio.run(scenarios_result)
            scenarios_list: list[str] = scenarios_result
            logger.info(f"Generated {len(scenarios_list)} test scenarios using LLM")
            return scenarios_list
        except Exception as e:  # Catch-all: tool must not crash the crew
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
            if llm_service is None:
                raise RuntimeError("llm_service not available")
            criteria_result: Any = llm_service.extract_acceptance_criteria(requirements)
            if asyncio.iscoroutine(criteria_result):
                try:
                    asyncio.get_running_loop()
                    import concurrent.futures

                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                        criteria_result = pool.submit(
                            asyncio.run, criteria_result
                        ).result()
                except RuntimeError:
                    criteria_result = asyncio.run(criteria_result)
            criteria_list: list[str] = criteria_result
            logger.info(f"Generated {len(criteria_list)} acceptance criteria using LLM")
            return criteria_list
        except Exception as e:  # Catch-all: tool must not crash the crew
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
            if llm_service is None:
                raise RuntimeError("llm_service not available")
            risks_result: Any = llm_service.identify_test_risks(requirements)
            if asyncio.iscoroutine(risks_result):
                try:
                    asyncio.get_running_loop()
                    import concurrent.futures

                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                        risks_result = pool.submit(asyncio.run, risks_result).result()
                except RuntimeError:
                    risks_result = asyncio.run(risks_result)
            risks_list: list[str] = risks_result
            logger.info(f"Identified {len(risks_list)} test risks using LLM")
            return risks_list
        except Exception as e:  # Catch-all: tool must not crash the crew
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
            if llm_service is None:
                raise RuntimeError("llm_service not available")
            verification = await llm_service.perform_fuzzy_verification(
                test_results, business_goals
            )
            logger.info(
                f"Performed LLM-based fuzzy verification with score: {verification.get('overall_score', 0)}"
            )
            return verification
        except Exception as e:  # Catch-all: tool must not crash the crew
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

    def _calculate_verification_score(
        self, results: dict[str, Any], goals: str
    ) -> float:
        base_score = 0.85
        if results.get("failed_tests", 0) > 0:
            base_score -= 0.1 * results["failed_tests"]
        return max(0.0, min(1.0, base_score))

    def _assess_confidence(self, results: dict[str, Any]) -> str:
        return "high" if results.get("test_coverage", 0) > 80 else "medium"

    def _check_business_alignment(self, results: dict[str, Any], goals: str) -> str:
        return "aligned" if results.get("pass_rate", 0) > 90 else "partial"

    def _generate_recommendations(
        self, results: dict[str, Any], score: float
    ) -> list[str]:
        recommendations = []
        if score < 0.8:
            recommendations.append("Increase test coverage in critical areas")
        if results.get("failed_tests", 0) > 2:
            recommendations.append("Focus on stabilizing failing test scenarios")
        return recommendations
