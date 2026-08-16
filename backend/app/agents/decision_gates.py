"""Deterministic recommendation gates and contrarian pressure."""

from __future__ import annotations

from app.agents.schemas import ContrarianAnalysis
from app.models.enums import Recommendation

BORDERLINE_SCORE_MIN = 45.0
BORDERLINE_SCORE_MAX = 60.0
CONFIDENCE_FLOOR = 0.35


def is_borderline(*, overall_score: float, recommendation: Recommendation) -> bool:
    if recommendation in (
        Recommendation.CONSIDER,
        Recommendation.WAIT,
        Recommendation.LOW_PRIORITY,
    ):
        return True
    return BORDERLINE_SCORE_MIN <= overall_score <= BORDERLINE_SCORE_MAX


def apply_confidence_floor(recommendation: Recommendation, confidence: float) -> Recommendation:
    if confidence < CONFIDENCE_FLOOR and recommendation in (
        Recommendation.STRONGLY_PURSUE,
        Recommendation.PURSUE,
    ):
        return Recommendation.CONSIDER
    return recommendation


def apply_contrarian_pressure(
    recommendation: Recommendation,
    confidence: float,
    analysis: ContrarianAnalysis | None,
) -> tuple[Recommendation, float, bool]:
    """Return updated recommendation, confidence, and whether it changed."""
    original = recommendation
    updated = apply_confidence_floor(recommendation, confidence)
    adjusted_confidence = confidence

    if analysis is None:
        return updated, adjusted_confidence, updated != original

    pressure = analysis.verdict_pressure
    if pressure >= 0.75 and updated == Recommendation.STRONGLY_PURSUE:
        updated = Recommendation.PURSUE
        adjusted_confidence *= 0.85
    elif pressure >= 0.55 and updated in (
        Recommendation.STRONGLY_PURSUE,
        Recommendation.PURSUE,
    ):
        updated = Recommendation.CONSIDER
        adjusted_confidence *= 0.75
    elif pressure >= 0.4 and updated == Recommendation.STRONGLY_PURSUE:
        updated = Recommendation.PURSUE
        adjusted_confidence *= 0.9

    return updated, adjusted_confidence, updated != original
