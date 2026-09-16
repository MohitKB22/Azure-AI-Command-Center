"""Vector stores.

`SqlVectorStore` keeps embeddings alongside the chunks in the relational
database and scores them in-process. It is exact (brute force cosine), needs no
extra service, and is what local development and CI use.

`QdrantVectorStore` targets a real Qdrant deployment. It is production-shaped
code but requires a running Qdrant instance and the `azure` extra.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ProviderError
from app.db.models import Document, DocumentChunk
from app.providers.base import VectorMatch, VectorRecord
from app.providers.embeddings import cosine_similarity


class SqlVectorStore:
    """Exact brute-force cosine search over chunk embeddings stored in SQL."""

    name = "local"

    def __init__(self, db: Session):
        self.db = db

    def upsert(self, records: list[VectorRecord]) -> int:
        count = 0
        for record in records:
            chunk = self.db.get(DocumentChunk, uuid.UUID(record.id))
            if chunk is None:
                continue
            chunk.embedding = record.vector
            chunk.embedding_model = record.payload.get("embedding_model")
            count += 1
        self.db.flush()
        return count

    def search(
        self,
        vector: list[float],
        *,
        top_k: int,
        filters: dict[str, Any] | None = None,
    ) -> list[VectorMatch]:
        stmt = (
            select(DocumentChunk, Document)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(
                Document.deleted_at.is_(None),
                Document.status == "indexed",
                DocumentChunk.embedding.is_not(None),
            )
        )
        filters = filters or {}
        if tags := filters.get("tags"):
            wanted = {str(tag).lower() for tag in tags}
        else:
            wanted = set()
        if document_ids := filters.get("document_ids"):
            stmt = stmt.where(
                Document.id.in_([uuid.UUID(str(item)) for item in document_ids])
            )

        matches: list[VectorMatch] = []
        for chunk, document in self.db.execute(stmt).all():
            if wanted and not wanted & {str(tag).lower() for tag in (document.tags or [])}:
                continue
            score = cosine_similarity(vector, chunk.embedding or [])
            matches.append(
                VectorMatch(
                    id=str(chunk.id),
                    score=score,
                    payload={
                        "document_id": str(document.id),
                        "document_name": document.filename,
                        "ordinal": chunk.ordinal,
                        "page": chunk.page,
                        "content": chunk.content,
                        "tags": document.tags,
                    },
                )
            )
        matches.sort(key=lambda match: match.score, reverse=True)
        return matches[:top_k]

    def delete_by_document(self, document_id: str) -> int:
        chunks = (
            self.db.execute(
                select(DocumentChunk).where(
                    DocumentChunk.document_id == uuid.UUID(str(document_id))
                )
            )
            .scalars()
            .all()
        )
        for chunk in chunks:
            chunk.embedding = None
        self.db.flush()
        return len(chunks)

    def health(self) -> dict[str, Any]:
        indexed = self.db.scalar(
            select(DocumentChunk.id).where(DocumentChunk.embedding.is_not(None)).limit(1)
        )
        return {
            "provider": "local",
            "status": "healthy",
            "detail": "In-database exact cosine search",
            "has_vectors": indexed is not None,
        }


class QdrantVectorStore:
    """Qdrant-backed store. Requires a reachable Qdrant service."""

    name = "qdrant"

    def __init__(self) -> None:
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.http import models as qmodels
        except ImportError as exc:  # pragma: no cover - optional extra
            raise ProviderError(
                "qdrant-client is not installed. Install the 'azure' extra to use Qdrant."
            ) from exc

        self._qmodels = qmodels
        self._client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)
        self._collection = settings.qdrant_collection
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        existing = {c.name for c in self._client.get_collections().collections}
        if self._collection not in existing:
            self._client.create_collection(
                collection_name=self._collection,
                vectors_config=self._qmodels.VectorParams(
                    size=settings.embedding_dim,
                    distance=self._qmodels.Distance.COSINE,
                ),
            )

    def upsert(self, records: list[VectorRecord]) -> int:
        if not records:
            return 0
        points = [
            self._qmodels.PointStruct(id=r.id, vector=r.vector, payload=r.payload)
            for r in records
        ]
        self._client.upsert(collection_name=self._collection, points=points)
        return len(points)

    def search(
        self,
        vector: list[float],
        *,
        top_k: int,
        filters: dict[str, Any] | None = None,
    ) -> list[VectorMatch]:
        query_filter = None
        if filters and filters.get("document_ids"):
            query_filter = self._qmodels.Filter(
                must=[
                    self._qmodels.FieldCondition(
                        key="document_id",
                        match=self._qmodels.MatchAny(
                            any=[str(item) for item in filters["document_ids"]]
                        ),
                    )
                ]
            )
        hits = self._client.search(
            collection_name=self._collection,
            query_vector=vector,
            limit=top_k,
            query_filter=query_filter,
            with_payload=True,
        )
        return [
            VectorMatch(id=str(hit.id), score=float(hit.score), payload=dict(hit.payload or {}))
            for hit in hits
        ]

    def delete_by_document(self, document_id: str) -> int:
        self._client.delete(
            collection_name=self._collection,
            points_selector=self._qmodels.FilterSelector(
                filter=self._qmodels.Filter(
                    must=[
                        self._qmodels.FieldCondition(
                            key="document_id",
                            match=self._qmodels.MatchValue(value=str(document_id)),
                        )
                    ]
                )
            ),
        )
        return 1

    def health(self) -> dict[str, Any]:
        try:
            info = self._client.get_collection(self._collection)
            return {
                "provider": "qdrant",
                "status": "healthy",
                "vectors": getattr(info, "points_count", None),
            }
        except Exception as exc:  # pragma: no cover - depends on live service
            return {"provider": "qdrant", "status": "unhealthy", "detail": str(exc)}
