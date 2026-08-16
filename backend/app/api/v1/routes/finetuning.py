"""Fine-tuning experiment endpoints."""

from __future__ import annotations

from fastapi import APIRouter, status

from app.agents.llm.factory import build_llm_provider
from app.api.deps import CurrentSuperuser, CurrentUser, SettingsDep
from app.data.extraction_gold import load_extraction_gold
from app.finetuning.comparison import ExtractionComparisonHarness
from app.finetuning.registry import (
    active_extraction_model,
    promote_extraction_model,
    rollback_extraction_model,
)
from app.observability.mlflow_tracking import log_training_metrics, start_training_run
from app.schemas.finetuning import (
    ComparisonRead,
    ExtractionMetricsRead,
    FineTuningCompareRequest,
    FineTuningPromoteRequest,
    ModelPromotionRead,
    ModelRollbackRead,
    ModeScoreRead,
)

router = APIRouter(prefix="/finetuning", tags=["finetuning"])


@router.get("/model", summary="Active extraction model")
async def get_active_model(user: CurrentUser, settings: SettingsDep) -> dict[str, str | bool]:
    del user
    return {
        "enabled": settings.finetuning.enabled,
        "active_model": active_extraction_model(settings),
        "rollback_model": settings.finetuning.rollback_extraction_model or "",
        "registry_name": settings.finetuning.registry_name,
    }


@router.post(
    "/compare",
    response_model=ComparisonRead,
    status_code=status.HTTP_200_OK,
    summary="Run four-way extraction comparison (admin only)",
)
async def compare_baselines(
    payload: FineTuningCompareRequest,
    admin: CurrentSuperuser,
    settings: SettingsDep,
) -> ComparisonRead:
    del admin
    llm = build_llm_provider(settings)
    harness = ExtractionComparisonHarness(llm)
    examples = load_extraction_gold(limit=payload.dataset_limit)
    result = await harness.run(
        examples=examples,
        noise_band=settings.finetuning.noise_band,
    )
    run_id = start_training_run(
        settings,
        run_name="extraction_compare",
        tags={"suite": "extraction", "phase": "8"},
    )
    log_training_metrics(
        run_id,
        {
            "lift": result.lift,
            f"{result.candidate.mode.value}_macro": result.candidate.macro_average,
            f"{result.prompted.mode.value}_macro": result.prompted.macro_average,
        },
    )
    return ComparisonRead(
        winner=result.winner.value,
        lift=result.lift,
        noise_band=result.noise_band,
        verdict=result.verdict.value,
        notes=result.notes,
        scores=[
            ModeScoreRead(
                mode=score.mode.value,
                metrics=ExtractionMetricsRead(
                    classification_accuracy=score.metrics.classification_accuracy,
                    deadline_accuracy=score.metrics.deadline_accuracy,
                    requirement_f1=score.metrics.requirement_f1,
                    macro_average=score.metrics.macro_average,
                ),
            )
            for score in result.scores
        ],
    )


@router.post(
    "/promote",
    response_model=ModelPromotionRead,
    summary="Register and promote a fine-tuned extraction model (admin only)",
)
async def promote_model(
    payload: FineTuningPromoteRequest,
    admin: CurrentSuperuser,
    settings: SettingsDep,
) -> ModelPromotionRead:
    del admin
    promotion = promote_extraction_model(
        settings,
        model_uri=payload.model_uri,
        version=payload.version,
    )
    return ModelPromotionRead(
        registry_name=promotion.registry_name,
        model_version=promotion.model_version,
        active_model=promotion.active_model,
        rollback_model=promotion.rollback_model,
    )


@router.post(
    "/rollback",
    response_model=ModelRollbackRead,
    summary="Restore the previous extraction model (admin only)",
)
async def rollback_model(admin: CurrentSuperuser, settings: SettingsDep) -> ModelRollbackRead:
    del admin
    rollback = rollback_extraction_model(settings)
    if rollback is None:
        return ModelRollbackRead(registry_name=settings.finetuning.registry_name, restored_model="")
    return ModelRollbackRead(
        registry_name=rollback.registry_name,
        restored_model=rollback.restored_model,
    )
