"""Scoring-engine properties.

These tests do not touch the database. The engine is a pure function; if it
fails an invariant here, a stored score cannot be trusted.
"""

from __future__ import annotations

import random
from decimal import Decimal

import pytest
from app.models.enums import ObjectiveProfile, Recommendation
from app.services.scoring import (
    BENEFIT_DIMENSIONS,
    COST_DIMENSIONS,
    DIMENSION_QUANTUM,
    ONE,
    ZERO,
    Dimension,
    ScoringError,
    Weights,
    score,
    weights_for,
)

PROFILES = tuple(ObjectiveProfile)
ALL_DIMENSIONS = tuple(Dimension)


def _uniform(value: Decimal) -> dict[str, Decimal]:
    return {d.value: value for d in ALL_DIMENSIONS}


def test_every_profile_sums_to_one() -> None:
    for profile in PROFILES:
        weights = weights_for(profile)
        assert sum(weights.benefit.values(), ZERO) == ONE
        assert weights.effort >= ZERO and weights.risk >= ZERO
        assert weights.version == f"{profile.value}.v1"


def test_score_is_bounded_over_random_inputs() -> None:
    rng = random.Random(20260816)  # noqa: S311  (deterministic fixture, not crypto)
    weights = weights_for(ObjectiveProfile.CAREER)
    for _ in range(250):
        factors = {d.value: Decimal(str(round(rng.random(), 4))) for d in ALL_DIMENSIONS}
        if rng.random() < 0.2:
            # Drop a random subset so unknown-dimension handling is exercised.
            for dimension in rng.sample(ALL_DIMENSIONS, k=rng.randint(1, 6)):
                del factors[dimension.value]
        result = score(factors, weights)
        assert ZERO <= result.overall <= Decimal("100")
        assert ZERO <= result.confidence <= ONE
        assert result.benefit >= ZERO
        assert result.cost >= ONE


@pytest.mark.parametrize("profile", PROFILES)
def test_raising_a_benefit_dimension_never_lowers_the_score(profile: ObjectiveProfile) -> None:
    weights = weights_for(profile)
    base = _uniform(Decimal("0.4"))
    for dimension in BENEFIT_DIMENSIONS:
        low = score({**base, dimension.value: Decimal("0.1")}, weights)
        high = score({**base, dimension.value: Decimal("0.9")}, weights)
        assert high.overall >= low.overall, dimension.value


@pytest.mark.parametrize("dimension", COST_DIMENSIONS)
def test_raising_effort_or_risk_never_raises_the_score(dimension: Dimension) -> None:
    weights = weights_for(ObjectiveProfile.CAREER)
    base = _uniform(Decimal("0.5"))
    low = score({**base, dimension.value: Decimal("0.1")}, weights)
    high = score({**base, dimension.value: Decimal("0.9")}, weights)
    assert high.overall <= low.overall


def test_unknown_dimensions_are_redistributed_not_zeroed() -> None:
    """A product would collapse; the weighted sum must not.

    When every *known* benefit dimension has the same value, redistribution
    leaves ``benefit`` equal to that value, regardless of how many are missing.
    """
    weights = weights_for(ObjectiveProfile.CAREER)
    uniform = Decimal("0.7")
    full = {d.value: uniform for d in BENEFIT_DIMENSIONS}
    partial = {"fit_score": uniform, "value_score": uniform}
    one = {"fit_score": uniform}
    assert score(full, weights).benefit == uniform.quantize(DIMENSION_QUANTUM)
    assert score(partial, weights).benefit == uniform.quantize(DIMENSION_QUANTUM)
    assert score(one, weights).benefit == uniform.quantize(DIMENSION_QUANTUM)
    assert score({}, weights).benefit == ZERO
    assert score({}, weights).overall == ZERO


def test_unknown_cost_does_not_penalise_but_does_reduce_confidence() -> None:
    weights = weights_for(ObjectiveProfile.CAREER)
    benefits = {d.value: Decimal("0.8") for d in BENEFIT_DIMENSIONS}
    with_cost = score(
        {**benefits, "effort_score": Decimal("0.3"), "risk_score": Decimal("0.2")}, weights
    )
    without_cost = score(benefits, weights)
    assert without_cost.overall > with_cost.overall
    assert without_cost.confidence < with_cost.confidence
    assert with_cost.confidence == ONE


def test_identical_inputs_are_bit_identical() -> None:
    weights = weights_for(ObjectiveProfile.RESEARCH)
    factors = _uniform(Decimal("0.55"))
    first = score(factors, weights)
    second = score(factors, weights)
    assert first == second
    # A payload that survived a database round-trip must score the same.
    restored = {k: Decimal(v) for k, v in first.as_factors()["dimensions"].items() if v is not None}
    assert score(restored, weights).overall == first.overall


def test_override_is_normalised_and_versioned() -> None:
    overridden = weights_for(
        ObjectiveProfile.CAREER,
        {
            "fit_score": 5,
            "value_score": 5,
            "probability_of_success": 0,
            "strategic_value": 0,
            "time_sensitivity": 0,
            "learning_value": 0,
            "network_value": 0,
            "long_term_value": 0,
        },
    )
    assert overridden.version == "career.v1+override"
    assert sum(overridden.benefit.values(), ZERO) == ONE
    assert overridden.benefit[Dimension.FIT] == Decimal("0.5")
    with pytest.raises(ScoringError):
        weights_for(ObjectiveProfile.CAREER, {"not_a_dimension": 1})
    with pytest.raises(ScoringError):
        Weights.build("bad", {"fit_score": -1})


def test_ineligible_keeps_the_numeric_score() -> None:
    weights = weights_for(ObjectiveProfile.CAREER)
    eligible = score(_uniform(Decimal("0.8")), weights, eligible=True)
    blocked = score(_uniform(Decimal("0.8")), weights, eligible=False)
    assert blocked.overall == eligible.overall
    assert blocked.recommendation is Recommendation.INELIGIBLE
    assert eligible.recommendation is not Recommendation.INELIGIBLE


def test_low_confidence_caps_an_enthusiastic_verdict() -> None:
    weights = weights_for(ObjectiveProfile.CAREER)
    result = score({"fit_score": Decimal("1.0")}, weights)
    assert result.overall >= Decimal("66")
    assert result.confidence < Decimal("0.45")
    assert result.recommendation is Recommendation.WAIT
