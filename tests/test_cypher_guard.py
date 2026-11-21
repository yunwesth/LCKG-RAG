import pytest

from common.errors import UnsafeQuery
from kg_tools.cypher_guard import assert_read_only


@pytest.mark.parametrize(
    "q",
    [
        "MATCH (n:StandardsFrameworkItem {identifier: $id}) RETURN n",
        "MATCH (a)-[:buildsTowards*1..3]->(b) RETURN a, b LIMIT 25",
        "CALL db.labels() YIELD label RETURN label",
        "CALL db.index.fulltext.queryNodes('kg_search', $text) YIELD node RETURN node",
        "MATCH (n) WHERE n.name = 'CREATE ME' RETURN n",  # keyword only inside a string literal
        "MATCH (n) RETURN n // SET is fine in a comment",
    ],
)
def test_allows_reads(q):
    assert_read_only(q)


@pytest.mark.parametrize(
    "q",
    [
        "CREATE (n:X) RETURN n",
        "MATCH (n) SET n.x = 1",
        "MATCH (n) DETACH DELETE n",
        "MERGE (n:X {id: 1})",
        "MATCH (n) REMOVE n.x",
        "LOAD CSV FROM 'file:///x.csv' AS row RETURN row",
        "MATCH (n) RETURN n; MATCH (m) DELETE m",
        "CALL apoc.cypher.doIt('CREATE (n)', {})",
        "CALL { CREATE (n) } RETURN 1",
        "MATCH (n) FOREACH (x IN [1] | SET n.a = x)",
        "DROP INDEX kg_search",
        "",
        "   ",
    ],
)
def test_rejects_writes_and_unknowns(q):
    with pytest.raises(UnsafeQuery):
        assert_read_only(q)
