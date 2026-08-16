"""Embedding duplicate probe."""

from __future__ import annotations

import pytest
from app.models.enums import OpportunityCategory, OpportunityStatus, RemoteStatus
from app.models.opportunity import Opportunity
from app.retrieval.embedding import FakeEmbeddingProvider
from app.services.dedup import Candidate, DeduplicationService, MatchMethod


@pytest.fixture
async def session(database_url: str):  # type: ignore[no-untyped-def]
    from app.db.session import get_session_factory

    factory = get_session_factory()
    async with factory() as db:
        yield db
        await db.rollback()


async def test_embedding_probe_finds_near_duplicate(session) -> None:  # type: ignore[no-untyped-def]
    embedder = FakeEmbeddingProvider(dimension=768)
    base_vector = (await embedder.embed(["Senior ML Engineer at Example Corp"]))[0]
    near_vector = base_vector
    far_vector = (await embedder.embed(["Junior accountant role"]))[0]

    existing = Opportunity(
        title="Senior ML Engineer",
        source_url="https://example.com/original",
        canonical_url="https://example.com/original",
        category=OpportunityCategory.JOB,
        status=OpportunityStatus.DISCOVERED,
        remote_status=RemoteStatus.REMOTE,
        embedding=base_vector,
    )
    session.add(existing)
    await session.flush()

    service = DeduplicationService(session)
    near = await service.find_duplicate(
        Candidate(
            title="Platform Reliability Specialist",
            source_url="https://other.example/copy",
            organization_name="Different Org",
            embedding=near_vector,
        )
    )
    far = await service.find_duplicate(
        Candidate(
            title="Junior Accountant",
            source_url="https://example.com/other",
            organization_name="Other Co",
            embedding=far_vector,
        )
    )

    assert near is not None
    assert near.method is MatchMethod.EMBEDDING
    assert near.opportunity_id == existing.id
    assert far is None
