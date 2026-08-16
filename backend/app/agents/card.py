"""Agent identity and contract."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AgentCard(BaseModel):
    name: str
    version: str
    description: str
    capabilities: list[str] = Field(default_factory=list)
    cost_class: Literal["small", "standard", "reasoning"] = "standard"
    side_effects: Literal["none", "internal_write", "external"] = "none"
    max_attempts: int = Field(default=2, ge=1, le=5)
    timeout_s: float = Field(default=60.0, gt=0)
