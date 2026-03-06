"""Tests for shared/rate_limit.py — RateLimiter and rate_limit decorator."""

import asyncio
import os
import sys
import time
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from shared.rate_limit import RateLimiter, _KEY_TTL_SECONDS, _MAX_KEYS


class TestRateLimiterInit:
    def test_default_values(self):
        limiter = RateLimiter()
        assert limiter.max_requests == 100
        assert limiter.window_seconds == 60

    def test_custom_values(self):
        limiter = RateLimiter(max_requests=10, window_seconds=30)
        assert limiter.max_requests == 10
        assert limiter.window_seconds == 30


class TestRateLimiterSync:
    def test_allows_under_limit(self):
        limiter = RateLimiter(max_requests=5, window_seconds=60)
        for _ in range(5):
            assert limiter.is_allowed_sync("key1") is True

    def test_blocks_over_limit(self):
        limiter = RateLimiter(max_requests=3, window_seconds=60)
        for _ in range(3):
            limiter.is_allowed_sync("key1")
        assert limiter.is_allowed_sync("key1") is False

    def test_separate_keys_independent(self):
        limiter = RateLimiter(max_requests=2, window_seconds=60)
        limiter.is_allowed_sync("a")
        limiter.is_allowed_sync("a")
        assert limiter.is_allowed_sync("a") is False
        assert limiter.is_allowed_sync("b") is True

    def test_expired_requests_evicted(self):
        limiter = RateLimiter(max_requests=2, window_seconds=1)
        limiter.is_allowed_sync("key")
        limiter.is_allowed_sync("key")
        assert limiter.is_allowed_sync("key") is False
        # Manually age the timestamps
        limiter.requests["key"] = [time.time() - 2]
        assert limiter.is_allowed_sync("key") is True


class TestRateLimiterAsync:
    @pytest.mark.asyncio
    async def test_allows_under_limit(self):
        limiter = RateLimiter(max_requests=3, window_seconds=60)
        assert await limiter.is_allowed("ip1") is True
        assert await limiter.is_allowed("ip1") is True
        assert await limiter.is_allowed("ip1") is True

    @pytest.mark.asyncio
    async def test_blocks_over_limit(self):
        limiter = RateLimiter(max_requests=2, window_seconds=60)
        await limiter.is_allowed("ip1")
        await limiter.is_allowed("ip1")
        assert await limiter.is_allowed("ip1") is False

    @pytest.mark.asyncio
    async def test_concurrent_access(self):
        limiter = RateLimiter(max_requests=5, window_seconds=60)
        results = await asyncio.gather(
            *[limiter.is_allowed("concurrent") for _ in range(10)]
        )
        assert results.count(True) == 5
        assert results.count(False) == 5


class TestGetRemaining:
    def test_full_remaining(self):
        limiter = RateLimiter(max_requests=10, window_seconds=60)
        assert limiter.get_remaining("new_key") == 10

    def test_decreases_with_requests(self):
        limiter = RateLimiter(max_requests=5, window_seconds=60)
        limiter.is_allowed_sync("k")
        limiter.is_allowed_sync("k")
        assert limiter.get_remaining("k") == 3

    def test_zero_when_exhausted(self):
        limiter = RateLimiter(max_requests=2, window_seconds=60)
        limiter.is_allowed_sync("k")
        limiter.is_allowed_sync("k")
        assert limiter.get_remaining("k") == 0


class TestCleanupStaleKeys:
    def test_removes_stale_keys(self):
        limiter = RateLimiter(max_requests=5, window_seconds=60)
        now = time.time()
        # Add a stale key (last seen beyond TTL)
        limiter.requests["stale"] = [now - 7200]
        limiter._last_seen["stale"] = now - _KEY_TTL_SECONDS - 1
        limiter._cleanup_stale_keys(now)
        assert "stale" not in limiter.requests
        assert "stale" not in limiter._last_seen

    def test_keeps_fresh_keys(self):
        limiter = RateLimiter(max_requests=5, window_seconds=60)
        now = time.time()
        limiter.requests["fresh"] = [now - 10]
        limiter._last_seen["fresh"] = now
        limiter._cleanup_stale_keys(now)
        assert "fresh" in limiter.requests

    def test_cleanup_triggered_at_max_keys(self):
        limiter = RateLimiter(max_requests=5, window_seconds=60)
        now = time.time()
        # Fill up to MAX_KEYS + 1 with stale entries
        for i in range(_MAX_KEYS + 1):
            limiter.requests[f"key_{i}"] = [now - 7200]
            limiter._last_seen[f"key_{i}"] = now - _KEY_TTL_SECONDS - 1
        # One fresh key
        limiter.requests["alive"] = [now]
        limiter._last_seen["alive"] = now
        # Next call should trigger cleanup
        limiter.is_allowed_sync("alive")
        assert len(limiter.requests) < _MAX_KEYS + 2


class TestRateLimitDecorator:
    @pytest.mark.asyncio
    async def test_decorator_allows_request(self):
        from shared.rate_limit import rate_limit

        limiter = RateLimiter(max_requests=5, window_seconds=60)

        @rate_limit(limiter)
        async def handler(request=None):
            return "ok"

        mock_request = MagicMock()
        mock_request.client.host = "1.2.3.4"
        result = await handler(request=mock_request)
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_decorator_blocks_when_exceeded(self):
        from fastapi import HTTPException

        from shared.rate_limit import rate_limit

        limiter = RateLimiter(max_requests=1, window_seconds=60)

        @rate_limit(limiter)
        async def handler(request=None):
            return "ok"

        mock_request = MagicMock()
        mock_request.client.host = "5.6.7.8"
        await handler(request=mock_request)  # first is allowed
        with pytest.raises(HTTPException) as exc_info:
            await handler(request=mock_request)
        assert exc_info.value.status_code == 429

    @pytest.mark.asyncio
    async def test_decorator_uses_default_key_without_request(self):
        from shared.rate_limit import rate_limit

        limiter = RateLimiter(max_requests=5, window_seconds=60)

        @rate_limit(limiter)
        async def handler():
            return "ok"

        result = await handler()
        assert result == "ok"
