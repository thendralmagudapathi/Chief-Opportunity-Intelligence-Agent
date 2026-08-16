"""Operational alert helpers."""

from __future__ import annotations

from app.core.logging import get_logger
from app.observability.metrics import MetricSnapshot, registry

logger = get_logger(__name__)


def check_operational_alerts(
    *,
    baseline: MetricSnapshot | None = None,
    tool_failure_rate_threshold: float = 0.10,
    structured_output_failure_threshold: float = 0.05,
) -> list[str]:
    snapshot = registry.snapshot()
    alerts: list[str] = []

    tool_calls = snapshot.counters.get("tool_calls", 0.0)
    tool_failures = snapshot.counters.get("tool_failures", 0.0)
    if tool_calls > 0 and tool_failures / tool_calls > tool_failure_rate_threshold:
        alerts.append(f"tool failure rate {tool_failures / tool_calls:.1%}")

    validation_failures = snapshot.counters.get("structured_output_failures", 0.0)
    llm_calls = snapshot.counters.get("llm_calls", 0.0)
    if llm_calls > 0 and validation_failures / llm_calls > structured_output_failure_threshold:
        alerts.append(f"structured output failure rate {validation_failures / llm_calls:.1%}")

    if baseline is not None:
        alerts.extend(registry.drift_alerts(baseline=baseline))

    for alert in alerts:
        logger.warning("operational_alert", alert=alert)
    return alerts
