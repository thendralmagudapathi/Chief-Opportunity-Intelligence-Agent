"""Freshness decay and expiry derivation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.models.enums import OpportunityCategory
from app.services.freshness import STALE_THRESHOLD, assess, derive_expires_at, is_stale

NOW = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)


def test_a_stated_deadline_wins_over_category_ttl() -> None:
    deadline = datetime(2026, 9, 30, tzinfo=UTC)
    expires = derive_expires_at(
        category=OpportunityCategory.JOB,
        deadline=deadline,
        posted_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert expires == deadline


def test_job_without_deadline_expires_after_the_category_ttl() -> None:
    posted = datetime(2026, 6, 1, tzinfo=UTC)
    expires = derive_expires_at(category=OpportunityCategory.JOB, posted_at=posted)
    assert expires == posted + timedelta(days=60)


def test_past_deadline_is_expired_with_zero_freshness() -> None:
    result = assess(
        now=NOW,
        category=OpportunityCategory.GRANT,
        deadline=NOW - timedelta(days=1),
    )
    assert result.is_expired is True
    assert result.score == 0.0
    assert result.days_remaining is not None and result.days_remaining < 0


def test_unverified_information_decays() -> None:
    fresh = assess(
        now=NOW,
        category=OpportunityCategory.JOB,
        deadline=NOW + timedelta(days=40),
        last_verified_at=NOW,
    )
    aged = assess(
        now=NOW,
        category=OpportunityCategory.JOB,
        deadline=NOW + timedelta(days=40),
        last_verified_at=NOW - timedelta(days=21),
    )
    assert fresh.score == 1.0
    assert 0.45 < aged.score < 0.55  # one half-life


def test_stale_threshold() -> None:
    assert is_stale(0.1) is True
    assert is_stale(STALE_THRESHOLD) is False
    assert is_stale(None) is False
