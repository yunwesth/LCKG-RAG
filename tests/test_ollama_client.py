import json

import httpx
import pytest

from common.errors import LLMUnavailable
from common.ollama_client import OllamaClient, model_matches
from common.settings import OllamaSettings


def make(handler, retries=2):
    s = OllamaSettings(
        _env_file=None, OLLAMA_CHAT_MODEL="chat-m", OLLAMA_EMBED_MODEL="embed-m",
        OLLAMA_MAX_RETRIES=retries,
    )
    return OllamaClient(s, transport=httpx.MockTransport(handler), sleep=lambda _s: None)


def test_model_matches_latest_alias():
    assert model_matches("llama", "llama:latest")
    assert not model_matches("llama:8b", "llama:70b")


def test_embed_sends_configured_model_and_returns_vectors():
    seen = {}

    def handler(req):
        seen.update(json.loads(req.content))
        return httpx.Response(200, json={"embeddings": [[0.1, 0.2], [0.3, 0.4]]})

    out = make(handler).embed(["a", "b"])
    assert seen["model"] == "embed-m" and seen["input"] == ["a", "b"]
    assert out == [[0.1, 0.2], [0.3, 0.4]]


def test_embed_count_mismatch_fails():
    c = make(lambda req: httpx.Response(200, json={"embeddings": [[0.1]]}))
    with pytest.raises(LLMUnavailable):
        c.embed(["a", "b"])


def test_chat_passes_json_schema_as_format():
    seen = {}

    def handler(req):
        seen.update(json.loads(req.content))
        return httpx.Response(200, json={"message": {"content": '{"intent":"prereq"}'}})

    schema = {"type": "object", "properties": {"intent": {"type": "string"}}}
    out = make(handler).chat([{"role": "user", "content": "hi"}], schema=schema)
    assert seen["format"] == schema and seen["stream"] is False and seen["model"] == "chat-m"
    assert out == '{"intent":"prereq"}'


def test_retries_5xx_then_succeeds():
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503, text="busy")
        return httpx.Response(200, json={"models": [{"name": "chat-m:latest"}]})

    c = make(handler, retries=3)
    assert c.has_model("chat-m")
    assert calls["n"] == 3


def test_gives_up_after_retries_and_fails_typed():
    c = make(lambda req: httpx.Response(500), retries=1)
    with pytest.raises(LLMUnavailable):
        c.list_models()


def test_4xx_is_not_retried():
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(404, text="model not found")

    with pytest.raises(LLMUnavailable):
        make(handler, retries=3).embed(["x"])
    assert calls["n"] == 1


def test_think_flag_is_sent_only_when_configured():
    seen = []

    def handler(req):
        seen.append(json.loads(req.content))
        return httpx.Response(200, json={"message": {"content": "ok"}})

    make(handler).chat([{"role": "user", "content": "hi"}])
    assert "think" not in seen[-1]
    s = OllamaSettings(_env_file=None, OLLAMA_CHAT_MODEL="c", OLLAMA_EMBED_MODEL="e", OLLAMA_THINK=False)
    OllamaClient(s, transport=httpx.MockTransport(handler)).chat([{"role": "user", "content": "hi"}])
    assert seen[-1]["think"] is False
