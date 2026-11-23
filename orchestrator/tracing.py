"""Wraps nodes, the chat model and the KG tools so each call becomes one span.

Nothing here changes behaviour: a wrapper returns exactly what the wrapped callable returns.
New tools are traced automatically (generic proxy), so adding a tool needs no change here.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from common.protocols import ChatModel, Tracer
from orchestrator.state import State

MAX_TEXT = 4000


def _plain(value: Any) -> Any:
    """JSON-friendly copy of a node update or tool argument; long text is cut."""
    if hasattr(value, "model_dump"):
        return _plain(value.model_dump(mode="json"))
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, str):
        return value if len(value) <= MAX_TEXT else value[:MAX_TEXT] + "…"
    return value if isinstance(value, (bool, int, float, type(None))) else repr(value)[:200]


def state_view(state: State) -> dict[str, Any]:
    """What a node saw, in short: the last user turn plus what earlier nodes decided."""
    last_user = next((m["content"] for m in reversed(state.messages) if m["role"] == "user"), "")
    return {
        "question": last_user,
        "jurisdiction": state.jurisdiction,
        "target": state.target.id if state.target else None,
        "evidence": len(state.evidence),
        "has_draft": state.draft is not None,
    }


def traced_node(tracer: Tracer, name: str, fn: Callable[[State], dict[str, Any]]) -> Callable[[State], dict[str, Any]]:
    def run(state: State) -> dict[str, Any]:
        with tracer.span(f"node.{name}", kind="chain", input=state_view(state)) as span:
            update = fn(state)
            span.update(output=_plain(update))
            return update

    run.__name__ = getattr(fn, "__name__", name)
    return run


class TracedChat:
    """ChatModel that records every call as a generation (prompt in, text out)."""

    def __init__(self, chat: ChatModel, tracer: Tracer) -> None:
        self._chat, self._tracer = chat, tracer

    def chat(self, messages: Sequence[dict[str, str]], *, schema: dict[str, Any] | None = None) -> str:
        with self._tracer.span("llm.chat", kind="generation", input=_plain(list(messages)),
                               metadata={"structured": schema is not None}) as span:
            out = self._chat.chat(messages, schema=schema)
            span.update(output=out)
            return out


def _summarize(result: Any) -> Any:
    items = getattr(result, "items", None)
    if isinstance(items, list):
        return {"count": len(items), "truncated": getattr(result, "truncated", None),
                "ids": [getattr(i, "id", None) for i in items][:20]}
    if isinstance(result, list):
        return {"count": len(result)}
    return _plain(result)


class TracedTools:
    """Proxy: any callable on the wrapped tools becomes a `tool.<name>` span."""

    def __init__(self, tools: Any, tracer: Tracer) -> None:
        self._tools, self._tracer = tools, tracer

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._tools, name)
        if name.startswith("_") or not callable(attr):
            return attr

        def call(*args: Any, **kwargs: Any) -> Any:
            with self._tracer.span(f"tool.{name}", kind="tool", input=_plain({"args": args, "kwargs": kwargs})) as span:
                result = attr(*args, **kwargs)
                span.update(output=_summarize(result))
                return result

        return call
