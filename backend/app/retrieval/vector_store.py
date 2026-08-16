"""Vector store implementations."""

from __future__ import annotations

import math
import uuid
from typing import Any

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import DocumentChunk
from app.retrieval.protocols import ScoredPassage


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


class PgVectorStore:
    """pgvector + Postgres full-text search, with a SQLite fallback for tests."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @property
    def _is_postgres(self) -> bool:
        bind = self.session.get_bind()
        return bind.dialect.name == "postgresql"

    async def upsert_chunks(
        self,
        *,
        user_id: uuid.UUID,
        document_id: uuid.UUID,
        chunks: list[tuple[int, str, list[float], dict[str, Any]]],
        embedding_model: str,
    ) -> None:
        await self.delete_document(user_id=user_id, document_id=document_id)
        for chunk_index, content, embedding, meta in chunks:
            self.session.add(
                DocumentChunk(
                    document_id=document_id,
                    user_id=user_id,
                    chunk_index=chunk_index,
                    content=content,
                    token_count=len(content.split()),
                    embedding=embedding,
                    embedding_model=embedding_model,
                    meta=meta,
                )
            )
        await self.session.flush()

    async def delete_document(self, *, user_id: uuid.UUID, document_id: uuid.UUID) -> None:
        await self.session.execute(
            delete(DocumentChunk).where(
                DocumentChunk.user_id == user_id,
                DocumentChunk.document_id == document_id,
            )
        )

    async def dense_search(
        self,
        *,
        user_id: uuid.UUID,
        query_vector: list[float],
        limit: int,
    ) -> list[ScoredPassage]:
        if self._is_postgres:
            return await self._postgres_dense_search(
                user_id=user_id, query_vector=query_vector, limit=limit
            )
        return await self._sqlite_dense_search(
            user_id=user_id, query_vector=query_vector, limit=limit
        )

    async def lexical_search(
        self,
        *,
        user_id: uuid.UUID,
        query: str,
        limit: int,
    ) -> list[ScoredPassage]:
        if self._is_postgres:
            return await self._postgres_lexical_search(user_id=user_id, query=query, limit=limit)
        return await self._sqlite_lexical_search(user_id=user_id, query=query, limit=limit)

    async def _postgres_dense_search(
        self,
        *,
        user_id: uuid.UUID,
        query_vector: list[float],
        limit: int,
    ) -> list[ScoredPassage]:
        stmt = text(
            """
            SELECT id, document_id, content,
                   1 - (embedding <=> :query_vector) AS score
            FROM document_chunks
            WHERE user_id = :user_id AND embedding IS NOT NULL
            ORDER BY embedding <=> :query_vector
            LIMIT :limit
            """
        )
        result = await self.session.execute(
            stmt,
            {"user_id": str(user_id), "query_vector": query_vector, "limit": limit},
        )
        return [
            ScoredPassage(
                chunk_id=row.id,
                document_id=row.document_id,
                content=row.content,
                score=float(row.score),
                channel="dense",
            )
            for row in result
        ]

    async def _postgres_lexical_search(
        self,
        *,
        user_id: uuid.UUID,
        query: str,
        limit: int,
    ) -> list[ScoredPassage]:
        stmt = text(
            """
            SELECT id, document_id, content,
                   ts_rank(
                       to_tsvector('english', content),
                       plainto_tsquery('english', :query)
                   ) AS score
            FROM document_chunks
            WHERE user_id = :user_id
              AND to_tsvector('english', content) @@ plainto_tsquery('english', :query)
            ORDER BY score DESC
            LIMIT :limit
            """
        )
        result = await self.session.execute(
            stmt, {"user_id": str(user_id), "query": query, "limit": limit}
        )
        return [
            ScoredPassage(
                chunk_id=row.id,
                document_id=row.document_id,
                content=row.content,
                score=float(row.score),
                channel="lexical",
            )
            for row in result
        ]

    async def _sqlite_dense_search(
        self,
        *,
        user_id: uuid.UUID,
        query_vector: list[float],
        limit: int,
    ) -> list[ScoredPassage]:
        result = await self.session.execute(
            select(DocumentChunk).where(
                DocumentChunk.user_id == user_id,
                DocumentChunk.embedding.is_not(None),
            )
        )
        rows = result.scalars().all()
        scored = sorted(
            (
                ScoredPassage(
                    chunk_id=row.id,
                    document_id=row.document_id,
                    content=row.content,
                    score=cosine_similarity(query_vector, row.embedding or []),
                    channel="dense",
                )
                for row in rows
            ),
            key=lambda passage: passage.score,
            reverse=True,
        )
        return scored[:limit]

    async def _sqlite_lexical_search(
        self,
        *,
        user_id: uuid.UUID,
        query: str,
        limit: int,
    ) -> list[ScoredPassage]:
        tokens = [token for token in query.lower().split() if token]
        if not tokens:
            return []
        result = await self.session.execute(
            select(DocumentChunk).where(DocumentChunk.user_id == user_id)
        )
        rows = result.scalars().all()
        scored: list[ScoredPassage] = []
        for row in rows:
            content_lower = row.content.lower()
            hits = sum(1 for token in tokens if token in content_lower)
            if hits:
                scored.append(
                    ScoredPassage(
                        chunk_id=row.id,
                        document_id=row.document_id,
                        content=row.content,
                        score=hits / len(tokens),
                        channel="lexical",
                    )
                )
        scored.sort(key=lambda passage: passage.score, reverse=True)
        return scored[:limit]
