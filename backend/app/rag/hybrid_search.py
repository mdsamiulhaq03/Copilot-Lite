"""Hybrid search: meaning search + word search, merged with RRF.

- Meaning search: ChromaDB compares the question's embedding with the chunks'.
  Good at "same idea, different words".
- Word search: BM25 scores chunks by matching words. Good at exact names like
  EPIC-8, TR-069 or nybsys, which meaning search blurs together.
- RRF (Reciprocal Rank Fusion): each chunk gets 1 / (60 + rank) from each list,
  the two are added, and the highest total wins. It uses rank, not score,
  because the two searches score on completely different scales.

The BM25 index lives only in memory. It is built from the chunks already in
ChromaDB, so ChromaDB stays the only stored data.
"""

from __future__ import annotations

import logging
import re

from langchain_chroma import Chroma
from langchain_classic.retrievers import EnsembleRetriever
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

from app.core.config import Settings

logger = logging.getLogger(__name__)

_WORD = re.compile(r"\w+")

# Reciprocal Rank Fusion: each chunk gets 1 / (RRF_C + rank) from each search.
# 60 is the standard value. Equal weights: meaning search and word search count the same.
RRF_C = 60
RRF_WEIGHTS = [0.5, 0.5]


class EmptyStoreError(Exception):
    """ChromaDB has no chunks, so there is nothing to search."""


def tokenize(text: str) -> list[str]:
    """Split text into lowercase words for BM25, plus pairs for codes.

    "What is EPIC-8?" -> ["what", "is", "epic", "8", "epic_8"]

    - BM25's default only splits at spaces, which would keep "EPIC-8?" as one
      word that never matches "EPIC-8" in the docs.
    - "epic" and "8" alone are very common (1,328 and 366 of 2,763 chunks), so
      they count for little. The pair "epic_8" is rare, so it counts a lot.
      Pairs are only made next to a number, the shape of codes like EPIC-8 or
      TR-069; pairs of normal words ("what_is") only added noise.
    """
    words = _WORD.findall(text.lower())
    code_pairs = [f"{a}_{b}" for a, b in zip(words, words[1:]) if a.isdigit() or b.isdigit()]
    return words + code_pairs


def load_all_chunks(store: Chroma) -> list[Document]:
    """Read every chunk's text and metadata back from ChromaDB."""
    data = store.get(include=["documents", "metadatas"])
    return [
        Document(page_content=text, metadata=metadata or {})
        for text, metadata in zip(data["documents"], data["metadatas"], strict=True)
    ]


def build_hybrid_retriever(store: Chroma, settings: Settings) -> BaseRetriever:
    """Combine meaning search and word search into one retriever.

    Falls back to meaning search only if the BM25 index cannot be built.
    """
    chunks = load_all_chunks(store)
    if not chunks:
        raise EmptyStoreError(
            "ChromaDB has no chunks. Run ingestion first: "
            "docker compose -f docker-compose.ingest.yml run --rm --build ingest"
        )

    meaning = store.as_retriever(search_kwargs={"k": settings.search_candidates})
    try:
        words = BM25Retriever.from_documents(
            chunks, k=settings.search_candidates, preprocess_func=tokenize
        )
    except Exception:
        logger.warning("Could not build the BM25 index; using meaning search only", exc_info=True)
        return meaning

    logger.info("Hybrid search ready: %d chunks indexed for word search", len(chunks))
    return EnsembleRetriever(retrievers=[meaning, words], weights=RRF_WEIGHTS, c=RRF_C)


def search(retriever: BaseRetriever, question: str, top_k: int) -> list[Document]:
    """Return the best top_k chunks for a question."""
    return retriever.invoke(question)[:top_k]
