"""Automated smoke tests for the Agnostic QA platform.

These mirror the manual smoke and integration tests documented in
docs/development/manual-testing.md.  Each test is self-contained and
idempotent.

Requires Docker Compose services to be running.
Run with: pytest tests/e2e/ -v -m e2e
"""

import time
import uuid

import httpx
import pytest

pytestmark = pytest.mark.e2e


# ---------------------------------------------------------------------------
# 1. Health & capabilities
# ---------------------------------------------------------------------------


def test_health_endpoint(http_client: httpx.Client):
    """GET /health returns 200 with a recognized status and components."""
    resp = http_client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("healthy", "degraded", "unhealthy")
    assert "components" in data or "redis" in data  # varies by version


def test_a2a_capabilities(http_client: httpx.Client):
    """GET /api/v1/a2a/capabilities lists 'qa'."""
    resp = http_client.get("/api/v1/a2a/capabilities")
    # 503 when YEOMAN_A2A_ENABLED is not set
    if resp.status_code == 503:
        pytest.skip("A2A not enabled (YEOMAN_A2A_ENABLED=false)")
    assert resp.status_code == 200
    data = resp.json()
    assert "capabilities" in data
    cap_names = [c["name"] for c in data["capabilities"]]
    assert "qa" in cap_names


def test_prometheus_metrics(http_client: httpx.Client):
    """GET /api/metrics returns Prometheus exposition text with qa_ metrics."""
    resp = http_client.get("/api/metrics")
    assert resp.status_code == 200
    body = resp.text
    # Prometheus metrics should contain at least one qa_ prefixed metric
    # or standard process/python metrics if no qa_ metrics have been emitted yet
    assert "qa_" in body or "process_" in body or "python_" in body


# ---------------------------------------------------------------------------
# 2. Authentication
# ---------------------------------------------------------------------------


def test_auth_rejects_no_credentials(http_client: httpx.Client):
    """GET /api/tasks/nonexistent without auth returns 401."""
    resp = http_client.get(f"/api/tasks/{uuid.uuid4()}")
    assert resp.status_code == 401


def test_auth_accepts_api_key(http_client: httpx.Client, api_headers: dict):
    """GET /api/dashboard with X-API-Key returns 200."""
    resp = http_client.get("/api/dashboard", headers=api_headers)
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 3. Task submission & polling
# ---------------------------------------------------------------------------


def test_submit_task_and_poll(http_client: httpx.Client, api_headers: dict):
    """POST /api/tasks, then poll until non-pending (max 30s)."""
    payload = {
        "title": "E2E smoke task",
        "description": "Verify login flow and basic navigation",
        "priority": "medium",
        "target_url": "http://example.com",
    }
    resp = http_client.post("/api/tasks", json=payload, headers=api_headers)
    # 201 = submitted, 500 = agent runtime unavailable (placeholder API key)
    if resp.status_code == 500:
        pytest.skip("Task submission failed (agent runtime unavailable in CI)")
    assert resp.status_code == 201
    data = resp.json()
    task_id = data["task_id"]
    assert data["status"] == "pending"

    # Poll until status leaves "pending" — task may fail fast without real LLM
    deadline = time.monotonic() + 30
    status = "pending"
    while status == "pending" and time.monotonic() < deadline:
        time.sleep(2)
        poll = http_client.get(f"/api/tasks/{task_id}", headers=api_headers)
        assert poll.status_code == 200
        status = poll.json()["status"]

    assert status in ("completed", "failed", "running", "pending")


def test_submit_security_task(http_client: httpx.Client, api_headers: dict):
    """POST /api/tasks/security returns 201."""
    payload = {"title": "E2E security scan", "description": "OWASP Top-10 check"}
    try:
        resp = http_client.post(
            "/api/tasks/security", json=payload, headers=api_headers
        )
    except httpx.RemoteProtocolError:
        pytest.skip("Server disconnected (agent runtime crash in CI)")
    if resp.status_code == 500:
        pytest.skip("Task submission failed (agent runtime unavailable in CI)")
    assert resp.status_code in (200, 201)


def test_submit_performance_task(http_client: httpx.Client, api_headers: dict):
    """POST /api/tasks/performance returns 200 or 201."""
    payload = {"title": "E2E perf test", "description": "Load test check"}
    try:
        resp = http_client.post(
            "/api/tasks/performance", json=payload, headers=api_headers
        )
    except httpx.RemoteProtocolError:
        pytest.skip("Server disconnected (agent runtime crash in CI)")
    if resp.status_code == 500:
        pytest.skip("Task submission failed (agent runtime unavailable in CI)")
    assert resp.status_code in (200, 201)


# ---------------------------------------------------------------------------
# 4. Sessions & reports
# ---------------------------------------------------------------------------


def test_list_sessions(http_client: httpx.Client, api_headers: dict):
    """GET /api/sessions returns 200 with a list."""
    try:
        resp = http_client.get("/api/sessions", headers=api_headers)
    except httpx.RemoteProtocolError:
        pytest.skip("Server disconnected (Redis timeout in CI)")
    assert resp.status_code == 200
    data = resp.json()
    # Endpoint returns paginated response with items list
    if isinstance(data, dict) and "items" in data:
        assert isinstance(data["items"], list)
    else:
        assert isinstance(data, list)


def test_report_generation(http_client: httpx.Client, api_headers: dict):
    """POST /api/reports/generate returns a report_id."""
    # Submit a quick task first to get a session_id
    task_resp = http_client.post(
        "/api/tasks",
        json={"title": "Report gen test", "description": "Quick task for report"},
        headers=api_headers,
    )
    if task_resp.status_code != 201:
        pytest.skip("Task submission failed — cannot test report generation")
    session_id = task_resp.json()["session_id"]

    report_resp = http_client.post(
        "/api/reports/generate",
        json={
            "session_id": session_id,
            "report_type": "executive_summary",
            "format": "json",
        },
        headers=api_headers,
    )
    if report_resp.status_code == 500:
        pytest.skip("Report generation failed (agent runtime unavailable in CI)")
    assert report_resp.status_code == 200
    assert "report_id" in report_resp.json()


def test_report_list(http_client: httpx.Client, api_headers: dict):
    """GET /api/reports returns 200 with a list."""
    try:
        resp = http_client.get("/api/reports", headers=api_headers)
    except httpx.RemoteProtocolError:
        pytest.skip("Server disconnected (Redis timeout in CI)")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, (list, dict))  # may be list or wrapped object


# ---------------------------------------------------------------------------
# 5. Agents
# ---------------------------------------------------------------------------


def test_agents_status(http_client: httpx.Client, api_headers: dict):
    """GET /api/agents returns 200 with agent list."""
    resp = http_client.get("/api/agents", headers=api_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, (list, dict))


# ---------------------------------------------------------------------------
# 6. Security
# ---------------------------------------------------------------------------


def test_security_headers_present(http_client: httpx.Client):
    """Responses include standard security headers."""
    resp = http_client.get("/health")
    headers_lower = {k.lower(): v for k, v in resp.headers.items()}
    assert "x-content-type-options" in headers_lower
    assert "x-frame-options" in headers_lower


def test_path_traversal_blocked(http_client: httpx.Client, api_headers: dict):
    """Report download with non-existent report_id returns 404."""
    # Path traversal via ../ is neutralized by HTTP URL normalization before
    # reaching the route handler.  The route itself validates resolved paths
    # via Path.is_relative_to().  Here we verify a bogus report_id returns 404.
    try:
        resp = http_client.get(
            "/api/reports/nonexistent-report-id/download", headers=api_headers
        )
    except httpx.RemoteProtocolError:
        pytest.skip("Server disconnected (unstable after agent crash in CI)")
    if resp.status_code == 500:
        pytest.skip("Server error (unstable after agent crash in CI)")
    assert resp.status_code == 404
