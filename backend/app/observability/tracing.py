"""OpenTelemetry setup and span helpers."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from typing import Any

from app.core.config import Settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_tracer: Any | None = None
_initialized = False


def setup_tracing(settings: Settings) -> None:
    global _tracer, _initialized
    if _initialized:
        return
    _initialized = True

    if not settings.observability.otel_enabled:
        _tracer = _NoopTracer()
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource.create(
            {
                "service.name": settings.observability.service_name,
                "service.version": settings.version,
                "deployment.environment": str(settings.environment),
            }
        )
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=settings.observability.otel_endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer(settings.observability.service_name)
        logger.info("otel_tracing_enabled", endpoint=settings.observability.otel_endpoint)
    except ImportError:
        logger.warning("otel_packages_missing", detail="Install oia-backend[observability]")
        _tracer = _NoopTracer()


def get_tracer() -> Any:
    if _tracer is None:
        return _NoopTracer()
    return _tracer


@contextmanager
def span(name: str, **attributes: object) -> Iterator[Any]:
    tracer = get_tracer()
    with tracer.start_as_current_span(name) as current:
        for key, value in attributes.items():
            current.set_attribute(key, str(value))
        yield current


@asynccontextmanager
async def async_span(name: str, **attributes: object) -> AsyncIterator[Any]:
    with span(name, **attributes) as current:
        yield current


class _NoopSpan:
    def set_attribute(self, *_args: object, **_kwargs: object) -> None:
        return None

    def record_exception(self, *_args: object, **_kwargs: object) -> None:
        return None


class _NoopTracer:
    @contextmanager
    def start_as_current_span(self, _name: str) -> Iterator[_NoopSpan]:
        yield _NoopSpan()
