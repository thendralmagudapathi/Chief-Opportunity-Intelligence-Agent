"""Observability helpers."""

from __future__ import annotations

from app.observability.metrics import registry
from app.observability.tracing import get_tracer, setup_tracing


def test_noop_tracer_when_otel_disabled(settings) -> None:
    setup_tracing(settings)
    tracer = get_tracer()
    with tracer.start_as_current_span("test.span"):
        registry.increment("test_counter")


def test_stage_timer_records_histogram() -> None:
    from app.observability.metrics import StageTimer

    timer = StageTimer("unit_test")
    timer.finish()
    snapshot = registry.snapshot()
    assert snapshot.histograms["stage_latency_ms.unit_test"]["count"] >= 1.0
