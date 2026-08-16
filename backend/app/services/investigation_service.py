"""Execute investigation graphs."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.context import RunContext
from app.agents.events import event_store
from app.agents.graph import build_investigation_graph
from app.agents.llm.factory import build_llm_provider
from app.agents.schemas import InvestigationRequest
from app.agents.state import InvestigationState
from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.db.session import get_session_factory
from app.models.enums import AgentRunStatus
from app.services.agent_run_service import AgentRunService

logger = get_logger(__name__)


class InvestigationService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.runs = AgentRunService(session)

    async def start(
        self, user_id: uuid.UUID, payload: InvestigationRequest
    ) -> tuple[uuid.UUID, str]:
        run = await self.runs.create_run(
            user_id=user_id,
            goal_id=payload.goal_id,
            objective=payload.objective,
            budget={
                "max_iterations": self.settings.agents.max_iterations,
                "remaining_usd": self.settings.agents.max_cost_usd,
                "max_tool_calls_total": self.settings.agents.max_tool_calls_total,
                "opportunity_ids": [str(value) for value in payload.opportunity_ids or []],
            },
        )
        return run.id, run.trace_id

    async def start_and_commit(
        self, user_id: uuid.UUID, payload: InvestigationRequest
    ) -> tuple[uuid.UUID, str]:
        run_id, trace_id = await self.start(user_id, payload)
        await self.session.commit()
        return run_id, trace_id


async def run_investigation_background(run_id: uuid.UUID, user_id: uuid.UUID) -> None:
    settings = get_settings()
    factory = get_session_factory()
    async with factory() as session:
        service = InvestigationService(session, settings)
        run = await service.runs.get_run(user_id, run_id)
        await service.runs.mark_running(run)
        await session.commit()

        def emit(event: str, data: dict[str, Any]) -> None:
            event_store.append(run_id, event, data)

        ctx = RunContext(
            session=session,
            settings=settings,
            llm=build_llm_provider(settings),
            run_id=run_id,
            trace_id=run.trace_id,
            user_id=user_id,
            emit=emit,
        )
        graph = build_investigation_graph(ctx)
        initial: InvestigationState = {
            "run_id": str(run_id),
            "trace_id": run.trace_id,
            "user_id": str(user_id),
            "goal_id": str(run.goal_id),
            "objective": run.objective_text or "",
            "iterations": 0,
            "budget": run.budget,
            "focus_opportunity_ids": run.budget.get("opportunity_ids", []),
            "degraded": False,
            "errors": [],
            "events": [],
        }
        config = {"configurable": {"thread_id": str(run_id)}}
        try:
            if event_store.is_cancelled(run_id):
                await service.runs.mark_cancelled(run)
                await session.commit()
                return
            final = await graph.ainvoke(initial, config=config)
            report = final.get("report")
            await service.runs.mark_succeeded(
                run, {"report": report, "events": final.get("events", [])}
            )
            emit("done", {"run_id": str(run_id), "status": AgentRunStatus.SUCCEEDED.value})
        except Exception as exc:
            logger.error("investigation_failed", run_id=str(run_id), exc_info=exc)
            await service.runs.mark_failed(run, str(exc))
            emit(
                "done",
                {"run_id": str(run_id), "status": AgentRunStatus.FAILED.value, "error": str(exc)},
            )
        finally:
            event_store.close(run_id)
        await session.commit()
