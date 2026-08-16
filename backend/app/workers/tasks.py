"""Celery task definitions."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Coroutine
from typing import Any, TypeVar

from app.core.logging import get_logger
from app.workers.celery_app import celery_app

logger = get_logger(__name__)
T = TypeVar("T")


def _run_async(coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


@celery_app.task(name="app.workers.tasks.run_investigation_task", bind=True, max_retries=2)
def run_investigation_task(self: Any, run_id: str, user_id: str) -> str:
    from app.services.investigation_service import run_investigation_background

    try:
        _run_async(run_investigation_background(uuid.UUID(run_id), uuid.UUID(user_id)))
        return run_id
    except Exception as exc:
        logger.error("investigation_task_failed", run_id=run_id, error=str(exc))
        raise self.retry(exc=exc, countdown=30) from exc


@celery_app.task(name="app.workers.tasks.index_document_task")
def index_document_task(document_id: str) -> str:
    from app.services.document_tasks import index_document_background

    _run_async(index_document_background(uuid.UUID(document_id)))
    return document_id


@celery_app.task(name="app.workers.tasks.revalidate_opportunities_task")
def revalidate_opportunities_task(limit: int = 100) -> int:
    return _run_async(_revalidate_opportunities(limit))


@celery_app.task(name="app.workers.tasks.scheduled_digest_task")
def scheduled_digest_task(since_hours: int = 24) -> int:
    return _run_async(_emit_digest(since_hours))


async def _revalidate_opportunities(limit: int) -> int:
    from sqlalchemy import select

    from app.db.session import get_session_factory
    from app.models.opportunity import Opportunity
    from app.services.ingestion import IngestionService

    factory = get_session_factory()
    refreshed = 0
    async with factory() as session:
        service = IngestionService(session)
        rows = list(
            (
                await session.execute(
                    select(Opportunity).order_by(Opportunity.last_verified_at.asc()).limit(limit)
                )
            ).scalars()
        )
        for row in rows:
            await service.refresh(row)
            refreshed += 1
        await session.commit()
    logger.info("revalidate_opportunities_complete", refreshed=refreshed)
    return refreshed


async def _emit_digest(since_hours: int) -> int:
    from app.db.session import get_session_factory
    from app.workers.digest import ScheduledDigestService

    factory = get_session_factory()
    async with factory() as session:
        count = await ScheduledDigestService(session).emit(since_hours=since_hours)
        await session.commit()
    return count
