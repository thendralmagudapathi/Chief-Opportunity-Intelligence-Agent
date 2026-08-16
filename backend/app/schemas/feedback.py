"""Feedback API payloads."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from app.models.enums import FeedbackSignal
from app.schemas.common import ORMModel


class FeedbackCreate(BaseModel):
    signal: FeedbackSignal
    opportunity_id: uuid.UUID | None = None
    agent_run_id: uuid.UUID | None = None
    comment: str | None = Field(default=None, max_length=4000)
    payload: dict[str, object] = Field(default_factory=dict)


class FeedbackRead(ORMModel):
    id: uuid.UUID
    user_id: uuid.UUID
    opportunity_id: uuid.UUID | None
    agent_run_id: uuid.UUID | None
    signal: FeedbackSignal
    comment: str | None
    payload: dict[str, object]
