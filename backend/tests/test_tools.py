"""Tool framework tests: permissions, timeout, denial, MCP and benchmark."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest
from app.mcp.adapter import check_mcp_conformance, registry_to_mcp_tools
from app.models.agent_run import AgentRun, ToolCall
from app.models.enums import ToolCallStatus
from app.tools.base import BaseTool
from app.tools.benchmark import argument_validity, selection_accuracy
from app.tools.context import ToolContext
from app.tools.executor import ToolExecutor
from app.tools.factory import build_tool_context, build_tool_registry
from app.tools.permissions import DEFAULT_INVESTIGATION_SCOPES, SCOPE_EXTERNAL_COMMUNICATE
from app.tools.registry import ToolRegistry
from pydantic import BaseModel, Field
from sqlalchemy import select


class _SlowArgs(BaseModel):
    delay_s: float = Field(default=0.2, ge=0.0, le=30.0)


class SlowTool(BaseTool):
    name = "slow_tool"
    description = "Test tool that sleeps."
    args_model = _SlowArgs
    permission_scope = "profile:read"
    timeout_s = 0.05
    max_calls_per_run = 3

    async def run(self, args: BaseModel, ctx: ToolContext) -> dict[str, Any]:
        payload = _SlowArgs.model_validate(args)
        await asyncio.sleep(payload.delay_s)
        return {"slept": payload.delay_s}


@pytest.fixture
def tool_registry() -> ToolRegistry:
    return build_tool_registry()


async def test_registry_has_fifteen_native_tools(tool_registry: ToolRegistry) -> None:
    assert len(tool_registry.names()) == 15


async def test_generate_outreach_denied_without_scope(settings, database_url) -> None:
    from app.db.session import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        ctx = build_tool_context(
            session=session,
            settings=settings,
            user_id=uuid.uuid4(),
            granted_scopes=DEFAULT_INVESTIGATION_SCOPES,
        )
        executor = ToolExecutor(build_tool_registry(), session)
        outcome = await executor.invoke(
            "generate_outreach",
            {
                "opportunity_id": str(uuid.uuid4()),
                "channel": "email",
            },
            ctx,
        )
        assert outcome.ok is False
        assert outcome.error_code == "permission_denied"


async def test_generate_outreach_allowed_with_external_scope(settings, database_url) -> None:
    from app.db.session import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        scopes = DEFAULT_INVESTIGATION_SCOPES | {SCOPE_EXTERNAL_COMMUNICATE}
        ctx = build_tool_context(
            session=session,
            settings=settings,
            user_id=uuid.uuid4(),
            granted_scopes=scopes,
        )
        executor = ToolExecutor(build_tool_registry(), session)
        outcome = await executor.invoke(
            "generate_outreach",
            {"opportunity_id": str(uuid.uuid4())},
            ctx,
        )
        assert outcome.error_code == "not_found"


async def test_slow_tool_times_out(settings, database_url) -> None:
    from app.db.session import get_session_factory

    registry = ToolRegistry.from_instances([SlowTool()])
    factory = get_session_factory()
    async with factory() as session:
        ctx = build_tool_context(session=session, settings=settings, user_id=uuid.uuid4())
        executor = ToolExecutor(registry, session)
        outcome = await executor.invoke("slow_tool", {"delay_s": 0.2}, ctx)
        assert outcome.ok is False
        assert outcome.error_code == "timeout"


async def test_invalid_arguments_are_normalised(settings, database_url) -> None:
    from app.db.session import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        ctx = build_tool_context(session=session, settings=settings, user_id=uuid.uuid4())
        executor = ToolExecutor(build_tool_registry(), session)
        outcome = await executor.invoke("search_opportunities", {"query": ""}, ctx)
        assert outcome.ok is False
        assert outcome.error_code == "invalid_arguments"


async def test_tool_calls_persist_for_runs(settings, registered_user, database_url) -> None:
    from app.db.session import get_session_factory
    from app.models.enums import ObjectiveProfile
    from app.models.goal import Goal
    from app.services.agent_run_service import AgentRunService

    user_id = uuid.UUID(registered_user["id"])
    factory = get_session_factory()
    async with factory() as session:
        goal = Goal(
            user_id=user_id,
            title="Test goal",
            objective_profile=ObjectiveProfile.CAREER,
        )
        session.add(goal)
        await session.flush()
        run = await AgentRunService(session).create_run(
            user_id=user_id,
            goal_id=goal.id,
            objective="test tools",
        )
        await session.commit()
        ctx = build_tool_context(
            session=session,
            settings=settings,
            user_id=user_id,
            run_id=run.id,
            goal_id=goal.id,
            budget=run.budget,
        )
        executor = ToolExecutor(build_tool_registry(), session)
        await executor.invoke("search_opportunities", {"query": "grant"}, ctx)
        await session.commit()

    async with factory() as session:
        refreshed = await session.get(AgentRun, run.id)
        assert refreshed is not None
        calls = (
            await session.execute(select(ToolCall).where(ToolCall.agent_run_id == run.id))
        ).scalars()
        rows = list(calls)
        assert len(rows) == 1
        assert rows[0].status == ToolCallStatus.SUCCEEDED


def test_mcp_conformance(tool_registry: ToolRegistry) -> None:
    check_mcp_conformance(tool_registry)
    tools = registry_to_mcp_tools(tool_registry)
    assert len(tools) == 15


def test_tool_benchmark_exit_criteria(tool_registry: ToolRegistry) -> None:
    assert selection_accuracy(tool_registry) >= 0.90
    assert argument_validity(tool_registry) >= 0.95
