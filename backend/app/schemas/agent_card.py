"""Agent card API payloads."""

from __future__ import annotations

from pydantic import BaseModel

from app.agents.card import AgentCard


class AgentCardListResponse(BaseModel):
    items: list[AgentCard]
