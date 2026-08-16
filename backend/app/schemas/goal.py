"""Goal payloads."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import GoalStatus, ObjectiveProfile
from app.schemas.common import ORMModel


class GoalCreate(BaseModel):
    title: str = Field(min_length=3, max_length=255)
    description: str | None = Field(default=None, max_length=8000)
    objective_profile: ObjectiveProfile = ObjectiveProfile.CAREER
    priority: int = Field(default=3, ge=1, le=5)
    deadline: datetime | None = None
    desired_outcome: str | None = Field(default=None, max_length=4000)
    constraints: dict[str, Any] = Field(default_factory=dict)
    acceptable_tradeoffs: list[str] = Field(default_factory=list, max_length=30)
    weights_override: dict[str, float] | None = Field(
        default=None,
        description="Overrides the weight vector implied by objective_profile",
    )


class GoalUpdate(BaseModel):
    model_config = {"extra": "forbid"}

    title: str | None = Field(default=None, min_length=3, max_length=255)
    description: str | None = None
    objective_profile: ObjectiveProfile | None = None
    priority: int | None = Field(default=None, ge=1, le=5)
    status: GoalStatus | None = None
    deadline: datetime | None = None
    desired_outcome: str | None = None
    constraints: dict[str, Any] | None = None
    acceptable_tradeoffs: list[str] | None = None
    weights_override: dict[str, float] | None = None


class GoalRead(ORMModel):
    id: uuid.UUID
    user_id: uuid.UUID
    title: str
    description: str | None
    objective_profile: ObjectiveProfile
    priority: int
    status: GoalStatus
    deadline: datetime | None
    desired_outcome: str | None
    constraints: dict[str, Any]
    acceptable_tradeoffs: list[Any]
    weights_override: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class ScoreRunRead(BaseModel):
    """Summary of a scoring pass against one goal."""

    goal_id: uuid.UUID
    scored: int
    recommended: int
