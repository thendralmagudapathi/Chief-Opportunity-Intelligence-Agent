"""Optional MLflow tracking for evaluation runs."""

from __future__ import annotations

from app.core.config import Settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def start_evaluation_run(
    settings: Settings,
    *,
    run_name: str,
    tags: dict[str, str] | None = None,
) -> str | None:
    if not settings.observability.mlflow_tracking_uri:
        return None
    try:
        import mlflow

        mlflow.set_tracking_uri(settings.observability.mlflow_tracking_uri)
        with mlflow.start_run(run_name=run_name) as run:
            if tags:
                mlflow.set_tags(tags)
            return str(run.info.run_id)
    except Exception as exc:
        logger.warning("mlflow_start_failed", error=str(exc))
        return None


def log_evaluation_metrics(run_id: str | None, metrics: dict[str, float]) -> None:
    if run_id is None:
        return
    try:
        import mlflow

        with mlflow.start_run(run_id=run_id):
            mlflow.log_metrics(metrics)
    except Exception as exc:
        logger.warning("mlflow_log_failed", error=str(exc))
