"""Eval case format. One JSON object per line in `evals/eval_set.jsonl`."""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

Kind = Literal["prerequisites", "followup", "clarify", "concept", "lesson", "lookup", "variant", "not_found", "unsupported"]


class EvalCase(BaseModel):
    id: str
    kind: Kind
    messages: list[dict[str, str]] = Field(min_length=1)
    expect_status: str                                    # answered | clarify | not_found | unsupported
    target_id: str | None = None                          # node the first citation must be
    near_ids: list[str] = Field(default_factory=list)     # direct prerequisites; the answer should cite them
    allowed_ids: list[str] = Field(default_factory=list)  # target plus every node the answer may cite
    reviewed: bool = False                                # set to true only by the owner after review
    note: str = ""


def load_cases(path: Path, *, reviewed_only: bool = True) -> list[EvalCase]:
    cases = [EvalCase.model_validate_json(line) for line in path.read_text().splitlines() if line.strip()]
    ids = [c.id for c in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate case ids in " + str(path))
    return [c for c in cases if c.reviewed] if reviewed_only else cases


def write_cases(path: Path, cases: list[EvalCase]) -> None:
    path.write_text("".join(c.model_dump_json() + "\n" for c in cases))
