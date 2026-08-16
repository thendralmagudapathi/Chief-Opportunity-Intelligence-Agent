"""Investigation trace completeness audit."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.agent_run import AgentRun
from app.models.enums import AgentRunStatus, AgentTaskStatus

REQUIRED_STAGES: frozenset[str] = frozenset(
    {
        "understand",
        "load_context",
        "plan",
        "discover",
        "triage",
        "evaluate",
        "verify",
        "score",
        "contrarian",
        "decide",
        "report",
    }
)

REQUIRED_TASK_CAPABILITIES: frozenset[tuple[str, str | None]] = frozenset(
    {
        ("supervisor", "understand"),
        ("supervisor", "plan"),
        ("verification", "verify"),
        ("contrarian", "contrarian"),
    }
)


@dataclass(frozen=True, slots=True)
class TraceAuditResult:
    complete: bool
    missing_stages: tuple[str, ...]
    missing_tasks: tuple[str, ...]
    tool_call_count: int
    task_count: int


async def audit_investigation_trace(session: AsyncSession, run_id: uuid.UUID) -> TraceAuditResult:
    stmt = (
        select(AgentRun)
        .where(AgentRun.id == run_id)
        .options(selectinload(AgentRun.tasks), selectinload(AgentRun.tool_calls))
    )
    run = (await session.execute(stmt)).scalar_one_or_none()
    if run is None:
        return TraceAuditResult(
            complete=False,
            missing_stages=tuple(REQUIRED_STAGES),
            missing_tasks=("run_not_found",),
            tool_call_count=0,
            task_count=0,
        )

    observed_stages: set[str] = set()
    if run.result and isinstance(run.result, dict):
        for event in run.result.get("events", []):
            if isinstance(event, dict) and event.get("stage"):
                observed_stages.add(str(event["stage"]))

    missing_stages = tuple(sorted(REQUIRED_STAGES - observed_stages))

    succeeded_tasks = {
        (task.agent_name, task.capability)
        for task in run.tasks
        if task.status == AgentTaskStatus.SUCCEEDED
    }
    missing_tasks = tuple(
        sorted(
            f"{agent}:{capability or '*'}"
            for agent, capability in REQUIRED_TASK_CAPABILITIES
            if (agent, capability) not in succeeded_tasks
        )
    )

    complete = (
        run.status == AgentRunStatus.SUCCEEDED
        and not missing_stages
        and not missing_tasks
        and run.result is not None
        and "report" in (run.result or {})
    )
    return TraceAuditResult(
        complete=complete,
        missing_stages=missing_stages,
        missing_tasks=missing_tasks,
        tool_call_count=len(run.tool_calls),
        task_count=len(run.tasks),
    )
