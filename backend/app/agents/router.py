"""The router: decides which agent answers a question.

Two checks, the cheap one first:
1. Keyword check (free, no Groq call): does the question contain a debug word
   like "error", "failure", "log" or "crash"? If not, it goes to the Generic Agent.
2. Groq yes/no check (only on a keyword hit): is the user reporting a problem?
   "What does the error handling module do?" has the word "error" but is a
   knowledge question, so Groq says "no" and it stays with the Generic Agent.

If Groq fails or gives an unclear reply, the question goes to the Generic Agent.
"""

from __future__ import annotations

import logging
import re

from langchain_core.language_models import BaseChatModel

logger = logging.getLogger(__name__)

GENERIC = "generic"
DEBUGGER = "debugger"

# Word starts, so "errors", "failed", "logs" and "crashed" also count.
# Some normal words also match ("login", "logic"); the Groq check catches those.
DEBUG_KEYWORDS = re.compile(r"\b(error|fail|log|crash)", re.IGNORECASE)

ROUTER_PROMPT = """You decide if a user is reporting a problem with the Maveric platform.

Answer "yes" if the user says something failed, crashed, errored or is not working, \
or asks to check error logs or find out why something broke.
Answer "no" if the user is asking how something works, what a word means, or any \
other knowledge question, even if it mentions errors or logs.

Reply with one word only: yes or no."""


def has_debug_keyword(question: str) -> bool:
    return DEBUG_KEYWORDS.search(question) is not None


def is_problem_report(llm: BaseChatModel, question: str) -> bool:
    """Ask Groq the yes/no question. Any failure or unclear reply counts as "no"."""
    try:
        reply = llm.invoke(
            [
                {"role": "system", "content": ROUTER_PROMPT},
                {"role": "user", "content": question},
            ]
        )
    except Exception:
        logger.warning("Router check failed; sending the question to the Generic Agent", exc_info=True)
        return False
    words = str(reply.content).strip().lower().split()
    answer = words[0].strip('."!') if words else ""
    if answer not in ("yes", "no"):
        logger.warning("Router got an unclear reply %r; using the Generic Agent", reply.content)
    return answer == "yes"


def route(llm: BaseChatModel, question: str) -> str:
    """Return GENERIC or DEBUGGER for this question."""
    if not has_debug_keyword(question):
        return GENERIC
    return DEBUGGER if is_problem_report(llm, question) else GENERIC
