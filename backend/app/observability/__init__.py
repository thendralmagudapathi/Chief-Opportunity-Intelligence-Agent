"""Tracing, metrics and cost accounting (Phase 7).

OpenTelemetry is the instrumentation API; Langfuse consumes the exported
stream and MLflow tracks evaluation and training runs. Traces are additionally
persisted to ``agent_runs`` / ``agent_tasks`` / ``tool_calls`` so the Agent Trace
UI keeps working when no collector is reachable.
"""
