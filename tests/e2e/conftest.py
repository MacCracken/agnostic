"""E2E test fixtures -- requires running Docker Compose services."""

import os

import httpx
import pytest

E2E_BASE_URL = os.getenv("E2E_BASE_URL", "http://localhost:8000")
E2E_API_KEY = os.getenv("E2E_API_KEY", "test-e2e-key")


@pytest.fixture(scope="session")
def base_url():
    return E2E_BASE_URL


@pytest.fixture(scope="session")
def api_headers():
    return {"X-API-Key": E2E_API_KEY}


@pytest.fixture(scope="session")
def http_client():
    """Create an httpx client for the session.

    If the service is unreachable at session start, every test that depends
    on this fixture will be skipped with a clear reason.
    """
    with httpx.Client(base_url=E2E_BASE_URL, timeout=30) as client:
        try:
            client.get("/health")
        except httpx.ConnectError:
            pytest.skip(
                f"E2E services unreachable at {E2E_BASE_URL} -- "
                "start Docker Compose before running e2e tests"
            )
        yield client
