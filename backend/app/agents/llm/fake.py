"""Deterministic LLM for tests and offline runs."""

from __future__ import annotations

import json
import re
from typing import Any

from app.agents.llm.protocols import LLMResponse, TaskClass

_JSON_BLOCK = re.compile(r"\{[\s\S]*\}")


class FakeLLMProvider:
    """Returns schema-valid JSON based on prompt markers."""

    def __init__(self, *, model_name: str = "fake-llm") -> None:
        self._model_name = model_name
        self.calls: list[str] = []

    async def complete(
        self,
        prompt: str,
        *,
        task_class: TaskClass = "standard",
        system: str | None = None,
    ) -> LLMResponse:
        del system
        self.calls.append(prompt)
        payload = _response_for_prompt(prompt, task_class=task_class)
        return LLMResponse(
            content=json.dumps(payload),
            model=self._model_name,
            input_tokens=max(1, len(prompt) // 4),
            output_tokens=max(1, len(json.dumps(payload)) // 4),
        )


def _response_for_prompt(prompt: str, *, task_class: TaskClass) -> dict[str, Any]:
    lowered = prompt.casefold()
    if "investigationplan" in lowered or "plan the investigation" in lowered:
        return {
            "summary": "Investigate indexed opportunities against the active goal.",
            "max_candidates": 5,
            "research_depth": "standard",
            "sources": ["index"],
            "stop_when": "top candidates scored and ranked",
        }
    if "objectiverequest" in lowered or "understand the objective" in lowered:
        return {
            "intent": "discover_and_rank",
            "focus_countries": ["DE"],
            "focus_categories": ["job"],
            "keywords": ["ai", "engineering"],
            "success_criteria": "realistic high-value matches",
        }
    if "researchdossier" in lowered or "research agent" in lowered:
        return {
            "organization_summary": "Credible organization with public presence.",
            "market_context": "Competitive but active hiring market.",
            "key_claims": ["Role aligns with stated requirements."],
            "open_questions": [],
        }
    if "eligibilityassessment" in lowered or "qualification agent" in lowered:
        return {
            "verdict": "eligible",
            "requirements": [
                {"name": "Relevant experience", "state": "met", "evidence": "Profile skills match."}
            ],
        }
    if "profilematch" in lowered or "matching agent" in lowered:
        return {
            "matched_skills": ["Python", "PyTorch"],
            "gaps": [],
            "transferable": ["FastAPI"],
            "seniority_delta": "aligned",
            "rationale": "Strong overlap with required stack.",
        }
    if "riskassessment" in lowered or "risk agent" in lowered:
        return {
            "findings": [
                {
                    "severity": "low",
                    "kind": "competition",
                    "detail": "Popular role with many applicants.",
                }
            ]
        }
    if "agentdecision" in lowered or "decision agent" in lowered:
        return {
            "headline_reason": "Strong fit and favourable score.",
            "why_this": ["Matches objective and profile."],
            "why_now": ["Active posting with future deadline."],
            "why_me": ["Skills align with requirements."],
            "what_could_go_wrong": ["Competition may be high."],
        }
    if "contrariananalysis" in lowered or "contrarian agent" in lowered:
        return {
            "opportunity_id": "00000000-0000-0000-0000-000000000001",
            "contradicting_evidence": ["Competition is intense for this role."],
            "weak_assumptions": ["Assumes remote work is available."],
            "failure_modes": ["Application may be deprioritised against senior hires."],
            "opportunity_cost": "Time spent here may displace stronger matches.",
            "verdict_pressure": 0.62,
        }
    if "verificationresult" in lowered or "verification agent" in lowered:
        return {
            "opportunity_id": "00000000-0000-0000-0000-000000000001",
            "claims": [
                {
                    "claim": "Role aligns with stated requirements.",
                    "claim_type": "INFERENCE",
                    "confidence": 0.72,
                    "supporting_sources": ["profile overlap"],
                    "contradicting_sources": [],
                    "unresolved": False,
                }
            ],
            "unresolved_high_impact_count": 0,
            "overall_confidence": 0.72,
        }
    if task_class == "extract":
        return {"title": "Extracted title", "organization_name": "Example GmbH"}
    return {"message": "acknowledged"}
