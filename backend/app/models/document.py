"""Personal knowledge base documents and their indexed chunks."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.constants import EMBEDDING_DIM
from app.db.types import Vector
from app.models.enums import DocumentStatus, DocumentType, enum_column

if TYPE_CHECKING:
    from app.models.user import User


class Document(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Metadata only — the bytes live in object storage, keyed by ``storage_uri``."""

    __tablename__ = "documents"
    __table_args__ = (
        # Re-uploading the same file is idempotent per user.
        UniqueConstraint("user_id", "sha256", name="uq_documents_user_id_sha256"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_uri: Mapped[str] = mapped_column(String(1024), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)

    doc_type: Mapped[DocumentType] = mapped_column(
        enum_column(DocumentType, "document_type"), default=DocumentType.OTHER, nullable=False
    )
    status: Mapped[DocumentStatus] = mapped_column(
        enum_column(DocumentStatus, "document_status"),
        default=DocumentStatus.PENDING,
        nullable=False,
    )
    error: Mapped[str | None] = mapped_column(Text)
    parsed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    meta: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)

    user: Mapped[User] = relationship(back_populates="documents")
    chunks: Mapped[list[DocumentChunk]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class DocumentChunk(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A retrievable unit of the private profile index.

    ``user_id`` is denormalised so every vector query can carry a
    ``WHERE user_id = :uid`` predicate in SQL rather than post-filtering ANN
    results (docs/SECURITY_MODEL.md §7).
    """

    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint(
            "document_id", "chunk_index", name="uq_document_chunks_document_id_chunk_index"
        ),
        Index("ix_document_chunks_user_id_document_id", "user_id", "document_id"),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int | None] = mapped_column(Integer)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    embedding_model: Mapped[str | None] = mapped_column(String(128))
    meta: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)

    document: Mapped[Document] = relationship(back_populates="chunks")
