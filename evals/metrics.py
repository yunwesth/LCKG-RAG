"""Scoring and the regression gate. Higher is better for every gated metric."""
from __future__ import annotations

import math

from pydantic import BaseModel

from evals.cases import EvalCase


class Response(BaseModel):
    status: str | None = None
    citations: list[str] = []
    target: str | None = None  # the node the orchestrator resolved the question to
    reply: str = ""
    latency_s: float = 0.0
    error: str | None = None


class CaseResult(BaseModel):
    id: str
    kind: str
    passed: bool
    status_ok: bool
    target_ok: bool | None      # None when the case has no target; Resolve picked the right node
    cites_target: bool | None = None  # the answer itself cites the target [1]
    grounded: bool              # only cites allowed nodes (and cites nothing when no answer is expected)
    recall_near: float | None   # share of direct prerequisites that were cited; None when there are none
    latency_s: float
    error: str | None = None
    got_status: str | None = None


GATED = ("pass_rate", "status_accuracy", "target_accuracy", "grounding_rate", "mean_recall_near", "cites_target_rate")


def score_case(case: EvalCase, resp: Response) -> CaseResult:
    cites = resp.citations
    status_ok = resp.error is None and resp.status == case.expect_status
    target_ok = None if case.target_id is None else resp.target == case.target_id
    cites_target = None if case.target_id is None else case.target_id in cites
    if case.expect_status == "answered":
        grounded = resp.error is None and bool(cites) and set(cites) <= set(case.allowed_ids)
    else:
        grounded = not cites
    recall = None if not case.near_ids else len(set(case.near_ids) & set(cites)) / len(case.near_ids)
    passed = status_ok and grounded and target_ok is not False
    return CaseResult(id=case.id, kind=case.kind, passed=passed, status_ok=status_ok, target_ok=target_ok, cites_target=cites_target,
                      grounded=grounded, recall_near=recall, latency_s=resp.latency_s, error=resp.error,
                      got_status=resp.status)


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, math.ceil(q * len(ordered)) - 1)], 3)


def aggregate(results: list[CaseResult]) -> dict[str, float | int | None]:
    targets = [r.target_ok for r in results if r.target_ok is not None]
    recalls = [r.recall_near for r in results if r.recall_near is not None]
    latencies = [r.latency_s for r in results]
    return {
        "n": len(results),
        "pass_rate": _mean([float(r.passed) for r in results]),
        "status_accuracy": _mean([float(r.status_ok) for r in results]),
        "target_accuracy": _mean([float(t) for t in targets]),
        "grounding_rate": _mean([float(r.grounded) for r in results]),
        "mean_recall_near": _mean(recalls),
        "cites_target_rate": _mean([float(r.cites_target) for r in results if r.cites_target is not None]),
        "errors": sum(1 for r in results if r.error),
        "latency_p50_s": _percentile(latencies, 0.5),
        "latency_p95_s": _percentile(latencies, 0.95),
    }


def compare(current: dict, baseline: dict, tolerance: float = 0.0) -> list[str]:
    """Names every gated metric that fell below the baseline by more than `tolerance`."""
    problems = []
    for key in GATED:
        before, now = baseline.get(key), current.get(key)
        if before is None:
            continue
        if now is None or now < before - tolerance:
            problems.append(f"{key}: {now} < baseline {before} (tolerance {tolerance})")
    return problems
