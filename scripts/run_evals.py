"""Run the eval set against a running orchestrator and apply the regression gate.

    .venv/bin/python -m scripts.run_evals                      # score reviewed cases, compare to baseline
    .venv/bin/python -m scripts.run_evals --include-unreviewed # look at candidates (never gates or writes)
    .venv/bin/python -m scripts.run_evals --write-baseline     # record the current scores as the baseline

Exit codes: 0 ok, 1 regression, 2 nothing to run / bad usage.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from common.settings import orchestrator_settings
from evals.cases import load_cases
from evals.client import Asker, make_asker
from evals.metrics import aggregate, compare
from evals.runner import load_baseline, run_cases, save_baseline

DEFAULT_CASES = Path("evals/eval_set.jsonl")
DEFAULT_BASELINE = Path("evals/baseline.json")


def main(argv: list[str] | None = None, *, asker: Asker | None = None) -> int:
    cfg = orchestrator_settings()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    ap.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    ap.add_argument("--url", default=f"http://{cfg.host}:{cfg.port}")
    ap.add_argument("--tolerance", type=float, default=0.0, help="allowed drop per gated metric")
    ap.add_argument("--include-unreviewed", action="store_true")
    ap.add_argument("--kinds", help="comma-separated case kinds to run (a partial run never gates or writes a baseline)")
    ap.add_argument("--write-baseline", action="store_true")
    args = ap.parse_args(argv)

    cases = load_cases(args.cases, reviewed_only=not args.include_unreviewed)
    partial = bool(args.kinds)
    if partial:
        wanted = set(args.kinds.split(","))
        cases = [c for c in cases if c.kind in wanted]
    if not cases:
        print("No reviewed cases. Review evals/eval_set.jsonl (set reviewed=true) or pass --include-unreviewed.", file=sys.stderr)
        return 2
    if args.write_baseline and (args.include_unreviewed or partial):
        print("A baseline may only be written from the full set of reviewed cases.", file=sys.stderr)
        return 2

    ask = asker or make_asker(args.url, api_key=cfg.api_key.get_secret_value())
    results = run_cases(cases, ask)
    metrics = aggregate(results)
    for key, value in metrics.items():
        print(f"{key:>18}: {value}")
    for r in (r for r in results if not r.passed):
        print(f"FAIL {r.id} [{r.kind}] got={r.got_status} grounded={r.grounded} target_ok={r.target_ok} error={r.error}")

    if args.write_baseline:
        save_baseline(args.baseline, metrics, {"cases": len(cases), "cases_file": str(args.cases)})
        print(f"baseline written to {args.baseline}")
        return 0
    baseline = load_baseline(args.baseline)
    if baseline is None or args.include_unreviewed or partial:
        print("no gate applied (no baseline, unreviewed cases, or a partial run)")
        return 0
    problems = compare(metrics, baseline["metrics"], args.tolerance)
    for p in problems:
        print("REGRESSION", p)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
