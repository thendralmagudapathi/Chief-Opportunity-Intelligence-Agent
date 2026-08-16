"""Opportunity payloads.

The read shapes are frozen now (they are the frontend contract) even though the
agent-produced fields stay empty until later phases. Freezing them early is
deliberate: the UI and the evaluation harness both code against this shape.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import (
    CompensationPeriod,
    ObjectiveProfile,
    OpportunityCategory,
    OpportunityStatus,
    Recommendation,
    RemoteStatus,
)
from app.schemas.common import ORMModel


class Compensation(BaseModel):
    min: Decimal | None = None
    max: Decimal | None = None
    currency: str | None = None
    period: CompensationPeriod | None = None


class Freshness(BaseModel):
    discovered_at: datetime | None = None
    last_verified_at: datetime | None = None
    expires_at: datetime | None = None
    score: float | None = None


class ScoreDimensions(BaseModel):
    """All dimensions normalised to [0, 1]; ``None`` means genuinely unknown."""

    fit_score: Decimal | None = None
    value_score: Decimal | None = None
    probability_of_success: Decimal | None = None
    strategic_value: Decimal | None = None
    time_sensitivity: Decimal | None = None
    effort_score: Decimal | None = None
    risk_score: Decimal | None = None
    learning_value: Decimal | None = None
    network_value: Decimal | None = None
    long_term_value: Decimal | None = None


class ScoreRead(BaseModel):
    overall_score: Decimal
    confidence: Decimal | None = None
    scoring_profile: ObjectiveProfile
    weights_version: str
    engine_version: str
    goal_id: uuid.UUID | None = None
    dimensions: ScoreDimensions = Field(default_factory=ScoreDimensions)
    computed_at: datetime | None = None


class EvidenceRead(ORMModel):
    id: uuid.UUID
    claim: str
    claim_type: str
    stance: str
    source_url: str | None
    source_title: str | None
    retrieved_at: datetime | None
    confidence: Decimal | None


class OpportunityListItem(ORMModel):
    id: uuid.UUID
    title: str
    category: OpportunityCategory
    subcategory: str | None
    organization_name: str | None
    location_country: str | None
    location_city: str | None
    remote_status: RemoteStatus
    deadline: datetime | None
    discovered_at: datetime | None
    freshness_score: float | None
    status: OpportunityStatus
    source_url: str
    summary: str | None
    overall_score: Decimal | None = None
    recommendation: Recommendation | None = None


class OpportunityRead(ORMModel):
    id: uuid.UUID
    title: str
    category: OpportunityCategory
    subcategory: str | None
    organization_name: str | None
    organization_domain: str | None
    description: str | None
    summary: str | None
    language: str | None
    source_url: str
    canonical_url: str | None
    location_country: str | None
    location_city: str | None
    remote_status: RemoteStatus
    requirements: list[Any]
    eligibility: dict[str, Any]
    required_skills: list[Any]
    preferred_skills: list[Any]
    posted_at: datetime | None
    deadline: datetime | None
    status: OpportunityStatus

    compensation: Compensation = Field(default_factory=Compensation)
    freshness: Freshness = Field(default_factory=Freshness)
    score: ScoreRead | None = None
    evidence: list[EvidenceRead] = Field(default_factory=list)


class OpportunityFilters(BaseModel):
    """Query parameters for the list endpoint."""

    category: OpportunityCategory | None = None
    status: OpportunityStatus | None = None
    country: str | None = Field(default=None, min_length=2, max_length=2)
    remote_status: RemoteStatus | None = None
    goal_id: uuid.UUID | None = None
    min_score: Decimal | None = Field(default=None, ge=0, le=100)
    deadline_before: datetime | None = None
    q: str | None = Field(default=None, max_length=200)
    include_expired: bool = False
