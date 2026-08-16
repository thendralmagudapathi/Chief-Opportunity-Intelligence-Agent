"""Enqueue background work through Celery or FastAPI BackgroundTasks."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from fastapi import BackgroundTasks

from app.core.config import Settings


def enqueue_investigation(
    settings: Settings,
    *,
    background: BackgroundTasks | None,
    run_id: uuid.UUID,
    user_id: uuid.UUID,
    inline_runner: Callable[[uuid.UUID, uuid.UUID], Any],
) -> str:
    if settings.workers.enabled:
        from app.workers.tasks import run_investigation_task

        run_investigation_task.delay(str(run_id), str(user_id))
        return "celery"
    if background is not None:
        background.add_task(inline_runner, run_id, user_id)
        return "background"
    inline_runner(run_id, user_id)
    return "inline"
