"""Single source of configuration. All values come from environment variables or `.env`.

Each module receives only the slice it needs (Neo4jSettings, OllamaSettings, ...), so modules
do not depend on each other's config. Models are config, never hardcoded (masterplan rule 5).
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

_CONFIG = SettingsConfigDict(env_file=".env", extra="ignore", frozen=True)


class Neo4jSettings(BaseSettings):
    model_config = _CONFIG

    uri: str = Field("bolt://localhost:7687", validation_alias="NEO4J_URI")
    database: str = Field("neo4j", validation_alias="NEO4J_DATABASE")
    # App credentials (orchestrator and tools). Read-only by construction in the client.
    user: str = Field("neo4j", validation_alias="NEO4J_USER")
    password: SecretStr = Field(SecretStr(""), validation_alias="NEO4J_PASSWORD")
    # Admin credentials: only ingest and bootstrap scripts may use these.
    admin_user: str = Field("neo4j", validation_alias="NEO4J_ADMIN_USER")
    admin_password: SecretStr = Field(SecretStr(""), validation_alias="NEO4J_ADMIN_PASSWORD")
    query_timeout_s: float = Field(15.0, gt=0, validation_alias="NEO4J_QUERY_TIMEOUT_S")
    result_limit: int = Field(500, gt=0, validation_alias="NEO4J_RESULT_LIMIT")


class OllamaSettings(BaseSettings):
    model_config = _CONFIG

    base_url: str = Field("http://localhost:11434", validation_alias="OLLAMA_BASE_URL")
    chat_model: str = Field(..., validation_alias="OLLAMA_CHAT_MODEL")
    embed_model: str = Field(..., validation_alias="OLLAMA_EMBED_MODEL")
    timeout_s: float = Field(60.0, gt=0, validation_alias="OLLAMA_TIMEOUT_S")
    max_retries: int = Field(3, ge=0, validation_alias="OLLAMA_MAX_RETRIES")


class IngestSettings(BaseSettings):
    model_config = _CONFIG

    batch_size: int = Field(64, ge=1, le=512, validation_alias="INGEST_BATCH_SIZE")
    max_chars: int = Field(2000, ge=50, validation_alias="INGEST_MAX_CHARS")


class OrchestratorSettings(BaseSettings):
    model_config = _CONFIG

    max_tool_steps: int = Field(4, ge=1, validation_alias="MAX_TOOL_STEPS")
    total_timeout_s: float = Field(120.0, gt=0, validation_alias="TOTAL_TIMEOUT_S")
    # HTTP API (scripts.serve). Loopback by default; a non-loopback host requires ORCH_API_KEY.
    host: str = Field("127.0.0.1", validation_alias="ORCH_HOST")
    port: int = Field(8000, ge=1, le=65535, validation_alias="ORCH_PORT")
    api_key: SecretStr = Field(SecretStr(""), validation_alias="ORCH_API_KEY")
    max_messages: int = Field(50, ge=1, validation_alias="ORCH_MAX_MESSAGES")
    max_chars: int = Field(20000, ge=100, validation_alias="ORCH_MAX_CHARS")
    max_concurrent: int = Field(2, ge=1, validation_alias="ORCH_MAX_CONCURRENT")
    queue_wait_s: float = Field(30.0, gt=0, validation_alias="ORCH_QUEUE_WAIT_S")
    keepalive_s: float = Field(10.0, gt=0, validation_alias="ORCH_KEEPALIVE_S")


@lru_cache
def neo4j_settings() -> Neo4jSettings:
    return Neo4jSettings()


@lru_cache
def ollama_settings() -> OllamaSettings:
    return OllamaSettings()


@lru_cache
def ingest_settings() -> IngestSettings:
    return IngestSettings()


@lru_cache
def orchestrator_settings() -> OrchestratorSettings:
    return OrchestratorSettings()
