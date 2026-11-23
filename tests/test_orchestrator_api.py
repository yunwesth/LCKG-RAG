import json
import threading
import time

from fastapi.testclient import TestClient

from common.settings import OrchestratorSettings
from orchestrator.api import create_app
from orchestrator.state import State, Status
from scripts.serve import check_exposure


class FakePipeline:
    delay = 0.0
    boom = False
    ok = True

    def run(self, msgs):
        time.sleep(self.delay)
        if self.boom:
            raise RuntimeError("secret prompt text must not leak")
        return State(messages=msgs, status=Status.ANSWERED, reply="Learn [2]. " * 10, citations=["P"])

    def ready(self):
        return self.ok


def cfg(**env):
    return OrchestratorSettings(**env)


def make(pipeline=None, **env):
    return TestClient(create_app(pipeline or FakePipeline(), cfg(**env)))


BODY = {"messages": [{"role": "user", "content": "hi"}]}
client = make()


def events(text):
    return [json.loads(l[6:]) for l in text.splitlines() if l.startswith("data: ") and l != "data: [DONE]"]


def test_non_streaming_response_shape():
    r = client.post("/v1/chat/completions", json=BODY).json()
    assert r["object"] == "chat.completion" and r["choices"][0]["message"]["role"] == "assistant"
    assert r["lcrag"] == {"status": "answered", "citations": ["P"]} and r["usage"]["total_tokens"] == 0


def test_streaming_reassembles_and_ends_correctly():
    r = client.post("/v1/chat/completions", json={**BODY, "stream": True})
    evs = events(r.text)
    assert r.text.rstrip().endswith("data: [DONE]")
    assert evs[0]["choices"][0]["delta"] == {"role": "assistant"}
    assert evs[-1]["choices"][0]["finish_reason"] == "stop" and evs[-1]["lcrag"]["status"] == "answered"
    assert "".join(e["choices"][0]["delta"].get("content", "") for e in evs) == "Learn [2]. " * 10
    assert r.headers["cache-control"] == "no-cache" and r.headers["x-accel-buffering"] == "no"


def test_usage_chunk_only_when_requested():
    body = {**BODY, "stream": True, "stream_options": {"include_usage": True}}
    assert "usage" in events(client.post("/v1/chat/completions", json=body).text)[-1]
    assert all("usage" not in e for e in events(client.post("/v1/chat/completions", json={**BODY, "stream": True}).text))


def test_parts_format_and_unicode_round_trip():
    parts = {"messages": [{"role": "user", "content": [{"type": "text", "text": "안녕"}]}]}
    assert client.post("/v1/chat/completions", json=parts).status_code == 200


def test_invalid_requests_use_one_error_shape():
    for body in ({"messages": [{"role": "system", "content": "x"}]}, {"messages": []}, {"messages": [{"role": "user", "content": None}]}):
        r = client.post("/v1/chat/completions", json=body)
        assert r.status_code == 422 and set(r.json()["error"]) == {"message", "type", "code"}
    assert "input" not in client.post("/v1/chat/completions", json={"messages": []}).text


def test_size_limits_return_413():
    small = make(ORCH_MAX_MESSAGES=2, ORCH_MAX_CHARS=100)
    many = {"messages": [{"role": "user", "content": "a"}] * 3}
    assert small.post("/v1/chat/completions", json=many).status_code == 413
    assert small.post("/v1/chat/completions", json={"messages": [{"role": "user", "content": "x" * 101}]}).status_code == 413


def test_pipeline_crash_gives_a_generic_500_without_leaking_text():
    p = FakePipeline()
    p.boom = True
    r = make(p).post("/v1/chat/completions", json=BODY)
    assert r.status_code == 500 and "secret" not in r.text and r.json()["error"]["code"] == "internal_error"
    s = make(p).post("/v1/chat/completions", json={**BODY, "stream": True})
    assert s.status_code == 200 and "secret" not in s.text and s.text.rstrip().endswith("[DONE]")


def test_busy_server_returns_429():
    p = FakePipeline()
    p.delay = 0.6
    c = make(p, ORCH_MAX_CONCURRENT=1, ORCH_QUEUE_WAIT_S=0.1)
    first = threading.Thread(target=lambda: c.post("/v1/chat/completions", json=BODY))
    first.start()
    time.sleep(0.2)
    r = c.post("/v1/chat/completions", json=BODY)
    first.join()
    assert r.status_code == 429 and r.headers["retry-after"]


def test_api_key_is_required_when_set():
    c = make(ORCH_API_KEY="s3cret")
    assert c.post("/v1/chat/completions", json=BODY).status_code == 401
    assert c.post("/v1/chat/completions", json=BODY, headers={"Authorization": "Bearer nope"}).status_code == 401
    assert c.post("/v1/chat/completions", json=BODY, headers={"Authorization": "Bearer s3cret"}).status_code == 200
    assert c.get("/healthz").status_code == 200


def test_keepalive_comments_are_sent_while_the_pipeline_works():
    p = FakePipeline()
    p.delay = 0.4
    r = make(p, ORCH_KEEPALIVE_S=0.05).post("/v1/chat/completions", json={**BODY, "stream": True})
    assert ": keepalive" in r.text


def test_models_health_and_readiness():
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/v1/models").json()["data"][0]["id"] == "lcrag"
    assert client.get("/readyz").status_code == 200
    p = FakePipeline()
    p.ok = False
    assert make(p).get("/readyz").status_code == 503


def test_serve_refuses_to_expose_an_unauthenticated_api():
    assert check_exposure(cfg(ORCH_HOST="0.0.0.0")) is not None
    assert check_exposure(cfg(ORCH_HOST="0.0.0.0", ORCH_API_KEY="k")) is None
    assert check_exposure(cfg()) is None
