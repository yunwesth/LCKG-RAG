"""Verify: fail closed. The answer is only released if every citation points at real evidence and
nothing in it (codes, links, leftover reasoning) is missing from that evidence."""
from __future__ import annotations

import re
from typing import Any

from orchestrator import messages
from orchestrator.state import State, Status

MIN_PROSE = 20  # a reply that is only citation numbers says nothing
_REF = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")  # [2], [2, 3]; "[2][3]" is two matches
_URL = re.compile(r"https?://|www\.", re.IGNORECASE)
_CODES = (
    re.compile(r"\b\d{1,2}\.[A-Z]{1,4}\.[A-Z]\.\d{1,2}\b"),        # 5.NF.B.5, 8.EE.C.8
    re.compile(r"\b[A-Z]{2,6}-[A-Z]{1,4}\.[A-Z]\.\d{1,2}\b"),      # HSS-ID.C.7
)


def _cited(draft: str) -> list[int]:
    return [int(n) for group in _REF.findall(draft) for n in re.findall(r"\d+", group)]


def _evidence_text(state: State) -> str:
    parts: list[str] = []
    for e in state.evidence:
        parts += [x for x in (e.node.code, e.node.name, e.node.description) if x]
    return " ".join(parts)


def _ungrounded_code(draft: str, haystack: str) -> bool:
    return any(c not in haystack for pattern in _CODES for c in pattern.findall(draft))


def _refuse(ko: bool) -> dict[str, Any]:
    return {"status": Status.REFUSED, "reply": messages.refused(ko)}


def verify(state: State) -> dict[str, Any]:
    ko = messages.user_is_korean(state.messages)
    draft = state.draft or ""
    by_ref = {e.ref: e for e in state.evidence}
    cited = _cited(draft)
    prose = _REF.sub("", draft).strip(" \n-:,.")
    if not cited or len(prose) < MIN_PROSE or any(n not in by_ref for n in cited):
        return _refuse(ko)
    if "<think" in draft or "</think" in draft or _URL.search(draft):
        return _refuse(ko)
    if _ungrounded_code(draft, _evidence_text(state)):
        return _refuse(ko)
    ordered = sorted(set(cited))
    sources = "\n".join(f"[{n}] {by_ref[n].node.id} ({by_ref[n].node.label})" for n in ordered)
    header = "출처" if ko else "Sources"
    note = ""
    if state.truncated:
        note = "\n\n(결과가 많아 일부만 표시했습니다.)" if ko else "\n\n(Results were truncated; only the nearest are shown.)"
    return {
        "status": Status.ANSWERED,
        "reply": f"{draft}{note}\n\n{header}:\n{sources}",
        "citations": [by_ref[n].node.id for n in ordered],
    }
