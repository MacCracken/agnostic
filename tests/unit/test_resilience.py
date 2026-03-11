"""Unit tests for shared.resilience — CircuitBreaker, retry_async, RetryConfig."""

import time

import pytest

from shared.resilience import (
    CircuitBreaker,
    CircuitState,
    GracefulShutdown,
    RetryConfig,
    retry_async,
)


class TestCircuitBreaker:
    def test_starts_closed(self):
        cb = CircuitBreaker(name="test")
        assert cb.state is CircuitState.CLOSED
        assert cb.can_execute() is True

    def test_opens_after_threshold_failures(self):
        cb = CircuitBreaker(name="test", failure_threshold=3)
        for _ in range(3):
            cb.record_failure()
        assert cb.state is CircuitState.OPEN
        assert cb.can_execute() is False

    def test_stays_closed_below_threshold(self):
        cb = CircuitBreaker(name="test", failure_threshold=5)
        for _ in range(4):
            cb.record_failure()
        assert cb.state is CircuitState.CLOSED
        assert cb.can_execute() is True

    def test_success_resets_failure_count(self):
        cb = CircuitBreaker(name="test", failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        # Should be reset — 3 more failures needed to trip
        cb.record_failure()
        cb.record_failure()
        assert cb.state is CircuitState.CLOSED

    def test_half_open_after_recovery_timeout(self):
        cb = CircuitBreaker(name="test", failure_threshold=1, recovery_timeout=0.01)
        cb.record_failure()
        assert cb.state is CircuitState.OPEN
        time.sleep(0.02)
        assert cb.state is CircuitState.HALF_OPEN
        assert cb.can_execute() is True

    def test_half_open_to_closed_on_success(self):
        cb = CircuitBreaker(name="test", failure_threshold=1, recovery_timeout=0.01)
        cb.record_failure()
        time.sleep(0.02)
        assert cb.state is CircuitState.HALF_OPEN
        cb.record_success()
        assert cb.state is CircuitState.CLOSED


class TestRetryConfig:
    def test_defaults(self):
        cfg = RetryConfig()
        assert cfg.max_retries == 3
        assert cfg.base_delay == 1.0
        assert cfg.max_delay == 60.0
        assert cfg.exponential_base == 2.0

    def test_custom_values(self):
        cfg = RetryConfig(max_retries=5, base_delay=0.5)
        assert cfg.max_retries == 5
        assert cfg.base_delay == 0.5


class TestRetryAsync:
    @pytest.mark.asyncio
    async def test_succeeds_first_try(self):
        call_count = 0

        @retry_async(RetryConfig(max_retries=3, base_delay=0.01))
        async def succeed():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = await succeed()
        assert result == "ok"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retries_then_succeeds(self):
        call_count = 0

        @retry_async(RetryConfig(max_retries=3, base_delay=0.01))
        async def fail_twice():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("not yet")
            return "ok"

        result = await fail_twice()
        assert result == "ok"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_exhausts_retries(self):
        @retry_async(RetryConfig(max_retries=2, base_delay=0.01))
        async def always_fail():
            raise RuntimeError("always")

        with pytest.raises(RuntimeError, match="always"):
            await always_fail()


class TestGracefulShutdown:
    @pytest.mark.asyncio
    async def test_should_stop_initially_false(self):
        async with GracefulShutdown("test") as shutdown:
            assert shutdown.should_stop is False
            # Manually trigger stop
            shutdown._stop_event.set()
            assert shutdown.should_stop is True

    @pytest.mark.asyncio
    async def test_cleanup_callbacks_run(self):
        cleaned = []

        async with GracefulShutdown("test") as shutdown:
            shutdown.add_cleanup(lambda: cleaned.append("a"))
            shutdown.add_cleanup(lambda: cleaned.append("b"))

        # Callbacks run in reverse order
        assert cleaned == ["b", "a"]
