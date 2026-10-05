"""The embedding model: turns text into 384 numbers.

We run BAAI/bge-small-en-v1.5 with fastembed (ONNX Runtime, no PyTorch),
through LangChain's FastEmbedEmbeddings wrapper. The same model must be used
for the chunks (ingestion) and for the questions (search), otherwise the
numbers cannot be compared.
"""

from __future__ import annotations

import os

from langchain_community.embeddings import FastEmbedEmbeddings
from tokenizers import Tokenizer

from app.core.config import Settings
from app.rag.chunker import TokenCounter

# Windows cannot create the symlinks the Hugging Face cache prefers. The cache
# still works without them, so hide the long warning about it.
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")


def load_embeddings(settings: Settings) -> FastEmbedEmbeddings:
    """Load the embedding model from the local cache (downloading it if missing)."""
    try:
        return FastEmbedEmbeddings(
            model_name=settings.embedding_model,
            cache_dir=str(settings.model_cache_dir),
            batch_size=settings.embed_batch_size,
        )
    except Exception as error:
        raise RuntimeError(
            f"Could not load the embedding model {settings.embedding_model!r} "
            f"from {settings.model_cache_dir}. In Docker it is downloaded when the "
            "image is built; locally it needs internet the first time."
        ) from error


def make_token_counter(embeddings: FastEmbedEmbeddings) -> TokenCounter:
    """Return a function that counts tokens exactly the way the model does.

    We copy the model's tokenizer and turn off its 512-token cut-off, so that
    long text shows its real length. The model keeps its own tokenizer as is.
    """
    model_tokenizer = embeddings.model.model.tokenizer  # fastembed's internal tokenizer
    tokenizer = Tokenizer.from_str(model_tokenizer.to_str())
    tokenizer.no_truncation()
    tokenizer.no_padding()

    def count_tokens(text: str) -> int:
        return len(tokenizer.encode(text, add_special_tokens=False).ids)

    return count_tokens
