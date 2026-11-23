"""Builds the real pipeline from configuration. The only place that names concrete clients."""
from __future__ import annotations

from common.ollama_client import OllamaClient
from common.settings import neo4j_settings, ollama_settings, orchestrator_settings
from kg_tools.neo4j_client import Neo4jReader
from kg_tools.tools import KGTools
from orchestrator.graph import Pipeline


def build_pipeline() -> Pipeline:
    llm = OllamaClient(ollama_settings())
    reader = Neo4jReader(neo4j_settings())
    return Pipeline(llm, KGTools(reader, llm), timeout_s=orchestrator_settings().total_timeout_s,
                    closers=(reader.close, llm.close), checks=(reader.ping,))
