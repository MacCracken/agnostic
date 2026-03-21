"""Tests for the AgnosAI HTTP backend."""

import json

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


class TestAgnosAIBackendExecute:
    @pytest.mark.asyncio
    async def test_successful_execution(self, httpx_mock):
        """Mock a successful AgnosAI crew execution."""
        httpx_mock.add_response(
            url="http://test:8080/api/v1/crews",
            method="POST",
            json={
                "crew_id": "abc-123",
                "status": "completed",
                "results": [
                    {"task_id": "t1", "output": "done", "status": "completed"},
                ],
            },
        )

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
    async def test_server_error(self, httpx_mock):
        """AgnosAI returns 500."""
        httpx_mock.add_response(
            url="http://test:8080/api/v1/crews",
            method="POST",
            status_code=500,
            text="internal error",
        )

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
    async def test_connection_refused(self, httpx_mock):
        """AgnosAI server unreachable."""
        httpx_mock.add_exception(
            httpx.ConnectError("Connection refused"),
            url="http://test:8080/api/v1/crews",
        )

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
