"""A2A-compatible agent card endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.agents.card import AgentCard
from app.agents.registry import get_agent_card, list_agent_cards
from app.schemas.agent_card import AgentCardListResponse

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("", response_model=AgentCardListResponse, summary="List agent cards")
async def list_agents() -> AgentCardListResponse:
    return AgentCardListResponse(items=list_agent_cards())


@router.get("/{name}", response_model=AgentCard, summary="Get an agent card")
async def get_agent(name: str) -> AgentCard:
    card = get_agent_card(name)
    if card is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return card
