"""Fine-tuning dataset export and promotion helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.extraction_gold import (
    DATASET_NAME,
    DATASET_VERSION,
    ExtractionGoldExample,
    build_extraction_gold,
    example_to_sft_record,
)
from app.models.enums import FeedbackSignal
from app.models.feedback import Feedback
from app.schemas.extraction import OpportunityExtraction


@dataclass(frozen=True, slots=True)
class DatasetExport:
    dataset_name: str
    dataset_version: str
    example_count: int
    path: Path


def write_extraction_gold_jsonl(
    path: Path,
    *,
    examples: tuple[ExtractionGoldExample, ...] | None = None,
) -> DatasetExport:
    rows = examples or build_extraction_gold()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for example in rows:
            payload = {
                "example_id": example.example_id,
                "posting_text": example.posting_text,
                "label": example.label.model_dump(mode="json"),
                "source_url": example.source_url,
            }
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return DatasetExport(
        dataset_name=DATASET_NAME,
        dataset_version=DATASET_VERSION,
        example_count=len(rows),
        path=path,
    )


def write_sft_jsonl(
    path: Path,
    *,
    examples: tuple[ExtractionGoldExample, ...] | None = None,
) -> Path:
    rows = examples or build_extraction_gold()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for example in rows:
            handle.write(json.dumps(example_to_sft_record(example), ensure_ascii=False) + "\n")
    return path


async def export_feedback_corrections(session: AsyncSession) -> list[dict[str, Any]]:
    """Return raw correction payloads — never auto-promoted to training."""
    stmt = select(Feedback).where(
        Feedback.signal.in_(
            (
                FeedbackSignal.NOT_ELIGIBLE,
                FeedbackSignal.IRRELEVANT,
                FeedbackSignal.LOW_VALUE,
            )
        )
    )
    rows = list((await session.execute(stmt)).scalars())
    exported: list[dict[str, Any]] = []
    for row in rows:
        payload = row.payload or {}
        if not payload:
            continue
        exported.append(
            {
                "feedback_id": str(row.id),
                "opportunity_id": str(row.opportunity_id),
                "signal": row.signal.value,
                "payload": payload,
            }
        )
    return exported


def merge_correction_into_label(
    label: OpportunityExtraction,
    correction: dict[str, Any],
) -> OpportunityExtraction:
    """Apply an explicit reviewed correction payload onto a gold label."""
    data = label.model_dump()
    for key, value in correction.items():
        if key in OpportunityExtraction.model_fields:
            data[key] = value
    return OpportunityExtraction.model_validate(data)
