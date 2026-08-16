"""Memory immutability tests."""

from __future__ import annotations

import uuid

import pytest
from app.memory.service import MemoryService
from app.models.memory import MemoryRecord


@pytest.fixture
async def session(database_url: str):  # type: ignore[no-untyped-def]
    from app.db.session import get_session_factory

    factory = get_session_factory()
    async with factory() as db:
        yield db
        await db.rollback()


async def test_semantic_memory_supersedes_instead_of_mutating(session, registered_user) -> None:  # type: ignore[no-untyped-def]
    user_id = uuid.UUID(registered_user["id"])
    service = MemoryService(session)
    first = await service.write_semantic(
        user_id=user_id,
        key="preferred_location",
        content="Berlin",
        provenance={"source": "profile"},
    )
    second = await service.write_semantic(
        user_id=user_id,
        key="preferred_location",
        content="Munich",
        provenance={"source": "profile"},
    )
    await session.commit()

    refreshed_first = await session.get(MemoryRecord, first.id)
    assert refreshed_first is not None
    assert refreshed_first.valid_to is not None
    assert refreshed_first.superseded_by_id == second.id
    assert refreshed_first.content == "Berlin"
    assert second.content == "Munich"


async def test_semantic_memory_is_idempotent_for_same_content(session, registered_user) -> None:  # type: ignore[no-untyped-def]
    user_id = uuid.UUID(registered_user["id"])
    service = MemoryService(session)
    first = await service.write_semantic(
        user_id=user_id,
        key="timezone",
        content="Europe/Berlin",
        provenance={"source": "profile"},
    )
    second = await service.write_semantic(
        user_id=user_id,
        key="timezone",
        content="Europe/Berlin",
        provenance={"source": "profile"},
    )
    assert first.id == second.id
