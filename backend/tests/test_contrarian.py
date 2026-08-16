"""Contrarian pressure and borderline decision tests."""

from __future__ import annotations

import uuid

from app.agents.decision_gates import apply_contrarian_pressure, is_borderline
from app.agents.schemas import ContrarianAnalysis
from app.models.enums import Recommendation


def test_borderline_detects_mid_scores() -> None:
    assert is_borderline(overall_score=52.0, recommendation=Recommendation.PURSUE)


def test_contrarian_changes_at_least_fifteen_percent_of_borderline_cases() -> None:
    cases = [
        (Recommendation.STRONGLY_PURSUE, 0.8, 0.62),
        (Recommendation.PURSUE, 0.7, 0.58),
        (Recommendation.CONSIDER, 0.55, 0.55),
        (Recommendation.WAIT, 0.5, 0.5),
        (Recommendation.STRONGLY_PURSUE, 0.75, 0.78),
        (Recommendation.PURSUE, 0.65, 0.61),
    ]
    changed = 0
    for recommendation, confidence, pressure in cases:
        if not is_borderline(overall_score=50.0, recommendation=recommendation):
            continue
        analysis = ContrarianAnalysis(
            opportunity_id=uuid.uuid4(),
            verdict_pressure=pressure,
            failure_modes=["competition"],
        )
        updated, _, did_change = apply_contrarian_pressure(recommendation, confidence, analysis)
        if did_change or updated != recommendation:
            changed += 1
    assert changed / len(cases) >= 0.15
