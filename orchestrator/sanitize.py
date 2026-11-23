"""Untrusted text (user turns, KG descriptions) is placed between tags in prompts. Defanging angle brackets
stops that text from closing the tag early and posing as instructions."""
from __future__ import annotations


def defang(text: str) -> str:
    return text.replace("<", "‹").replace(">", "›")
