"""In-process evaluation hooks (Phase 7).

Dataset definitions, the offline harness and metric implementations live in
``ml/evaluation``; this package holds only what the running application needs:
metric emission, the CI gate helpers and the ``evaluation_runs`` writer. Metrics
and thresholds are specified in docs/EVALUATION_PLAN.md.
"""
