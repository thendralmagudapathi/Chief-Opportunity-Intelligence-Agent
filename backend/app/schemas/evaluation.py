"""Evaluation run API schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import EvaluationStatus
from app.schemas.common import ORMModel


class EvaluationRunRead(ORMModel):
    id: uuid.UUID
    name: str
    suite: str
    dataset_name: str
    dataset_version: str
    git_sha: str | None
    status: EvaluationStatus
    config: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = None
    mlflow_run_id: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime


class EvaluationRunListResponse(BaseModel):
    items: list[EvaluationRunRead]


class EvaluationTriggerRequest(BaseModel):
    suite: str = Field(default="ci", max_length=64)
    dataset_version: str = Field(default="v1", max_length=64)


class EvaluationTriggerResponse(BaseModel):
    run_id: uuid.UUID
    passed: bool
    metrics: dict[str, float]
    failures: list[str] = Field(default_factory=list)
