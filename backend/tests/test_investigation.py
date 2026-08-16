"""Investigation graph end-to-end."""

from __future__ import annotations

import uuid

import pytest
from app.agents.schemas import InvestigationRequest
from app.models.enums import AgentRunStatus, ObjectiveProfile
from app.seed import seed_corpus
from app.services.investigation_service import run_investigation_background


@pytest.fixture
async def session(database_url: str):  # type: ignore[no-untyped-def]
    from app.db.session import get_session_factory

    factory = get_session_factory()
    async with factory() as db:
        yield db
        await db.rollback()


async def test_investigation_produces_a_persisted_report(session, registered_user) -> None:  # type: ignore[no-untyped-def]
    from app.core.config import get_settings
    from app.models.goal import Goal
    from app.services.agent_run_service import AgentRunService
    from app.services.investigation_service import InvestigationService

    await seed_corpus(session)
    goal = Goal(
        user_id=uuid.UUID(registered_user["id"]),
        title="AI roles in Germany",
        objective_profile=ObjectiveProfile.CAREER,
    )
    session.add(goal)
    await session.flush()

    settings = get_settings()
    investigation = InvestigationService(session, settings)
    run_id, _trace = await investigation.start(
        uuid.UUID(registered_user["id"]),
        InvestigationRequest(
            objective="Find high-value AI engineering opportunities in Germany",
            goal_id=goal.id,
        ),
    )
    await session.commit()

    await run_investigation_background(run_id, uuid.UUID(registered_user["id"]))

    from app.models.opportunity import Opportunity
    from sqlalchemy import delete

    await session.execute(delete(Opportunity))
    await session.commit()

    runs = AgentRunService(session)
    run = await runs.get_run(uuid.UUID(registered_user["id"]), run_id)
    assert run.status is AgentRunStatus.SUCCEEDED
    assert run.result is not None
    assert run.result.get("report") is not None
    assert run.tasks
