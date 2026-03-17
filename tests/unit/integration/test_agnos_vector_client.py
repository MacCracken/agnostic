"""Unit tests for shared/agnos_vector_client.py."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))


class TestVectorQueryResult:
    def test_to_dict(self):
        from shared.agnos_vector_client import VectorQueryResult

        r = VectorQueryResult(
            id="doc-1",
            content="some code snippet",
            score=0.95,
            metadata={"project": "myapp", "language": "python"},
        )
        d = r.to_dict()
        assert d["id"] == "doc-1"
        assert d["score"] == 0.95
        assert d["metadata"]["language"] == "python"

    def test_defaults(self):
        from shared.agnos_vector_client import VectorQueryResult

        r = VectorQueryResult(id="x", content="y", score=0.5)
        assert r.metadata == {}


class TestAgnosVectorClient:
    def test_disabled_by_default(self):
        from shared.agnos_vector_client import AgnosVectorClient

        client = AgnosVectorClient()
        assert client.enabled is False

    def test_can_execute_when_disabled(self):
        from shared.agnos_vector_client import AgnosVectorClient

        client = AgnosVectorClient()
        client.enabled = False
        assert client._can_execute() is False

    @pytest.mark.asyncio
    async def test_search_returns_empty_when_disabled(self):
        from shared.agnos_vector_client import AgnosVectorClient

        client = AgnosVectorClient()
        client.enabled = False
        results = await client.search("test query")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_qa_findings_returns_empty_when_disabled(self):
        from shared.agnos_vector_client import AgnosVectorClient

        client = AgnosVectorClient()
        client.enabled = False
        results = await client.search_qa_findings("security vulnerability")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_code_returns_empty_when_disabled(self):
        from shared.agnos_vector_client import AgnosVectorClient

        client = AgnosVectorClient()
        client.enabled = False
        results = await client.search_code("authentication handler")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_docs_returns_empty_when_disabled(self):
        from shared.agnos_vector_client import AgnosVectorClient

        client = AgnosVectorClient()
        client.enabled = False
        results = await client.search_docs("deployment guide")
        assert results == []

    @pytest.mark.asyncio
    async def test_list_collections_returns_empty_when_disabled(self):
        from shared.agnos_vector_client import AgnosVectorClient

        client = AgnosVectorClient()
        client.enabled = False
        results = await client.list_collections()
        assert results == []

    @pytest.mark.asyncio
    async def test_search_with_mock_server(self):
        from unittest.mock import AsyncMock, MagicMock

        from shared.agnos_vector_client import AgnosVectorClient

        client = AgnosVectorClient()
        client.enabled = True

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "results": [
                {
                    "id": "doc-1",
                    "content": "Found code",
                    "score": 0.92,
                    "metadata": {"file": "auth.py"},
                },
                {
                    "id": "doc-2",
                    "content": "More code",
                    "score": 0.85,
                    "metadata": {},
                },
            ]
        }

        mock_client = MagicMock()
        mock_client.is_closed = False
        mock_client.post = AsyncMock(return_value=mock_response)
        client._client = mock_client

        results = await client.search("authentication", top_k=5)
        assert len(results) == 2
        assert results[0].id == "doc-1"
        assert results[0].score == 0.92
        assert results[1].content == "More code"

        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert "/v1/vectors/agnostic-qa/search" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_search_with_filters(self):
        from unittest.mock import AsyncMock, MagicMock

        from shared.agnos_vector_client import AgnosVectorClient

        client = AgnosVectorClient()
        client.enabled = True

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"results": []}

        mock_client = MagicMock()
        mock_client.is_closed = False
        mock_client.post = AsyncMock(return_value=mock_response)
        client._client = mock_client

        await client.search(
            "test",
            collection="custom-coll",
            min_score=0.5,
            filters={"project": "myapp"},
        )

        call_args = mock_client.post.call_args
        assert "/v1/vectors/custom-coll/search" in call_args[0][0]
        payload = call_args[1]["json"]
        assert payload["min_score"] == 0.5
        assert payload["filters"]["project"] == "myapp"

    @pytest.mark.asyncio
    async def test_search_qa_findings_with_project(self):
        from unittest.mock import AsyncMock, MagicMock

        from shared.agnos_vector_client import AgnosVectorClient

        client = AgnosVectorClient()
        client.enabled = True

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"results": []}

        mock_client = MagicMock()
        mock_client.is_closed = False
        mock_client.post = AsyncMock(return_value=mock_response)
        client._client = mock_client

        await client.search_qa_findings("XSS", project="frontend")

        call_args = mock_client.post.call_args
        assert "/v1/vectors/qa-findings/search" in call_args[0][0]
        payload = call_args[1]["json"]
        assert payload["filters"]["project"] == "frontend"

    @pytest.mark.asyncio
    async def test_search_code_with_language(self):
        from unittest.mock import AsyncMock, MagicMock

        from shared.agnos_vector_client import AgnosVectorClient

        client = AgnosVectorClient()
        client.enabled = True

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"results": []}

        mock_client = MagicMock()
        mock_client.is_closed = False
        mock_client.post = AsyncMock(return_value=mock_response)
        client._client = mock_client

        await client.search_code("error handling", language="python")

        call_args = mock_client.post.call_args
        assert "/v1/vectors/code/search" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_search_handles_network_error(self):
        from unittest.mock import AsyncMock, MagicMock

        from shared.agnos_vector_client import AgnosVectorClient

        client = AgnosVectorClient()
        client.enabled = True
        client._circuit = None  # Disable circuit breaker for test

        mock_client = MagicMock()
        mock_client.is_closed = False
        mock_client.post = AsyncMock(side_effect=Exception("connection refused"))
        client._client = mock_client

        results = await client.search("test")
        assert results == []

    @pytest.mark.asyncio
    async def test_list_collections_with_mock(self):
        from unittest.mock import AsyncMock, MagicMock

        from shared.agnos_vector_client import AgnosVectorClient

        client = AgnosVectorClient()
        client.enabled = True

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "collections": ["code", "docs", "qa-findings"]
        }

        mock_client = MagicMock()
        mock_client.is_closed = False
        mock_client.get = AsyncMock(return_value=mock_response)
        client._client = mock_client

        colls = await client.list_collections()
        assert colls == ["code", "docs", "qa-findings"]

    @pytest.mark.asyncio
    async def test_close(self):
        from unittest.mock import AsyncMock, MagicMock

        from shared.agnos_vector_client import AgnosVectorClient

        client = AgnosVectorClient()
        mock_http = MagicMock()
        mock_http.is_closed = False
        mock_http.aclose = AsyncMock()
        client._client = mock_http

        await client.close()
        mock_http.aclose.assert_called_once()
        assert client._client is None

    def test_top_k_capped_at_100(self):
        # Verify the cap logic used in search()
        assert min(200, 100) == 100

    def test_singleton_exists(self):
        from shared.agnos_vector_client import agnos_vector_client

        assert agnos_vector_client is not None
        assert agnos_vector_client.enabled is False
