"""Profile retrieval payloads."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field


class ProfileSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    top_k: int | None = Field(default=None, ge=1, le=100)
    rerank: bool | None = None


class RetrievedPassage(BaseModel):
    content: str
    score: float
    channel: Literal["dense", "lexical", "profile", "fused", "reranked"]
    chunk_id: uuid.UUID | None = None
    document_id: uuid.UUID | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class ProfileSearchResponse(BaseModel):
    query: str
    passages: list[RetrievedPassage]
    degraded: bool = False
    detail: str | None = None
