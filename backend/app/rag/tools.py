"""The rag_search tool: the Generic Agent's only way to read the docs.

The agent (Groq) decides when to call it and what to search for. The tool runs
the hybrid search and hands back the best chunks as plain text, each with a
number and its source file, so the agent can say where an answer came from.
"""

from __future__ import annotations

import logging

from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langchain_core.tools import BaseTool, tool

from app.rag.hybrid_search import search

logger = logging.getLogger(__name__)

NO_RESULTS = "No matching documents were found. The knowledge base does not cover this."
SEARCH_FAILED = "The document search failed. Tell the user the docs could not be searched right now."


def format_chunks(chunks: list[Document]) -> str:
    """Turn chunks into one text block for the agent.

    Each chunk's text already starts with its breadcrumb line
    ([file > H1 > H2]), so the agent sees where every part comes from.
    """
    return "\n\n".join(
        f"[{number}] source: {chunk.metadata.get('source', 'unknown')}\n{chunk.page_content}"
        for number, chunk in enumerate(chunks, 1)
    )


def make_rag_search_tool(retriever: BaseRetriever, top_k: int) -> BaseTool:
    """Build the tool around a retriever that was set up once at startup."""

    @tool
    def rag_search(query: str) -> str:
        """Search the Maveric platform documentation.

        Use this for any question about the Maveric platform: its features,
        architecture, configuration, setup, epics, user stories and terms.
        Pass a short, specific search query, not a whole conversation.
        """
        try:
            chunks = search(retriever, query, top_k)
        except Exception:
            # Fail gracefully at runtime: the agent gets a message, not a crash
            logger.exception("rag_search failed for query %r", query)
            return SEARCH_FAILED
        if not chunks:
            return NO_RESULTS
        return format_chunks(chunks)

    return rag_search
