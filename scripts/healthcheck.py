"""Phase 1 exit check: is each external dependency reachable and as expected?

    .venv/bin/python -m scripts.healthcheck [--deep]

Each check runs independently, so one failure does not hide the others. Exits non-zero on any failure.
"""
from __future__ import annotations

import argparse
import sys
from collections.abc import Callable

from common.errors import RagError
from common.ollama_client import OllamaClient
from common.settings import neo4j_settings, ollama_settings
from kg_tools.neo4j_client import Neo4jReader
from kg_tools.schema import verify_schema


def check_neo4j() -> str:
    reader = Neo4jReader(neo4j_settings())
    try:
        if not reader.ping():
            raise RagError("Neo4j did not answer RETURN 1")
        return "reachable"
    finally:
        reader.close()


def check_schema(deep: bool) -> Callable[[], str]:
    def run() -> str:
        reader = Neo4jReader(neo4j_settings())
        try:
            report = verify_schema(reader, deep=deep)
        finally:
            reader.close()
        if not report.ok:
            raise RagError("; ".join(report.problems))
        return f"{report.total_nodes:,} nodes, {report.total_rels:,} relationships match"
    return run


def check_read_only() -> str:
    """The client must refuse writes before they reach the server."""
    from common.errors import UnsafeQuery

    reader = Neo4jReader(neo4j_settings())
    try:
        try:
            reader.read("CREATE (n:__HealthcheckShouldNeverExist) RETURN n")
        except UnsafeQuery:
            return "write attempts are rejected"
        raise RagError("write query was NOT rejected")
    finally:
        reader.close()


def check_ollama_models() -> str:
    s = ollama_settings()
    client = OllamaClient(s)
    try:
        missing = [m for m in (s.chat_model, s.embed_model) if not client.has_model(m)]
        if missing:
            raise RagError(f"not pulled: {', '.join(missing)} (run `ollama pull <tag>`)")
        return f"chat={s.chat_model}, embed={s.embed_model} installed"
    finally:
        client.close()


def check_embedding_dimension() -> str:
    client = OllamaClient(ollama_settings())
    try:
        dim = len(client.embed(["healthcheck"])[0])
        return f"embedding dimension = {dim} (record this in Neo4j metadata in Phase 2)"
    finally:
        client.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--deep", action="store_true", help="also check per-label node counts")
    args = ap.parse_args()
    checks: list[tuple[str, Callable[[], str]]] = [
        ("neo4j connection", check_neo4j),
        ("neo4j read-only guard", check_read_only),
        ("kg schema", check_schema(args.deep)),
        ("ollama models", check_ollama_models),
        ("ollama embedding", check_embedding_dimension),
    ]
    failed = 0
    for name, fn in checks:
        try:
            print(f"PASS  {name}: {fn()}")
        except Exception as e:  # noqa: BLE001 - report every failure, never crash the checker
            failed += 1
            print(f"FAIL  {name}: {e}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
