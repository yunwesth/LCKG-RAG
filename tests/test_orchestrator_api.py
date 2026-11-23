import json

from fastapi.testclient import TestClient

from orchestrator.api import create_app
from orchestrator.state import State, Status


class FakePipeline:
    def run(self, msgs):
        return State(messages=msgs, status=Status.ANSWERED, reply="Learn [2]. " * 10, citations=["P"])


client = TestClient(create_app(FakePipeline()))
BODY = {"messages": [{"role": "user", "content": "hi"}]}


def test_non_streaming_response_shape():
    r = client.post("/v1/chat/completions", json=BODY).json()
    assert r["object"] == "chat.completion" and r["choices"][0]["message"]["role"] == "assistant"
    assert r["lcrag"] == {"status": "answered", "citations": ["P"]}


def test_streaming_reassembles_to_the_reply_and_ends_with_done():
    r = client.post("/v1/chat/completions", json={**BODY, "stream": True})
    lines = [l[6:] for l in r.text.splitlines() if l.startswith("data: ")]
    assert lines[-1] == "[DONE]"
    text = "".join(json.loads(l)["choices"][0]["delta"].get("content", "") for l in lines[:-1])
    assert text == "Learn [2]. " * 10


def test_parts_format_and_validation():
    parts = {"messages": [{"role": "user", "content": [{"type": "text", "text": "hi"}]}]}
    assert client.post("/v1/chat/completions", json=parts).status_code == 200
    assert client.post("/v1/chat/completions", json={"messages": [{"role": "system", "content": "x"}]}).status_code == 400
    assert client.post("/v1/chat/completions", json={"messages": []}).status_code == 422


def test_models_and_health():
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/v1/models").json()["data"][0]["id"] == "lcrag"
