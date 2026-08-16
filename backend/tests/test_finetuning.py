"""Fine-tuning dataset, comparison, registry and API tests."""

from __future__ import annotations

from app.agents.llm.fake import FakeLLMProvider
from app.data.extraction_gold import build_extraction_gold
from app.finetuning.comparison import ComparisonVerdict, ExtractionComparisonHarness
from app.finetuning.dataset import merge_correction_into_label, write_extraction_gold_jsonl
from app.finetuning.registry import active_extraction_model, promote_extraction_model
from app.models.enums import OpportunityCategory
from app.schemas.extraction import OpportunityExtraction


async def test_four_way_comparison_promotes_rag_ft_over_prompted() -> None:
    harness = ExtractionComparisonHarness(FakeLLMProvider())
    result = await harness.run(examples=build_extraction_gold(limit=5), noise_band=0.02)
    assert result.prompted.macro_average < result.candidate.macro_average
    assert result.verdict == ComparisonVerdict.PROMOTED
    assert len(result.scores) == 4


def test_dataset_export_writes_jsonl(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "extraction_gold_v1.jsonl"
    export = write_extraction_gold_jsonl(path, examples=build_extraction_gold(limit=3))
    assert export.example_count == 3
    assert path.read_text(encoding="utf-8").count("\n") == 3


def test_merge_correction_updates_label() -> None:
    label = OpportunityExtraction(title="Old", category=OpportunityCategory.JOB)
    updated = merge_correction_into_label(label, {"title": "New title"})
    assert updated.title == "New title"


def test_active_extraction_model_uses_finetuning_override(settings) -> None:  # type: ignore[no-untyped-def]
    previous_enabled = settings.finetuning.enabled
    previous_active = settings.finetuning.active_extraction_model
    settings.finetuning.enabled = True
    settings.finetuning.active_extraction_model = "ft-extraction-v1"
    assert active_extraction_model(settings) == "ft-extraction-v1"
    settings.finetuning.enabled = previous_enabled
    settings.finetuning.active_extraction_model = previous_active


def test_promote_extraction_model_returns_rollback_target(settings) -> None:  # type: ignore[no-untyped-def]
    settings.finetuning.enabled = False
    settings.finetuning.active_extraction_model = None
    promotion = promote_extraction_model(
        settings,
        model_uri="models:/oia-extraction/2",
        version="v2",
    )
    assert promotion.active_model == "models:/oia-extraction/2"
    assert promotion.rollback_model == settings.models.model_extraction


async def test_finetuning_compare_endpoint(client, admin_user) -> None:  # type: ignore[no-untyped-def]
    response = await client.post(
        "/api/v1/finetuning/compare",
        json={"dataset_limit": 5},
        headers=admin_user["headers"],
    )
    assert response.status_code == 200
    body = response.json()
    assert body["verdict"] == "promoted"
    assert len(body["scores"]) == 4


async def test_finetuning_model_endpoint(client, registered_user) -> None:  # type: ignore[no-untyped-def]
    response = await client.get("/api/v1/finetuning/model", headers=registered_user["headers"])
    assert response.status_code == 200
    assert "active_model" in response.json()
