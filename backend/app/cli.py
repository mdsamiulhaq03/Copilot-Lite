"""Terminal chat with the copilot.

Run from the backend/ folder:
    python -m app.cli

Each question goes through:
1. rewrite: a follow-up becomes a standalone question (uses the last 3 turns)
2. Generic Agent: routes it, then answers from the docs (debug questions get a
   "Debugger not ready" reply until step 7)
3. memory: the turn is saved, and the oldest drops off after 3

Type "clear" to forget the chat so far, or "exit" to quit.
"""

from __future__ import annotations

import logging
import sys

from langchain_core.language_models import BaseChatModel
from langgraph.graph.state import CompiledStateGraph

from app.agents.generic import build_generic_agent, handle_question
from app.agents.memory import ChatMemory, rewrite_question
from app.core.config import ConfigError, load_settings
from app.core.llm import friendly_error, load_llm
from app.rag.embeddings import load_embeddings
from app.rag.hybrid_search import EmptyStoreError, build_hybrid_retriever
from app.rag.tools import make_rag_search_tool
from app.rag.vector_store import open_vector_store

EXIT_WORDS = {"exit", "quit"}


def start() -> tuple[CompiledStateGraph, BaseChatModel]:
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
    return agent, llm


def answer_one(
    question: str, agent: CompiledStateGraph, llm: BaseChatModel, memory: ChatMemory
) -> str:
    standalone = rewrite_question(llm, question, memory.turns)
    if standalone != question:
        print(f"(searching for: {standalone})")
    try:
        answer, chosen = handle_question(agent, llm, standalone)
    except Exception as error:
        # Reached only after the Groq client's own retries (see core/llm.py)
        return friendly_error(error)
    # Save the standalone question: it gives the next rewrite clearer context.
    # Which agent answered is saved too, for sticky routing in step 7.
    memory.add(standalone, answer, chosen)
    return answer


def chat() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    print("Loading the docs and the search index...")
    agent, llm = start()
    memory = ChatMemory()
    print('NetAI Copilot Lite. Ask about the Maveric platform. Type "clear" or "exit".')

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
        print(f"\nCopilot: {answer_one(question, agent, llm, memory)}")
    print("\nBye.")


if __name__ == "__main__":
    chat()
