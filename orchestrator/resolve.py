"""Resolve: map the user's words to one KG node. No LLM. Policy (owner, 2026-11-22): when a standard
could belong to several jurisdictions and the user named none, ask which one instead of guessing."""
from __future__ import annotations

from typing import Any

from kg_tools.tools import NodeSummary
from orchestrator import messages
from orchestrator.ports import KnowledgeTools
from orchestrator.state import Intent, State, Status

SEARCH_LABELS = ("StandardsFrameworkItem", "LessonGrouping")
AMBIGUITY_WINDOW = 5   # top hits inspected for jurisdiction spread
CODE_LIMIT = 60


def _last_user_text(state: State) -> str:
    users = [m["content"] for m in state.messages if m.get("role") == "user"]
    return users[-1] if users else ""


def _match_jurisdiction(raw: str | None, known: list[str]) -> str | None:
    if not raw:
        return None
    wanted = raw.strip().casefold()
    return next((k for k in known if k.casefold() == wanted), None)


def make_resolve(tools: KnowledgeTools):
    def resolve(state: State) -> dict[str, Any]:
        u = state.understanding
        ko = messages.user_is_korean(state.messages)
        if u is None or u.intent is Intent.UNSUPPORTED or not (u.code or u.concept):
            return {"status": Status.UNSUPPORTED, "reply": messages.unsupported(ko)}

        jurisdiction = _match_jurisdiction(u.jurisdiction, tools.list_jurisdictions())
        target: NodeSummary | None = None
        candidates: list[NodeSummary] = []

        if u.code:
            candidates = tools.find_standard_by_code(u.code, jurisdiction=jurisdiction, limit=CODE_LIMIT).items
        if not u.code and u.concept:  # an explicit code is never silently swapped for a topic search
            hits = tools.search_nodes(u.concept, labels=SEARCH_LABELS, limit=10).items
            candidates = [h for h in hits if jurisdiction is None or h.jurisdiction in (None, jurisdiction)]
            candidates = [NodeSummary(**h.model_dump(exclude={"score"})) for h in candidates]

        if not candidates:
            return {"status": Status.NOT_FOUND, "reply": messages.not_found(ko), "jurisdiction": jurisdiction}

        top = candidates[0]
        if jurisdiction is None and top.label == "StandardsFrameworkItem":
            window = candidates if u.code else candidates[:AMBIGUITY_WINDOW]
            spread = sorted({c.jurisdiction for c in window if c.jurisdiction})
            if len(spread) > 1:
                return {"status": Status.CLARIFY, "reply": messages.clarify_jurisdiction(ko, spread)}
        target = top
        return {"target": target, "jurisdiction": jurisdiction}

    return resolve
