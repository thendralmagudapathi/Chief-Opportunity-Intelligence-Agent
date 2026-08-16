"""Schema drift check.

The migration is the source of truth for the physical schema and the ORM is the
source of truth for the code. This test asserts they agree, which is the failure
mode that otherwise shows up only in production.
"""

from __future__ import annotations

from app.db.base import Base
from app.models import *  # noqa: F403  (registers every mapper)
from sqlalchemy import create_engine, inspect

IGNORED_TABLES = {"alembic_version"}


def _sync_url(async_url: str) -> str:
    return async_url.replace("+aiosqlite", "").replace("+asyncpg", "")


def test_migrated_schema_matches_orm_metadata(database_url: str) -> None:
    engine = create_engine(_sync_url(database_url))
    try:
        inspector = inspect(engine)
        migrated_tables = set(inspector.get_table_names()) - IGNORED_TABLES
        expected_tables = set(Base.metadata.tables)

        assert migrated_tables == expected_tables, (
            f"missing from migration: {sorted(expected_tables - migrated_tables)}; "
            f"unexpected in database: {sorted(migrated_tables - expected_tables)}"
        )

        for table_name in sorted(expected_tables):
            migrated_columns = {c["name"] for c in inspector.get_columns(table_name)}
            expected_columns = set(Base.metadata.tables[table_name].columns.keys())
            assert migrated_columns == expected_columns, (
                f"{table_name}: missing {sorted(expected_columns - migrated_columns)}, "
                f"unexpected {sorted(migrated_columns - expected_columns)}"
            )
    finally:
        engine.dispose()


def test_every_table_has_a_primary_key(database_url: str) -> None:
    engine = create_engine(_sync_url(database_url))
    try:
        inspector = inspect(engine)
        for table_name in set(inspector.get_table_names()) - IGNORED_TABLES:
            pk = inspector.get_pk_constraint(table_name)
            assert pk["constrained_columns"], f"{table_name} has no primary key"
    finally:
        engine.dispose()


def test_expected_entity_count(database_url: str) -> None:
    """A blunt guard against a table being dropped from the migration by mistake."""
    engine = create_engine(_sync_url(database_url))
    try:
        tables = set(inspect(engine).get_table_names()) - IGNORED_TABLES
        assert len(tables) == 18, sorted(tables)
    finally:
        engine.dispose()
