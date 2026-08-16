"""Non-LLM and LLM extraction baselines for four-way comparison."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from app.agents.llm.protocols import LLMProvider
from app.data.extraction_gold import ExtractionGoldExample
from app.models.enums import OpportunityCategory, RemoteStatus
from app.schemas.extraction import OpportunityExtraction
from app.services.extraction_service import ExtractionExample, ExtractionMode, ExtractionService

_LINE = re.compile(r"^([A-Za-z ]+):\s*(.+)$", re.MULTILINE)


class BaselineMode(StrEnum):
    KEYWORD = "keyword"
    PROMPTED = "prompted"
    RAG = "rag"
    RAG_FT = "rag_ft"


@dataclass(frozen=True, slots=True)
class BaselineResult:
    mode: BaselineMode
    predictions: tuple[OpportunityExtraction, ...]


class KeywordBaselineExtractor:
    """Rule-based parser over labelled posting text."""

    async def extract(self, posting_text: str) -> OpportunityExtraction:
        fields = {
            key.strip().casefold(): value.strip() for key, value in _LINE.findall(posting_text)
        }
        title = fields.get("title") or "Unknown opportunity"
        organization = fields.get("organization")
        category = _parse_category(fields.get("category"))
        remote_status = _parse_remote(fields.get("remote"))
        deadline = _parse_deadline(fields.get("deadline"))
        required_skills = _parse_csv(fields.get("required skills"))
        preferred_skills = _parse_csv(fields.get("preferred skills"))
        country = fields.get("country")
        summary = fields.get("summary")
        compensation = _parse_compensation(fields.get("compensation"))
        return OpportunityExtraction(
            title=title,
            organization_name=organization,
            category=category,
            summary=summary,
            location_country=country,
            remote_status=remote_status,
            deadline=deadline,
            required_skills=required_skills,
            preferred_skills=preferred_skills,
            compensation_min=compensation.get("min"),
            compensation_max=compensation.get("max"),
            compensation_currency=compensation.get("currency"),
            compensation_period=compensation.get("period"),
        )


class LLMBaselineExtractor:
    def __init__(self, llm: LLMProvider) -> None:
        self.service = ExtractionService(llm)

    async def extract(
        self,
        posting_text: str,
        *,
        mode: BaselineMode,
        few_shot: tuple[ExtractionGoldExample, ...] = (),
    ) -> OpportunityExtraction:
        examples = tuple(
            ExtractionExample(posting_text=row.posting_text, label=row.label) for row in few_shot
        )
        extraction_mode = {
            BaselineMode.PROMPTED: ExtractionMode.PROMPTED,
            BaselineMode.RAG: ExtractionMode.RAG,
            BaselineMode.RAG_FT: ExtractionMode.RAG_FT,
        }[mode]
        return await self.service.extract(
            posting_text,
            mode=extraction_mode,
            few_shot=examples,
        )


def _parse_category(raw: str | None) -> OpportunityCategory:
    if not raw:
        return OpportunityCategory.OTHER
    try:
        return OpportunityCategory(raw.strip().casefold())
    except ValueError:
        return OpportunityCategory.OTHER


def _parse_remote(raw: str | None) -> RemoteStatus:
    if not raw:
        return RemoteStatus.UNKNOWN
    try:
        return RemoteStatus(raw.strip().casefold())
    except ValueError:
        return RemoteStatus.UNKNOWN


def _parse_deadline(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw.strip())
    except ValueError:
        return None


def _parse_csv(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def _parse_compensation(raw: str | None) -> dict[str, object | None]:
    if not raw:
        return {"min": None, "max": None, "currency": None, "period": None}
    match = re.search(
        r"(?P<min>\d+)\-(?P<max>\d+)\s+(?P<currency>[A-Z]{3})\s+per\s+(?P<period>\w+)",
        raw,
        re.IGNORECASE,
    )
    if match is None:
        return {"min": None, "max": None, "currency": None, "period": None}
    return {
        "min": int(match.group("min")),
        "max": int(match.group("max")),
        "currency": match.group("currency").upper(),
        "period": match.group("period").casefold(),
    }
