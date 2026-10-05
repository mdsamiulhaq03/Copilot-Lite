# Copilot Lite

Intern project: a two-agent assistant for the Maveric platform. The **Generic Agent** answers knowledge questions with RAG over 88 docs; the **Debugger Agent** diagnoses failures from error logs fetched through an MCP tool. Everything runs locally in Docker. Spec: [Copilot-lite.md](Copilot-lite.md) (Markdown copy of `Copilot-lite.pdf`). Diagrams: `copilot-lite-diagrams.excalidraw`.

## Working rules

- **No code until the user says "start coding".** Until then, only explain, plan and answer questions.
- The user must explain every part to their senior, so: build one step at a time, explain each step after building it, and show how to run and test it on its own before moving on.
- Keep the code small and plain. The reference repo is ~90% out of scope (auth, Redis, Postgres, guardrails, quality pipeline, tracing); copy patterns, not complexity.
- Don't change a decision below without asking; they were made one by one with the user.

## Hard constraints (from the guide, §4.3)

- **LLM:** Groq for both agents; model name and API key come from env vars, never hardcoded.
- **MCP:** the Debugger calls `fetch_error_logs` only through an MCP client connection to the MCP server, which runs as its own Compose service. Never import the tool function directly. Never hardcode log data in an agent.
- **RAG:** ingestion is purely local, with no external API calls (no LLM, no hosted embeddings). `/knowledge` is the only RAG source.
- **Debugger has no RAG:** it uses only the tool's logs plus base LLM knowledge.
- **Scope:** no auth, no frontend, no persistence beyond the vector store.
- **Docker:** write our own Compose files; the reference repo has none.

## Decided stack

| Part | Choice |
|---|---|
| LLM | Groq via `langchain-groq` |
| Agents | LangChain `create_agent` |
| MCP | `fastmcp`, Streamable HTTP transport; client side via `langchain-mcp-adapters` |
| Dummy Error Log API | FastAPI, one endpoint: `GET /v1/tenants/{tenant_id}/baselines/logs/errors`, returns the 3 logs from `/mock-logs` as a JSON array |
| Router | Keyword check (error, failure, log, crash), then a Groq yes/no check ("is the user reporting a problem?") only on a keyword hit |
| Vector store | ChromaDB, local and persistent |
| Embeddings | `BAAI/bge-small-en-v1.5` (local, 384-dim, 512-token limit), run through `fastembed` (ONNX Runtime, no PyTorch) via LangChain's `FastEmbedEmbeddings`. Model downloaded at Docker build time; ingestion runs offline. Not all-MiniLM-L6-v2: it truncates at 256 tokens |
| RAG components | LangChain throughout: `MarkdownHeaderTextSplitter` + our own small function for the size cap, whole tables and breadcrumbs; `langchain-chroma` `Chroma`; `BM25Retriever`; `EnsembleRetriever` for RRF (c=60, equal weights). In LangChain 1.0 `EnsembleRetriever` may have moved to `langchain-classic`: check, and fall back to ~10 lines of our own RRF if needed. Turn off ChromaDB telemetry and make sure LangSmith tracing is off (no outside calls) |
| Chunking | Split at `##` / `###` headings; cap ~350–400 tokens by splitting at paragraphs with 1–2 sentence overlap; keep tables and code blocks whole (an oversized table is split by rows with its header row repeated); prepend a breadcrumb `[folder/file.md > H1 > H2]` to every chunk |
| Retrieval | Hybrid: ChromaDB vector top-10 + `rank_bm25` keyword top-10, merged with Reciprocal Rank Fusion (`1/(60+rank)`), keep top 4. The BM25 index is built in memory at agent startup from `collection.get()`, so ChromaDB stays the only store |
| Interface | Command-line chat (`docker compose run --rm agents`) |
| Chat memory | Last 3 question/answer turns, kept in a Python list in memory only and cleared when the chat ends (nothing written to disk, so the "no persistence" rule holds). Follow-ups are rewritten into a standalone question by Groq before `rag_search`, and routing is sticky: a follow-up stays with the agent that handled the previous turn |

ChromaDB's built-in hybrid Search API is Chroma Cloud only. Checked with chromadb 1.5.9: `collection.search()` raises "Search is not implemented for Local Chroma". So we use LangChain's `EnsembleRetriever` (from `langchain_classic.retrievers`); `BM25Retriever` comes from `langchain_community.retrievers`. fastembed's bge-small is the quantized ONNX copy `Qdrant/bge-small-en-v1.5-onnx-Q` (67 MB).

## Fallback behaviour

Fail loudly at startup, fail gracefully at runtime, never make things up.

- Router error or unparseable LLM reply → Generic Agent.
- Question rewrite fails → search with the original question.
- No relevant chunks → say the docs don't cover it; don't answer from guesswork, don't forward to the Debugger.
- Empty ChromaDB → stop at startup with the ingestion command to run.
- BM25 fails to build → continue with vector search alone and log a warning.
- MCP server or Dummy API down → the tool returns an error message (no exception); the Debugger tells the user it couldn't fetch logs.
- Empty logs → say no errors were found; don't invent a root cause.
- Missing `GROQ_API_KEY` → stop at startup. Rate limit / timeout → retry 2–3 times with backoff, then a friendly message. Groq 400 "tool call validation failed" → ask the user to rephrase.

## Planned layout

Chosen by the user (option A): the main Python app lives in `backend/`; the folders the guide names (marked *) stay at the root, and so does each separate service.

```
backend/                     ingestion + RAG + agents: one requirements.txt, one Dockerfile, one image
  app/
    core/config.py           all env settings in one place
    rag/chunker.py           headings, ~400 tokens, tables whole, breadcrumb
    rag/embeddings.py        loads bge-small
    rag/vector_store.py      ChromaDB connection
    rag/hybrid_search.py     BM25 + RRF (step 2)
    rag/tools.py             rag_search tool (step 3)
    agents/                  generic, debugger, router (steps 3, 4, 7)
    cli.py                   terminal chat (step 3)
  scripts/ingest.py          one-off ingestion job (python -m scripts.ingest)
  tests/                     optional, later
  requirements.txt
  Dockerfile
dummy-api/                   FastAPI service (step 5)
mcp-server/*                 fastmcp server with fetch_error_logs (step 6)
mock-logs/*                  3 error log JSON files (step 5)
knowledge/*                  KB_V2 unzipped: 15 folders, 88 docs, plus MANIFEST.md (not ingested); git-ignored
docker-compose.yml           dummy-api, mcp-server, agents (backend image)
docker-compose.ingest.yml    one-off ingestion job using the backend image
.env.example                 GROQ_API_KEY, GROQ_MODEL, service URLs
README.md
```

## Build order

The user chose to build RAG first and the Debugger last. They are new to MCP, so explain it fully when steps 5 to 7 come up.

1. Ingestion (chunk → embed → ChromaDB) + `docker-compose.ingest.yml`
2. Hybrid search (ChromaDB + BM25 + RRF)
3. Generic Agent (Groq + `rag_search`) + CLI chat + 3-turn memory with question rewriting
4. Router (keyword + Groq check); debug questions get a "Debugger not ready yet" reply until step 7
5. Dummy Error Log API + 3 mock logs
6. MCP server with `fetch_error_logs`
7. Debugger Agent as MCP client + sticky routing
8. `docker-compose.yml` for everything + README

Commit after each step. requirements.txt: one per service (`backend/`, `dummy-api/`, `mcp-server/`), only direct dependencies, pinned with `==`, saved as UTF-8.

## Knowledge base facts

- 253k words; files range from 97 to 16,268 words (median 1,220). 87 of 88 have `##` headings; 55 have tables; 41 have code blocks. The longest single section is 3,633 words, so the size cap is needed.
- Chunker result with the real bge tokenizer: 2,763 chunks, 26 to 399 tokens (median 304). Table separator rows are padded with hundreds of dashes, and the tokenizer counts every dash, so the chunker shortens them to `| --- |`. A few single table rows or code lines exceed the limit and are split by words as a last resort.
- Embedding batch size must stay small (`EMBED_BATCH_SIZE`, default 32). Docker Desktop here has only 3.7 GB of memory, and fastembed's default batch of 256 used about 3 GB and stalled. With batch 32 and chunks sorted by length, full ingestion in Docker takes about 345 s (the earlier local run with batch 256 took 908 s).
- Read files with `encoding="utf-8"`. Windows PowerShell 5.1 prints them garbled (`â€”` for `—`), but the files are fine.
- `KB_V2.zip` stored its paths with backslashes; unzip it on Windows, not inside a Linux container.

## Reference repo

`C:\Users\HP\Downloads\cloudlynet_ai_copilot-main\cloudlynet_ai_copilot-main` (also https://github.com/CloudlyIO/cloudlynet_ai_copilot). Read it for patterns only; it can't run here. Starting files per guide §4.1:

- Ingestion / `rag_search`: `backend/scripts/ingest_knowledge_base.py`, `backend/app/rag/ingestion.py`, `backend/app/rag/tools.py`
- MCP server: `backend/app/mcp_server/server.py`, `backend/app/mcp_server/domains/diagnostics_tools.py`
- Debugger + MCP client: `backend/app/agents/debugger/agent.py`, `backend/app/mcp_client.py`
- Generic Agent + routing: `backend/app/agents/reactive/agent.py`, `backend/app/agents/routing/agent.py`
- Dockerfiles: `backend/Dockerfile`, `backend/app/mcp_server/Dockerfile`

Where the reference differs from this project, follow this project:
- Its ingestion calls Groq per chunk to add context. We don't; the breadcrumb replaces it.
- It uses Postgres/pgvector and Redis. We use ChromaDB only.
- Its Debugger inherits RAG from ReactiveAgent. Ours has no RAG.
- It uses SSE for MCP. We use Streamable HTTP.
- Its MCP server Dockerfile exposes 8080 while its client uses 8082. Pick one port per service and use it everywhere.

## Environment

Windows 11; Docker 29.7. Local virtual environment: `.venv` (Python 3.13, run with `.venv\Scripts\python.exe`); the system default is Python 3.14, so don't use bare `python`. Containers pin their own Python (3.12 planned), so use Docker for running the services.

Git: remote `origin` = github.com/mdsamiulhaq03/Copilot-Lite, default branch `main`. One feature branch per build step (`feat/ingestion`, `feat/hybrid-search`, ...), merged into `main` when the step works. Ignored (never committed): `.env`, `docs/`, `knowledge/`, `Copilot-lite.md`, `Copilot-lite.pdf`, the diagram, `.venv/`, Python caches. Because `knowledge/` is ignored, the README must tell readers to unzip `KB_V2.zip` into `/knowledge`.
