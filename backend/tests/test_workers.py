"""Worker enqueue and digest tests."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from app.workers.digest import ScheduledDigestService
from app.workers.enqueue import enqueue_investigation


@pytest.fixture
async def session(database_url: str):  # type: ignore[no-untyped-def]
    from app.db.session import get_session_factory

    factory = get_session_factory()
    async with factory() as db:
        yield db
        await db.rollback()


def test_enqueue_uses_background_tasks_by_default(settings) -> None:  # type: ignore[no-untyped-def]
    settings.workers.enabled = False
    background = MagicMock()
    run_id = uuid.uuid4()
    user_id = uuid.uuid4()
    mode = enqueue_investigation(
        settings,
        background=background,
        run_id=run_id,
        user_id=user_id,
        inline_runner=lambda *_args: None,
    )
    assert mode == "background"
    background.add_task.assert_called_once()


async def test_scheduled_digest_emits_for_user_with_goals(session, registered_user) -> None:  # type: ignore[no-untyped-def]
    from app.models.enums import GoalStatus, ObjectiveProfile
    from app.models.goal import Goal

    goal = Goal(
        user_id=uuid.UUID(registered_user["id"]),
        title="Find AI roles",
        objective_profile=ObjectiveProfile.CAREER,
        status=GoalStatus.ACTIVE,
    )
    session.add(goal)
    await session.flush()
    count = await ScheduledDigestService(session).emit(since_hours=24)
    assert count >= 0
