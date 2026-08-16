"""Structured output repair behaviour."""

from __future__ import annotations

from app.agents.llm.fake import FakeLLMProvider
from app.agents.llm.structured import structured_complete
from pydantic import BaseModel, Field


class SamplePlan(BaseModel):
    summary: str
    max_candidates: int = Field(ge=1)


class BrokenLLM:
    def __init__(self) -> None:
        self.attempts = 0

    async def complete(
        self, prompt: str, *, task_class: str = "standard", system: str | None = None
    ):
        del prompt, task_class, system
        self.attempts += 1
        if self.attempts == 1:
            from app.agents.llm.protocols import LLMResponse

            return LLMResponse(content='{"summary": "broken", "max_candidates": 0}', model="broken")
        from app.agents.llm.protocols import LLMResponse

        return LLMResponse(
            content='{"summary": "Valid plan", "max_candidates": 3}',
            model="broken",
        )


async def test_structured_complete_retries_after_validation_failure() -> None:
    llm = BrokenLLM()
    result = await structured_complete(llm, SamplePlan, "Return SamplePlan JSON", max_attempts=3)
    assert result.summary == "Valid plan"
    assert llm.attempts == 2


async def test_fake_llm_returns_valid_plan_json() -> None:
    from app.agents.schemas import InvestigationPlan

    llm = FakeLLMProvider()
    result = await structured_complete(
        llm,
        InvestigationPlan,
        "Plan the investigation. Return InvestigationPlan JSON.",
        max_attempts=1,
    )
    assert result.max_candidates >= 1
