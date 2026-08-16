"""Long-term memory with provenance.

Memory is bitemporal-lite: a contradicted fact is closed off with ``valid_to``
and linked via ``superseded_by_id``. Nothing is ever silently overwritten, which
is what keeps memory from quietly rewriting the evidence base.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.constants import EMBEDDING_DIM
from app.db.types import Vector
from app.models.enums import MemoryType, enum_column

if TYPE_CHECKING:
    from app.models.user import User


class MemoryRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "memory_records"
    __table_args__ = (
        Index(
            "ix_memory_records_user_id_memory_type_valid_to", "user_id", "memory_type", "valid_to"
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    memory_type: Mapped[MemoryType] = mapped_column(
        enum_column(MemoryType, "memory_type"), nullable=False
    )
    key: Mapped[str | None] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))

    importance: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    provenance: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)
    source_ref: Mapped[str | None] = mapped_column(String(255))

    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: NULL means "currently believed".
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("memory_records.id", ondelete="SET NULL")
    )

    user: Mapped[User] = relationship(back_populates="memories")
