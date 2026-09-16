"""Document intelligence: upload, ingest, inspect, reprocess, delete."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy import or_, select

from app.core.config import settings
from app.core.db import utcnow
from app.core.deps import DbSession, require_permission
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.pagination import Page, PageParams, apply_sort, page_params, paginate
from app.db.models import Document, DocumentChunk, User
from app.providers.registry import get_blob_store, get_vector_store
from app.schemas import ChunkOut, DocumentDetail, DocumentOut
from app.services import audit
from app.services.rag import checksum, ingest_document, resolve_pipeline

router = APIRouter(prefix="/documents", tags=["documents"])


def _validate_upload(file: UploadFile, data: bytes) -> None:
    if not data:
        raise ValidationError("Uploaded file is empty.")
    if len(data) > settings.max_upload_bytes:
        raise ValidationError(
            f"File exceeds the {settings.max_upload_bytes // (1024 * 1024)} MB limit."
        )
    name = file.filename or ""
    suffix = ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""
    if suffix not in settings.allowed_upload_extensions:
        raise ValidationError(
            f"Unsupported file type '{suffix or 'unknown'}'. Allowed: "
            + ", ".join(settings.allowed_upload_extensions)
        )
    # Reject path separators and traversal in the client-supplied filename.
    if "/" in name or "\\" in name or ".." in name:
        raise ValidationError("Filename must not contain path separators.")
    # Integration point: hand `data` to a malware scanner before persisting.


@router.get("", response_model=Page[DocumentOut])
def list_documents(
    db: DbSession,
    params: PageParams = Depends(page_params),
    status_filter: str | None = None,
    _: User = Depends(require_permission("documents:read")),
) -> Page[DocumentOut]:
    stmt = select(Document).where(Document.deleted_at.is_(None))
    if status_filter:
        stmt = stmt.where(Document.status == status_filter)
    if params.q:
        needle = f"%{params.q.lower()}%"
        stmt = stmt.where(
            or_(Document.filename.ilike(needle), Document.extracted_text.ilike(needle))
        )
    stmt = apply_sort(stmt, Document, params, "created_at")
    rows, total = paginate(db, stmt, params)
    return Page.build([DocumentOut.model_validate(row) for row in rows], total, params)


@router.post("", response_model=DocumentDetail, status_code=status.HTTP_201_CREATED)
async def upload_document(
    db: DbSession,
    file: UploadFile = File(...),
    tags: str = Form(default=""),
    pipeline_id: uuid.UUID | None = Form(default=None),
    user: User = Depends(require_permission("documents:write")),
) -> DocumentDetail:
    data = await file.read()
    _validate_upload(file, data)

    digest = checksum(data)
    existing = db.execute(
        select(Document).where(Document.checksum == digest, Document.deleted_at.is_(None))
    ).scalar_one_or_none()
    if existing:
        raise ConflictError(
            f"An identical document is already indexed as '{existing.filename}'."
        )

    pipeline = resolve_pipeline(db, pipeline_id)
    document = Document(
        filename=file.filename or "upload.txt",
        content_type=file.content_type or "application/octet-stream",
        size_bytes=len(data),
        checksum=digest,
        status="pending",
        tags=[t.strip() for t in tags.split(",") if t.strip()],
        pipeline_id=pipeline.id,
        uploaded_by=user.id,
    )
    db.add(document)
    db.flush()

    store = get_blob_store()
    document.storage_uri = store.put(
        f"documents/{document.id}/{document.filename}", data, document.content_type
    )

    try:
        ingest_document(db, document, data, pipeline=pipeline)
        outcome = "success"
    except Exception:
        outcome = "failure"  # document.status is already 'failed' with the reason

    audit.record(
        db,
        action="document.upload",
        resource_type="document",
        resource_id=document.id,
        actor=user,
        outcome=outcome,
        changes={"filename": document.filename, "bytes": len(data)},
    )
    db.commit()
    db.refresh(document)
    return _detail(document)


def _detail(document: Document) -> DocumentDetail:
    payload = DocumentDetail.model_validate(document)
    payload.extracted_text_preview = (document.extracted_text or "")[:4000] or None
    return payload


@router.get("/{document_id}", response_model=DocumentDetail)
def get_document(
    document_id: uuid.UUID,
    db: DbSession,
    _: User = Depends(require_permission("documents:read")),
) -> DocumentDetail:
    document = db.get(Document, document_id)
    if document is None or document.deleted_at is not None:
        raise NotFoundError("Document not found.")
    return _detail(document)


@router.get("/{document_id}/chunks", response_model=Page[ChunkOut])
def list_chunks(
    document_id: uuid.UUID,
    db: DbSession,
    params: PageParams = Depends(page_params),
    _: User = Depends(require_permission("documents:read")),
) -> Page[ChunkOut]:
    document = db.get(Document, document_id)
    if document is None or document.deleted_at is not None:
        raise NotFoundError("Document not found.")
    stmt = (
        select(DocumentChunk)
        .where(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.ordinal.asc())
    )
    rows, total = paginate(db, stmt, params)
    return Page.build([ChunkOut.model_validate(row) for row in rows], total, params)


@router.post("/{document_id}/reprocess", response_model=DocumentDetail)
def reprocess_document(
    document_id: uuid.UUID,
    db: DbSession,
    user: User = Depends(require_permission("documents:write")),
) -> DocumentDetail:
    document = db.get(Document, document_id)
    if document is None or document.deleted_at is not None:
        raise NotFoundError("Document not found.")
    if not document.storage_uri:
        raise ValidationError("Original file is no longer available for reprocessing.")

    store = get_blob_store()
    data = store.get(f"documents/{document.id}/{document.filename}")
    document.version += 1
    try:
        ingest_document(db, document, data)
        outcome = "success"
    except Exception:
        outcome = "failure"

    audit.record(
        db,
        action="document.reprocess",
        resource_type="document",
        resource_id=document.id,
        actor=user,
        outcome=outcome,
        changes={"version": document.version},
    )
    db.commit()
    db.refresh(document)
    return _detail(document)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: uuid.UUID,
    db: DbSession,
    user: User = Depends(require_permission("documents:delete")),
) -> None:
    document = db.get(Document, document_id)
    if document is None or document.deleted_at is not None:
        raise NotFoundError("Document not found.")

    get_vector_store(db).delete_by_document(str(document.id))
    try:
        get_blob_store().delete(f"documents/{document.id}/{document.filename}")
    except Exception:  # storage cleanup must not block the soft delete
        pass

    document.deleted_at = utcnow()
    document.status = "deleted"
    audit.record(
        db,
        action="document.delete",
        resource_type="document",
        resource_id=document.id,
        actor=user,
        changes={"filename": document.filename},
    )
    db.commit()
