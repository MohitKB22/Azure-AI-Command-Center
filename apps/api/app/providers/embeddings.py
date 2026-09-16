"""Embedding providers: deterministic local hashing + Azure OpenAI."""

from __future__ import annotations

import hashlib
import math
import re

import httpx

from app.core.config import settings
from app.core.errors import ProviderError, ProviderNotConfiguredError
from app.providers.base import EmbeddingResult, estimate_tokens

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "is", "are", "for", "on",
    "with", "as", "by", "that", "this", "it", "be", "was", "were", "at", "from",
}


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS and len(t) > 1]


class LocalHashEmbedding:
    """Deterministic hashed bag-of-words embedding.

    This is a real, reproducible lexical embedding — not a stub. It supports
    unigrams and bigrams with sublinear term weighting, which gives usable
    retrieval quality offline. It is not a semantic model: synonyms will not
    match. Switch EMBEDDING_PROVIDER=azure for semantic retrieval.
    """

    name = "local"
    model = "local-hash-embedding"

    def __init__(self, dimension: int | None = None):
        self.dimension = dimension or settings.embedding_dim

    def _bucket(self, term: str) -> int:
        digest = hashlib.blake2b(term.encode("utf-8"), digest_size=8).digest()
        return int.from_bytes(digest, "big") % self.dimension

    def embed_one(self, text: str) -> list[float]:
        # Weights stay non-negative. Signed hashing cancels collisions in
        # expectation but produces noisy (and occasionally negative) cosine
        # scores for short queries, which is exactly our retrieval case.
        vector = [0.0] * self.dimension
        tokens = tokenize(text)
        if not tokens:
            return vector
        counts: dict[str, int] = {}
        for token in tokens:
            counts[token] = counts.get(token, 0) + 1
        # Bigrams are weighted higher: they carry most of the phrase signal.
        for first, second in zip(tokens, tokens[1:], strict=False):
            bigram = f"{first}_{second}"
            counts[bigram] = counts.get(bigram, 0) + 2
        for term, count in counts.items():
            vector[self._bucket(term)] += 1.0 + math.log(count)
        norm = math.sqrt(sum(value * value for value in vector))
        if norm > 0:
            vector = [value / norm for value in vector]
        return vector

    def embed(self, texts: list[str]) -> EmbeddingResult:
        return EmbeddingResult(
            vectors=[self.embed_one(text) for text in texts],
            model=self.model,
            prompt_tokens=sum(estimate_tokens(text) for text in texts),
        )


class AzureOpenAIEmbedding:
    """Azure OpenAI embeddings via the documented REST contract.

    POST {endpoint}/openai/deployments/{deployment}/embeddings?api-version=...
    """

    name = "azure"

    def __init__(self) -> None:
        if not settings.azure_openai_endpoint or not settings.azure_openai_embedding_deployment:
            raise ProviderNotConfiguredError(
                "Azure embeddings require AZURE_OPENAI_ENDPOINT and "
                "AZURE_OPENAI_EMBEDDING_DEPLOYMENT."
            )
        self.model = settings.azure_openai_embedding_deployment
        self.dimension = settings.embedding_dim
        self._endpoint = settings.azure_openai_endpoint.rstrip("/")

    def _headers(self) -> dict[str, str]:
        if settings.azure_openai_api_key:
            return {"api-key": settings.azure_openai_api_key}
        if settings.azure_use_managed_identity:
            from app.providers.azure_auth import managed_identity_token

            return {"Authorization": f"Bearer {managed_identity_token()}"}
        raise ProviderNotConfiguredError(
            "Set AZURE_OPENAI_API_KEY or enable AZURE_USE_MANAGED_IDENTITY."
        )

    def embed(self, texts: list[str]) -> EmbeddingResult:
        url = (
            f"{self._endpoint}/openai/deployments/{self.model}/embeddings"
            f"?api-version={settings.azure_openai_api_version}"
        )
        try:
            response = httpx.post(
                url, headers=self._headers(), json={"input": texts}, timeout=60.0
            )
            response.raise_for_status()
            body = response.json()
        except httpx.HTTPStatusError as exc:
            raise ProviderError(
                f"Azure embedding request failed with status {exc.response.status_code}."
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError("Azure embedding request failed.") from exc

        vectors = [item["embedding"] for item in body.get("data", [])]
        if vectors:
            self.dimension = len(vectors[0])
        return EmbeddingResult(
            vectors=vectors,
            model=self.model,
            prompt_tokens=body.get("usage", {}).get("prompt_tokens", 0),
        )


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
