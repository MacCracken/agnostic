"""Tests for CorrelationIdMiddleware and RateLimitMiddleware."""

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
except ImportError:
    pytest.skip("fastapi not available", allow_module_level=True)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def app_with_middleware():
    """Create a FastAPI app with all middleware applied."""
    from starlette.middleware.base import BaseHTTPMiddleware

    from webgui.app import CorrelationIdMiddleware, RateLimitMiddleware

    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(CorrelationIdMiddleware)

    @app.get("/api/test")
    async def test_endpoint():
        return {"ok": True}

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    return app


@pytest.fixture()
def client(app_with_middleware):
    return TestClient(app_with_middleware)


# ---------------------------------------------------------------------------
# Correlation ID tests
# ---------------------------------------------------------------------------


class TestCorrelationIdMiddleware:
    def test_generates_correlation_id(self, client):
        """Response includes X-Correlation-ID even if not sent by client."""
        resp = client.get("/api/test")
        assert resp.status_code == 200
        cid = resp.headers.get("X-Correlation-ID")
        assert cid is not None
        assert len(cid) == 32  # uuid hex

    def test_propagates_client_correlation_id(self, client):
        """Server echoes the client-provided correlation ID."""
        resp = client.get("/api/test", headers={"X-Correlation-ID": "my-trace-123"})
        assert resp.status_code == 200
        assert resp.headers["X-Correlation-ID"] == "my-trace-123"

    def test_different_requests_get_different_ids(self, client):
        """Each request gets a unique correlation ID when not provided."""
        r1 = client.get("/api/test")
        r2 = client.get("/api/test")
        assert r1.headers["X-Correlation-ID"] != r2.headers["X-Correlation-ID"]

    def test_non_api_paths_get_correlation_id(self, client):
        """Correlation ID middleware runs on all paths."""
        resp = client.get("/health")
        assert "X-Correlation-ID" in resp.headers


# ---------------------------------------------------------------------------
# Rate limit tests
# ---------------------------------------------------------------------------


class TestRateLimitMiddleware:
    def test_allows_requests_under_limit(self, client):
        """Requests under the limit pass through."""
        resp = client.get("/api/test")
        assert resp.status_code == 200

    @patch.dict(os.environ, {"RATE_LIMIT_MAX_REQUESTS": "3", "RATE_LIMIT_WINDOW_SECONDS": "60"})
    def test_blocks_after_limit_exceeded(self):
        """Returns 429 after exceeding the rate limit."""
        from shared.rate_limit import RateLimiter
        from webgui.app import CorrelationIdMiddleware, RateLimitMiddleware

        # Create fresh app with a fresh limiter
        app = FastAPI()
        app.add_middleware(RateLimitMiddleware)
        app.add_middleware(CorrelationIdMiddleware)

        limiter = RateLimiter(max_requests=3, window_seconds=60)

        @app.get("/api/test")
        async def test_endpoint():
            return {"ok": True}

        with patch("shared.rate_limit.default_rate_limiter", limiter):
            tc = TestClient(app)
            for _ in range(3):
                resp = tc.get("/api/test")
                assert resp.status_code == 200

            resp = tc.get("/api/test")
            assert resp.status_code == 429
            assert "Rate limit exceeded" in resp.json()["detail"]
            assert "Retry-After" in resp.headers

    def test_exempt_paths_not_rate_limited(self, client):
        """Health and metrics endpoints bypass rate limiting."""
        resp = client.get("/health")
        assert resp.status_code == 200
        # /health is not under /api, so never rate limited

    @patch.dict(os.environ, {"RATE_LIMIT_MAX_REQUESTS": "2", "RATE_LIMIT_WINDOW_SECONDS": "60"})
    def test_rate_limit_headers_on_429(self):
        """429 responses include rate limit headers."""
        from shared.rate_limit import RateLimiter
        from webgui.app import CorrelationIdMiddleware, RateLimitMiddleware

        app = FastAPI()
        app.add_middleware(RateLimitMiddleware)
        app.add_middleware(CorrelationIdMiddleware)

        limiter = RateLimiter(max_requests=2, window_seconds=60)

        @app.get("/api/test")
        async def test_endpoint():
            return {"ok": True}

        with patch("shared.rate_limit.default_rate_limiter", limiter):
            tc = TestClient(app)
            tc.get("/api/test")
            tc.get("/api/test")
            resp = tc.get("/api/test")
            assert resp.status_code == 429
            assert resp.headers["X-RateLimit-Limit"] == "2"
            assert resp.headers["Retry-After"] == "60"


# ---------------------------------------------------------------------------
# Correlation ID in audit log
# ---------------------------------------------------------------------------


class TestCorrelationIdInAudit:
    def test_audit_log_includes_correlation_id(self):
        """Audit log events include the correlation ID when set."""
        import json

        from webgui.app import correlation_id_ctx

        correlation_id_ctx.set("test-cid-123")
        try:
            from shared.audit import AuditAction, audit_log

            with patch("shared.audit._audit_logger") as mock_logger:
                with patch("shared.audit.AUDIT_ENABLED", True):
                    audit_log(AuditAction.TASK_SUBMITTED, actor="test-user")
                    call_args = mock_logger.log.call_args[0][1]
                    event = json.loads(call_args)
                    assert event["correlation_id"] == "test-cid-123"
        finally:
            correlation_id_ctx.set(None)

    def test_audit_log_without_correlation_id(self):
        """Audit log works fine when no correlation ID is set."""
        import json

        from webgui.app import correlation_id_ctx

        correlation_id_ctx.set(None)
        from shared.audit import AuditAction, audit_log

        with patch("shared.audit._audit_logger") as mock_logger:
            with patch("shared.audit.AUDIT_ENABLED", True):
                audit_log(AuditAction.TASK_SUBMITTED, actor="test-user")
                call_args = mock_logger.log.call_args[0][1]
                event = json.loads(call_args)
                assert "correlation_id" not in event


# ---------------------------------------------------------------------------
# DB pool config
# ---------------------------------------------------------------------------


class TestDbPoolConfig:
    @patch.dict(
        os.environ,
        {
            "POSTGRES_HOST": "localhost",
            "POSTGRES_PORT": "5432",
            "POSTGRES_USER": "test",
            "POSTGRES_PASSWORD": "test",
            "POSTGRES_DB": "test",
            "DB_POOL_SIZE": "10",
            "DB_MAX_OVERFLOW": "20",
            "DB_POOL_RECYCLE": "1800",
            "DB_POOL_TIMEOUT": "15",
        },
    )
    def test_pool_env_vars_read(self):
        """Verify pool config reads from env vars."""
        from shared.database.models import get_database_url

        url = get_database_url()
        assert "test@localhost:5432/test" in url

    def test_get_database_url_defaults(self):
        """Verify default database URL construction."""
        from shared.database.models import get_database_url

        url = get_database_url()
        assert url.startswith("postgresql+asyncpg://")
