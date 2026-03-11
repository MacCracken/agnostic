from unittest.mock import Mock

import pytest


@pytest.fixture()
def sample_requirements() -> str:
    return "User login, data validation, performance, and security checks."


@pytest.fixture()
def sample_test_results() -> dict:
    return {
        "tests_run": 10,
        "passed": 8,
        "failed": 2,
        "severity": "high",
        "category": "security",
        "description": "Sample finding",
    }


@pytest.fixture()
def mock_redis():
    """Mock Redis client for testing"""
    mock_client = Mock()
    mock_client.get.return_value = None
    mock_client.set.return_value = True
    mock_client.hgetall.return_value = {}
    mock_client.lrange.return_value = []
    mock_client.exists.return_value = False
    mock_client.keys.return_value = []
    mock_client.delete.return_value = True
    mock_client.setex.return_value = True
    return mock_client


@pytest.fixture()
def mock_celery():
    """Mock Celery app for testing"""
    mock_app = Mock()
    mock_app.send_task.return_value = Mock(id="test-task-id")
    return mock_app


@pytest.fixture()
def mock_llm():
    """Mock LLM for testing"""
    mock = Mock()
    mock.invoke.return_value = Mock(content="Mock LLM response")
    return mock
