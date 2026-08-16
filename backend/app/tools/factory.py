"""Construct the process-wide tool registry and executor."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.context import RunContext
from app.core.config import Settings
from app.security.egress import SafeHttpClient
from app.tools.budget import ToolBudget
from app.tools.context import ToolContext
from app.tools.executor import ToolExecutor
from app.tools.native import NATIVE_TOOLS
from app.tools.permissions import DEFAULT_INVESTIGATION_SCOPES
from app.tools.rate_limit import ToolRateLimiter
from app.tools.registry import ToolRegistry

_registry: ToolRegistry | None = None


def build_tool_registry() -> ToolRegistry:
    global _registry
    if _registry is None:
        instances = [tool_cls() for tool_cls in NATIVE_TOOLS]
        _registry = ToolRegistry.from_instances(instances)
    return _registry


def build_tool_executor(session: AsyncSession) -> ToolExecutor:
    return ToolExecutor(build_tool_registry(), session)


def build_tool_context(
    *,
    session: AsyncSession,
    settings: Settings,
    user_id: uuid.UUID,
    run_id: uuid.UUID | None = None,
    goal_id: uuid.UUID | None = None,
    budget: dict[str, object] | None = None,
    granted_scopes: frozenset[str] | None = None,
) -> ToolContext:
    return ToolContext(
        session=session,
        settings=settings,
        user_id=user_id,
        run_id=run_id,
        goal_id=goal_id,
        granted_scopes=granted_scopes or DEFAULT_INVESTIGATION_SCOPES,
        budget=ToolBudget.from_run_budget(budget or {}) if budget is not None else None,
        rate_limiter=ToolRateLimiter(
            per_tool_limit={
                "search_web": settings.egress.host_rate_limit_per_minute,
                "research_company": settings.egress.host_rate_limit_per_minute,
            }
        ),
        http=SafeHttpClient(settings),
    )


def attach_tools(
    ctx: RunContext,
    *,
    budget: dict[str, object] | None = None,
    goal_id: uuid.UUID | None = None,
) -> tuple[ToolContext, ToolExecutor]:
    tool_ctx = build_tool_context(
        session=ctx.session,
        settings=ctx.settings,
        user_id=ctx.user_id,
        run_id=ctx.run_id,
        goal_id=goal_id,
        budget=budget,
    )
    executor = build_tool_executor(ctx.session)
    return tool_ctx, executor
