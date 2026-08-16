"""Structured extraction output for opportunity normalization."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from app.models.enums import OpportunityCategory, RemoteStatus


class OpportunityExtraction(BaseModel):
    """LLM extraction target — maps to :class:`RawOpportunity` after validation."""

    title: str = Field(min_length=1, max_length=512)
    organization_name: str | None = Field(default=None, max_length=255)
    category: OpportunityCategory = OpportunityCategory.OTHER
    summary: str | None = Field(default=None, max_length=2000)
    location_country: str | None = Field(default=None, max_length=2)
    location_city: str | None = Field(default=None, max_length=128)
    remote_status: RemoteStatus = RemoteStatus.UNKNOWN
    deadline: date | None = None
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    requirements: list[str] = Field(default_factory=list)
    compensation_min: int | None = None
    compensation_max: int | None = None
    compensation_currency: str | None = Field(default=None, max_length=8)
    compensation_period: str | None = Field(default=None, max_length=16)
