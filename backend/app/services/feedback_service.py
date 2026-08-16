"""Feedback capture."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feedback import Feedback
from app.schemas.feedback import FeedbackCreate


class FeedbackService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, user_id: uuid.UUID, payload: FeedbackCreate) -> Feedback:
        row = Feedback(
            user_id=user_id,
            opportunity_id=payload.opportunity_id,
            agent_run_id=payload.agent_run_id,
            signal=payload.signal,
            comment=payload.comment,
            payload=dict(payload.payload),
        )
        self.session.add(row)
        await self.session.flush()
        return row
