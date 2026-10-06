"""Ingestion: load the knowledge base into ChromaDB.

Steps: find the docs -> split them into chunks -> embed the chunks -> save them.
Runs fully offline once the embedding model is downloaded. Every run rebuilds
the collection from scratch, so it always matches the current docs.

Run from the backend/ folder:
    python -m scripts.ingest            # full run
    python -m scripts.ingest --dry-run  # only chunk and print statistics
"""

from __future__ import annotations

import argparse
import logging
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

from langchain_core.embeddings import Embeddings

from app.core.config import Settings, load_settings
from app.rag.chunker import Chunk, TokenCounter, chunk_document
from app.rag.embeddings import load_embeddings, make_token_counter
from app.rag.vector_store import add_chunks, clear_collection, count_chunks, open_vector_store

# How many chunks go to ChromaDB in one save call (and how often progress is
# logged). Not the embedding batch: the model still embeds EMBED_BATCH_SIZE (32)
# chunks at a time, which is what keeps memory low.
SAVE_BATCH_SIZE = 256

logger = logging.getLogger("ingest")


class IngestError(Exception):
    """A problem that stops ingestion, with a message that says how to fix it."""


def find_markdown_files(knowledge_dir: Path) -> list[Path]:
    """All .md files inside the knowledge folder's sub-folders.

    Files directly in the knowledge folder (like MANIFEST.md, which only lists
    the bundle's contents) are skipped.
    """
    if not knowledge_dir.is_dir():
        raise IngestError(
            f"Knowledge folder not found: {knowledge_dir}. "
            "Unzip KB_V2.zip into the project's knowledge/ folder, or set KNOWLEDGE_DIR."
        )
    files = sorted(path for path in knowledge_dir.rglob("*.md") if path.parent != knowledge_dir)
    if not files:
        raise IngestError(f"No .md files found in the sub-folders of {knowledge_dir}.")
    return files


def chunk_files(files: list[Path], settings: Settings, count_tokens: TokenCounter) -> list[Chunk]:
    """Read every file as UTF-8 and split it into chunks."""
    chunks: list[Chunk] = []
    for path in files:
        source = path.relative_to(settings.knowledge_dir).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise IngestError(f"Could not read {source}: {error}") from error
        chunks += chunk_document(text, source, settings.chunk_max_tokens, count_tokens)
    if not chunks:
        raise IngestError("The docs produced 0 chunks. Check that the files are not empty.")
    return chunks


def log_statistics(files: list[Path], chunks: list[Chunk]) -> None:
    sizes = [chunk.token_count for chunk in chunks]
    per_folder = Counter(chunk.source.split("/")[0] for chunk in chunks)
    logger.info("Files: %d | chunks: %d", len(files), len(chunks))
    logger.info(
        "Chunk size in tokens: min %d, median %d, max %d",
        min(sizes),
        int(statistics.median(sizes)),
        max(sizes),
    )
    for folder, total in sorted(per_folder.items()):
        logger.info("  %-16s %5d chunks", folder, total)


def save_chunks(chunks: list[Chunk], settings: Settings, embeddings: Embeddings) -> int:
    """Clear the collection, then embed and save the chunks in batches.

    Chunks are sorted by length first. The model pads every chunk in a batch to
    the longest one, so batching similar lengths together wastes less work.
    The order inside ChromaDB does not matter for search.
    """
    store = open_vector_store(settings, embeddings)
    clear_collection(store)
    by_length = sorted(chunks, key=lambda chunk: chunk.token_count)
    for start in range(0, len(by_length), SAVE_BATCH_SIZE):
        batch = by_length[start : start + SAVE_BATCH_SIZE]
        add_chunks(store, batch)
        logger.info("Saved %d / %d chunks", start + len(batch), len(chunks))
    saved = count_chunks(store)
    if saved != len(chunks):
        raise IngestError(f"Expected {len(chunks)} chunks in ChromaDB but found {saved}.")
    return saved


def run(dry_run: bool) -> None:
    settings = load_settings()
    logger.info("Knowledge folder: %s", settings.knowledge_dir)

    files = find_markdown_files(settings.knowledge_dir)
    embeddings = load_embeddings(settings)
    chunks = chunk_files(files, settings, make_token_counter(embeddings))
    log_statistics(files, chunks)

    if dry_run:
        logger.info("Dry run: nothing was saved.")
        return

    logger.info("Embedding with %s and saving to %s", settings.embedding_model, settings.chroma_dir)
    started = time.monotonic()
    saved = save_chunks(chunks, settings, embeddings)
    logger.info(
        "Done: %d chunks in collection %r (%.0f s)",
        saved,
        settings.collection_name,
        time.monotonic() - started,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Load the knowledge base into ChromaDB.")
    parser.add_argument("--dry-run", action="store_true", help="only chunk and print statistics")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        run(args.dry_run)
    except (IngestError, RuntimeError) as error:
        logger.error("%s", error)
        sys.exit(1)


if __name__ == "__main__":
    main()
