"""Agent run endpoints."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.agents.events import event_store
from app.api.deps import AgentRunServiceDep, CurrentUser
from app.models.enums import AgentRunStatus
from app.schemas.agent_run import AgentRunListResponse, AgentRunRead, AgentRunSummary

router = APIRouter(prefix="/agent-runs", tags=["agent-runs"])


@router.get("", response_model=AgentRunListResponse, summary="List agent runs")
async def list_runs(user: CurrentUser, runs: AgentRunServiceDep) -> AgentRunListResponse:
    rows = await runs.list_runs(user.id)
    return AgentRunListResponse(items=[AgentRunSummary.model_validate(row) for row in rows])


@router.get("/{run_id}", response_model=AgentRunRead, summary="Get an agent run")
async def get_run(run_id: uuid.UUID, user: CurrentUser, runs: AgentRunServiceDep) -> AgentRunRead:
    row = await runs.get_run(user.id, run_id)
    return AgentRunRead.model_validate(row)


@router.get("/{run_id}/stream", summary="SSE progress stream")
async def stream_run(
    run_id: uuid.UUID, user: CurrentUser, runs: AgentRunServiceDep
) -> StreamingResponse:
    await runs.get_run(user.id, run_id)

    async def event_generator() -> AsyncIterator[str]:
        queue = await event_store.subscribe(run_id)
        while True:
            item = await queue.get()
            if item is None:
                break
            yield f"event: {item['event']}\ndata: {json.dumps(item['data'])}\n\n"
            await asyncio.sleep(0)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/{run_id}/cancel", response_model=AgentRunSummary, summary="Cancel a run")
async def cancel_run(
    run_id: uuid.UUID, user: CurrentUser, runs: AgentRunServiceDep
) -> AgentRunSummary:
    run = await runs.get_run(user.id, run_id)
    if run.status not in (AgentRunStatus.PENDING, AgentRunStatus.RUNNING):
        return AgentRunSummary.model_validate(run)
    event_store.cancel(run_id)
    await runs.mark_cancelled(run)
    return AgentRunSummary.model_validate(run)
