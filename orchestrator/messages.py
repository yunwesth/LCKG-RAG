"""User-facing fixed texts (Korean or English, chosen from the user's last message)."""
from __future__ import annotations

import re

_HANGUL = re.compile(r"[가-힣]")


def is_korean(text: str) -> bool:
    return bool(_HANGUL.search(text))


def clarify_jurisdiction(ko: bool, options: list[str]) -> str:
    shown = ", ".join(options[:12]) + (" ..." if len(options) > 12 else "")
    if ko:
        return f"같은 표준 코드가 여러 주(관할)에 있습니다. 어느 주 기준인가요? 후보: {shown}"
    return f"This standard exists in several jurisdictions. Which one do you mean? Options: {shown}"


def not_found(ko: bool) -> str:
    return ("지식 그래프에서 해당 항목을 찾지 못했습니다. 표준 코드나 주제를 더 구체적으로 알려주세요."
            if ko else "I could not find that in the knowledge graph. Please give a standard code or a more specific topic.")


def unsupported(ko: bool) -> str:
    return ("현재는 선수 개념(무엇을 먼저 배워야 하는지) 질문만 지원합니다."
            if ko else "I currently support prerequisite questions only (what must be learned first).")


def no_prerequisites(ko: bool, ref: int) -> str:
    return (f"[{ref}]에 대해 그래프에 기록된 선수 개념이 없습니다."
            if ko else f"No prerequisites are recorded in the graph for [{ref}].")


def refused(ko: bool) -> str:
    return ("검증 가능한 근거로 답을 만들지 못해 답변하지 않습니다. 질문을 바꿔 다시 시도해 주세요."
            if ko else "I could not produce an answer that is verifiable against the graph, so I will not answer.")


def unavailable(ko: bool) -> str:
    return ("모델 또는 데이터베이스에 일시적으로 연결할 수 없습니다. 잠시 후 다시 시도해 주세요."
            if ko else "The model or database is temporarily unavailable. Please try again shortly.")


def user_is_korean(msgs: list[dict[str, str]]) -> bool:
    """Korean if any user turn contains Hangul, so a short English follow-up ("Texas") keeps the language."""
    return any(is_korean(m["content"]) for m in msgs if m.get("role") == "user")
