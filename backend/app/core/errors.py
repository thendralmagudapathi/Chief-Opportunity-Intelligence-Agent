"""Error contract.

One exception hierarchy, one response shape (RFC 9457 flavoured), no stack
traces on the wire. Handlers are registered in ``app.main``.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.context import get_request_id
from app.core.logging import get_logger

logger = get_logger(__name__)


class AppError(Exception):
    """Base class for every error the application raises deliberately."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_type: str = "internal_error"
    title: str = "Internal server error"

    def __init__(self, detail: str | None = None, **extra: Any) -> None:
        self.detail = detail or self.title
        self.extra = extra
        super().__init__(self.detail)


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    error_type = "not_found"
    title = "Resource not found"


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    error_type = "conflict"
    title = "Conflicting request"


class ValidationError(AppError):
    # Literal 422 rather than a Starlette constant: the constant was renamed
    # between versions and this contract must not move with the framework.
    status_code = 422
    error_type = "validation_error"
    title = "Request validation failed"


class AuthenticationError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    error_type = "unauthenticated"
    title = "Authentication required"


class PermissionDeniedError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    error_type = "permission_denied"
    title = "Permission denied"


class RateLimitedError(AppError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    error_type = "rate_limited"
    title = "Too many requests"

    def __init__(self, detail: str | None = None, retry_after_s: int = 60) -> None:
        super().__init__(detail)
        self.retry_after_s = retry_after_s


class DependencyUnavailableError(AppError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    error_type = "dependency_unavailable"
    title = "A required dependency is unavailable"


class BudgetExhaustedError(AppError):
    """Raised when an agent run exceeds its declared budget (docs/AGENT_DESIGN.md §6)."""

    status_code = status.HTTP_402_PAYMENT_REQUIRED
    error_type = "budget_exhausted"
    title = "Investigation budget exhausted"


def problem_response(
    *,
    status_code: int,
    error_type: str,
    title: str,
    detail: str,
    instance: str,
    errors: list[dict[str, str]] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": error_type,
        "title": title,
        "status": status_code,
        "detail": detail,
        "instance": instance,
        "trace_id": get_request_id(),
    }
    if errors:
        body["errors"] = errors
    return JSONResponse(status_code=status_code, content=body, headers=headers)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        headers = None
        if isinstance(exc, RateLimitedError):
            headers = {"Retry-After": str(exc.retry_after_s)}
        if exc.status_code >= 500:
            logger.error("app_error", error_type=exc.error_type, detail=exc.detail, exc_info=exc)
        else:
            logger.info("app_error", error_type=exc.error_type, detail=exc.detail)
        return problem_response(
            status_code=exc.status_code,
            error_type=exc.error_type,
            title=exc.title,
            detail=exc.detail,
            instance=request.url.path,
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {"field": ".".join(str(p) for p in err["loc"]), "message": err["msg"]}
            for err in exc.errors()
        ]
        return problem_response(
            status_code=ValidationError.status_code,
            error_type="validation_error",
            title="Request validation failed",
            detail=f"{len(errors)} field(s) failed validation",
            instance=request.url.path,
            errors=errors,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return problem_response(
            status_code=exc.status_code,
            error_type="http_error",
            title=str(exc.detail),
            detail=str(exc.detail),
            instance=request.url.path,
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # The message is intentionally generic; the trace id is the only handle
        # the client gets, and it correlates with the full server-side log.
        logger.error("unhandled_exception", path=request.url.path, exc_info=exc)
        return problem_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_type="internal_error",
            title="Internal server error",
            detail="An unexpected error occurred. Quote the trace id when reporting this.",
            instance=request.url.path,
        )
