"""Tracing, metrics and cost accounting (Phase 7).

OpenTelemetry is the instrumentation API; Langfuse consumes the exported
stream and MLflow tracks evaluation and training runs. Traces are additionally
persisted to ``agent_runs`` / ``agent_tasks`` / ``tool_calls`` so the Agent Trace
UI keeps working when no collector is reachable.
"""

from app.observability.alerts import check_operational_alerts
from app.observability.cost import CostLedger, InvestigationCostTracker
from app.observability.metrics import MetricsRegistry, StageTimer, registry
from app.observability.tracing import async_span, get_tracer, setup_tracing

__all__ = [
    "CostLedger",
    "InvestigationCostTracker",
    "MetricsRegistry",
    "StageTimer",
    "async_span",
    "check_operational_alerts",
    "get_tracer",
    "registry",
    "setup_tracing",
]
