"""The Generic Agent: answers questions about the Maveric platform from the docs.

It is a LangChain agent with one tool, rag_search. The agent loop works like this:
1. Groq reads the question and decides to call rag_search with a search query.
2. The tool runs the hybrid search and returns the top chunks.
3. Groq reads the chunks and writes the answer, or searches again if needed.
"""

from __future__ import annotations

from langchain.agents import create_agent
from langchain.agents.middleware import ToolCallLimitMiddleware
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.graph.state import CompiledStateGraph

# Every search adds about 1,000 tokens to the next Groq request. Without a limit
# the agent kept searching (8 times for one question) and went over the free
# tier's 8,000 tokens per minute.
MAX_SEARCHES = 2

SYSTEM_PROMPT = """You are the Generic Agent of NetAI Copilot Lite. You answer questions \
about the Maveric platform using its documentation.

Rules:
- Always call rag_search before answering. Never answer from your own memory.
- Search once. Search a second time only if the first results are about a \
different topic. Then answer with what you have.
- Answer only with facts found in the search results. If the results do not \
contain the answer, say that the documentation does not cover it. Do not guess.
- Do not add anything the results do not say. Never spell out what an \
abbreviation (like MCP or RCA) stands for unless the results spell it out.
- The results are only the 4 best-matching parts of the docs, not whole files. \
If the question asks for a count or a full list, give only what the results show \
and say the list may be incomplete.
- Do not add citation marks like 【1】 inside the text. Name the files only in the \
Sources line.
- At the end, list the source files you used, like: Sources: folder/file.md
- Keep answers clear and short. Use bullet points for lists of steps or items."""


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


def ask(agent: CompiledStateGraph, question: str) -> str:
    """Send one question to the agent and return its final answer."""
    result = agent.invoke({"messages": [{"role": "user", "content": question}]})
    return result["messages"][-1].content
