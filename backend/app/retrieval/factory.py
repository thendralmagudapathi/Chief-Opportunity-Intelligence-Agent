"""Build retrieval components from application settings."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.retrieval.embedding import build_embedding_provider
from app.retrieval.parsing import CompositeDocumentParser
from app.retrieval.protocols import DocumentParser, EmbeddingProvider, ObjectStorage, Reranker
from app.retrieval.reranker import build_reranker
from app.retrieval.retriever import ProfileRetriever
from app.retrieval.storage import LocalObjectStorage
from app.retrieval.vector_store import PgVectorStore


@dataclass(slots=True)
class RetrievalStack:
    embedder: EmbeddingProvider
    vector_store: PgVectorStore
    retriever: ProfileRetriever
    parser: DocumentParser
    storage: ObjectStorage
    reranker: Reranker | None


def build_retrieval_stack(
    session: AsyncSession,
    settings: Settings,
    *,
    redis_client: Any | None = None,
) -> RetrievalStack:
    embedder = build_embedding_provider(
        settings.rag,
        base_url=settings.models.base_url,
        redis_client=redis_client,
        cache_ttl_s=settings.redis.cache_ttl_s,
    )
    vector_store = PgVectorStore(session)
    reranker = build_reranker(
        model_name=settings.rag.reranker_model,
        enabled=settings.rag.rerank_enabled,
    )

    retriever = ProfileRetriever(
        vector_store=vector_store,
        embedder=embedder,
        reranker=reranker,
        retrieval_top_k=settings.rag.retrieval_top_k,
        rerank_top_n=settings.rag.rerank_top_n,
    )
    storage = LocalObjectStorage(Path(settings.storage.local_path))
    return RetrievalStack(
        embedder=embedder,
        vector_store=vector_store,
        retriever=retriever,
        parser=CompositeDocumentParser(),
        storage=storage,
        reranker=reranker if settings.rag.rerank_enabled else None,
    )
