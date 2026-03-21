"""Tests for the AgnosAI HTTP backend."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from agents.backend.agnosai_backend import AgnosAIBackend, _translate_crew_config


class TestTranslateCrewConfig:
    def test_basic_translation(self):
        config = {
            "title": "Test Crew",
            "agents": [
                {
                    "agent_key": "analyst",
                    "name": "Analyst",
                    "role": "analyst",
                    "goal": "analyze things",
                    "domain": "quality",
                    "tools": ["code_analysis"],
                    "complexity": "high",
                }
            ],
            "tasks": [
                {"description": "Analyze the code", "expected_output": "report"},
            ],
            "process": "sequential",
        }
        result = _translate_crew_config(config)
        assert result["name"] == "Test Crew"
        assert len(result["agents"]) == 1
        assert result["agents"][0]["agent_key"] == "analyst"
        assert result["agents"][0]["domain"] == "quality"
        assert len(result["tasks"]) == 1
        assert result["tasks"][0]["description"] == "Analyze the code"
        assert result["process"] == "sequential"

    def test_fallback_single_task(self):
        config = {
            "title": "Simple Crew",
            "description": "Do something",
            "agents": [
                {"role": "worker", "goal": "work"},
            ],
        }
        result = _translate_crew_config(config)
        assert len(result["tasks"]) == 1
        assert result["tasks"][0]["description"] == "Do something"

    def test_gpu_fields_included_when_set(self):
        config = {
            "agents": [
                {
                    "agent_key": "gpu-agent",
                    "name": "GPU Agent",
                    "role": "trainer",
                    "goal": "train model",
                    "gpu_required": True,
                    "gpu_memory_min_mb": 8192,
                }
            ],
        }
        result = _translate_crew_config(config)
        agent = result["agents"][0]
        assert agent["gpu_required"] is True
        assert agent["gpu_memory_min_mb"] == 8192

    def test_multiple_tasks_with_dependencies(self):
        config = {
            "agents": [{"role": "worker", "goal": "work"}],
            "tasks": [
                {"description": "task A"},
                {"description": "task B", "dependencies": [0]},
            ],
        }
        result = _translate_crew_config(config)
        assert len(result["tasks"]) == 2
        assert result["tasks"][1]["dependencies"] == [0]


def _mock_response(
    status_code: int = 200, json_data: dict | None = None, text: str = ""
) -> httpx.Response:
    """Build a fake httpx.Response."""
    import json as _json

    content = (
        _json.dumps(json_data).encode() if json_data is not None else text.encode()
    )
    headers = {"content-type": "application/json"} if json_data is not None else {}
    return httpx.Response(
        status_code=status_code,
        request=httpx.Request("POST", "http://test"),
        content=content,
        headers=headers,
    )


class TestAgnosAIBackendExecute:
    @pytest.mark.asyncio
    async def test_successful_execution(self):
        """Mock a successful AgnosAI crew execution."""
        resp = _mock_response(
            200,
            json_data={
                "crew_id": "abc-123",
                "status": "completed",
                "results": [
                    {"task_id": "t1", "output": "done", "status": "completed"},
                ],
            },
        )
        mock_client = AsyncMock()
        mock_client.post.return_value = resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "agents.backend.agnosai_backend.httpx.AsyncClient", return_value=mock_client
        ):
            backend = AgnosAIBackend(base_url="http://test:8080")
            result = await backend.execute_crew(
                crew_config={
                    "title": "test",
                    "agents": [{"role": "w", "goal": "g"}],
                    "tasks": [{"description": "do"}],
                },
                session_id="s1",
                crew_id="c1",
                task_id="t1",
            )

        assert result.status == "completed"
        assert "t1" in result.agent_results
        assert result.error is None

    @pytest.mark.asyncio
    async def test_server_error(self):
        """AgnosAI returns 500."""
        resp = _mock_response(500, text="internal error")
        mock_client = AsyncMock()
        mock_client.post.return_value = resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "agents.backend.agnosai_backend.httpx.AsyncClient", return_value=mock_client
        ):
            backend = AgnosAIBackend(base_url="http://test:8080")
            result = await backend.execute_crew(
                crew_config={
                    "agents": [{"role": "w", "goal": "g"}],
                    "tasks": [{"description": "do"}],
                },
                session_id="s1",
                crew_id="c1",
                task_id="t1",
            )

        assert result.status == "failed"
        assert "500" in result.error

    @pytest.mark.asyncio
    async def test_connection_refused(self):
        """AgnosAI server unreachable."""
        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.ConnectError("Connection refused")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "agents.backend.agnosai_backend.httpx.AsyncClient", return_value=mock_client
        ):
            backend = AgnosAIBackend(base_url="http://test:8080")
            result = await backend.execute_crew(
                crew_config={
                    "agents": [{"role": "w", "goal": "g"}],
                    "tasks": [{"description": "do"}],
                },
                session_id="s1",
                crew_id="c1",
                task_id="t1",
            )

        assert result.status == "failed"
        assert "unreachable" in result.error.lower()


class TestTranslateCrewConfigSources:
    """Verify _translate_crew_config handles all crew_config shapes."""

    def test_agent_definitions_key(self):
        """Should read from agent_definitions when agents key is absent."""
        config = {
            "title": "Inline Crew",
            "agent_definitions": [
                {
                    "agent_key": "worker",
                    "name": "Worker",
                    "role": "worker",
                    "goal": "work",
                },
            ],
            "description": "test task",
        }
        result = _translate_crew_config(config)
        assert len(result["agents"]) == 1
        assert result["agents"][0]["agent_key"] == "worker"

    def test_agents_key_preferred_over_agent_definitions(self):
        """When both keys exist, agents takes precedence."""
        config = {
            "agents": [
                {"agent_key": "primary", "role": "primary", "goal": "lead"},
            ],
            "agent_definitions": [
                {"agent_key": "fallback", "role": "fallback", "goal": "backup"},
            ],
        }
        result = _translate_crew_config(config)
        assert len(result["agents"]) == 1
        assert result["agents"][0]["agent_key"] == "primary"

    def test_empty_agents_falls_through_to_agent_definitions(self):
        """Empty agents list should fall through to agent_definitions."""
        config = {
            "agents": [],
            "agent_definitions": [
                {"agent_key": "backup", "role": "backup", "goal": "work"},
            ],
        }
        result = _translate_crew_config(config)
        assert len(result["agents"]) == 1
        assert result["agents"][0]["agent_key"] == "backup"


class TestAgnosAIBackendCancel:
    @pytest.mark.asyncio
    async def test_cancel_success(self):
        resp = _mock_response(200, json_data={"status": "cancelled"})
        mock_client = AsyncMock()
        mock_client.post.return_value = resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "agents.backend.agnosai_backend.httpx.AsyncClient", return_value=mock_client
        ):
            backend = AgnosAIBackend(base_url="http://test:8080")
            result = await backend.cancel_crew("abc-123")

        assert result["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_server_error(self):
        resp = _mock_response(500, text="error")
        mock_client = AsyncMock()
        mock_client.post.return_value = resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "agents.backend.agnosai_backend.httpx.AsyncClient", return_value=mock_client
        ):
            backend = AgnosAIBackend(base_url="http://test:8080")
            result = await backend.cancel_crew("abc-123")

        assert "error" in result

    @pytest.mark.asyncio
    async def test_cancel_unreachable(self):
        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.ConnectError("Connection refused")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "agents.backend.agnosai_backend.httpx.AsyncClient", return_value=mock_client
        ):
            backend = AgnosAIBackend(base_url="http://test:8080")
            result = await backend.cancel_crew("abc-123")

        assert "unreachable" in result["error"].lower()
