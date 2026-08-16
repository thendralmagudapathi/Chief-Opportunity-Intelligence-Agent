"""Evaluation run persistence."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.evaluation.gates import evaluate_gates
from app.models.enums import EvaluationStatus
from app.models.evaluation import EvaluationRun


class EvaluationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_run(
        self,
        *,
        name: str,
        suite: str,
        dataset_name: str,
        dataset_version: str,
        git_sha: str | None,
        config: dict[str, Any] | None = None,
    ) -> EvaluationRun:
        row = EvaluationRun(
            name=name,
            suite=suite,
            dataset_name=dataset_name,
            dataset_version=dataset_version,
            git_sha=git_sha,
            status=EvaluationStatus.PENDING,
            config=config or {},
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def mark_running(self, run: EvaluationRun) -> None:
        run.status = EvaluationStatus.RUNNING
        run.started_at = datetime.now(UTC)
        await self.session.flush()

    async def mark_succeeded(
        self,
        run: EvaluationRun,
        metrics: dict[str, Any],
        *,
        notes: str | None = None,
        mlflow_run_id: str | None = None,
    ) -> None:
        run.status = EvaluationStatus.SUCCEEDED
        run.finished_at = datetime.now(UTC)
        run.metrics = metrics
        run.notes = notes
        run.mlflow_run_id = mlflow_run_id
        await self.session.flush()

    async def mark_failed(self, run: EvaluationRun, error: str) -> None:
        run.status = EvaluationStatus.FAILED
        run.finished_at = datetime.now(UTC)
        run.notes = error
        await self.session.flush()

    async def get_run(self, run_id: uuid.UUID) -> EvaluationRun:
        row = await self.session.get(EvaluationRun, run_id)
        if row is None:
            raise NotFoundError("Evaluation run not found")
        return row

    async def list_runs(self, *, limit: int = 20) -> list[EvaluationRun]:
        stmt = select(EvaluationRun).order_by(EvaluationRun.created_at.desc()).limit(limit)
        return list((await self.session.execute(stmt)).scalars())

    @staticmethod
    def gate_passed(metrics: dict[str, float]) -> bool:
        passed, _ = evaluate_gates(metrics)
        return passed
