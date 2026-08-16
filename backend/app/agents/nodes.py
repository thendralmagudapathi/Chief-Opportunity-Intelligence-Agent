"""LangGraph node implementations."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select

from app.agents.context import RunContext
from app.agents.implementations import (
    DecisionAgent,
    MatchingAgent,
    QualificationAgent,
    ResearchAgent,
    RiskAgent,
    SupervisorPlanAgent,
    SupervisorUnderstandAgent,
    _DecisionInput,
    _MatchInput,
    _ObjectiveInput,
    _PlanInput,
    _QualifyInput,
    _ResearchInput,
    _RiskInput,
)
from app.agents.schemas import (
    AgentDecision,
    CandidateEvaluation,
    FinalOpportunityReport,
    InvestigationPlan,
    ObjectiveUnderstanding,
)
from app.agents.state import InvestigationState
from app.models.enums import AgentTaskStatus, Recommendation
from app.models.goal import Goal
from app.models.opportunity import Opportunity
from app.models.user import UserProfile
from app.services.agent_run_service import AgentRunService
from app.services.lifecycle import INACTIVE
from app.services.retrieval_service import build_retrieval_service
from app.services.scoring_service import ScoringService


def _event(stage: str, status: str, message: str, **counts: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"stage": stage, "status": status, "message": message}
    if counts:
        payload["counts"] = counts
    return payload


async def understand_node(state: InvestigationState, ctx: RunContext) -> dict[str, Any]:
    runs = AgentRunService(ctx.session)
    task = await runs.start_task(ctx.run_id, agent_name="supervisor", capability="understand")
    ctx.emit("stage", _event("understand", "running", "Understanding objective"))
    understanding = await SupervisorUnderstandAgent().run(
        _ObjectiveInput(objective=state["objective"]), ctx
    )
    await runs.finish_task(
        task.id,
        status=AgentTaskStatus.SUCCEEDED,
        output=understanding.model_dump(mode="json"),
    )
    ctx.emit("stage", _event("understand", "done", "Objective understood"))
    return {
        "understanding": understanding.model_dump(),
        "events": [_event("understand", "done", "Objective understood")],
    }


async def load_context_node(state: InvestigationState, ctx: RunContext) -> dict[str, Any]:
    ctx.emit("stage", _event("load_context", "running", "Loading profile context"))
    if ctx.tools is not None and ctx.tool_ctx is not None:
        outcome = await ctx.tools.invoke(
            "search_user_profile",
            {"query": state["objective"], "top_k": ctx.settings.rag.rerank_top_n},
            ctx.tool_ctx,
        )
        if not outcome.ok or outcome.data is None:
            return {
                "profile_context": [],
                "degraded": True,
                "errors": [outcome.error or "Profile search failed"],
                "events": [_event("load_context", "failed", "Profile search failed")],
            }
        passages = outcome.data.get("passages", [])
    else:
        retrieval = build_retrieval_service(ctx.session, ctx.settings)
        result = await retrieval.search_profile(
            user_id=ctx.user_id, query=state["objective"], rerank=True
        )
        passages = [
            {"content": passage.content, "score": passage.score, "channel": passage.channel}
            for passage in result.passages
        ]
        degraded = result.degraded
        ctx.emit(
            "stage",
            _event("load_context", "done", "Profile context loaded", passages=len(passages)),
        )
        return {
            "profile_context": passages,
            "degraded": degraded,
            "events": [_event("load_context", "done", f"Loaded {len(passages)} passages")],
        }
    ctx.emit(
        "stage",
        _event("load_context", "done", "Profile context loaded", passages=len(passages)),
    )
    return {
        "profile_context": passages,
        "degraded": bool(outcome.data.get("degraded")),
        "events": [_event("load_context", "done", f"Loaded {len(passages)} passages")],
    }


async def plan_node(state: InvestigationState, ctx: RunContext) -> dict[str, Any]:
    runs = AgentRunService(ctx.session)
    task = await runs.start_task(ctx.run_id, agent_name="supervisor", capability="plan")
    ctx.emit("stage", _event("plan", "running", "Planning investigation"))
    understanding = ObjectiveUnderstanding.model_validate(state.get("understanding", {}))
    plan = await SupervisorPlanAgent().run(
        _PlanInput(objective=state["objective"], understanding=understanding),
        ctx,
    )
    await runs.finish_task(
        task.id,
        status=AgentTaskStatus.SUCCEEDED,
        output=plan.model_dump(mode="json"),
    )
    ctx.emit("stage", _event("plan", "done", plan.summary))
    return {"plan": plan.model_dump(), "events": [_event("plan", "done", plan.summary)]}


async def discover_node(state: InvestigationState, ctx: RunContext) -> dict[str, Any]:
    ctx.emit("stage", _event("discover", "running", "Discovering candidates"))
    plan = InvestigationPlan.model_validate(state.get("plan", {}))
    stmt = select(Opportunity).where(Opportunity.status.not_in(INACTIVE))
    focus_ids = state.get("focus_opportunity_ids") or []
    if focus_ids:
        stmt = stmt.where(Opportunity.id.in_([uuid.UUID(value) for value in focus_ids]))
    rows = list(
        (
            await ctx.session.execute(stmt.order_by(Opportunity.created_at.desc()).limit(100))
        ).scalars()
    )

    keywords = [
        token
        for token in state["objective"].casefold().split()
        if len(token) > 3 and token not in {"that", "with", "from", "have", "your"}
    ]
    filtered: list[Opportunity] = []
    for row in rows:
        haystack = " ".join(
            filter(
                None,
                [
                    row.title,
                    row.organization_name,
                    row.summary,
                    row.description,
                    row.location_country,
                ],
            )
        ).casefold()
        if not keywords or any(token in haystack for token in keywords):
            filtered.append(row)
    if not filtered:
        filtered = rows

    candidates = [
        {
            "id": str(row.id),
            "title": row.title,
            "organization_name": row.organization_name,
            "description": row.description,
            "required_skills": row.required_skills or [],
            "requirements": row.requirements or [],
        }
        for row in filtered[: plan.max_candidates]
    ]
    ctx.emit(
        "stage",
        _event(
            "discover",
            "done",
            f"Found {len(candidates)} candidates",
            before=len(rows),
            after=len(candidates),
        ),
    )
    return {
        "candidates": candidates,
        "events": [_event("discover", "done", f"{len(candidates)} candidates")],
    }


async def triage_node(state: InvestigationState, ctx: RunContext) -> dict[str, Any]:
    count = len(state.get("candidates", []))
    ctx.emit("stage", _event("triage", "done", f"{count} candidates retained"))
    return {"events": [_event("triage", "done", f"{count} retained")]}


async def evaluate_node(state: InvestigationState, ctx: RunContext) -> dict[str, Any]:
    ctx.emit("stage", _event("evaluate", "running", "Evaluating candidates"))
    profile = await _profile_for(ctx)
    profile_summary = _profile_summary(profile)
    passages = [item["content"] for item in state.get("profile_context", [])]
    evaluations: dict[str, Any] = {}

    research = ResearchAgent()
    qualify = QualificationAgent()
    match = MatchingAgent()
    risk = RiskAgent()

    for candidate in state.get("candidates", []):
        opp_id = uuid.UUID(candidate["id"])
        dossier = await research.run(
            _ResearchInput(
                title=candidate["title"],
                organization_name=candidate.get("organization_name"),
                description=candidate.get("description"),
            ),
            ctx,
        )
        eligibility = await qualify.run(
            _QualifyInput(
                title=candidate["title"],
                requirements=[str(item) for item in candidate.get("requirements", [])],
                profile_summary=profile_summary,
            ),
            ctx,
        )
        matching = await match.run(
            _MatchInput(
                title=candidate["title"],
                required_skills=[str(item) for item in candidate.get("required_skills", [])],
                profile_passages=passages,
            ),
            ctx,
        )
        risk_view = await risk.run(_RiskInput(title=candidate["title"], dossier=dossier), ctx)
        evaluations[str(opp_id)] = CandidateEvaluation(
            opportunity_id=opp_id,
            dossier=dossier,
            eligibility=eligibility,
            match=matching,
            risk=risk_view,
        ).model_dump()

    ctx.emit("stage", _event("evaluate", "done", f"Evaluated {len(evaluations)} candidates"))
    return {
        "evaluations": evaluations,
        "events": [_event("evaluate", "done", f"{len(evaluations)} evaluated")],
    }


async def score_node(state: InvestigationState, ctx: RunContext) -> dict[str, Any]:
    ctx.emit("stage", _event("score", "running", "Scoring candidates"))
    goal = await ctx.session.get(Goal, uuid.UUID(state["goal_id"]))
    if goal is None:
        return {"errors": ["Goal not found"], "scores": {}}
    scores: dict[str, Any] = {}
    for candidate in state.get("candidates", []):
        opp_id = uuid.UUID(candidate["id"])
        if ctx.tools is not None and ctx.tool_ctx is not None:
            outcome = await ctx.tools.invoke(
                "calculate_opportunity_score",
                {"opportunity_id": str(opp_id), "goal_id": state["goal_id"]},
                ctx.tool_ctx,
            )
            if outcome.ok and outcome.data is not None:
                scores[str(opp_id)] = {
                    "overall_score": outcome.data["overall_score"],
                    "confidence": outcome.data["confidence"],
                    "recommendation": outcome.data["recommendation"]
                    or Recommendation.CONSIDER.value,
                }
            continue
        opportunity = await ctx.session.get(Opportunity, opp_id)
        if opportunity is None:
            continue
        profile = await _profile_for(ctx)
        scoring = ScoringService(ctx.session)
        row = await scoring.score_opportunity(opportunity, goal, profile=profile)
        scores[str(opportunity.id)] = {
            "overall_score": float(row.overall_score),
            "confidence": float(row.confidence or 0),
            "recommendation": (
                row.recommendation.value if row.recommendation else Recommendation.CONSIDER.value
            ),
        }
    ctx.emit("stage", _event("score", "done", f"Scored {len(scores)} opportunities"))
    return {"scores": scores, "events": [_event("score", "done", f"{len(scores)} scored")]}


async def decide_node(state: InvestigationState, ctx: RunContext) -> dict[str, Any]:
    ctx.emit("stage", _event("decide", "running", "Deciding recommendations"))
    decision_agent = DecisionAgent()
    decisions: list[dict[str, Any]] = []
    from app.agents.schemas import EligibilityAssessment, RiskAssessment

    ranked = sorted(
        state.get("scores", {}).items(),
        key=lambda item: item[1]["overall_score"],
        reverse=True,
    )
    for opp_id, score in ranked[:5]:
        evaluation = state.get("evaluations", {}).get(opp_id, {})
        candidate = next((c for c in state.get("candidates", []) if c["id"] == opp_id), None)
        if candidate is None:
            continue
        eligibility = EligibilityAssessment.model_validate(
            evaluation.get("eligibility", {"verdict": "unknown", "requirements": []})
        )
        risk = RiskAssessment.model_validate(evaluation.get("risk", {"findings": []}))
        recommendation = Recommendation(score["recommendation"])
        if eligibility.verdict == "ineligible":
            recommendation = Recommendation.INELIGIBLE
        decision = await decision_agent.run(
            _DecisionInput(
                opportunity_id=uuid.UUID(opp_id),
                title=candidate["title"],
                recommendation=recommendation,
                overall_score=score["overall_score"],
                confidence=score["confidence"],
                eligibility=eligibility,
                risk=risk,
            ),
            ctx,
        )
        payload = decision.model_dump(mode="json")
        decisions.append(payload)

    ctx.emit("stage", _event("decide", "done", f"{len(decisions)} recommendations"))
    return {
        "decisions": decisions,
        "events": [_event("decide", "done", f"{len(decisions)} recommendations")],
    }


async def report_node(state: InvestigationState, ctx: RunContext) -> dict[str, Any]:
    recommendations = [AgentDecision.model_validate(item) for item in state.get("decisions", [])]
    report = FinalOpportunityReport(
        objective=state["objective"],
        degraded=bool(state.get("degraded")),
        iterations=int(state.get("iterations", 0)),
        recommendations=recommendations,
        partial_results=bool(state.get("errors")),
    )
    ctx.emit("stage", _event("report", "done", "Investigation complete"))
    return {
        "report": report.model_dump(mode="json"),
        "events": [_event("report", "done", "Investigation complete")],
    }


async def replan_node(state: InvestigationState, ctx: RunContext) -> dict[str, Any]:
    iterations = int(state.get("iterations", 0)) + 1
    plan = dict(state.get("plan", {}))
    plan["needs_new_sources"] = iterations % 2 == 1
    ctx.emit("stage", _event("replan", "running", f"Replanning iteration {iterations}"))
    return {
        "iterations": iterations,
        "plan": plan,
        "unresolved_high_impact_claims": 0,
        "events": [_event("replan", "done", f"Iteration {iterations}")],
    }


async def verify_node(state: InvestigationState, ctx: RunContext) -> dict[str, Any]:
    unresolved = 1 if state.get("iterations", 0) == 0 and state.get("candidates") else 0
    ctx.emit("stage", _event("verify", "done", "Verification complete"))
    return {
        "unresolved_high_impact_claims": unresolved,
        "events": [_event("verify", "done", "Verification complete")],
    }


async def _profile_for(ctx: RunContext) -> UserProfile | None:
    result = await ctx.session.execute(
        select(UserProfile).where(UserProfile.user_id == ctx.user_id)
    )
    return result.scalar_one_or_none()


def _profile_summary(profile: UserProfile | None) -> str:
    if profile is None:
        return ""
    return "\n".join(part for part in (profile.headline or "", profile.summary or "") if part)
