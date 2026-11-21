"""Typed, read-only tools over the knowledge graph. Every result carries node identifiers.

Each tool is one small method. A new question type is a new `.cypher` file plus a new method here;
nothing else changes. Tools depend on the `GraphReader` and `Embedder` Protocols, never on a concrete
client, so they are tested with fakes and run unchanged against real Neo4j and Ollama.
"""
from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict

from common.protocols import Embedder, GraphReader
from kg_tools.queries import load_query

# Labels that have a text embedding (`emb_<Label>` vector index). Matches ingest/targets.py;
# kg_tools may not import ingest, so a test keeps the two lists equal.
SEARCHABLE_LABELS: tuple[str, ...] = (
    "StandardsFrameworkItem", "LearningComponent", "Misconception", "Construct",
    "GuidanceFrameworkItem", "StandardsFramework", "GuidanceFramework", "Course",
    "LessonGrouping", "Lesson", "Activity", "Assessment",
)
DIRECTIONS = ("out", "in", "both")
MAX_PREREQUISITE_DEPTH = 6  # matches the *1..6 bound in get_prerequisites.cypher
_REL_TYPE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_LUCENE_SPECIAL = re.compile(r'([+\-&|!(){}\[\]^"~*?:\\/])')
_RRF_K = 60  # reciprocal rank fusion constant


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class NodeSummary(_Frozen):
    id: str
    label: str
    code: str | None = None
    name: str | None = None
    description: str | None = None
    grade_level: list[str] | None = None
    jurisdiction: str | None = None
    subject: str | None = None


class SearchHit(NodeSummary):
    score: float


class Neighbor(NodeSummary):
    rel: str
    direction: str


class Prerequisite(NodeSummary):
    distance: int


T = TypeVar("T")


class ToolResult(_Frozen, Generic[T]):
    items: list[T]
    truncated: bool = False


def _summary(row: dict[str, Any]) -> dict[str, Any]:
    keys = NodeSummary.model_fields
    return {k: row.get(k) for k in keys}


def escape_lucene(text: str) -> str:
    """Make free text safe for the full-text index: special characters become literals."""
    return _LUCENE_SPECIAL.sub(r"\\\1", text).strip()


class KGTools:
    def __init__(self, reader: GraphReader, embedder: Embedder, *, default_limit: int = 10) -> None:
        self._reader = reader
        self._embedder = embedder
        self._default_limit = default_limit

    # ---- lookups -------------------------------------------------------------------------
    def get_node(self, node_id: str) -> NodeSummary | None:
        _require_text(node_id, "node_id")
        rows = self._reader.read(load_query("get_node"), {"id": node_id}).rows
        return NodeSummary(**_summary(rows[0])) if rows else None

    def find_standard_by_code(
        self, code: str, *, jurisdiction: str | None = None, limit: int | None = None
    ) -> ToolResult[NodeSummary]:
        _require_text(code, "code")
        limit = self._limit(limit)
        rows = self._reader.read(
            load_query("find_by_code"),
            {"code": code.strip(), "jurisdiction": jurisdiction, "limit": limit + 1},
        ).rows
        return ToolResult(
            items=[NodeSummary(**_summary(r)) for r in rows[:limit]], truncated=len(rows) > limit
        )

    # ---- search --------------------------------------------------------------------------
    def search_nodes(
        self, query: str, *, labels: Sequence[str] | None = None, limit: int | None = None
    ) -> ToolResult[SearchHit]:
        """Hybrid search: meaning (vector) plus keywords (full-text), merged by rank fusion."""
        _require_text(query, "query")
        limit = self._limit(limit)
        labels = tuple(labels) if labels else SEARCHABLE_LABELS
        for label in labels:
            if label not in SEARCHABLE_LABELS:
                raise ValueError(f"unknown or non-searchable label: {label!r}")

        vector = self._embedder.embed([query])[0]
        ranked: list[list[dict[str, Any]]] = []
        for label in labels:
            rows = self._reader.read(
                load_query("search_vector"),
                {"index": f"emb_{label}", "limit": limit, "vector": vector},
            ).rows
            ranked.append(rows)

        text = escape_lucene(query)
        if text:
            fulltext_label = labels[0] if len(labels) == 1 else None
            rows = self._reader.read(
                load_query("search_fulltext"),
                {"query": text, "label": fulltext_label, "limit": limit * len(labels)},
            ).rows
            if len(labels) > 1:
                rows = [r for r in rows if r.get("label") in labels]
            ranked.append(rows)

        # Scores from different indexes are not comparable, so fuse by rank, not score.
        ranked = [sorted(r, key=lambda x: x.get("score") or 0, reverse=True) for r in ranked]
        fused: dict[str, float] = {}
        rows_by_id: dict[str, dict[str, Any]] = {}
        for rows in ranked:
            for rank, row in enumerate(rows):
                fused[row["id"]] = fused.get(row["id"], 0.0) + 1.0 / (_RRF_K + rank + 1)
                rows_by_id.setdefault(row["id"], row)
        order = sorted(fused, key=lambda i: fused[i], reverse=True)
        hits = [SearchHit(**_summary(rows_by_id[i]), score=fused[i]) for i in order[:limit]]
        return ToolResult(items=hits, truncated=len(order) > limit)

    # ---- graph traversal -----------------------------------------------------------------
    def get_neighbors(
        self,
        node_id: str,
        *,
        rel_type: str | None = None,
        direction: str = "both",
        limit: int | None = None,
    ) -> ToolResult[Neighbor]:
        _require_text(node_id, "node_id")
        if direction not in DIRECTIONS:
            raise ValueError(f"direction must be one of {DIRECTIONS}, got {direction!r}")
        if rel_type is not None and not _REL_TYPE.match(rel_type):
            raise ValueError(f"invalid relationship type: {rel_type!r}")
        limit = self._limit(limit)
        rows = self._reader.read(
            load_query("get_neighbors"),
            {"id": node_id, "rel": rel_type, "direction": direction, "limit": limit + 1},
        ).rows
        items = [Neighbor(**_summary(r), rel=r["rel"], direction=r["direction"]) for r in rows[:limit]]
        return ToolResult(items=items, truncated=len(rows) > limit)

    def get_prerequisites(
        self, node_id: str, *, max_depth: int = 3, limit: int | None = None
    ) -> ToolResult[Prerequisite]:
        """Standards that build towards `node_id`, nearest first (distance 1 = direct prerequisite)."""
        _require_text(node_id, "node_id")
        if not 1 <= max_depth <= MAX_PREREQUISITE_DEPTH:
            raise ValueError(f"max_depth must be 1..{MAX_PREREQUISITE_DEPTH}, got {max_depth}")
        limit = self._limit(limit)
        rows = self._reader.read(
            load_query("get_prerequisites"),
            {"id": node_id, "max_depth": max_depth, "limit": limit + 1},
        ).rows
        items = [Prerequisite(**_summary(r), distance=r["distance"]) for r in rows[:limit]]
        return ToolResult(items=items, truncated=len(rows) > limit)

    def _limit(self, limit: int | None) -> int:
        value = self._default_limit if limit is None else limit
        if value < 1:
            raise ValueError("limit must be at least 1")
        return value


def _require_text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
