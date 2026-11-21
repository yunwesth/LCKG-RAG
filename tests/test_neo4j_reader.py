import pytest
from neo4j.exceptions import ServiceUnavailable

from common.errors import KGUnavailable, UnsafeQuery
from common.settings import Neo4jSettings
from kg_tools.neo4j_client import Neo4jReader


class Rec:
    def __init__(self, d):
        self._d = d

    def data(self):
        return self._d


class FakeResult:
    def __init__(self, rows):
        self._rows = [Rec(r) for r in rows]
        self.consumed = False

    def __iter__(self):
        return iter(self._rows)

    def consume(self):
        self.consumed = True


class FakeTx:
    def __init__(self, rows, log):
        self._rows, self._log = rows, log

    def run(self, query, params):
        self._log.append((query, params))
        return FakeResult(self._rows)


class FakeSession:
    def __init__(self, rows, log, fail):
        self._rows, self._log, self._fail = rows, log, fail

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute_read(self, work):
        self._log.append(("timeout", work.timeout))
        if self._fail:
            raise ServiceUnavailable("down")
        return work(FakeTx(self._rows, self._log))

    def execute_write(self, work):  # must never be used
        raise AssertionError("reader attempted a write transaction")


class FakeDriver:
    def __init__(self, rows=(), fail=False):
        self.rows, self.fail, self.log, self.closed = list(rows), fail, [], False

    def session(self, database=None):
        return FakeSession(self.rows, self.log, self.fail)

    def close(self):
        self.closed = True


def settings(limit=3):
    return Neo4jSettings(_env_file=None, NEO4J_RESULT_LIMIT=limit, NEO4J_QUERY_TIMEOUT_S=5)


def test_read_returns_rows_and_passes_params_with_timeout():
    d = FakeDriver([{"a": 1}, {"a": 2}])
    out = Neo4jReader(settings(), driver=d).read("MATCH (n) WHERE n.id=$id RETURN n", {"id": "x"})
    assert out.rows == [{"a": 1}, {"a": 2}] and not out.truncated
    assert d.log[0] == ("timeout", 5)  # timeout is applied to the transaction
    query, params = d.log[1]
    assert params == {"id": "x"} and isinstance(query, str)


def test_result_cap_sets_truncated():
    d = FakeDriver([{"a": i} for i in range(10)])
    out = Neo4jReader(settings(limit=3), driver=d).read("MATCH (n) RETURN n")
    assert len(out.rows) == 3 and out.truncated


def test_write_is_rejected_before_touching_the_driver():
    d = FakeDriver()
    with pytest.raises(UnsafeQuery):
        Neo4jReader(settings(), driver=d).read("MATCH (n) DETACH DELETE n")
    assert d.log == []  # nothing reached the driver


def test_connection_failure_becomes_kgunavailable():
    with pytest.raises(KGUnavailable):
        Neo4jReader(settings(), driver=FakeDriver(fail=True)).read("RETURN 1")


def test_ping_false_when_down_true_when_up():
    assert Neo4jReader(settings(), driver=FakeDriver(fail=True)).ping() is False
    assert Neo4jReader(settings(), driver=FakeDriver([{"ok": 1}])).ping() is True


def test_read_file_cannot_escape_cypher_dir():
    with pytest.raises(ValueError):
        Neo4jReader(settings(), driver=FakeDriver()).read_file("../neo4j_client")
