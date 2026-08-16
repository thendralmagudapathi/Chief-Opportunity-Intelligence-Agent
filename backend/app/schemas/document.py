"""Document upload and indexing payloads."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import DocumentStatus, DocumentType
from app.schemas.common import ORMModel


class DocumentRead(ORMModel):
    id: uuid.UUID
    filename: str
    content_type: str
    size_bytes: int
    doc_type: DocumentType
    status: DocumentStatus
    error: str | None = None
    parsed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class DocumentUploadResponse(BaseModel):
    document_id: uuid.UUID
    status: DocumentStatus


class DocumentListResponse(BaseModel):
    items: list[DocumentRead] = Field(default_factory=list)
