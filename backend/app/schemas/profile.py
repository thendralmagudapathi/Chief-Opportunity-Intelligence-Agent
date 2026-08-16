"""User profile payloads.

The JSONB sections of ``user_profiles`` are shapeless in the database and
strictly typed here, which is the trade we want: the schema can evolve without a
migration, but nothing unvalidated is ever written.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, StringConstraints

from app.schemas.common import ORMModel

CountryCode = Annotated[str, StringConstraints(min_length=2, max_length=2, to_upper=True)]
CurrencyCode = Annotated[str, StringConstraints(min_length=3, max_length=3, to_upper=True)]


class Skill(BaseModel):
    name: str = Field(max_length=120)
    level: int = Field(default=3, ge=1, le=5)
    years: float | None = Field(default=None, ge=0, le=60)
    evidence_document_id: uuid.UUID | None = None


class WorkAuthorization(BaseModel):
    country: CountryCode
    status: Literal["citizen", "permanent_resident", "work_visa", "student_visa", "none", "unknown"]
    expires_at: datetime | None = None
    requires_sponsorship: bool = False


class Education(BaseModel):
    institution: str = Field(max_length=255)
    degree: str | None = Field(default=None, max_length=255)
    field_of_study: str | None = Field(default=None, max_length=255)
    start_year: int | None = Field(default=None, ge=1900, le=2100)
    end_year: int | None = Field(default=None, ge=1900, le=2100)


class Certification(BaseModel):
    name: str = Field(max_length=255)
    issuer: str | None = Field(default=None, max_length=255)
    issued_at: datetime | None = None
    expires_at: datetime | None = None
    credential_url: str | None = Field(default=None, max_length=1024)


class Language(BaseModel):
    code: Annotated[str, StringConstraints(min_length=2, max_length=8)]
    proficiency: Literal["basic", "conversational", "professional", "fluent", "native"]


class ProfileBase(BaseModel):
    headline: str | None = Field(default=None, max_length=255)
    summary: str | None = Field(default=None, max_length=8000)
    location_country: CountryCode | None = None
    location_city: str | None = Field(default=None, max_length=120)
    timezone: str | None = Field(default=None, max_length=64)
    years_experience: Decimal | None = Field(default=None, ge=0, le=80)

    salary_expectation_min: Decimal | None = Field(default=None, ge=0)
    salary_expectation_max: Decimal | None = Field(default=None, ge=0)
    salary_currency: CurrencyCode | None = None

    skills: list[Skill] = Field(default_factory=list, max_length=200)
    work_authorization: list[WorkAuthorization] = Field(default_factory=list, max_length=20)
    education: list[Education] = Field(default_factory=list, max_length=30)
    certifications: list[Certification] = Field(default_factory=list, max_length=50)
    languages: list[Language] = Field(default_factory=list, max_length=20)
    interests: list[str] = Field(default_factory=list, max_length=50)
    preferences: dict[str, Any] = Field(default_factory=dict)
    constraints: dict[str, Any] = Field(default_factory=dict)


class ProfileUpdate(ProfileBase):
    """Full replacement (PUT)."""


class ProfilePatch(BaseModel):
    """Partial update (PATCH); unset fields are left untouched."""

    model_config = {"extra": "forbid"}

    headline: str | None = None
    summary: str | None = None
    location_country: CountryCode | None = None
    location_city: str | None = None
    timezone: str | None = None
    years_experience: Decimal | None = None
    salary_expectation_min: Decimal | None = None
    salary_expectation_max: Decimal | None = None
    salary_currency: CurrencyCode | None = None
    skills: list[Skill] | None = None
    work_authorization: list[WorkAuthorization] | None = None
    education: list[Education] | None = None
    certifications: list[Certification] | None = None
    languages: list[Language] | None = None
    interests: list[str] | None = None
    preferences: dict[str, Any] | None = None
    constraints: dict[str, Any] | None = None


class ProfileRead(ORMModel, ProfileBase):
    id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
