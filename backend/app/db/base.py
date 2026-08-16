"""Declarative base, naming conventions and shared mixins."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, ClassVar

from sqlalchemy import DateTime, MetaData, String, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.db.types import JSONColumn

# Deterministic constraint names so Alembic can always emit a matching
# ``downgrade`` and so ``ALTER``s never depend on database-generated names.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    type_annotation_map: ClassVar[dict[Any, Any]] = {
        dict[str, Any]: JSONColumn,
        list[Any]: JSONColumn,
        datetime: DateTime(timezone=True),
        str: String(255),
    }

    def __repr__(self) -> str:
        ident = getattr(self, "id", None)
        return f"<{type(self).__name__} id={ident}>"


class UUIDPrimaryKeyMixin:
    """Application-generated UUID primary key.

    Generated in Python so a row can be referenced (in evidence, events and
    traces) before the transaction commits.
    """

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)


def utcnow() -> datetime:
    return datetime.now(UTC)


class TimestampMixin:
    """Creation and modification timestamps.

    Both a Python-side ``default`` and a ``server_default`` are set. The server
    default protects rows written by raw SQL; the Python default is what makes
    the value available immediately after ``flush()`` and guarantees microsecond
    precision on every backend — SQLite's ``CURRENT_TIMESTAMP`` only has second
    resolution, which breaks timestamp-based keyset pagination.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        server_default=func.now(),
        nullable=False,
    )
