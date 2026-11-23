"""Tracing tests: a recording tracer and a fake Langfuse client (no server, no network)."""
from contextlib import contextmanager

import pytest

from common.settings import LangfuseSettings
from common.tracing import LangfuseTracer, NoopTracer, build_tracer
from orchestrator.graph import Pipeline
from orchestrator.state import Status
from tests.test_orchestrator import FakeChat, FakeTools, U, node


class Recorder:
    """Tracer that records spans as (depth, name, kind, input, output, level)."""

    def __init__(self):
        self.spans, self.depth, self.shut = [], 0, False

    @contextmanager
    def span(self, name, *, kind="span", input=None, metadata=None):
        rec = {"depth": self.depth, "name": name, "kind": kind, "input": input, "output": None, "level": None}
        self.spans.append(rec)

        class H:
            def update(_, *, output=None, level=None, message=None):
                if output is not None:
                    rec["output"] = output
                rec["level"] = level or rec["level"]

        self.depth += 1
        try:
            yield H()
        except BaseException:
            rec["level"] = "ERROR"
            raise
        finally:
            self.depth -= 1

    def flush(self): ...

    def shutdown(self):
        self.shut = True


def answered_tools():
    return FakeTools(by_code=[node("T", code="8.EE.C.8", jur="Texas")], prereqs=[node("P", code="7.EE.B.4")])


def run(tracer, chat=None, tools=None):
    p = Pipeline(chat or FakeChat(U), tools or answered_tools(), tracer=tracer)
    return p, p.run([{"role": "user", "content": "What comes before 8.EE.C.8?"}])


def test_pipeline_records_one_span_per_node_llm_call_and_tool_call():
    rec = Recorder()
    _, out = run(rec)
    assert out.status is Status.ANSWERED
    names = [s["name"] for s in rec.spans]
    assert names[0] == "pipeline"
    for n in ("node.understand", "node.resolve", "node.retrieve", "node.synthesize", "node.verify"):
        assert n in names
    assert names.count("llm.chat") == 2  # Understand + Synthesize
    assert "tool.find_standard_by_code" in names and "tool.get_prerequisites" in names


def test_spans_nest_under_the_pipeline_span():
    rec = Recorder()
    run(rec)
    by_name = {s["name"]: s for s in rec.spans}
    assert by_name["pipeline"]["depth"] == 0
    assert by_name["node.resolve"]["depth"] == 1
    assert by_name["tool.find_standard_by_code"]["depth"] == 2
    assert by_name["pipeline"]["output"]["status"] == "answered"


def test_tool_span_output_is_a_compact_summary():
    rec = Recorder()
    run(rec)
    tool = next(s for s in rec.spans if s["name"] == "tool.get_prerequisites")
    assert tool["output"]["count"] == 1 and tool["output"]["ids"] == ["P"]


def test_llm_span_is_a_generation_with_prompt_and_text():
    rec = Recorder()
    run(rec)
    gens = [s for s in rec.spans if s["kind"] == "generation"]
    assert len(gens) == 2 and all(g["input"] and g["output"] for g in gens)


def test_clarify_path_skips_retrieve_and_synthesize():
    rec = Recorder()
    tools = FakeTools(by_code=[node("A", code="X", jur="Texas"), node("B", code="X", jur="Maryland")])
    run(rec, tools=tools)
    names = [s["name"] for s in rec.spans]
    assert "node.retrieve" not in names and "node.synthesize" not in names


def test_failure_marks_the_span_and_still_returns_a_refusal():
    class Boom(FakeTools):
        def get_prerequisites(self, *a, **k):
            raise RuntimeError("secret detail")

    rec = Recorder()
    _, out = run(rec, tools=Boom(by_code=[node("T", code="8.EE.C.8", jur="Texas")]))
    assert out.status is Status.REFUSED
    assert next(s for s in rec.spans if s["name"] == "tool.get_prerequisites")["level"] == "ERROR"


def test_close_shuts_the_tracer_down():
    rec = Recorder()
    p, _ = run(rec)
    p.close()
    assert rec.shut


def test_tracing_does_not_change_the_answer():
    plain = Pipeline(FakeChat(U), answered_tools()).run([{"role": "user", "content": "What comes before 8.EE.C.8?"}])
    _, traced = run(Recorder())
    assert (plain.status, plain.reply, plain.citations) == (traced.status, traced.reply, traced.citations)


# --- Noop and settings ---

def test_noop_tracer_yields_a_usable_span():
    with NoopTracer().span("x", input={"a": 1}) as s:
        s.update(output="y")


def test_tracing_off_without_keys(monkeypatch):
    for k in ("LANGFUSE_HOST", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
        monkeypatch.delenv(k, raising=False)
    cfg = LangfuseSettings(_env_file=None)
    assert not cfg.enabled
    assert isinstance(build_tracer(cfg), NoopTracer)


def test_tracing_needs_host_and_both_keys():
    assert not LangfuseSettings(_env_file=None, LANGFUSE_HOST="http://x", LANGFUSE_PUBLIC_KEY="pk").enabled
    assert LangfuseSettings(_env_file=None, LANGFUSE_HOST="http://x", LANGFUSE_PUBLIC_KEY="pk",
                            LANGFUSE_SECRET_KEY="sk").enabled


# --- LangfuseTracer over a fake client ---

class FakeObs:
    def __init__(self, log, kwargs):
        self.log, self.kwargs, self.updates = log, kwargs, []

    def update(self, **kw):
        self.updates.append(kw)


class FakeCM:
    def __init__(self, obs, log, fail_enter=False):
        self.obs, self.log, self.fail_enter, self.exit_args = obs, log, fail_enter, None

    def __enter__(self):
        if self.fail_enter:
            raise RuntimeError("down")
        return self.obs

    def __exit__(self, *a):
        self.exit_args = a


class FakeLangfuse:
    def __init__(self, fail_enter=False):
        self.cms, self.flushed, self.stopped, self.fail_enter = [], False, False, fail_enter

    def start_as_current_observation(self, **kwargs):
        cm = FakeCM(FakeObs(self.cms, kwargs), self.cms, self.fail_enter)
        self.cms.append(cm)
        return cm

    def flush(self):
        self.flushed = True

    def shutdown(self):
        self.stopped = True


def test_langfuse_tracer_passes_name_kind_input_and_output():
    lf = FakeLangfuse()
    with LangfuseTracer(lf).span("node.x", kind="chain", input={"q": "hello"}) as s:
        s.update(output={"ok": 1})
    obs = lf.cms[0].obs
    assert obs.kwargs["name"] == "node.x" and obs.kwargs["as_type"] == "chain" and obs.kwargs["input"] == {"q": "hello"}
    assert obs.updates == [{"output": {"ok": 1}}]


def test_unknown_kind_falls_back_to_span():
    lf = FakeLangfuse()
    with LangfuseTracer(lf).span("x", kind="weird"):
        pass
    assert lf.cms[0].obs.kwargs["as_type"] == "span"


def test_capture_content_off_keeps_sizes_not_text():
    lf = FakeLangfuse()
    with LangfuseTracer(lf, capture_content=False).span("x", input={"question": "secret words"}) as s:
        s.update(output="answer text")
    obs = lf.cms[0].obs
    assert obs.kwargs["input"] == {"question": {"chars": 12}}
    assert obs.updates == [{"output": {"chars": 11}}]
    assert "secret" not in str(obs.kwargs) + str(obs.updates)


def test_exception_is_marked_by_type_only_and_reraised():
    lf = FakeLangfuse()
    with pytest.raises(ValueError), LangfuseTracer(lf).span("x"):
        raise ValueError("private prompt text")
    obs = lf.cms[0].obs
    assert obs.updates == [{"level": "ERROR", "status_message": "ValueError"}]
    assert lf.cms[0].exit_args[0] is ValueError


def test_broken_langfuse_never_breaks_the_caller():
    lf = FakeLangfuse(fail_enter=True)
    with LangfuseTracer(lf).span("x") as s:
        s.update(output="fine")


def test_flush_and_shutdown_delegate_and_swallow_errors():
    lf = FakeLangfuse()
    t = LangfuseTracer(lf)
    t.flush(), t.shutdown()
    assert lf.flushed and lf.stopped

    class Bad:
        def flush(self):
            raise RuntimeError

        def shutdown(self):
            raise RuntimeError

    LangfuseTracer(Bad()).flush()
    LangfuseTracer(Bad()).shutdown()
