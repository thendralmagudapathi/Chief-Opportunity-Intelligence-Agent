"""Deterministic factor derivation.

The scoring engine consumes dimensions in [0, 1]; this is where the ones that can
be computed from stored data come from. Phase 2 derives exactly three — skill
fit, compensation value, and time sensitivity — plus a work-authorisation
eligibility check.

Everything else is left unknown, deliberately. Probability of success, strategic
value and long-term value require research and judgement that no arithmetic over
a job posting can supply, and the engine already handles unknowns properly: they
are excluded from the weighted sum and reflected in ``confidence``. Guessing them
from proxies would produce a score that looks better informed than it is, which
is the failure mode this whole design exists to avoid.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.models.goal import Goal
from app.models.opportunity import Opportunity
from app.models.user import UserProfile
from app.services.normalization import normalize_text
from app.services.scoring import Dimension

#: Below this many days a deadline is treated as maximally urgent.
URGENT_DAYS = 7
#: Beyond this horizon a deadline exerts no time pressure at all.
RELAXED_DAYS = 120

#: A posting listing more required skills than this is a wish list; matching
#: every entry is not a realistic bar, so fit saturates before full coverage.
FIT_SATURATION = 0.85


@dataclass(frozen=True, slots=True)
class DerivedFactors:
    values: Mapping[Dimension, Decimal | None]
    eligible: bool | None
    days_to_deadline: int | None
    #: Why each derived dimension has the value it does, for the audit trail.
    rationale: dict[str, str]


def derive(
    opportunity: Opportunity,
    *,
    profile: UserProfile | None = None,
    goal: Goal | None = None,
    now: datetime | None = None,
) -> DerivedFactors:
    """Compute what can be computed, and be explicit about the rest."""
    moment = (now or datetime.now(UTC)).astimezone(UTC)
    values: dict[Dimension, Decimal | None] = dict.fromkeys(Dimension, None)
    rationale: dict[str, str] = {}

    days_to_deadline = _days_until(opportunity.deadline, moment)
    if days_to_deadline is not None:
        values[Dimension.TIME_SENSITIVITY] = _time_sensitivity(days_to_deadline)
        rationale[Dimension.TIME_SENSITIVITY.value] = (
            f"{days_to_deadline} days to the stated deadline"
        )
    else:
        rationale[Dimension.TIME_SENSITIVITY.value] = "no deadline is known"

    fit = _skill_fit(opportunity, profile)
    if fit is not None:
        values[Dimension.FIT] = fit.value
        rationale[Dimension.FIT.value] = fit.reason
    else:
        rationale[Dimension.FIT.value] = "no skills recorded on the profile or the posting"

    value = _compensation_value(opportunity, profile)
    if value is not None:
        values[Dimension.VALUE] = value.value
        rationale[Dimension.VALUE.value] = value.reason
    else:
        rationale[Dimension.VALUE.value] = "no comparable compensation information"

    eligible, eligibility_reason = _work_authorization(opportunity, profile)
    if eligibility_reason:
        rationale["eligibility"] = eligibility_reason

    for dimension in (
        Dimension.PROBABILITY,
        Dimension.STRATEGIC,
        Dimension.LEARNING,
        Dimension.NETWORK,
        Dimension.LONG_TERM,
        Dimension.EFFORT,
        Dimension.RISK,
    ):
        rationale.setdefault(dimension.value, "requires research; not derivable from the posting")

    return DerivedFactors(
        values=values,
        eligible=eligible,
        days_to_deadline=days_to_deadline,
        rationale=rationale,
    )


@dataclass(frozen=True, slots=True)
class _Derived:
    value: Decimal
    reason: str


def _days_until(deadline: datetime | None, now: datetime) -> int | None:
    if deadline is None:
        return None
    moment = deadline.astimezone(UTC) if deadline.tzinfo else deadline.replace(tzinfo=UTC)
    delta = moment - now
    return delta.days if delta.total_seconds() >= 0 else -((-delta).days + 1)


def _time_sensitivity(days: int) -> Decimal:
    """Urgency as a function of days remaining, linear between the two bounds."""
    if days <= URGENT_DAYS:
        return Decimal("1.0")
    if days >= RELAXED_DAYS:
        return Decimal("0.0")
    span = Decimal(RELAXED_DAYS - URGENT_DAYS)
    return ((Decimal(RELAXED_DAYS - days)) / span).quantize(Decimal("0.0001"))


def _skill_names(entries: Sequence[Any] | None) -> set[str]:
    names: set[str] = set()
    for entry in entries or ():
        if isinstance(entry, str):
            candidate = entry
        elif isinstance(entry, Mapping):
            candidate = str(entry.get("name") or entry.get("skill") or "")
        else:
            continue
        normalized = normalize_text(candidate)
        if normalized:
            names.add(normalized.casefold())
    return names


def _skill_fit(opportunity: Opportunity, profile: UserProfile | None) -> _Derived | None:
    """Coverage of the posting's required skills by the profile's skills.

    Preferred skills count for less than required ones: missing a nice-to-have is
    not the same as missing a prerequisite.
    """
    if profile is None:
        return None
    held = _skill_names(profile.skills)
    required = _skill_names(opportunity.required_skills)
    preferred = _skill_names(opportunity.preferred_skills)
    if not held or not (required or preferred):
        return None

    required_hit = len(required & held)
    preferred_hit = len(preferred & held)
    weighted_total = len(required) + Decimal("0.4") * len(preferred)
    if weighted_total == 0:
        return None
    weighted_hit = required_hit + Decimal("0.4") * preferred_hit

    coverage = Decimal(weighted_hit) / Decimal(weighted_total)
    scaled = min(coverage / Decimal(str(FIT_SATURATION)), Decimal("1"))
    return _Derived(
        value=scaled.quantize(Decimal("0.0001")),
        reason=(
            f"{required_hit} of {len(required)} required and "
            f"{preferred_hit} of {len(preferred)} preferred skills matched"
        ),
    )


def _compensation_value(opportunity: Opportunity, profile: UserProfile | None) -> _Derived | None:
    """Compensation relative to what the user said they want.

    Only comparable when both sides are stated in the same currency; converting
    currencies would need a rate the system does not have, and a wrong conversion
    is worse than an unknown.
    """
    if profile is None:
        return None
    target_min = profile.salary_expectation_min
    target_max = profile.salary_expectation_max
    if target_min is None and target_max is None:
        return None

    offered = opportunity.compensation_max or opportunity.compensation_min
    if offered is None:
        return None
    if (
        opportunity.compensation_currency
        and profile.salary_currency
        and opportunity.compensation_currency != profile.salary_currency
    ):
        return None

    floor = target_min or target_max
    ceiling = target_max or target_min
    if floor is None or ceiling is None or floor <= 0:
        return None

    if offered >= ceiling:
        return _Derived(Decimal("1.0"), f"offers {offered}, at or above the expectation {ceiling}")
    if offered <= floor / 2:
        return _Derived(Decimal("0.0"), f"offers {offered}, far below the expectation {floor}")

    span = ceiling - (floor / 2)
    if span <= 0:
        return _Derived(Decimal("0.5"), "expectation range is degenerate")
    ratio = (offered - floor / 2) / span
    return _Derived(
        max(min(ratio, Decimal("1")), Decimal("0")).quantize(Decimal("0.0001")),
        f"offers {offered} against an expectation of {floor} to {ceiling}",
    )


def _work_authorization(
    opportunity: Opportunity, profile: UserProfile | None
) -> tuple[bool | None, str | None]:
    """Check the one eligibility rule that is a hard fact rather than a judgement.

    Returns ``None`` when it cannot be decided. An unstated requirement is not
    evidence of eligibility, and declaring someone ineligible on a guess would
    hide opportunities from them.
    """
    if profile is None or not opportunity.location_country:
        return None, None
    country = opportunity.location_country.upper()

    authorizations = profile.work_authorization or ()
    for entry in authorizations:
        if not isinstance(entry, Mapping):
            continue
        if str(entry.get("country", "")).upper() != country:
            continue
        status = str(entry.get("status", "unknown")).lower()
        if status in ("citizen", "permanent_resident", "work_visa"):
            return True, f"authorised to work in {country} ({status})"
        if status == "none":
            return False, f"not authorised to work in {country}"
        return None, f"work authorisation for {country} is {status}"
    return None, f"no work authorisation recorded for {country}"
