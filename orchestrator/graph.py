"""The fixed pipeline: Understand -> Resolve -> Retrieve -> Synthesize -> Verify (LangGraph)."""
from __future__ import annotations

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
    def __init__(self, chat: ChatModel, tools: KnowledgeTools) -> None:
        self._graph = build_graph(chat, tools)

    def run(self, msgs: list[dict[str, str]]) -> State:
        try:
            out = self._graph.invoke(State(messages=msgs))
            return State.model_validate(out)
        except (LLMUnavailable, KGUnavailable):
            return State(messages=msgs, status=Status.REFUSED, reply=messages.unavailable(messages.user_is_korean(msgs)))
