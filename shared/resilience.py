"""
Resilience primitives for the Agentic QA Team System.

Pure stdlib — no external dependencies required.

* **CircuitBreaker** — tracks failures and short-circuits calls when a
  threshold is reached, recovering after a configurable timeout.
* **RetryConfig** + **retry_async** decorator — exponential-backoff retry
  for async functions.
* **GracefulShutdown** — async context manager that registers SIGTERM/SIGINT
  handlers and runs cleanup callbacks on exit.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import signal
import time
from collections.abc import Callable, Coroutine  # noqa: TC003
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Circuit Breaker
# ------------------------------------------------------------------


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreaker:
    """Simple circuit breaker with automatic OPEN → HALF_OPEN transition."""

    name: str
    failure_threshold: int = 5
    recovery_timeout: float = 60.0
    on_state_change: Callable[[str, str, str], None] | None = field(
        default=None, repr=False
    )

    _failure_count: int = field(default=0, init=False, repr=False)
    _last_failure_time: float = field(default=0.0, init=False, repr=False)
    _state: CircuitState = field(default=CircuitState.CLOSED, init=False, repr=False)

    @property
    def state(self) -> CircuitState:
        if (
            self._state is CircuitState.OPEN
            and time.monotonic() - self._last_failure_time >= self.recovery_timeout
        ):
            self._state = CircuitState.HALF_OPEN
            logger.info("Circuit breaker '%s' transitioned to HALF_OPEN", self.name)
        return self._state

    def can_execute(self) -> bool:
        """Return True if a call is allowed (CLOSED or HALF_OPEN)."""
        return self.state is not CircuitState.OPEN

    def record_success(self) -> None:
        """Record a successful call — resets the breaker to CLOSED."""
        if self._state is not CircuitState.CLOSED:
            old = self._state.value
            logger.info("Circuit breaker '%s' recovered → CLOSED", self.name)
            self._state = CircuitState.CLOSED
            if self.on_state_change:
                self.on_state_change(self.name, old, "closed")
        self._failure_count = 0

    def record_failure(self) -> None:
        """Record a failed call — may trip the breaker to OPEN."""
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if self._failure_count >= self.failure_threshold:
            old = self._state.value
            self._state = CircuitState.OPEN
            logger.warning(
                "Circuit breaker '%s' tripped → OPEN (failures=%d)",
                self.name,
                self._failure_count,
            )
            if self.on_state_change:
                self.on_state_change(self.name, old, "open")


# ------------------------------------------------------------------
# Retry with exponential backoff
# ------------------------------------------------------------------


@dataclass
class RetryConfig:
    """Configuration for retry_async decorator."""

    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0


def retry_async(
    config: RetryConfig | None = None,
) -> Callable[..., Callable[..., Coroutine[Any, Any, Any]]]:
    """Decorator that retries an async function with exponential backoff."""
    cfg = config or RetryConfig()

    def decorator(
        fn: Callable[..., Coroutine[Any, Any, Any]],
    ) -> Callable[..., Coroutine[Any, Any, Any]]:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: BaseException | None = None
            for attempt in range(cfg.max_retries + 1):
                try:
                    return await fn(*args, **kwargs)
                except Exception as exc:
                    last_exc = exc
                    if attempt < cfg.max_retries:
                        delay = min(
                            cfg.base_delay * (cfg.exponential_base**attempt),
                            cfg.max_delay,
                        )
                        logger.warning(
                            "Retry %d/%d for %s after %.1fs (error: %s)",
                            attempt + 1,
                            cfg.max_retries,
                            fn.__name__,
                            delay,
                            exc,
                        )
                        await asyncio.sleep(delay)
            raise last_exc  # type: ignore[misc]

        return wrapper

    return decorator


# ------------------------------------------------------------------
# Graceful Shutdown
# ------------------------------------------------------------------


class GracefulShutdown:
    """Async context manager that handles SIGTERM/SIGINT for clean shutdown.

    Usage::

        async with GracefulShutdown("MyAgent") as shutdown:
            while not shutdown.should_stop:
                await asyncio.sleep(1)
    """

    def __init__(self, service_name: str) -> None:
        self.service_name = service_name
        self._stop_event = asyncio.Event()
        self._cleanup_callbacks: list[Callable[[], Any]] = []
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def should_stop(self) -> bool:
        return self._stop_event.is_set()

    def add_cleanup(self, callback: Callable[[], Any]) -> None:
        """Register a cleanup callback to run on shutdown."""
        self._cleanup_callbacks.append(callback)

    def _signal_handler(self) -> None:
        logger.info("%s received shutdown signal", self.service_name)
        self._stop_event.set()

    async def __aenter__(self) -> GracefulShutdown:
        self._loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                self._loop.add_signal_handler(sig, self._signal_handler)
            except NotImplementedError:
                # Windows does not support add_signal_handler
                pass
        logger.info("%s graceful shutdown handler registered", self.service_name)
        return self

    async def __aexit__(self, *_exc: object) -> None:
        logger.info(
            "%s shutting down, running %d cleanup callbacks ...",
            self.service_name,
            len(self._cleanup_callbacks),
        )
        for cb in reversed(self._cleanup_callbacks):
            try:
                result = cb()
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                logger.exception("%s cleanup callback failed", self.service_name)
        logger.info("%s shutdown complete", self.service_name)
