"""Run against the real Neo4j (and Ollama for search). Deselected by `make test`: pytest -m live."""
import pytest

from common.settings import neo4j_settings, ollama_settings
from kg_tools.neo4j_client import Neo4jReader
from kg_tools.tools import KGTools

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def reader():
    r = Neo4jReader(neo4j_settings())
    yield r
    r.close()


@pytest.fixture(scope="module")
def tools(reader):
    from common.ollama_client import OllamaClient

    return KGTools(reader, OllamaClient(ollama_settings()))


@pytest.fixture(scope="module")
def sample(reader):
    rows = reader.read(
        "MATCH (a:StandardsFrameworkItem)-[:buildsTowards]->(b:StandardsFrameworkItem)"
        " RETURN a.identifier AS pre, b.identifier AS target, b.statementCode AS code LIMIT 1"
    ).rows
    return rows[0]


def test_get_node_and_code_lookup(tools, sample):
    n = tools.get_node(sample["target"])
    assert n.id == sample["target"] and n.label == "StandardsFrameworkItem"
    found = tools.find_standard_by_code(sample["code"], limit=500)  # codes repeat across jurisdictions
    assert sample["target"] in {i.id for i in found.items}
    assert tools.get_node("does-not-exist") is None


def test_prerequisites_direction_and_ids(tools, sample):
    res = tools.get_prerequisites(sample["target"], max_depth=3)
    ids = [p.id for p in res.items]
    assert sample["pre"] in ids and sample["target"] not in ids
    assert all(p.id and p.distance >= 1 for p in res.items)
    assert res.items[0].distance == 1


def test_neighbors_directions(tools, sample):
    out = tools.get_neighbors(sample["pre"], rel_type="buildsTowards", direction="out")
    assert sample["target"] in {n.id for n in out.items}
    back = tools.get_neighbors(sample["target"], rel_type="buildsTowards", direction="in")
    assert sample["pre"] in {n.id for n in back.items}


def test_search_finds_standard_by_meaning(tools):
    res = tools.search_nodes(
        "solving systems of linear equations", labels=["StandardsFrameworkItem"], limit=5
    )
    assert res.items and all(h.id for h in res.items)
