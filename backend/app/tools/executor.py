"""Tool execution with permissions, budgets, tracing and error normalisation."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
import uuid
from typing import Any, cast

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, BudgetExhaustedError, ValidationError
from app.models.agent_run import ToolCall
from app.models.enums import ToolCallStatus, ToolTransport
from app.tools.base import BaseTool
from app.tools.context import ToolContext
from app.tools.errors import (
    ToolArgumentError,
    ToolBudgetError,
    ToolError,
    ToolNotFoundError,
    ToolPermissionError,
    ToolRateLimitError,
)
from app.tools.registry import ToolRegistry
from app.tools.types import ToolOutcome

_RESULT_MAX_CHARS = 8000


class ToolExecutor:
    def __init__(self, registry: ToolRegistry, session: AsyncSession) -> None:
        self.registry = registry
        self.session = session

    async def invoke(
        self,
        name: str,
        arguments: dict[str, Any],
        ctx: ToolContext,
        *,
        transport: ToolTransport = ToolTransport.NATIVE,
        task_id: uuid.UUID | None = None,
    ) -> ToolOutcome:
        started = time.monotonic()
        tool: BaseTool | None = None
        parsed_args: Any = None
        status = ToolCallStatus.FAILED
        error_message: str | None = None
        error_code: str | None = None
        result_payload: dict[str, Any] | None = None

        try:
            tool = self.registry.get(name)
        except KeyError:
            outcome = ToolOutcome(
                ok=False,
                error=f"Unknown tool: {name}",
                error_code="not_found",
            )
            await self._persist(
                ctx=ctx,
                tool_name=name,
                transport=transport,
                status=ToolCallStatus.FAILED,
                arguments=arguments,
                result=None,
                error=outcome.error,
                latency_ms=int((time.monotonic() - started) * 1000),
                task_id=task_id,
            )
            return outcome

        try:
            if ctx.budget is not None:
                ctx.budget.check_total()
                ctx.budget.check_tool(name, tool.max_calls_per_run)
            ctx.rate_limiter.check(name)
            tool.check_permission(ctx)
            parsed_args = tool.parse_args(arguments)
        except ToolPermissionError as exc:
            status = ToolCallStatus.DENIED
            error_code = "permission_denied"
            error_message = exc.message
        except (ToolBudgetError, BudgetExhaustedError) as exc:
            status = ToolCallStatus.DENIED
            error_code = "budget_exhausted"
            error_message = str(exc)
        except ToolRateLimitError as exc:
            status = ToolCallStatus.DENIED
            error_code = "rate_limited"
            error_message = exc.message
        except PydanticValidationError as exc:
            error_code = "invalid_arguments"
            error_message = "; ".join(err["msg"] for err in exc.errors())
        except ToolArgumentError as exc:
            error_code = "invalid_arguments"
            error_message = exc.message

        if error_message is not None:
            outcome = ToolOutcome(ok=False, error=error_message, error_code=error_code)
            await self._persist(
                ctx=ctx,
                tool_name=name,
                transport=transport,
                status=status,
                arguments=arguments,
                result=None,
                error=error_message,
                latency_ms=int((time.monotonic() - started) * 1000),
                task_id=task_id,
            )
            return outcome

        if tool is None or parsed_args is None:
            return ToolOutcome(
                ok=False,
                error="Internal tool dispatch error",
                error_code="internal_error",
            )

        attempts = tool.max_retries + 1
        last_error: str | None = None
        for attempt in range(attempts):
            try:
                raw = await asyncio.wait_for(tool.run(parsed_args, ctx), timeout=tool.timeout_s)
                result_payload = raw
                status = ToolCallStatus.SUCCEEDED
                if ctx.budget is not None:
                    ctx.budget.record(tool_name=name, cost_usd=tool.cost_usd)
                break
            except TimeoutError:
                status = ToolCallStatus.TIMEOUT
                error_code = "timeout"
                last_error = f"Tool timed out after {tool.timeout_s}s"
                break
            except ToolNotFoundError as exc:
                error_code = "not_found"
                last_error = exc.message
                break
            except (ToolError, ValidationError, AppError) as exc:
                error_code = getattr(exc, "code", "validation_error")
                last_error = getattr(exc, "message", str(exc))
                if attempt + 1 < attempts:
                    continue
                break
            except Exception:
                error_code = "internal_error"
                last_error = "Tool execution failed"
                break

        latency_ms = int((time.monotonic() - started) * 1000)
        if result_payload is not None:
            outcome = ToolOutcome(ok=True, data=result_payload)
        else:
            outcome = ToolOutcome(
                ok=False,
                error=last_error,
                error_code=cast(Any, error_code),
            )

        await self._persist(
            ctx=ctx,
            tool_name=name,
            transport=transport,
            status=status,
            arguments=arguments,
            result=result_payload,
            error=last_error,
            latency_ms=latency_ms,
            task_id=task_id,
            cost_usd=tool.cost_usd if result_payload is not None else 0.0,
        )
        return outcome

    async def _persist(
        self,
        *,
        ctx: ToolContext,
        tool_name: str,
        transport: ToolTransport,
        status: ToolCallStatus,
        arguments: dict[str, Any],
        result: dict[str, Any] | None,
        error: str | None,
        latency_ms: int,
        task_id: uuid.UUID | None,
        cost_usd: float = 0.0,
    ) -> None:
        if ctx.run_id is None:
            return
        stored_result, result_hash = _prepare_result(result)
        row = ToolCall(
            agent_run_id=ctx.run_id,
            agent_task_id=task_id or ctx.task_id,
            tool_name=tool_name,
            transport=transport,
            status=status,
            arguments=arguments,
            result=stored_result,
            result_hash=result_hash,
            error=error,
            latency_ms=latency_ms,
            cost_usd=cost_usd,
        )
        self.session.add(row)
        await self.session.flush()


def _prepare_result(result: dict[str, Any] | None) -> tuple[dict[str, Any] | None, str | None]:
    if result is None:
        return None, None
    encoded = json.dumps(result, sort_keys=True, default=str)
    result_hash = hashlib.sha256(encoded.encode()).hexdigest()
    if len(encoded) > _RESULT_MAX_CHARS:
        return {"truncated": True, "preview": encoded[:_RESULT_MAX_CHARS]}, result_hash
    return result, result_hash
