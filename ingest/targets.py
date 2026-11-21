"""What gets embedded. One row per node label: add a row to embed another label, nothing else changes.

`primary` is the property that must be non-empty for a node to be embedded. `parts` are the
properties joined (in order) into the text that is embedded. Property names come from this file
only, never from user input, and are validated before they reach Cypher.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class EmbedTarget:
    label: str
    primary: str
    parts: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in (self.label, self.primary, *self.parts):
            if not _IDENT.match(name):
                raise ValueError(f"unsafe identifier in embed target: {name!r}")
        if self.primary not in self.parts:
            raise ValueError(f"{self.label}: primary {self.primary!r} must be one of parts")

    @property
    def index_name(self) -> str:
        return f"emb_{self.label}"


TARGETS: tuple[EmbedTarget, ...] = (
    EmbedTarget("StandardsFrameworkItem", "description", ("statementCode", "description")),
    EmbedTarget("LearningComponent", "description", ("description",)),
    EmbedTarget("Misconception", "description", ("description",)),
    EmbedTarget("Construct", "description", ("description",)),
    EmbedTarget("GuidanceFrameworkItem", "description", ("statementCode", "description")),
    EmbedTarget("StandardsFramework", "name", ("name", "description")),
    EmbedTarget("GuidanceFramework", "name", ("name", "description")),
    EmbedTarget("Course", "name", ("name", "description")),
    EmbedTarget("LessonGrouping", "name", ("name",)),
    EmbedTarget("Lesson", "name", ("name",)),
    EmbedTarget("Activity", "name", ("name",)),
    EmbedTarget("Assessment", "name", ("name",)),
)
# MasteryThreshold has no text, so it is not a target.


def targets_by_label(labels: list[str] | None) -> tuple[EmbedTarget, ...]:
    if not labels:
        return TARGETS
    known = {t.label: t for t in TARGETS}
    unknown = [lab for lab in labels if lab not in known]
    if unknown:
        raise ValueError(f"unknown embed label(s): {unknown}; known: {sorted(known)}")
    return tuple(known[lab] for lab in labels)


def normalize(value: Any) -> str:
    """Collapse whitespace; join list values; turn None into ''."""
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        value = " ".join(str(v) for v in value)
    return " ".join(str(value).split())


def build_text(target: EmbedTarget, props: Mapping[str, Any], max_chars: int) -> str | None:
    """Text to embed, or None when the primary property is empty. Deterministic, so re-runs agree."""
    if not normalize(props.get(target.primary)):
        return None
    pieces = [normalize(props.get(p)) for p in target.parts]
    text = ". ".join(p for p in pieces if p)
    return text[:max_chars]
