"""Async engine and session lifecycle."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings, get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _engine_kwargs(settings: Settings) -> dict[str, Any]:
    db = settings.database
    if db.is_sqlite:
        # SQLite (tests) has no server-side pool to tune and rejects the
        # PostgreSQL-specific connect args.
        return {"echo": db.echo}
    return {
        "echo": db.echo,
        "pool_size": db.pool_size,
        "max_overflow": db.max_overflow,
        "pool_timeout": db.pool_timeout_s,
        "pool_recycle": db.pool_recycle_s,
        "pool_pre_ping": True,
        "connect_args": {"timeout": db.connect_timeout_s},
    }


def create_engine(settings: Settings | None = None) -> AsyncEngine:
    s = settings or get_settings()
    return create_async_engine(s.database.url, **_engine_kwargs(s))


def get_engine(settings: Settings | None = None) -> AsyncEngine:
    global _engine
    if _engine is None:
        s = settings or get_settings()
        _engine = create_engine(s)
        logger.info("database_engine_created", url=s.database.safe_url)
    return _engine


def get_session_factory(settings: Settings | None = None) -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(settings),
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_factory


async def dispose_engine() -> None:
    """Close pooled connections on shutdown."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        logger.info("database_engine_disposed")
    _engine = None
    _session_factory = None


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a session with request-scoped transaction.

    The request handler owns the unit of work: a handler that raises leaves the
    transaction rolled back, and services never commit on their own.
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
