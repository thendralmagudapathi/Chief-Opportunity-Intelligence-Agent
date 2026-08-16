"""The scoring engine.

``score()`` is a pure function: no I/O, no model access, no clock. Given the same
factors and weights it returns the same result forever, which is what makes a
stored score reproducible — every row records the factors and the
``weights_version`` that produced it, so any past recommendation can be recomputed
and diffed offline.

The arithmetic is the one fixed in ``docs/DATA_MODEL.md``::

    benefit = Σ wᵢ · dᵢ        over the benefit dimensions
    cost    = 1 + w_effort·effort + w_risk·risk
    overall = 100 · benefit / cost      clipped to [0, 100]

A weighted sum over a penalty denominator, rather than the product the brief
sketched: a product collapses to zero the moment one dimension is unknown, which
would make the score say "worthless" when it means "not yet known". Unknown
dimensions are instead dropped from the sum and their weight redistributed across
the dimensions that are known, so a partially-researched opportunity is scored on
what it has rather than punished for what it lacks. How much was known is
reported separately as ``confidence``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from app.models.enums import ObjectiveProfile, Recommendation

ZERO = Decimal("0")
ONE = Decimal("1")
HUNDRED = Decimal("100")

#: Dimensions are stored to four decimal places, overall scores to two, matching
#: the column precision so a round trip through the database changes nothing.
DIMENSION_QUANTUM = Decimal("0.0001")
SCORE_QUANTUM = Decimal("0.01")


class Dimension(StrEnum):
    """Scoring dimensions, named exactly as the ``opportunity_scores`` columns.

    Keeping the names identical means ``factors`` can be persisted, re-read and
    diffed without a translation layer that could drift.
    """

    FIT = "fit_score"
    VALUE = "value_score"
    PROBABILITY = "probability_of_success"
    STRATEGIC = "strategic_value"
    TIME_SENSITIVITY = "time_sensitivity"
    LEARNING = "learning_value"
    NETWORK = "network_value"
    LONG_TERM = "long_term_value"
    EFFORT = "effort_score"
    RISK = "risk_score"


BENEFIT_DIMENSIONS: tuple[Dimension, ...] = (
    Dimension.FIT,
    Dimension.VALUE,
    Dimension.PROBABILITY,
    Dimension.STRATEGIC,
    Dimension.TIME_SENSITIVITY,
    Dimension.LEARNING,
    Dimension.NETWORK,
    Dimension.LONG_TERM,
)
COST_DIMENSIONS: tuple[Dimension, ...] = (Dimension.EFFORT, Dimension.RISK)

#: Human-readable names for the explanation payload.
DIMENSION_LABELS: Mapping[Dimension, str] = MappingProxyType(
    {
        Dimension.FIT: "fit with your profile",
        Dimension.VALUE: "direct value",
        Dimension.PROBABILITY: "probability of success",
        Dimension.STRATEGIC: "strategic value",
        Dimension.TIME_SENSITIVITY: "time sensitivity",
        Dimension.LEARNING: "learning value",
        Dimension.NETWORK: "network value",
        Dimension.LONG_TERM: "long-term value",
        Dimension.EFFORT: "effort required",
        Dimension.RISK: "risk",
    }
)


class ScoringError(ValueError):
    """Raised when a weight vector cannot be used."""


def _clamp_unit(value: object) -> Decimal | None:
    """Coerce to a Decimal in [0, 1]; anything unusable becomes ``None``.

    Out-of-range numbers are clamped rather than rejected: an upstream producer
    reporting 1.2 means "as high as it goes", and refusing to score the whole
    opportunity over it would be a worse answer than capping it.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except (ArithmeticError, ValueError, TypeError):
        return None
    if not number.is_finite():
        return None
    return min(max(number, ZERO), ONE)


@dataclass(frozen=True, slots=True)
class Weights:
    """A benefit weight vector plus the two cost coefficients.

    Benefit weights always sum to exactly one, so ``benefit`` is directly
    comparable across profiles and across versions.
    """

    version: str
    benefit: Mapping[Dimension, Decimal]
    effort: Decimal
    risk: Decimal

    def __post_init__(self) -> None:
        missing = set(BENEFIT_DIMENSIONS) - set(self.benefit)
        if missing:
            raise ScoringError(
                f"weight vector {self.version} is missing: "
                + ", ".join(sorted(d.value for d in missing))
            )
        if any(w < ZERO for w in self.benefit.values()):
            raise ScoringError(f"weight vector {self.version} has a negative weight")
        if self.effort < ZERO or self.risk < ZERO:
            raise ScoringError(f"weight vector {self.version} has a negative cost weight")
        total = sum(self.benefit.values(), ZERO)
        if total <= ZERO:
            raise ScoringError(f"weight vector {self.version} has no positive benefit weight")
        if abs(total - ONE) > Decimal("0.000001"):
            raise ScoringError(f"weight vector {self.version} sums to {total}, expected 1")

    @classmethod
    def build(
        cls,
        version: str,
        benefit: Mapping[Dimension, object] | Mapping[str, object],
        *,
        effort: object = Decimal("0.5"),
        risk: object = Decimal("0.5"),
    ) -> Weights:
        """Normalise raw weights into a valid vector.

        Callers supply relative importances; the ratios are what matter, so the
        benefit weights are rescaled to sum to one rather than demanding the
        caller do the arithmetic.
        """
        raw: dict[Dimension, Decimal] = {}
        for key, value in benefit.items():
            try:
                dimension = Dimension(key)
            except ValueError as exc:
                raise ScoringError(f"unknown scoring dimension: {key!r}") from exc
            if dimension in COST_DIMENSIONS:
                raise ScoringError(f"{dimension.value} is a cost dimension, not a benefit weight")
            number = _to_weight(value, dimension.value)
            raw[dimension] = number

        for dimension in BENEFIT_DIMENSIONS:
            raw.setdefault(dimension, ZERO)

        total = sum(raw.values(), ZERO)
        if total <= ZERO:
            raise ScoringError("benefit weights must include at least one positive value")

        normalised = {d: (w / total) for d, w in raw.items()}
        # Absorb the rounding remainder into the largest weight so the vector sums
        # to exactly one and the invariant holds under equality, not tolerance.
        quantised = {d: w.quantize(Decimal("0.00000001")) for d, w in normalised.items()}
        drift = ONE - sum(quantised.values(), ZERO)
        heaviest = max(quantised, key=lambda d: quantised[d])
        quantised[heaviest] += drift

        return cls(
            version=version,
            benefit=MappingProxyType(quantised),
            effort=_to_weight(effort, "effort"),
            risk=_to_weight(risk, "risk"),
        )

    def with_override(self, override: Mapping[str, Any] | None, *, version: str) -> Weights:
        """Apply a goal's partial weight override on top of this vector.

        Overrides come from user-supplied JSON, so an unknown key or a negative
        number is an error rather than something to silently ignore — a weight
        that was quietly dropped would produce a plausible score for the wrong
        reason.
        """
        if not override:
            return self
        merged: dict[str, object] = {d.value: w for d, w in self.benefit.items()}
        effort: object = self.effort
        risk: object = self.risk
        for key, value in override.items():
            if key == Dimension.EFFORT.value:
                effort = value
            elif key == Dimension.RISK.value:
                risk = value
            else:
                try:
                    merged[Dimension(key)] = value
                except ValueError as exc:
                    raise ScoringError(f"unknown scoring dimension in override: {key!r}") from exc
        return Weights.build(version, merged, effort=effort, risk=risk)


def _to_weight(value: object, label: str) -> Decimal:
    if value is None or isinstance(value, bool):
        raise ScoringError(f"weight for {label} must be a number")
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except (ArithmeticError, ValueError, TypeError) as exc:
        raise ScoringError(f"weight for {label} must be a number, got {value!r}") from exc
    if not number.is_finite() or number < ZERO:
        raise ScoringError(f"weight for {label} must be a finite, non-negative number")
    return number


def _profile(
    profile: ObjectiveProfile,
    weights: Mapping[Dimension, str],
    *,
    effort: str,
    risk: str,
) -> Weights:
    return Weights.build(
        f"{profile.value}.v1",
        {d: Decimal(w) for d, w in weights.items()},
        effort=Decimal(effort),
        risk=Decimal(risk),
    )


#: Default weight vector per objective. The numbers encode what each objective is
#: actually for: an income goal cares about money now and cares little what the
#: role teaches, a learning goal is the reverse, and a startup goal tolerates risk
#: that a career goal would not.
WEIGHT_PROFILES: Mapping[ObjectiveProfile, Weights] = MappingProxyType(
    {
        ObjectiveProfile.CAREER: _profile(
            ObjectiveProfile.CAREER,
            {
                Dimension.FIT: "0.22",
                Dimension.VALUE: "0.14",
                Dimension.PROBABILITY: "0.16",
                Dimension.STRATEGIC: "0.14",
                Dimension.TIME_SENSITIVITY: "0.06",
                Dimension.LEARNING: "0.10",
                Dimension.NETWORK: "0.06",
                Dimension.LONG_TERM: "0.12",
            },
            effort="0.35",
            risk="0.45",
        ),
        ObjectiveProfile.INCOME: _profile(
            ObjectiveProfile.INCOME,
            {
                Dimension.FIT: "0.16",
                Dimension.VALUE: "0.34",
                Dimension.PROBABILITY: "0.20",
                Dimension.STRATEGIC: "0.06",
                Dimension.TIME_SENSITIVITY: "0.12",
                Dimension.LEARNING: "0.03",
                Dimension.NETWORK: "0.03",
                Dimension.LONG_TERM: "0.06",
            },
            effort="0.55",
            risk="0.50",
        ),
        ObjectiveProfile.BUSINESS: _profile(
            ObjectiveProfile.BUSINESS,
            {
                Dimension.FIT: "0.14",
                Dimension.VALUE: "0.24",
                Dimension.PROBABILITY: "0.14",
                Dimension.STRATEGIC: "0.18",
                Dimension.TIME_SENSITIVITY: "0.08",
                Dimension.LEARNING: "0.04",
                Dimension.NETWORK: "0.08",
                Dimension.LONG_TERM: "0.10",
            },
            effort="0.40",
            risk="0.45",
        ),
        ObjectiveProfile.LEARNING: _profile(
            ObjectiveProfile.LEARNING,
            {
                Dimension.FIT: "0.14",
                Dimension.VALUE: "0.06",
                Dimension.PROBABILITY: "0.12",
                Dimension.STRATEGIC: "0.10",
                Dimension.TIME_SENSITIVITY: "0.06",
                Dimension.LEARNING: "0.32",
                Dimension.NETWORK: "0.08",
                Dimension.LONG_TERM: "0.12",
            },
            effort="0.30",
            risk="0.25",
        ),
        ObjectiveProfile.NETWORKING: _profile(
            ObjectiveProfile.NETWORKING,
            {
                Dimension.FIT: "0.12",
                Dimension.VALUE: "0.06",
                Dimension.PROBABILITY: "0.14",
                Dimension.STRATEGIC: "0.12",
                Dimension.TIME_SENSITIVITY: "0.10",
                Dimension.LEARNING: "0.08",
                Dimension.NETWORK: "0.30",
                Dimension.LONG_TERM: "0.08",
            },
            effort="0.30",
            risk="0.25",
        ),
        ObjectiveProfile.STARTUP: _profile(
            ObjectiveProfile.STARTUP,
            {
                Dimension.FIT: "0.14",
                Dimension.VALUE: "0.14",
                Dimension.PROBABILITY: "0.10",
                Dimension.STRATEGIC: "0.20",
                Dimension.TIME_SENSITIVITY: "0.10",
                Dimension.LEARNING: "0.08",
                Dimension.NETWORK: "0.10",
                Dimension.LONG_TERM: "0.14",
            },
            # A startup objective is chosen in full knowledge of the risk, so
            # risk weighs less here than anywhere else.
            effort="0.30",
            risk="0.20",
        ),
        ObjectiveProfile.RESEARCH: _profile(
            ObjectiveProfile.RESEARCH,
            {
                Dimension.FIT: "0.20",
                Dimension.VALUE: "0.08",
                Dimension.PROBABILITY: "0.14",
                Dimension.STRATEGIC: "0.16",
                Dimension.TIME_SENSITIVITY: "0.06",
                Dimension.LEARNING: "0.16",
                Dimension.NETWORK: "0.08",
                Dimension.LONG_TERM: "0.12",
            },
            effort="0.35",
            risk="0.30",
        ),
    }
)

#: Score thresholds for each verdict. Tuned so that the default of "we know
#: nothing" lands in CONSIDER rather than in either extreme.
RECOMMENDATION_THRESHOLDS: tuple[tuple[Decimal, Recommendation], ...] = (
    (Decimal("82"), Recommendation.STRONGLY_PURSUE),
    (Decimal("66"), Recommendation.PURSUE),
    (Decimal("45"), Recommendation.CONSIDER),
    (Decimal("28"), Recommendation.LOW_PRIORITY),
)

#: Below this share of known weight, an enthusiastic verdict is not earned: the
#: engine reports WAIT, meaning "worth pursuing on what we know, but find out
#: more before acting".
CONFIDENCE_FLOOR = Decimal("0.45")

ENGINE_VERSION = "0.2.0"


@dataclass(frozen=True, slots=True)
class ScoreResult:
    """The full, auditable output of one scoring run."""

    overall: Decimal
    confidence: Decimal
    recommendation: Recommendation
    weights_version: str
    engine_version: str
    #: Clamped inputs, ``None`` where the dimension was unknown.
    dimensions: Mapping[Dimension, Decimal | None]
    #: Weight actually applied after redistribution, for the known dimensions.
    effective_weights: Mapping[Dimension, Decimal]
    #: ``effective_weight * value`` per dimension; these sum to ``benefit``.
    contributions: Mapping[Dimension, Decimal]
    benefit: Decimal
    cost: Decimal
    explanation: dict[str, Any] = field(default_factory=dict)

    def as_factors(self) -> dict[str, Any]:
        """The payload persisted to ``opportunity_scores.factors``.

        Sufficient on its own to recompute the score offline.
        """
        return {
            "dimensions": {
                d.value: (str(v) if v is not None else None) for d, v in self.dimensions.items()
            },
            "effective_weights": {d.value: str(w) for d, w in self.effective_weights.items()},
            "contributions": {d.value: str(c) for d, c in self.contributions.items()},
            "benefit": str(self.benefit),
            "cost": str(self.cost),
            "confidence": str(self.confidence),
            "weights_version": self.weights_version,
            "engine_version": self.engine_version,
        }


#: Factors may arrive keyed by enum member (freshly derived) or by column name
#: (read back from a stored ``factors`` payload).
FactorMapping = Mapping[Dimension, Decimal | None] | Mapping[str, object]


def score(
    factors: FactorMapping,
    weights: Weights,
    *,
    eligible: bool | None = None,
    days_to_deadline: int | None = None,
) -> ScoreResult:
    """Score one opportunity against one weight vector.

    ``factors`` maps dimension names to values in [0, 1]. A missing key and an
    explicit ``None`` mean the same thing — not known — and are excluded from the
    benefit sum with their weight redistributed proportionally.

    ``eligible=False`` produces an INELIGIBLE verdict. The numeric score is still
    computed and returned: it explains how much was given up, and if the
    eligibility judgement is later corrected the score is already there.
    """
    # Accept either enum members or their string names as keys, so a payload
    # read back from ``factors`` JSON scores identically to a freshly built one.
    supplied = {
        (key.value if isinstance(key, Dimension) else str(key)): value
        for key, value in factors.items()
    }
    values = {d: _clamp_unit(supplied.get(d.value)) for d in Dimension}

    known = [d for d in BENEFIT_DIMENSIONS if values[d] is not None]
    known_weight = sum((weights.benefit[d] for d in known), ZERO)

    effective: dict[Dimension, Decimal] = {}
    contributions: dict[Dimension, Decimal] = {}
    if known_weight > ZERO:
        for dimension in known:
            # Redistribution is proportional, which preserves the relative
            # importance the profile expressed among whatever is known.
            share = weights.benefit[dimension] / known_weight
            effective[dimension] = share
            contributions[dimension] = share * (values[dimension] or ZERO)

    benefit = sum(contributions.values(), ZERO)

    effort = values[Dimension.EFFORT] or ZERO
    risk = values[Dimension.RISK] or ZERO
    cost = ONE + weights.effort * effort + weights.risk * risk

    raw_overall = (HUNDRED * benefit / cost) if cost > ZERO else ZERO
    overall = min(max(raw_overall, ZERO), HUNDRED).quantize(SCORE_QUANTUM, ROUND_HALF_UP)

    # Confidence is the share of all weight — benefit and cost — that was known.
    # It measures how much of the picture we have, not how good it looks. Cost
    # counts because an unknown effort or risk adds no penalty to the score, so
    # without this an opportunity nobody has assessed for risk would look as
    # trustworthy as one that has been.
    total_weight = ONE + weights.effort + weights.risk
    known_total = known_weight
    if values[Dimension.EFFORT] is not None:
        known_total += weights.effort
    if values[Dimension.RISK] is not None:
        known_total += weights.risk
    confidence = (known_total / total_weight).quantize(DIMENSION_QUANTUM, ROUND_HALF_UP)

    recommendation = recommend(overall, confidence, eligible=eligible)

    return ScoreResult(
        overall=overall,
        confidence=confidence,
        recommendation=recommendation,
        weights_version=weights.version,
        engine_version=ENGINE_VERSION,
        dimensions=MappingProxyType(
            {
                d: (v.quantize(DIMENSION_QUANTUM, ROUND_HALF_UP) if v is not None else None)
                for d, v in values.items()
            }
        ),
        effective_weights=MappingProxyType(
            {d: w.quantize(Decimal("0.000001"), ROUND_HALF_UP) for d, w in effective.items()}
        ),
        contributions=MappingProxyType(
            {d: c.quantize(DIMENSION_QUANTUM, ROUND_HALF_UP) for d, c in contributions.items()}
        ),
        benefit=benefit.quantize(DIMENSION_QUANTUM, ROUND_HALF_UP),
        cost=cost.quantize(DIMENSION_QUANTUM, ROUND_HALF_UP),
        explanation=explain(
            values=values,
            contributions=contributions,
            overall=overall,
            confidence=confidence,
            recommendation=recommendation,
            days_to_deadline=days_to_deadline,
            eligible=eligible,
        ),
    )


def recommend(
    overall: Decimal, confidence: Decimal, *, eligible: bool | None = None
) -> Recommendation:
    """Map a score onto a verdict."""
    if eligible is False:
        return Recommendation.INELIGIBLE

    verdict = Recommendation.IGNORE
    for threshold, candidate in RECOMMENDATION_THRESHOLDS:
        if overall >= threshold:
            verdict = candidate
            break

    if confidence < CONFIDENCE_FLOOR and verdict in (
        Recommendation.STRONGLY_PURSUE,
        Recommendation.PURSUE,
    ):
        return Recommendation.WAIT
    return verdict


def explain(
    *,
    values: Mapping[Dimension, Decimal | None],
    contributions: Mapping[Dimension, Decimal],
    overall: Decimal,
    confidence: Decimal,
    recommendation: Recommendation,
    days_to_deadline: int | None,
    eligible: bool | None,
) -> dict[str, Any]:
    """Build the WHY THIS / WHY NOW / WHY ME / WHAT COULD GO WRONG payload.

    Phase 2 can only explain arithmetic, so every line here is derived from the
    numbers. The evidence lists stay empty until the research agents fill them;
    an empty list is honest, invented prose would not be.
    """
    ranked = sorted(contributions.items(), key=lambda kv: kv[1], reverse=True)
    strong = [(d, c) for d, c in ranked if c > ZERO][:3]

    why_this = [
        f"{DIMENSION_LABELS[d]} scores {values[d]} and contributes "
        f"{(c * HUNDRED).quantize(SCORE_QUANTUM, ROUND_HALF_UP)} of the 100 points"
        for d, c in strong
    ]

    why_now: list[str] = []
    if days_to_deadline is not None:
        if days_to_deadline < 0:
            why_now.append(f"the deadline passed {abs(days_to_deadline)} days ago")
        elif days_to_deadline == 0:
            why_now.append("the deadline is today")
        else:
            why_now.append(f"{days_to_deadline} days remain before the deadline")
    time_sensitivity = values[Dimension.TIME_SENSITIVITY]
    if time_sensitivity is not None and time_sensitivity >= Decimal("0.6"):
        why_now.append("this opportunity is time sensitive")
    if not why_now:
        why_now.append("no deadline is known, so there is no timing pressure to report")

    why_me: list[str] = []
    for dimension in (Dimension.FIT, Dimension.PROBABILITY):
        value = values[dimension]
        if value is not None:
            why_me.append(f"{DIMENSION_LABELS[dimension]} is {value}")
    if not why_me:
        why_me.append("no fit assessment has been made yet")

    what_could_go_wrong: list[str] = []
    if eligible is False:
        what_could_go_wrong.append("you do not currently meet the stated eligibility requirements")
    for dimension in COST_DIMENSIONS:
        value = values[dimension]
        if value is not None and value >= Decimal("0.5"):
            what_could_go_wrong.append(f"{DIMENSION_LABELS[dimension]} is high at {value}")
    weakest = [
        (d, value)
        for d, _ in reversed(ranked)
        if (value := values[d]) is not None and value < Decimal("0.35")
    ]
    what_could_go_wrong.extend(
        f"{DIMENSION_LABELS[d]} is low at {value}" for d, value in weakest[:2]
    )
    if not what_could_go_wrong:
        what_could_go_wrong.append(
            "no specific risk has been identified from the available factors"
        )

    missing = [DIMENSION_LABELS[d] for d in Dimension if values[d] is None]

    return {
        "why_this": why_this or ["nothing is known about this opportunity yet"],
        "why_now": why_now,
        "why_me": why_me,
        "what_could_go_wrong": what_could_go_wrong,
        "supporting_evidence": [],
        "contradicting_evidence": [],
        "missing_information": missing,
        "next_step": _next_step(recommendation, missing),
        "summary": (
            f"Scored {overall} with {(confidence * HUNDRED).quantize(SCORE_QUANTUM)}% "
            f"of the weighted picture known."
        ),
    }


def _next_step(recommendation: Recommendation, missing: list[str]) -> str:
    if recommendation is Recommendation.INELIGIBLE:
        return "Confirm the eligibility requirement before spending any more time on this."
    if recommendation is Recommendation.WAIT:
        return (
            "Gather the missing factors before acting — "
            f"{', '.join(missing[:3])} are still unknown."
            if missing
            else "Verify the strongest factors before acting."
        )
    if recommendation in (Recommendation.STRONGLY_PURSUE, Recommendation.PURSUE):
        return "Prepare an application and confirm the deadline against the source."
    if recommendation is Recommendation.CONSIDER:
        return "Review alongside your other candidates before committing time."
    if recommendation is Recommendation.LOW_PRIORITY:
        return "Revisit only if stronger candidates do not materialise."
    return "No action recommended."


def weights_for(profile: ObjectiveProfile, override: Mapping[str, Any] | None = None) -> Weights:
    """Resolve the weight vector for a goal.

    The objective selects the default vector; a goal's ``weights_override``
    replaces the entries it names. An override produces a distinct
    ``weights_version`` so two scores computed under different weights can never
    be mistaken for each other.
    """
    base = WEIGHT_PROFILES[profile]
    if not override:
        return base
    return base.with_override(override, version=f"{profile.value}.v1+override")
