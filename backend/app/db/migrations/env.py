"""Alembic environment.

Runs against the async engine in online mode and renders SQL for the PostgreSQL
dialect in offline mode (``alembic upgrade head --sql``), which is how the
migration is verified without a running server.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection, pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.config import get_settings

# Importing the models package registers every mapper on Base.metadata, which
# is what makes autogenerate see the full schema.
from app.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database.url)


def _configure(connection: Connection | None = None, url: str | None = None) -> None:
    context.configure(
        connection=connection,
        url=url,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        # Server-side enums are emulated with VARCHAR + CHECK, so batch mode is
        # what makes constraint changes possible on SQLite in tests.
        render_as_batch=settings.database.is_sqlite,
        dialect_opts={"paramstyle": "named"},
    )


def run_migrations_offline() -> None:
    _configure(url=settings.database.url.replace("+asyncpg", "").replace("+aiosqlite", ""))
    with context.begin_transaction():
        context.run_migrations()


def _do_run(connection: Connection) -> None:
    _configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(_do_run)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
