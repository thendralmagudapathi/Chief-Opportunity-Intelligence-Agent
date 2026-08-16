"""Investigation and agent run API routes."""

from __future__ import annotations

import uuid

import pytest
from app.models.enums import ObjectiveProfile
from app.seed import seed_corpus
from app.services.investigation_service import run_investigation_background


@pytest.fixture
async def seeded_goal(client, registered_user):  # type: ignore[no-untyped-def]
    from app.db.session import get_session_factory
    from app.models.goal import Goal

    factory = get_session_factory()
    async with factory() as db:
        await seed_corpus(db)
        goal = Goal(
            user_id=uuid.UUID(registered_user["id"]),
            title="AI in Germany",
            objective_profile=ObjectiveProfile.CAREER,
        )
        db.add(goal)
        await db.commit()
        await db.refresh(goal)
        return goal


async def test_investigate_endpoint_returns_run_metadata(
    client, registered_user, seeded_goal
) -> None:  # type: ignore[no-untyped-def]
    response = await client.post(
        "/api/v1/opportunities/investigate",
        headers=registered_user["headers"],
        json={
            "objective": "Find AI engineering opportunities in Germany",
            "goal_id": str(seeded_goal.id),
        },
    )
    assert response.status_code == 202, response.text
    body = response.json()
    run_id = body["run_id"]

    await run_investigation_background(uuid.UUID(run_id), uuid.UUID(registered_user["id"]))

    from app.db.session import get_session_factory
    from app.models.opportunity import Opportunity
    from sqlalchemy import delete

    factory = get_session_factory()
    async with factory() as db:
        await db.execute(delete(Opportunity))
        await db.commit()

    detail = await client.get(
        f"/api/v1/agent-runs/{run_id}",
        headers=registered_user["headers"],
    )
    assert detail.status_code == 200
    assert detail.json()["status"] == "succeeded"
    assert detail.json()["result"]["report"]["recommendations"] is not None
