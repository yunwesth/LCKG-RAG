"""Pipeline tests with a scripted chat model and fake tools (no Neo4j, no Ollama)."""
import json

from common.errors import LLMUnavailable
from kg_tools.tools import NodeSummary, Prerequisite, SearchHit, ToolResult
from orchestrator.graph import Pipeline
from orchestrator.state import Status


def node(i, label="StandardsFrameworkItem", code=None, name=None, jur=None):
    return {"id": i, "label": label, "code": code, "name": name, "description": name or code, "jurisdiction": jur}


class FakeChat:
    def __init__(self, understanding, answer="Students should first learn the earlier standard [2] before the target [1]."):
        self.understanding, self.answer, self.calls = understanding, answer, []

    def chat(self, messages, *, schema=None):
        self.calls.append(schema is not None)
        if schema is not None:
            return json.dumps(self.understanding) if isinstance(self.understanding, dict) else self.understanding
        return self.answer


class FakeTools:
    def __init__(self, by_code=(), hits=(), prereqs=(), lesson_prereqs=(), truncated=False):
        self.by_code, self.hits, self.prereqs = list(by_code), list(hits), list(prereqs)
        self.lesson_prereqs, self.truncated = list(lesson_prereqs), truncated
        self.code_calls = []

    def list_jurisdictions(self):
        return ["Maryland", "Texas", "Multi-State"]

    def find_standard_by_code(self, code, *, jurisdiction=None, limit=None):
        self.code_calls.append(jurisdiction)
        items = [n for n in self.by_code if jurisdiction in (None, n["jurisdiction"])]
        return ToolResult(items=[NodeSummary(**n) for n in items])

    def search_nodes(self, query, *, labels=None, limit=None):
        return ToolResult(items=[SearchHit(**h, score=1.0) for h in self.hits])

    def get_prerequisites(self, node_id, *, max_depth=3, limit=None):
        return ToolResult(items=[Prerequisite(**p, distance=1) for p in self.prereqs], truncated=self.truncated)

    def get_lesson_prerequisites(self, node_id, *, max_depth=3, limit=None):
        return ToolResult(items=[Prerequisite(**p, distance=1) for p in self.lesson_prereqs])


def ask(chat, tools, text="What comes before 8.EE.C.8?"):
    return Pipeline(chat, tools).run([{"role": "user", "content": text}])


U = {"intent": "prerequisites", "concept": None, "code": "8.EE.C.8", "jurisdiction": None}


def test_code_in_one_jurisdiction_is_answered_with_citations():
    tools = FakeTools(by_code=[node("T", code="8.EE.C.8", jur="Texas")], prereqs=[node("P", code="7.EE.B.4")])
    out = ask(FakeChat(U), tools)
    assert out.status is Status.ANSWERED
    assert out.citations == ["T", "P"]
    assert "T (StandardsFrameworkItem)" in out.reply


def test_code_in_several_jurisdictions_asks_which_one():
    tools = FakeTools(by_code=[node("A", code="X", jur="Texas"), node("B", code="X", jur="Maryland")])
    chat = FakeChat(U)
    out = ask(chat, tools)
    assert out.status is Status.CLARIFY
    assert "Maryland" in out.reply and "Texas" in out.reply
    assert chat.calls == [True]  # no Synthesize call


def test_korean_user_gets_korean_clarification():
    tools = FakeTools(by_code=[node("A", jur="Texas"), node("B", jur="Maryland")])
    assert "어느 주" in ask(FakeChat(U), tools, "8.EE.C.8 선수 개념 알려줘").reply


def test_stated_jurisdiction_is_validated_case_insensitively_and_passed_on():
    tools = FakeTools(by_code=[node("A", jur="Texas"), node("B", jur="Maryland")], prereqs=[node("P")])
    out = ask(FakeChat({**U, "jurisdiction": "texas"}), tools)
    assert out.status is Status.ANSWERED and tools.code_calls == ["Texas"]


def test_invented_jurisdiction_is_ignored_so_user_is_asked():
    tools = FakeTools(by_code=[node("A", jur="Texas"), node("B", jur="Maryland")])
    assert ask(FakeChat({**U, "jurisdiction": "Narnia"}), tools).status is Status.CLARIFY


def test_concept_search_on_lesson_grouping_needs_no_jurisdiction():
    tools = FakeTools(hits=[node("L", "LessonGrouping", name="Add within 20")],
                      lesson_prereqs=[node("L2", "LessonGrouping", name="Make a Ten")])
    out = ask(FakeChat({"intent": "prerequisites", "concept": "add within 20", "code": None, "jurisdiction": None}), tools)
    assert out.status is Status.ANSWERED and out.citations == ["L", "L2"]


def test_nothing_found():
    out = ask(FakeChat(U), FakeTools())
    assert out.status is Status.NOT_FOUND


def test_unsupported_intent_and_garbage_llm_output_fail_closed():
    assert ask(FakeChat({"intent": "unsupported", "concept": None, "code": None, "jurisdiction": None}), FakeTools()).status is Status.UNSUPPORTED
    assert ask(FakeChat("not json"), FakeTools()).status is Status.UNSUPPORTED


def test_answer_citing_unknown_reference_is_refused():
    tools = FakeTools(by_code=[node("T", jur="Texas")], prereqs=[node("P")])
    assert ask(FakeChat(U, answer="Students should first learn the earlier standard [9]."), tools).status is Status.REFUSED


def test_answer_without_citation_is_refused():
    tools = FakeTools(by_code=[node("T", jur="Texas")], prereqs=[node("P")])
    assert ask(FakeChat(U, answer="Just learn it."), tools).status is Status.REFUSED


def test_no_prerequisites_skips_the_llm_and_cites_the_target():
    tools = FakeTools(by_code=[node("T", jur="Texas")])
    chat = FakeChat(U)
    out = ask(chat, tools)
    assert out.status is Status.ANSWERED and out.citations == ["T"] and chat.calls == [True]


def test_think_blocks_are_stripped():
    tools = FakeTools(by_code=[node("T", jur="Texas")], prereqs=[node("P")])
    out = ask(FakeChat(U, answer="<think>[7] hmm</think>Students should first learn the earlier standard [2]."), tools)
    assert out.status is Status.ANSWERED


def test_truncation_is_disclosed():
    tools = FakeTools(by_code=[node("T", jur="Texas")], prereqs=[node("P")], truncated=True)
    assert "truncated" in ask(FakeChat(U), tools).reply


def test_llm_outage_returns_a_refusal_not_an_exception():
    class Down:
        def chat(self, *a, **k):
            raise LLMUnavailable("down")
    out = ask(Down(), FakeTools())
    assert out.status is Status.REFUSED


def test_unknown_code_is_not_replaced_by_a_topic_search():
    tools = FakeTools(hits=[node("L", "LessonGrouping", name="Something else")])
    out = ask(FakeChat({**U, "concept": "linear equations"}), tools)
    assert out.status is Status.NOT_FOUND


def test_answer_that_is_only_citation_numbers_is_refused():
    tools = FakeTools(by_code=[node("T", jur="Texas")], prereqs=[node("P")])
    assert ask(FakeChat(U, answer="[1] [2]"), tools).status is Status.REFUSED


def test_language_follows_the_conversation_not_just_the_last_message():
    tools = FakeTools(by_code=[node("A", jur="Texas"), node("B", jur="Maryland")])
    msgs = [{"role": "user", "content": "8.EE.C.8 선수 개념"}, {"role": "assistant", "content": "?"},
            {"role": "user", "content": "Ohio"}]
    assert "어느 주" in Pipeline(FakeChat(U), tools).run(msgs).reply
