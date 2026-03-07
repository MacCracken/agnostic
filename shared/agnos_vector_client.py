"""
AGNOS Vector Store Query Client.

REST client for querying an embedded vector store for cross-project
knowledge: code snippets, documentation, prior QA findings.  Enables
QA agents to leverage broader codebase context when planning and
analysing tests.

Configure via:
- AGNOS_VECTOR_ENABLED: Enable vector store queries (default: false)
- AGNOS_VECTOR_URL: Vector store API base URL (default: http://localhost:8090)
- AGNOS_VECTOR_API_KEY: API key for authentication
- AGNOS_VECTOR_COLLECTION: Default collection name (default: agnostic-qa)
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

try:
    import httpx

    _HTTPX_AVAILABLE = True
except ImportError:  # pragma: no cover
    httpx = None  # type: ignore[assignment]
    _HTTPX_AVAILABLE = False


class VectorQueryResult:
    """A single result from a vector similarity search."""

    __slots__ = ("content", "id", "metadata", "score")

    def __init__(
        self,
        id: str,
        content: str,
        score: float,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.id = id
        self.content = content
        self.score = score
        self.metadata = metadata or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "score": self.score,
            "metadata": self.metadata,
        }


class AgnosVectorClient:
    """Client for AGNOS embedded vector store REST API."""

    def __init__(self) -> None:
        self.enabled = (
            os.getenv("AGNOS_VECTOR_ENABLED", "false").lower() in ("true", "1", "yes")
            and _HTTPX_AVAILABLE
        )
        self.base_url = os.getenv("AGNOS_VECTOR_URL", "http://localhost:8090").rstrip(
            "/"
        )
        self.api_key = os.getenv("AGNOS_VECTOR_API_KEY", "")
        self.default_collection = os.getenv("AGNOS_VECTOR_COLLECTION", "agnostic-qa")
        self._client: httpx.AsyncClient | None = None  # type: ignore[name-defined]

        try:
            from shared.resilience import CircuitBreaker

            self._circuit = CircuitBreaker(
                name="agnos_vector", failure_threshold=5, recovery_timeout=60.0
            )
        except ImportError:
            self._circuit = None

    def _get_client(self) -> httpx.AsyncClient:  # type: ignore[name-defined]
        if not _HTTPX_AVAILABLE:
            raise RuntimeError("httpx is not installed")
        if self._client is None or self._client.is_closed:
            headers: dict[str, str] = {"Content-Type": "application/json"}
            if self.api_key:
                headers["X-API-Key"] = self.api_key
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=headers,
                timeout=10.0,
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

    async def search(
        self,
        query: str,
        *,
        collection: str | None = None,
        top_k: int = 5,
        min_score: float = 0.0,
        filters: dict[str, Any] | None = None,
    ) -> list[VectorQueryResult]:
        """Search the vector store by semantic similarity.

        Args:
            query: Natural-language search query.
            collection: Collection name (defaults to ``AGNOS_VECTOR_COLLECTION``).
            top_k: Maximum number of results to return.
            min_score: Minimum similarity score threshold (0.0-1.0).
            filters: Optional metadata filters (e.g. ``{"project": "myapp"}``).

        Returns:
            List of :class:`VectorQueryResult` sorted by descending score.
        """
        if not self._can_execute():
            return []

        payload: dict[str, Any] = {
            "query": query,
            "top_k": min(top_k, 100),
        }
        if min_score > 0:
            payload["min_score"] = min_score
        if filters:
            payload["filters"] = filters

        coll = collection or self.default_collection
        try:
            client = self._get_client()
            resp = await client.post(
                f"/api/v1/vectors/{coll}/search",
                json=payload,
            )
            resp.raise_for_status()
            self._record_success()

            results = []
            for item in resp.json().get("results", []):
                results.append(
                    VectorQueryResult(
                        id=item.get("id", ""),
                        content=item.get("content", ""),
                        score=item.get("score", 0.0),
                        metadata=item.get("metadata"),
                    )
                )
            return results

        except Exception as exc:
            self._record_failure()
            logger.debug("AGNOS vector search failed: %s", exc)
            return []

    async def search_qa_findings(
        self,
        query: str,
        *,
        top_k: int = 10,
        project: str | None = None,
    ) -> list[VectorQueryResult]:
        """Search prior QA findings relevant to a query.

        Convenience wrapper that searches the ``qa-findings`` collection
        with an optional project filter.
        """
        filters = {}
        if project:
            filters["project"] = project
        return await self.search(
            query,
            collection="qa-findings",
            top_k=top_k,
            filters=filters or None,
        )

    async def search_code(
        self,
        query: str,
        *,
        top_k: int = 5,
        language: str | None = None,
    ) -> list[VectorQueryResult]:
        """Search code snippets by semantic similarity.

        Convenience wrapper for the ``code`` collection.
        """
        filters = {}
        if language:
            filters["language"] = language
        return await self.search(
            query,
            collection="code",
            top_k=top_k,
            filters=filters or None,
        )

    async def search_docs(
        self,
        query: str,
        *,
        top_k: int = 5,
    ) -> list[VectorQueryResult]:
        """Search documentation by semantic similarity."""
        return await self.search(
            query,
            collection="docs",
            top_k=top_k,
        )

    async def list_collections(self) -> list[str]:
        """List available vector store collections."""
        if not self._can_execute():
            return []
        try:
            client = self._get_client()
            resp = await client.get("/api/v1/vectors/collections")
            resp.raise_for_status()
            self._record_success()
            return resp.json().get("collections", [])
        except Exception as exc:
            self._record_failure()
            logger.debug("AGNOS vector list_collections failed: %s", exc)
            return []

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None


# Module-level singleton
agnos_vector_client = AgnosVectorClient()
