"""Profile knowledge retrieval."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.retrieval.factory import RetrievalStack, build_retrieval_stack
from app.retrieval.protocols import RetrievalResult
from app.services.user_service import UserService


class RetrievalService:
    def __init__(self, session: AsyncSession, stack: RetrievalStack, settings: Settings) -> None:
        self.session = session
        self.stack = stack
        self.settings = settings

    async def search_profile(
        self,
        *,
        user_id: uuid.UUID,
        query: str,
        top_k: int | None = None,
        rerank: bool | None = None,
    ) -> RetrievalResult:
        profile = await UserService(self.session).get_profile(user_id)
        result = await self.stack.retriever.search(
            user_id=user_id,
            query=query,
            profile=profile,
            rerank=rerank,
        )
        limit = top_k or self.settings.rag.rerank_top_n
        return RetrievalResult(
            query=result.query,
            passages=result.passages[:limit],
            degraded=result.degraded,
            detail=result.detail,
        )


def build_retrieval_service(session: AsyncSession, settings: Settings) -> RetrievalService:
    stack = build_retrieval_stack(session, settings)
    return RetrievalService(session, stack, settings)
