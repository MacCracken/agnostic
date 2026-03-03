"""
Rate limiting utilities for API endpoints.
"""

import time
from collections import defaultdict
from functools import wraps
from typing import Callable


class RateLimiter:
    """Simple in-memory rate limiter."""

    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, key: str) -> bool:
        """Check if request is allowed for given key."""
        now = time.time()
        window_start = now - self.window_seconds

        # Remove old requests
        self.requests[key] = [t for t in self.requests[key] if t > window_start]

        if len(self.requests[key]) >= self.max_requests:
            return False

        self.requests[key].append(now)
        return True

    def get_remaining(self, key: str) -> int:
        """Get remaining requests for key."""
        now = time.time()
        window_start = now - self.window_seconds
        self.requests[key] = [t for t in self.requests[key] if t > window_start]
        return max(0, self.max_requests - len(self.requests[key]))


# Global rate limiters
default_rate_limiter = RateLimiter(
    max_requests=int(__import__("os")..getenv("RATE_LIMIT_MAX_REQUESTS", "100")),
    window_seconds=int(__import__("os").getenv("RATE_LIMIT_WINDOW_SECONDS", "60")),
)


def rate_limit(limiter: RateLimiter = None):
    """Decorator to apply rate limiting to an endpoint."""
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Get client identifier (could be user_id or IP)
            from fastapi import Request, HTTPException

            request = kwargs.get("request") or (
                args[0] if args and isinstance(args[0], Request) else None
            )

            if request:
                # Use user_id if authenticated, otherwise fall back to IP
                user_id = None
                try:
                    from webgui.auth import get_current_user
                    # This won't work directly, so we'll use IP
                except Exception:
                    pass

                client_ip = request.client.host if request.client else "unknown"
                key = user_id or client_ip
            else:
                key = "default"

            limit = limiter or default_rate_limiter

            if not limit.is_allowed(key):
                raise HTTPException(
                    status_code=429,
                    detail="Rate limit exceeded. Please try again later.",
                )

            return await func(*args, **kwargs)

        return wrapper
    return decorator
