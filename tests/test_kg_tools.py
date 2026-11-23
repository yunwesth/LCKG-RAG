import pytest

from ingest.targets import TARGETS
from kg_tools.cypher_guard import assert_read_only
from kg_tools.queries import CYPHER_DIR, load_query
from kg_tools.tools import SEARCHABLE_LABELS, KGTools, escape_lucene


class Result:
    def __init__(self, rows):
        self.rows, self.truncated = rows, False


class FakeReader:
    """Returns canned rows keyed by a marker found in the query text; records every call."""

    def __init__(self, by_marker=None):
        self.by_marker = by_marker or {}
        self.calls = []

    def read(self, query, params=None):
        self.calls.append((query, params))
        for marker, rows in self.by_marker.items():
            if marker in query:
                return Result(rows)
        return Result([])


class FakeEmbedder:
    def embed(self, texts):
        return [[0.1, 0.2] for _ in texts]


def node(i, **kw):
    return {"id": i, "label": "StandardsFrameworkItem", "code": kw.pop("code", i), **kw}


def tools(by_marker=None, **kw):
    reader = FakeReader(by_marker)
    return KGTools(reader, FakeEmbedder(), **kw), reader


# ---- the query files ---------------------------------------------------------------------
def test_every_cypher_file_passes_the_read_only_guard():
    files = list(CYPHER_DIR.glob("*.cypher"))
    assert len(files) >= 6
    for f in files:
        assert_read_only(f.read_text())


def test_every_cypher_file_is_parameterized_not_string_built():
    for f in CYPHER_DIR.glob("*.cypher"):
        assert "%s" not in f.read_text() and "{}" not in f.read_text(), f.name


@pytest.mark.parametrize("bad", ["../secret", "a/b", "Get_Node", "", "x.y"])
def test_load_query_rejects_path_tricks(bad):
    with pytest.raises(ValueError):
        load_query(bad)


def test_searchable_labels_match_ingest_targets():
    assert set(SEARCHABLE_LABELS) == {t.label for t in TARGETS}


# ---- get_node / find_standard_by_code -----------------------------------------------------
def test_get_node_returns_summary_and_none():
    t, r = tools({"RETURN": [node("A", name="x")]})
    assert t.get_node("A").id == "A"
    assert r.calls[0][1] == {"id": "A"}
    t2, _ = tools()
    assert t2.get_node("missing") is None


@pytest.mark.parametrize("bad", ["", "   "])
def test_empty_ids_rejected(bad):
    t, r = tools()
    with pytest.raises(ValueError):
        t.get_node(bad)
    with pytest.raises(ValueError):
        t.get_prerequisites(bad)
    assert r.calls == []


def test_find_by_code_passes_params_and_truncates():
    t, r = tools({"statementCode": [node("A"), node("B"), node("C")]})
    res = t.find_standard_by_code(" 8.EE.C.8 ", jurisdiction="Common Core", limit=2)
    assert [i.id for i in res.items] == ["A", "B"] and res.truncated
    assert r.calls[0][1] == {"code": "8.EE.C.8", "jurisdiction": "Common Core", "limit": 3}


# ---- search ------------------------------------------------------------------------------
def test_escape_lucene():
    assert escape_lucene('slope (y=mx+b)?') == r"slope \(y=mx\+b\)\?"
    assert escape_lucene("  plain words ") == "plain words"


def test_search_single_label_uses_that_index_and_label_filter():
    t, r = tools({"db.index.vector": [node("A", score=0.9)], "fulltext": [node("B", score=3.0)]})
    t.search_nodes("linear functions", labels=["StandardsFrameworkItem"], limit=5)
    vec = [c for c in r.calls if "db.index.vector" in c[0]]
    ft = [c for c in r.calls if "fulltext" in c[0]]
    assert len(vec) == 1 and vec[0][1]["index"] == "emb_StandardsFrameworkItem"
    assert vec[0][1]["vector"] == [0.1, 0.2]
    assert ft[0][1]["label"] == "StandardsFrameworkItem"


def test_search_defaults_to_all_labels():
    t, r = tools()
    t.search_nodes("anything")
    indexes = {c[1]["index"] for c in r.calls if "db.index.vector" in c[0]}
    assert indexes == {f"emb_{label}" for label in SEARCHABLE_LABELS}


def test_search_fuses_by_rank_and_dedupes():
    # B is found by both vector and full-text, so it should beat A (vector only) and C (text only).
    t, _ = tools(
        {
            "db.index.vector": [node("A", score=0.99), node("B", score=0.5)],
            "fulltext": [node("B", score=9.0), node("C", score=1.0)],
        }
    )
    res = t.search_nodes("q", labels=["StandardsFrameworkItem"], limit=10)
    assert [h.id for h in res.items] == ["B", "A", "C"]
    assert len({h.id for h in res.items}) == 3


def test_search_truncates_and_validates():
    t, _ = tools({"db.index.vector": [node(str(i), score=1 - i / 10) for i in range(5)]})
    res = t.search_nodes("q", labels=["Lesson"], limit=2)
    assert len(res.items) == 2 and res.truncated
    with pytest.raises(ValueError):
        t.search_nodes("q", labels=["MasteryThreshold"])
    with pytest.raises(ValueError):
        t.search_nodes("  ")


def test_search_punctuation_is_escaped_for_fulltext():
    t, r = tools()
    t.search_nodes("a+b?", labels=["Lesson"])
    ft = [c for c in r.calls if "fulltext" in c[0]]
    assert ft[0][1]["query"] == r"a\+b\?"


# ---- neighbors / prerequisites ------------------------------------------------------------
def test_get_neighbors_validates_inputs():
    t, r = tools()
    with pytest.raises(ValueError):
        t.get_neighbors("A", direction="sideways")
    with pytest.raises(ValueError):
        t.get_neighbors("A", rel_type="x) DETACH DELETE (n")
    assert r.calls == []


def test_get_neighbors_maps_rows():
    row = {**node("B"), "rel": "buildsTowards", "direction": "out"}
    t, r = tools({"startNode": [row]})
    res = t.get_neighbors("A", rel_type="buildsTowards", direction="out")
    assert res.items[0].rel == "buildsTowards" and res.items[0].id == "B"
    assert r.calls[0][1]["rel"] == "buildsTowards" and r.calls[0][1]["direction"] == "out"


def test_get_prerequisites_maps_depth_and_limits():
    rows = [{**node("P1"), "distance": 1}, {**node("P2"), "distance": 2}, {**node("P3"), "distance": 2}]
    t, r = tools({"buildsTowards": rows})
    res = t.get_prerequisites("S", max_depth=2, limit=2)
    assert [(p.id, p.distance) for p in res.items] == [("P1", 1), ("P2", 2)] and res.truncated
    assert r.calls[0][1] == {"id": "S", "max_depth": 2, "limit": 3}


@pytest.mark.parametrize("depth", [0, 7, -1])
def test_prerequisite_depth_bounds(depth):
    t, r = tools()
    with pytest.raises(ValueError):
        t.get_prerequisites("S", max_depth=depth)
    assert r.calls == []


def test_get_lesson_prerequisites_and_list_jurisdictions():
    class R:
        def __init__(self, rows): self.rows, self.truncated = rows, False
    seen = []
    class Reader:
        def read(self, q, params=None):
            seen.append(params)
            if "DISTINCT n.jurisdiction" in q:
                return R([{"jurisdiction": "Texas"}])
            return R([{"id": "L2", "label": "LessonGrouping", "name": "Make a Ten", "distance": 1}])
    tools = KGTools(Reader(), embedder=None)
    res = tools.get_lesson_prerequisites("L1", max_depth=2)
    assert [i.id for i in res.items] == ["L2"] and seen[0]["max_depth"] == 2
    assert tools.list_jurisdictions() == ["Texas"]
