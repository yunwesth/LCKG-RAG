"""Ollama HTTP client: chat (optional JSON-schema output), embeddings, health. Retries with backoff."""
from __future__ import annotations

import time
from collections.abc import Sequence
from typing import Any

import httpx

from common.errors import LLMUnavailable
from common.settings import OllamaSettings


def model_matches(wanted: str, installed: str) -> bool:
    """`name` and `name:latest` are the same Ollama model."""
    def norm(n: str) -> str:
        return n if ":" in n else f"{n}:latest"
    return norm(wanted) == norm(installed)


class OllamaClient:
    def __init__(
        self,
        settings: OllamaSettings,
        *,
        transport: httpx.BaseTransport | None = None,
        sleep=time.sleep,
    ) -> None:
        self._s = settings
        self._http = httpx.Client(
            base_url=settings.base_url, timeout=settings.timeout_s, transport=transport
        )
        self._sleep = sleep

    def close(self) -> None:
        self._http.close()

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        last: Exception | None = None
        for attempt in range(self._s.max_retries + 1):
            try:
                r = self._http.request(method, path, **kwargs)
                if r.status_code >= 500:
                    raise httpx.HTTPStatusError("server error", request=r.request, response=r)
                r.raise_for_status()
                return r.json()
            except (httpx.TransportError, httpx.HTTPStatusError) as e:
                if isinstance(e, httpx.HTTPStatusError) and e.response.status_code < 500:
                    raise LLMUnavailable(f"Ollama rejected {path}: {e.response.text[:200]}") from e
                last = e
                if attempt < self._s.max_retries:
                    self._sleep(min(2**attempt * 0.5, 8))
        raise LLMUnavailable(f"Ollama unreachable at {self._s.base_url}: {last}") from last

    def list_models(self) -> list[str]:
        return [m["name"] for m in self._request("GET", "/api/tags").get("models", [])]

    def has_model(self, name: str) -> bool:
        return any(model_matches(name, m) for m in self.list_models())

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        out = self._request(
            "POST", "/api/embed", json={"model": self._s.embed_model, "input": list(texts)}
        )
        vectors = out.get("embeddings", [])
        if len(vectors) != len(texts):
            raise LLMUnavailable(f"expected {len(texts)} embeddings, got {len(vectors)}")
        return vectors

    def chat(self, messages: Sequence[dict[str, str]], *, schema: dict[str, Any] | None = None) -> str:
        body: dict[str, Any] = {
            "model": self._s.chat_model,
            "messages": list(messages),
            "stream": False,
        }
        if schema is not None:
            body["format"] = schema
        if self._s.think is not None:
            body["think"] = self._s.think
        return self._request("POST", "/api/chat", json=body)["message"]["content"]
