"""ChromaDB: where the chunks and their numbers (embeddings) are stored.

We create the ChromaDB client ourselves so we can turn off its anonymous usage
statistics: nothing should leave the machine. LangChain's Chroma class sits on
top of it and uses our embedding model to turn text into numbers.
"""

from __future__ import annotations

import chromadb
from chromadb.config import Settings as ChromaSettings
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from app.core.config import Settings
from app.rag.chunker import Chunk


def open_vector_store(settings: Settings, embeddings: Embeddings) -> Chroma:
    """Open (or create) the ChromaDB collection saved in settings.chroma_dir."""
    client = chromadb.PersistentClient(
        path=str(settings.chroma_dir),
        settings=ChromaSettings(anonymized_telemetry=False),
    )
    return Chroma(
        client=client,
        collection_name=settings.collection_name,
        embedding_function=embeddings,
        # Compare vectors by direction (cosine), the right measure for bge.
        collection_configuration={"hnsw": {"space": "cosine"}},
    )


def clear_collection(store: Chroma) -> None:
    """Delete every chunk, so ingestion always rebuilds from the current docs.

    Without this, chunks from a doc that was changed or removed would stay in
    the store and could still show up in answers.
    """
    store.reset_collection()


def add_chunks(store: Chroma, chunks: list[Chunk]) -> None:
    """Embed the chunks with our model and save them, with their metadata."""
    documents = [
        Document(
            page_content=chunk.text,
            metadata={
                "source": chunk.source,
                "breadcrumb": chunk.breadcrumb,
                "chunk_index": chunk.index,
                "token_count": chunk.token_count,
            },
        )
        for chunk in chunks
    ]
    ids = [f"{chunk.source}#{chunk.index}" for chunk in chunks]
    store.add_documents(documents, ids=ids)


def count_chunks(store: Chroma) -> int:
    """How many chunks are saved in the collection."""
    return len(store.get(include=[])["ids"])
