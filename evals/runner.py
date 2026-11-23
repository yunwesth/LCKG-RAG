"""Runs cases through an asker and handles the stored baseline."""
from __future__ import annotations

import json
from pathlib import Path

from evals.cases import EvalCase
from evals.client import Asker
from evals.metrics import CaseResult, score_case


def run_cases(cases: list[EvalCase], ask: Asker) -> list[CaseResult]:
    return [score_case(c, ask(c.messages)) for c in cases]


def save_baseline(path: Path, metrics: dict, meta: dict) -> None:
    path.write_text(json.dumps({"meta": meta, "metrics": metrics}, indent=2, sort_keys=True) + "\n")


def load_baseline(path: Path) -> dict | None:
    return json.loads(path.read_text()) if path.exists() else None
