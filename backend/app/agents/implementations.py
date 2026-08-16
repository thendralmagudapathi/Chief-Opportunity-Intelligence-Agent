"""Specialised investigation agents."""

from __future__ import annotations

import uuid

from pydantic import BaseModel

from app.agents.base import BaseAgent
from app.agents.card import AgentCard
from app.agents.context import RunContext
from app.agents.llm.structured import structured_complete
from app.agents.prompts import load_prompt, render_prompt
from app.agents.schemas import (
    AgentDecision,
    ContrarianAnalysis,
    EligibilityAssessment,
    InvestigationPlan,
    ObjectiveUnderstanding,
    ProfileMatch,
    ResearchDossier,
    RiskAssessment,
    VerificationResult,
)
from app.models.enums import Recommendation


class _ObjectiveInput(BaseModel):
    objective: str


class SupervisorUnderstandAgent(BaseAgent[_ObjectiveInput, ObjectiveUnderstanding]):
    card = AgentCard(
        name="supervisor",
        version="1",
        description="Understand the user's objective.",
        capabilities=["understand"],
        cost_class="reasoning",
    )

    async def run(self, payload: _ObjectiveInput, ctx: RunContext) -> ObjectiveUnderstanding:
        template = load_prompt("supervisor", "understand")
        prompt = render_prompt(template, objective=payload.objective)
        return await structured_complete(
            ctx.llm,
            ObjectiveUnderstanding,
            prompt,
            task_class="reasoning",
            max_attempts=ctx.settings.agents.max_iterations,
        )


class _PlanInput(BaseModel):
    objective: str
    understanding: ObjectiveUnderstanding


class SupervisorPlanAgent(BaseAgent[_PlanInput, InvestigationPlan]):
    card = AgentCard(
        name="supervisor",
        version="1",
        description="Plan the investigation.",
        capabilities=["plan"],
        cost_class="reasoning",
        side_effects="none",
    )

    async def run(self, payload: _PlanInput, ctx: RunContext) -> InvestigationPlan:
        template = load_prompt("supervisor", "plan")
        prompt = render_prompt(
            template,
            objective=payload.objective,
            understanding=payload.understanding.model_dump_json(),
        )
        return await structured_complete(
            ctx.llm,
            InvestigationPlan,
            "Plan the investigation. Return InvestigationPlan JSON.\n" + prompt,
            task_class="reasoning",
        )


class _ResearchInput(BaseModel):
    title: str
    organization_name: str | None
    description: str | None


class ResearchAgent(BaseAgent[_ResearchInput, ResearchDossier]):
    card = AgentCard(
        name="research",
        version="1",
        description="Research an opportunity.",
        capabilities=["research"],
        cost_class="reasoning",
    )

    async def run(self, payload: _ResearchInput, ctx: RunContext) -> ResearchDossier:
        prompt = render_prompt(
            load_prompt("research", "dossier"),
            title=payload.title,
            organization=payload.organization_name or "Unknown",
            description=payload.description or "",
        )
        return await structured_complete(
            ctx.llm,
            ResearchDossier,
            "Research Agent\n" + prompt,
            task_class="reasoning",
        )


class _QualifyInput(BaseModel):
    title: str
    requirements: list[str]
    profile_summary: str


class QualificationAgent(BaseAgent[_QualifyInput, EligibilityAssessment]):
    card = AgentCard(
        name="qualification",
        version="1",
        description="Assess hard eligibility requirements.",
        capabilities=["qualify"],
        cost_class="standard",
    )

    async def run(self, payload: _QualifyInput, ctx: RunContext) -> EligibilityAssessment:
        prompt = render_prompt(
            load_prompt("qualification", "assess"),
            title=payload.title,
            requirements=", ".join(payload.requirements),
            profile=payload.profile_summary,
        )
        return await structured_complete(
            ctx.llm,
            EligibilityAssessment,
            "Qualification Agent\n" + prompt,
            task_class="standard",
        )


class _MatchInput(BaseModel):
    title: str
    required_skills: list[str]
    profile_passages: list[str]


class MatchingAgent(BaseAgent[_MatchInput, ProfileMatch]):
    card = AgentCard(
        name="matching",
        version="1",
        description="Match the opportunity to the profile.",
        capabilities=["match"],
        cost_class="standard",
    )

    async def run(self, payload: _MatchInput, ctx: RunContext) -> ProfileMatch:
        prompt = render_prompt(
            load_prompt("matching", "assess"),
            title=payload.title,
            required_skills=", ".join(payload.required_skills),
            profile="\n".join(payload.profile_passages),
        )
        return await structured_complete(
            ctx.llm,
            ProfileMatch,
            "Matching Agent\n" + prompt,
            task_class="standard",
        )


class _RiskInput(BaseModel):
    title: str
    dossier: ResearchDossier


class RiskAgent(BaseAgent[_RiskInput, RiskAssessment]):
    card = AgentCard(
        name="risk",
        version="1",
        description="Assess opportunity risks.",
        capabilities=["risk"],
        cost_class="standard",
    )

    async def run(self, payload: _RiskInput, ctx: RunContext) -> RiskAssessment:
        prompt = render_prompt(
            load_prompt("risk", "assess"),
            title=payload.title,
            dossier=payload.dossier.model_dump_json(),
        )
        return await structured_complete(
            ctx.llm,
            RiskAssessment,
            "Risk Agent\n" + prompt,
            task_class="standard",
        )


class _DecisionInput(BaseModel):
    opportunity_id: uuid.UUID
    title: str
    recommendation: Recommendation
    overall_score: float
    confidence: float
    eligibility: EligibilityAssessment
    risk: RiskAssessment


class DecisionAgent(BaseAgent[_DecisionInput, AgentDecision]):
    card = AgentCard(
        name="decision",
        version="1",
        description="Explain the recommendation.",
        capabilities=["decide"],
        cost_class="reasoning",
    )

    async def run(self, payload: _DecisionInput, ctx: RunContext) -> AgentDecision:
        prompt = render_prompt(
            load_prompt("decision", "decide"),
            title=payload.title,
            recommendation=payload.recommendation.value,
            score=f"{payload.overall_score:.1f}",
            confidence=f"{payload.confidence:.2f}",
            eligibility=payload.eligibility.model_dump_json(),
            risk=payload.risk.model_dump_json(),
        )
        narrative = await structured_complete(
            ctx.llm,
            _DecisionNarrative,
            "Decision Agent\n" + prompt,
            task_class="reasoning",
        )
        return AgentDecision(
            opportunity_id=payload.opportunity_id,
            recommendation=payload.recommendation,
            overall_score=payload.overall_score,
            confidence=payload.confidence,
            headline_reason=narrative.headline_reason,
            why_this=narrative.why_this,
            why_now=narrative.why_now,
            why_me=narrative.why_me,
            what_could_go_wrong=narrative.what_could_go_wrong,
        )


class _ContrarianInput(BaseModel):
    opportunity_id: uuid.UUID
    title: str
    recommendation: Recommendation
    overall_score: float
    confidence: float
    evaluation_summary: str


class ContrarianAgent(BaseAgent[_ContrarianInput, ContrarianAnalysis]):
    card = AgentCard(
        name="contrarian",
        version="1",
        description="Argue against the current recommendation.",
        capabilities=["contrarian"],
        cost_class="reasoning",
    )

    async def run(self, payload: _ContrarianInput, ctx: RunContext) -> ContrarianAnalysis:
        prompt = render_prompt(
            load_prompt("contrarian", "analyze"),
            title=payload.title,
            recommendation=payload.recommendation.value,
            score=f"{payload.overall_score:.1f}",
            confidence=f"{payload.confidence:.2f}",
            evaluation=payload.evaluation_summary,
        )
        result = await structured_complete(
            ctx.llm,
            ContrarianAnalysis,
            "Contrarian Agent\n" + prompt,
            task_class="reasoning",
        )
        return result.model_copy(update={"opportunity_id": payload.opportunity_id})


class _VerificationInput(BaseModel):
    opportunity_id: uuid.UUID
    title: str
    claims: list[str]


class VerificationAgent(BaseAgent[_VerificationInput, VerificationResult]):
    card = AgentCard(
        name="verification",
        version="1",
        description="Verify high-impact claims with calibrated confidence.",
        capabilities=["verify"],
        cost_class="reasoning",
    )

    async def run(self, payload: _VerificationInput, ctx: RunContext) -> VerificationResult:
        prompt = render_prompt(
            load_prompt("verification", "verify"),
            title=payload.title,
            claims="\n".join(f"- {claim}" for claim in payload.claims) or "- none",
        )
        result = await structured_complete(
            ctx.llm,
            VerificationResult,
            "Verification Agent\n" + prompt,
            task_class="reasoning",
        )
        return result.model_copy(update={"opportunity_id": payload.opportunity_id})


class _DecisionNarrative(BaseModel):
    headline_reason: str
    why_this: list[str] = []
    why_now: list[str] = []
    why_me: list[str] = []
    what_could_go_wrong: list[str] = []
