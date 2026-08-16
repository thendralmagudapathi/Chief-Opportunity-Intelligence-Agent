"""Application factory.

Composition root only: wiring, no business logic. Everything the application
does lives behind ``app.api``, ``app.services`` and ``app.agents``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.middleware import (
    RateLimitMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
)
from app.api.v1.router import api_router
from app.core.config import Environment, Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.db.constants import EMBEDDING_DIM
from app.db.session import dispose_engine

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    logger.info(
        "application_starting",
        version=settings.version,
        environment=str(settings.environment),
        database=settings.database.safe_url,
    )
    yield
    await dispose_engine()
    logger.info("application_stopped")


def _assert_schema_compatibility(settings: Settings) -> None:
    """Fail fast if runtime settings disagree with the physical schema.

    A mismatched embedding dimension would otherwise surface much later as
    silently unusable vectors.
    """
    if settings.rag.embedding_dim != EMBEDDING_DIM:
        raise RuntimeError(
            f"RAG__EMBEDDING_DIM={settings.rag.embedding_dim} does not match the schema "
            f"dimension {EMBEDDING_DIM}. Changing it requires a migration and a re-embed."
        )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)
    _assert_schema_compatibility(settings)

    app = FastAPI(
        title=settings.project_name,
        version=settings.version,
        description=(
            "Autonomous opportunity discovery, research, qualification, scoring and "
            "recommendation. See /docs for the interactive schema (development only)."
        ),
        docs_url=settings.docs_url,
        redoc_url=None,
        openapi_url=f"{settings.api_v1_prefix}/openapi.json",
        lifespan=lifespan,
    )
    app.state.settings = settings

    # Middleware executes in reverse registration order, so the request-context
    # middleware is registered last to make sure it wraps everything else and
    # every log line — including rate-limit rejections — carries a request id.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors.origins,
        allow_credentials=settings.cors.allow_credentials,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID", "Idempotency-Key"],
        expose_headers=["X-Request-ID", "X-Trace-ID"],
    )
    app.add_middleware(RateLimitMiddleware, settings=settings)
    app.add_middleware(
        SecurityHeadersMiddleware,
        enable_hsts=settings.environment is Environment.PRODUCTION,
    )
    app.add_middleware(RequestContextMiddleware)

    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    return app


app = create_app()
