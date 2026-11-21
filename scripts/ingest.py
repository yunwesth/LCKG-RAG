"""Phase 2 CLI: embed nodes, create vector indexes, validate. Safe to re-run (idempotent).

  python -m scripts.ingest                       # all labels
  python -m scripts.ingest --label LearningComponent --label Misconception
  python -m scripts.ingest --limit 200           # time a sample (indexes still created)
  python -m scripts.ingest --validate-only
"""
from __future__ import annotations

import argparse
import sys
import time

from common.errors import RagError
from common.ollama_client import OllamaClient
from common.settings import ingest_settings, neo4j_settings, ollama_settings
from ingest.pipeline import run
from ingest.store import Neo4jIngestStore
from ingest.targets import targets_by_label
from ingest.validate import validate


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--label", action="append", help="only this label (repeatable)")
    ap.add_argument("--limit", type=int, help="max nodes to embed per label")
    ap.add_argument("--validate-only", action="store_true")
    args = ap.parse_args(argv)

    targets = targets_by_label(args.label)
    o, i = ollama_settings(), ingest_settings()
    store = Neo4jIngestStore(neo4j_settings())
    embedder = OllamaClient(o)
    try:
        if not args.validate_only:
            t0 = time.monotonic()
            report = run(
                store,
                embedder,
                model=o.embed_model,
                targets=targets,
                batch_size=i.batch_size,
                max_chars=i.max_chars,
                limit=args.limit,
                progress=lambda m: print(f"\r{m}      ", end="", flush=True),
            )
            print()
            secs = time.monotonic() - t0
            for lab in report.labels:
                print(f"  {lab.label}: embedded {lab.embedded}")
            rate = report.total_embedded / secs if secs else 0
            print(f"model={report.model} dim={report.dimension} "
                  f"embedded={report.total_embedded} in {secs:.1f}s ({rate:.1f}/s)")
        # A sample run (--limit) is intentionally incomplete, so only enforce completeness otherwise.
        result = validate(store, model=o.embed_model, targets=targets,
                          expect_complete=args.limit is None)
        for label, (with_text, embedded) in result.per_label.items():
            print(f"  {label}: {embedded}/{with_text} embedded")
        if result.ok:
            print("VALIDATION PASS")
            return 0
        print("VALIDATION FAIL")
        for p in result.problems:
            print(f"  - {p}")
        return 1
    except RagError as e:
        print(f"ingest failed: {e}", file=sys.stderr)
        return 2
    finally:
        embedder.close()
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
