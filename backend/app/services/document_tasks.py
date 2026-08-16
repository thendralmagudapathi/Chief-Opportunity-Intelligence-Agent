"""Background document indexing with a fresh database session."""

from __future__ import annotations

import uuid

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.session import get_session_factory
from app.retrieval.factory import build_retrieval_stack
from app.services.document_service import DocumentService

logger = get_logger(__name__)


async def index_document_background(document_id: uuid.UUID) -> None:
    settings = get_settings()
    factory = get_session_factory()
    async with factory() as session:
        stack = build_retrieval_stack(session, settings)
        service = DocumentService(session, stack, settings)
        await service.index_document(document_id)
        await session.commit()
        logger.info("document_background_index_complete", document_id=str(document_id))
