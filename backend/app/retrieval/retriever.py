"""Hybrid retrieval orchestration."""

from __future__ import annotations

import uuid

from app.models.user import UserProfile
from app.retrieval.hybrid import reciprocal_rank_fusion
from app.retrieval.profile_index import profile_passages, rank_profile_passages
from app.retrieval.protocols import (
    EmbeddingProvider,
    Reranker,
    RetrievalResult,
    ScoredPassage,
    VectorStore,
)


class ProfileRetriever:
    """Retrieve from the private profile index (documents + structured profile)."""

    def __init__(
        self,
        *,
        vector_store: VectorStore,
        embedder: EmbeddingProvider,
        reranker: Reranker | None,
        retrieval_top_k: int,
        rerank_top_n: int,
    ) -> None:
        self._vector_store = vector_store
        self._embedder = embedder
        self._reranker = reranker
        self._retrieval_top_k = retrieval_top_k
        self._rerank_top_n = rerank_top_n

    async def search(
        self,
        *,
        user_id: uuid.UUID,
        query: str,
        profile: UserProfile | None = None,
        rerank: bool | None = None,
    ) -> RetrievalResult:
        query = query.strip()
        if not query:
            return RetrievalResult(query=query, passages=[])

        degraded = False
        dense: list[ScoredPassage] = []
        try:
            query_vector = (await self._embedder.embed([query]))[0]
            dense = await self._vector_store.dense_search(
                user_id=user_id,
                query_vector=query_vector,
                limit=self._retrieval_top_k,
            )
        except Exception:
            degraded = True

        lexical = await self._vector_store.lexical_search(
            user_id=user_id,
            query=query,
            limit=self._retrieval_top_k,
        )

        profile_hits: list[ScoredPassage] = []
        if profile is not None:
            profile_hits = rank_profile_passages(
                query,
                profile_passages(profile),
                limit=self._retrieval_top_k,
            )

        fused = reciprocal_rank_fusion(
            dense,
            lexical,
            profile_hits,
            limit=self._retrieval_top_k,
        )

        use_rerank = rerank if rerank is not None else self._reranker is not None
        if use_rerank and self._reranker is not None and fused:
            passages = await self._reranker.rerank(query, fused, top_n=self._rerank_top_n)
        else:
            passages = fused[: self._retrieval_top_k]

        return RetrievalResult(
            query=query,
            passages=passages,
            degraded=degraded,
            detail="dense retrieval unavailable; lexical and profile only" if degraded else None,
        )

    async def search_multi(
        self,
        *,
        user_id: uuid.UUID,
        queries: list[str],
        profile: UserProfile | None = None,
        rerank: bool | None = None,
    ) -> RetrievalResult:
        """Run hybrid retrieval for multiple query variants and fuse the results."""
        cleaned = [query.strip() for query in queries if query.strip()]
        if not cleaned:
            return RetrievalResult(query="", passages=[])

        ranked_lists: list[list[ScoredPassage]] = []
        degraded = False
        detail: str | None = None
        for query in cleaned:
            result = await self.search(
                user_id=user_id,
                query=query,
                profile=profile,
                rerank=False,
            )
            ranked_lists.append(result.passages)
            degraded = degraded or result.degraded
            if result.detail and detail is None:
                detail = result.detail

        fused = (
            reciprocal_rank_fusion(*ranked_lists, limit=self._retrieval_top_k)
            if ranked_lists
            else []
        )
        use_rerank = rerank if rerank is not None else self._reranker is not None
        primary_query = cleaned[0]
        if use_rerank and self._reranker is not None and fused:
            passages = await self._reranker.rerank(primary_query, fused, top_n=self._rerank_top_n)
        else:
            passages = fused[: self._rerank_top_n]

        return RetrievalResult(
            query=primary_query,
            passages=passages,
            degraded=degraded,
            detail=detail,
        )
