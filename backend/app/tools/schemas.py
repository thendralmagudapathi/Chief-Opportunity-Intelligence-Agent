"""Pydantic argument schemas for native tools."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field, HttpUrl

from app.models.enums import OpportunityCategory, OpportunityStatus


class SearchOpportunitiesArgs(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    goal_id: uuid.UUID | None = None
    category: OpportunityCategory | None = None
    limit: int = Field(default=20, ge=1, le=100)


class SearchWebArgs(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    url: HttpUrl | None = None


class ResearchCompanyArgs(BaseModel):
    company_name: str = Field(min_length=1, max_length=255)
    domain: str | None = Field(default=None, max_length=255)


class GetCompanyInformationArgs(BaseModel):
    opportunity_id: uuid.UUID


class ExtractDeadlineArgs(BaseModel):
    opportunity_id: uuid.UUID | None = None
    text: str | None = Field(default=None, max_length=5000)


class CheckEligibilityArgs(BaseModel):
    opportunity_id: uuid.UUID
    goal_id: uuid.UUID | None = None


class SearchUserProfileArgs(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    top_k: int = Field(default=8, ge=1, le=50)


class SearchUserDocumentsArgs(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    top_k: int = Field(default=8, ge=1, le=50)


class CalculateOpportunityScoreArgs(BaseModel):
    opportunity_id: uuid.UUID
    goal_id: uuid.UUID


class GetPreviousOpportunitiesArgs(BaseModel):
    limit: int = Field(default=20, ge=1, le=100)


class CreateFollowUpArgs(BaseModel):
    opportunity_id: uuid.UUID
    notes: str = Field(default="", max_length=4000)


class PrepareApplicationArgs(BaseModel):
    opportunity_id: uuid.UUID
    checklist: list[str] = Field(default_factory=list, max_length=50)


class GenerateOutreachArgs(BaseModel):
    opportunity_id: uuid.UUID
    channel: str = Field(default="email", max_length=64)
    tone: str = Field(default="professional", max_length=64)


class SaveOpportunityArgs(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    source_url: HttpUrl
    category: OpportunityCategory = OpportunityCategory.OTHER
    organization_name: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=10000)


class UpdateOpportunityStatusArgs(BaseModel):
    opportunity_id: uuid.UUID
    status: OpportunityStatus
    reason: str | None = Field(default=None, max_length=500)


class ToolSelectionCase(BaseModel):
    """Fixture for the tool-selection benchmark."""

    prompt: str
    expected_tool: str


class ToolArgumentCase(BaseModel):
    tool_name: str
    arguments: dict[str, Any]
    valid: bool
