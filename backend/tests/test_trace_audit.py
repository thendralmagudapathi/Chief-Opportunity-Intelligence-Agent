"""Investigation trace audit."""

from __future__ import annotations

import uuid

import pytest
from app.evaluation.trace_audit import REQUIRED_STAGES, audit_investigation_trace
from app.models.enums import AgentRunStatus, AgentTaskStatus, ObjectiveProfile
from app.models.goal import Goal


@pytest.fixture
async def session(database_url: str):  # type: ignore[no-untyped-def]
    from app.db.session import get_session_factory

    factory = get_session_factory()
    async with factory() as db:
        yield db
        await db.rollback()


async def test_complete_trace_detects_missing_stages(session, registered_user) -> None:  # type: ignore[no-untyped-def]
    from app.models.agent_run import AgentTask
    from app.services.agent_run_service import AgentRunService

    user_id = uuid.UUID(registered_user["id"])
    goal = Goal(user_id=user_id, title="Test", objective_profile=ObjectiveProfile.CAREER)
    session.add(goal)
    await session.flush()
    run = await AgentRunService(session).create_run(
        user_id=user_id,
        goal_id=goal.id,
        objective="test trace",
    )
    run.status = AgentRunStatus.SUCCEEDED
    run.result = {
        "report": {"objective": "test"},
        "events": [
            {"stage": stage, "status": "done", "message": stage} for stage in REQUIRED_STAGES
        ],
    }
    session.add(
        AgentTask(
            agent_run_id=run.id,
            agent_name="supervisor",
            capability="understand",
            status=AgentTaskStatus.SUCCEEDED,
        )
    )
    session.add(
        AgentTask(
            agent_run_id=run.id,
            agent_name="supervisor",
            capability="plan",
            status=AgentTaskStatus.SUCCEEDED,
        )
    )
    session.add(
        AgentTask(
            agent_run_id=run.id,
            agent_name="verification",
            capability="verify",
            status=AgentTaskStatus.SUCCEEDED,
        )
    )
    session.add(
        AgentTask(
            agent_run_id=run.id,
            agent_name="contrarian",
            capability="contrarian",
            status=AgentTaskStatus.SUCCEEDED,
        )
    )
    await session.flush()

    audit = await audit_investigation_trace(session, run.id)
    assert audit.complete is True
    assert audit.missing_stages == ()
    assert audit.missing_tasks == ()
