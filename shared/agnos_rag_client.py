"""
AGNOS RAG (Retrieval-Augmented Generation) Client.

Ingests QA documentation and compliance specs into the AGNOS vector store
and queries for grounded context to enrich agent responses.

Configure via:
- AGNOS_RAG_ENABLED: Enable RAG ingestion and querying (default: false)
- AGNOS_AGENT_REGISTRY_URL: Daimon base URL (shared with agent registration)
- AGNOS_AGENT_API_KEY: API key for daimon (shared with agent registration)
"""

import asyncio
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

AGNOS_PATH_PREFIX = os.getenv("AGNOS_PATH_PREFIX", "/v1")

try:
    import httpx

    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False


class RagChunk:
    """A single chunk returned from a RAG query."""

    __slots__ = ("content", "metadata", "score")

    def __init__(
        self,
        content: str,
        score: float,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.content = content
        self.score = score
        self.metadata = metadata or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "score": self.score,
            "metadata": self.metadata,
        }


class AgnosRagClient:
    """Client for AGNOS RAG ingest and query endpoints."""

    def __init__(self) -> None:
        self.enabled = (
            os.getenv("AGNOS_RAG_ENABLED", "false").lower() == "true"
            and _HTTPX_AVAILABLE
        )
        self.base_url = os.getenv("AGNOS_AGENT_REGISTRY_URL", "http://localhost:8090")
        self.api_key = os.getenv("AGNOS_AGENT_API_KEY", "")
        self._client: httpx.AsyncClient | None = None
        self._client_lock = asyncio.Lock()

        try:
            from shared.resilience import CircuitBreaker

            self._circuit = CircuitBreaker(
                name="agnos_rag", failure_threshold=5, recovery_timeout=60.0
            )
        except ImportError:
            self._circuit = None

    async def _get_client(self) -> "httpx.AsyncClient":
        async with self._client_lock:
            if self._client is None or self._client.is_closed:
                self._client = httpx.AsyncClient(
                    base_url=self.base_url,
                    headers={"X-API-Key": self.api_key} if self.api_key else {},
                    timeout=30.0,
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

    # ------------------------------------------------------------------
    # Ingest
    # ------------------------------------------------------------------

    async def ingest(
        self,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Ingest a document into the AGNOS vector store.

        Args:
            text: Document text to ingest (will be chunked server-side).
            metadata: Optional metadata tags (e.g. framework, source).

        Returns:
            Dict with status and chunk count, or error info.
        """
        if not self._can_execute():
            return {"status": "disabled"}

        try:
            client = await self._get_client()
            payload: dict[str, Any] = {"text": text}
            if metadata:
                payload["metadata"] = metadata
            response = await client.post(
                f"{AGNOS_PATH_PREFIX}/rag/ingest",
                json=payload,
            )
            response.raise_for_status()
            self._record_success()
            result = response.json()
            logger.info(
                "Ingested document (%d chars, %d chunks)",
                len(text),
                result.get("chunks", 0),
            )
            return result
        except Exception as exc:
            self._record_failure()
            logger.warning("RAG ingest failed: %s", exc)
            return {"status": "error", "message": str(exc)}

    async def ingest_batch(
        self,
        documents: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Ingest multiple documents sequentially.

        Args:
            documents: List of dicts with "text" and optional "metadata" keys.

        Returns:
            List of ingest results, one per document.
        """
        results = []
        for doc in documents:
            result = await self.ingest(
                text=doc["text"],
                metadata=doc.get("metadata"),
            )
            results.append(result)
        return results

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    async def query(
        self,
        query: str,
        *,
        top_k: int = 5,
    ) -> list[RagChunk]:
        """Query the RAG store for relevant context.

        Args:
            query: Semantic search query string.
            top_k: Maximum number of chunks to return.

        Returns:
            List of RagChunk results sorted by descending relevance.
        """
        if not self._can_execute():
            return []

        try:
            client = await self._get_client()
            response = await client.post(
                f"{AGNOS_PATH_PREFIX}/rag/query",
                json={"query": query, "top_k": top_k},
            )
            response.raise_for_status()
            self._record_success()
            data = response.json()
            return [
                RagChunk(
                    content=chunk["content"],
                    score=chunk.get("score", 0.0),
                    metadata=chunk.get("metadata", {}),
                )
                for chunk in data.get("chunks", [])
            ]
        except Exception as exc:
            self._record_failure()
            logger.debug("RAG query failed: %s", exc)
            return []

    async def query_formatted(
        self,
        query: str,
        *,
        top_k: int = 5,
    ) -> str:
        """Query and return a pre-formatted context string for LLM prompts.

        Returns:
            Formatted context string, or empty string on failure.
        """
        if not self._can_execute():
            return ""

        try:
            client = await self._get_client()
            response = await client.post(
                f"{AGNOS_PATH_PREFIX}/rag/query",
                json={"query": query, "top_k": top_k},
            )
            response.raise_for_status()
            self._record_success()
            data = response.json()
            return data.get("formatted_context", "")
        except Exception as exc:
            self._record_failure()
            logger.debug("RAG formatted query failed: %s", exc)
            return ""

    # ------------------------------------------------------------------
    # Convenience methods for common QA knowledge domains
    # ------------------------------------------------------------------

    async def query_compliance(
        self, framework: str, topic: str, *, top_k: int = 5
    ) -> list[RagChunk]:
        """Query compliance framework knowledge (OWASP, GDPR, PCI DSS, etc.)."""
        return await self.query(f"{framework}: {topic}", top_k=top_k)

    async def query_security(self, topic: str, *, top_k: int = 5) -> list[RagChunk]:
        """Query security knowledge base (OWASP Top 10, CVEs, best practices)."""
        return await self.query(f"security: {topic}", top_k=top_k)

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()


agnos_rag = AgnosRagClient()
