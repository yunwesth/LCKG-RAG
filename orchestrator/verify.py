"""Verify: fail closed. The answer is only released if every citation points at real evidence."""
from __future__ import annotations

import re
from typing import Any

from orchestrator import messages
from orchestrator.state import State, Status

MIN_PROSE = 20  # a reply that is only citation numbers says nothing
_REF = re.compile(r"\[(\d+)\]")


def verify(state: State) -> dict[str, Any]:
    ko = messages.user_is_korean(state.messages)
    draft = state.draft or ""
    by_ref = {e.ref: e for e in state.evidence}
    cited = [int(n) for n in _REF.findall(draft)]
    prose = _REF.sub("", draft).strip(" \n-:,.")
    if not cited or len(prose) < MIN_PROSE or any(n not in by_ref for n in cited):
        return {"status": Status.REFUSED, "reply": messages.refused(ko)}
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
