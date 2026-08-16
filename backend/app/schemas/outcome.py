"""Outcome tracking payloads."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import OutcomeType
from app.schemas.common import ORMModel


class OutcomeCreate(BaseModel):
    opportunity_id: uuid.UUID
    application_id: uuid.UUID | None = None
    outcome: OutcomeType
    occurred_at: datetime | None = None
    details: dict[str, object] = Field(default_factory=dict)


class OutcomeRead(ORMModel):
    id: uuid.UUID
    user_id: uuid.UUID
    opportunity_id: uuid.UUID
    application_id: uuid.UUID | None
    outcome: OutcomeType
    occurred_at: datetime | None
    details: dict[str, object]
