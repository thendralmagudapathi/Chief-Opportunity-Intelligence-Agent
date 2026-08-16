"""Retrieval protocols and shared value types.

Business logic depends on these abstractions, never on a concrete vector store
or embedding vendor.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

RetrievalChannel = Literal["dense", "lexical", "profile", "fused", "reranked"]


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    """Structured text extracted from an uploaded file."""

    text: str
    title: str | None = None
    sections: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class TextChunk:
    """A bounded passage ready for embedding."""

    index: int
    content: str
    token_count: int
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ScoredPassage:
    chunk_id: uuid.UUID | None
    content: str
    score: float
    channel: RetrievalChannel
    document_id: uuid.UUID | None = None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    query: str
    passages: list[ScoredPassage]
    degraded: bool = False
    detail: str | None = None


@runtime_checkable
class DocumentParser(Protocol):
    def supports(self, content_type: str, filename: str) -> bool: ...

    def parse(self, data: bytes, *, filename: str, content_type: str) -> ParsedDocument: ...


@runtime_checkable
class EmbeddingProvider(Protocol):
    @property
    def model_name(self) -> str: ...

    @property
    def dimension(self) -> int: ...

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


@runtime_checkable
class VectorStore(Protocol):
    async def upsert_chunks(
        self,
        *,
        user_id: uuid.UUID,
        document_id: uuid.UUID,
        chunks: list[tuple[int, str, list[float], dict[str, Any]]],
        embedding_model: str,
    ) -> None: ...

    async def delete_document(self, *, user_id: uuid.UUID, document_id: uuid.UUID) -> None: ...

    async def dense_search(
        self,
        *,
        user_id: uuid.UUID,
        query_vector: list[float],
        limit: int,
    ) -> list[ScoredPassage]: ...

    async def lexical_search(
        self,
        *,
        user_id: uuid.UUID,
        query: str,
        limit: int,
    ) -> list[ScoredPassage]: ...


@runtime_checkable
class Reranker(Protocol):
    async def rerank(
        self, query: str, passages: list[ScoredPassage], *, top_n: int
    ) -> list[ScoredPassage]: ...


@runtime_checkable
class ObjectStorage(Protocol):
    async def put(self, *, key: str, data: bytes, content_type: str) -> str: ...

    async def get(self, *, uri: str) -> bytes: ...

    async def delete(self, *, uri: str) -> None: ...
