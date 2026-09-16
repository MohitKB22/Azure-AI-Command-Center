"""Chat/completion providers.

`LocalGroundedLLM` is the offline implementation. It is deliberately extractive:
it answers only from the retrieved context it is given and says so when the
context does not cover the question. That keeps local demos honest — no
fabricated facts and no fabricated citations.
"""

from __future__ import annotations

import re
import time

import httpx

from app.core.config import settings
from app.core.errors import ProviderError, ProviderNotConfiguredError
from app.providers.base import ChatMessage, ChatResult, estimate_tokens
from app.providers.embeddings import tokenize

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
NO_CONTEXT_ANSWER = (
    "I could not find supporting content in the indexed documents, so I am not "
    "answering from memory. Try rephrasing, lowering the similarity threshold, "
    "or ingesting a document that covers this topic."
)


class LocalGroundedLLM:
    """Deterministic extractive responder for local/offline mode."""

    name = "local"

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 800,
        timeout: float = 60.0,
    ) -> ChatResult:
        started = time.perf_counter()
        question = next(
            (m.content for m in reversed(messages) if m.role == "user"), ""
        )
        context_blocks = [m.content for m in messages if m.role == "tool"]
        context = "\n".join(context_blocks).strip()

        if not context:
            text = NO_CONTEXT_ANSWER
        else:
            text = self._extract(question, context, max_tokens)

        prompt_tokens = sum(estimate_tokens(m.content) for m in messages)
        return ChatResult(
            text=text,
            prompt_tokens=prompt_tokens,
            completion_tokens=estimate_tokens(text),
            model=model,
            raw={
                "provider": "local",
                "temperature": temperature,
                "deterministic": True,
                "elapsed_ms": int((time.perf_counter() - started) * 1000),
                # Surfaced in the run trace and as a UI badge rather than being
                # appended to the answer, so evaluation scores the answer only.
                "note": (
                    "Extractive answer assembled verbatim from retrieved context. "
                    "Set LLM_PROVIDER=azure for generative answers."
                ),
            },
        )

    @staticmethod
    def _extract(question: str, context: str, max_tokens: int) -> str:
        question_terms = set(tokenize(question))
        sentences = [s.strip() for s in _SENTENCE_RE.split(context) if len(s.strip()) > 25]
        if not sentences:
            sentences = [context[:600]]

        scored: list[tuple[float, int, str]] = []
        for index, sentence in enumerate(sentences):
            terms = set(tokenize(sentence))
            if not terms:
                continue
            overlap = len(question_terms & terms)
            score = overlap / (len(question_terms) or 1)
            scored.append((score, index, sentence))

        scored.sort(key=lambda item: (-item[0], item[1]))
        best = [item for item in scored if item[0] > 0][:4] or scored[:2]
        if not best:
            return NO_CONTEXT_ANSWER

        ordered = [sentence for _, _, sentence in sorted(best, key=lambda item: item[1])]
        budget_chars = max(300, max_tokens * 4)
        return " ".join(ordered)[:budget_chars]


class AzureOpenAIChat:
    """Azure OpenAI chat completions via the documented REST contract.

    POST {endpoint}/openai/deployments/{deployment}/chat/completions?api-version=...
    """

    name = "azure"

    def __init__(self) -> None:
        if not settings.azure_openai_endpoint:
            raise ProviderNotConfiguredError("AZURE_OPENAI_ENDPOINT is required.")
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

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 800,
        timeout: float = 60.0,
    ) -> ChatResult:
        deployment = model or settings.azure_openai_chat_deployment
        if not deployment:
            raise ProviderNotConfiguredError("No Azure OpenAI chat deployment configured.")
        url = (
            f"{self._endpoint}/openai/deployments/{deployment}/chat/completions"
            f"?api-version={settings.azure_openai_api_version}"
        )
        payload = {
            "messages": [
                {"role": "user" if m.role == "tool" else m.role, "content": m.content}
                for m in messages
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        try:
            response = httpx.post(url, headers=self._headers(), json=payload, timeout=timeout)
            response.raise_for_status()
            body = response.json()
        except httpx.HTTPStatusError as exc:
            raise ProviderError(
                f"Azure OpenAI request failed with status {exc.response.status_code}."
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError("Azure OpenAI request failed.") from exc

        choice = (body.get("choices") or [{}])[0]
        usage = body.get("usage") or {}
        return ChatResult(
            text=(choice.get("message") or {}).get("content", ""),
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            model=deployment,
            finish_reason=choice.get("finish_reason", "stop"),
            raw={"provider": "azure", "id": body.get("id")},
        )
