"""Investigation graph schemas."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models.enums import ClaimType, Recommendation


class ObjectiveUnderstanding(BaseModel):
    intent: str
    focus_countries: list[str] = Field(default_factory=list)
    focus_categories: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    success_criteria: str


class InvestigationPlan(BaseModel):
    summary: str
    max_candidates: int = Field(default=5, ge=1, le=20)
    research_depth: Literal["light", "standard", "deep"] = "standard"
    sources: list[str] = Field(default_factory=lambda: ["index"])
    stop_when: str = "top candidates scored"


class OpportunityRef(BaseModel):
    id: uuid.UUID
    title: str
    organization_name: str | None = None


class ResearchDossier(BaseModel):
    organization_summary: str
    market_context: str
    key_claims: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)


class RequirementAssessment(BaseModel):
    name: str
    state: Literal["met", "not_met", "unknown"]
    evidence: str | None = None


class EligibilityAssessment(BaseModel):
    verdict: Literal["eligible", "ineligible", "unknown"]
    requirements: list[RequirementAssessment] = Field(default_factory=list)


class ProfileMatch(BaseModel):
    matched_skills: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    transferable: list[str] = Field(default_factory=list)
    seniority_delta: str = "unknown"
    rationale: str


class RiskFinding(BaseModel):
    severity: Literal["low", "medium", "high", "critical"]
    kind: str
    detail: str


class RiskAssessment(BaseModel):
    findings: list[RiskFinding] = Field(default_factory=list)


class CandidateEvaluation(BaseModel):
    opportunity_id: uuid.UUID
    dossier: ResearchDossier
    eligibility: EligibilityAssessment
    match: ProfileMatch
    risk: RiskAssessment


class VerifiedClaim(BaseModel):
    claim: str
    claim_type: ClaimType
    confidence: float = Field(ge=0.0, le=1.0)
    supporting_sources: list[str] = Field(default_factory=list)
    contradicting_sources: list[str] = Field(default_factory=list)
    unresolved: bool = False


class VerificationResult(BaseModel):
    opportunity_id: uuid.UUID
    claims: list[VerifiedClaim] = Field(default_factory=list)
    unresolved_high_impact_count: int = Field(default=0, ge=0)
    overall_confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class ContrarianAnalysis(BaseModel):
    opportunity_id: uuid.UUID
    contradicting_evidence: list[str] = Field(default_factory=list)
    weak_assumptions: list[str] = Field(default_factory=list)
    failure_modes: list[str] = Field(default_factory=list)
    opportunity_cost: str = ""
    verdict_pressure: float = Field(default=0.0, ge=0.0, le=1.0)


class AgentDecision(BaseModel):
    opportunity_id: uuid.UUID
    recommendation: Recommendation
    overall_score: float
    confidence: float
    headline_reason: str
    why_this: list[str] = Field(default_factory=list)
    why_now: list[str] = Field(default_factory=list)
    why_me: list[str] = Field(default_factory=list)
    what_could_go_wrong: list[str] = Field(default_factory=list)


class FinalOpportunityReport(BaseModel):
    objective: str
    degraded: bool = False
    iterations: int = 0
    recommendations: list[AgentDecision] = Field(default_factory=list)
    counterpoints: list[ContrarianAnalysis] = Field(default_factory=list)
    partial_results: bool = False
    detail: str | None = None


class InvestigationRequest(BaseModel):
    objective: str = Field(min_length=8, max_length=4000)
    goal_id: uuid.UUID
    opportunity_ids: list[uuid.UUID] | None = None


class InvestigationStartResponse(BaseModel):
    run_id: uuid.UUID
    trace_id: str
    stream_url: str
    dispatch_mode: str = "background"


class GraphEvent(BaseModel):
    stage: str
    status: Literal["running", "done", "failed"]
    message: str
    counts: dict[str, Any] = Field(default_factory=dict)
