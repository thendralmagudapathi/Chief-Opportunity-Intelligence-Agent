"""LLM-backed opportunity field extraction."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.agents.llm.protocols import LLMProvider
from app.agents.llm.structured import structured_complete
from app.agents.prompts import load_prompt, render_prompt
from app.schemas.extraction import OpportunityExtraction
from app.services.ingestion import RawOpportunity


class ExtractionMode(StrEnum):
    PROMPTED = "prompted"
    RAG = "rag"
    RAG_FT = "rag_ft"


@dataclass(frozen=True, slots=True)
class ExtractionExample:
    posting_text: str
    label: OpportunityExtraction


class ExtractionService:
    """Extract structured fields from raw posting text."""

    PROMPT_VERSION = "normalize.v1"

    def __init__(self, llm: LLMProvider) -> None:
        self.llm = llm

    async def extract(
        self,
        posting_text: str,
        *,
        mode: ExtractionMode = ExtractionMode.PROMPTED,
        few_shot: tuple[ExtractionExample, ...] = (),
    ) -> OpportunityExtraction:
        template = load_prompt("extraction", "normalize", version=1)
        prompt = render_prompt(template, posting_text=posting_text)
        if mode in (ExtractionMode.RAG, ExtractionMode.RAG_FT) and few_shot:
            prompt = _append_few_shot(prompt, few_shot)
        return await structured_complete(
            self.llm,
            OpportunityExtraction,
            prompt,
            task_class="extract",
        )

    def to_raw_opportunity(
        self,
        extraction: OpportunityExtraction,
        *,
        source_url: str,
        external_id: str | None = None,
    ) -> RawOpportunity:
        return RawOpportunity(
            title=extraction.title,
            source_url=source_url,
            category=extraction.category,
            external_id=external_id,
            organization_name=extraction.organization_name,
            summary=extraction.summary,
            location_country=extraction.location_country,
            location_city=extraction.location_city,
            remote_status=extraction.remote_status,
            compensation_min=extraction.compensation_min,
            compensation_max=extraction.compensation_max,
            compensation_currency=extraction.compensation_currency,
            compensation_period=extraction.compensation_period,
            requirements=list(extraction.requirements),
            required_skills=list(extraction.required_skills),
            preferred_skills=list(extraction.preferred_skills),
            deadline=extraction.deadline.isoformat() if extraction.deadline else None,
        )


def _append_few_shot(prompt: str, examples: tuple[ExtractionExample, ...]) -> str:
    blocks: list[str] = ["Few-shot examples (input → JSON label):"]
    for index, example in enumerate(examples, start=1):
        blocks.append(f"Example {index} input:\n{example.posting_text}")
        blocks.append(f"Example {index} label:\n{example.label.model_dump_json()}")
    return f"{prompt}\n\n" + "\n\n".join(blocks)
