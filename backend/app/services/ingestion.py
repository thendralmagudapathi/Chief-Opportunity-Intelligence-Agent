"""Ingestion: raw source payload in, canonical opportunity row out.

This is the deterministic half of discovery. A source adapter (Phase 4) or a seed
script hands over a :class:`RawOpportunity`; everything from there — normalising
the fields, deciding whether it is something we already have, dating it, and
recording what happened — is rule-based and reproducible.

The pipeline never invents a value. A deadline that cannot be parsed is left
null, and the failure is recorded on the row's event log rather than replaced
with a plausible date.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.enums import (
    OpportunityCategory,
    OpportunityEventType,
    OpportunityStatus,
    RemoteStatus,
)
from app.models.opportunity import Opportunity, OpportunityEvent
from app.services import freshness, lifecycle
from app.services.dedup import Candidate, DeduplicationService, DuplicateMatch, MatchMethod
from app.services.normalization import (
    DateOutcome,
    canonicalize_url,
    content_fingerprint,
    normalize_compensation,
    normalize_country,
    normalize_text,
    parse_deadline,
)

logger = get_logger(__name__)


class IngestionOutcome(StrEnum):
    CREATED = "created"
    #: Matched an existing row exactly; that row was refreshed instead.
    MERGED = "merged"
    #: Probably a duplicate. Stored, linked to the original, kept out of ranking.
    FLAGGED_DUPLICATE = "flagged_duplicate"
    #: Rejected before insert; see ``reason``.
    REJECTED = "rejected"


@dataclass(slots=True)
class RawOpportunity:
    """What a source yields, before any interpretation."""

    title: str
    source_url: str
    category: OpportunityCategory = OpportunityCategory.OTHER
    external_id: str | None = None
    organization_name: str | None = None
    organization_domain: str | None = None
    description: str | None = None
    summary: str | None = None
    language: str | None = None
    location_country: str | None = None
    location_city: str | None = None
    remote_status: RemoteStatus | str | None = None
    compensation_min: object = None
    compensation_max: object = None
    compensation_currency: str | None = None
    compensation_period: str | None = None
    requirements: list[Any] = field(default_factory=list)
    eligibility: dict[str, Any] = field(default_factory=dict)
    required_skills: list[Any] = field(default_factory=list)
    preferred_skills: list[Any] = field(default_factory=list)
    posted_at: datetime | str | None = None
    deadline: datetime | str | None = None
    raw: dict[str, Any] | None = None
    #: Set when the source's date convention is known, so that an otherwise
    #: ambiguous numeric date can be resolved.
    day_first: bool | None = None


@dataclass(frozen=True, slots=True)
class IngestionResult:
    outcome: IngestionOutcome
    opportunity: Opportunity | None = None
    duplicate_of: uuid.UUID | None = None
    match: DuplicateMatch | None = None
    reason: str | None = None
    #: Field-level notes, e.g. a deadline that could not be parsed.
    notes: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class IngestionReport:
    created: int = 0
    merged: int = 0
    flagged: int = 0
    rejected: int = 0

    @property
    def total(self) -> int:
        return self.created + self.merged + self.flagged + self.rejected


class IngestionService:
    """Turns raw source payloads into canonical rows. Owns its transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.dedup = DeduplicationService(session)

    async def ingest(
        self,
        raw: RawOpportunity,
        *,
        source_id: uuid.UUID | None = None,
        now: datetime | None = None,
    ) -> IngestionResult:
        moment = (now or datetime.now(UTC)).astimezone(UTC)
        notes: dict[str, str] = {}

        title = normalize_text(raw.title)
        if not title:
            return IngestionResult(IngestionOutcome.REJECTED, reason="title is empty")

        canonical_url = canonicalize_url(raw.source_url)
        if canonical_url is None:
            return IngestionResult(
                IngestionOutcome.REJECTED, reason=f"unusable source url: {raw.source_url!r}"
            )

        organization = normalize_text(raw.organization_name)
        description = normalize_text(raw.description)
        fingerprint = content_fingerprint(
            title=title, organization=organization, description=description
        )

        candidate = Candidate(
            title=title,
            canonical_url=canonical_url,
            source_url=canonical_url,
            content_hash=fingerprint,
            organization_name=organization,
            organization_domain=normalize_text(raw.organization_domain),
        )
        match = await self.dedup.find_duplicate(candidate)

        if match is not None and match.method in (
            MatchMethod.CANONICAL_URL,
            MatchMethod.CONTENT_HASH,
        ):
            existing = await self.session.get(Opportunity, match.opportunity_id)
            if existing is not None:
                await self._revalidate(existing, moment)
                return IngestionResult(
                    IngestionOutcome.MERGED,
                    opportunity=existing,
                    duplicate_of=existing.id,
                    match=match,
                )

        deadline_parse = parse_deadline(raw.deadline, day_first=raw.day_first)
        if deadline_parse.outcome in (DateOutcome.AMBIGUOUS, DateOutcome.UNPARSED):
            notes["deadline"] = f"{deadline_parse.outcome.value}: {raw.deadline!r}"
        posted_parse = parse_deadline(raw.posted_at, day_first=raw.day_first)

        compensation = normalize_compensation(
            raw.compensation_min,
            raw.compensation_max,
            raw.compensation_currency,
            raw.compensation_period,
        )

        assessment = freshness.assess(
            now=moment,
            category=raw.category,
            deadline=deadline_parse.value,
            posted_at=posted_parse.value,
            discovered_at=moment,
        )

        status = (
            OpportunityStatus.EXPIRED if assessment.is_expired else OpportunityStatus.DISCOVERED
        )
        is_flagged = match is not None

        opportunity = Opportunity(
            source_id=source_id,
            external_id=raw.external_id,
            title=title,
            category=raw.category,
            organization_name=organization,
            organization_domain=normalize_text(raw.organization_domain),
            description=description,
            summary=normalize_text(raw.summary),
            language=normalize_text(raw.language),
            location_country=normalize_country(raw.location_country),
            location_city=normalize_text(raw.location_city),
            remote_status=_remote_status(raw.remote_status),
            compensation_min=compensation.minimum,
            compensation_max=compensation.maximum,
            compensation_currency=compensation.currency,
            compensation_period=compensation.period,
            requirements=list(raw.requirements),
            eligibility=dict(raw.eligibility),
            required_skills=list(raw.required_skills),
            preferred_skills=list(raw.preferred_skills),
            posted_at=posted_parse.value,
            deadline=deadline_parse.value,
            discovered_at=moment,
            last_verified_at=moment,
            expires_at=assessment.expires_at,
            freshness_score=assessment.score,
            source_url=canonical_url,
            canonical_url=canonical_url,
            content_hash=fingerprint,
            status=OpportunityStatus.DUPLICATE if is_flagged else status,
            duplicate_of_id=match.opportunity_id if match else None,
            raw=raw.raw,
        )
        self.session.add(opportunity)
        await self.session.flush()

        self._record(
            opportunity,
            OpportunityEventType.DISCOVERED,
            {"source_url": canonical_url, **({"notes": notes} if notes else {})},
        )
        if is_flagged and match is not None:
            self._record(
                opportunity,
                OpportunityEventType.DEDUPLICATED,
                {
                    "duplicate_of": str(match.opportunity_id),
                    "method": match.method.value,
                    "similarity": match.similarity,
                },
            )
        elif assessment.is_expired:
            self._record(
                opportunity,
                OpportunityEventType.EXPIRED,
                {
                    "expires_at": assessment.expires_at.isoformat()
                    if assessment.expires_at
                    else None
                },
            )

        return IngestionResult(
            outcome=IngestionOutcome.FLAGGED_DUPLICATE if is_flagged else IngestionOutcome.CREATED,
            opportunity=opportunity,
            duplicate_of=match.opportunity_id if match else None,
            match=match,
            notes=notes,
        )

    async def ingest_many(
        self,
        items: Iterable[RawOpportunity],
        *,
        source_id: uuid.UUID | None = None,
        now: datetime | None = None,
    ) -> tuple[IngestionReport, Sequence[IngestionResult]]:
        created = merged = flagged = rejected = 0
        results: list[IngestionResult] = []
        for raw in items:
            result = await self.ingest(raw, source_id=source_id, now=now)
            results.append(result)
            match result.outcome:
                case IngestionOutcome.CREATED:
                    created += 1
                case IngestionOutcome.MERGED:
                    merged += 1
                case IngestionOutcome.FLAGGED_DUPLICATE:
                    flagged += 1
                case IngestionOutcome.REJECTED:
                    rejected += 1
                    logger.info("ingestion_rejected", reason=result.reason)
        return IngestionReport(created, merged, flagged, rejected), results

    async def refresh(
        self, opportunity: Opportunity, *, now: datetime | None = None
    ) -> freshness.FreshnessAssessment:
        """Recompute freshness and apply an expiry transition if it is due.

        Re-fetching the source is the discovery pipeline's job; this recomputes
        from what is already stored, which is what keeps expired rows out of
        recommendations between crawls.
        """
        moment = (now or datetime.now(UTC)).astimezone(UTC)
        assessment = freshness.assess(
            now=moment,
            category=opportunity.category,
            deadline=opportunity.deadline,
            posted_at=opportunity.posted_at,
            discovered_at=opportunity.discovered_at,
            last_verified_at=opportunity.last_verified_at,
            expires_at=opportunity.expires_at,
        )
        opportunity.freshness_score = assessment.score
        opportunity.expires_at = assessment.expires_at

        if assessment.is_expired and opportunity.status not in lifecycle.INACTIVE:
            event = lifecycle.transition(
                opportunity.status, OpportunityStatus.EXPIRED, reason="past expiry"
            )
            if event is not None:
                opportunity.status = OpportunityStatus.EXPIRED
                self._record(opportunity, event.event_type, event.payload)
        else:
            self._record(
                opportunity,
                OpportunityEventType.REVALIDATED,
                {"freshness_score": assessment.score},
            )
        return assessment

    async def set_status(
        self,
        opportunity: Opportunity,
        target: OpportunityStatus,
        *,
        reason: str | None = None,
    ) -> bool:
        """Move an opportunity through the lifecycle, recording the event."""
        event = lifecycle.transition(opportunity.status, target, reason=reason)
        if event is None:
            return False
        opportunity.status = target
        self._record(opportunity, event.event_type, event.payload)
        return True

    async def _revalidate(self, existing: Opportunity, moment: datetime) -> None:
        existing.last_verified_at = moment
        assessment = freshness.assess(
            now=moment,
            category=existing.category,
            deadline=existing.deadline,
            posted_at=existing.posted_at,
            discovered_at=existing.discovered_at,
            last_verified_at=moment,
            expires_at=existing.expires_at,
        )
        existing.freshness_score = assessment.score
        self._record(
            existing,
            OpportunityEventType.REVALIDATED,
            {"seen_again_at": moment.isoformat(), "freshness_score": assessment.score},
        )

    def _record(
        self, opportunity: Opportunity, event_type: OpportunityEventType, payload: dict[str, Any]
    ) -> None:
        self.session.add(
            OpportunityEvent(opportunity_id=opportunity.id, event_type=event_type, payload=payload)
        )


def _remote_status(value: RemoteStatus | str | None) -> RemoteStatus:
    if isinstance(value, RemoteStatus):
        return value
    if not value:
        return RemoteStatus.UNKNOWN
    try:
        return RemoteStatus(str(value).strip().lower())
    except ValueError:
        return RemoteStatus.UNKNOWN
