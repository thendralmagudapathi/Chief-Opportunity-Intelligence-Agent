"""Fine-tuning API schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ExtractionMetricsRead(BaseModel):
    classification_accuracy: float
    deadline_accuracy: float
    requirement_f1: float
    macro_average: float


class ModeScoreRead(BaseModel):
    mode: str
    metrics: ExtractionMetricsRead


class ComparisonRead(BaseModel):
    winner: str
    lift: float
    noise_band: float
    verdict: str
    notes: str
    scores: list[ModeScoreRead]


class ModelPromotionRead(BaseModel):
    registry_name: str
    model_version: str
    active_model: str
    rollback_model: str


class ModelRollbackRead(BaseModel):
    registry_name: str
    restored_model: str


class FineTuningCompareRequest(BaseModel):
    dataset_limit: int = Field(default=20, ge=1, le=50)


class FineTuningPromoteRequest(BaseModel):
    model_uri: str = Field(min_length=1, max_length=512)
    version: str = Field(min_length=1, max_length=64)
