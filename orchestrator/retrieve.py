"""Retrieve: fixed tool calls that gather evidence for the resolved node. No LLM."""
from __future__ import annotations

from typing import Any

from orchestrator.ports import KnowledgeTools
from orchestrator.state import Evidence, State

MAX_DEPTH = 3
EVIDENCE_LIMIT = 15


def make_retrieve(tools: KnowledgeTools):
    def retrieve(state: State) -> dict[str, Any]:
        target = state.target
        if target is None:  # the graph only routes here after Resolve found a node
            raise RuntimeError("retrieve ran without a resolved target")
        evidence = [Evidence(ref=1, node=target)]
        truncated = False
        if target.label == "StandardsFrameworkItem":
            result = tools.get_prerequisites(target.id, max_depth=MAX_DEPTH, limit=EVIDENCE_LIMIT)
        elif target.label == "LessonGrouping":
            result = tools.get_lesson_prerequisites(target.id, max_depth=MAX_DEPTH, limit=EVIDENCE_LIMIT)
        else:
            result = None
        if result is not None:
            truncated = result.truncated
            for i, item in enumerate(result.items, start=2):
                evidence.append(Evidence(ref=i, node=item, distance=item.distance))
        return {"evidence": evidence, "truncated": truncated}

    return retrieve
