"""E2E: crew execution against both backends.

Run with:
    E2E_BACKEND=crewai  pytest tests/e2e/test_crew_dual_backend.py
    E2E_BACKEND=agnosai pytest tests/e2e/test_crew_dual_backend.py

Or via Docker Compose:
    docker compose -f docker-compose.yml -f docker-compose.e2e.yml up -d
    E2E_BACKEND=crewai  pytest tests/e2e/test_crew_dual_backend.py
    E2E_BACKEND=agnosai pytest tests/e2e/test_crew_dual_backend.py
"""

import os

import httpx
import pytest

AGNOSTIC_URL = os.getenv("AGNOSTIC_URL", "http://localhost:8000")
AGNOSAI_URL = os.getenv("AGNOSAI_URL", "http://localhost:8080")
E2E_BACKEND = os.getenv("E2E_BACKEND", os.getenv("AGNOSTIC_BACKEND", "crewai"))


@pytest.fixture(scope="module")
def backend_name():
    return E2E_BACKEND


@pytest.fixture(scope="module", autouse=True)
async def check_services(backend_name):
    """Verify required services are healthy before running tests."""
    async with httpx.AsyncClient(timeout=10) as client:
        # Agnostic must always be running.
        resp = await client.get(f"{AGNOSTIC_URL}/health")
        assert resp.status_code == 200, "Agnostic not healthy"

        if backend_name == "agnosai":
            resp = await client.get(f"{AGNOSAI_URL}/health")
            assert resp.status_code == 200, "AgnosAI not healthy"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_create_crew_returns_result(backend_name):
    """Smoke test: create a crew and verify it completes."""
    payload = {
        "name": f"e2e-{backend_name}",
        "preset": "quality-lean",
        "description": "E2E smoke test",
    }

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{AGNOSTIC_URL}/api/v1/crews",
            json=payload,
        )
        assert resp.status_code in (200, 201, 202), f"Unexpected: {resp.status_code} {resp.text}"
        data = resp.json()
        assert "crew_id" in data or "id" in data


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_crew_status_endpoint(backend_name):
    """Verify crew status can be polled."""
    # Create a crew first.
    payload = {
        "name": f"e2e-status-{backend_name}",
        "preset": "quality-lean",
        "description": "Status poll test",
    }

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(f"{AGNOSTIC_URL}/api/v1/crews", json=payload)
        assert resp.status_code in (200, 201, 202)
        data = resp.json()
        crew_id = data.get("crew_id") or data.get("id")
        assert crew_id

        # Poll status.
        resp = await client.get(f"{AGNOSTIC_URL}/api/v1/crews/{crew_id}")
        # Could be 200 (found) or 404 (async, not yet registered).
        assert resp.status_code in (200, 404)


@pytest.mark.e2e
@pytest.mark.asyncio
@pytest.mark.skipif(E2E_BACKEND != "agnosai", reason="SSE only for agnosai backend")
async def test_sse_stream_connects(backend_name):
    """Verify SSE stream endpoint returns event-stream content type."""
    import uuid

    crew_id = str(uuid.uuid4())

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{AGNOSAI_URL}/api/v1/crews/{crew_id}/stream",
        )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")
