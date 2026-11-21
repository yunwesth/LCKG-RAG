"""Typed errors shared across modules so callers can fail closed without catching library exceptions."""


class RagError(Exception):
    """Base class for all project errors."""


class KGUnavailable(RagError):
    """Neo4j could not be reached or the query timed out."""


class UnsafeQuery(RagError):
    """A Cypher query contained a write clause or was not parameterized safely."""


class LLMUnavailable(RagError):
    """Ollama could not be reached after retries."""


class ConfigError(RagError):
    """Required configuration is missing or inconsistent."""
