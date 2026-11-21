import pytest
from pydantic import ValidationError

from common.settings import Neo4jSettings, OllamaSettings


def test_neo4j_defaults_and_env(monkeypatch):
    monkeypatch.setenv("NEO4J_PASSWORD", "s3cret-pw")
    monkeypatch.setenv("NEO4J_RESULT_LIMIT", "10")
    s = Neo4jSettings(_env_file=None)
    assert s.uri == "bolt://localhost:7687"
    assert s.result_limit == 10
    assert "s3cret-pw" not in repr(s)  # secrets never leak into logs
    assert s.password.get_secret_value() == "s3cret-pw"


def test_models_come_from_config_not_code(monkeypatch):
    monkeypatch.delenv("OLLAMA_CHAT_MODEL", raising=False)
    monkeypatch.delenv("OLLAMA_EMBED_MODEL", raising=False)
    with pytest.raises(ValidationError):
        OllamaSettings(_env_file=None)  # no hardcoded model fallback (masterplan rule 5)
    monkeypatch.setenv("OLLAMA_CHAT_MODEL", "chat-x")
    monkeypatch.setenv("OLLAMA_EMBED_MODEL", "embed-y")
    s = OllamaSettings(_env_file=None)
    assert (s.chat_model, s.embed_model) == ("chat-x", "embed-y")
