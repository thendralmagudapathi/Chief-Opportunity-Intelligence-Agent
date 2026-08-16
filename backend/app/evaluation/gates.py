"""Gate thresholds from docs/EVALUATION_PLAN.md."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GateThreshold:
    metric: str
    minimum: float | None = None
    maximum: float | None = None
    hard: bool = False


CI_GATE_THRESHOLDS: tuple[GateThreshold, ...] = (
    GateThreshold("recall_at_20", minimum=0.90),
    GateThreshold("ndcg_at_10", minimum=0.80),
    GateThreshold("tool_selection_accuracy", minimum=0.90),
    GateThreshold("tool_argument_validity", minimum=0.95),
    GateThreshold("agent_routing_accuracy", minimum=0.90),
    GateThreshold("task_completion_rate", minimum=0.95),
    GateThreshold("trace_completeness_rate", minimum=1.00, hard=True),
    GateThreshold("faithfulness", minimum=0.85, hard=True),
    GateThreshold("failure_rate", maximum=0.03),
)

NOISE_BAND_SIGMA = 2.0


def evaluate_gates(
    metrics: dict[str, float],
    *,
    baseline: dict[str, float] | None = None,
    noise_sigma: dict[str, float] | None = None,
) -> tuple[bool, list[str]]:
    """Return (passed, failures). Applies optional 2-sigma noise band vs baseline."""
    failures: list[str] = []
    for gate in CI_GATE_THRESHOLDS:
        value = metrics.get(gate.metric)
        if value is None:
            failures.append(f"missing metric: {gate.metric}")
            continue
        if gate.minimum is not None and value < gate.minimum:
            if baseline and noise_sigma:
                base = baseline.get(gate.metric, value)
                sigma = noise_sigma.get(gate.metric, 0.0)
                if value >= base - NOISE_BAND_SIGMA * sigma:
                    continue
            failures.append(f"{gate.metric}={value:.3f} below minimum {gate.minimum:.3f}")
        if gate.maximum is not None and value > gate.maximum:
            failures.append(f"{gate.metric}={value:.3f} above maximum {gate.maximum:.3f}")
    return len(failures) == 0, failures
