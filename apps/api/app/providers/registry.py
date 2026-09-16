"""Single place that resolves configuration into concrete provider instances."""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.providers.base import BlobStore, EmbeddingProvider, LLMProvider, VectorStore
from app.providers.blob import AzureBlobStore, LocalBlobStore
from app.providers.embeddings import AzureOpenAIEmbedding, LocalHashEmbedding
from app.providers.llm import AzureOpenAIChat, LocalGroundedLLM
from app.providers.vector_store import QdrantVectorStore, SqlVectorStore

logger = get_logger(__name__)


@lru_cache
def get_llm() -> LLMProvider:
    if settings.llm_provider == "azure":
        logger.info("provider_selected", extra={"provider": "azure", "kind": "llm"})
        return AzureOpenAIChat()
    return LocalGroundedLLM()


@lru_cache
def get_embedder() -> EmbeddingProvider:
    if settings.embedding_provider == "azure":
        logger.info("provider_selected", extra={"provider": "azure", "kind": "embedding"})
        return AzureOpenAIEmbedding()
    return LocalHashEmbedding()


def get_vector_store(db: Session) -> VectorStore:
    """Qdrant is process-global; the SQL store is bound to the request session."""
    if settings.vector_store == "qdrant":
        return _qdrant_singleton()
    return SqlVectorStore(db)


@lru_cache
def _qdrant_singleton() -> VectorStore:
    return QdrantVectorStore()


@lru_cache
def get_blob_store() -> BlobStore:
    if settings.blob_provider == "azure":
        return AzureBlobStore()
    return LocalBlobStore()


def provider_summary() -> dict[str, str]:
    return {
        "llm": settings.llm_provider,
        "embeddings": settings.embedding_provider,
        "vector_store": settings.vector_store,
        "blob": settings.blob_provider,
    }


def reset_provider_cache() -> None:
    """Used by tests and by settings changes that alter provider selection."""
    get_llm.cache_clear()
    get_embedder.cache_clear()
    get_blob_store.cache_clear()
    _qdrant_singleton.cache_clear()
