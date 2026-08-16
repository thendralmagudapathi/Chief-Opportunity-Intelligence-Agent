"""Phase 6 golden-set quality harness."""

from __future__ import annotations

import uuid

from app.agents.decision_gates import apply_contrarian_pressure
from app.agents.schemas import AgentDecision, ContrarianAnalysis
from app.models.enums import Recommendation


def _quality_score(decisions: list[AgentDecision]) -> float:
    if not decisions:
        return 0.0
    total = 0.0
    for decision in decisions:
        score = 0.0
        if decision.headline_reason:
            score += 0.2
        if decision.why_this:
            score += 0.2
        if decision.confidence >= 0.35:
            score += 0.2
        if decision.what_could_go_wrong:
            score += 0.2
        if decision.recommendation != Recommendation.STRONGLY_PURSUE or decision.confidence <= 0.8:
            score += 0.2
        total += score
    return total / len(decisions)


def test_phase6_improves_borderline_quality_over_baseline() -> None:
    baseline = AgentDecision(
        opportunity_id=uuid.uuid4(),
        recommendation=Recommendation.STRONGLY_PURSUE,
        overall_score=52.0,
        confidence=0.82,
        headline_reason="Looks good",
        why_this=["Skill overlap"],
        why_now=["Open role"],
        why_me=["Profile fit"],
        what_could_go_wrong=[],
    )
    analysis = ContrarianAnalysis(
        opportunity_id=baseline.opportunity_id,
        verdict_pressure=0.62,
        failure_modes=["High competition"],
        contradicting_evidence=["Many applicants expected"],
    )
    updated_recommendation, updated_confidence, _ = apply_contrarian_pressure(
        baseline.recommendation,
        baseline.confidence,
        analysis,
    )
    phase6 = baseline.model_copy(
        update={
            "recommendation": updated_recommendation,
            "confidence": updated_confidence,
            "what_could_go_wrong": analysis.failure_modes,
        }
    )
    assert _quality_score([phase6]) > _quality_score([baseline])
