"""Status state machine."""

from __future__ import annotations

import pytest
from app.core.errors import ValidationError
from app.models.enums import OpportunityEventType, OpportunityStatus
from app.services.lifecycle import can_transition, transition


def test_discovered_can_skip_straight_to_scored() -> None:
    """Phase 2 scores a freshly ingested row without an enrichment pass."""
    event = transition(OpportunityStatus.DISCOVERED, OpportunityStatus.SCORED)
    assert event is not None
    assert event.event_type is OpportunityEventType.SCORED
    assert event.payload["from"] == "discovered"
    assert event.payload["to"] == "scored"


def test_recommendation_can_be_withdrawn() -> None:
    event = transition(OpportunityStatus.RECOMMENDED, OpportunityStatus.SCORED, reason="re-score")
    assert event is not None
    assert event.payload["reason"] == "re-score"


def test_archived_is_terminal() -> None:
    assert can_transition(OpportunityStatus.ARCHIVED, OpportunityStatus.SCORED) is False
    with pytest.raises(ValidationError):
        transition(OpportunityStatus.ARCHIVED, OpportunityStatus.DISCOVERED)


def test_idempotent_no_op_produces_no_event() -> None:
    assert transition(OpportunityStatus.SCORED, OpportunityStatus.SCORED) is None


def test_cannot_move_backwards_to_discovered() -> None:
    with pytest.raises(ValidationError):
        transition(OpportunityStatus.SCORED, OpportunityStatus.DISCOVERED)
