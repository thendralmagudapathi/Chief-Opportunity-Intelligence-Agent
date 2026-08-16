"""Shared tool metadata types."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class SideEffect(StrEnum):
    NONE = "none"
    INTERNAL_WRITE = "internal_write"
    EXTERNAL = "external"


class ToolSpec(BaseModel):
    """Advertised metadata for a registered tool."""

    name: str
    description: str
    permission_scope: str
    side_effects: SideEffect
    timeout_s: float = Field(gt=0)
    max_calls_per_run: int = Field(ge=1)
    max_retries: int = Field(default=0, ge=0, le=5)
    cost_usd: float = Field(default=0.0, ge=0.0)
    input_schema: dict[str, Any]


class ToolOutcome(BaseModel):
    """Normalised result returned to agents and MCP callers."""

    ok: bool
    data: dict[str, Any] | None = None
    error: str | None = None
    error_code: Literal[
        "invalid_arguments",
        "permission_denied",
        "budget_exhausted",
        "rate_limited",
        "timeout",
        "not_found",
        "validation_error",
        "dependency_unavailable",
        "internal_error",
    ] | None = None
