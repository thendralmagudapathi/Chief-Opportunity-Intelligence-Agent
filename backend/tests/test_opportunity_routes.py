"""Opportunity HTTP endpoints.

The detail endpoint is exercised through the ASGI app rather than the service,
because its failure mode was serialisation: composing the response used to
validate the response model straight off the ORM instance, and the ``evidence``
field then reached for the relationship of the same name and emitted lazy IO
inside the async session. Only a request that actually renders the body catches
that.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from app.models.enums import (
    ClaimType,
    EvidenceStance,
    ObjectiveProfile,
    OpportunityCategory,
    OpportunityStatus,
    Recommendation,
    RemoteStatus,
)
from app.models.opportunity import Opportunity, OpportunityEvidence, OpportunityScore

NOW = datetime.now(UTC)


@pytest.fixture
async def scored_opportunity(app, registered_user, cleanup_opportunities):  # type: ignore[no-untyped-def]
    """An opportunity carrying one score row and one evidence row."""
    from app.db.session import get_session_factory

    goal_id = uuid.UUID(registered_user["id"])  # any UUID; the score is user-scoped
    factory = get_session_factory()
    async with factory() as session:
        opportunity = Opportunity(
            title="Research Scientist, Alignment",
            category=OpportunityCategory.RESEARCH,
            organization_name="Example Lab",
            location_country="US",
            remote_status=RemoteStatus.REMOTE,
            source_url=f"https://example.com/{uuid.uuid4().hex[:8]}",
            status=OpportunityStatus.RECOMMENDED,
            compensation_min=Decimal("150000.00"),
            compensation_max=Decimal("210000.00"),
            compensation_currency="USD",
            requirements=[],
            eligibility={},
            required_skills=[],
            preferred_skills=[],
            freshness_score=0.9,
            discovered_at=NOW,
        )
        session.add(opportunity)
        await session.flush()

        session.add(
            OpportunityScore(
                opportunity_id=opportunity.id,
                user_id=uuid.UUID(registered_user["id"]),
                scoring_profile=ObjectiveProfile.CAREER,
                weights_version="v1",
                engine_version="0.1.0",
                overall_score=Decimal("91.50"),
                fit_score=Decimal("0.9200"),
                recommendation=Recommendation.PURSUE,
                computed_at=NOW,
            )
        )
        session.add(
            OpportunityEvidence(
                opportunity_id=opportunity.id,
                claim="Role is fully remote within the US.",
                claim_type=ClaimType.FACT,
                stance=EvidenceStance.SUPPORTS,
                source_url="https://example.com/posting",
                retrieved_at=NOW,
                confidence=Decimal("0.9500"),
            )
        )
        await session.commit()
        cleanup_opportunities.append(opportunity.id)
        return {"id": str(opportunity.id), "goal_id": str(goal_id)}


async def test_detail_returns_score_and_evidence(client, registered_user, scored_opportunity):  # type: ignore[no-untyped-def]
    response = await client.get(
        f"/api/v1/opportunities/{scored_opportunity['id']}",
        headers=registered_user["headers"],
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["title"] == "Research Scientist, Alignment"
    assert body["score"]["overall_score"] == "91.50"
    assert body["score"]["dimensions"]["fit_score"] == "0.9200"
    assert body["recommendation"] == "PURSUE"
    assert body["explanation"] == {}
    assert body["compensation"] == {
        "min": "150000.00",
        "max": "210000.00",
        "currency": "USD",
        "period": None,
    }
    assert body["freshness"]["score"] == 0.9
    assert len(body["evidence"]) == 1
    assert body["evidence"][0]["claim_type"] == "FACT"


async def test_detail_without_a_score_still_renders(client, registered_user, cleanup_opportunities):  # type: ignore[no-untyped-def]
    """An unscored opportunity is a normal state, not an error."""
    from app.db.session import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        opportunity = Opportunity(
            title="Unscored posting",
            category=OpportunityCategory.JOB,
            remote_status=RemoteStatus.UNKNOWN,
            source_url=f"https://example.com/{uuid.uuid4().hex[:8]}",
            status=OpportunityStatus.DISCOVERED,
            requirements=[],
            eligibility={},
            required_skills=[],
            preferred_skills=[],
        )
        session.add(opportunity)
        await session.commit()
        opportunity_id = opportunity.id
        cleanup_opportunities.append(opportunity_id)

    response = await client.get(
        f"/api/v1/opportunities/{opportunity_id}", headers=registered_user["headers"]
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["score"] is None
    assert body["evidence"] == []


async def test_detail_of_unknown_id_is_404(client, registered_user):  # type: ignore[no-untyped-def]
    response = await client.get(
        f"/api/v1/opportunities/{uuid.uuid4()}", headers=registered_user["headers"]
    )
    assert response.status_code == 404
    assert response.json()["type"] == "not_found"


async def test_detail_requires_authentication(client, scored_opportunity):  # type: ignore[no-untyped-def]
    response = await client.get(f"/api/v1/opportunities/{scored_opportunity['id']}")
    assert response.status_code == 401


async def test_list_exposes_score_and_recommendation(client, registered_user, scored_opportunity):  # type: ignore[no-untyped-def]
    """List items carry the score flat; the nested object belongs to the detail."""
    response = await client.get(
        "/api/v1/opportunities", params={"sort": "score"}, headers=registered_user["headers"]
    )
    assert response.status_code == 200, response.text
    items = response.json()["items"]

    match = next(i for i in items if i["id"] == scored_opportunity["id"])
    assert match["overall_score"] == "91.50"
    assert match["recommendation"] == "PURSUE"
    assert "score" not in match
