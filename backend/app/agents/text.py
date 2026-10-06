"""Clean-up for agent answers, shared by the Generic Agent and the Debugger.

Done in code, because the model sometimes breaks the prompt's format rules.
"""

from __future__ import annotations

import re

CITATION_MARKS = re.compile(r"【[^】]*】")
MODEL_SOURCES_LINE = re.compile(r"^\s*sources?:.*$", re.IGNORECASE | re.MULTILINE)
ODD_HYPHENS = str.maketrans({"‑": "-", "‐": "-", "–": "-", "—": "-"})


def tidy(answer: str) -> str:
    """Remove citation marks, Markdown bold, backticks and any Sources line the
    model wrote, and turn odd hyphens into normal ones."""
    text = CITATION_MARKS.sub("", answer).translate(ODD_HYPHENS)
    return MODEL_SOURCES_LINE.sub("", text).replace("**", "").replace("`", "").strip()
