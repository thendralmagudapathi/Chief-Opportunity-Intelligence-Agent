"""CI evaluation harness tests."""

from __future__ import annotations

import uuid

import pytest
from app.data.ci_evaluation_subset import total_case_count
from app.evaluation.harness import CIHarness


@pytest.fixture
async def session(database_url: str):  # type: ignore[no-untyped-def]
    from app.db.session import get_session_factory

    factory = get_session_factory()
    async with factory() as db:
        yield db
        await db.rollback()


async def test_ci_subset_has_fifty_cases() -> None:
    assert total_case_count() == 50


async def test_ci_harness_passes_gate(settings, session, registered_user, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("RAG__CHUNK_SIZE_TOKENS", "80")
    monkeypatch.setenv("RAG__CHUNK_OVERLAP_TOKENS", "16")
    from app.core.config import get_settings

    get_settings.cache_clear()
    harness = CIHarness(session, get_settings())
    result = await harness.run(user_id=uuid.UUID(registered_user["id"]))
    assert result.case_count == 50
    assert result.metrics["tool_selection_accuracy"] >= 0.90
    assert result.metrics["faithfulness"] >= 0.85
    assert result.passed, result.failures
