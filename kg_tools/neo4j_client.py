"""Read-only Neo4j access: guarded Cypher, read transactions, per-query timeout, result cap."""
from __future__ import annotations

from dataclasses import dataclass, field
from itertools import islice
from pathlib import Path
from typing import Any

from neo4j.exceptions import Neo4jError, ServiceUnavailable

from common.errors import KGUnavailable
from common.settings import Neo4jSettings
from kg_tools.cypher_guard import assert_read_only
from neo4j import Driver, GraphDatabase, unit_of_work

CYPHER_DIR = Path(__file__).parent / "cypher"


@dataclass(frozen=True)
class ReadResult:
    rows: list[dict[str, Any]] = field(default_factory=list)
    truncated: bool = False


class Neo4jReader:
    """The only Neo4j entry point for the orchestrator and tools. Cannot write by construction."""

    def __init__(self, settings: Neo4jSettings, *, driver: Driver | None = None) -> None:
        self._s = settings
        self._driver = driver or GraphDatabase.driver(
            settings.uri, auth=(settings.user, settings.password.get_secret_value())
        )

    def close(self) -> None:
        self._driver.close()

    def read(self, query: str, params: dict[str, Any] | None = None) -> ReadResult:
        assert_read_only(query)
        limit = self._s.result_limit
        # Server-side timeout must be set on the transaction function, not on a Query object.
        @unit_of_work(timeout=self._s.query_timeout_s)
        def work(tx):
            result = tx.run(query, params or {})
            rows = [r.data() for r in islice(result, limit + 1)]
            result.consume()
            return rows

        try:
            with self._driver.session(database=self._s.database) as session:
                rows = session.execute_read(work)
        except (ServiceUnavailable, Neo4jError, OSError) as e:
            raise KGUnavailable(f"Neo4j read failed: {e}") from e
        return ReadResult(rows=rows[:limit], truncated=len(rows) > limit)

    def read_file(self, name: str, params: dict[str, Any] | None = None) -> ReadResult:
        """Run a parameterized query stored in kg_tools/cypher/<name>.cypher."""
        path = (CYPHER_DIR / f"{name}.cypher").resolve()
        if CYPHER_DIR.resolve() not in path.parents:
            raise ValueError(f"query file outside cypher dir: {name}")
        return self.read(path.read_text(), params)

    def ping(self) -> bool:
        try:
            return bool(self.read("RETURN 1 AS ok").rows)
        except KGUnavailable:
            return False
