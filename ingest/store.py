"""Neo4j access for ingest. The only code that uses admin credentials (see test_module_boundaries).

`IngestStore` is the Protocol the pipeline and validator depend on, so they are tested with fakes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from common.constants import EMBEDDING_PROPERTY, INGEST_META_LABEL
from common.errors import KGUnavailable
from common.settings import Neo4jSettings
from ingest.targets import EmbedTarget
from neo4j import Driver, GraphDatabase

META_KEY = "embedding"


@dataclass(frozen=True)
class EmbeddingMeta:
    model: str
    dimension: int


@dataclass(frozen=True)
class PendingNode:
    identifier: str
    props: dict[str, Any]


@dataclass(frozen=True)
class IndexInfo:
    state: str
    dimension: int | None
    similarity: str | None


class IngestStore(Protocol):
    def get_meta(self) -> EmbeddingMeta | None: ...
    def set_meta(self, meta: EmbeddingMeta) -> None: ...
    def fetch_pending(self, t: EmbedTarget, after: str | None, limit: int) -> list[PendingNode]: ...
    def write_embeddings(self, t: EmbedTarget, rows: list[tuple[str, list[float]]]) -> None: ...
    def count_with_text(self, t: EmbedTarget) -> int: ...
    def count_embedded(self, t: EmbedTarget) -> int: ...
    def bad_dimension_count(self, t: EmbedTarget, dimension: int) -> int: ...
    def ensure_vector_index(self, t: EmbedTarget, dimension: int) -> None: ...
    def vector_index(self, t: EmbedTarget) -> IndexInfo | None: ...
    def has_fulltext_index(self, name: str) -> bool: ...
    def unique_constraint_labels(self) -> set[str]: ...


def _has_text(t: EmbedTarget) -> str:
    return f"n.`{t.primary}` IS NOT NULL AND trim(toString(n.`{t.primary}`)) <> ''"


class Neo4jIngestStore:
    def __init__(self, settings: Neo4jSettings, *, driver: Driver | None = None) -> None:
        self._s = settings
        self._driver = driver or GraphDatabase.driver(
            settings.uri,
            auth=(settings.admin_user, settings.admin_password.get_secret_value()),
            notifications_min_severity="OFF",  # first-run probes of absent labels are expected
        )

    def close(self) -> None:
        self._driver.close()

    def _run(self, query: str, **params: Any) -> list[dict[str, Any]]:
        try:
            with self._driver.session(database=self._s.database) as session:
                return session.run(query, params).data()
        except Exception as e:  # driver, auth and service errors all mean "KG not usable"
            raise KGUnavailable(f"Neo4j ingest query failed: {e}") from e

    def get_meta(self) -> EmbeddingMeta | None:
        rows = self._run(
            f"MATCH (m:`{INGEST_META_LABEL}` {{key: $key}}) RETURN m.model AS model, m.dimension AS dim",
            key=META_KEY,
        )
        return EmbeddingMeta(rows[0]["model"], rows[0]["dim"]) if rows else None

    def set_meta(self, meta: EmbeddingMeta) -> None:
        self._run(
            f"MERGE (m:`{INGEST_META_LABEL}` {{key: $key}}) "
            "ON CREATE SET m.model = $model, m.dimension = $dim, m.created = toString(datetime())",
            key=META_KEY,
            model=meta.model,
            dim=meta.dimension,
        )

    def fetch_pending(self, t: EmbedTarget, after: str | None, limit: int) -> list[PendingNode]:
        projection = ", ".join(f".`{p}`" for p in t.parts)
        rows = self._run(
            f"MATCH (n:`{t.label}`) "
            f"WHERE n.`{EMBEDDING_PROPERTY}` IS NULL AND ($after IS NULL OR n.identifier > $after) "
            f"AND {_has_text(t)} "
            f"RETURN n.identifier AS id, n {{ {projection} }} AS props "
            "ORDER BY n.identifier LIMIT $limit",
            after=after,
            limit=limit,
        )
        return [PendingNode(r["id"], r["props"]) for r in rows]

    def write_embeddings(self, t: EmbedTarget, rows: list[tuple[str, list[float]]]) -> None:
        self._run(
            "UNWIND $rows AS row "
            f"MATCH (n:`{t.label}` {{identifier: row.id}}) "
            f"CALL db.create.setNodeVectorProperty(n, '{EMBEDDING_PROPERTY}', row.vec)",
            rows=[{"id": i, "vec": v} for i, v in rows],
        )

    def count_with_text(self, t: EmbedTarget) -> int:
        return self._run(f"MATCH (n:`{t.label}`) WHERE {_has_text(t)} RETURN count(n) AS c")[0]["c"]

    def count_embedded(self, t: EmbedTarget) -> int:
        return self._run(
            f"MATCH (n:`{t.label}`) WHERE n.`{EMBEDDING_PROPERTY}` IS NOT NULL RETURN count(n) AS c"
        )[0]["c"]

    def bad_dimension_count(self, t: EmbedTarget, dimension: int) -> int:
        return self._run(
            f"MATCH (n:`{t.label}`) WHERE n.`{EMBEDDING_PROPERTY}` IS NOT NULL "
            f"AND size(n.`{EMBEDDING_PROPERTY}`) <> $dim RETURN count(n) AS c",
            dim=dimension,
        )[0]["c"]

    def ensure_vector_index(self, t: EmbedTarget, dimension: int) -> None:
        self._run(
            f"CREATE VECTOR INDEX `{t.index_name}` IF NOT EXISTS "
            f"FOR (n:`{t.label}`) ON (n.`{EMBEDDING_PROPERTY}`) "
            "OPTIONS {indexConfig: {`vector.dimensions`: $dim, `vector.similarity_function`: 'cosine'}}",
            dim=dimension,
        )
        self._run("CALL db.awaitIndexes(300)")

    def vector_index(self, t: EmbedTarget) -> IndexInfo | None:
        rows = self._run(
            "SHOW INDEXES YIELD name, type, state, options WHERE name = $name AND type = 'VECTOR' "
            "RETURN state, options",
            name=t.index_name,
        )
        if not rows:
            return None
        cfg = (rows[0]["options"] or {}).get("indexConfig", {})
        return IndexInfo(
            rows[0]["state"], cfg.get("vector.dimensions"), cfg.get("vector.similarity_function")
        )

    def has_fulltext_index(self, name: str) -> bool:
        return bool(
            self._run(
                "SHOW INDEXES YIELD name, type, state WHERE name = $n AND type = 'FULLTEXT' "
                "AND state = 'ONLINE' RETURN name",
                n=name,
            )
        )

    def unique_constraint_labels(self) -> set[str]:
        rows = self._run(
            "SHOW CONSTRAINTS YIELD type, labelsOrTypes WHERE type = 'UNIQUENESS' "
            "RETURN labelsOrTypes AS labels"
        )
        return {label for r in rows for label in r["labels"]}
