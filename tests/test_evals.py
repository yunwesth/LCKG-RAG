import json
import random

import httpx
import pytest

from evals.cases import EvalCase, load_cases, write_cases
from evals.client import make_asker
from evals.metrics import Response, aggregate, compare, score_case
from kg_tools.tools import NodeSummary, Prerequisite, ToolResult
from scripts import run_evals
from scripts.build_eval_candidates import build_candidates

CASE = EvalCase(id="c1", kind="prerequisites", messages=[{"role": "user", "content": "q"}], expect_status="answered",
                target_id="T", near_ids=["A", "B"], allowed_ids=["T", "A", "B", "C"])


def resp(status="answered", cites=("T", "A", "B"), target="T", **kw):
    return Response(status=status, citations=list(cites), target=target, latency_s=1.0, **kw)


def test_perfect_answer_passes():
    r = score_case(CASE, resp())
    assert r.passed and r.target_ok and r.grounded and r.recall_near == 1.0


def test_wrong_target_or_uncited_prerequisites_are_measured():
    assert not score_case(CASE, resp(target="OTHER")).passed
    r = score_case(CASE, resp(cites=("A", "B")))  # right node resolved, but the answer never cites it
    assert r.passed and r.target_ok and r.cites_target is False
    assert score_case(CASE, resp(cites=("T", "A"))).recall_near == 0.5


def test_citing_a_node_outside_the_allowed_set_is_not_grounded():
    r = score_case(CASE, resp(cites=("T", "ZZZ")))
    assert not r.grounded and not r.passed


def test_non_answers_must_not_cite_anything():
    clarify = EvalCase(id="x", kind="clarify", messages=[{"role": "user", "content": "q"}], expect_status="clarify")
    assert score_case(clarify, resp("clarify", ())).passed
    assert not score_case(clarify, resp("answered", ("T",))).passed


def test_transport_errors_fail_the_case():
    r = score_case(CASE, Response(error="ConnectError"))
    assert not r.passed and r.error == "ConnectError"


def test_aggregate_and_percentiles():
    results = [score_case(CASE, resp()), score_case(CASE, resp(cites=("A",), target="X"))]
    m = aggregate(results)
    assert m["n"] == 2 and m["pass_rate"] == 0.5 and m["target_accuracy"] == 0.5 and m["latency_p95_s"] == 1.0
    assert aggregate([])["pass_rate"] is None


def test_gate_flags_drops_only():
    base = {"pass_rate": 0.9, "grounding_rate": 1.0, "mean_recall_near": None}
    assert compare({"pass_rate": 0.9, "grounding_rate": 1.0}, base) == []
    assert compare({"pass_rate": 0.95, "grounding_rate": 1.0}, base) == []
    assert len(compare({"pass_rate": 0.8, "grounding_rate": 1.0}, base)) == 1
    assert compare({"pass_rate": 0.89, "grounding_rate": 1.0}, base, tolerance=0.02) == []
    assert compare({"pass_rate": None, "grounding_rate": 1.0}, base)  # a missing metric is a regression
    assert compare({"cites_target_rate": 0.7}, {"cites_target_rate": 1.0})  # citing the target is gated too


def test_cases_round_trip_and_reviewed_filter(tmp_path):
    path = tmp_path / "set.jsonl"
    write_cases(path, [CASE, CASE.model_copy(update={"id": "c2", "reviewed": True})])
    assert [c.id for c in load_cases(path, reviewed_only=False)] == ["c1", "c2"]
    assert [c.id for c in load_cases(path)] == ["c2"]
    write_cases(path, [CASE, CASE])
    with pytest.raises(ValueError):
        load_cases(path, reviewed_only=False)


def test_http_asker_reads_the_lcrag_extension_and_survives_failures():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer k"
        return httpx.Response(200, json={"choices": [{"message": {"content": "hi"}}], "lcrag": {"status": "answered", "citations": ["T"], "target": "T"}})
    out = make_asker("http://x", api_key="k", transport=httpx.MockTransport(handler))([{"role": "user", "content": "q"}])
    assert out.status == "answered" and out.citations == ["T"] and out.target == "T" and out.error is None

    bad = make_asker("http://x", transport=httpx.MockTransport(lambda r: httpx.Response(500)))([{"role": "user", "content": "q"}])
    assert bad.error == "http 500"

    def boom(request):
        raise httpx.ConnectError("down")
    assert make_asker("http://x", transport=httpx.MockTransport(boom))([{"role": "user", "content": "q"}]).error == "ConnectError"


class FakeTools:
    def search_nodes(self, query, *, labels=None, limit=None):
        if query == "place value":  # a standard that exists in two jurisdictions: Resolve would ask which one
            return ToolResult(items=[NodeSummary(id="S1", label="StandardsFrameworkItem", jurisdiction="Texas"),
                                     NodeSummary(id="S2", label="StandardsFrameworkItem", jurisdiction="Ohio")])
        if query == "nothing":
            return ToolResult(items=[])
        return ToolResult(items=[NodeSummary(id=f"L-{query}", label="LessonGrouping")])

    def get_lesson_prerequisites(self, node_id, *, max_depth=3, limit=None):
        return ToolResult(items=[Prerequisite(id=f"{node_id}-p1", label="LessonGrouping", distance=1)])

    def find_standard_by_code(self, code, *, jurisdiction=None, limit=None):
        if code.startswith("DUP"):
            return ToolResult(items=[NodeSummary(id="1", label="L"), NodeSummary(id="2", label="L")])
        return ToolResult(items=[NodeSummary(id=f"{code}-{jurisdiction}", label="StandardsFrameworkItem", code=code)])

    def get_prerequisites(self, node_id, *, max_depth=3, limit=None):
        if node_id.startswith("NOPRE"):
            return ToolResult(items=[])
        return ToolResult(items=[Prerequisite(id=f"{node_id}-p1", label="L", distance=1), Prerequisite(id=f"{node_id}-p2", label="L", distance=2)])


def test_candidate_builder_makes_every_kind_with_gold_from_the_tools():
    pairs = [(f"C.{i}.X", "Texas") for i in range(30)] + [("DUP.1", "Texas"), ("NOPRE.1", "Texas"), ("2", "Texas")]
    multi = [(f"{i + 1}.NF.A.{i + 1}", ["Texas", "Ohio"]) for i in range(12)] + [("2", ["Texas", "Ohio"])]
    multi += [("LS2.C", ["Texas", "Ohio"]), ("W.5.2.a", ["Texas", "Ohio"]), ("4.MP.6", ["Texas", "Ohio"])]
    cases = build_candidates(FakeTools(), pairs, multi, random.Random(1), ["Metric Measurement", "Place Value Lesson", "Counting"])
    kinds = [c.kind for c in cases]
    assert kinds.count("prerequisites") == 20 and kinds.count("followup") == 5 and kinds.count("clarify") == 6
    assert kinds.count("lookup") == 3 and kinds.count("variant") == 2 and kinds.count("lesson") == 3 and kinds.count("concept") == 5
    assert not any(c.note.startswith(("LS2.C", "W.5.2.a", "4.MP.6")) for c in cases)  # science, ELA, practice codes are skipped
    clarify_concept = next(c for c in cases if c.kind == "concept" and "place value" in c.note)
    assert clarify_concept.expect_status == "clarify" and clarify_concept.target_id is None
    lesson = next(c for c in cases if c.kind == "lesson")
    assert lesson.expect_status == "answered" and lesson.near_ids == [f"{lesson.target_id}-p1"]
    assert next(c for c in cases if c.kind == "variant").messages[0]["content"] != next(c for c in cases if c.kind == "prerequisites").messages[0]["content"]
    assert kinds.count("not_found") == 3 and kinds.count("unsupported") == 4
    p = next(c for c in cases if c.kind == "prerequisites")
    assert p.target_id in p.allowed_ids and p.near_ids == [f"{p.target_id}-p1"] and not p.reviewed
    assert all("DUP.1" not in c.note and "NOPRE.1" not in c.note for c in cases)
    assert all(c.note.split(" ")[0] != "2" for c in cases)  # bare "2" is not a standard code  # ambiguous or empty gold is skipped
    f = next(c for c in cases if c.kind == "followup")
    assert [m["role"] for m in f.messages] == ["user", "assistant", "user"]
    assert len({c.id for c in cases}) == len(cases)


def test_run_evals_cli_gate(tmp_path, capsys):
    cases = tmp_path / "set.jsonl"
    base = tmp_path / "base.json"
    write_cases(cases, [CASE.model_copy(update={"reviewed": True})])
    good = lambda msgs: resp()
    bad = lambda msgs: resp(cites=("T",))
    args = ["--cases", str(cases), "--baseline", str(base)]
    assert run_evals.main([*args, "--include-unreviewed", "--write-baseline"], asker=good) == 2
    assert run_evals.main([*args, "--write-baseline"], asker=good) == 0 and base.exists()
    assert run_evals.main(args, asker=good) == 0
    assert run_evals.main(args, asker=bad) == 1 and "REGRESSION" in capsys.readouterr().out
    assert json.loads(base.read_text())["metrics"]["pass_rate"] == 1.0


def test_run_evals_refuses_when_nothing_is_reviewed(tmp_path):
    cases = tmp_path / "set.jsonl"
    write_cases(cases, [CASE])
    assert run_evals.main(["--cases", str(cases)], asker=lambda m: resp()) == 2


def test_kinds_filter_runs_a_partial_set_without_gating(tmp_path):
    cases = tmp_path / "set.jsonl"
    base = tmp_path / "base.json"
    clarify = EvalCase(id="k", kind="clarify", messages=[{"role": "user", "content": "q"}], expect_status="clarify", reviewed=True)
    write_cases(cases, [CASE.model_copy(update={"reviewed": True}), clarify])
    args = ["--cases", str(cases), "--baseline", str(base)]
    assert run_evals.main([*args, "--write-baseline"], asker=lambda m: resp("clarify", ())) == 0  # clarify fits, prerequisites does not
    asked = []
    assert run_evals.main([*args, "--kinds", "clarify"], asker=lambda m: asked.append(m) or resp("clarify", ())) == 0
    assert len(asked) == 1
    assert run_evals.main([*args, "--kinds", "clarify", "--write-baseline"], asker=lambda m: resp("clarify", ())) == 2
