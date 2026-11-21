"""Accepted KG schema (masterplan section 9, Learning Commons KG v1.17.0) and a verifier.

Reused by the Phase 1 health check and Phase 2 ingest validation. Counts are the expected totals
from the original load; embeddings are added later without changing them.
"""
from __future__ import annotations

from dataclasses import dataclass

from common.constants import INGEST_META_LABEL
from common.protocols import GraphReader

NODE_COUNTS = {
    "StandardsFrameworkItem": 276_818,
    "LearningComponent": 10_731,
    "Activity": 8_173,
    "Misconception": 8_117,
    "Assessment": 4_516,
    "Lesson": 2_550,
    "Construct": 2_258,
    "MasteryThreshold": 1_022,
    "LessonGrouping": 764,
    "StandardsFramework": 266,
    "GuidanceFrameworkItem": 198,
    "Course": 18,
    "GuidanceFramework": 3,
}
REL_COUNTS = {
    "hasChild": 277_622,
    "supports": 154_124,
    "hasEducationalAlignment": 52_807,
    "hasStandardAlignment": 28_271,
    "hinders": 19_294,
    "hasPart": 15_944,
    "hasMasteryThreshold": 1_022,
    "buildsTowards": 757,
    "hasReference": 472,
    "relatesTo": 284,
    "hasDependency": 269,
    "mutuallyExclusiveWith": 192,
}
TOTAL_NODES = 315_434
TOTAL_RELS = 551_058


@dataclass(frozen=True)
class SchemaReport:
    ok: bool
    problems: list[str]
    total_nodes: int
    total_rels: int


def verify_schema(reader: GraphReader, *, deep: bool = False) -> SchemaReport:
    """Cheap check: totals, label set, relationship-type set. `deep` also checks per-label counts."""
    problems: list[str] = []
    # Ingest bookkeeping nodes are not KG data: exclude them so counts stay comparable.
    nodes = reader.read(
        f"MATCH (n) WHERE NOT n:`{INGEST_META_LABEL}` RETURN count(n) AS c"
    ).rows[0]["c"]
    rels = reader.read("MATCH ()-[r]->() RETURN count(r) AS c").rows[0]["c"]
    labels = {r["label"] for r in reader.read("CALL db.labels() YIELD label RETURN label").rows}
    labels.discard(INGEST_META_LABEL)
    types = {
        r["t"]
        for r in reader.read(
            "CALL db.relationshipTypes() YIELD relationshipType AS t RETURN t"
        ).rows
    }
    if nodes != TOTAL_NODES:
        problems.append(f"node count {nodes} != expected {TOTAL_NODES}")
    if rels != TOTAL_RELS:
        problems.append(f"relationship count {rels} != expected {TOTAL_RELS}")
    if missing := set(NODE_COUNTS) - labels:
        problems.append(f"missing labels: {sorted(missing)}")
    if extra := labels - set(NODE_COUNTS):
        problems.append(f"unexpected labels: {sorted(extra)}")
    if missing := set(REL_COUNTS) - types:
        problems.append(f"missing relationship types: {sorted(missing)}")
    if extra := types - set(REL_COUNTS):
        problems.append(f"unexpected relationship types: {sorted(extra)}")
    if deep:
        for label, expected in NODE_COUNTS.items():
            got = reader.read(f"MATCH (n:`{label}`) RETURN count(n) AS c").rows[0]["c"]
            if got != expected:
                problems.append(f"{label}: {got} != {expected}")
    return SchemaReport(not problems, problems, nodes, rels)
