"""Shared response envelopes."""

from __future__ import annotations

from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ORMModel(BaseModel):
    """Base for models read directly from ORM instances."""

    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    """Keyset pagination envelope.

    Offset pagination drifts when rows are inserted between requests, which is
    the normal case here — discovery inserts continuously.
    """

    items: list[T]
    next_cursor: str | None = None
    has_more: bool = False
    total: int | None = Field(
        default=None, description="Only populated when a count was cheap to obtain"
    )


class HealthCheck(BaseModel):
    name: str
    status: Literal["ok", "degraded", "error"]
    latency_ms: float | None = None
    detail: str | None = None


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "error"]
    checks: list[HealthCheck] = Field(default_factory=list)


class ServiceInfo(BaseModel):
    name: str
    version: str
    environment: str
    git_sha: str


class MessageResponse(BaseModel):
    message: str
