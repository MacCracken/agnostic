"""
AGNOS ReasoningTrace API Client.

Submits structured chain-of-thought traces from QA agent decisions
to the AGNOS ReasoningTrace API for unified dashboard visibility.

Configure via:
- AGNOS_REASONING_ENABLED: Enable trace submission (default: false)
- AGNOS_REASONING_URL: AGNOS reasoning endpoint base URL
- AGNOS_REASONING_API_KEY: API key for AGNOS reasoning API
"""

import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

try:
    import httpx

    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False


@dataclass
class ReasoningStep:
    """A single step in a QA reasoning trace."""

    phase: str  # "planning", "execution", "analysis", "verdict"
    agent_id: str
    description: str
    input_summary: str
    output_summary: str
    confidence: float  # 0.0-1.0
    timestamp: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(UTC).isoformat()


@dataclass
class ReasoningTrace:
    """A complete chain-of-thought trace for a QA session."""

    trace_id: str
    session_id: str
    task_description: str
    steps: list[ReasoningStep] = field(default_factory=list)
    final_verdict: str | None = None
    overall_confidence: float = 0.0
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = datetime.now(UTC).isoformat()


class AgnosReasoningClient:
    """Client for AGNOS ReasoningTrace REST API."""

    def __init__(self) -> None:
        self.enabled = (
            os.getenv("AGNOS_REASONING_ENABLED", "false").lower() == "true"
            and _HTTPX_AVAILABLE
        )
        self.base_url = os.getenv("AGNOS_REASONING_URL", "http://localhost:8090")
        self.api_key = os.getenv("AGNOS_REASONING_API_KEY", "")
        self._client: httpx.AsyncClient | None = None

        try:
            from shared.resilience import CircuitBreaker

            self._circuit = CircuitBreaker(
                name="agnos_reasoning", failure_threshold=5, recovery_timeout=60.0
            )
        except ImportError:
            self._circuit = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={"X-API-Key": self.api_key},
                timeout=5.0,
            )
        return self._client

    def _can_execute(self) -> bool:
        if not self.enabled:
            return False
        if self._circuit and not self._circuit.can_execute():
            return False
        return True

    def _record_success(self) -> None:
        if self._circuit:
            self._circuit.record_success()

    def _record_failure(self) -> None:
        if self._circuit:
            self._circuit.record_failure()

    def _correlation_headers(self) -> dict[str, str]:
        """Include X-Correlation-ID if available."""
        headers: dict[str, str] = {}
        try:
            from webgui.app import correlation_id_ctx

            cid = correlation_id_ctx.get()
            if cid:
                headers["X-Correlation-ID"] = cid
        except (ImportError, LookupError):
            pass
        return headers

    async def submit_trace(self, trace: ReasoningTrace) -> bool:
        """Submit a complete reasoning trace to AGNOS."""
        if not self._can_execute():
            return False
        try:
            client = self._get_client()
            payload = asdict(trace)
            response = await client.post(
                "/api/v1/reasoning/traces",
                json=payload,
                headers=self._correlation_headers(),
            )
            response.raise_for_status()
            self._record_success()
            logger.debug("Submitted reasoning trace %s", trace.trace_id)
            return True
        except Exception as exc:
            self._record_failure()
            logger.debug("Failed to submit reasoning trace: %s", exc)
            return False

    async def append_step(self, trace_id: str, step: ReasoningStep) -> bool:
        """Append a step to an existing reasoning trace."""
        if not self._can_execute():
            return False
        try:
            client = self._get_client()
            response = await client.post(
                f"/api/v1/reasoning/traces/{trace_id}/steps",
                json=asdict(step),
                headers=self._correlation_headers(),
            )
            response.raise_for_status()
            self._record_success()
            return True
        except Exception as exc:
            self._record_failure()
            logger.debug("Failed to append reasoning step: %s", exc)
            return False

    async def finalize_trace(
        self, trace_id: str, verdict: str, confidence: float
    ) -> bool:
        """Finalize a trace with a verdict and confidence score."""
        if not self._can_execute():
            return False
        try:
            client = self._get_client()
            response = await client.put(
                f"/api/v1/reasoning/traces/{trace_id}/verdict",
                json={"verdict": verdict, "confidence": confidence},
                headers=self._correlation_headers(),
            )
            response.raise_for_status()
            self._record_success()
            logger.debug("Finalized reasoning trace %s", trace_id)
            return True
        except Exception as exc:
            self._record_failure()
            logger.debug("Failed to finalize reasoning trace: %s", exc)
            return False

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()


agnos_reasoning = AgnosReasoningClient()
