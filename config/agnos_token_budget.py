"""
AGNOS Token Budget Integration.

Draws from AGNOS shared token budget pools instead of per-project accounting.
Checks budget before LLM calls and reports usage after.

Open-by-default: if the budget service is unreachable the call is allowed
so that QA workloads are never blocked by a sidecar outage.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

try:
    import httpx

    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False

try:
    from shared.resilience import CircuitBreaker

    _budget_circuit: CircuitBreaker | None = CircuitBreaker(
        name="agnos_token_budget", failure_threshold=5, recovery_timeout=30.0
    )
except ImportError:
    _budget_circuit = None

_TIMEOUT = 5.0  # seconds


class AgnosTokenBudgetClient:
    """Client for the AGNOS shared token budget service."""

    def __init__(self) -> None:
        self.enabled = (
            os.getenv("AGNOS_TOKEN_BUDGET_ENABLED", "false").lower() == "true"
            and _HTTPX_AVAILABLE
        )
        self.base_url = os.getenv(
            "AGNOS_TOKEN_BUDGET_URL", "http://localhost:8088"
        ).rstrip("/")
        self.api_key = os.getenv("AGNOS_TOKEN_BUDGET_API_KEY", "")
        self.pool = os.getenv("AGNOS_TOKEN_BUDGET_POOL", "agnostic-qa")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    def _pool_url(self, path: str) -> str:
        return f"{self.base_url}/api/v1/budget/pools/{self.pool}{path}"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def check_budget(self, agent_id: str, estimated_tokens: int) -> bool:
        """Check whether *estimated_tokens* are available for *agent_id*.

        Returns ``True`` if budget is available **or** the service is
        unreachable (open-by-default).
        """
        if not self.enabled:
            return True
        if _budget_circuit and not _budget_circuit.can_execute():
            logger.warning("Token budget circuit open -- allowing call")
            return True

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(
                    self._pool_url("/check"),
                    params={"agent": agent_id, "tokens": estimated_tokens},
                    headers=self._headers(),
                )
                resp.raise_for_status()
                data = resp.json()
                if _budget_circuit:
                    _budget_circuit.record_success()
                return bool(data.get("allowed", True))
        except Exception as exc:
            if _budget_circuit:
                _budget_circuit.record_failure()
            logger.warning("Token budget check failed (allowing call): %s", exc)
            return True

    async def reserve_tokens(self, agent_id: str, tokens: int) -> str | None:
        """Reserve *tokens* for *agent_id*.

        Returns a ``reservation_id`` on success, or ``None`` if the
        reservation could not be made (caller should still proceed).
        """
        if not self.enabled:
            return None
        if _budget_circuit and not _budget_circuit.can_execute():
            return None

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.post(
                    self._pool_url("/reserve"),
                    json={"agent": agent_id, "tokens": tokens},
                    headers=self._headers(),
                )
                resp.raise_for_status()
                data = resp.json()
                if _budget_circuit:
                    _budget_circuit.record_success()
                return data.get("reservation_id")
        except Exception as exc:
            if _budget_circuit:
                _budget_circuit.record_failure()
            logger.warning("Token budget reserve failed: %s", exc)
            return None

    async def report_usage(
        self,
        reservation_id: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> bool:
        """Report actual token usage for a completed reservation."""
        if not self.enabled:
            return False
        if _budget_circuit and not _budget_circuit.can_execute():
            return False

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.post(
                    self._pool_url("/usage"),
                    json={
                        "reservation_id": reservation_id,
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                    },
                    headers=self._headers(),
                )
                resp.raise_for_status()
                if _budget_circuit:
                    _budget_circuit.record_success()
                return True
        except Exception as exc:
            if _budget_circuit:
                _budget_circuit.record_failure()
            logger.warning("Token budget usage report failed: %s", exc)
            return False

    async def get_remaining(self, agent_id: str) -> int | None:
        """Return remaining token budget for *agent_id*, or ``None`` on error."""
        if not self.enabled:
            return None
        if _budget_circuit and not _budget_circuit.can_execute():
            return None

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(
                    self._pool_url("/remaining"),
                    params={"agent": agent_id},
                    headers=self._headers(),
                )
                resp.raise_for_status()
                data = resp.json()
                if _budget_circuit:
                    _budget_circuit.record_success()
                return int(data.get("remaining", 0))
        except Exception as exc:
            if _budget_circuit:
                _budget_circuit.record_failure()
            logger.warning("Token budget remaining query failed: %s", exc)
            return None

    async def release_reservation(self, reservation_id: str) -> bool:
        """Release an unused reservation (e.g. after a failed LLM call)."""
        if not self.enabled:
            return False
        if _budget_circuit and not _budget_circuit.can_execute():
            return False

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.delete(
                    self._pool_url(f"/reserve/{reservation_id}"),
                    headers=self._headers(),
                )
                resp.raise_for_status()
                if _budget_circuit:
                    _budget_circuit.record_success()
                return True
        except Exception as exc:
            if _budget_circuit:
                _budget_circuit.record_failure()
            logger.warning("Token budget release failed: %s", exc)
            return False


# Module-level singleton
agnos_token_budget = AgnosTokenBudgetClient()
