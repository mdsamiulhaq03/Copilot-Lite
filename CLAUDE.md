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
| Embeddings | `BAAI/bge-small-en-v1.5` (local, 384-dim, 512-token limit). Not all-MiniLM-L6-v2: it truncates at 256 tokens |
| Chunking | Split at `##` / `###` headings; cap ~350–400 tokens by splitting at paragraphs with 1–2 sentence overlap; keep tables and code blocks whole (an oversized table is split by rows with its header row repeated); prepend a breadcrumb `[folder/file.md > H1 > H2]` to every chunk |
| Retrieval | Hybrid: ChromaDB vector top-10 + `rank_bm25` keyword top-10, merged with Reciprocal Rank Fusion (`1/(60+rank)`), keep top 4. The BM25 index is built in memory at agent startup from `collection.get()`, so ChromaDB stays the only store |
| Interface | Command-line chat (`docker compose run --rm agents`) |
| Chat memory | Last 3 question/answer turns, kept in a Python list in memory only and cleared when the chat ends (nothing written to disk, so the "no persistence" rule holds). Follow-ups are rewritten into a standalone question by Groq before `rag_search`, and routing is sticky: a follow-up stays with the agent that handled the previous turn |

ChromaDB's built-in hybrid Search API was Chroma Cloud only when this was decided, which would break the local-only rule. When building ingestion, check whether the installed `chromadb` supports it locally; if so, raise it with the user as an option.

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

Not created yet. Folder names marked * are fixed by the guide.

```
knowledge/*          KB_V2 unzipped: 15 folders, 88 docs, plus MANIFEST.md (not ingested)
mock-logs/*          3 error log JSON files (e.g. BDT engine timeout, missing CSV, worker crash)
dummy-api/           FastAPI app
mcp-server/*         fastmcp server with fetch_error_logs
ingestion/           chunk → embed → ChromaDB
agents/              generic, debugger, router, rag (hybrid search), cli
docker-compose.yml          dummy-api, mcp-server, agents
docker-compose.ingest.yml   one-off ingestion job that exits
.env.example         GROQ_API_KEY, GROQ_MODEL, service URLs
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

Commit after each step. requirements.txt: one per service folder, only direct dependencies, pinned with `==`, saved as UTF-8.

## Knowledge base facts

- 253k words; files range from 97 to 16,268 words (median 1,220). 87 of 88 have `##` headings; 55 have tables; 41 have code blocks. The longest single section is 3,633 words, so the size cap is needed.
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

Windows 11; Docker 29.7. Local virtual environment: `.venv` (Python 3.13, run with `.venv\Scripts\python.exe`); the system default is Python 3.14, so don't use bare `python`. Containers pin their own Python (3.12 planned), so use Docker for running the services. Not a git repository yet.
