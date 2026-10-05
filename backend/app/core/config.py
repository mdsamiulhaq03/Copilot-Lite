"""All settings in one place.

Each value can be set with an environment variable (in Docker, or in .env).
The defaults work when running from the backend/ folder on your laptop.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# backend/app/core/config.py -> parents[3] is the project root
PROJECT_ROOT = Path(__file__).resolve().parents[3]


class ConfigError(Exception):
    """A required setting is missing, so the app cannot start."""


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
    groq_model: str
    # repr=False: the key never shows up if the settings are printed or logged
    groq_api_key: str = field(repr=False)


def load_settings() -> Settings:
    # On your laptop, read the project's .env file. It never overrides a value
    # that is already set, and in Docker there is no .env file, so it does nothing.
    load_dotenv(PROJECT_ROOT / ".env")
    # LangChain can send traces to LangSmith. Force it off: no outside calls.
    os.environ["LANGSMITH_TRACING"] = "false"

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
        # No defaults: the guide says the model and key come only from env vars
        groq_model=os.environ.get("GROQ_MODEL", "").strip(),
        groq_api_key=os.environ.get("GROQ_API_KEY", "").strip(),
    )


def check_groq_settings(settings: Settings) -> None:
    """Stop at startup if Groq is not set up. Only the agents need this;
    ingestion and search work without a key."""
    missing = [
        name
        for name, value in (("GROQ_API_KEY", settings.groq_api_key), ("GROQ_MODEL", settings.groq_model))
        if not value
    ]
    if missing:
        raise ConfigError(
            f"Missing {', '.join(missing)}. Copy .env.example to .env in the project root "
            "and fill it in."
        )
