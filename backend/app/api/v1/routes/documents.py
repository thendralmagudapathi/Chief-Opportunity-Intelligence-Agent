"""Profile document upload and management."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, File, UploadFile, status

from app.api.deps import CurrentUser, DocumentServiceDep
from app.models.enums import DocumentStatus, DocumentType
from app.schemas.document import DocumentListResponse, DocumentRead, DocumentUploadResponse
from app.services.document_tasks import index_document_background

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post(
    "",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a profile document for indexing",
)
async def upload_document(
    background: BackgroundTasks,
    user: CurrentUser,
    documents: DocumentServiceDep,
    file: UploadFile = File(...),
    doc_type: DocumentType = DocumentType.OTHER,
) -> DocumentUploadResponse:
    data = await file.read()
    document = await documents.upload(
        user_id=user.id,
        filename=file.filename or "upload.txt",
        data=data,
        doc_type=doc_type,
    )
    if document.status in (DocumentStatus.PENDING, DocumentStatus.FAILED):
        background.add_task(index_document_background, document.id)
    return DocumentUploadResponse(document_id=document.id, status=document.status)


@router.get("", response_model=DocumentListResponse, summary="List uploaded documents")
async def list_documents(user: CurrentUser, documents: DocumentServiceDep) -> DocumentListResponse:
    rows = await documents.list_documents(user.id)
    return DocumentListResponse(items=[DocumentRead.model_validate(row) for row in rows])


@router.get("/{document_id}", response_model=DocumentRead, summary="Document metadata")
async def get_document(
    document_id: uuid.UUID, user: CurrentUser, documents: DocumentServiceDep
) -> DocumentRead:
    row = await documents.get_document(user.id, document_id)
    return DocumentRead.model_validate(row)


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a document and its indexed chunks",
)
async def delete_document(
    document_id: uuid.UUID, user: CurrentUser, documents: DocumentServiceDep
) -> None:
    await documents.delete_document(user.id, document_id)
