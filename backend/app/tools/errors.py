"""Tool-layer errors.

These are converted into :class:`ToolOutcome` by the executor so failing tools
never leak raw exception text into agent context.
"""

from __future__ import annotations


class ToolError(Exception):
    code: str = "internal_error"

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class ToolArgumentError(ToolError):
    code = "invalid_arguments"


class ToolPermissionError(ToolError):
    code = "permission_denied"


class ToolBudgetError(ToolError):
    code = "budget_exhausted"


class ToolRateLimitError(ToolError):
    code = "rate_limited"


class ToolTimeoutError(ToolError):
    code = "timeout"


class ToolNotFoundError(ToolError):
    code = "not_found"
