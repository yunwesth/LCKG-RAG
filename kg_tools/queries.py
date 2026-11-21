"""Loads the parameterized Cypher files in `kg_tools/cypher/`. Tools pass the text to any GraphReader."""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

CYPHER_DIR = Path(__file__).parent / "cypher"
_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


@lru_cache
def load_query(name: str) -> str:
    """Return the text of `cypher/<name>.cypher`. Names are plain snake_case, so no path tricks."""
    if not _NAME.match(name):
        raise ValueError(f"invalid query name: {name!r}")
    return (CYPHER_DIR / f"{name}.cypher").read_text()
