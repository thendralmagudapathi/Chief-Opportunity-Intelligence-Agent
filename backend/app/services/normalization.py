"""Normalisation of raw opportunity fields.

Everything here is a pure function. Sources disagree about how to write a URL, a
salary and a date, and comparing raw values produces both false duplicates and
missed ones, so values are reduced to a canonical form once, at ingestion, and
stored that way.

The date parser is deliberately conservative. ``03/04/2026`` is the third of
April in most of the world and the fourth of March in the United States, and no
amount of cleverness recovers the intent from the string alone, so an ambiguous
date is reported as unparsed rather than guessed. An opportunity with an unknown
deadline is a known unknown; one with a confidently wrong deadline is a missed
opportunity or a wasted application.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.models.enums import CompensationPeriod

# Parameters that identify a marketing campaign rather than a document. Two URLs
# differing only by these point at the same posting.
_TRACKING_PARAMS = frozenset(
    {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "utm_id",
        "gclid",
        "fbclid",
        "msclkid",
        "mc_cid",
        "mc_eid",
        "igshid",
        "ref",
        "referrer",
        "source",
        "src",
        "trk",
        "trackingid",
        "_hsenc",
        "_hsmi",
    }
)

_DEFAULT_PORTS = {"http": 80, "https": 443}

# Unicode categories that carry no meaning in a title or description but do
# break equality: control characters, zero-width joiners, soft hyphens.
_INVISIBLE = re.compile(r"[\u00ad\u200b-\u200f\u2028\u2029\ufeff]")
_WHITESPACE = re.compile(r"\s+")

_MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}  # fmt: skip

_ORDINAL = re.compile(r"(\d{1,2})(st|nd|rd|th)\b", re.IGNORECASE)
_ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_DAY_MONTH_YEAR = re.compile(r"\b(\d{1,2})\s+([a-z]+)\.?,?\s+(\d{4})\b", re.IGNORECASE)
_MONTH_DAY_YEAR = re.compile(r"\b([a-z]+)\.?\s+(\d{1,2}),?\s+(\d{4})\b", re.IGNORECASE)
_NUMERIC_DATE = re.compile(r"\b(\d{1,2})[/.](\d{1,2})[/.](\d{4})\b")

# Phrases meaning "there is no fixed date", which is different from "we could
# not read the date".
_ROLLING = re.compile(
    r"\b(rolling|ongoing|continuous|open until filled|until filled|no deadline|"
    r"applications? are accepted year[- ]round|anytime)\b",
    re.IGNORECASE,
)

_CURRENCY_CODE = re.compile(r"^[A-Za-z]{3}$")
_CURRENCY_SYMBOLS = {
    "$": "USD",
    "£": "GBP",
    "€": "EUR",
    "¥": "JPY",
    "₹": "INR",
    "₽": "RUB",
    "₩": "KRW",
    "R$": "BRL",
    "C$": "CAD",
    "A$": "AUD",
}

_PERIOD_WORDS = {
    "hour": CompensationPeriod.HOUR,
    "hourly": CompensationPeriod.HOUR,
    "hr": CompensationPeriod.HOUR,
    "day": CompensationPeriod.DAY,
    "daily": CompensationPeriod.DAY,
    "diem": CompensationPeriod.DAY,
    "month": CompensationPeriod.MONTH,
    "monthly": CompensationPeriod.MONTH,
    "mo": CompensationPeriod.MONTH,
    "year": CompensationPeriod.YEAR,
    "yearly": CompensationPeriod.YEAR,
    "annual": CompensationPeriod.YEAR,
    "annually": CompensationPeriod.YEAR,
    "annum": CompensationPeriod.YEAR,
    "pa": CompensationPeriod.YEAR,
    "project": CompensationPeriod.PROJECT,
    "total": CompensationPeriod.TOTAL,
    "one-off": CompensationPeriod.TOTAL,
    "lump": CompensationPeriod.TOTAL,
}


class DateOutcome(StrEnum):
    """Why a date string did or did not become a date."""

    PARSED = "parsed"
    #: A real date exists but the string does not determine which one.
    AMBIGUOUS = "ambiguous"
    #: The source states there is no fixed deadline.
    ROLLING = "rolling"
    #: Nothing date-shaped was found.
    UNPARSED = "unparsed"
    EMPTY = "empty"


@dataclass(frozen=True, slots=True)
class ParsedDate:
    value: datetime | None
    outcome: DateOutcome

    @property
    def is_known(self) -> bool:
        return self.value is not None


@dataclass(frozen=True, slots=True)
class NormalizedCompensation:
    minimum: Decimal | None = None
    maximum: Decimal | None = None
    currency: str | None = None
    period: CompensationPeriod | None = None


def normalize_text(value: str | None) -> str | None:
    """Collapse a string to a comparable form, or ``None`` if nothing remains."""
    if value is None:
        return None
    # NFKC folds presentation variants (ligatures, full-width Latin) onto the
    # characters they represent, so visually identical titles compare equal.
    text = unicodedata.normalize("NFKC", value)
    text = _INVISIBLE.sub("", text)
    text = "".join(
        ch
        for ch in text
        if ch == "\n" or ch == "\t" or not unicodedata.category(ch).startswith("C")
    )
    text = _WHITESPACE.sub(" ", text).strip()
    return text or None


def canonicalize_url(url: str | None) -> str | None:
    """Reduce a URL to the form used for identity comparison.

    Drops tracking parameters, default ports, fragments and a leading ``www.``,
    and orders the remaining query so that parameter order cannot make one
    posting look like two.
    """
    if not url or not url.strip():
        return None
    raw = url.strip()
    scheme_hint = raw.split(":", 1)[0].lower()
    if scheme_hint in {"mailto", "ftp", "file", "javascript", "data", "tel"}:
        return None
    if "://" not in raw:
        raw = f"https://{raw}"

    parts = urlsplit(raw)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None

    scheme = parts.scheme.lower()
    host = parts.hostname.lower() if parts.hostname else ""
    if host.startswith("www."):
        host = host[4:]
    if not host:
        return None

    netloc = host
    if parts.port and parts.port != _DEFAULT_PORTS.get(scheme):
        netloc = f"{host}:{parts.port}"

    query = urlencode(
        sorted(
            (k, v)
            for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if k.lower() not in _TRACKING_PARAMS
        )
    )

    path = re.sub(r"/{2,}", "/", parts.path)
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    return urlunsplit((scheme, netloc, path, query, ""))


def normalize_currency(value: str | None) -> str | None:
    """Return an upper-case ISO-4217-shaped code, resolving common symbols."""
    if not value:
        return None
    candidate = value.strip()
    if candidate in _CURRENCY_SYMBOLS:
        return _CURRENCY_SYMBOLS[candidate]
    if _CURRENCY_CODE.match(candidate):
        return candidate.upper()
    return None


def normalize_period(value: str | None) -> CompensationPeriod | None:
    """Map a free-text pay period onto the enum, or ``None`` when unclear."""
    if not value:
        return None
    token = re.sub(r"[^a-z]", "", value.strip().lower())
    if not token:
        return None
    if token in _PERIOD_WORDS:
        return _PERIOD_WORDS[token]
    # "per annum", "per year", "/yr" all reduce to a word we know.
    for word, period in _PERIOD_WORDS.items():
        if word in token:
            return period
    return None


def _to_decimal(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int | float):
        return Decimal(str(value))
    if isinstance(value, str):
        cleaned = re.sub(r"[,\s_]", "", value.strip())
        cleaned = re.sub(r"^[^\d.\-]+", "", cleaned)
        cleaned = re.sub(r"[^\d.]+$", "", cleaned)
        if not cleaned:
            return None
        try:
            return Decimal(cleaned)
        except InvalidOperation:
            return None
    return None


def normalize_compensation(
    minimum: object = None,
    maximum: object = None,
    currency: str | None = None,
    period: str | CompensationPeriod | None = None,
) -> NormalizedCompensation:
    """Coerce a compensation range into comparable numbers.

    A reversed range is a data-entry artefact rather than a meaningful signal, so
    the bounds are ordered instead of rejected.
    """
    low = _to_decimal(minimum)
    high = _to_decimal(maximum)
    if low is not None and high is not None and low > high:
        low, high = high, low
    if low is not None and low < 0:
        low = None
    if high is not None and high < 0:
        high = None

    resolved_period = period if isinstance(period, CompensationPeriod) else normalize_period(period)
    return NormalizedCompensation(
        minimum=low,
        maximum=high,
        currency=normalize_currency(currency),
        period=resolved_period,
    )


def _end_of_day(year: int, month: int, day: int) -> datetime | None:
    try:
        return datetime(year, month, day, 23, 59, 59, tzinfo=UTC)
    except ValueError:
        return None


def parse_deadline(value: str | datetime | None, *, day_first: bool | None = None) -> ParsedDate:
    """Parse a deadline without guessing.

    A date with no time component becomes the last second of that day in UTC: a
    deadline of "30 September" has not passed at nine in the morning.

    ``day_first`` resolves purely numeric dates when the source's locale is
    known. Left unset, an ambiguous ``03/04/2026`` is reported as
    :attr:`DateOutcome.AMBIGUOUS` rather than resolved arbitrarily.
    """
    if value is None:
        return ParsedDate(None, DateOutcome.EMPTY)
    if isinstance(value, datetime):
        moment = value if value.tzinfo else value.replace(tzinfo=UTC)
        return ParsedDate(moment.astimezone(UTC), DateOutcome.PARSED)

    text = normalize_text(value)
    if not text:
        return ParsedDate(None, DateOutcome.EMPTY)

    if _ROLLING.search(text):
        return ParsedDate(None, DateOutcome.ROLLING)

    # Full ISO 8601 first: it is unambiguous and carries a timezone.
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        pass
    else:
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=UTC)
        # fromisoformat treats a date-only string as midnight. A deadline of
        # "2026-09-30" has not passed at 09:00 that day.
        if (
            "T" not in text.upper()
            and " " not in text
            and (parsed := _end_of_day(moment.year, moment.month, moment.day))
        ):
            return ParsedDate(parsed, DateOutcome.PARSED)
        return ParsedDate(moment.astimezone(UTC), DateOutcome.PARSED)

    if match := _ISO_DATE.search(text):
        year, month, day = (int(g) for g in match.groups())
        if parsed := _end_of_day(year, month, day):
            return ParsedDate(parsed, DateOutcome.PARSED)

    stripped = _ORDINAL.sub(r"\1", text)

    if match := _DAY_MONTH_YEAR.search(stripped):
        day_s, month_s, year_s = match.groups()
        named = _MONTHS.get(month_s.lower())
        if named is not None and (parsed := _end_of_day(int(year_s), named, int(day_s))):
            return ParsedDate(parsed, DateOutcome.PARSED)

    if match := _MONTH_DAY_YEAR.search(stripped):
        month_s, day_s, year_s = match.groups()
        named = _MONTHS.get(month_s.lower())
        if named is not None and (parsed := _end_of_day(int(year_s), named, int(day_s))):
            return ParsedDate(parsed, DateOutcome.PARSED)

    if match := _NUMERIC_DATE.search(stripped):
        first, second, year_s = (int(g) for g in match.groups())
        if first > 12 and second <= 12:
            resolved: tuple[int, int] | None = (second, first)
        elif second > 12 and first <= 12:
            resolved = (first, second)
        elif day_first is None:
            return ParsedDate(None, DateOutcome.AMBIGUOUS)
        else:
            resolved = (second, first) if day_first else (first, second)
        if resolved is not None:
            month, day = resolved
            if parsed := _end_of_day(year_s, month, day):
                return ParsedDate(parsed, DateOutcome.PARSED)

    return ParsedDate(None, DateOutcome.UNPARSED)


def normalize_country(value: str | None) -> str | None:
    """Return a two-letter upper-case country code, or ``None``."""
    if not value:
        return None
    token = value.strip().upper()
    return token if len(token) == 2 and token.isalpha() else None


def content_fingerprint(
    *, title: str | None, organization: str | None, description: str | None
) -> str:
    """A stable hash of the fields that make a posting the posting it is.

    Location and compensation are excluded on purpose: the same role reposted
    with a corrected salary is the same opportunity, and treating it as new would
    resurface something the user already dismissed.
    """
    parts = [
        (normalize_text(title) or "").casefold(),
        (normalize_text(organization) or "").casefold(),
        (normalize_text(description) or "").casefold(),
    ]
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()
