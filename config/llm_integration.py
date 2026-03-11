"""
LLM Integration Service for Agentic QA Team System.
Provides real LLM-driven analysis for tools instead of static/mock data.
"""

import json
import logging
import os
import time
from typing import Any

import litellm

from shared.metrics import (
    LLM_CALL_DURATION,
    LLM_CALLS_TOTAL,
    LLM_TOKENS_COMPLETION,
    LLM_TOKENS_PROMPT,
)
from shared.resilience import CircuitBreaker
from shared.telemetry import trace_llm_call

try:
    from config.agnos_token_budget import agnos_token_budget
except ImportError:
    agnos_token_budget = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


def _on_llm_breaker_change(name: str, old_state: str, new_state: str) -> None:
    """Update Prometheus gauge when the LLM circuit breaker changes state."""
    from shared.metrics import CIRCUIT_BREAKER_STATE

    state_values = {"closed": 0, "open": 1, "half_open": 2}
    CIRCUIT_BREAKER_STATE.labels(service=name).set(state_values.get(new_state, -1))
    logger.info("Circuit breaker %s: %s → %s", name, old_state, new_state)


_llm_circuit = CircuitBreaker(
    name="llm_api",
    failure_threshold=5,
    recovery_timeout=60.0,
    on_state_change=_on_llm_breaker_change,
)


class LLMIntegrationService:
    """Service for integrating with various LLM providers for tool implementations."""

    def __init__(
        self,
        model_name: str | None = None,
        temperature: float = 0.3,
        agent_name: str = "unknown",
    ):
        """Initialize LLM service with specified model."""
        self.temperature = temperature
        self.max_tokens = 2000
        self._agent_name = agent_name

        # When AGNOS LLM Gateway is enabled, route all calls through it.
        # The gateway exposes an OpenAI-compatible API; litellm treats it
        # as an "openai/" model with a custom base_url.
        gateway_enabled = os.getenv("AGNOS_LLM_GATEWAY_ENABLED", "").lower() in (
            "true",
            "1",
            "yes",
        )

        if gateway_enabled:
            gateway_url = os.getenv("AGNOS_LLM_GATEWAY_URL", "http://localhost:8088")
            gateway_model = os.getenv("AGNOS_LLM_GATEWAY_MODEL", "default")
            # litellm routes "openai/<model>" to base_url/v1/chat/completions
            self.model_name = f"openai/{gateway_model}"
            self._api_key = os.getenv("AGNOS_LLM_GATEWAY_API_KEY", "")
            self._base_url = f"{gateway_url}/v1"
            self._provider_name = "agnos_gateway"
            self._extra_headers = {"x-agent-id": agent_name}
            logger.info(
                "LLM service routing through AGNOS Gateway at %s (agent=%s)",
                gateway_url,
                agent_name,
            )
        else:
            self.model_name = model_name or os.getenv("OPENAI_MODEL", "gpt-4o")
            self._api_key = os.getenv("OPENAI_API_KEY")
            self._base_url = None
            self._provider_name = self._detect_provider(self.model_name)
            self._extra_headers = {}
            if self._api_key:
                logger.info(f"Initialized LLM service with model: {self.model_name}")
            else:
                logger.warning("OPENAI_API_KEY not set — LLM calls will use fallbacks")

    @staticmethod
    def _detect_provider(model_name: str) -> str:
        """Derive the credential-store provider key from a litellm model string."""
        model_lower = model_name.lower()
        if model_lower.startswith("anthropic/") or "claude" in model_lower:
            return "anthropic"
        if model_lower.startswith("gemini/") or model_lower.startswith("google/"):
            return "google"
        if model_lower.startswith("ollama/"):
            return "ollama"
        return "openai"

    def _resolve_api_key(self) -> str | None:
        """Return the configured API key."""
        return self._api_key

    async def _streaming_call(self, call_kwargs: dict[str, Any], span: Any) -> Any:
        """Execute a streaming LLM call, assembling chunks into a full response.

        Uses ``litellm.acompletion(stream=True)`` which returns an async
        generator of SSE chunks. The chunks are concatenated into a complete
        response object that matches the non-streaming format.
        """
        chunks: list[str] = []
        response_obj = None

        async for chunk in await litellm.acompletion(**call_kwargs):
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and hasattr(delta, "content") and delta.content:
                chunks.append(delta.content)
            # Keep last chunk for usage info (some providers include it on final chunk)
            response_obj = chunk

        # Build a response-like object with assembled content
        full_content = "".join(chunks)

        class _AssembledMessage:
            content = full_content

        class _AssembledChoice:
            message = _AssembledMessage()

        class _AssembledResponse:
            choices = [_AssembledChoice()]
            usage = getattr(response_obj, "usage", None)

        return _AssembledResponse()

    async def _llm_call(
        self,
        method_name: str,
        system_prompt: str,
        user_prompt: str,
        fallback: Any,
        expected_type: type = list,
        *,
        stream: bool = False,
    ) -> Any:
        """Common LLM call wrapper with circuit breaker, metrics, and fallback.

        Returns parsed JSON response or fallback value on failure.
        When *stream* is True and the gateway supports it, uses SSE streaming
        for real-time token output, then assembles the full response.
        """
        api_key = self._resolve_api_key()
        if not api_key or not _llm_circuit.can_execute():
            return fallback

        # --- AGNOS token budget: check & reserve -------------------------
        reservation_id: str | None = None
        if agnos_token_budget and agnos_token_budget.enabled:
            budget_ok = await agnos_token_budget.check_budget(
                self._agent_name, self.max_tokens
            )
            if not budget_ok:
                logger.warning(
                    "AGNOS token budget exhausted for agent=%s — returning fallback",
                    self._agent_name,
                )
                return fallback
            reservation_id = await agnos_token_budget.reserve_tokens(
                self._agent_name, self.max_tokens
            )

        start = time.monotonic()
        try:
            with trace_llm_call(
                method_name, model=self.model_name, agent=self._agent_name
            ) as span:
                call_kwargs: dict[str, Any] = {
                    "model": self.model_name,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": self.temperature,
                    "max_tokens": self.max_tokens,
                    "api_key": api_key,
                    "stream": stream,
                }
                if self._base_url:
                    call_kwargs["base_url"] = self._base_url
                if self._extra_headers:
                    call_kwargs["extra_headers"] = self._extra_headers

                if stream:
                    response = await self._streaming_call(call_kwargs, span)
                else:
                    response = await litellm.acompletion(**call_kwargs)

                content = str(response.choices[0].message.content).strip()
                if content.startswith("```json") and content.endswith("```"):
                    content = content[7:-3].strip()

                parsed = json.loads(content)
                _llm_circuit.record_success()
                LLM_CALLS_TOTAL.labels(method=method_name, status="success").inc()

                prompt_tokens = 0
                completion_tokens = 0
                if hasattr(response, "usage") and response.usage:
                    prompt_tokens = response.usage.prompt_tokens or 0
                    completion_tokens = response.usage.completion_tokens or 0
                    LLM_TOKENS_PROMPT.labels(
                        agent=self._agent_name, method=method_name
                    ).inc(prompt_tokens)
                    LLM_TOKENS_COMPLETION.labels(
                        agent=self._agent_name, method=method_name
                    ).inc(completion_tokens)
                    span.set_attribute("llm.tokens.prompt", prompt_tokens)
                    span.set_attribute("llm.tokens.completion", completion_tokens)

                # --- AGNOS token budget: report actual usage -----------------
                if reservation_id and agnos_token_budget:
                    await agnos_token_budget.report_usage(
                        reservation_id, prompt_tokens, completion_tokens
                    )

                return parsed if isinstance(parsed, expected_type) else fallback

        except Exception as e:
            _llm_circuit.record_failure()
            LLM_CALLS_TOTAL.labels(method=method_name, status="error").inc()
            logger.error(f"LLM {method_name} failed: {e}")
            # --- AGNOS token budget: release unused reservation ----------
            if reservation_id and agnos_token_budget:
                await agnos_token_budget.release_reservation(reservation_id)
            return fallback
        finally:
            LLM_CALL_DURATION.labels(method=method_name).observe(
                time.monotonic() - start
            )

    async def generate_test_scenarios(self, requirements: str) -> list[str]:
        """Generate test scenarios using LLM from requirements."""
        return await self._llm_call(
            method_name="generate_test_scenarios",
            system_prompt="You are an expert QA engineer specializing in test scenario generation.",
            user_prompt=f"""
            As an expert QA engineer, analyze the following requirements and generate comprehensive test scenarios:

            Requirements: {requirements}

            Please generate 5-8 test scenarios that cover:
            1. Functional testing
            2. Integration testing
            3. Performance testing
            4. Security testing
            5. User experience testing

            Return ONLY a JSON array of scenario strings, like:
            ["Scenario 1", "Scenario 2", "Scenario 3"]
            """,
            fallback=self._fallback_scenarios(),
            expected_type=list,
        )

    async def extract_acceptance_criteria(self, requirements: str) -> list[str]:
        """Extract acceptance criteria using LLM from requirements."""
        return await self._llm_call(
            method_name="extract_acceptance_criteria",
            system_prompt="You are an expert QA engineer specializing in requirements analysis.",
            user_prompt=f"""
            As an expert QA engineer, extract detailed acceptance criteria from these requirements:

            Requirements: {requirements}

            Generate 5-7 specific, measurable acceptance criteria that define success.
            Focus on functionality, performance, security, and user experience.

            Return ONLY a JSON array of criteria strings, like:
            ["Criterion 1", "Criterion 2", "Criterion 3"]
            """,
            fallback=self._fallback_criteria(),
            expected_type=list,
        )

    async def identify_test_risks(self, requirements: str) -> list[str]:
        """Identify potential test risks using LLM from requirements."""
        return await self._llm_call(
            method_name="identify_test_risks",
            system_prompt="You are an expert QA risk analyst with deep experience in testing risk identification.",
            user_prompt=f"""
            As a seasoned QA risk analyst, identify potential testing risks from these requirements:

            Requirements: {requirements}

            Identify 4-6 potential risks that could impact testing:
            1. Technical risks
            2. Integration risks
            3. Performance risks
            4. Security risks

            Return ONLY a JSON array of risk descriptions, like:
            ["Risk 1", "Risk 2", "Risk 3"]
            """,
            fallback=self._fallback_risks(),
            expected_type=list,
        )

    async def perform_fuzzy_verification(
        self, test_results: dict[str, Any], business_goals: str
    ) -> dict[str, Any]:
        """Perform LLM-based fuzzy verification of test results."""
        return await self._llm_call(
            method_name="perform_fuzzy_verification",
            system_prompt="You are an expert QA analyst specializing in test result verification and business alignment.",
            user_prompt=f"""
            As an expert QA analyst, perform fuzzy verification of these test results against business goals:

            Test Results: {json.dumps(test_results, indent=2)}
            Business Goals: {business_goals}

            Analyze:
            1. Overall quality score (0.0-1.0)
            2. Confidence level (high/medium/low)
            3. Business alignment (aligned/partial/misaligned)
            4. Specific recommendations

            Consider both quantitative metrics and qualitative factors.
            Return ONLY a JSON object with this exact structure:
            {{
                "overall_score": 0.85,
                "confidence_level": "high",
                "business_alignment": "aligned",
                "recommendations": ["Recommendation 1", "Recommendation 2"]
            }}
            """,
            fallback=self._fallback_verification(test_results, business_goals),
            expected_type=dict,
        )

    async def analyze_security_findings(
        self, scan_results: dict[str, Any]
    ) -> dict[str, Any]:
        """Analyze security findings using LLM intelligence."""
        return await self._llm_call(
            method_name="analyze_security_findings",
            system_prompt="You are a cybersecurity expert specializing in vulnerability analysis and risk assessment.",
            user_prompt=f"""
            As a security expert, analyze these scan results and provide intelligent assessment:

            Scan Results: {json.dumps(scan_results, indent=2)}

            Provide:
            1. Risk level assessment (critical/high/medium/low)
            2. Business impact analysis
            3. Prioritized remediation steps
            4. Compliance implications
            5. Executive summary

            Return ONLY a JSON object with this structure:
            {{
                "risk_level": "high",
                "business_impact": "Data exposure could lead to regulatory fines",
                "remediation_priority": ["Fix authentication bypass", "Update SSL certificates"],
                "compliance_gaps": ["PCI-DSS", "GDPR"],
                "executive_summary": "Multiple high-severity vulnerabilities requiring immediate attention"
            }}
            """,
            fallback=self._fallback_security_analysis(scan_results),
            expected_type=dict,
        )

    async def generate_performance_profile(
        self, performance_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Generate intelligent performance profile analysis."""
        return await self._llm_call(
            method_name="generate_performance_profile",
            system_prompt="You are a performance engineering expert specializing in system optimization and capacity planning.",
            user_prompt=f"""
            As a performance engineering expert, analyze this performance data:

            Performance Data: {json.dumps(performance_data, indent=2)}

            Provide:
            1. Performance grade (A/B/C/D/F)
            2. Bottleneck identification
            3. Optimization recommendations
            4. SLA impact assessment
            5. Capacity planning insights

            Return ONLY a JSON object with this structure:
            {{
                "performance_grade": "B",
                "bottlenecks": ["Database queries", "API response time"],
                "optimization_recommendations": ["Add database indexes", "Implement caching"],
                "sla_impact": "Current response times exceed SLA by 15%",
                "capacity_insights": "Expected load increase of 25% in 6 months"
            }}
            """,
            fallback=self._fallback_performance_analysis(performance_data),
            expected_type=dict,
        )

    def _fallback_scenarios(self) -> list[str]:
        """Fallback scenarios when LLM is unavailable."""
        return [
            "User authentication flow",
            "Data validation and error handling",
            "Performance under load",
            "Security vulnerability assessment",
            "Cross-browser compatibility",
        ]

    def _fallback_criteria(self) -> list[str]:
        """Fallback acceptance criteria when LLM is unavailable."""
        return [
            "System responds within 2 seconds",
            "All input fields properly validated",
            "Session management secure",
            "Error messages user-friendly",
        ]

    def _fallback_risks(self) -> list[str]:
        """Fallback risks when LLM is unavailable."""
        return [
            "Authentication bypass",
            "Data corruption",
            "Performance degradation",
            "UI inconsistency",
        ]

    def _fallback_verification(
        self, test_results: dict[str, Any], business_goals: str
    ) -> dict[str, Any]:
        """Fallback verification when LLM is unavailable."""
        base_score = 0.85
        if test_results.get("failed_tests", 0) > 0:
            base_score -= 0.1 * test_results["failed_tests"]

        return {
            "overall_score": max(0.0, min(1.0, base_score)),
            "confidence_level": "high"
            if test_results.get("test_coverage", 0) > 80
            else "medium",
            "business_alignment": "aligned"
            if test_results.get("pass_rate", 0) > 90
            else "partial",
            "recommendations": self._generate_basic_recommendations(
                test_results, max(0.0, min(1.0, base_score))
            ),
        }

    def _generate_basic_recommendations(
        self, results: dict[str, Any], score: float
    ) -> list[str]:
        """Generate basic recommendations without LLM."""
        recommendations = []
        if score < 0.8:
            recommendations.append("Increase test coverage in critical areas")
        if results.get("failed_tests", 0) > 2:
            recommendations.append("Focus on stabilizing failing test scenarios")
        return recommendations

    def _fallback_security_analysis(
        self, scan_results: dict[str, Any]
    ) -> dict[str, Any]:
        """Fallback security analysis when LLM is unavailable."""
        return {
            "risk_level": "medium",
            "business_impact": "Potential security vulnerabilities detected",
            "remediation_priority": ["Review security headers", "Update dependencies"],
            "compliance_gaps": ["Security best practices"],
            "executive_summary": "Security scan completed with medium priority findings",
        }

    def _fallback_performance_analysis(
        self, performance_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Fallback performance analysis when LLM is unavailable."""
        avg_response_time = performance_data.get("avg_response_time", 1.5)

        if avg_response_time < 1.0:
            grade = "A"
        elif avg_response_time < 2.0:
            grade = "B"
        elif avg_response_time < 3.0:
            grade = "C"
        else:
            grade = "D"

        return {
            "performance_grade": grade,
            "bottlenecks": ["Response time"] if avg_response_time > 2.0 else [],
            "optimization_recommendations": ["Optimize database queries"]
            if avg_response_time > 2.0
            else ["Performance looks good"],
            "sla_impact": f"Grade {grade} performance - {'within' if grade in ['A', 'B'] else 'below'} SLA expectations",
            "capacity_insights": "Monitor load patterns for capacity planning",
        }


# Module-level singleton for agent imports
llm_service = LLMIntegrationService()
