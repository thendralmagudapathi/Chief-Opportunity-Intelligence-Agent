"""Document upload, storage and indexing."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models.document import Document
from app.models.enums import DocumentStatus, DocumentType
from app.retrieval.chunking import chunk_text
from app.retrieval.factory import RetrievalStack
from app.retrieval.parsing import allowed_extension, sniff_content_type

logger = get_logger(__name__)


class DocumentService:
    def __init__(self, session: AsyncSession, stack: RetrievalStack, settings: Settings) -> None:
        self.session = session
        self.stack = stack
        self.settings = settings

    async def upload(
        self,
        *,
        user_id: uuid.UUID,
        filename: str,
        data: bytes,
        doc_type: DocumentType = DocumentType.OTHER,
    ) -> Document:
        if len(data) > self.settings.security.max_upload_bytes:
            raise ValidationError(
                f"File exceeds the {self.settings.security.max_upload_bytes} byte upload limit"
            )
        if not allowed_extension(filename):
            raise ValidationError("Unsupported file type; allowed: pdf, docx, md, txt")

        content_type = sniff_content_type(filename, data)
        digest = hashlib.sha256(data).hexdigest()

        existing = await self._find_by_hash(user_id, digest)
        if existing is not None:
            return existing

        key = f"{user_id}/{digest}{Path(filename).suffix.lower()}"
        storage_uri = await self.stack.storage.put(key=key, data=data, content_type=content_type)

        document = Document(
            user_id=user_id,
            filename=Path(filename).name,
            content_type=content_type,
            size_bytes=len(data),
            storage_uri=storage_uri,
            sha256=digest,
            doc_type=doc_type,
            status=DocumentStatus.PENDING,
        )
        self.session.add(document)
        await self.session.flush()
        logger.info("document_uploaded", document_id=str(document.id), user_id=str(user_id))
        return document

    async def list_documents(self, user_id: uuid.UUID) -> list[Document]:
        result = await self.session.execute(
            select(Document).where(Document.user_id == user_id).order_by(Document.created_at.desc())
        )
        return list(result.scalars())

    async def get_document(self, user_id: uuid.UUID, document_id: uuid.UUID) -> Document:
        document = await self.session.get(Document, document_id)
        if document is None or document.user_id != user_id:
            raise NotFoundError("Document not found")
        return document

    async def delete_document(self, user_id: uuid.UUID, document_id: uuid.UUID) -> None:
        document = await self.get_document(user_id, document_id)
        await self.stack.vector_store.delete_document(user_id=user_id, document_id=document.id)
        await self.stack.storage.delete(uri=document.storage_uri)
        await self.session.delete(document)
        await self.session.flush()

    async def index_document(self, document_id: uuid.UUID) -> None:
        document = await self.session.get(Document, document_id)
        if document is None:
            return

        document.status = DocumentStatus.PARSING
        document.error = None
        await self.session.flush()

        try:
            raw = await self.stack.storage.get(uri=document.storage_uri)
            parsed = self.stack.parser.parse(
                raw, filename=document.filename, content_type=document.content_type
            )
            chunks = chunk_text(
                parsed.text,
                max_tokens=self.settings.rag.chunk_size_tokens,
                overlap_tokens=self.settings.rag.chunk_overlap_tokens,
            )
            if not chunks:
                raise ValidationError("Document produced no indexable chunks")

            vectors = await self.stack.embedder.embed([chunk.content for chunk in chunks])
            await self.stack.vector_store.upsert_chunks(
                user_id=document.user_id,
                document_id=document.id,
                chunks=[
                    (chunk.index, chunk.content, vector, chunk.meta)
                    for chunk, vector in zip(chunks, vectors, strict=True)
                ],
                embedding_model=self.stack.embedder.model_name,
            )
            document.status = DocumentStatus.INDEXED
            document.parsed_at = datetime.now(UTC)
            document.error = None
            logger.info("document_indexed", document_id=str(document.id), chunks=len(chunks))
        except Exception as exc:
            document.status = DocumentStatus.FAILED
            document.error = str(exc)
            logger.warning("document_index_failed", document_id=str(document.id), error=str(exc))
        await self.session.flush()

    async def _find_by_hash(self, user_id: uuid.UUID, digest: str) -> Document | None:
        result = await self.session.execute(
            select(Document).where(Document.user_id == user_id, Document.sha256 == digest)
        )
        return result.scalar_one_or_none()
