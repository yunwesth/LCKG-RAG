"""Asks the running orchestrator over HTTP (OpenAI-compatible API). Imports nothing from it."""
from __future__ import annotations

import time
from collections.abc import Callable

import httpx

from evals.metrics import Response

Asker = Callable[[list[dict[str, str]]], Response]


def make_asker(base_url: str, *, api_key: str = "", timeout_s: float = 180.0,
               transport: httpx.BaseTransport | None = None) -> Asker:
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    http = httpx.Client(base_url=base_url, timeout=timeout_s, headers=headers, transport=transport)

    def ask(messages: list[dict[str, str]]) -> Response:
        start = time.perf_counter()
        try:
            r = http.post("/v1/chat/completions", json={"model": "lcrag", "messages": messages})
            elapsed = time.perf_counter() - start
            if r.status_code != 200:
                return Response(latency_s=elapsed, error=f"http {r.status_code}")
            body = r.json()
            meta = body.get("lcrag", {})
            return Response(status=meta.get("status"), citations=meta.get("citations", []), target=meta.get("target"),
                            reply=body["choices"][0]["message"]["content"], latency_s=elapsed)
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            return Response(latency_s=time.perf_counter() - start, error=type(exc).__name__)

    return ask
