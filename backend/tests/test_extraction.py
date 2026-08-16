"""Extraction schema and service tests."""

from __future__ import annotations

from datetime import date

from app.agents.llm.fake import FakeLLMProvider
from app.data.extraction_gold import build_extraction_gold
from app.finetuning.metrics import evaluate_extractions
from app.models.enums import OpportunityCategory
from app.schemas.extraction import OpportunityExtraction
from app.services.extraction_service import ExtractionExample, ExtractionMode, ExtractionService


async def test_extraction_service_prompted_parses_partial_fields() -> None:
    example = build_extraction_gold(limit=1)[0]
    service = ExtractionService(FakeLLMProvider())
    result = await service.extract(example.posting_text, mode=ExtractionMode.PROMPTED)
    assert result.title
    assert result.organization_name
    assert result.category == example.label.category


async def test_extraction_service_rag_parses_full_fields() -> None:
    examples = build_extraction_gold(limit=3)
    holdout = examples[1]
    service = ExtractionService(FakeLLMProvider())
    result = await service.extract(
        holdout.posting_text,
        mode=ExtractionMode.RAG,
        few_shot=tuple(
            ExtractionExample(posting_text=row.posting_text, label=row.label)
            for row in examples[:2]
        ),
    )
    assert result.deadline == holdout.label.deadline
    assert result.required_skills == holdout.label.required_skills


def test_extraction_metrics_perfect_match() -> None:
    label = OpportunityExtraction(
        title="Research Fellow",
        organization_name="CERN",
        category=OpportunityCategory.FELLOWSHIP,
        deadline=date(2026, 11, 15),
        required_skills=["python"],
    )
    metrics = evaluate_extractions(predictions=[label], gold=[label])
    assert metrics.classification_accuracy == 1.0
    assert metrics.deadline_accuracy == 1.0
    assert metrics.requirement_f1 == 1.0


def test_corpus_posting_contains_title_line() -> None:
    example = build_extraction_gold(limit=1)[0]
    assert example.posting_text.startswith("Title:")


def test_extraction_service_to_raw_opportunity() -> None:
    extraction = OpportunityExtraction(
        title="Grant",
        organization_name="ERC",
        category=OpportunityCategory.GRANT,
    )
    raw = ExtractionService(FakeLLMProvider()).to_raw_opportunity(
        extraction,
        source_url="https://example.com/grant",
    )
    assert raw.title == "Grant"
    assert raw.source_url == "https://example.com/grant"
