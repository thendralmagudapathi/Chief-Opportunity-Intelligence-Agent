"""Duplicate detection.

The same opportunity reaches us repeatedly: reposted by the employer, syndicated
to three aggregators, and re-crawled next week with a tidied-up description. Each
copy that survives ingestion is a row the user has to dismiss again, so detection
runs before insert rather than as a later clean-up.

Four probes, cheapest and most certain first, stopping at the first hit:

1. canonical URL — the same document at the same address
2. content hash — the same text, wherever it was found
3. organisation and title similarity — the same role, re-worded
4. embedding proximity — the same role, differently worded (Phase 3)

The similarity comparison is computed in Python rather than delegated to
``pg_trgm`` so that the verdict is identical on PostgreSQL and on SQLite. The
trigram index still earns its keep: on PostgreSQL it narrows the candidate set
before those comparisons happen.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import OpportunityStatus
from app.models.opportunity import Opportunity
from app.services.normalization import normalize_text

#: Jaccard similarity over character trigrams above which two titles from the
#: same organisation are considered the same posting. Set from the labelled
#: duplicate set in ``tests/test_dedup.py``: high enough that "Senior Engineer"
#: and "Junior Engineer" stay distinct, low enough to absorb re-wording.
TITLE_SIMILARITY_THRESHOLD = 0.62

#: How many same-organisation rows to compare against. An organisation with more
#: open postings than this is a job board, and the URL and hash probes are the
#: ones that matter there.
CANDIDATE_LIMIT = 200


class MatchMethod(StrEnum):
    CANONICAL_URL = "canonical_url"
    CONTENT_HASH = "content_hash"
    TITLE_SIMILARITY = "title_similarity"
    EMBEDDING = "embedding"


@dataclass(frozen=True, slots=True)
class DuplicateMatch:
    opportunity_id: uuid.UUID
    method: MatchMethod
    #: 1.0 for an exact identifier match; the measured similarity otherwise.
    similarity: float


@dataclass(frozen=True, slots=True)
class Candidate:
    """The fields duplicate detection needs, independent of the ORM."""

    title: str
    canonical_url: str | None = None
    source_url: str | None = None
    content_hash: str | None = None
    organization_name: str | None = None
    organization_domain: str | None = None
    embedding: list[float] | None = None


def trigrams(value: str) -> set[str]:
    """Character trigrams of a string, padded at the edges.

    Padding follows ``pg_trgm``: the boundaries of a word carry signal, so "cat"
    yields ``{'  c', ' ca', 'cat', 'at '}`` rather than a single trigram.
    """
    text = (normalize_text(value) or "").casefold()
    if not text:
        return set()
    padded = f"  {text} "
    return {padded[i : i + 3] for i in range(len(padded) - 2)}


def similarity(left: str, right: str) -> float:
    """Jaccard similarity of two strings' trigram sets, in [0, 1]."""
    a, b = trigrams(left), trigrams(right)
    if not a or not b:
        return 0.0
    intersection = len(a & b)
    if intersection == 0:
        return 0.0
    return intersection / len(a | b)


class DeduplicationService:
    """Finds the existing row a candidate duplicates, if there is one."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find_duplicate(
        self, candidate: Candidate, *, exclude_id: uuid.UUID | None = None
    ) -> DuplicateMatch | None:
        for probe in (self._by_url, self._by_hash, self._by_title):
            match = await probe(candidate, exclude_id)
            if match is not None:
                return match
        # Embedding proximity is the fourth probe. It stays a no-op until Phase 3
        # populates the vectors; wiring it in early would mean comparing against
        # nulls and calling the result a decision.
        return None

    async def _by_url(
        self, candidate: Candidate, exclude_id: uuid.UUID | None
    ) -> DuplicateMatch | None:
        urls = {u for u in (candidate.canonical_url, candidate.source_url) if u}
        if not urls:
            return None
        stmt = select(Opportunity.id).where(
            or_(
                Opportunity.canonical_url.in_(urls),
                Opportunity.source_url.in_(urls),
            )
        )
        found = await self._first(stmt, exclude_id)
        return DuplicateMatch(found, MatchMethod.CANONICAL_URL, 1.0) if found is not None else None

    async def _by_hash(
        self, candidate: Candidate, exclude_id: uuid.UUID | None
    ) -> DuplicateMatch | None:
        if not candidate.content_hash:
            return None
        stmt = select(Opportunity.id).where(Opportunity.content_hash == candidate.content_hash)
        found = await self._first(stmt, exclude_id)
        return DuplicateMatch(found, MatchMethod.CONTENT_HASH, 1.0) if found is not None else None

    async def _by_title(
        self, candidate: Candidate, exclude_id: uuid.UUID | None
    ) -> DuplicateMatch | None:
        """Compare titles among postings from the same organisation.

        Restricting to one organisation is what keeps this precise: "Research
        Engineer" at two different labs is two opportunities, not one.
        """
        organization = normalize_text(candidate.organization_name)
        domain = normalize_text(candidate.organization_domain)
        if not organization and not domain:
            return None

        predicates = []
        if organization:
            predicates.append(func.lower(Opportunity.organization_name) == organization.casefold())
        if domain:
            predicates.append(func.lower(Opportunity.organization_domain) == domain.casefold())

        stmt = (
            select(Opportunity.id, Opportunity.title)
            .where(or_(*predicates))
            .where(Opportunity.status != OpportunityStatus.DUPLICATE)
            .limit(CANDIDATE_LIMIT)
        )
        if exclude_id is not None:
            stmt = stmt.where(Opportunity.id != exclude_id)

        rows = (await self.session.execute(stmt)).all()
        best: DuplicateMatch | None = None
        for row_id, title in rows:
            ratio = similarity(candidate.title, title)
            if ratio >= TITLE_SIMILARITY_THRESHOLD and (best is None or ratio > best.similarity):
                best = DuplicateMatch(row_id, MatchMethod.TITLE_SIMILARITY, round(ratio, 4))
        return best

    async def _first(self, stmt, exclude_id: uuid.UUID | None) -> uuid.UUID | None:  # type: ignore[no-untyped-def]
        stmt = stmt.where(Opportunity.status != OpportunityStatus.DUPLICATE)
        if exclude_id is not None:
            stmt = stmt.where(Opportunity.id != exclude_id)
        return (await self.session.execute(stmt.limit(1))).scalar_one_or_none()
