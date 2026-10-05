"""Try the search from the terminal.

Run from the backend/ folder:
    python -m scripts.search "What is EPIC-8?"            # hybrid search
    python -m scripts.search "What is EPIC-8?" --compare  # also show meaning search alone
    python -m scripts.search                              # ask questions one by one
"""

from __future__ import annotations

import argparse
import logging
import sys

from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

from app.core.config import load_settings
from app.rag.embeddings import load_embeddings
from app.rag.hybrid_search import EmptyStoreError, build_hybrid_retriever, search
from app.rag.vector_store import open_vector_store

SNIPPET_LENGTH = 150


def show(title: str, chunks: list[Document]) -> None:
    """Print each chunk's breadcrumb and the start of its text."""
    print(f"\n{title}")
    for number, chunk in enumerate(chunks, 1):
        breadcrumb, _, body = chunk.page_content.partition("\n")
        snippet = " ".join(body.split())[:SNIPPET_LENGTH]
        print(f"  {number}. {breadcrumb}")
        print(f"     {snippet}...")


def ask(question: str, hybrid: BaseRetriever, meaning: BaseRetriever | None, top_k: int) -> None:
    print(f"\n=== {question}")
    if meaning is not None:
        show("Meaning search only:", meaning.invoke(question)[:top_k])
    show("Hybrid search (meaning + words, merged with RRF):", search(hybrid, question, top_k))


def main() -> None:
    parser = argparse.ArgumentParser(description="Search the knowledge base.")
    parser.add_argument("question", nargs="?", help="leave out to ask questions one by one")
    parser.add_argument("--compare", action="store_true", help="also show meaning search alone")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    settings = load_settings()
    store = open_vector_store(settings, load_embeddings(settings))
    try:
        hybrid = build_hybrid_retriever(store, settings)
    except EmptyStoreError as error:
        print(f"ERROR {error}")
        sys.exit(1)
    meaning = store.as_retriever(search_kwargs={"k": settings.search_top_k}) if args.compare else None

    if args.question:
        ask(args.question, hybrid, meaning, settings.search_top_k)
        return
    while question := input("\nQuestion (press Enter to quit): ").strip():
        ask(question, hybrid, meaning, settings.search_top_k)


if __name__ == "__main__":
    main()
