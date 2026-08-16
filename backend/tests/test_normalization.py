"""Normalisation: URLs, dates, money, text. Pure functions, no I/O."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.models.enums import CompensationPeriod
from app.services.normalization import (
    DateOutcome,
    canonicalize_url,
    content_fingerprint,
    normalize_compensation,
    normalize_country,
    normalize_currency,
    normalize_period,
    normalize_text,
    parse_deadline,
)


def test_tracking_parameters_and_www_do_not_change_identity() -> None:
    left = canonicalize_url(
        "HTTPS://WWW.Example.COM:443/jobs/ml-engineer/?utm_source=twitter&utm_campaign=x&q=1"
    )
    right = canonicalize_url("https://example.com/jobs/ml-engineer?q=1")
    assert left == right == "https://example.com/jobs/ml-engineer?q=1"


def test_parameter_order_is_sorted_and_fragments_are_dropped() -> None:
    left = canonicalize_url("https://example.com/a?b=2&a=1#section")
    right = canonicalize_url("https://example.com/a?a=1&b=2")
    assert left == right


def test_scheme_less_urls_are_assumed_https() -> None:
    assert canonicalize_url("example.com/role") == "https://example.com/role"


def test_unusable_urls_are_rejected() -> None:
    assert canonicalize_url("mailto:jobs@example.com") is None
    assert canonicalize_url("") is None
    assert canonicalize_url("   ") is None


def test_text_collapses_unicode_noise() -> None:
    assert normalize_text("  Senior\u00a0Engineer\u200b  ") == "Senior Engineer"
    assert normalize_text("ﬁt") == "fit"  # NFKC ligature
    assert normalize_text("   ") is None


def test_iso_and_named_dates_parse() -> None:
    iso = parse_deadline("2026-09-30")
    assert iso.outcome is DateOutcome.PARSED
    assert iso.value == datetime(2026, 9, 30, 23, 59, 59, tzinfo=UTC)

    named = parse_deadline("30 September 2026")
    assert named.value is not None and named.value.date() == iso.value.date()

    us = parse_deadline("September 30, 2026")
    assert us.value is not None and us.value.date() == iso.value.date()


def test_ambiguous_numeric_dates_are_not_guessed() -> None:
    result = parse_deadline("03/04/2026")
    assert result.outcome is DateOutcome.AMBIGUOUS
    assert result.value is None

    day_first = parse_deadline("03/04/2026", day_first=True)
    assert day_first.value is not None and day_first.value.day == 3 and day_first.value.month == 4

    month_first = parse_deadline("03/04/2026", day_first=False)
    assert month_first.value is not None and month_first.value.day == 4


def test_unambiguous_numeric_dates_parse_without_a_locale() -> None:
    result = parse_deadline("23/04/2026")
    assert result.outcome is DateOutcome.PARSED
    assert result.value is not None and result.value.day == 23 and result.value.month == 4


def test_rolling_deadlines_are_a_known_unknown() -> None:
    result = parse_deadline("Applications are accepted year-round")
    assert result.outcome is DateOutcome.ROLLING
    assert result.value is None


def test_compensation_normalises_and_orders_a_reversed_range() -> None:
    result = normalize_compensation("£90,000", "£70,000", "£", "per annum")
    assert result.minimum == Decimal("70000")
    assert result.maximum == Decimal("90000")
    assert result.currency == "GBP"
    assert result.period is CompensationPeriod.YEAR


def test_currency_and_period_helpers() -> None:
    assert normalize_currency("eur") == "EUR"
    assert normalize_currency("$") == "USD"
    assert normalize_currency("dollars") is None
    assert normalize_period("hourly") is CompensationPeriod.HOUR
    assert normalize_period("pa") is CompensationPeriod.YEAR
    assert normalize_country("de") == "DE"
    assert normalize_country("Germany") is None


def test_content_fingerprint_ignores_compensation_and_location() -> None:
    left = content_fingerprint(
        title="Research Scientist", organization="Lab", description="Build models."
    )
    right = content_fingerprint(
        title="  research scientist ", organization="LAB", description="Build models."
    )
    assert left == right
    assert len(left) == 64
