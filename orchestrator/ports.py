"""What the orchestrator needs from the tool layer, as a Protocol, so nodes are tested with fakes."""
from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from kg_tools.tools import NodeSummary, Prerequisite, SearchHit, ToolResult


class KnowledgeTools(Protocol):
    def find_standard_by_code(
        self, code: str, *, jurisdiction: str | None = None, limit: int | None = None
    ) -> ToolResult[NodeSummary]: ...

    def search_nodes(
        self, query: str, *, labels: Sequence[str] | None = None, limit: int | None = None
    ) -> ToolResult[SearchHit]: ...

    def get_prerequisites(
        self, node_id: str, *, max_depth: int = 3, limit: int | None = None
    ) -> ToolResult[Prerequisite]: ...

    def get_lesson_prerequisites(
        self, node_id: str, *, max_depth: int = 3, limit: int | None = None
    ) -> ToolResult[Prerequisite]: ...

    def list_jurisdictions(self) -> list[str]: ...
