"""The Generic Agent: the front door for every question.

handle_question() first decides who answers:
- a follow-up stays with the agent that answered the last turn (sticky routing)
- otherwise the router (agents/router.py) decides: a problem report goes to the
  Debugger Agent (agents/debugger.py), everything else is answered from the docs

Answering from the docs is a LangChain agent with one tool, rag_search:
1. Groq reads the question and decides to call rag_search with a search query.
2. The tool runs the hybrid search and returns the top chunks.
3. Groq reads the chunks and writes the answer, or searches again if needed.
"""

from __future__ import annotations

import re

from langchain.agents import create_agent
from langchain.agents.middleware import ToolCallLimitMiddleware
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.graph.state import CompiledStateGraph

from app.agents.debugger import DebuggerAgent
from app.agents.router import DEBUGGER, route
from app.agents.text import tidy

# Every search adds about 1,000 tokens to the next Groq request. Without a limit
# the agent kept searching (8 times for one question) and went over the free
# tier's 8,000 tokens per minute.
MAX_SEARCHES = 2

NOT_COVERED = "The documentation does not cover this."

# The users are customers who are not very technical, so answers lead with the
# main idea in plain words and leave the details for a follow-up question.
SYSTEM_PROMPT = f"""You are the Generic Agent of NetAI Copilot Lite. You answer questions \
about the Maveric platform using its documentation. The user is not technical.

Searching:
- Always call rag_search before answering. Never answer from your own memory.
- Search once. Search a second time only if the first results are about a \
different topic. Then answer with what you have.

Facts:
- Answer only with facts found in the search results. Do not add anything the \
results do not say, and do not guess. If the results do not contain the answer, \
reply with exactly this sentence and nothing else: {NOT_COVERED}
- Write abbreviations (like MCP, RCA, BDT) exactly as the results write them. \
Never put a meaning in brackets after an abbreviation, unless those exact words \
appear next to it in the results. Write "the Copilot MCP layer", not \
"the Copilot MCP (...) layer".
- The results are only the 4 best-matching parts of the docs, not whole files. \
If the question asks for a count or a full list, give only what the results show \
and say the list may be incomplete.

How to write the answer:
- Start with 1 or 2 plain sentences that answer the question directly.
- Then, only if useful, at most 4 bullet points with the key ideas. Each bullet \
is one short sentence of at most 15 words.
- Unless the user asks for technical details, never include: URLs or API paths, \
table or field names, HTTP status codes, port numbers, standard or spec numbers, \
parameter names, code, or file names.
- Use simple everyday words to say what the docs say. Simplify; do not add new facts.
- Plain text only: no ** or backticks, no headings. Start bullet points with "- ".
- End with one short line offering more detail, like: "Want the technical details?"
- Do not write a Sources line or citation marks like 【1】. Sources are added for you.

The shape of a good answer (the words in <> are placeholders, not facts):
<Name> is the part of Maveric that <what it does, in plain words>.

- <key idea, one short sentence>
- <key idea, one short sentence>
- <key idea, one short sentence>

Want the technical details?

If the user asks for technical details, give them, still in plain text.

Before you reply, check every abbreviation in your answer. If you wrote a meaning \
for it that is not in the search results, remove that meaning."""

# Finds the file names in rag_search's results, for the Sources line
SOURCE_IN_TOOL_RESULT = re.compile(r"^\[\d+\] source: (.+)$", re.MULTILINE)


def build_generic_agent(llm: BaseChatModel, rag_search: BaseTool) -> CompiledStateGraph:
    """Create the agent with Groq as its model and rag_search as its only tool."""
    # A hard stop on top of the prompt rule: after MAX_SEARCHES, any further
    # search is blocked and the agent is told to answer with what it has.
    search_limit = ToolCallLimitMiddleware(tool_name=rag_search.name, run_limit=MAX_SEARCHES)
    return create_agent(
        model=llm,
        tools=[rag_search],
        system_prompt=SYSTEM_PROMPT,
        middleware=[search_limit],
    )


def searched_files(messages: list[BaseMessage]) -> list[str]:
    """The files rag_search returned during this question, in order, without repeats."""
    files: list[str] = []
    for message in messages:
        if isinstance(message, ToolMessage):
            files += SOURCE_IN_TOOL_RESULT.findall(str(message.content))
    return list(dict.fromkeys(files))


def clean_answer(answer: str, files: list[str]) -> str:
    """Remove what the model was told not to write, then add the Sources line."""
    text = tidy(answer)
    # No sources when the docs had no answer: the files found did not help
    if not files or NOT_COVERED in text:
        return text
    return f"{text}\n\nSources: {', '.join(files)}"


def ask(agent: CompiledStateGraph, question: str) -> str:
    """Send one question to the agent and return its cleaned-up final answer."""
    result = agent.invoke({"messages": [{"role": "user", "content": question}]})
    messages = result["messages"]
    return clean_answer(str(messages[-1].content), searched_files(messages))


def handle_question(
    agent: CompiledStateGraph,
    debugger: DebuggerAgent,
    llm: BaseChatModel,
    question: str,
    sticky_agent: str | None = None,
) -> tuple[str, str]:
    """Pick the agent, then answer. Returns (answer, which agent answered).

    sticky_agent is the agent that answered the last turn, given only when this
    question is a follow-up. "How do I fix it?" has no debug word, but after a
    Debugger answer it must stay with the Debugger, so the router is skipped.
    """
    chosen = sticky_agent or route(llm, question)
    if chosen == DEBUGGER:
        return debugger.ask(question), chosen
    return ask(agent, question), chosen
