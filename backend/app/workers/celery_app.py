"""Celery application factory."""

from __future__ import annotations

from celery import Celery

from app.core.config import get_settings
from app.workers.schedules import BEAT_SCHEDULE


def create_celery_app() -> Celery:
    settings = get_settings()
    app = Celery("oia")
    app.conf.update(
        broker_url=settings.workers.broker_url,
        result_backend=settings.workers.result_backend,
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        task_track_started=True,
        worker_concurrency=settings.workers.concurrency,
        task_routes={
            "app.workers.tasks.run_investigation_task": {
                "queue": settings.workers.investigation_queue
            },
            "app.workers.tasks.*": {"queue": settings.workers.maintenance_queue},
        },
        beat_schedule=BEAT_SCHEDULE,
        imports=("app.workers.tasks",),
    )
    return app


celery_app = create_celery_app()
