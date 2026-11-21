"""Static read-only check for Cypher text.

Neo4j Community has no read-only users (RBAC is Enterprise-only), so read-only is enforced in
code: this guard (defence in depth) plus read transactions in `neo4j_client`. Fails closed:
anything it cannot classify as a plain read is rejected.
"""
from __future__ import annotations

import re

from common.errors import UnsafeQuery

_WRITE_KEYWORDS = re.compile(
    r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|FOREACH|LOAD\s+CSV|"
    r"START|GRANT|DENY|REVOKE|ALTER|RENAME|TERMINATE)\b",
    re.IGNORECASE,
)
_CALL = re.compile(r"\bCALL\s+([A-Za-z0-9_.]+)", re.IGNORECASE)
_SUBQUERY_CALL = re.compile(r"\bCALL\s*(\(.*?\))?\s*\{", re.IGNORECASE | re.DOTALL)

# Read-only procedures the tool layer may call.
ALLOWED_PROCEDURES = frozenset(
    {
        "db.labels",
        "db.relationshiptypes",
        "db.propertykeys",
        "db.index.fulltext.querynodes",
        "db.index.fulltext.queryrelationships",
        "db.index.vector.querynodes",
    }
)


def _strip_literals_and_comments(q: str) -> str:
    q = re.sub(r"//[^\n]*", " ", q)
    q = re.sub(r"/\*.*?\*/", " ", q, flags=re.DOTALL)
    q = re.sub(r"'(?:[^'\\]|\\.)*'", "''", q)
    q = re.sub(r'"(?:[^"\\]|\\.)*"', '""', q)
    return q


def assert_read_only(query: str) -> None:
    """Raise UnsafeQuery unless `query` is a single read-only statement."""
    if not query or not query.strip():
        raise UnsafeQuery("empty query")
    q = _strip_literals_and_comments(query)
    if ";" in q.strip().rstrip(";"):
        raise UnsafeQuery("multiple statements are not allowed")
    if m := _WRITE_KEYWORDS.search(q):
        raise UnsafeQuery(f"write clause not allowed: {m.group(1).upper()}")
    if _SUBQUERY_CALL.search(q):
        raise UnsafeQuery("CALL subqueries are not allowed")
    for proc in _CALL.findall(q):
        if proc.lower() not in ALLOWED_PROCEDURES:
            raise UnsafeQuery(f"procedure not allowed: {proc}")
