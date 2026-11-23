"""Narrow interfaces between modules. Consumers depend on these, never on a concrete client,
so any module can be tested with a fake and any backend can be swapped (masterplan modularity rule)."""
from __future__ import annotations

from collections.abc import Sequence
from contextlib import AbstractContextManager
from typing import Any, Protocol


class Embedder(Protocol):
    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class ChatModel(Protocol):
    def chat(self, messages: Sequence[dict[str, str]], *, schema: dict[str, Any] | None = None) -> str:
        """Return the assistant message text. If `schema` is given, output must be JSON matching it."""
        ...


class GraphReader(Protocol):
    def read(self, query: str, params: dict[str, Any] | None = None) -> ReadResult: ...


class ReadResult(Protocol):
    rows: list[dict[str, Any]]
    truncated: bool


class Span(Protocol):
    def update(self, *, output: Any = None, level: str | None = None, message: str | None = None) -> None: ...


class Tracer(Protocol):
    """Records one span per pipeline step. Must never raise into the caller; a no-op when tracing is off."""

    def span(self, name: str, *, kind: str = "span", input: Any = None,
             metadata: dict[str, Any] | None = None) -> AbstractContextManager[Span]: ...

    def flush(self) -> None: ...

    def shutdown(self) -> None: ...
