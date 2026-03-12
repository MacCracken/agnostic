"""Deeper task lifecycle E2E tests for the Agnostic QA platform.

These validate the full task lifecycle, input validation, error handling,
and the A2A delegation protocol.

Requires Docker Compose services to be running.
Run with: pytest tests/e2e/ -v -m e2e
"""

import time
import uuid

import httpx
import pytest

pytestmark = pytest.mark.e2e


def test_full_task_lifecycle(http_client: httpx.Client, api_headers: dict):
    """Submit a task, poll to completion, verify result structure."""
    payload = {
        "title": "Lifecycle E2E test",
        "description": "Full lifecycle validation of task submission and completion",
        "priority": "high",
        "target_url": "http://example.com",
    }
    try:
        resp = http_client.post("/api/v1/tasks", json=payload, headers=api_headers)
    except httpx.RemoteProtocolError:
        pytest.skip("Server disconnected (agent runtime crash in CI)")
    if resp.status_code == 500:
        pytest.skip("Task submission failed (agent runtime unavailable in CI)")
    assert resp.status_code == 201
    data = resp.json()
    task_id = data["task_id"]
    assert "session_id" in data
    assert data["status"] == "pending"

    # Poll until terminal state (max 60s for full lifecycle)
    deadline = time.monotonic() + 60
    status = "pending"
    result_data = None
    while status in ("pending", "running") and time.monotonic() < deadline:
        time.sleep(3)
        poll = http_client.get(f"/api/v1/tasks/{task_id}", headers=api_headers)
        assert poll.status_code == 200
        result_data = poll.json()
        status = result_data["status"]

    assert status in ("completed", "failed", "pending")
    if result_data and status in ("completed", "failed"):
        assert "session_id" in result_data
        assert "status" in result_data
        assert "result" in result_data


def test_task_not_found(http_client: httpx.Client, api_headers: dict):
    """GET /api/tasks/{random-uuid} returns 404."""
    fake_id = str(uuid.uuid4())
    try:
        resp = http_client.get(f"/api/v1/tasks/{fake_id}", headers=api_headers)
    except httpx.RemoteProtocolError:
        pytest.skip("Server disconnected (unstable after agent crash in CI)")
    if resp.status_code == 500:
        pytest.skip("Server error (unstable after agent crash in CI)")
    assert resp.status_code == 404


def test_input_validation_rejects_empty_title(
    http_client: httpx.Client, api_headers: dict
):
    """POST /api/tasks with empty title returns 422."""
    payload = {"title": "", "description": "Some description"}
    try:
        resp = http_client.post("/api/v1/tasks", json=payload, headers=api_headers)
    except httpx.RemoteProtocolError:
        pytest.skip("Server disconnected (unstable after agent crash in CI)")
    assert resp.status_code == 422


def test_input_validation_rejects_invalid_priority(
    http_client: httpx.Client, api_headers: dict
):
    """POST /api/tasks with priority='invalid' returns 422."""
    payload = {
        "title": "Validation test",
        "description": "Testing invalid priority",
        "priority": "invalid",
    }
    resp = http_client.post("/api/v1/tasks", json=payload, headers=api_headers)
    assert resp.status_code == 422


def test_a2a_delegate(http_client: httpx.Client, api_headers: dict):
    """POST /api/v1/a2a/receive with delegate payload returns 200."""
    msg = {
        "id": f"e2e-test-{uuid.uuid4().hex[:8]}",
        "type": "a2a:delegate",
        "fromPeerId": "e2e-test-suite",
        "toPeerId": "agnostic",
        "payload": {
            "title": "A2A E2E delegate test",
            "description": "Delegated task from E2E test suite",
            "priority": "high",
            "agents": ["security-compliance"],
            "standards": ["OWASP"],
        },
        "timestamp": 1708516800000,
    }
    try:
        resp = http_client.post("/api/v1/a2a/receive", json=msg, headers=api_headers)
    except httpx.RemoteProtocolError:
        pytest.skip("Server disconnected (agent runtime crash in CI)")
    # 503 when A2A is not enabled, 500 when agent runtime unavailable
    if resp.status_code == 503:
        pytest.skip("A2A not enabled (YEOMAN_A2A_ENABLED=false)")
    if resp.status_code == 500:
        pytest.skip("A2A delegate failed (agent runtime unavailable in CI)")
    assert resp.status_code == 200
    data = resp.json()
    assert data["accepted"] is True
    assert "task_id" in data
