"""
Rate limiting utilities for API endpoints.
"""

import asyncio
import os
import time
from collections import defaultdict
from collections.abc import Callable
from functools import wraps

_MAX_KEYS = 10_000


class RateLimiter:
    """Simple in-memory rate limiter."""

    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: dict[str, list[float]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def is_allowed(self, key: str) -> bool:
        """Check if request is allowed for given key."""
        async with self._lock:
            now = time.time()
            window_start = now - self.window_seconds

            # Remove old requests
            self.requests[key] = [t for t in self.requests[key] if t > window_start]

            if len(self.requests[key]) >= self.max_requests:
                return False

            self.requests[key].append(now)

            # Periodic cleanup of stale keys
            if len(self.requests) > _MAX_KEYS:
                self._cleanup_stale_keys(window_start)

            return True

    def is_allowed_sync(self, key: str) -> bool:
        """Synchronous check if request is allowed for given key."""
        now = time.time()
        window_start = now - self.window_seconds

        # Remove old requests
        self.requests[key] = [t for t in self.requests[key] if t > window_start]

        if len(self.requests[key]) >= self.max_requests:
            return False

        self.requests[key].append(now)

        # Periodic cleanup of stale keys
        if len(self.requests) > _MAX_KEYS:
            self._cleanup_stale_keys(window_start)

        return True

    def _cleanup_stale_keys(self, window_start: float) -> None:
        """Remove keys with no recent requests."""
        stale_keys = [
            k for k, v in self.requests.items() if not v or all(t <= window_start for t in v)
        ]
        for k in stale_keys:
            del self.requests[k]

    def get_remaining(self, key: str) -> int:
        """Get remaining requests for key."""
        now = time.time()
        window_start = now - self.window_seconds
        self.requests[key] = [t for t in self.requests[key] if t > window_start]
        return max(0, self.max_requests - len(self.requests[key]))


# Global rate limiters
default_rate_limiter = RateLimiter(
    max_requests=int(os.getenv("RATE_LIMIT_MAX_REQUESTS", "100")),
    window_seconds=int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60")),
)


def rate_limit(limiter: RateLimiter = None):
    """Decorator to apply rate limiting to an endpoint."""
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Get client identifier (could be user_id or IP)
            from fastapi import HTTPException, Request

            request = kwargs.get("request") or (
                args[0] if args and isinstance(args[0], Request) else None
            )

            if request:
                client_ip = request.client.host if request.client else "unknown"
                key = client_ip
            else:
                key = "default"

            limit = limiter or default_rate_limiter

            if not await limit.is_allowed(key):
                raise HTTPException(
                    status_code=429,
                    detail="Rate limit exceeded. Please try again later.",
                )

            return await func(*args, **kwargs)

        return wrapper
    return decorator
