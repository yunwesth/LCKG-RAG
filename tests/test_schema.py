from kg_tools.neo4j_client import ReadResult
from kg_tools.schema import NODE_COUNTS, REL_COUNTS, TOTAL_NODES, TOTAL_RELS, verify_schema


class FakeReader:
    def __init__(self, nodes=TOTAL_NODES, rels=TOTAL_RELS, labels=None, types=None):
        self.nodes, self.rels = nodes, rels
        self.labels = list(NODE_COUNTS) if labels is None else labels
        self.types = list(REL_COUNTS) if types is None else types

    def read(self, query, params=None):
        if "count(n)" in query and "MATCH (n:" not in query:
            return ReadResult([{"c": self.nodes}])
        if "count(r)" in query:
            return ReadResult([{"c": self.rels}])
        if "db.labels" in query:
            return ReadResult([{"label": x} for x in self.labels])
        if "db.relationshipTypes" in query:
            return ReadResult([{"t": x} for x in self.types])
        label = query.split("`")[1]
        return ReadResult([{"c": NODE_COUNTS[label]}])


def test_totals_match_the_accepted_schema():
    assert sum(NODE_COUNTS.values()) == TOTAL_NODES
    assert sum(REL_COUNTS.values()) == TOTAL_RELS


def test_ok_when_everything_matches():
    r = verify_schema(FakeReader(), deep=True)
    assert r.ok and r.problems == []


def test_reports_each_kind_of_drift():
    r = verify_schema(
        FakeReader(nodes=10, labels=["Course", "Surprise"], types=["hasChild"])
    )
    text = " ".join(r.problems)
    assert not r.ok
    assert "node count 10" in text
    assert "missing labels" in text and "unexpected labels" in text
    assert "missing relationship types" in text
