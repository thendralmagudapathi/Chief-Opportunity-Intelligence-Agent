"""HTTP middleware: request identity, access logging, security headers, rate limiting."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from typing import Protocol

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.core.config import Settings
from app.core.context import get_request_id, new_request_id, set_request_id
from app.core.errors import problem_response
from app.core.logging import bind_contextvars, clear_contextvars, get_logger

logger = get_logger(__name__)

RequestHandler = Callable[[Request], Awaitable[Response]]

REQUEST_ID_HEADER = "X-Request-ID"
TRACE_ID_HEADER = "X-Trace-ID"


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assign a request id, bind it to the log context and echo it back.

    An inbound ``X-Request-ID`` is honoured but sanitised, so a client can
    correlate its own traces without being able to inject log content.
    """

    async def dispatch(self, request: Request, call_next: RequestHandler) -> Response:
        inbound = request.headers.get(REQUEST_ID_HEADER, "")
        request_id = inbound if inbound.isalnum() and len(inbound) <= 64 else new_request_id()

        set_request_id(request_id)
        clear_contextvars()
        bind_contextvars(request_id=request_id)
        request.state.request_id = request_id

        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            # The exception handler produces the response; we only record timing
            # here so that failed requests still appear in the access log.
            logger.exception(
                "request_failed",
                method=request.method,
                path=request.url.path,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )
            raise
        finally:
            clear_contextvars()

        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        response.headers[REQUEST_ID_HEADER] = request_id
        response.headers[TRACE_ID_HEADER] = request_id

        # Health probes are high-frequency and uninteresting at INFO.
        log = logger.debug if request.url.path.endswith(("/live", "/ready")) else logger.info
        log(
            "request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=duration_ms,
        )
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Baseline hardening headers.

    CSP is intentionally restrictive: the API serves JSON only, and the docs UI
    is disabled outside development (see ``Settings.docs_url``).
    """

    def __init__(self, app: ASGIApp, *, enable_hsts: bool) -> None:
        super().__init__(app)
        self.enable_hsts = enable_hsts

    async def dispatch(self, request: Request, call_next: RequestHandler) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.headers.setdefault(
            "Permissions-Policy", "geolocation=(), microphone=(), camera=()"
        )
        if not request.url.path.startswith(("/docs", "/redoc")):
            response.headers.setdefault("Content-Security-Policy", "default-src 'none'")
        if self.enable_hsts:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response


class RateLimiterBackend(Protocol):
    """Pluggable so the in-memory limiter can be swapped for Redis in production."""

    async def hit(self, key: str, limit: int, window_s: int) -> tuple[bool, int]:
        """Record a hit. Returns ``(allowed, retry_after_seconds)``."""
        ...


class InMemoryRateLimiter:
    """Sliding-window counter.

    Correct for a single process only; production uses the Redis backend so the
    window is shared across replicas.
    """

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    async def hit(self, key: str, limit: int, window_s: int) -> tuple[bool, int]:
        now = time.monotonic()
        window = self._hits[key]
        cutoff = now - window_s
        while window and window[0] <= cutoff:
            window.popleft()

        if len(window) >= limit:
            retry_after = max(1, int(window[0] + window_s - now) + 1)
            return False, retry_after

        window.append(now)
        return True, 0


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-identity sliding-window limiting with a tighter bucket for auth routes.

    Identity is the bearer token subject when present, otherwise the client IP.
    Authentication endpoints get their own, much smaller budget because they are
    the credential-stuffing surface.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        settings: Settings,
        backend: RateLimiterBackend | None = None,
    ) -> None:
        super().__init__(app)
        self.settings = settings
        self.backend = backend or InMemoryRateLimiter()
        self._auth_paths = (
            f"{settings.api_v1_prefix}/auth/login",
            f"{settings.api_v1_prefix}/auth/register",
        )

    def _identity(self, request: Request) -> str:
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            # Hash-free short prefix: enough to separate callers, never logged.
            return f"tok:{hash(auth[7:]) & 0xFFFFFFFF:08x}"
        client = request.client
        return f"ip:{client.host}" if client else "ip:unknown"

    async def dispatch(self, request: Request, call_next: RequestHandler) -> Response:
        cfg = self.settings.security
        if not cfg.rate_limit_enabled or request.url.path.endswith(("/live", "/ready")):
            return await call_next(request)

        is_auth = request.url.path in self._auth_paths
        limit = cfg.auth_rate_limit_requests if is_auth else cfg.rate_limit_requests
        bucket = "auth" if is_auth else "api"
        key = f"{bucket}:{self._identity(request)}"

        allowed, retry_after = await self.backend.hit(key, limit, cfg.rate_limit_window_s)
        if not allowed:
            logger.warning("rate_limited", path=request.url.path, bucket=bucket)
            return problem_response(
                status_code=429,
                error_type="rate_limited",
                title="Too many requests",
                detail=f"Rate limit of {limit} requests per {cfg.rate_limit_window_s}s exceeded",
                instance=request.url.path,
                headers={"Retry-After": str(retry_after), REQUEST_ID_HEADER: get_request_id()},
            )
        return await call_next(request)
