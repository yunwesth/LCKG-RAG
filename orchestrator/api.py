"""OpenAI-compatible `/v1/chat/completions` over the pipeline. Verify runs before any answer text is sent,
so streaming only chunks the already-verified reply (fail-closed answers never leak partial text).

Accepted and used: `model` (ignored, one model is served), `messages`, `stream`, `stream_options.include_usage`.
Other OpenAI fields (temperature, max_tokens, ...) are accepted and ignored. Token usage is reported as zeros.
Errors use the OpenAI shape `{"error": {"message", "type", "code"}}` and never echo the request body.
"""
from __future__ import annotations

import asyncio
import hmac
import json
import logging
import threading
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any, Protocol

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from common.settings import OrchestratorSettings, orchestrator_settings
from orchestrator.state import State

MODEL_NAME = "lcrag"
CHUNK_CHARS = 40
USAGE = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}

logger = logging.getLogger("lcrag.api")


class Runner(Protocol):
    def run(self, msgs: list[dict[str, str]]) -> State: ...


class ApiFailure(Exception):
    def __init__(self, status: int, message: str, code: str, headers: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.status, self.message, self.code, self.headers = status, message, code, headers or {}


def _error(status: int, message: str, code: str, headers: dict[str, str] | None = None) -> JSONResponse:
    kind = "invalid_request_error" if status < 500 else "server_error"
    return JSONResponse({"error": {"message": message, "type": kind, "code": code}}, status_code=status, headers=headers)


class ChatMessage(BaseModel):
    role: str
    content: str | list[dict[str, Any]] | None = None

    def text(self) -> str:
        if isinstance(self.content, list):  # OpenAI "parts" format (Open WebUI may send it)
            return "".join(p.get("text", "") for p in self.content if p.get("type") == "text")
        return self.content or ""


class ChatRequest(BaseModel):
    model: str = MODEL_NAME
    messages: list[ChatMessage] = Field(min_length=1)
    stream: bool = False
    stream_options: dict[str, Any] | None = None


def _chunk(cid: str, delta: dict[str, Any], finish: str | None = None, extra: dict[str, Any] | None = None) -> str:
    body: dict[str, Any] = {"id": cid, "object": "chat.completion.chunk", "created": int(time.time()), "model": MODEL_NAME,
                            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
    if extra:
        body.update(extra)
    return f"data: {json.dumps(body, ensure_ascii=False)}\n\n"


def _usage_chunk(cid: str) -> str:
    body = {"id": cid, "object": "chat.completion.chunk", "created": int(time.time()), "model": MODEL_NAME,
            "choices": [], "usage": USAGE}
    return f"data: {json.dumps(body)}\n\n"


def _meta(state: State | None) -> dict[str, Any]:
    if state is None:
        return {"status": "error", "citations": []}
    return {"status": state.status.value if state.status else None, "citations": state.citations}


_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"description": "missing or wrong API key"}, 413: {"description": "request too large"},
    422: {"description": "invalid request"}, 429: {"description": "server busy"}, 500: {"description": "internal error"},
}


def create_app(pipeline: Runner, settings: OrchestratorSettings | None = None) -> FastAPI:
    cfg = settings or orchestrator_settings()
    gate = threading.BoundedSemaphore(cfg.max_concurrent)
    app = FastAPI(title="LCKG RAG orchestrator")

    @app.exception_handler(ApiFailure)
    async def _failure(_: Request, exc: ApiFailure) -> JSONResponse:
        return _error(exc.status, exc.message, exc.code, exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _invalid(_: Request, exc: RequestValidationError) -> JSONResponse:
        where = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors())[:300]
        return _error(422, f"invalid request ({where})", "invalid_request")

    def authorize(request: Request) -> None:
        key = cfg.api_key.get_secret_value()
        if not key:
            return
        given = request.headers.get("authorization", "")
        if not (given.startswith("Bearer ") and hmac.compare_digest(given[7:].encode(), key.encode())):
            raise ApiFailure(401, "missing or invalid API key", "invalid_api_key", {"WWW-Authenticate": "Bearer"})

    def prepare(req: ChatRequest) -> list[dict[str, str]]:
        if len(req.messages) > cfg.max_messages:
            raise ApiFailure(413, f"too many messages (limit {cfg.max_messages})", "too_many_messages")
        msgs = [{"role": m.role, "content": m.text()} for m in req.messages]
        if sum(len(m["content"]) for m in msgs) > cfg.max_chars:
            raise ApiFailure(413, f"conversation too long (limit {cfg.max_chars} characters)", "context_too_long")
        if not any(m["role"] == "user" and m["content"].strip() for m in msgs):
            raise ApiFailure(422, "a non-empty user message is required", "empty_user_message")
        return msgs

    def execute(msgs: list[dict[str, str]]) -> State:
        """Runs in a worker thread. At most `max_concurrent` pipelines run at once (they share one model)."""
        if not gate.acquire(timeout=cfg.queue_wait_s):
            raise ApiFailure(429, "the server is busy, try again shortly", "server_busy", {"Retry-After": "10"})
        try:
            return pipeline.run(msgs)
        except Exception as exc:  # noqa: BLE001 - API boundary: any crash becomes a generic 500
            logger.error("pipeline crashed: %s", type(exc).__name__)
            raise ApiFailure(500, "internal error", "internal_error") from None
        finally:
            gate.release()

    async def live_stream(cid: str, msgs: list[dict[str, str]], include_usage: bool) -> AsyncIterator[str]:
        """Starts at once and sends keepalive comments while the pipeline works, so proxies keep the connection."""
        yield _chunk(cid, {"role": "assistant"})
        task = asyncio.ensure_future(asyncio.to_thread(execute, msgs))
        try:
            while True:
                done, _ = await asyncio.wait({task}, timeout=cfg.keepalive_s)
                if done:
                    break
                yield ": keepalive\n\n"
            try:
                state: State | None = task.result()
                reply = state.reply or ""
            except ApiFailure as failure:
                state, reply = None, failure.message
            for i in range(0, len(reply), CHUNK_CHARS):
                yield _chunk(cid, {"content": reply[i:i + CHUNK_CHARS]})
            yield _chunk(cid, {}, "stop", {"lcrag": _meta(state)})
            if include_usage:
                yield _usage_chunk(cid)
            yield "data: [DONE]\n\n"
        finally:
            if not task.done():
                task.cancel()  # the worker thread cannot be stopped, but its own timeouts end it

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    def readyz() -> JSONResponse:
        ready = getattr(pipeline, "ready", lambda: True)
        ok = bool(ready())
        return JSONResponse({"status": "ready" if ok else "unavailable"}, status_code=200 if ok else 503)

    @app.get("/v1/models")
    def models(request: Request) -> dict[str, Any]:
        authorize(request)
        return {"object": "list", "data": [{"id": MODEL_NAME, "object": "model", "owned_by": "lcrag"}]}

    @app.post("/v1/chat/completions", responses=_RESPONSES)
    async def completions(req: ChatRequest, request: Request):
        authorize(request)
        msgs = prepare(req)
        cid = f"chatcmpl-{uuid.uuid4().hex[:24]}"
        if req.stream:
            include_usage = bool((req.stream_options or {}).get("include_usage"))
            return StreamingResponse(live_stream(cid, msgs, include_usage), media_type="text/event-stream",
                                     headers=SSE_HEADERS)
        state = await asyncio.to_thread(execute, msgs)
        return {
            "id": cid, "object": "chat.completion", "created": int(time.time()), "model": MODEL_NAME,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": state.reply or ""}, "finish_reason": "stop"}],
            "usage": USAGE, "lcrag": _meta(state),
        }

    return app
