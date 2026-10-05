"""All settings in one place.

Each value can be set with an environment variable (in Docker, or in .env).
The defaults work when running from the backend/ folder on your laptop.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# backend/app/core/config.py -> parents[3] is the project root
PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _env_path(name: str, default: Path) -> Path:
    return Path(os.environ.get(name, str(default)))


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as error:
        raise ValueError(f"{name} must be a whole number, got {raw!r}") from error


@dataclass(frozen=True)
class Settings:
    knowledge_dir: Path
    chroma_dir: Path
    collection_name: str
    embedding_model: str
    model_cache_dir: Path
    chunk_max_tokens: int
    embed_batch_size: int
    search_candidates: int
    search_top_k: int


def load_settings() -> Settings:
    return Settings(
        knowledge_dir=_env_path("KNOWLEDGE_DIR", PROJECT_ROOT / "knowledge"),
        chroma_dir=_env_path("CHROMA_DIR", PROJECT_ROOT / "data" / "chroma"),
        collection_name=os.environ.get("COLLECTION_NAME", "maveric_docs"),
        embedding_model=os.environ.get("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5"),
        model_cache_dir=_env_path("MODEL_CACHE_DIR", PROJECT_ROOT / ".cache" / "fastembed"),
        chunk_max_tokens=_env_int("CHUNK_MAX_TOKENS", 400),
        # How many chunks the model embeds at once. Small batches keep memory low
        # (Docker has under 4 GB here); 256 needed about 3 GB and stalled.
        embed_batch_size=_env_int("EMBED_BATCH_SIZE", 32),
        # Hybrid search: each search (meaning and words) returns this many chunks,
        # then RRF merges the two lists and we keep the best search_top_k.
        search_candidates=_env_int("SEARCH_CANDIDATES", 10),
        search_top_k=_env_int("SEARCH_TOP_K", 4),
    )
