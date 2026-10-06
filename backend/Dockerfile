# Backend image: the agents (chat), and the one-off ingestion job.
FROM python:3.12-slim

# No .pyc files, print logs straight away, keep pip quiet and the image small
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# 1. Install libraries first. Docker caches this step, so changing our code
#    later does not reinstall everything.
COPY requirements.txt .
RUN pip install -r requirements.txt

# 2. Download the embedding model now, while building, so the container never
#    needs the internet at run time (the guide: ingestion is purely local).
ENV EMBEDDING_MODEL=BAAI/bge-small-en-v1.5 \
    MODEL_CACHE_DIR=/models
RUN python -c "import os; from fastembed import TextEmbedding; \
TextEmbedding(os.environ['EMBEDDING_MODEL'], cache_dir=os.environ['MODEL_CACHE_DIR'])"

# From here on, never try to reach Hugging Face
ENV HF_HUB_OFFLINE=1

# 3. Copy our code
COPY app ./app
COPY scripts ./scripts

# Where things live inside the container (mounted by docker compose)
ENV KNOWLEDGE_DIR=/knowledge \
    CHROMA_DIR=/data/chroma

# 4. Run as a normal user, not root. /data/chroma is created here so a Docker
#    volume mounted on it is writable by this user.
RUN useradd --create-home appuser \
    && mkdir -p /data/chroma \
    && chown -R appuser:appuser /app /models /data
USER appuser

# Default job: the terminal chat. (docker-compose.ingest.yml runs ingestion instead.)
CMD ["python", "-m", "app.cli"]
