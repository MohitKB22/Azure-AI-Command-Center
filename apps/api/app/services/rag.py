"""RAG engine: ingestion, retrieval, reranking and context assembly."""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.db.models import Document, DocumentChunk, RagPipeline
from app.providers.base import VectorRecord
from app.providers.embeddings import tokenize
from app.providers.registry import get_embedder, get_vector_store
from app.services.chunking import chunk_text, extract_text

logger = get_logger(__name__)


@dataclass(slots=True)
class RetrievedChunk:
    chunk_id: str
    document_id: str
    document_name: str
    ordinal: int
    page: int | None
    content: str
    score: float
    rerank_score: float | None = None

    def citation(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "document_name": self.document_name,
            "page": self.page,
            "ordinal": self.ordinal,
            "score": round(self.score, 4),
            "snippet": self.content[:240],
        }


@dataclass(slots=True)
class RetrievalResult:
    query: str
    chunks: list[RetrievedChunk] = field(default_factory=list)
    candidates_considered: int = 0
    latency_ms: int = 0
    pipeline: dict[str, Any] = field(default_factory=dict)
    stages: list[dict[str, Any]] = field(default_factory=list)

    @property
    def citations(self) -> list[dict[str, Any]]:
        return [chunk.citation() for chunk in self.chunks]


def default_pipeline(db: Session) -> RagPipeline:
    pipeline = db.execute(
        select(RagPipeline).where(
            RagPipeline.is_default.is_(True), RagPipeline.deleted_at.is_(None)
        )
    ).scalar_one_or_none()
    if pipeline:
        return pipeline
    pipeline = db.execute(
        select(RagPipeline).where(RagPipeline.deleted_at.is_(None)).limit(1)
    ).scalar_one_or_none()
    if pipeline:
        return pipeline
    pipeline = RagPipeline(
        name="Default Pipeline",
        description="Created automatically because no pipeline existed.",
        chunk_size=settings.default_chunk_size,
        chunk_overlap=settings.default_chunk_overlap,
        top_k=settings.default_top_k,
        similarity_threshold=settings.default_similarity_threshold,
        is_default=True,
    )
    db.add(pipeline)
    db.flush()
    return pipeline


def resolve_pipeline(db: Session, pipeline_id: uuid.UUID | None) -> RagPipeline:
    if pipeline_id is None:
        return default_pipeline(db)
    pipeline = db.get(RagPipeline, pipeline_id)
    if pipeline is None or pipeline.deleted_at is not None:
        raise NotFoundError("RAG pipeline not found.")
    return pipeline


# ------------------------------------------------------------------ ingestion


def checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def ingest_document(
    db: Session,
    document: Document,
    raw: bytes,
    *,
    pipeline: RagPipeline | None = None,
) -> Document:
    """Run the full ingestion pipeline for one document.

    Stages: extract -> normalise -> chunk -> embed -> index. Any failure marks
    the document `failed` with the reason instead of leaving it stuck.
    """
    pipeline = pipeline or resolve_pipeline(db, document.pipeline_id)
    started = time.perf_counter()
    document.status = "processing"
    document.error_message = None
    db.flush()

    try:
        extracted = extract_text(raw, document.filename, document.content_type)
        if not extracted.text.strip():
            raise ValidationError(
                "No text could be extracted. Scanned documents require OCR, which is "
                "an integration point rather than a built-in capability."
            )

        document.extracted_text = extracted.text
        document.page_count = extracted.page_count
        if extracted.warnings:
            document.doc_metadata = {
                **(document.doc_metadata or {}),
                "warnings": extracted.warnings,
            }

        # Replace any previous chunks: reprocessing must be idempotent.
        for existing in list(document.chunks):
            db.delete(existing)
        db.flush()

        pieces = chunk_text(
            extracted.text,
            chunk_size=pipeline.chunk_size,
            chunk_overlap=pipeline.chunk_overlap,
        )
        if not pieces:
            raise ValidationError("Document produced no chunks after cleaning.")

        embedder = get_embedder()
        vectors = embedder.embed([piece.content for piece in pieces])

        chunk_rows: list[DocumentChunk] = []
        for piece, vector in zip(pieces, vectors.vectors, strict=True):
            chunk_rows.append(
                DocumentChunk(
                    document_id=document.id,
                    ordinal=piece.ordinal,
                    content=piece.content,
                    token_estimate=piece.token_estimate,
                    page=piece.page,
                    embedding=vector,
                    embedding_model=vectors.model,
                    chunk_metadata={"pipeline": pipeline.name},
                )
            )
        db.add_all(chunk_rows)
        db.flush()

        store = get_vector_store(db)
        store.upsert(
            [
                VectorRecord(
                    id=str(row.id),
                    vector=row.embedding or [],
                    payload={
                        "document_id": str(document.id),
                        "document_name": document.filename,
                        "ordinal": row.ordinal,
                        "page": row.page,
                        "content": row.content,
                        "embedding_model": vectors.model,
                        "tags": document.tags,
                    },
                )
                for row in chunk_rows
            ]
        )

        document.chunk_count = len(chunk_rows)
        document.status = "indexed"
        document.indexed_at = datetime.now(timezone.utc)
        document.pipeline_id = pipeline.id
        db.flush()

        logger.info(
            "document_indexed",
            extra={
                "document_id": str(document.id),
                "chunks": len(chunk_rows),
                "duration_ms": int((time.perf_counter() - started) * 1000),
            },
        )
        return document

    except Exception as exc:
        document.status = "failed"
        document.error_message = str(exc)[:500]
        document.chunk_count = 0
        db.flush()
        logger.warning(
            "document_ingest_failed",
            extra={"document_id": str(document.id), "reason": str(exc)[:200]},
        )
        raise


# ------------------------------------------------------------------ retrieval


def _lexical_overlap(query: str, content: str) -> float:
    query_terms = set(tokenize(query))
    if not query_terms:
        return 0.0
    content_terms = set(tokenize(content))
    return len(query_terms & content_terms) / len(query_terms)


def rerank(query: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    """Blend vector score with lexical overlap.

    A cross-encoder would be better; this is a deterministic, dependency-free
    reranker that measurably improves ordering for keyword-heavy queries.
    """
    for chunk in chunks:
        overlap = _lexical_overlap(query, chunk.content)
        chunk.rerank_score = round(0.65 * chunk.score + 0.35 * overlap, 6)
    return sorted(chunks, key=lambda c: c.rerank_score or 0.0, reverse=True)


def retrieve(
    db: Session,
    query: str,
    *,
    pipeline: RagPipeline | None = None,
    top_k: int | None = None,
    similarity_threshold: float | None = None,
    filters: dict[str, Any] | None = None,
    use_reranking: bool | None = None,
) -> RetrievalResult:
    query = (query or "").strip()
    if not query:
        raise ValidationError("Query must not be empty.")

    pipeline = pipeline or default_pipeline(db)
    top_k = top_k or pipeline.top_k
    threshold = (
        pipeline.similarity_threshold if similarity_threshold is None else similarity_threshold
    )
    use_reranking = pipeline.reranking_enabled if use_reranking is None else use_reranking
    merged_filters = {**(pipeline.metadata_filters or {}), **(filters or {})}

    started = time.perf_counter()
    stages: list[dict[str, Any]] = []

    embedder = get_embedder()
    embed_started = time.perf_counter()
    query_vector = embedder.embed([query]).vectors[0]
    stages.append(
        {
            "stage": "embedding",
            "detail": embedder.model,
            "duration_ms": int((time.perf_counter() - embed_started) * 1000),
        }
    )

    store = get_vector_store(db)
    search_started = time.perf_counter()
    # Over-fetch so the reranker and threshold have candidates to work with.
    matches = store.search(query_vector, top_k=max(top_k * 4, top_k), filters=merged_filters)
    stages.append(
        {
            "stage": "vector_search",
            "detail": f"{store.name}: {len(matches)} candidates",
            "duration_ms": int((time.perf_counter() - search_started) * 1000),
        }
    )

    chunks = [
        RetrievedChunk(
            chunk_id=match.id,
            document_id=str(match.payload.get("document_id", "")),
            document_name=str(match.payload.get("document_name", "unknown")),
            ordinal=int(match.payload.get("ordinal", 0) or 0),
            page=match.payload.get("page"),
            content=str(match.payload.get("content", "")),
            score=float(match.score),
        )
        for match in matches
    ]
    candidates = len(chunks)

    above_threshold = [chunk for chunk in chunks if chunk.score >= threshold]
    stages.append(
        {
            "stage": "threshold_filter",
            "detail": f">= {threshold}: {len(above_threshold)}/{candidates} kept",
            "duration_ms": 0,
        }
    )

    if use_reranking and above_threshold:
        rerank_started = time.perf_counter()
        above_threshold = rerank(query, above_threshold)
        stages.append(
            {
                "stage": "reranking",
                "detail": "vector 0.65 + lexical 0.35",
                "duration_ms": int((time.perf_counter() - rerank_started) * 1000),
            }
        )

    selected = above_threshold[:top_k]
    return RetrievalResult(
        query=query,
        chunks=selected,
        candidates_considered=candidates,
        latency_ms=int((time.perf_counter() - started) * 1000),
        pipeline={
            "id": str(pipeline.id),
            "name": pipeline.name,
            "chunk_size": pipeline.chunk_size,
            "chunk_overlap": pipeline.chunk_overlap,
            "top_k": top_k,
            "similarity_threshold": threshold,
            "reranking": use_reranking,
            "embedding_model": embedder.model,
            "vector_store": store.name,
        },
        stages=stages,
    )


def build_context(result: RetrievalResult, *, max_chars: int = 6000) -> str:
    """Assemble numbered context blocks. Numbering matches citation order."""
    blocks: list[str] = []
    used = 0
    for index, chunk in enumerate(result.chunks, start=1):
        header = f"[{index}] Source: {chunk.document_name}"
        if chunk.page:
            header += f" (page {chunk.page})"
        block = f"{header}\n{chunk.content}"
        if used + len(block) > max_chars:
            break
        blocks.append(block)
        used += len(block)
    return "\n\n".join(blocks)
