"""
OpenTelemetry integration for AGNOS distributed tracing.

Exports traces and metrics to AGNOS OpenTelemetry collector.
Falls back to no-op when disabled or when opentelemetry-sdk is not installed.

Configure via:
- AGNOS_OTEL_ENABLED: Enable OpenTelemetry (default: false)
- AGNOS_OTEL_ENDPOINT: OTLP collector endpoint (default: http://localhost:4317)
- AGNOS_OTEL_SERVICE_NAME: Service name (default: agnostic-qa)
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Generator

logger = logging.getLogger(__name__)

_OTEL_ENABLED = os.getenv("AGNOS_OTEL_ENABLED", "false").lower() == "true"
_OTEL_ENDPOINT = os.getenv("AGNOS_OTEL_ENDPOINT", "http://localhost:4317")
_OTEL_SERVICE_NAME = os.getenv("AGNOS_OTEL_SERVICE_NAME", "agnostic-qa")

try:
    from opentelemetry import metrics as otel_metrics
    from opentelemetry import trace as otel_trace
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
        OTLPMetricExporter,
    )
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
        OTLPSpanExporter,
    )
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    _OTEL_AVAILABLE = True
except ImportError:
    _OTEL_AVAILABLE = False


# ------------------------------------------------------------------
# No-op fallbacks
# ------------------------------------------------------------------


class _NoOpSpan:
    def set_attribute(self, key: str, value: Any) -> None:
        pass

    def set_status(self, status: Any) -> None:
        pass

    def record_exception(self, exc: BaseException) -> None:
        pass

    def end(self) -> None:
        pass

    def __enter__(self) -> _NoOpSpan:
        return self

    def __exit__(self, *args: Any) -> None:
        pass


class _NoOpTracer:
    def start_as_current_span(self, name: str, **kwargs: Any) -> _NoOpSpan:
        return _NoOpSpan()

    def start_span(self, name: str, **kwargs: Any) -> _NoOpSpan:
        return _NoOpSpan()


class _NoOpMeter:
    def create_counter(self, name: str, **kwargs: Any) -> Any:
        return _NoOpMetricInstrument()

    def create_histogram(self, name: str, **kwargs: Any) -> Any:
        return _NoOpMetricInstrument()

    def create_up_down_counter(self, name: str, **kwargs: Any) -> Any:
        return _NoOpMetricInstrument()


class _NoOpMetricInstrument:
    def add(self, amount: float, attributes: dict | None = None) -> None:
        pass

    def record(self, amount: float, attributes: dict | None = None) -> None:
        pass


_noop_tracer = _NoOpTracer()
_noop_meter = _NoOpMeter()
_configured = False


# ------------------------------------------------------------------
# Setup
# ------------------------------------------------------------------


def configure_telemetry() -> None:
    """Initialize OpenTelemetry tracing and metrics export to AGNOS collector."""
    global _configured

    if _configured or not _OTEL_ENABLED or not _OTEL_AVAILABLE:
        if not _OTEL_AVAILABLE and _OTEL_ENABLED:
            logger.warning(
                "AGNOS_OTEL_ENABLED=true but opentelemetry packages not installed"
            )
        return

    try:
        resource = Resource.create(
            {
                "service.name": _OTEL_SERVICE_NAME,
                "service.version": os.getenv("AGNOSTIC_VERSION", "dev"),
                "deployment.environment": os.getenv("ENVIRONMENT", "development"),
            }
        )

        # Tracing
        tracer_provider = TracerProvider(resource=resource)
        span_exporter = OTLPSpanExporter(endpoint=_OTEL_ENDPOINT)
        tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
        otel_trace.set_tracer_provider(tracer_provider)

        # Metrics
        metric_exporter = OTLPMetricExporter(endpoint=_OTEL_ENDPOINT)
        metric_reader = PeriodicExportingMetricReader(metric_exporter)
        meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
        otel_metrics.set_meter_provider(meter_provider)

        _configured = True
        logger.info(
            "OpenTelemetry configured: endpoint=%s service=%s",
            _OTEL_ENDPOINT,
            _OTEL_SERVICE_NAME,
        )
    except Exception as exc:
        logger.warning("Failed to configure OpenTelemetry: %s", exc)


def get_tracer(name: str) -> Any:
    """Return an OpenTelemetry tracer or no-op."""
    if _configured and _OTEL_AVAILABLE:
        return otel_trace.get_tracer(name)
    return _noop_tracer


def get_meter(name: str) -> Any:
    """Return an OpenTelemetry meter or no-op."""
    if _configured and _OTEL_AVAILABLE:
        return otel_metrics.get_meter(name)
    return _noop_meter


@contextmanager
def trace_llm_call(
    method_name: str,
    model: str = "",
    agent: str = "",
) -> Generator[_NoOpSpan | Any, None, None]:
    """Context manager that creates a span for an LLM call."""
    tracer = get_tracer("agnostic.llm")
    if isinstance(tracer, _NoOpTracer):
        yield _NoOpSpan()
        return

    with tracer.start_as_current_span(f"llm.{method_name}") as span:
        span.set_attribute("llm.method", method_name)
        if model:
            span.set_attribute("llm.model", model)
        if agent:
            span.set_attribute("llm.agent", agent)
        yield span


@contextmanager
def trace_task(
    task_id: str,
    agent: str = "",
) -> Generator[_NoOpSpan | Any, None, None]:
    """Context manager that creates a span for task execution."""
    tracer = get_tracer("agnostic.task")
    if isinstance(tracer, _NoOpTracer):
        yield _NoOpSpan()
        return

    with tracer.start_as_current_span(f"task.{task_id}") as span:
        span.set_attribute("task.id", task_id)
        if agent:
            span.set_attribute("task.agent", agent)
        yield span
