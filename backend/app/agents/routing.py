"""Pure routing functions over investigation state."""

from __future__ import annotations

from typing import Literal

from app.agents.state import InvestigationState


def route_after_triage(state: InvestigationState) -> Literal["evaluate", "report"]:
    return "evaluate" if state.get("candidates") else "report"


def route_after_verify(state: InvestigationState) -> Literal["replan", "score"]:
    budget = state.get("budget", {})
    iterations = int(state.get("iterations", 0))
    max_iterations = int(budget.get("max_iterations", 3))
    unresolved = int(state.get("unresolved_high_impact_claims", 0))
    remaining = float(budget.get("remaining_usd", 0.0))

    if unresolved > 0 and iterations < max_iterations and remaining > 0:
        return "replan"
    return "score"


def route_after_replan(state: InvestigationState) -> Literal["discover", "evaluate"]:
    plan = state.get("plan") or {}
    if plan.get("needs_new_sources"):
        return "discover"
    return "evaluate"
