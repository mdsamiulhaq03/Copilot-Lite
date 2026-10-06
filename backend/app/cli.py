"""Terminal chat with the copilot.

Run from the backend/ folder:
    python -m app.cli

Each question goes through:
1. rewrite: a follow-up becomes a standalone question (uses the last 3 turns)
2. Generic Agent: picks the agent (a follow-up stays with the last one), then
   answers from the docs, or hands a problem report to the Debugger Agent
3. memory: the turn is saved, and the oldest drops off after 3

The Debugger needs the MCP server (and the Dummy API behind it) running. If they
are down, the chat still works for docs questions.

Type "clear" to forget the chat so far, or "exit" to quit.
"""

from __future__ import annotations

import logging
import sys

from langchain_core.language_models import BaseChatModel
from langgraph.graph.state import CompiledStateGraph

from app.agents.debugger import DebuggerAgent
from app.agents.generic import build_generic_agent, handle_question
from app.agents.memory import ChatMemory, rewrite_question
from app.agents.router import DEBUGGER, GENERIC
from app.core.config import ConfigError, load_settings
from app.core.llm import friendly_error, load_llm
from app.rag.embeddings import load_embeddings
from app.rag.hybrid_search import EmptyStoreError, build_hybrid_retriever
from app.rag.tools import make_rag_search_tool
from app.rag.vector_store import open_vector_store

EXIT_WORDS = {"exit", "quit"}


def start() -> tuple[CompiledStateGraph, DebuggerAgent, BaseChatModel]:
    """Set everything up once. Stops with a clear message if anything is missing."""
    settings = load_settings()
    try:
        llm = load_llm(settings)
        store = open_vector_store(settings, load_embeddings(settings))
        retriever = build_hybrid_retriever(store, settings)
    except (ConfigError, EmptyStoreError, RuntimeError) as error:
        print(f"Cannot start: {error}")
        sys.exit(1)
    agent = build_generic_agent(llm, make_rag_search_tool(retriever, settings.search_top_k))
    # Does not connect yet: it connects to the MCP server on the first debug question
    debugger = DebuggerAgent(llm, settings.mcp_server_url, settings.default_tenant_id)
    return agent, debugger, llm


def answer_one(
    question: str,
    agent: CompiledStateGraph,
    debugger: DebuggerAgent,
    llm: BaseChatModel,
    memory: ChatMemory,
) -> tuple[str, str | None]:
    """Answer one question. Returns (answer, which agent answered, or None on an error)."""
    standalone = rewrite_question(llm, question, memory.turns)
    # The rewriter only changes a question that leans on the chat so far, so a
    # changed question is a follow-up: it stays with the agent that answered last.
    is_follow_up = standalone != question
    if is_follow_up:
        print(f"(understood as: {standalone})")
    try:
        answer, chosen = handle_question(
            agent, debugger, llm, standalone, memory.last_agent if is_follow_up else None
        )
    except Exception as error:
        # Reached only after the Groq client's own retries (see core/llm.py)
        return friendly_error(error), None
    # Save the standalone question: it gives the next rewrite clearer context.
    # Which agent answered is saved too, for sticky routing.
    memory.add(standalone, answer, chosen)
    return answer, chosen


def speaker(chosen: str | None) -> str:
    """The name shown before an answer, so it is clear which agent answered."""
    if chosen == DEBUGGER:
        return "Copilot (Debugger Agent)"
    if chosen == GENERIC:
        return "Copilot (Generic Agent)"
    return "Copilot"  # an error message: no agent answered


def chat() -> None:
    # Warnings show as one short line in brackets, apart from the chat text
    logging.basicConfig(level=logging.WARNING, format="[%(levelname)s] %(message)s")
    print("Loading the docs and the search index...")
    agent, debugger, llm = start()
    memory = ChatMemory()
    print(
        "NetAI Copilot Lite. Ask about the Maveric platform, or describe a problem "
        'and I will check the error logs. Type "clear" or "exit".'
    )

    while True:
        try:
            question = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not question:
            continue
        if question.lower() in EXIT_WORDS:
            break
        if question.lower() == "clear":
            memory.clear()
            print("Chat history cleared.")
            continue
        answer, chosen = answer_one(question, agent, debugger, llm, memory)
        print(f"\n{speaker(chosen)}: {answer}")
    print("\nBye.")


if __name__ == "__main__":
    chat()
