"""Phase 2 exit check: embeddings complete, indexes online with the right dimension, metadata matches.

Read-only apart from using the ingest store's connection. Returns problems instead of raising so
the CLI can print all of them at once.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ingest.store import IngestStore
from ingest.targets import EmbedTarget

FULLTEXT_INDEX = "kg_search"


@dataclass(frozen=True)
class ValidationReport:
    ok: bool
    problems: list[str]
    per_label: dict[str, tuple[int, int]]  # label -> (nodes with text, nodes embedded)


def validate(
    store: IngestStore,
    *,
    model: str,
    targets: Sequence[EmbedTarget],
    expect_complete: bool = True,
) -> ValidationReport:
    problems: list[str] = []
    per_label: dict[str, tuple[int, int]] = {}

    meta = store.get_meta()
    if meta is None:
        problems.append("no embedding metadata recorded (ingest has not run)")
    elif meta.model != model:
        problems.append(f"metadata model {meta.model!r} != configured {model!r}")

    for t in targets:
        with_text = store.count_with_text(t)
        embedded = store.count_embedded(t)
        per_label[t.label] = (with_text, embedded)
        if expect_complete and embedded != with_text:
            problems.append(f"{t.label}: {with_text - embedded} of {with_text} nodes missing embedding")
        if embedded > with_text:
            problems.append(f"{t.label}: {embedded} embeddings but only {with_text} nodes with text")
        idx = store.vector_index(t)
        if idx is None:
            problems.append(f"{t.label}: vector index {t.index_name} missing")
        else:
            if idx.state != "ONLINE":
                problems.append(f"{t.label}: index {t.index_name} is {idx.state}, not ONLINE")
            if meta and idx.dimension != meta.dimension:
                problems.append(
                    f"{t.label}: index dimension {idx.dimension} != metadata {meta.dimension}"
                )
            if (idx.similarity or "").lower() != "cosine":
                problems.append(f"{t.label}: index similarity {idx.similarity!r}, expected cosine")
        if meta and embedded:
            wrong = store.bad_dimension_count(t, meta.dimension)
            if wrong:
                problems.append(f"{t.label}: {wrong} embeddings with wrong dimension")

    if not store.has_fulltext_index(FULLTEXT_INDEX):
        problems.append(f"full-text index {FULLTEXT_INDEX} missing or not ONLINE")
    for t in targets:
        if t.label not in store.unique_constraint_labels():
            problems.append(f"{t.label}: no unique constraint on identifier")

    return ValidationReport(not problems, problems, per_label)
