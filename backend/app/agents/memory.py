"""Chat memory: the last 3 question/answer turns, plus question rewriting.

Memory lives in a Python list only. It is gone when the chat ends, and nothing
is written to disk, so the "no persistence beyond the vector store" rule holds.

Why rewrite? A follow-up like "how many stories does it have?" means nothing to
the search: "it" is not in any doc. Groq rewrites it into a full question,
"How many stories does EPIC-8 have?", using the last turns. Only the rewritten
question goes to the agent, so the agent needs no history and each request stays small.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from langchain_core.language_models import BaseChatModel

logger = logging.getLogger(__name__)

MAX_TURNS = 2
# Answers can be long. The rewriter only needs the topic, so it gets the start of each one.
ANSWER_PREVIEW_CHARS = 400

# The examples are there because Groq kept tying new questions to the last topic:
# "The worker crashed last night" became "...the worker for the Copilot MCP layer...".
REWRITE_PROMPT = """You help a search tool understand follow-up questions. The search \
tool cannot see the chat, so a message like "how many does it have?" means nothing \
to it. Your job is to fill in the missing name, and only that.

When to rewrite: only when the message cannot be understood on its own, because it \
uses a word like "it", "that", "they", "this" or "the second one", or leaves out \
what it is about. Then swap only that word for the name it refers to. Add nothing \
else from the chat.

When to leave it alone: if the message already names what it is about, return it \
exactly as written, word for word, even if it could be related to the chat. A message \
that reports a problem (something failed, crashed or broke) is a new topic: return \
it unchanged.

Examples, after a chat about EPIC-8:
- "How many stories does it have?" -> "How many stories does EPIC-8 have?"
- "What does S1 fix?" -> "What does S1 of EPIC-8 fix?"
- "How does the BDT Engine work?" -> "How does the BDT Engine work?"
- "The worker crashed last night" -> "The worker crashed last night"

Do not answer the message. Reply with the rewritten message only."""


@dataclass(frozen=True)
class Turn:
    question: str
    answer: str
    agent: str  # which agent answered: used later for sticky routing (step 7)


class ChatMemory:
    """Keeps only the last MAX_TURNS turns; older ones drop off."""

    def __init__(self, max_turns: int = MAX_TURNS) -> None:
        self._max_turns = max_turns
        self._turns: list[Turn] = []

    @property
    def turns(self) -> tuple[Turn, ...]:
        return tuple(self._turns)

    @property
    def last_agent(self) -> str | None:
        return self._turns[-1].agent if self._turns else None

    def add(self, question: str, answer: str, agent: str) -> None:
        self._turns = [*self._turns, Turn(question, answer, agent)][-self._max_turns :]

    def clear(self) -> None:
        self._turns = []


def format_history(turns: tuple[Turn, ...]) -> str:
    return "\n\n".join(
        f"User: {turn.question}\nAssistant: {turn.answer[:ANSWER_PREVIEW_CHARS]}" for turn in turns
    )


def rewrite_question(llm: BaseChatModel, question: str, turns: tuple[Turn, ...]) -> str:
    """Turn a follow-up into a standalone question.

    The first question has no history, so it is used as it is (no Groq call).
    If the rewrite fails, the original question is used.
    """
    if not turns:
        return question
    try:
        reply = llm.invoke(
            [
                {"role": "system", "content": REWRITE_PROMPT},
                {
                    "role": "user",
                    "content": f"Chat history:\n{format_history(turns)}\n\nFollow-up question: {question}",
                },
            ]
        )
    except Exception:
        logger.warning("Question rewrite failed; using the original question", exc_info=True)
        return question
    rewritten = str(reply.content).strip().strip('"')
    return rewritten or question
