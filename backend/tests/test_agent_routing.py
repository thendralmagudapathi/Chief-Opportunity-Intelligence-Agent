"""Graph routing rules."""

from __future__ import annotations

from app.agents.routing import route_after_replan, route_after_triage, route_after_verify
from app.agents.state import InvestigationState


def test_triage_routes_to_report_when_empty() -> None:
    state: InvestigationState = {"candidates": []}
    assert route_after_triage(state) == "report"


def test_triage_routes_to_evaluate_when_candidates_exist() -> None:
    state: InvestigationState = {"candidates": [{"id": "1", "title": "Role"}]}
    assert route_after_triage(state) == "evaluate"


def test_verify_routes_to_replan_when_unresolved_and_budget_remaining() -> None:
    state: InvestigationState = {
        "unresolved_high_impact_claims": 2,
        "iterations": 0,
        "budget": {"max_iterations": 3, "remaining_usd": 1.0},
    }
    assert route_after_verify(state) == "replan"


def test_verify_routes_to_score_when_iteration_cap_reached() -> None:
    state: InvestigationState = {
        "unresolved_high_impact_claims": 2,
        "iterations": 3,
        "budget": {"max_iterations": 3, "remaining_usd": 1.0},
    }
    assert route_after_verify(state) == "score"


def test_replan_routes_to_discover_when_new_sources_needed() -> None:
    state: InvestigationState = {"plan": {"needs_new_sources": True}}
    assert route_after_replan(state) == "discover"


def test_replan_routes_to_evaluate_otherwise() -> None:
    state: InvestigationState = {"plan": {"needs_new_sources": False}}
    assert route_after_replan(state) == "evaluate"
