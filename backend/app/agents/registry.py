"""Registered agent cards for A2A discovery."""

from __future__ import annotations

from app.agents.card import AgentCard
from app.agents.implementations import (
    ContrarianAgent,
    DecisionAgent,
    MatchingAgent,
    QualificationAgent,
    ResearchAgent,
    RiskAgent,
    VerificationAgent,
)


def list_agent_cards() -> list[AgentCard]:
    return [
        AgentCard(
            name="supervisor",
            version="1",
            description="Understand objectives and plan investigations.",
            capabilities=["understand", "plan"],
            cost_class="reasoning",
        ),
        ResearchAgent.card,
        QualificationAgent.card,
        MatchingAgent.card,
        RiskAgent.card,
        VerificationAgent.card,
        ContrarianAgent.card,
        DecisionAgent.card,
    ]


def get_agent_card(name: str) -> AgentCard | None:
    for card in list_agent_cards():
        if card.name == name:
            return card
    return None
