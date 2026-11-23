"""OpenAI-compatible `/v1/chat/completions` over the pipeline. Verify runs before anything is sent,
so streaming only chunks the already-verified reply (fail-closed answers never leak partial text)."""
from __future__ import annotations

import json
import time
import uuid
from collections.abc import Iterator
from typing import Any, Protocol

from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from orchestrator.state import State

MODEL_NAME = "lcrag"
CHUNK_CHARS = 40


class Runner(Protocol):
    def run(self, msgs: list[dict[str, str]]) -> State: ...


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


def _chunk(cid: str, delta: dict[str, Any], finish: str | None = None) -> str:
    body = {"id": cid, "object": "chat.completion.chunk", "created": int(time.time()), "model": MODEL_NAME,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
    return f"data: {json.dumps(body, ensure_ascii=False)}\n\n"


def _stream(cid: str, reply: str) -> Iterator[str]:
    yield _chunk(cid, {"role": "assistant"})
    for i in range(0, len(reply), CHUNK_CHARS):
        yield _chunk(cid, {"content": reply[i:i + CHUNK_CHARS]})
    yield _chunk(cid, {}, "stop")
    yield "data: [DONE]\n\n"


def create_app(pipeline: Runner) -> FastAPI:
    app = FastAPI(title="LCKG RAG orchestrator")

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/models")
    def models() -> dict[str, Any]:
        return {"object": "list", "data": [{"id": MODEL_NAME, "object": "model", "owned_by": "lcrag"}]}

    @app.post("/v1/chat/completions")
    def completions(req: ChatRequest):
        msgs = [{"role": m.role, "content": m.text()} for m in req.messages]
        if not any(m["role"] == "user" and m["content"].strip() for m in msgs):
            return JSONResponse({"error": {"message": "a non-empty user message is required"}}, status_code=400)
        state = pipeline.run(msgs)
        reply = state.reply or ""
        cid = f"chatcmpl-{uuid.uuid4().hex[:24]}"
        if req.stream:
            return StreamingResponse(_stream(cid, reply), media_type="text/event-stream")
        return {
            "id": cid, "object": "chat.completion", "created": int(time.time()), "model": MODEL_NAME,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": reply}, "finish_reason": "stop"}],
            "lcrag": {"status": state.status.value if state.status else None, "citations": state.citations},
        }

    return app
