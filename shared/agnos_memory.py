"""
AGNOS AgentMemoryStore Client.

Provides persistent key-value storage scoped per agent via the AGNOS
AgentMemoryStore REST API. Survives container restarts without volume mounts.

Configure via:
- AGNOS_MEMORY_ENABLED: Enable persistent memory (default: false)
- AGNOS_MEMORY_URL: AGNOS memory endpoint base URL
- AGNOS_MEMORY_API_KEY: API key for AGNOS memory store
"""

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

try:
    import httpx

    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False


class AgnosMemoryClient:
    """Client for AGNOS AgentMemoryStore REST API."""

    def __init__(self) -> None:
        self.enabled = (
            os.getenv("AGNOS_MEMORY_ENABLED", "false").lower() == "true"
            and _HTTPX_AVAILABLE
        )
        self.base_url = os.getenv("AGNOS_MEMORY_URL", "http://localhost:8090")
        self.api_key = os.getenv("AGNOS_MEMORY_API_KEY", "")
        self._client: httpx.AsyncClient | None = None

        try:
            from shared.resilience import CircuitBreaker

            self._circuit = CircuitBreaker(
                name="agnos_memory", failure_threshold=5, recovery_timeout=60.0
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

    async def store(
        self, agent_id: str, key: str, value: Any, namespace: str = "default"
    ) -> bool:
        """Store a value in AGNOS memory."""
        if not self._can_execute():
            return False
        try:
            client = self._get_client()
            response = await client.put(
                f"/api/v1/memory/{agent_id}/{namespace}/{key}",
                json={"value": value},
            )
            response.raise_for_status()
            self._record_success()
            return True
        except Exception as exc:
            self._record_failure()
            logger.debug("AGNOS memory store failed: %s", exc)
            return False

    async def retrieve(
        self, agent_id: str, key: str, namespace: str = "default"
    ) -> Any | None:
        """Retrieve a value from AGNOS memory."""
        if not self._can_execute():
            return None
        try:
            client = self._get_client()
            response = await client.get(f"/api/v1/memory/{agent_id}/{namespace}/{key}")
            response.raise_for_status()
            self._record_success()
            data = response.json()
            return data.get("value")
        except Exception as exc:
            self._record_failure()
            logger.debug("AGNOS memory retrieve failed: %s", exc)
            return None

    async def list_keys(self, agent_id: str, namespace: str = "default") -> list[str]:
        """List all keys for an agent in a namespace."""
        if not self._can_execute():
            return []
        try:
            client = self._get_client()
            response = await client.get(f"/api/v1/memory/{agent_id}/{namespace}")
            response.raise_for_status()
            self._record_success()
            return response.json().get("keys", [])
        except Exception as exc:
            self._record_failure()
            logger.debug("AGNOS memory list_keys failed: %s", exc)
            return []

    async def delete(self, agent_id: str, key: str, namespace: str = "default") -> bool:
        """Delete a key from AGNOS memory."""
        if not self._can_execute():
            return False
        try:
            client = self._get_client()
            response = await client.delete(
                f"/api/v1/memory/{agent_id}/{namespace}/{key}"
            )
            response.raise_for_status()
            self._record_success()
            return True
        except Exception as exc:
            self._record_failure()
            logger.debug("AGNOS memory delete failed: %s", exc)
            return False

    async def retrieve_batch(
        self, agent_id: str, keys: list[str], namespace: str = "default"
    ) -> list[Any]:
        """Retrieve multiple keys in a single request (avoids N+1)."""
        if not self._can_execute() or not keys:
            return []
        try:
            client = self._get_client()
            response = await client.post(
                f"/api/v1/memory/{agent_id}/{namespace}/batch",
                json={"keys": keys},
            )
            response.raise_for_status()
            self._record_success()
            return response.json().get("values", [])
        except Exception:
            # Fallback to sequential retrieval if batch endpoint unavailable
            results = []
            for key in keys:
                val = await self.retrieve(agent_id, key, namespace=namespace)
                results.append(val)
            return results

    async def store_pattern(self, agent_id: str, pattern: dict) -> bool:
        """Store a test pattern (convenience for 'patterns' namespace)."""
        key = pattern.get("name", f"pattern_{id(pattern)}")
        return await self.store(agent_id, key, pattern, namespace="patterns")

    async def get_patterns(self, agent_id: str) -> list[dict]:
        """Retrieve all stored test patterns."""
        keys = await self.list_keys(agent_id, namespace="patterns")
        values = await self.retrieve_batch(agent_id, keys, namespace="patterns")
        return [v for v in values if isinstance(v, dict)]

    async def store_risk_model(self, agent_id: str, model: dict) -> bool:
        """Store a risk model (convenience for 'risk_models' namespace)."""
        key = model.get("name", f"model_{id(model)}")
        return await self.store(agent_id, key, model, namespace="risk_models")

    async def get_risk_models(self, agent_id: str) -> list[dict]:
        """Retrieve all stored risk models."""
        keys = await self.list_keys(agent_id, namespace="risk_models")
        values = await self.retrieve_batch(agent_id, keys, namespace="risk_models")
        return [v for v in values if isinstance(v, dict)]

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()


agnos_memory = AgnosMemoryClient()
