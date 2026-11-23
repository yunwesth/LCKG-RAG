"""Draft eval cases from the graph. Output is `reviewed=false`: the owner reads and approves each case.

    set -a; . ./.env; set +a
    .venv/bin/python -m scripts.build_eval_candidates            # writes evals/eval_candidates.jsonl

Gold answers are what the KG tools return for the same standard, so the set checks that the pipeline
resolves the right node and cites only real prerequisites. It does not judge wording quality.
"""
from __future__ import annotations

import random
import re
from pathlib import Path
from typing import Any, Protocol

from common.settings import neo4j_settings, ollama_settings
from evals.cases import EvalCase, write_cases
from kg_tools.neo4j_client import Neo4jReader
from kg_tools.tools import KGTools
from orchestrator.resolve import AMBIGUITY_WINDOW, SEARCH_LABELS
from orchestrator.retrieve import EVIDENCE_LIMIT, MAX_DEPTH

SEED = 5
N_PREREQ, N_FOLLOWUP, N_CLARIFY, N_NOT_FOUND, N_LOOKUP, N_LESSON = 20, 5, 6, 3, 3, 3
PAIRS_QUERY = """MATCH (a:StandardsFrameworkItem)-[:buildsTowards]->(b:StandardsFrameworkItem)
WHERE b.statementCode IS NOT NULL AND b.jurisdiction IS NOT NULL
RETURN DISTINCT b.statementCode AS code, b.jurisdiction AS jurisdiction LIMIT 500"""
MULTI_QUERY = """MATCH (s:StandardsFrameworkItem) WHERE s.statementCode IS NOT NULL
WITH s.statementCode AS code, collect(DISTINCT s.jurisdiction) AS jurisdictions
WHERE size(jurisdictions) > 1 RETURN code, jurisdictions LIMIT 300"""
WITH_STATE = (
    "What should students know before {code} in {jur}?",
    "Which skills lead up to {code} ({jur})?",
    "What are the prerequisites for standard {code} in {jur}?",
    "A student is struggling with {code} in {jur}. What should they have learned earlier?",
)
NO_STATE = (
    "What should students know before {code}?",
    "What are the prerequisites for standard {code}?",
)
LESSON_QUERY = """MATCH (l:LessonGrouping)-[:hasDependency]->(:LessonGrouping)
WHERE l.name IS NOT NULL AND size(l.name) <= 70 RETURN DISTINCT l.name AS name LIMIT 200"""
CONCEPTS = ("multiplying fractions", "adding within 20", "solving linear equations", "area of triangles", "place value")
UNSUPPORTED = (
    "Write a short poem about fractions.",
    "What is the weather in Austin today?",
    "Translate 'good morning' into Spanish.",
    "Who won the football game last night?",
)


_MATH_CODE = re.compile(r"^((K|\d{1,2})\.[A-Z]{1,4}\.[A-Z]|HS[A-Z]-[A-Z]{1,4}\.[A-Z])\.\d+(\.[a-z])?$")


def _is_leaf_standard(code: str) -> bool:
    """A specific Common Core math standard such as 8.EE.C.8 or HSF-BF.B.4 (not a cluster, practice or ELA code)."""
    return bool(_MATH_CODE.match(code)) and ".MP." not in code


class Tools(Protocol):
    def search_nodes(self, query: str, *, labels: Any = None, limit: int | None = None) -> Any: ...
    def get_lesson_prerequisites(self, node_id: str, *, max_depth: int = 3, limit: int | None = None) -> Any: ...
    def find_standard_by_code(self, code: str, *, jurisdiction: str | None = None, limit: int | None = None) -> Any: ...
    def get_prerequisites(self, node_id: str, *, max_depth: int = 3, limit: int | None = None) -> Any: ...


def _is_standard_code(code: str) -> bool:
    """Skip bare values such as "2": real standard codes contain a dot or a dash and letters."""
    return len(code) >= 5 and any(ch in code for ch in ".-") and any(ch.isalpha() for ch in code)


def _gold(tools: Tools, code: str, jurisdiction: str) -> tuple[str, list[str], list[str]] | None:
    """(target id, direct prerequisite ids, all citable ids) or None when the standard is ambiguous or has none."""
    found = tools.find_standard_by_code(code, jurisdiction=jurisdiction, limit=5).items
    if len(found) != 1:
        return None  # two nodes share code and jurisdiction: the gold answer would be arbitrary
    target = found[0]
    prereqs = tools.get_prerequisites(target.id, max_depth=MAX_DEPTH, limit=EVIDENCE_LIMIT).items
    if not prereqs:
        return None
    return target.id, [p.id for p in prereqs if p.distance == 1], [target.id] + [p.id for p in prereqs]


def _concept_gold(tools: Tools, concept: str) -> tuple[str, str | None, list[str], list[str]] | None:
    """What Resolve should do for a topic phrase: ask for a jurisdiction, or answer from the top hit."""
    hits = tools.search_nodes(concept, labels=SEARCH_LABELS, limit=10).items
    if not hits:
        return None
    top = hits[0]
    is_standard = top.label == "StandardsFrameworkItem"
    if is_standard and len({h.jurisdiction for h in hits[:AMBIGUITY_WINDOW] if h.jurisdiction}) > 1:
        return "clarify", None, [], []
    fetch = tools.get_prerequisites if is_standard else tools.get_lesson_prerequisites
    prereqs = fetch(top.id, max_depth=MAX_DEPTH, limit=EVIDENCE_LIMIT).items
    return "answered", top.id, [p.id for p in prereqs if p.distance == 1], [top.id] + [p.id for p in prereqs]


def build_candidates(tools: Tools, pairs: list[tuple[str, str]], multi: list[tuple[str, list[str]]],
                     rng: random.Random, lessons: list[str] | None = None) -> list[EvalCase]:
    cases: list[EvalCase] = []
    pairs = [p for p in pairs if _is_standard_code(p[0])]
    multi = [m for m in multi if _is_standard_code(m[0]) and _is_leaf_standard(m[0])]
    lessons = sorted(set(lessons or []))
    rng.shuffle(lessons)
    rng.shuffle(pairs)
    rng.shuffle(multi)

    for code, jur in pairs:
        if sum(c.kind == "prerequisites" for c in cases) >= N_PREREQ:
            break
        gold = _gold(tools, code, jur)
        if gold is None:
            continue
        n = sum(c.kind == "prerequisites" for c in cases)
        q = WITH_STATE[n % len(WITH_STATE)].format(code=code, jur=jur)
        cases.append(EvalCase(id=f"prereq-{n + 1:02d}", kind="prerequisites", messages=[{"role": "user", "content": q}],
                              expect_status="answered", target_id=gold[0], near_ids=gold[1], allowed_ids=gold[2],
                              note=f"{code} / {jur}"))

    followups = 0
    for code, jurs in multi:
        if followups >= N_FOLLOWUP:
            break
        jur = next((j for j in sorted(jurs) if j and _gold(tools, code, j)), None)
        gold = _gold(tools, code, jur) if jur else None
        if gold is None:
            continue
        followups += 1
        msgs = [{"role": "user", "content": NO_STATE[0].format(code=code)},
                {"role": "assistant", "content": "This standard exists in several jurisdictions. Which one do you mean?"},
                {"role": "user", "content": jur}]
        cases.append(EvalCase(id=f"followup-{followups:02d}", kind="followup", messages=msgs, expect_status="answered",
                              target_id=gold[0], near_ids=gold[1], allowed_ids=gold[2], note=f"{code} / {jur}"))

    # same standards as the prerequisite cases, asked in other ways
    used = [c for c in cases if c.kind == "prerequisites"]
    for i, base in enumerate(used[:N_LOOKUP], start=1):
        code, jur = base.note.split(" / ")
        cases.append(base.model_copy(update={"id": f"lookup-{i:02d}", "kind": "lookup",
                                             "messages": [{"role": "user", "content": f"What is {code} in {jur}?"}]}))
    for i, (variant, base) in enumerate(zip(("lowercase code", "trailing period"), used[N_LOOKUP:], strict=False), start=1):
        code, jur = base.note.split(" / ")
        q = (f"what should students know before {code.lower()} in {jur}?" if i == 1
             else f"What should students know before {code}. in {jur}.")
        cases.append(base.model_copy(update={"id": f"variant-{i:02d}", "kind": "variant", "note": f"{base.note} ({variant})",
                                             "messages": [{"role": "user", "content": q}]}))

    topics = [(f"What should students know before learning {c}?", c, "concept") for c in CONCEPTS]
    topics += [(f'What should students know before the lesson "{n}"?', n, "lesson") for n in lessons]
    counts = {"concept": 0, "lesson": 0}
    for question, concept, kind in topics:
        if kind == "lesson" and counts["lesson"] >= N_LESSON:
            continue
        gold = _concept_gold(tools, concept)
        if gold is None:
            continue
        counts[kind] += 1
        status, target, near, allowed = gold
        cases.append(EvalCase(id=f"{kind}-{counts[kind]:02d}", kind=kind, messages=[{"role": "user", "content": question}],  # type: ignore[arg-type]
                              expect_status=status, target_id=target, near_ids=near, allowed_ids=allowed,
                              note=f"topic: {concept}; gold follows the search result, wording may differ"))

    for i, (code, jurs) in enumerate(multi[N_FOLLOWUP:N_FOLLOWUP + N_CLARIFY], start=1):
        q = NO_STATE[i % len(NO_STATE)].format(code=code)
        cases.append(EvalCase(id=f"clarify-{i:02d}", kind="clarify", messages=[{"role": "user", "content": q}],
                              expect_status="clarify", note=f"{code} exists in {len(jurs)} jurisdictions"))

    for i in range(1, N_NOT_FOUND + 1):
        code = f"99.ZZ.Z.{i}"
        cases.append(EvalCase(id=f"notfound-{i:02d}", kind="not_found", expect_status="not_found",
                              messages=[{"role": "user", "content": WITH_STATE[0].format(code=code, jur="Texas")}],
                              note="invented code"))

    for i, q in enumerate(UNSUPPORTED, start=1):
        cases.append(EvalCase(id=f"unsupported-{i:02d}", kind="unsupported", expect_status="unsupported",
                              messages=[{"role": "user", "content": q}], note="off topic"))
    return cases


def main() -> int:
    from common.ollama_client import (
        OllamaClient,  # tools need an embedder only for search, which is not used here
    )

    llm = OllamaClient(ollama_settings())
    reader = Neo4jReader(neo4j_settings())
    try:
        pairs = [(r["code"], r["jurisdiction"]) for r in reader.read(PAIRS_QUERY).rows]
        multi = [(r["code"], list(r["jurisdictions"])) for r in reader.read(MULTI_QUERY).rows]
        lessons = [r["name"] for r in reader.read(LESSON_QUERY).rows]
        cases = build_candidates(KGTools(reader, llm), pairs, multi, random.Random(SEED), lessons)
    finally:
        reader.close()
        llm.close()
    out = Path("evals/eval_candidates.jsonl")
    write_cases(out, cases)
    kinds = {k: sum(c.kind == k for c in cases) for k in sorted({c.kind for c in cases})}
    print(f"wrote {len(cases)} candidate cases to {out}: {kinds}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
