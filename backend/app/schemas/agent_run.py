"""Agent run API schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import AgentRunStatus, AgentRunType, AgentTaskStatus
from app.schemas.common import ORMModel


class AgentTaskRead(ORMModel):
    id: uuid.UUID
    agent_name: str
    capability: str | None
    status: AgentTaskStatus
    attempt: int
    started_at: datetime | None
    finished_at: datetime | None
    latency_ms: int | None
    error: str | None


class AgentRunSummary(ORMModel):
    id: uuid.UUID
    trace_id: str
    run_type: AgentRunType
    status: AgentRunStatus
    objective_text: str | None
    degraded: bool
    started_at: datetime | None
    finished_at: datetime | None
    latency_ms: int | None
    cost_usd: Decimal
    created_at: datetime


class AgentRunRead(AgentRunSummary):
    goal_id: uuid.UUID | None
    graph_version: str | None
    iterations: int
    input_tokens: int
    output_tokens: int
    budget: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    result: dict[str, Any] | None = None
    tasks: list[AgentTaskRead] = Field(default_factory=list)


class AgentRunListResponse(BaseModel):
    items: list[AgentRunSummary]
