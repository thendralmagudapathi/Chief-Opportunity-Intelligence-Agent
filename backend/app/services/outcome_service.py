"""Outcome tracking and outcome memory writes."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.memory.service import MemoryService
from app.models.application import Outcome
from app.models.opportunity import Opportunity
from app.schemas.outcome import OutcomeCreate


class OutcomeService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self._memory = MemoryService(session)

    async def record(self, user_id: uuid.UUID, payload: OutcomeCreate) -> Outcome:
        opportunity = await self.session.get(Opportunity, payload.opportunity_id)
        if opportunity is None:
            raise NotFoundError("Opportunity not found")

        occurred = payload.occurred_at or datetime.now(UTC)
        row = Outcome(
            user_id=user_id,
            opportunity_id=payload.opportunity_id,
            application_id=payload.application_id,
            outcome=payload.outcome,
            occurred_at=occurred,
            details=dict(payload.details),
        )
        self.session.add(row)
        await self.session.flush()

        await self._memory.write_outcome(
            user_id=user_id,
            content=f"{payload.outcome.value} for opportunity {payload.opportunity_id}",
            provenance={"outcome_id": str(row.id), "opportunity_id": str(payload.opportunity_id)},
            source_ref=str(row.id),
            confidence=1.0,
        )
        return row
