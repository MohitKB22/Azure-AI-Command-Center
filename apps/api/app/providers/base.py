"""Provider interfaces.

Every external dependency (LLM, embeddings, vector store, blob storage,
telemetry) is reached through one of these protocols so the platform runs
identically against local deterministic implementations or real Azure services.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(slots=True)
class ChatMessage:
    role: str  # system | user | assistant | tool
    content: str


@dataclass(slots=True)
class ChatResult:
    text: str
    prompt_tokens: int
    completion_tokens: int
    model: str
    finish_reason: str = "stop"
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass(slots=True)
class EmbeddingResult:
    vectors: list[list[float]]
    model: str
    prompt_tokens: int = 0


@dataclass(slots=True)
class VectorRecord:
    id: str
    vector: list[float]
    payload: dict[str, Any]


@dataclass(slots=True)
class VectorMatch:
    id: str
    score: float
    payload: dict[str, Any]


@runtime_checkable
class LLMProvider(Protocol):
    name: str

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 800,
        timeout: float = 60.0,
    ) -> ChatResult: ...


@runtime_checkable
class EmbeddingProvider(Protocol):
    name: str
    dimension: int
    model: str

    def embed(self, texts: list[str]) -> EmbeddingResult: ...


@runtime_checkable
class VectorStore(Protocol):
    name: str

    def upsert(self, records: list[VectorRecord]) -> int: ...

    def search(
        self,
        vector: list[float],
        *,
        top_k: int,
        filters: dict[str, Any] | None = None,
    ) -> list[VectorMatch]: ...

    def delete_by_document(self, document_id: str) -> int: ...

    def health(self) -> dict[str, Any]: ...


@runtime_checkable
class BlobStore(Protocol):
    name: str

    def put(self, key: str, data: bytes, content_type: str) -> str: ...

    def get(self, key: str) -> bytes: ...

    def delete(self, key: str) -> None: ...

    def health(self) -> dict[str, Any]: ...


def estimate_tokens(text: str) -> int:
    """Approximate token count (~4 characters per token).

    Used for local-mode accounting and for pre-flight context checks. Real usage
    numbers always come from the provider response when one is available.
    """
    if not text:
        return 0
    return max(1, len(text) // 4)
