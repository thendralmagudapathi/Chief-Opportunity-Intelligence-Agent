"""LangGraph investigation state."""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class InvestigationState(TypedDict, total=False):
    run_id: str
    trace_id: str
    user_id: str
    goal_id: str
    objective: str
    understanding: dict[str, Any]
    plan: dict[str, Any]
    profile_context: list[dict[str, Any]]
    memory_context: list[dict[str, Any]]
    expanded_queries: list[str]
    candidates: list[dict[str, Any]]
    evaluations: dict[str, dict[str, Any]]
    verifications: dict[str, dict[str, Any]]
    counterpoints: dict[str, dict[str, Any]]
    scores: dict[str, dict[str, Any]]
    decisions: list[dict[str, Any]]
    report: dict[str, Any]
    focus_opportunity_ids: list[str]
    iterations: int
    unresolved_high_impact_claims: int
    budget: dict[str, Any]
    degraded: bool
    errors: Annotated[list[str], operator.add]
    events: Annotated[list[dict[str, Any]], operator.add]
