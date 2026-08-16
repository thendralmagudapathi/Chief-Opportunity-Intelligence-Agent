"""Versioned extraction gold examples for evaluation and fine-tuning."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from app.data.corpus import CORPUS
from app.models.enums import OpportunityCategory, RemoteStatus
from app.schemas.extraction import OpportunityExtraction

DATASET_VERSION = "v1"
DATASET_NAME = "extraction_gold"


@dataclass(frozen=True, slots=True)
class ExtractionGoldExample:
    example_id: str
    posting_text: str
    label: OpportunityExtraction
    source_url: str


def corpus_item_to_posting(item: dict[str, Any]) -> str:
    """Render a corpus row as labelled posting text for extraction."""
    category = item["category"]
    category_value = category.value if isinstance(category, OpportunityCategory) else category
    lines = [
        f"Title: {item['title']}",
        f"Organization: {item.get('organization_name') or 'Unknown'}",
        f"Category: {category_value}",
    ]
    if item.get("location_country"):
        lines.append(f"Country: {item['location_country']}")
    if item.get("remote_status"):
        remote = item["remote_status"]
        value = remote.value if isinstance(remote, RemoteStatus) else remote
        lines.append(f"Remote: {value}")
    if item.get("deadline"):
        lines.append(f"Deadline: {item['deadline']}")
    if item.get("required_skills"):
        lines.append(f"Required skills: {', '.join(item['required_skills'])}")
    if item.get("preferred_skills"):
        lines.append(f"Preferred skills: {', '.join(item['preferred_skills'])}")
    if item.get("compensation_min") is not None:
        period = item.get("compensation_period") or "year"
        currency = item.get("compensation_currency") or ""
        lines.append(
            f"Compensation: {item['compensation_min']}-{item.get('compensation_max')} "
            f"{currency} per {period}"
        )
    if item.get("summary"):
        lines.append(f"Summary: {item['summary']}")
    return "\n".join(lines)


def corpus_item_to_label(item: dict[str, Any]) -> OpportunityExtraction:
    category = item["category"]
    if not isinstance(category, OpportunityCategory):
        category = OpportunityCategory(str(category))
    remote = item.get("remote_status") or RemoteStatus.UNKNOWN
    if not isinstance(remote, RemoteStatus):
        remote = RemoteStatus(str(remote))
    deadline_value = item.get("deadline")
    deadline: date | None = None
    if deadline_value:
        try:
            deadline = date.fromisoformat(str(deadline_value))
        except ValueError:
            deadline = None
    return OpportunityExtraction(
        title=str(item["title"]),
        organization_name=item.get("organization_name"),
        category=category,
        summary=item.get("summary"),
        location_country=item.get("location_country"),
        remote_status=remote,
        deadline=deadline,
        required_skills=[str(skill) for skill in item.get("required_skills") or []],
        preferred_skills=[str(skill) for skill in item.get("preferred_skills") or []],
        compensation_min=item.get("compensation_min"),
        compensation_max=item.get("compensation_max"),
        compensation_currency=item.get("compensation_currency"),
        compensation_period=item.get("compensation_period"),
    )


def build_extraction_gold(*, limit: int = 20) -> tuple[ExtractionGoldExample, ...]:
    examples: list[ExtractionGoldExample] = []
    for index, item in enumerate(CORPUS[:limit]):
        examples.append(
            ExtractionGoldExample(
                example_id=f"gold-{index:03d}",
                posting_text=corpus_item_to_posting(item),
                label=corpus_item_to_label(item),
                source_url=str(item["source_url"]),
            )
        )
    return tuple(examples)


def load_extraction_gold(limit: int = 20) -> tuple[ExtractionGoldExample, ...]:
    repo_root = Path(__file__).resolve().parents[3]
    jsonl_path = repo_root / "ml" / "datasets" / f"extraction_gold_{DATASET_VERSION}.jsonl"
    if not jsonl_path.exists():
        return build_extraction_gold(limit=limit)
    examples: list[ExtractionGoldExample] = []
    for line in jsonl_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        examples.append(
            ExtractionGoldExample(
                example_id=str(payload["example_id"]),
                posting_text=str(payload["posting_text"]),
                label=OpportunityExtraction.model_validate(payload["label"]),
                source_url=str(payload["source_url"]),
            )
        )
        if len(examples) >= limit:
            break
    return tuple(examples)


def example_to_sft_record(example: ExtractionGoldExample) -> dict[str, str]:
    """Alpaca-style SFT row for LoRA training."""
    instruction = (
        "Extract structured opportunity fields from the posting. "
        "Return JSON matching OpportunityExtraction."
    )
    return {
        "instruction": instruction,
        "input": example.posting_text,
        "output": example.label.model_dump_json(),
    }
