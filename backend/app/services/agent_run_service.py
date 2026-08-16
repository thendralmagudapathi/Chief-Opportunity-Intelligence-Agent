"""Agent run persistence and lifecycle."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.context import get_request_id
from app.core.errors import NotFoundError
from app.models.agent_run import AgentRun, AgentTask
from app.models.enums import AgentRunStatus, AgentRunType, AgentTaskStatus


class AgentRunService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_run(
        self,
        *,
        user_id: uuid.UUID,
        goal_id: uuid.UUID,
        objective: str,
        run_type: AgentRunType = AgentRunType.INVESTIGATE,
        budget: dict[str, Any] | None = None,
    ) -> AgentRun:
        run = AgentRun(
            user_id=user_id,
            goal_id=goal_id,
            trace_id=get_request_id(),
            run_type=run_type,
            status=AgentRunStatus.PENDING,
            objective_text=objective,
            graph_version="investigation.v1",
            budget=budget
            or {
                "max_iterations": 3,
                "remaining_usd": 1.0,
                "max_tool_calls_total": 60,
            },
        )
        self.session.add(run)
        await self.session.flush()
        return run

    async def get_run(self, user_id: uuid.UUID, run_id: uuid.UUID) -> AgentRun:
        stmt = (
            select(AgentRun)
            .where(AgentRun.id == run_id, AgentRun.user_id == user_id)
            .options(selectinload(AgentRun.tasks), selectinload(AgentRun.tool_calls))
        )
        run = (await self.session.execute(stmt)).scalar_one_or_none()
        if run is None:
            raise NotFoundError("Agent run not found")
        return run

    async def list_runs(self, user_id: uuid.UUID, *, limit: int = 20) -> list[AgentRun]:
        stmt = (
            select(AgentRun)
            .where(AgentRun.user_id == user_id)
            .order_by(AgentRun.created_at.desc())
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars())

    async def mark_running(self, run: AgentRun) -> None:
        run.status = AgentRunStatus.RUNNING
        run.started_at = datetime.now(UTC)
        await self.session.flush()

    async def mark_succeeded(self, run: AgentRun, result: dict[str, Any]) -> None:
        run.status = AgentRunStatus.SUCCEEDED
        run.finished_at = datetime.now(UTC)
        run.result = result
        if run.started_at is not None:
            delta = run.finished_at - run.started_at
            run.latency_ms = int(delta.total_seconds() * 1000)
        await self.session.flush()

    async def mark_failed(self, run: AgentRun, error: str) -> None:
        run.status = AgentRunStatus.FAILED
        run.finished_at = datetime.now(UTC)
        run.error = error
        await self.session.flush()

    async def mark_cancelled(self, run: AgentRun) -> None:
        run.status = AgentRunStatus.CANCELLED
        run.finished_at = datetime.now(UTC)
        await self.session.flush()

    async def start_task(
        self,
        run_id: uuid.UUID,
        *,
        agent_name: str,
        capability: str | None = None,
        input_payload: dict[str, Any] | None = None,
    ) -> AgentTask:
        task = AgentTask(
            agent_run_id=run_id,
            agent_name=agent_name,
            capability=capability,
            status=AgentTaskStatus.RUNNING,
            started_at=datetime.now(UTC),
            input=input_payload,
        )
        self.session.add(task)
        await self.session.flush()
        return task

    async def finish_task(
        self,
        task_id: uuid.UUID,
        *,
        status: AgentTaskStatus,
        output: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        task = await self.session.get(AgentTask, task_id)
        if task is None:
            return
        task.status = status
        task.output = output
        task.error = error
        task.finished_at = datetime.now(UTC)
        if task.started_at is not None:
            delta = task.finished_at - task.started_at
            task.latency_ms = int(delta.total_seconds() * 1000)
        await self.session.flush()
