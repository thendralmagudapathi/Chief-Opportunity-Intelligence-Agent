"""MLflow model registry helpers and rollback state."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.core.logging import get_logger
from app.observability import mlflow_tracking

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ModelPromotion:
    registry_name: str
    model_version: str
    active_model: str
    rollback_model: str


@dataclass(frozen=True, slots=True)
class ModelRollback:
    registry_name: str
    restored_model: str


def active_extraction_model(settings: Settings) -> str:
    finetuning = settings.finetuning
    if finetuning.enabled and finetuning.active_extraction_model:
        return finetuning.active_extraction_model
    return settings.models.model_extraction


def promote_extraction_model(
    settings: Settings,
    *,
    model_uri: str,
    version: str,
) -> ModelPromotion:
    previous = active_extraction_model(settings)
    mlflow_tracking.register_model(
        settings,
        model_uri=model_uri,
        registry_name=settings.finetuning.registry_name,
        version=version,
    )
    logger.info(
        "extraction_model_promoted",
        registry=settings.finetuning.registry_name,
        version=version,
        previous=previous,
        active=model_uri,
    )
    return ModelPromotion(
        registry_name=settings.finetuning.registry_name,
        model_version=version,
        active_model=model_uri,
        rollback_model=previous,
    )


def rollback_extraction_model(settings: Settings) -> ModelRollback | None:
    rollback = settings.finetuning.rollback_extraction_model
    if not rollback:
        logger.warning("extraction_model_rollback_missing")
        return None
    logger.info(
        "extraction_model_rollback",
        registry=settings.finetuning.registry_name,
        restored=rollback,
    )
    return ModelRollback(
        registry_name=settings.finetuning.registry_name,
        restored_model=rollback,
    )
