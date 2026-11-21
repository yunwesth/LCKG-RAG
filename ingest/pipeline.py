"""Idempotent embedding ingest. Only embeds nodes that have text and no embedding yet, so a re-run
on a finished database finds nothing to do and writes nothing (masterplan Phase 2 exit).

Depends on the `Embedder` Protocol and `IngestStore`, never on Ollama or Neo4j directly.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from common.errors import ConfigError
from common.protocols import Embedder
from ingest.store import EmbeddingMeta, IngestStore
from ingest.targets import EmbedTarget, build_text

PROBE_TEXT = "dimension probe"


@dataclass
class LabelReport:
    label: str
    embedded: int = 0
    skipped_empty: int = 0


@dataclass
class RunReport:
    model: str
    dimension: int
    labels: list[LabelReport] = field(default_factory=list)

    @property
    def total_embedded(self) -> int:
        return sum(lab.embedded for lab in self.labels)


def ensure_meta(store: IngestStore, embedder: Embedder, model: str) -> EmbeddingMeta:
    """Measure the model's dimension, record model + dimension once, refuse a silent change."""
    probe = embedder.embed([PROBE_TEXT])
    dim = len(probe[0])
    wanted = EmbeddingMeta(model=model, dimension=dim)
    stored = store.get_meta()
    if stored is None:
        store.set_meta(wanted)
        return wanted
    if stored != wanted:
        raise ConfigError(
            f"database was embedded with {stored.model} (dim {stored.dimension}) but config now "
            f"gives {wanted.model} (dim {wanted.dimension}). Changing the embedding model needs a "
            "full re-embed: drop the embeddings and vector indexes first."
        )
    return stored


def run(
    store: IngestStore,
    embedder: Embedder,
    *,
    model: str,
    targets: Sequence[EmbedTarget],
    batch_size: int,
    max_chars: int,
    limit: int | None = None,
    progress: Callable[[str], None] = lambda _msg: None,
) -> RunReport:
    """Embed every pending node of each target, then make sure its vector index exists.

    `limit` caps nodes embedded per label (for timing a sample); indexes are still created.
    """
    meta = ensure_meta(store, embedder, model)
    report = RunReport(model=meta.model, dimension=meta.dimension)
    for target in targets:
        lab = LabelReport(target.label)
        cursor: str | None = None
        while limit is None or lab.embedded < limit:
            take = batch_size if limit is None else min(batch_size, limit - lab.embedded)
            pending = store.fetch_pending(target, cursor, take)
            if not pending:
                break
            cursor = pending[-1].identifier
            ids: list[str] = []
            texts: list[str] = []
            for node in pending:
                text = build_text(target, node.props, max_chars)
                if text is None:
                    lab.skipped_empty += 1
                else:
                    ids.append(node.identifier)
                    texts.append(text)
            if texts:
                vectors = embedder.embed(texts)
                bad = [len(v) for v in vectors if len(v) != meta.dimension]
                if bad:
                    raise ConfigError(
                        f"{target.label}: got vector length {bad[0]}, expected {meta.dimension}"
                    )
                store.write_embeddings(target, list(zip(ids, vectors, strict=True)))
                lab.embedded += len(texts)
            progress(f"{target.label}: {lab.embedded} embedded")
        store.ensure_vector_index(target, meta.dimension)
        report.labels.append(lab)
    return report
