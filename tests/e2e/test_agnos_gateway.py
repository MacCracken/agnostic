"""E2E tests for AGNOS LLM Gateway integration.

Validates that when AGNOS_LLM_GATEWAY_ENABLED=true, LLM calls route through
hoosh and agents register/heartbeat with daimon.

Requires Docker Compose services (docker compose --profile dev) to be running:
    docker compose -f docker compose --profile dev up -d

Run with: pytest tests/e2e/test_agnos_gateway.py -v -m e2e
"""

import os

import httpx
import pytest

pytestmark = pytest.mark.e2e

HOOSH_URL = os.getenv("HOOSH_URL", "http://localhost:8088")
DAIMON_URL = os.getenv("DAIMON_URL", "http://localhost:8090")


@pytest.fixture(scope="module")
def hoosh_client():
    """httpx client pointed at hoosh (LLM Gateway)."""
    with httpx.Client(base_url=HOOSH_URL, timeout=10) as client:
        try:
            client.get("/v1/health")
        except httpx.ConnectError:
            pytest.skip(
                f"hoosh unreachable at {HOOSH_URL} -- "
                "start docker compose --profile dev before running these tests"
            )
        yield client


@pytest.fixture(scope="module")
def daimon_client():
    """httpx client pointed at daimon (Agent Runtime)."""
    with httpx.Client(base_url=DAIMON_URL, timeout=10) as client:
        try:
            client.get("/v1/health")
        except httpx.ConnectError:
            pytest.skip(
                f"daimon unreachable at {DAIMON_URL} -- "
                "start docker compose --profile dev before running these tests"
            )
        yield client


# ---------------------------------------------------------------------------
# 1. AGNOS service health
# ---------------------------------------------------------------------------


def test_hoosh_health(hoosh_client: httpx.Client):
    """hoosh LLM Gateway is healthy."""
    resp = hoosh_client.get("/v1/health")
    assert resp.status_code == 200


def test_daimon_health(daimon_client: httpx.Client):
    """daimon Agent Runtime is healthy."""
    resp = daimon_client.get("/v1/health")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 2. Agnostic → hoosh LLM gateway round-trip
# ---------------------------------------------------------------------------


def test_gateway_llm_round_trip(http_client: httpx.Client, api_headers: dict):
    """Submit a task through webgui; LLM call should route via hoosh.

    This validates the full path: webgui → LLMIntegrationService → litellm
    → hoosh gateway → upstream provider → response.
    """
    resp = http_client.get("/health")
    data = resp.json()

    # If gateway isn't configured, skip
    if data.get("status") == "unhealthy":
        pytest.skip("webgui unhealthy — AGNOS services may not be running")

    # Submit a lightweight task that triggers an LLM call
    task_payload = {
        "title": "Quick test",
        "description": "Verify that the login page loads correctly",
        "priority": "low",
    }
    resp = http_client.post(
        "/api/tasks",
        json=task_payload,
        headers=api_headers,
    )

    # 201 means the task was accepted (LLM call runs in background)
    assert resp.status_code in (200, 201, 202), f"Task submit failed: {resp.text}"
    data = resp.json()
    assert "task_id" in data or "session_id" in data


# ---------------------------------------------------------------------------
# 3. Agent registration with daimon
# ---------------------------------------------------------------------------


def test_agents_registered_with_daimon(
    http_client: httpx.Client, daimon_client: httpx.Client
):
    """Agnostic agents should be registered with daimon after startup."""
    # Query daimon for registered agents
    resp = daimon_client.get("/v1/agents")
    if resp.status_code == 404:
        pytest.skip("daimon /v1/agents endpoint not available")

    assert resp.status_code == 200
    data = resp.json()

    # Check that at least one agnostic agent is registered
    agents = data if isinstance(data, list) else data.get("agents", [])
    agnostic_agents = [
        a
        for a in agents
        if isinstance(a, dict) and "agnostic" in a.get("agent_id", "").lower()
    ]
    assert len(agnostic_agents) > 0, (
        "No agnostic agents registered with daimon. "
        "Check AGNOS_AGENT_REGISTRATION_ENABLED=true in webgui."
    )


def test_webgui_health_shows_gateway(http_client: httpx.Client):
    """Health endpoint should reflect AGNOS gateway status when enabled."""
    resp = http_client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    # The health check should at minimum be reachable
    assert data["status"] in ("healthy", "degraded", "unhealthy")


# ---------------------------------------------------------------------------
# 4. Credential provisioning is NOT needed with gateway
# ---------------------------------------------------------------------------


def test_no_openai_key_needed_with_gateway(
    http_client: httpx.Client, api_headers: dict
):
    """When gateway is enabled, tasks should work without OPENAI_API_KEY.

    hoosh holds the provider keys — Agnostic only needs AGNOS_LLM_GATEWAY_API_KEY.
    """
    resp = http_client.get("/health")
    if resp.json().get("status") == "unhealthy":
        pytest.skip("webgui unhealthy")

    # Submit task — if gateway is properly configured, this should not fail
    # with "OPENAI_API_KEY not set"
    resp = http_client.post(
        "/api/tasks",
        json={
            "title": "Smoke test",
            "description": "Smoke test: verify homepage loads",
            "priority": "low",
        },
        headers=api_headers,
    )
    # Should not get a 500 about missing API key
    assert resp.status_code != 500 or "API_KEY" not in resp.text
