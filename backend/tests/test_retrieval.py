"""Document ingestion and profile retrieval."""

from __future__ import annotations

import uuid

import pytest
from app.data.profile_qa_benchmark import PROFILE_QA_BENCHMARK, SAMPLE_PROFILE_DOCUMENT
from app.models.enums import DocumentStatus
from app.retrieval.metrics import phrase_ndcg_at_k, phrase_recall_at_k
from app.schemas.profile import ProfilePatch


@pytest.fixture
def storage_path(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    path = tmp_path / "uploads"
    monkeypatch.setenv("STORAGE__LOCAL_PATH", str(path))
    from app.core.config import get_settings

    get_settings.cache_clear()
    yield path
    get_settings.cache_clear()


@pytest.fixture
async def session(database_url: str):  # type: ignore[no-untyped-def]
    from app.db.session import get_session_factory

    factory = get_session_factory()
    async with factory() as db:
        yield db
        await db.rollback()


async def test_document_upload_index_and_search(session, registered_user, storage_path) -> None:  # type: ignore[no-untyped-def]
    from app.core.config import get_settings
    from app.retrieval.factory import build_retrieval_stack
    from app.services.document_service import DocumentService
    from app.services.retrieval_service import RetrievalService

    settings = get_settings()
    stack = build_retrieval_stack(session, settings)
    documents = DocumentService(session, stack, settings)
    retrieval = RetrievalService(session, stack, settings)

    from app.services.user_service import UserService

    await UserService(session).patch_profile(
        uuid.UUID(registered_user["id"]),
        ProfilePatch(
            headline="AI engineer",
            location_city="Bangalore",
            location_country="IN",
            skills=[{"name": "PyTorch", "level": 4, "years": 3}],
        ),
    )

    document = await documents.upload(
        user_id=uuid.UUID(registered_user["id"]),
        filename="profile.txt",
        data=SAMPLE_PROFILE_DOCUMENT.encode("utf-8"),
    )
    assert document.status is DocumentStatus.PENDING

    await documents.index_document(document.id)
    await session.flush()

    document = await documents.get_document(uuid.UUID(registered_user["id"]), document.id)
    assert document.status is DocumentStatus.INDEXED

    result = await retrieval.search_profile(
        user_id=uuid.UUID(registered_user["id"]),
        query="Which ML frameworks does the user know?",
        rerank=True,
    )
    joined = " ".join(passage.content.casefold() for passage in result.passages)
    assert "pytorch" in joined


async def test_profile_qa_benchmark_recall_and_rerank_gain(
    session, registered_user, storage_path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("RAG__CHUNK_SIZE_TOKENS", "80")
    monkeypatch.setenv("RAG__CHUNK_OVERLAP_TOKENS", "16")
    from app.core.config import get_settings

    get_settings.cache_clear()

    from app.retrieval.factory import build_retrieval_stack
    from app.services.document_service import DocumentService
    from app.services.retrieval_service import RetrievalService

    settings = get_settings()
    stack = build_retrieval_stack(session, settings)
    documents = DocumentService(session, stack, settings)
    retrieval = RetrievalService(session, stack, settings)

    document = await documents.upload(
        user_id=uuid.UUID(registered_user["id"]),
        filename="profile.txt",
        data=SAMPLE_PROFILE_DOCUMENT.encode("utf-8"),
    )
    await documents.index_document(document.id)
    await session.flush()

    recalls: list[float] = []
    ndcgs_without: list[float] = []
    ndcgs_with: list[float] = []

    for pair in PROFILE_QA_BENCHMARK:
        without = await retrieval.search_profile(
            user_id=uuid.UUID(registered_user["id"]),
            query=pair.question,
            rerank=False,
            top_k=20,
        )
        with_rerank = await retrieval.search_profile(
            user_id=uuid.UUID(registered_user["id"]),
            query=pair.question,
            rerank=True,
            top_k=10,
        )
        relevant = {phrase.casefold() for phrase in pair.relevant_phrases}
        retrieved_without = [passage.content.casefold() for passage in without.passages[:20]]
        retrieved_with = [passage.content.casefold() for passage in with_rerank.passages[:10]]

        recalls.append(
            phrase_recall_at_k(
                relevant,
                retrieved_without,
                k=20,
            )
        )
        ndcgs_without.append(phrase_ndcg_at_k(relevant, retrieved_without, k=10))
        ndcgs_with.append(phrase_ndcg_at_k(relevant, retrieved_with, k=10))

    assert sum(recalls) / len(recalls) >= 0.9
    assert (sum(ndcgs_with) / len(ndcgs_with)) >= (sum(ndcgs_without) / len(ndcgs_without)) * 1.05
