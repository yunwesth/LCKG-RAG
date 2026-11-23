"""The fixed pipeline: Understand -> Resolve -> Retrieve -> Synthesize -> Verify (LangGraph)."""
from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

from langgraph.graph import END, START, StateGraph

from common.errors import KGUnavailable, LLMUnavailable
from common.protocols import ChatModel
from orchestrator import messages
from orchestrator.ports import KnowledgeTools
from orchestrator.resolve import make_resolve
from orchestrator.retrieve import make_retrieve
from orchestrator.state import State, Status
from orchestrator.synthesize import make_synthesize
from orchestrator.understand import make_understand
from orchestrator.verify import verify

logger = logging.getLogger("lcrag.pipeline")


def build_graph(chat: ChatModel, tools: KnowledgeTools):
    g = StateGraph(State)
    g.add_node("understand", make_understand(chat))
    g.add_node("resolve", make_resolve(tools))
    g.add_node("retrieve", make_retrieve(tools))
    g.add_node("synthesize", make_synthesize(chat))
    g.add_node("verify", verify)
    g.add_edge(START, "understand")
    g.add_edge("understand", "resolve")
    g.add_conditional_edges("resolve", lambda s: "retrieve" if s.target is not None else END)
    g.add_edge("retrieve", "synthesize")
    g.add_edge("synthesize", "verify")
    g.add_edge("verify", END)
    return g.compile()


class Pipeline:
    """Runs the graph under a total time limit. Any failure becomes a safe reply, never an exception."""

    def __init__(self, chat: ChatModel, tools: KnowledgeTools, *, timeout_s: float | None = None,
                 closers: Sequence[Callable[[], object]] = (), checks: Sequence[Callable[[], bool]] = ()) -> None:
        self._graph = build_graph(chat, tools)
        self._timeout_s = timeout_s
        self._closers, self._checks = list(closers), list(checks)
        self._pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="lcrag")

    def _invoke(self, msgs: list[dict[str, str]]) -> State:
        return State.model_validate(self._graph.invoke(State(messages=msgs)))

    def run(self, msgs: list[dict[str, str]]) -> State:
        ko = messages.user_is_korean(msgs)

        def refused(text: str) -> State:
            return State(messages=msgs, status=Status.REFUSED, reply=text)

        try:
            return self._pool.submit(self._invoke, msgs).result(timeout=self._timeout_s)
        except FutureTimeout:  # the worker thread ends on its own; the model client has its own timeouts
            return refused(messages.timed_out(ko))
        except (LLMUnavailable, KGUnavailable):
            return refused(messages.unavailable(ko))
        except Exception as exc:  # noqa: BLE001 - fail closed; log the type only  # fail closed on anything unexpected; log the type only (messages may hold prompts)
            logger.error("pipeline failed: %s", type(exc).__name__)
            return refused(messages.refused(ko))

    def ready(self) -> bool:
        try:
            return all(check() for check in self._checks)
        except Exception:  # noqa: BLE001 - a failing check means not ready
            return False

    def close(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)
        for closer in self._closers:
            try:
                closer()
            except Exception as exc:  # noqa: BLE001 - closing must not raise
                logger.error("close failed: %s", type(exc).__name__)
