"""In-process evaluation hooks (Phase 7).

Dataset definitions, the offline harness and metric implementations live in
``ml/evaluation``; this package holds what the running application needs:
metric emission, the CI gate helpers and the ``evaluation_runs`` writer. Metrics
and thresholds are specified in docs/EVALUATION_PLAN.md.
"""

from app.evaluation.gates import CI_GATE_THRESHOLDS, evaluate_gates
from app.evaluation.harness import CIHarness, HarnessResult, run_ci_harness
from app.evaluation.service import EvaluationService
from app.evaluation.trace_audit import TraceAuditResult, audit_investigation_trace

__all__ = [
    "CI_GATE_THRESHOLDS",
    "CIHarness",
    "EvaluationService",
    "HarnessResult",
    "TraceAuditResult",
    "audit_investigation_trace",
    "evaluate_gates",
    "run_ci_harness",
]
