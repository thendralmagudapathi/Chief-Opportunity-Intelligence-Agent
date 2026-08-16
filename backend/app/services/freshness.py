"""Freshness and expiry.

A stale opportunity is worse than no opportunity: recommending a role that
closed last month costs the user time and costs the system trust. Freshness is
therefore computed explicitly rather than inferred from ``created_at`` at read
time, stored on the row, and used to exclude stale candidates from ranking.

Two separate questions are answered here. *Has it expired* is a fact derived from
the deadline. *How fresh is what we know* is a decay curve over the time since we
last verified the posting, because a listing we last read three months ago may
well have changed without telling us.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.models.enums import OpportunityCategory

#: How long after discovery an opportunity with no stated deadline is presumed
#: closed. Categories differ: job postings go stale in weeks, a fellowship round
#: runs for months.
DEFAULT_TTL_DAYS: dict[OpportunityCategory, int] = {
    OpportunityCategory.JOB: 60,
    OpportunityCategory.FREELANCE: 30,
    OpportunityCategory.CONSULTING: 45,
    OpportunityCategory.CLIENT: 45,
    OpportunityCategory.STARTUP: 90,
    OpportunityCategory.GRANT: 180,
    OpportunityCategory.FELLOWSHIP: 180,
    OpportunityCategory.SCHOLARSHIP: 180,
    OpportunityCategory.ACCELERATOR: 120,
    OpportunityCategory.INCUBATOR: 120,
    OpportunityCategory.COMPETITION: 90,
    OpportunityCategory.CONFERENCE: 120,
    OpportunityCategory.SPEAKING: 90,
    OpportunityCategory.RESEARCH: 120,
    OpportunityCategory.PARTNERSHIP: 120,
    OpportunityCategory.BUSINESS: 90,
    OpportunityCategory.OPEN_SOURCE: 180,
    OpportunityCategory.OTHER: 90,
}

FALLBACK_TTL_DAYS = 90

#: Time for confidence in unverified information to halve.
VERIFICATION_HALF_LIFE_DAYS = 21.0

#: Below this, a row is treated as stale and kept out of recommendations.
STALE_THRESHOLD = 0.25


@dataclass(frozen=True, slots=True)
class FreshnessAssessment:
    score: float
    expires_at: datetime | None
    is_expired: bool
    #: Days until expiry; negative once past, ``None`` when nothing is known.
    days_remaining: int | None


def derive_expires_at(
    *,
    category: OpportunityCategory,
    deadline: datetime | None = None,
    posted_at: datetime | None = None,
    discovered_at: datetime | None = None,
    explicit: datetime | None = None,
) -> datetime | None:
    """Work out when an opportunity should stop being offered.

    A stated deadline wins. Otherwise the category's typical lifetime is applied
    to the posting date, which is a presumption rather than a fact — hence it is
    only ever used to stop recommending something, never to claim a deadline the
    source did not give.
    """
    if explicit is not None:
        return _as_utc(explicit)
    if deadline is not None:
        return _as_utc(deadline)
    anchor = posted_at or discovered_at
    if anchor is None:
        return None
    ttl = DEFAULT_TTL_DAYS.get(category, FALLBACK_TTL_DAYS)
    return _as_utc(anchor) + timedelta(days=ttl)


def assess(
    *,
    now: datetime,
    category: OpportunityCategory,
    deadline: datetime | None = None,
    posted_at: datetime | None = None,
    discovered_at: datetime | None = None,
    last_verified_at: datetime | None = None,
    expires_at: datetime | None = None,
) -> FreshnessAssessment:
    """Score how much the stored information can still be trusted.

    The clock is passed in rather than read, so the same inputs always produce
    the same assessment and tests need no patching.
    """
    moment = _as_utc(now)
    resolved_expiry = derive_expires_at(
        category=category,
        deadline=deadline,
        posted_at=posted_at,
        discovered_at=discovered_at,
        explicit=expires_at,
    )

    days_remaining: int | None = None
    is_expired = False
    if resolved_expiry is not None:
        delta = resolved_expiry - moment
        days_remaining = delta.days if delta.total_seconds() >= 0 else -((-delta).days + 1)
        is_expired = moment > resolved_expiry

    if is_expired:
        return FreshnessAssessment(0.0, resolved_expiry, True, days_remaining)

    anchor = last_verified_at or discovered_at or posted_at
    if anchor is None:
        # Nothing to date the information by. Half is the honest answer: not
        # trusted, not discarded.
        decay = 0.5
    else:
        age_days = max((moment - _as_utc(anchor)).total_seconds() / 86400.0, 0.0)
        decay = 0.5 ** (age_days / VERIFICATION_HALF_LIFE_DAYS)

    # An imminent deadline does not make information stale, but it does reduce
    # how useful the row is, so it damps the score rather than replacing it.
    if days_remaining is not None and days_remaining <= 7:
        decay *= 0.5 + (max(days_remaining, 0) / 14.0)

    return FreshnessAssessment(
        score=round(min(max(decay, 0.0), 1.0), 4),
        expires_at=resolved_expiry,
        is_expired=False,
        days_remaining=days_remaining,
    )


def is_stale(score: float | None) -> bool:
    """Whether a freshness score is too low to recommend on."""
    return score is not None and score < STALE_THRESHOLD


def _as_utc(moment: datetime) -> datetime:
    return moment.astimezone(UTC) if moment.tzinfo else moment.replace(tzinfo=UTC)
