"""LangGraph assembly for investigations."""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from app.agents.context import RunContext
from app.agents.nodes import (
    contrarian_node,
    decide_node,
    discover_node,
    evaluate_node,
    load_context_node,
    plan_node,
    replan_node,
    report_node,
    score_node,
    triage_node,
    understand_node,
    verify_node,
)
from app.agents.routing import route_after_replan, route_after_triage, route_after_verify
from app.agents.state import InvestigationState


def build_investigation_graph(ctx: RunContext) -> Any:
    graph: StateGraph[InvestigationState] = StateGraph(InvestigationState)

    async def understand(state: InvestigationState) -> dict[str, Any]:
        return await understand_node(state, ctx)

    async def load_context(state: InvestigationState) -> dict[str, Any]:
        return await load_context_node(state, ctx)

    async def plan(state: InvestigationState) -> dict[str, Any]:
        return await plan_node(state, ctx)

    async def discover(state: InvestigationState) -> dict[str, Any]:
        return await discover_node(state, ctx)

    async def triage(state: InvestigationState) -> dict[str, Any]:
        return await triage_node(state, ctx)

    async def evaluate(state: InvestigationState) -> dict[str, Any]:
        return await evaluate_node(state, ctx)

    async def verify(state: InvestigationState) -> dict[str, Any]:
        return await verify_node(state, ctx)

    async def replan(state: InvestigationState) -> dict[str, Any]:
        return await replan_node(state, ctx)

    async def score(state: InvestigationState) -> dict[str, Any]:
        return await score_node(state, ctx)

    async def contrarian(state: InvestigationState) -> dict[str, Any]:
        return await contrarian_node(state, ctx)

    async def decide(state: InvestigationState) -> dict[str, Any]:
        return await decide_node(state, ctx)

    async def report(state: InvestigationState) -> dict[str, Any]:
        return await report_node(state, ctx)

    graph.add_node("understand", understand)
    graph.add_node("load_context", load_context)
    graph.add_node("plan", plan)
    graph.add_node("discover", discover)
    graph.add_node("triage", triage)
    graph.add_node("evaluate", evaluate)
    graph.add_node("verify", verify)
    graph.add_node("replan", replan)
    graph.add_node("score", score)
    graph.add_node("contrarian", contrarian)
    graph.add_node("decide", decide)
    graph.add_node("report", report)

    graph.set_entry_point("understand")
    graph.add_edge("understand", "load_context")
    graph.add_edge("load_context", "plan")
    graph.add_edge("plan", "discover")
    graph.add_edge("discover", "triage")
    graph.add_conditional_edges(
        "triage",
        route_after_triage,
        {"evaluate": "evaluate", "report": "report"},
    )
    graph.add_edge("evaluate", "verify")
    graph.add_conditional_edges(
        "verify",
        route_after_verify,
        {"replan": "replan", "score": "score"},
    )
    graph.add_conditional_edges(
        "replan",
        route_after_replan,
        {"discover": "discover", "evaluate": "evaluate"},
    )
    graph.add_edge("score", "contrarian")
    graph.add_edge("contrarian", "decide")
    graph.add_edge("decide", "report")
    graph.add_edge("report", END)

    return graph.compile(checkpointer=MemorySaver())
