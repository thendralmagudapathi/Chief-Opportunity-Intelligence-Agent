"""Ingestion, scoring persistence, refresh, and ranking determinism."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.data.corpus import CORPUS
from app.models.enums import OpportunityCategory, OpportunityStatus, Recommendation, RemoteStatus
from app.seed import seed_corpus
from app.services.ingestion import IngestionOutcome, IngestionService, RawOpportunity
from app.services.scoring_service import ScoringService

NOW = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)


@pytest.fixture
async def session(database_url: str):  # type: ignore[no-untyped-def]
    from app.db.session import get_session_factory

    factory = get_session_factory()
    async with factory() as db:
        yield db
        await db.rollback()


def _raw(
    title: str, url: str, *, deadline: str | None = None, org: str = "Example"
) -> RawOpportunity:
    return RawOpportunity(
        title=title,
        source_url=url,
        category=OpportunityCategory.JOB,
        organization_name=org,
        deadline=deadline,
        remote_status=RemoteStatus.REMOTE,
    )


async def test_ingest_rejects_an_empty_title(session) -> None:  # type: ignore[no-untyped-def]
    result = await IngestionService(session).ingest(
        RawOpportunity(title="  ", source_url="https://example.com/x")
    )
    assert result.outcome is IngestionOutcome.REJECTED


async def test_refresh_expires_a_row_whose_deadline_has_passed(session) -> None:  # type: ignore[no-untyped-def]
    ingestion = IngestionService(session)
    created = await ingestion.ingest(
        _raw("Expiring role", "https://expire.example/role", deadline="2026-08-20"),
        now=NOW,
    )
    assert created.opportunity is not None
    assert created.opportunity.status is OpportunityStatus.DISCOVERED

    assessment = await ingestion.refresh(created.opportunity, now=NOW + timedelta(days=10))
    assert assessment.is_expired is True
    assert created.opportunity.status is OpportunityStatus.EXPIRED


async def test_scoring_moves_discovered_to_scored(session, registered_user) -> None:  # type: ignore[no-untyped-def]
    from app.models.enums import ObjectiveProfile
    from app.models.goal import Goal

    ingestion = IngestionService(session)
    created = await ingestion.ingest(
        _raw("Role", f"https://score.example/{uuid.uuid4().hex}", deadline="2026-12-01"),
        now=NOW,
    )
    goal = Goal(
        user_id=uuid.UUID(registered_user["id"]),
        title="Find a role",
        objective_profile=ObjectiveProfile.CAREER,
    )
    session.add(goal)
    await session.flush()

    row = await ScoringService(session).score_opportunity(created.opportunity, goal, now=NOW)
    assert created.opportunity.status in (
        OpportunityStatus.SCORED,
        OpportunityStatus.RECOMMENDED,
    )
    assert row.factors["weights_version"] == "career.v1"
    assert "rationale" in row.factors
    assert "why_this" in row.explanation


async def test_corpus_seed_is_idempotent(session) -> None:  # type: ignore[no-untyped-def]
    first = await seed_corpus(session, now=NOW)
    assert first.created == len(CORPUS)
    assert first.rejected == 0
    second = await seed_corpus(session, now=NOW)
    assert second.created == 0
    assert second.merged == len(CORPUS)


async def test_ranking_is_deterministic_for_a_fixed_corpus(
    client, registered_user, cleanup_opportunities
) -> None:  # type: ignore[no-untyped-def]
    """The exit criterion: the same corpus, scored twice, ranks identically."""
    from app.db.session import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        ingestion = IngestionService(session)
        titles = [
            ("Close deadline", "2026-08-25"),
            ("Mid deadline", "2026-10-01"),
            ("Far deadline", "2026-12-01"),
            ("No deadline", None),
        ]
        for title, deadline in titles:
            result = await ingestion.ingest(
                _raw(title, f"https://rank.example/{title.replace(' ', '-')}", deadline=deadline),
                now=NOW,
            )
            assert result.opportunity is not None
            cleanup_opportunities.append(result.opportunity.id)
        await session.commit()

    created = await client.post(
        "/api/v1/goals",
        headers=registered_user["headers"],
        json={"title": "Rank these", "objective_profile": "career"},
    )
    assert created.status_code == 201, created.text
    goal_id = created.json()["id"]

    first_score = await client.post(
        f"/api/v1/goals/{goal_id}/score", headers=registered_user["headers"]
    )
    assert first_score.status_code == 200, first_score.text
    assert first_score.json()["scored"] >= 4

    async def titles_in_rank_order() -> list[str]:
        response = await client.get(
            "/api/v1/opportunities",
            params={"goal_id": goal_id, "sort": "score", "q": "deadline"},
            headers=registered_user["headers"],
        )
        assert response.status_code == 200, response.text
        return [item["title"] for item in response.json()["items"]]

    first = await titles_in_rank_order()
    second_score = await client.post(
        f"/api/v1/goals/{goal_id}/score", headers=registered_user["headers"]
    )
    assert second_score.status_code == 200
    second = await titles_in_rank_order()
    assert first == second
    # Time sensitivity is the only derived benefit, so closer deadlines rank higher.
    assert first.index("Close deadline") < first.index("Mid deadline")
    assert first.index("Mid deadline") < first.index("Far deadline")
    assert first.index("Far deadline") < first.index("No deadline")


async def test_http_refresh_returns_the_updated_row(
    client, registered_user, cleanup_opportunities
) -> None:  # type: ignore[no-untyped-def]
    from app.db.session import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        result = await IngestionService(session).ingest(
            _raw(
                "Past deadline",
                f"https://refresh.example/{uuid.uuid4().hex}",
                deadline="2020-01-01",
            ),
            now=NOW,
        )
        assert result.opportunity is not None
        await session.commit()
        opportunity_id = result.opportunity.id
        cleanup_opportunities.append(opportunity_id)

    response = await client.post(
        f"/api/v1/opportunities/{opportunity_id}/refresh",
        headers=registered_user["headers"],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "expired"
    assert body["freshness"]["score"] == 0.0


async def test_detail_exposes_explanation_after_scoring(
    client, registered_user, cleanup_opportunities
) -> None:  # type: ignore[no-untyped-def]
    from app.db.session import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        result = await IngestionService(session).ingest(
            _raw(
                "Explained role",
                f"https://explain.example/{uuid.uuid4().hex}",
                deadline="2026-09-01",
            ),
            now=NOW,
        )
        assert result.opportunity is not None
        await session.commit()
        cleanup_opportunities.append(result.opportunity.id)
        opportunity_id = result.opportunity.id

    goal = await client.post(
        "/api/v1/goals",
        headers=registered_user["headers"],
        json={"title": "Explain this", "objective_profile": "career"},
    )
    goal_id = goal.json()["id"]
    scored = await client.post(f"/api/v1/goals/{goal_id}/score", headers=registered_user["headers"])
    assert scored.status_code == 200, scored.text

    detail = await client.get(
        f"/api/v1/opportunities/{opportunity_id}",
        params={"goal_id": goal_id},
        headers=registered_user["headers"],
    )
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["score"] is not None
    assert body["recommendation"] in {item.value for item in Recommendation}
    assert "why_this" in body["explanation"]
    assert "next_step" in body["explanation"]
