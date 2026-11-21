"""Ingest unit tests with in-memory fakes (no Neo4j, no Ollama)."""
import pytest

from common.errors import ConfigError
from ingest.pipeline import run
from ingest.store import EmbeddingMeta, IndexInfo, PendingNode
from ingest.targets import TARGETS, EmbedTarget, build_text, normalize, targets_by_label
from ingest.validate import validate

DIM = 4
T = EmbedTarget("Thing", "description", ("code", "description"))


class FakeEmbedder:
    def __init__(self, dim=DIM):
        self.dim, self.calls = dim, 0

    def embed(self, texts):
        self.calls += 1
        return [[float(len(t))] * self.dim for t in texts]


class FakeStore:
    """Keeps nodes in memory; mimics keyset pagination and 'embedding IS NULL' filtering."""

    def __init__(self, nodes, meta=None):
        self.nodes = {i: {"props": p, "vec": None} for i, p in nodes.items()}
        self.meta, self.indexes, self.writes = meta, {}, 0

    def get_meta(self):
        return self.meta

    def set_meta(self, meta):
        self.meta = meta

    def _text_ok(self, t, n):
        return bool(normalize(n["props"].get(t.primary)))

    def fetch_pending(self, t, after, limit):
        ids = sorted(
            i for i, n in self.nodes.items()
            if n["vec"] is None and self._text_ok(t, n) and (after is None or i > after)
        )
        return [PendingNode(i, self.nodes[i]["props"]) for i in ids[:limit]]

    def write_embeddings(self, t, rows):
        self.writes += len(rows)
        for i, v in rows:
            self.nodes[i]["vec"] = v

    def count_with_text(self, t):
        return sum(self._text_ok(t, n) for n in self.nodes.values())

    def count_embedded(self, t):
        return sum(n["vec"] is not None for n in self.nodes.values())

    def bad_dimension_count(self, t, dimension):
        return sum(n["vec"] is not None and len(n["vec"]) != dimension for n in self.nodes.values())

    def ensure_vector_index(self, t, dimension):
        self.indexes[t.index_name] = IndexInfo("ONLINE", dimension, "cosine")

    def vector_index(self, t):
        return self.indexes.get(t.index_name)

    def has_fulltext_index(self, name):
        return True

    def unique_constraint_labels(self):
        return {t.label for t in TARGETS} | {T.label}


def nodes(n):
    return {f"id{i:03d}": {"code": f"C{i}", "description": f"desc {i}"} for i in range(n)}


def run_all(store, embedder=None, **kw):
    return run(store, embedder or FakeEmbedder(), model="m", targets=[T], batch_size=3,
               max_chars=100, **kw)


def test_embeds_every_node_with_text_and_creates_index():
    data = nodes(10) | {"empty": {"code": "X", "description": "   "}}
    store = FakeStore(data)
    report = run_all(store)
    assert report.total_embedded == 10
    assert store.count_embedded(T) == 10 == store.count_with_text(T)
    assert store.indexes["emb_Thing"].dimension == DIM
    assert store.meta == EmbeddingMeta("m", DIM)


def test_rerun_changes_nothing():
    store = FakeStore(nodes(7))
    run_all(store)
    writes, calls = store.writes, FakeEmbedder()
    report = run_all(store, calls)
    assert report.total_embedded == 0 and store.writes == writes
    assert calls.calls == 1  # only the dimension probe


def test_resumes_after_interruption():
    store = FakeStore(nodes(9))
    run_all(store, limit=4)
    assert store.count_embedded(T) == 4
    run_all(store)
    assert store.count_embedded(T) == 9


def test_refuses_silent_model_change():
    store = FakeStore(nodes(2), meta=EmbeddingMeta("other-model", DIM))
    with pytest.raises(ConfigError, match="other-model"):
        run_all(store)
    assert store.writes == 0


def test_refuses_dimension_change():
    store = FakeStore(nodes(2), meta=EmbeddingMeta("m", 999))
    with pytest.raises(ConfigError):
        run_all(store)


def test_validate_passes_after_complete_run():
    store = FakeStore(nodes(5))
    run_all(store)
    assert validate(store, model="m", targets=[T]).ok


def test_validate_reports_missing_embeddings_and_index():
    store = FakeStore(nodes(5))
    run_all(store, limit=2)
    store.indexes.clear()
    r = validate(store, model="m", targets=[T])
    text = " ".join(r.problems)
    assert not r.ok and "missing embedding" in text and "index emb_Thing missing" in text


def test_validate_flags_wrong_dimension_and_model():
    store = FakeStore(nodes(3))
    run_all(store)
    store.nodes["id000"]["vec"] = [1.0]
    r = validate(store, model="different", targets=[T])
    text = " ".join(r.problems)
    assert "wrong dimension" in text and "metadata model" in text


def test_build_text_joins_normalizes_and_truncates():
    t = EmbedTarget("X", "description", ("code", "description"))
    assert build_text(t, {"code": "K.1", "description": " a\n  b "}, 100) == "K.1. a b"
    assert build_text(t, {"code": "K.1", "description": "  "}, 100) is None
    assert build_text(t, {"description": "x" * 50}, 10) == "x" * 10


def test_targets_are_safe_and_selectable():
    assert len({t.label for t in TARGETS}) == len(TARGETS)
    assert [t.label for t in targets_by_label(["Lesson"])] == ["Lesson"]
    with pytest.raises(ValueError):
        targets_by_label(["Nope"])
    with pytest.raises(ValueError):
        EmbedTarget("Bad`Label", "d", ("d",))
    with pytest.raises(ValueError):
        EmbedTarget("Ok", "missing", ("d",))
