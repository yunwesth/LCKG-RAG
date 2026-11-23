"""Pipeline state. Each node reads it and returns only the fields it changes."""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from kg_tools.tools import NodeSummary


class Intent(str, Enum):
    PREREQUISITES = "prerequisites"
    LOOKUP = "lookup"
    UNSUPPORTED = "unsupported"


class Status(str, Enum):
    ANSWERED = "answered"
    CLARIFY = "clarify"          # we need the user to say which jurisdiction
    NOT_FOUND = "not_found"
    UNSUPPORTED = "unsupported"
    REFUSED = "refused"          # fail-closed: the answer could not be verified


class Understanding(BaseModel):
    intent: Intent = Intent.UNSUPPORTED
    concept: str | None = None       # free-text topic, e.g. "multiplying fractions"
    code: str | None = None          # statement code, e.g. "8.EE.C.8"
    jurisdiction: str | None = None  # only if the user said it, e.g. "Texas"


class Evidence(BaseModel):
    ref: int                         # the [n] the answer may cite
    node: NodeSummary
    distance: int | None = None      # hops from the target (None for the target itself)


class State(BaseModel):
    messages: list[dict[str, str]]
    understanding: Understanding | None = None
    jurisdiction: str | None = None  # validated against the KG
    target: NodeSummary | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    truncated: bool = False
    draft: str | None = None
    status: Status | None = None
    reply: str | None = None
    citations: list[str] = Field(default_factory=list)  # node ids cited in the verified reply
