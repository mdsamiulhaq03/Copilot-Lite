# Copilot Implementation Summary

**Project:** cloudlynet_ai_copilot
**Branch:** `main`
**Date:** 2026-05-22 (last updated)
**Assisted by:** Claude Code (across multiple sessions with auto-compactions)

> **Session continuity note:** If the conversation context has been compacted or a new session has started, read this file first before doing anything. It contains the current-state record of copilot architecture, integration, known issues, and pending work. The extensive implementation log (plan evolution, full phase-by-phase narrative, developer attributions, fixed-and-forgotten bug postmortems) is archived in [COPILOT_HISTORY.md](./COPILOT_HISTORY.md) — consult that file only when this file references a past decision you need depth on. User/workflow preferences for working in this submodule live in [CLAUDE.md](./CLAUDE.md).

> **On "Maveric" vs "CloudlyNet":** Maveric is the upstream open-source platform that copilot integrates with; CloudlyNet is the in-house build on top of Maveric with additional features and enhancements. CloudlyNet tracks Maveric but typically lives ahead of it. Throughout this document, references to "Maveric" (the `maveric` Docker network, `maveric_platform_*` submodules, "Maveric ecosystem") apply equally to CloudlyNet — the codebase has not been wholesale renamed. When in doubt, read "Maveric" as "Maveric/CloudlyNet".

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Implementation Timeline (Lean History)](#2-implementation-timeline-lean-history)
7. [Integration Architecture (net_ai ↔ Copilot)](#7-integration-architecture-net_ai--copilot)
8. [Current File Map](#8-current-file-map)
9. [Remaining Work](#9-remaining-work)
10. [RAG Pipeline & Knowledge Base — Current State + Known Issues](#10-rag-pipeline--knowledge-base--current-state--known-issues)
12. [Issue Tracker Categories](#12-issue-tracker-categories-github-project)
18. [Troubleshooting & Operational Notes](#18-troubleshooting--operational-notes-2026-03-11)
19. [Tenant Isolation & PostgreSQL RLS](#19-tenant-isolation--postgresql-rls)
20. [Data Generation Agent](#20-data-generation-agent)
21. [SSE Streaming for Agent Queries](#21-sse-streaming-for-agent-queries)
22. [JWT Forwarding for MCP Tool Calls](#22-jwt-forwarding-for-mcp-tool-calls)
23. [Trial User Query Cap](#23-trial-user-query-cap)
24. [Inference Explanation Agent + Page Context](#24-inference-explanation-agent--page-context)
25. [Per-Query Trace Logging](#25-per-query-trace-logging)
26. [Response Length Calibration + Structured Output Payloads](#26-response-length-calibration--structured-output-payloads)
27. [Guardrail Pipeline (Input Safety)](#27-guardrail-pipeline-input-safety)
28. [Routing Prompt Disambiguation](#28-routing-prompt-disambiguation)
29. [User-Facing Output Rules](#29-user-facing-output-rules)
30. [Orchestrator mypy Fixes + CI Scoping](#30-orchestrator-mypy-fixes--ci-scoping-2026-07-30)
31. [MCP Domain Coverage](#31-mcp-domain-coverage-2026-08-20)
32. [MCP Server Lifecycle Tracing](#32-mcp-server-lifecycle-tracing-2026-08-27)
33. [Backend MCP Client — Copilot Consumes the MCP Server (Milestone 1)](#33-backend-mcp-client--copilot-consumes-the-mcp-server-milestone-1-2026-08-28)
34. [RCA Tool Wiring + LLM-Driven Loop (Milestone 2, Part 1)](#34-rca-tool-wiring--llm-driven-loop-milestone-2-part-1-2026-09-03)
35. [MCP Wiring Paging — Cursor Auto-Paging and Fields Projection](#35-mcp-wiring-paging--cursor-auto-paging-and-fields-projection-2026-09-08)
36. [KB v2 — Corpus Rebuild from `artifacts/`, and the Standing Include/Exclude Policy](#36-kb-v2--corpus-rebuild-from-artifacts-and-the-standing-includeexclude-policy-2026-09-10)
37. [Output Redaction Layer (Tiers 0/1/2/4)](#37-output-redaction-layer-tiers-0124-2026-09-14)

> **What moved out of SUMMARY (and where to find it):**
> - §3–§6 (Plan Evolution, Phase-by-Phase Implementation, Developer Contributions, Bug Log) → [COPILOT_HISTORY.md §1–§4](./COPILOT_HISTORY.md)
> - §14–§17 (KPI Tool deprecated, RAG Benchmark snapshot, Infrastructure Consolidation event, Post-Consolidation Task Plan mostly DONE) → [COPILOT_HISTORY.md §5–§8](./COPILOT_HISTORY.md)
> - §13 (RAG Improvement Research Evolution — branch strategy, implementation log, benchmarking plan) → folded into the merged §10 here for current-state, with historical narrative archived at [COPILOT_HISTORY.md §9](./COPILOT_HISTORY.md#9-rag-improvement-research--evaluation-evolution-2026-03)
> - §11 (Parent Repo Integration — Docker compose / DB init / env vars) → folded into [CLAUDE.md "Build / Run / Test"](./CLAUDE.md) where the operational steps actually belong
> - §6 User Preferences → [CLAUDE.md](./CLAUDE.md)
>
> §2 below is the lean replacement timeline.

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                         Copilot                              │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│   ┌─────────────────────────────────────────────────────┐   │
│   │                    RAG Layer                         │   │
│   │  - EmbeddingService (all-MiniLM-L6-v2, 384-dim)     │   │
│   │  - DocumentProcessor (markdown/code-aware chunking)  │   │
│   │  - PlatformKnowledgeRetriever (pgvector search)      │   │
│   │  - Exposes: rag_search tool                          │   │
│   │  - Location: backend/app/rag/                        │   │
│   └─────────────────────────────────────────────────────┘   │
│                           │                                  │
│              (rag_search tool available to)                   │
│                           │                                  │
│   ┌─────────────────────────────────────────────────────┐   │
│   │           Reactive Agent (Primary Default)           │   │
│   │  - ReAct agent using LangChain create_agent          │   │
│   │  - Tool: rag_search (when retriever wired)           │   │
│   │  - Base class for specialized agents                 │   │
│   │  - Dynamic prompts based on tool availability        │   │
│   └─────────────────────────────────────────────────────┘   │
│                           │                                  │
│                   (inherits from)                             │
│                           │                                  │
│   ┌─────────────────────────────────────────────────────┐   │
│   │           Debugger Agent (Debugging Specialist)      │   │
│   │  - Inherits from Reactive Agent                      │   │
│   │  - Tool: rag_search (inherited)                      │   │
│   │  - Tool: compare_rapp_policies (MCP)                 │   │
│   │  - Tool: get_platform_error_logs (MCP)               │   │
│   │  - Dynamic prompts (3-tier: full/rag-only/no-tools)  │   │
│   └─────────────────────────────────────────────────────┘   │
│                                                              │
│   ┌─────────────────────────────────────────────────────┐   │
│   │       Data Generation Agent (Guidance-Only)          │   │
│   │  - Inherits from Reactive Agent                      │   │
│   │  - 8 MCP tools (validate, recommend, query,          │   │
│   │    compare, estimate, docs)                          │   │
│   │  - Tool: rag_search (inherited, supplementary)       │   │
│   │  - Never mutates — emits API commands only           │   │
│   └─────────────────────────────────────────────────────┘   │
│                                                              │
│   ┌─────────────────────────────────────────────────────┐   │
│   │   Inference Explanation Agent (Result Expert)        │   │
│   │  - Inherits from Reactive Agent                      │   │
│   │  - Tool: rag_search (inherited)                      │   │
│   │  - Tool: get_inference_report (MCP, page-bound)      │   │
│   │  - Tool: compare_inference_models (MCP, page-bound)  │   │
│   │  - 4-tier prompts (full/navigate/rag-only/no-tools)  │   │
│   │  - Strict guardrails: no math, every claim cites     │   │
│   │    a value, no rollout decisions                     │   │
│   └─────────────────────────────────────────────────────┘   │
│                                                              │
│   ┌─────────────────────────────────────────────────────┐   │
│   │          Internal Fallback Agents (Not Public)       │   │
│   │  - GenericAgent: simple conversation (internal)      │   │
│   │  - OfflineDebuggingAgent: placeholder (internal)     │   │
│   └─────────────────────────────────────────────────────┘   │
│                                                              │
│   ┌─────────────────────────────────────────────────────┐   │
│   │                 MCP Tools Layer                       │   │
│   │  - CloudlyNetAPIClient (per-request JWT auth)        │   │
│   │  - compare_rapp_policies, get_platform_error_logs    │   │
│   │  - get_inference_report, compare_inference_models    │   │
│   │  - 8 data-generation tools (6 in-memory, 2 gateway)  │   │
│   │  - MCP Server (FastMCP SSE, maveric network)         │   │
│   └─────────────────────────────────────────────────────┘   │
│                                                              │
│   ┌─────────────────────────────────────────────────────┐   │
│   │            Knowledge Ingestion API                   │   │
│   │  - POST /knowledge/sources (create source)           │   │
│   │  - GET  /knowledge/sources (list sources)            │   │
│   │  - POST /knowledge/sources/{id}/ingest (fetch+embed) │   │
│   │  - POST /knowledge/search (semantic search)          │   │
│   └─────────────────────────────────────────────────────┘   │
│                                                              │
│   ┌─────────────────────────────────────────────────────┐   │
│   │            LangGraph Orchestrator                    │   │
│   │  - Routing agent (LLM-based query classification)    │   │
│   │  - Conditional edges: START → router → agent → END   │   │
│   │  - Agent hierarchy: reactive > debugger > data_gen   │   │
│   └─────────────────────────────────────────────────────┘   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Agent Tool Mapping

| Agent | rag_search | compare_rapp_policies | get_platform_error_logs | get_inference_report | compare_inference_models | data-gen tools (8) |
|-------|:---:|:---:|:---:|:---:|:---:|:---:|
| ReactiveAgent | Yes (when retriever wired) | No | No | No | No | No |
| DebuggerAgent | Yes (inherited) | Yes (when api_client set) | Yes (when api_client set) | No | No | No |
| DataGenerationAgent | Yes (supplementary) | No | No | No | No | Yes (when api_client set) |
| InferenceExplanationAgent | Yes (inherited) | No | No | Yes (on Recommendation Review) | Yes (on Compare Outcomes) | No |
| GenericAgent (internal) | No | No | No | No | No | No |
| OfflineDebuggingAgent (internal) | No | No | No | No | No | No |

> All agents now also receive `page_context` from the FE on every query — see §24. Every agent's system prompt includes a "Current Page Context" block so Copilot is aware of which CloudlyNet page the user is on. Inference agent tool registration is page-bound: tools are only added to the LLM's available set when their target page is active.

> `analyze_rapp_kpis` (previously on DebuggerAgent — see [HISTORY §5](./COPILOT_HISTORY.md#5-kpi-analysis-mcp-tool-2026-03-05-implemented-2026-03-16)) was **removed** in the inference agent commit. The new `get_inference_report` is a strict superset; debugger drops back to platform diagnostics only.

> **Legacy / dead-code agents — never exposed:** `GenericAgent` ([`generic/agent.py`](./backend/app/agents/generic/agent.py)) and `OfflineDebuggingAgent` ([`offline_debugging/agent.py`](./backend/app/agents/offline_debugging/agent.py)) are placeholders from an earlier design. They are not wired into the routing path, not invoked at runtime, and **will not be exposed to users**. Do not factor them into feature design, prompt work, output-rule scope, or test planning. The corresponding `AgentName` enum entries (`GENERIC_AGENT`, `OFFLINE_DEBUGGING_AGENT` in [`app/core/enums.py`](./backend/app/core/enums.py)) are similarly dormant. Treat both as code awaiting deletion.

---

## 2. Implementation Timeline (Lean History)

One-line-per-feature chronology of how copilot got to its current state. **Each entry links to the deeper section in this file** (current state) **and to its full implementation log in [`COPILOT_HISTORY.md`](./COPILOT_HISTORY.md)** (rationale, files changed, decisions). For full bug-fix archaeology and developer attributions, see HISTORY §3 and §4.

| When | Feature / Phase | Branch / PR | What landed | Current state |
|------|-----------------|-------------|-------------|---------------|
| Feb 2026 | Phases 1–4: RAG foundation | `bc798ca` → PR #4 | pgvector schema (`knowledge.*`), `EmbeddingService` (all-MiniLM-L6-v2, 384-dim), `DocumentProcessor` (markdown/code-aware), `PlatformKnowledgeRetriever`, `KnowledgeIngestionService`, `rag_search` tool | §1, §10 |
| Feb 2026 | Phase 5: Reactive Agent | PR #5 | `ReactiveAgent` base class with LangChain `create_agent`, Groq `openai/gpt-oss-120b`, tool-trace extraction | §1 |
| Feb 2026 | Phase 6: MCP Tools (Tanzim) | PR #3 | FastMCP SSE server, `CloudlyNetAPIClient`, `compare_rapp_policies` + `get_platform_error_logs` | §1 |
| Feb 2026 | Phase 7: Debugger Agent | PR #6 | `DebuggerAgent` inheriting `ReactiveAgent`; MCP tools wired in; works in RAG-only mode | §1 |
| Feb 2026 | Phase 8: Orchestrator | `8a4bbc6` → `362970e` | LangGraph routing, 4-agent hierarchy, dynamic prompts (fixed Groq `tool_choice=none` 400) | §1 |
| Feb 2026 | Phase 9: Knowledge Ingestion API | `e2c25bf`, `a99084f` | REST endpoints for sources/ingest/search; retriever wired into orchestrator with per-invocation DB sessions | §10 |
| Feb 2026 | Phase 10: MCP reconnection + tenant_id | `28b6b65` | MCP config decoupled from Settings, `tenant_id` threaded from JWT, error-log parsing fix | §7 |
| Feb 2026 | Phase 11: URL tenant routing | `mcp_fix` branch | `tenant_id` moved from header → URL path; `StrEnum` migration; test coverage uplift | §7 |
| Aug 2026 | EPIC-8: MCP domain coverage | PR #36 (`feat/epic-8`) | One server, per-domain tool modules; registry 12 → 34; one response envelope; identity moved off the LLM into `ToolContext`; triple-gated approve/reject as the first write path; two placeholder tools deleted | §31 |
| Aug 2026 | EPIC-8: inference-report and dataset-read fixes | PR #36 | Per-tick recommendation objects read correctly (a real 24-tick run went from `0` to **182** switched-off cells); congestion derived from `serving_cells` as rApp derives it; `get_ue_dataset` reads the new per-dataset endpoint instead of scanning a bounded list | §31 |
| Aug 2026 | EPIC-8: MCP live-validation fix set | PR #36 (`feat/epic-8`) | All 37 tools validated live against a running stack; ~40 defects fixed (envelope/paging/id-validation/read-back evidence across every domain) and test fakes reshaped from the fixture pack to real gateway rows. Suite 1113 → 1282 | §31 |
| Aug 2026 | EPIC-8: MCP server lifecycle tracing | PR #36 (`feat/epic-8`) | The `:8082` container logged nothing on any success path and discarded every startup record; it now emits boot / session / handshake / list / call / shutdown events. Fixed four latent defects found while building it, including a `@retry` that had never fired and four tools dead on the wire | §32 |
| 2026-08-28 | Backend MCP client (Milestone 1) | `feat/mcp-integration` (off `089ee26`) | First backend→MCP-server connection: agents can call the `:8082` registry over SSE. `app/mcp_client.py` + 8 read-only tools wired into the Debugger behind `COPILOT_MCP_SERVER_URL`. All 34 reachable; other agents + the RCA loop are Milestone 2 | §33 |
| 2026-09-03 | RCA tool wiring + LLM-driven loop (Milestone 2 pt 1) | `feat/mcp-integration` | All 34 MCP tools wired to the Debugger (pin 12 + pool 22); LLM-driven RCA loop — gate + tool-forcing middleware + answer cleanup; folded the duplicate api_client tools; disabled the broken RedisCache. 30/34 tools verified called via an API sweep (RCA set 16/16) | §34 |
| 2026-09-08 | MCP wiring paging | `feat/mcp-integration` | Wiring exposed only `limit`, dropping the server's cursor paging + `fields` projection: RCA saw page 1 only and full-width rows. Added internal cursor auto-paging (`_auto_paged`, bound 4, cursor never shown to the model) + `fields` projection on 11 list tools (available fields listed per tool description); `list_devices`/`list_edges` given real schemas | §35 |
| 2026-02-19 | RAG threshold + retry tuning | inline commits | Threshold 0.5 → 0.15, mandatory RAG-first, 3-attempt retry strategy, References section (later removed §29) | §10 |
| 2026-03-04 | RAG improvement research | `rag/*` branches | Hybrid (BM25 + RRF) and contextual retrieval (`ChunkContextualizer`) merged; cross-encoder reranker built but not merged due to 8–12 s latency | §10 (current state), [HISTORY §6 + §9](./COPILOT_HISTORY.md) |
| 2026-03-05 | KPI MCP tool (debugger) | `kpi-tools` branch | `analyze_rapp_kpis` — combines `/infer` day-scope KPIs with RAG explanations | [HISTORY §5](./COPILOT_HISTORY.md#5-kpi-analysis-mcp-tool-2026-03-05-implemented-2026-03-16) (deprecated by §24) |
| 2026-03-09 | Infrastructure consolidation | parent repo | Single `docker-compose.yaml`; shared postgres/redis/minio; dual router (platform `/v1` + legacy `/api/v1`) | [CLAUDE.md](./CLAUDE.md) (operational steps), [HISTORY §7](./COPILOT_HISTORY.md#7-infrastructure-consolidation-2026-03-09) (event narrative) |
| 2026-03–04 | Tenant isolation + Postgres RLS | `feature/tenant-rls` | `tenant_id` columns + RLS context vars on conversation tables; defense-in-depth on top of WHERE filters | §19 |
| 2026-04 | Data Generation Agent | `feature/data-generation-agent` | `DataGenerationAgent` (guidance-only); 8 MCP tools (validate / recommend / query / compare / estimate) | §20 |
| 2026-04 | SSE streaming | `enhancement/streaming` | `POST /agents/query/stream` with `EventSourceResponse`; 6 SSE event types; `generic_agent` removed from public list | §21 |
| 2026-04 | JWT forwarding | `fix/jwt-forwarding` | Cognito JWT threaded end-to-end to MCP tool factories; `CLOUDLYNET_API_KEY` deleted; production 401s resolved | §22 |
| 2026-04 | Trial query cap | `feature/trial-signup-dev` | Redis-backed per-user limit (20 queries / 24 h) for trial users; `init_redis` lifecycle | §23 |
| 2026-05-11 | Per-query trace logging | `inference_agent` (PR #21, `1f8ecf7`) | `QueryTraceCollector` writes structured trace block (tools, RAG refs, token usage, timing) to docker stdout | §25 |
| 2026-05-12 | Inference Explanation Agent + page context | `inference_agent` (PR #21, `2809b29`) | `InferenceExplanationAgent` with `get_inference_report` + `compare_inference_models`; FE-provided `PageContext`; KPI tool removed (superseded) | §24 |
| 2026-05-12 | Output calibration + structured payloads | `copilot-cleaning-tuning-v2` (PR #20, `301270b`) | 3-tier response-length guidance in every prompt; typed `structured` discriminated union on `AgentResponse` for FE cards | §26 |
| 2026-05-13 | Guardrail Pipeline (Tanzim) | `feat/guardrail-pipeline` (PR #19) | `backend/app/guardrails/` module — PII redaction middleware + Safeguard-20B input classifier; `GUARDRAIL_ENABLED` + `GUARDRAIL_MODE` (`disabled` / `shadow` / `enforce`) kill switches; audit log to `conversation.guardrail_decision_log` | §27 |
| 2026-05-19 | Routing prompt disambiguation | `copilot-orchestrator` (PR #22) | Routing prompt rules to stop inference-keyword bleed; 4 contrastive examples; 35-query eval corpus (100% baseline); `tests/routing/test_routing.py` with 3 mocked test classes | §28 |
| 2026-05-19 | User-facing output rules | direct fix (PR #23) | `USER_OUTPUT_RULES` appended in `ReactiveAgent._get_agent()` — no internal RAG citations, no runnable commands, tool-failure vs error-content distinction, no internal IDs, plain language. Mandatory References section removed | §29 |
| 2026-07-30 | Orchestrator mypy fixes | `fix/orchestrator-mypy-errors` | Fixed all 10 mypy errors isolated to `orchestrator.py` (`--follow-imports=silent`); fixed a real bug where 3 both-agents-failed fallback sites silently dropped diagnostic error strings via `AgentMetadata`'s default `extra="ignore"` | §30 |

---

## 7. Integration Architecture (net_ai ↔ Copilot)

From `README.md` and `Agent.md`:

### Production Access Pattern
```
Frontend → maveric_platform_gateway → /v1/tenants/{tenant_id}/copilot/** → copilot backend /api/v1/tenants/{tenant_id}/**
```

### API Routing Contract (Updated Phase 11)
- **Tenant-scoped routes:** Copilot backend now natively serves `/api/v1/tenants/{tenant_id}/agents/**` and `/api/v1/tenants/{tenant_id}/sessions/**`
- **Non-tenant routes:** `/api/v1/users/**`, `/api/v1/knowledge/**`, `/api/v1/health` remain at the root level
- Gateway rewrites `/v1/tenants/{tenant_id}/copilot/**` → `/api/v1/tenants/{tenant_id}/**` (gateway must preserve the tenant_id segment)
- CORS is gateway-owned in platform mode (`ENABLE_CORS=false` on copilot backend)
- `tenant_id` is sourced **exclusively** from the URL path — no header fallback, no env var fallback

### Network Architecture (Consolidated — updated 2026-03-09)
- **All services** share a single `maveric` external Docker network (`docker network create maveric` required before first run)
- **Copilot backend** connects to shared postgres, redis, and minio — no separate copilot-specific infrastructure containers
- **Copilot databases** (`netai_copilot_dev`, `netai_copilot_test`) are isolated databases within shared postgres, owned by `netai_copilot` user
- **MCP server** routes through gateway (`http://gateway:8080`), not directly to copilot-backend

### Infrastructure (consolidated — single `docker-compose.yaml`)
| Service | Port | Description |
|---------|------|-------------|
| **Shared Infrastructure** | | |
| postgres | 5432 | Single pgvector:pg15 instance (platform `maveric` DB + copilot `netai_copilot_dev`/`_test` DBs) |
| redis | 6379 | Shared cache (Redis 7-alpine) |
| minio | 9000/9001 | Shared S3 object storage |
| pgadmin | 5050 | Database GUI (replaces previous separate Adminer for copilot) |
| mongo | 27017 | MongoDB (platform use) |
| zookeeper | — | Kafka coordination |
| kafka | 9092/29092 | Message broker |
| **Platform Apps** | | |
| gateway | 8080 | Maveric API gateway (proxies copilot routes) |
| bdt-engine | 8000 | Big Data Training engine |
| bdt-worker | — | Async BDT worker |
| rapp | 8001 | RAN APP engine |
| rapp-worker | — | Async rApp worker |
| smo-sim | 8002 | SMO Simulator |
| data-sim | 8003 | Data Simulator |
| **Copilot Apps** | | |
| copilot-backend | 8100 | FastAPI backend |
| copilot-mcp-server | 8082 | FastMCP SSE tools |

**Removed services** (no longer separate): `copilot-postgres`, `copilot-postgres-test`, `copilot-redis`, `copilot-minio`, `copilot-mlflow`, `copilot-adminer`

### Submodule Setup
- This repo is submoduled into `cloudlynet_ai` (the parent/backend repo)
- Everything runs from the parent repo's Docker Compose (single `docker-compose.yaml`)
- Parent repo Dockerfiles account for the submodule structure

### Health Checks
- Backend: `http://localhost:8100/health`
- MCP server: `http://localhost:8082/health`
- Gateway-routed: `http://localhost:8080/v1/tenants/{tenant_id}/copilot/health`

---

## 8. Current File Map

> Authoritative layout as of 2026-05-22. For attribution of who built what, see [`COPILOT_HISTORY.md` §3](./COPILOT_HISTORY.md#3-developer-contributions).

### Application code (`backend/app/`)

```
agents/
├── base.py                       # BaseAgent + AgentCapability StrEnum (REACTIVE, DEBUGGER, DATA_GENERATION, INFERENCE_EXPLANATION)
├── orchestrator.py               # run()/run_stream(); nodes per agent; auth_token + page_context threading
├── callbacks.py                  # QueryTraceCollector (AsyncCallbackHandler) — §25
├── schemas.py                    # AgentResponse + structured discriminated-union payload — §26
├── state.py                      # AgentState, ConversationState
├── reactive/
│   ├── agent.py                  # ReactiveAgent; USER_OUTPUT_RULES (§29); _build_structured (§26)
│   └── prompts.py                # Dynamic prompts (with/without tools); response-length tiers (§26)
├── debugger/
│   ├── agent.py                  # Inherits ReactiveAgent + tenant_id + auth_token + page_context
│   └── prompts.py                # 3-tier prompts (full / rag-only / no-tools)
├── data_generation/
│   ├── agent.py                  # Inherits ReactiveAgent; 8 MCP data-gen tools (guidance-only)
│   └── prompts.py                # 3-tier prompts
├── inference_explanation/        # §24
│   ├── agent.py                  # InferenceExplanationAgent
│   └── prompts.py                # 4-tier prompts (full / navigate / rag-only / no-tools)
├── routing/
│   ├── agent.py                  # Router (4 agents, fallback to reactive)
│   └── prompts.py                # Routing rules + disambiguation (§28)
├── generic/                      # Internal fallback only (not publicly listed)
└── offline_debugging/            # Internal only

rag/
├── embeddings.py                 # EmbeddingService singleton (all-MiniLM-L6-v2, 384-dim)
├── document_processor.py         # Markdown/code-aware chunking via tiktoken
├── retriever.py                  # PlatformKnowledgeRetriever — hybrid (vector + BM25 + RRF + concept expansion)
├── ingestion.py                  # KnowledgeIngestionService
├── contextualizer.py             # ChunkContextualizer — LLM-enriched chunk prefixes + metadata
├── tools.py                      # create_rag_search_tool()
└── reranker.py                   # RerankerService (cross-encoder; built, not enabled in main — see HISTORY §6)

mcp_server/
├── server.py                     # FastMCP SSE app (separate Docker service, port 8082)
├── config.py                     # MCPConfig (decoupled, MCP_* env vars only)
├── cloudlynet_client.py          # Async HTTP client; per-request Authorization: Bearer (§22)
├── platform_tools.py             # Tool factories — closures bind tenant_id + auth_token (§22)
└── schemas.py                    # MCP response models incl. InferenceReportResponse / InferenceCompareResponse (§24); old KpiAnalysisResponse removed in §24

guardrails/                       # §27 (PR #19, Tanzim)
├── config.py                     # GuardrailSettings, GuardrailMode (disabled/shadow/enforce), policy text + regex patterns
├── pii.py                        # PIIMiddleware stack — block (SSN, credit card) vs redact (api_key, email, phone, public IP)
├── safeguard.py                  # @before_agent Safeguard-20B classifier; logs to conversation.guardrail_decision_log
└── __init__.py                   # build_middleware_stack() entry point

models/
├── conversation.py               # Conversation models with tenant_id (§19) + guardrail_decision_log (§27)
└── knowledge.py                  # DocumentSource, Document, DocumentChunk ORM

schemas/
├── knowledge.py                  # Pydantic request/response
├── agent_query.py                # AgentQueryRequest + 6 SSE event models; context (PageContext) field (§24)
└── page_context.py               # PageContext model (§24)

services/
├── knowledge_service.py
├── session_service.py
├── health_service.py
└── agent_query_service.py        # access_token + page_context + create_message_stream

api/v1/
├── router.py                     # Dual routing: platform_router (/v1) + api_router (/api/v1) — see HISTORY §7
└── endpoints/
    ├── agent_query.py            # POST /query, PATCH /query, POST /query/stream; trial cap check
    ├── sessions.py               # tenant_id path param + RLS
    ├── knowledge.py              # 4 REST endpoints for KB ingestion/search
    ├── users.py
    └── health.py

core/
├── auth.py                       # CopilotUser (access_token, role fields)
├── config.py                     # Settings + GuardrailSettings co-exist
├── database.py                   # AsyncSessionLocal + set_rls_context (§19)
├── enums.py                      # AgentName StrEnum
├── redis.py                      # Shared async Redis client + init/close lifecycle (§23)
├── rate_limit.py                 # check_trial_query_limit (§23)
└── query_log.py                  # format_query_trace + emit (§25)

main.py                           # FastAPI app; init_redis/close_redis lifespan
```

### Tests (`backend/tests/`)

```
agents/
├── test_reactive_agent.py        # 28 baseline tests + TestUserOutputRules (6) + TestSystemPromptComposition (3) + TestMandatoryReferencesRemoved (4) — §29
├── test_debugger_agent.py        # 18 tests (incl. TestDebuggerTenantId 4)
├── test_data_generation_agent.py # Construction, tools, routing, orchestrator
└── test_inference_explanation_agent.py  # §24

rag/
├── test_document_processor.py    # 24 tests
└── test_retriever.py             # 5 tests

services/
└── test_tenant_isolation.py      # 9 tests: cross-tenant, cross-user, session creation, RLS context — §19

routing/                          # §28
├── conftest.py
└── test_routing.py               # TestRoutingAgentParsing / Fallback / Output — fully mocked

guardrails/                       # §27
├── test_config.py
├── test_safeguard.py
└── test_stack.py

test_mcp_tools.py                 # incl. TestFormatErrorLogs (12)
test_callbacks.py                 # QueryTraceCollector capture (§25)
test_database.py                  # incl. set_rls_context export
conftest.py
```

### Scripts (`backend/scripts/`)

```
ingest_knowledge_base.py          # RAG KB ingestion (contextualization always-on)
contextualize_chunks.py           # Backfill contextualization for existing chunks (see §10 + HISTORY §9)
eval_routing.py                   # Routing eval harness against 35-query corpus (§28)
rag_eval.py                       # Deterministic P@K / R@K / MRR — see §10 + HISTORY §9
hallucination_smoke.py            # Local smoke (PLANNED — not yet implemented; see §9)
test_rag.py                       # Manual test script
```

### Module-relative key paths
- `backend/Dockerfile` — Multi-stage build, CPU-only PyTorch, libgomp1, non-root appuser
- `backend/.env.example` — All env vars documented incl. GUARDRAIL_* (§27) and TOKEN_LOGGING_ENABLED (§25)
- `backend/conftest.py` — Pytest base config (formatting cleaned during guardrail PR merge)
- `backend/alembic/versions/7f2dc1ff03e2*.py` — Initial knowledge schema migration (fixed in Phase 7 of HISTORY)

---

## 9. Remaining Work

### Knowledge Data Ingestion (Not Done)
7 GitHub sources from `Debugger_Agent_Specification.md` need to be ingested:
1. `https://github.com/lf-connectivity/maveric/` (public)
2. `https://github.com/CloudlyIO/cloudlynet_ai/tree/main/design` (private)
3. `https://github.com/CloudlyIO/maveric_platform_bdt_engine/blob/main/README.md` (private)
4. `https://github.com/CloudlyIO/maveric_platform_data_sim/blob/main/README.md` (private)
5. `https://github.com/CloudlyIO/maveric_platform_gateway/blob/main/README.md` (private)
6. `https://github.com/CloudlyIO/maveric_platform_rapp/blob/main/README.md` (private)
7. `https://github.com/CloudlyIO/maveric_platform_smo_sim/blob/main/README.md` (private)

**Blocker:** 6 of 7 are private repos. `_fetch_content()` uses plain `httpx.get()` — needs GitHub token authentication to access private repos.

### KnowledgeService Delegation Inconsistency (Tech Debt)
`KnowledgeService.ingest_source()` (`app/services/knowledge_service.py`, Phase 9) reimplements the chunking/embedding/storing pipeline inline instead of delegating to `KnowledgeIngestionService` (`app/rag/ingestion.py`, Phase 4), which was the intended single source of truth. Both paths produce identical DB output, so this is duplication not a bug.

**Fix:** After `_fetch_content()` returns the raw text, replace the inline pipeline in `ingest_source()` with a call to `KnowledgeIngestionService.ingest_text()`.

**When to fix:** At the same time as adding GitHub token auth to `_fetch_content()` — both changes are in `knowledge_service.py` and address the same Phase 9 gaps.

### GitHub Token Auth for REST Ingestion Endpoint (Blocker)
`KnowledgeService._fetch_content()` uses plain `httpx.get()` with no authentication. 6 of 7 knowledge sources are private GitHub repos — the `POST /knowledge/sources/{id}/ingest` REST endpoint cannot fetch them until a GitHub token is added.

**Fix:** Add `Authorization: Bearer <GITHUB_TOKEN>` header to `_fetch_content()`, sourced from a new `GITHUB_TOKEN` env var in `Settings`.

**Workaround in use:** Previously `docker-compose.data-loaders.yml` ran `scripts/ingest_knowledge_base.py` as a one-shot service. That compose override file has been **removed** after infrastructure consolidation. The script can still be run manually via `docker exec` into the copilot-backend container, or locally. It reads from the local `knowledge_base/` directory (copied from local submodule checkouts) and calls `KnowledgeIngestionService.ingest_directory()` directly — bypassing the HTTP fetch entirely.

### Output-Side Hallucination Pipeline (Planned, Not Implemented)

The Hallucination Pipeline V1 ([../../claude_contexts/Hallucination_Pipeline_Implementation_Plan.md](../../claude_contexts/Hallucination_Pipeline_Implementation_Plan.md)) is a planned output-side safety layer (post-response verification: deterministic checks + LLM judge + corrective retry + soft refusal). **Not yet implemented.** The CI/eval set work is deferred to [../../claude_contexts/Hallucination_Pipeline_CI_Ticket.md](../../claude_contexts/Hallucination_Pipeline_CI_Ticket.md).

> **Disambiguation:** This is distinct from the **Guardrail Pipeline** (§27, PR #19) which is **input-side** (PII redaction + Safeguard-20B classifier on user queries before the agent runs). The Hallucination Pipeline targets agent **output** verification.

### Routing Eval Corpus — No CI Gate

The 35-query routing eval corpus and `scripts/eval_routing.py` (§28, PR #22) currently run manually. Accuracy regressions only caught if someone runs it before merging. CI integration is a follow-up sub-ticket.

### Cross-Provider Routing / Judge Model Comparison

Routing eval is single-model only (`llama-3.1-8b-instant`); no cross-model consistency check. If the routing accuracy plateaus, a cross-provider eval pass would help calibrate.

### Pre-Production Limitations

#### `CLOUDLYNET_API_BASE_URL` not set per environment
`docker-compose.yaml` now defaults to `http://gateway:8080` but `.env` in the submodule still references old hostnames. Must be a proper per-environment variable (not hardcoded) before non-Docker deployment. See §18 for the fix applied during consolidation.

#### No guard for empty `tenant_id` in MCP tool factories
If `tenant_id` is `None` or `""`, the gateway URL becomes `/v1/tenants//baselines/logs/errors` — a malformed path that returns a silent 404. Should raise a clear error at the factory or tool level instead. (Note: with URL-path routing, FastAPI enforces presence of `tenant_id` in the URL, but the value could still be an invalid UUID.)

#### Demo-user fallback in `get_current_user`
Any request without a bearer token becomes an unrestricted demo user regardless of `APP_ENV`. Should be gated on `APP_ENV == "development"` and return 401 otherwise — flagged during the trial-cap-bypass investigation in §18.

### Recently Resolved (kept for traceability)

- ~~**Streaming path missing `auth_token`**~~ — RESOLVED in §24's commit (`2809b29`); `run_stream()` and `_create_agent_for_streaming()` now thread `auth_token` + `page_context` end-to-end.
- ~~**`CLOUDLYNET_TENANT_ID` env var bypasses JWT tenant boundary**~~ — RESOLVED in Phase 11 (`f5798fa`/`533489f`/`6ce5583`); tenant_id is URL-path-only.
- ~~**Parent Repo Integration**~~ — RESOLVED (see [HISTORY §7](./COPILOT_HISTORY.md#7-infrastructure-consolidation-2026-03-09)); single `docker-compose.yaml`, dual router verified.
- ~~**Lint + Test Coverage for Phase 10 Commit**~~ — RESOLVED in Phase 11 (`dfc35b1`, `3abd2b8`).
- ~~**Mandatory References section appended after every reactive agent response**~~ — RESOLVED in §29 (PR #23); replaced by `USER_OUTPUT_RULES` block at single call site.
- ~~**Inference-keyword bleed in routing (RSRP, SINR, guardrail → inference_explanation_agent on definition queries)**~~ — RESOLVED in §28 (PR #22).

---

## 10. RAG Pipeline & Knowledge Base — Current State + Known Issues

### Current RAG Pipeline

- **Embedding model**: `all-MiniLM-L6-v2` (384-dim, sentence-transformers)
- **Vector store**: pgvector, cosine similarity
- **Retrieval**: Hybrid (vector + BM25) with RRF fusion (k=60 dampening), concept expansion via ConceptIndex (one-hop cross-document linking)
- **Config**: `RAG_TOP_K=5`, `RAG_SIMILARITY_THRESHOLD=0.25` (defaults; see Known Issues A for the tuned values used in compose)
- **Chunking**: 512 tokens, 50-token overlap, tiktoken `cl100k_base`. Markdown-aware (splits by headers); Python-aware (splits by functions/classes)
- **Contextualization**: always-on at ingestion. `ChunkContextualizer` (Groq `openai/gpt-oss-120b`) adds `context_prefix` + `topics` + `entities` + `related_concepts` to chunk metadata; embedding is computed from contextualized text
- **Reranker**: cross-encoder `ms-marco-MiniLM-L-6-v2` built but **not enabled in main** due to 8–12 s CPU latency; see [HISTORY §9](./COPILOT_HISTORY.md#9-rag-improvement-research--evaluation-evolution-2026-03) for benchmarked alternatives
- **Key files**: `rag/retriever.py`, `rag/embeddings.py`, `rag/document_processor.py`, `rag/ingestion.py`, `rag/contextualizer.py`, `rag/reranker.py`, `rag/tools.py`
- **Design research doc**: `claude_contexts/RAG_DESIGN_RESEARCH.md` (local-only; not in git)

### Knowledge Base Status

Ingested via `scripts/ingest_knowledge_base.py` (run manually via `docker exec`). Current count: **491 chunks, 31 documents, 7 sources** (post-consolidation, March 2026).

| Source | Docs | Chunks | Avg tokens/chunk |
|--------|------|--------|-----------------|
| bdt_engine | 4 | 17 | 206 |
| data_sim | 4 | 53 | 105 |
| gateway | 5 | 31 | 230 |
| maveric | 2 | 45 | 141 |
| platform_design | 5 | 119 | 164 |
| rapp | 5 | 50 | 197 |
| smo_sim | 6 | 190 | 111 |

### Known Retrieval Issues

#### A. Similarity Threshold Sensitivity
`RAG_SIMILARITY_THRESHOLD=0.5` (original default) was too strict for general-purpose queries. `all-MiniLM-L6-v2` does semantic similarity, not keyword matching — acronyms (BDT, SMO, MRO) score low against mixed-content chunks.
- **Applied fix:** Threshold lowered to `0.15` via `RAG_SIMILARITY_THRESHOLD` env var in `docker-compose.apps.yml`. Value can be overridden per-deployment via `COPILOT_RAG_SIMILARITY_THRESHOLD`.
- **RAG_TOP_K** increased to 8 (was 5).

#### B. Chunk Dilution — rApp Types (LB, ES, MRO, CCO)
`rapp/radplib/README.md` chunk 0 describes all four rApp types in a single chunk. The resulting embedding is a blended vector of ES + LB + MRO + CCO, so individual rApp type queries score ~0.18–0.22 against it.
- **Root fix needed:** Add dedicated concept files — one per rApp type — in `knowledge_base/rapp/` (e.g. `mro.md`, `lb.md`, `es.md`, `cco.md`). Re-run indexer after.

#### C. Content Gap — BDT Engine
No document in the knowledge base defines what BDT is conceptually. All BDT chunks are API specs, DB schemas, and metrics — no "what is BDT, what does it do, how does it relate to rApps" content.
- **Root fix needed:** Create `knowledge_base/bdt_engine/concept.md` explaining BDT's purpose, role in the Maveric / CloudlyNet ecosystem, and relationship to training/inference. Re-run indexer after.

#### D. Content Gap — SMO Simulator
`smo_sim/README.md` starts with only the repo name (`# maveric_platform_smo_sim`) and jumps to project layout and DB config. No conceptual intro. 57 of 190 chunks contain "SMO" but none explain what the SMO Simulator is.
- **Root fix needed:** Create `knowledge_base/smo_sim/concept.md` explaining what the SMO Simulator does. Re-run indexer after.

#### E. Artifact Text in HLD.md / LLD.md
Both `design/HLD.md` and `design/LLD.md` (and their `knowledge_base/platform_design/` copies) began with ChatGPT / Claude response preambles that were accidentally saved into the documents. These were ingested as garbage chunk 0 entries.
- **Applied fix (2026-02-19):** Removed artifact lines from all four files. Re-ingest required to purge from DB.

### RAG Agent Behaviour Rules (Applied in Prompts)

| Change | File | Description |
|--------|------|-------------|
| Mandatory RAG first | `reactive/prompts.py` | Prompt mandates `rag_search` BEFORE answering platform questions |
| Retry on failure | `reactive/prompts.py` | 3-attempt escalation: specific → noun-only → bare acronym |
| Multi-keyword decomposition | `reactive/prompts.py` | Agent instructed to run separate searches per topic in multi-topic queries |
| App logging | `main.py` | `logging.basicConfig()` added so RAG/agent logs appear in Docker stdout |
| Tool schema hardened | `rag/tools.py` | Removed `top_k` from `rag_search` schema; only `query: str` accepted |
| Graceful 400 handling | `reactive/agent.py` | Groq tool schema mismatch returns user-friendly message instead of 500 |

> The previously-mandatory References section in every response was removed by §29 (PR #23). RAG citations now never reach the user — see §29's `USER_OUTPUT_RULES`.

### Knowledge Base Quality Issues

KB docs are treated as the **definitive source of truth** for RAG eval, but discrepancies with actual system behaviour have been identified:

- **Port inconsistency:** rApp README OpenAPI spec shows `localhost:8004` while the actual rApp worker runs on port 8001 per Docker.
- **`bdt_engine/README.md`** lists `train_test_split` and `random_seed` as training hyperparameters in the OpenAPI schema, but the actual BDT Engine does not implement these.
- **`rapp/README.md`** describes a "CCO inference reuse" optimization with `input_signature` hash and `allow_reoptimization` flag (Q16) — does not reflect actual behaviour.
- **Baseline relationship under-documented:** docs don't clearly explain that a baseline is a composite of (topology CSV, UE training dataset CSV, config CSV), that BDT trains using a `baseline_id`, and that UE datasets link to baselines. Context is spread across `smo_sim/README.md`, `data_sim/README.md`, `rapp/README.md` without a single authoritative explanation.
- **R1 delivery doc** uses "Phase 1/2/3" without defining these as O-RAN R1 spec implementation stages (Phase 1 = Service Management APIs, Phase 2 = Data Management APIs, Phase 3 = RAN OAM Services).

Fixing KB docs improves both eval accuracy and end-user answer quality simultaneously.

### Groq Rate Limiting

Groq free-tier rate limits cause 429 retries during multi-search queries (observed 15-second waits, total response time up to 39 s). With the 3-attempt RAG retry strategy each query can make up to 8 Groq API calls. Consider upgrading the Groq tier or switching providers for production.

### Open Work

- [ ] **Option B end-to-end API eval** — covers the full pipeline including agent reasoning, not just retrieval. The deterministic Option A (P@K / R@K / MRR via `scripts/rag_eval.py`) is complete; see [HISTORY §9](./COPILOT_HISTORY.md#9-rag-improvement-research--evaluation-evolution-2026-03) for the eval evolution and benchmarked numbers.
- [ ] **Hypothetical question generation** for contextual retrieval — planned (`claude_contexts/HYPOTHETICAL_QUESTIONS_PLAN.md`).
- [ ] **Reranker latency reduction** — GPU inference or smaller candidate pool to bring the cross-encoder under ~200 ms; not enabled in main today.
- [ ] **Post-consolidation re-benchmark** — establish current 491-chunk KB as the new baseline; investigate the 12-chunk content diff against the March 5 snapshot.

---

## 12. Issue Tracker Categories (GitHub Project)

Four parent issue categories on the GitHub Project board. New issues should land in the category whose scope best matches — see descriptions, heuristics, and tie-breakers below.

### Category Descriptions

#### 1. Model & RAG
**Scope:** Anything about the LLM layer and how it's grounded in knowledge — which model we use, how we prompt/cache it, what it retrieves, and the KB content itself.

**File here if the issue is about:**
- Choosing, benchmarking, or swapping the LLM backend (Groq, Anthropic, OpenAI, HF, etc.)
- Prompt caching, response caching, embedding cache
- Models with extra capabilities (online search, vision, long-context)
- Retrieval mechanics: embeddings, rerankers, hybrid/BM25, similarity thresholds, contextualizers
- Knowledge-base content: missing docs, stale docs, coverage gaps (MRO, LB, ES, CCO, Maveric topics)

**Heuristic:** *"Would fixing this change the answer the LLM produces, not the route the request takes or the loop the agent runs?"* → Model & RAG.

#### 2. API & Integration
**Scope:** The request path between frontend, gateway, copilot, and platform services. How calls are shaped, authenticated, scoped, and transported — not what happens inside them.

**File here if the issue is about:**
- New/changed endpoints, request/response shapes, OpenAPI spec
- Tenant scoping, RBAC, auth enforcement on an endpoint (JWT, Cognito, dev-bypass)
- Streaming / SSE / transport-layer plumbing between services
- Frontend ↔ backend contract mismatches (wrong tenant_id, missing headers, CORS)
- Gateway routing, forwarding, proxy behaviour

**Heuristic:** *"Is this about a request crossing a service boundary?"* → API & Integration.

#### 3. Agent & Tool
**Scope:** The agents themselves (reactive, debugger, future agents), their orchestration, tools, prompts, and output quality. Everything "inside" a copilot turn.

**File here if the issue is about:**
- Orchestrator routing (picking the right agent/tool)
- Tool additions, MCP wiring, tool-choice behaviour
- Prompt engineering, response formatting (markdown/JSON verbosity)
- Guardrails, hallucination checks, response-quality pipelines
- Agent bugs, crashes, wrong-answer failure modes
- New agents (Inference/Explanation, Debugger v2, etc.)

**Heuristic:** *"Would this change what the copilot does during a single query turn?"* → Agent & Tool.

#### 4. Infra & Provider
**Scope:** The runtime and external services copilot depends on. Ops-shaped work — not feature work.

**File here if the issue is about:**
- Docker, docker-compose, networks, volumes, env vars
- Databases (pgvector, Redis, MinIO) — setup, migrations infra, tuning
- Provider quotas and rate limits (Groq 429s, HF token caps, Cognito throttling)
- CI/CD, deployment scripts, compose lifecycle tooling
- Secrets handling, credential rotation, env bootstrapping

**Heuristic:** *"Would this issue still exist if the copilot codebase had zero agents and zero RAG?"* → Infra & Provider.

### Tie-breakers (when an issue spans two categories)
- **Model & RAG vs. Agent & Tool** → "answer content" vs. "agent loop". Hallucination *detection logic* lives in Agent & Tool; hallucination *reduction via better retrieval* lives in Model & RAG.
- **Infra & Provider vs. Model & RAG** → provider *quota/ops* = Infra; provider *capability/choice* = Model.
- **API & Integration vs. Agent & Tool** → endpoint *shape* = API; what the endpoint handler's agent *does* = Agent & Tool.

---

## 18. Troubleshooting & Operational Notes (2026-03-11)

### Shell Script Line Endings (CRLF → LF)

**Problem:** `design/db/init_copilot_databases.sh` saved with Windows line endings (CRLF) causes:
```
/usr/bin/env: 'bash\r': No such file or directory
```
This aborts the entire postgres entrypoint — `20-maveric-schemas.sql` and `30-init-copilot.sql` never run, leaving both maveric and copilot DBs empty.

**Fix:** Ensure `init_copilot_databases.sh` uses LF line endings (not CRLF). In VS Code: bottom status bar → click "CRLF" → select "LF" → save.

**Prevention:** Add to `.gitattributes`:
```
*.sh text eol=lf
```

### Docker Volume Persistence

`docker-entrypoint-initdb.d/` scripts only run when the pgdata volume is **empty** (first-time init). If the volume exists from a previous (failed or partial) init, docker skips all init scripts silently. Log line to watch for:
```
PostgreSQL Database directory appears to contain a database; Skipping initialization
```
**Fix:** `docker compose down -v` to remove named volumes, then `up` again.

### Gateway Force-Recreate After pgAdmin Setup

After setting up pgAdmin (or any infrastructure change that touches the network/postgres), force-recreate the gateway to pick up fresh connections:
```bash
docker compose -f docker-compose.infra.yml -f docker-compose.apps.yml up -d --force-recreate gateway
```

### asyncpg SET Parameter Bug

PostgreSQL's `SET` command does not accept parameterized values. asyncpg sends `SET app.current_tenant_id = $1` as a prepared statement, which Postgres rejects. Must use validated string interpolation:
```python
_SAFE_ID = re.compile(r"^[a-zA-Z0-9_\-]+$")
await db.execute(text(f"SET app.current_tenant_id = '{tenant_id}'"))
```
See `app/core/database.py` → `set_rls_context()` for the implementation.

### GROQ_API_KEY Silent Failure During Ingestion

**Symptom:** Knowledge base ingestion completes successfully (575 chunks, all with embeddings), but `metadata` is `{}` on every chunk — no `context_prefix`, `topics`, `entities`, or `related_concepts`.

**Root cause:** `docker compose up` does NOT update environment variables on an existing container, even if `.env` changed. The `GROQ_API_KEY` falls back to the placeholder `your-groq-api-key-here` from the compose default. The `ChunkContextualizer` silently catches LLM errors and returns empty metadata.

**Fix:**
1. Ensure `GROQ_API_KEY=gsk_...` is in the root `.env`
2. Recreate the container: `docker compose -f docker-compose.infra.yml -f docker-compose.apps.yml up -d --force-recreate copilot-backend`
3. Re-run ingestion or use `scripts/contextualize_chunks.py` to backfill metadata on existing chunks

**Prevention:** Added startup warnings in `app/rag/contextualizer.py` (logs WARNING on init) and `scripts/ingest_knowledge_base.py` (prints to stderr before ingestion starts) when the API key is missing or set to a placeholder value.

**General rule:** Any `.env` change requires `--force-recreate` on affected containers. `docker compose up` alone reuses existing containers with stale env vars.

### CLOUDLYNET_API_BASE_URL Missing from copilot-backend (2026-03-12)


**Root cause:** During infra consolidation, `CLOUDLYNET_API_BASE_URL` was never added to the `copilot-backend` service environment in `docker-compose.yaml`. Pre-consolidation, copilot had its own compose file that set this. The MCP server container had `MCP_CLOUDLYNET_BASE_URL` (different env var prefix), but the backend container — which runs the debugger agent — did not.

**Fix:** Added to `copilot-backend` environment in `docker-compose.yaml`:
```yaml
CLOUDLYNET_API_BASE_URL: ${CLOUDLYNET_API_BASE_URL:-http://gateway:8080}
```
Then `docker compose up -d --force-recreate copilot-backend`.

**Note:** Two code paths, two env vars:
- `CLOUDLYNET_API_BASE_URL` — used by backend (`orchestrator.py` → `CloudlyNetAPIClient`)
- `MCP_CLOUDLYNET_BASE_URL` — used by standalone MCP server (`mcp_server/config.py`)

**Verified:** All 3 debugger tools working after fix:
- `rag_search` → hybrid search returning results
- `get_platform_error_logs` → `GET gateway:8080/.../logs/errors` → 200 OK
- `compare_rapp_policies` → `POST gateway:8080/.../rapps/compare/infer` → 500 (expected, no trained rApps)
- `analyze_rapp_kpis` → `POST gateway:8080/.../rapps/cco/models/model_placeholder/infer` → 404 (expected, no trained models)

### Gateway `DEV_TENANT_ROLE` Caused Trial Query Cap Bypass (2026-04-21)

**Symptom:** Trial query cap ([rate_limit.py](../submodule/cloudlynet_ai_copilot/backend/app/core/rate_limit.py)) never tripped in local dev even after many requests. Copilot saw no `Authorization` header on incoming requests.

**Root cause:** `submodule/maveric_platform_gateway/.env` had `DEV_TENANT_ROLE=trial_user` with `DEV_BYPASS_JWT=true`. In dev-bypass mode the gateway synthesises tenant/role context locally and does not require (or forward) a real Cognito JWT, so copilot receives no `Authorization: Bearer …` header. Copilot's [auth.py:67-77](../submodule/cloudlynet_ai_copilot/backend/app/core/auth.py#L67-L77) then falls back to the demo user with `role=None`, and [rate_limit.py:25](../submodule/cloudlynet_ai_copilot/backend/app/core/rate_limit.py#L25) skips the cap because `role != "trial_user"`.

**Fix:** Changed gateway `.env` to `DEV_TENANT_ROLE=tenant_admin` (previous `trial_user` value left commented for quick toggle). This restores the standard admin dev path; the trial-user dev path remains available by flipping the comment.

**Follow-up to consider:** the demo-user fallback in `get_current_user` is a genuine bypass surface — any request without a bearer token becomes an unrestricted demo user regardless of `APP_ENV`. Harden by gating the fallback on `APP_ENV == "development"` and returning 401 otherwise.

---

## 19. Tenant Isolation & PostgreSQL RLS

Tenant + user isolation enforced at two layers — application WHERE clauses (`tenant_id + user_id`) and PostgreSQL RLS context vars set via `set_rls_context()`. Cross-tenant access returns 404 (not 403) to prevent tenant enumeration.

```
Layer 1: Application — WHERE clause: tenant_id + user_id  → 404 for cross-tenant access
Layer 2: Database   — SET app.current_tenant_id → RLS policies  → fail-closed safety net
```

**Key files:**
- `app/core/database.py` — `set_rls_context()`, reset in `get_db()` `finally` block (prevents cross-request leakage on pooled connections)
- `app/models/conversation.py` — `tenant_id` (NOT NULL, indexed) on all 3 conversation models
- `app/api/v1/endpoints/{agent_query,sessions}.py` — call `set_rls_context()` before service construction
- `design/copilot/copilot_schemas.sql`, `design/db/init_copilot_rls.sql` — schema + RLS policies

**Schema mgmt:** column renames applied manually via pgAdmin — no Alembic migration. **Tests:** `tests/services/test_tenant_isolation.py` (9 tests).

**Implementation log:** [HISTORY §10.1](./COPILOT_HISTORY.md#101-tenant-isolation--postgresql-rls).

---

## 20. Data Generation Agent

`DataGenerationAgent` — guidance-only specialist for baseline topology + UE dataset generation. Inherits from `ReactiveAgent`. Emits API call templates rather than executing mutations ("You are a guidance-only agent — you must NEVER perform mutations.").

**Tools (8 MCP + 1 RAG, when api_client + auth_token provided):**

| Tool | Type | Purpose |
|------|------|---------|
| `validate_baseline_params` / `validate_dataset_params` | in-memory | Parameter validation |
| `recommend_baseline_config` / `recommend_dataset_config` | in-memory | Config recommendation |
| `query_existing_baselines` | Gateway | Tenant's existing baselines |
| `compare_datasets` | Gateway | UE dataset diff |
| `estimate_impact` | in-memory | Performance estimate |
| `get_generation_docs` | in-memory | Inline docs |
| `rag_search` | pgvector | Supplementary (inherited) |

**Key files:** `app/agents/data_generation/{agent,prompts}.py`, orchestrator `data_generation_node()`. **Tests:** `tests/agents/test_data_generation_agent.py`.

**Implementation log:** [HISTORY §10.2](./COPILOT_HISTORY.md#102-data-generation-agent).

---

## 21. SSE Streaming for Agent Queries

`POST /agents/query/stream` — Server-Sent Events streaming with `EventSourceResponse`. Eliminates 5–15 s silent waits on complex queries. Sync `POST /agents/query` unchanged. `generic_agent` removed from public routing as part of this work (still exists as an internal orchestrator node).

**Event protocol (`app/schemas/agent_query.py`):**

| Event | Payload |
|-------|---------|
| `stream_start` | `message_id`, `agent_id`, `version_number` |
| `tool_call` | `tool_name`, `tool_input` |
| `tool_result` | `tool_call_id`, `output` (truncated to 500 chars) |
| `token` | `content` |
| `stream_end` | `message_id`, `version_id`, `finish_reason` |
| `error` | `error_code`, `message` |

**Architecture:** agent instantiated directly via `_create_agent_for_streaming()` (no outer StateGraph streaming); `AsyncSessionLocal` wraps the whole stream so RAG tool calls keep an active DB session; pre-stream HTTP error checks (429 / 404 / 401) run before SSE headers are sent so they surface as regular HTTP errors rather than truncated streams.

**Key files:** `app/api/v1/endpoints/agent_query.py` (`POST /query/stream`), `app/services/agent_query_service.py` (`create_message_stream()`, `validate_session()`), `app/agents/orchestrator.py` (`run_stream()`, `_create_agent_for_streaming()`).

**Implementation log:** [HISTORY §10.3](./COPILOT_HISTORY.md#103-sse-streaming-for-agent-queries).

---

## 22. JWT Forwarding for MCP Tool Calls

The authenticated user's Cognito JWT is threaded end-to-end from every inbound copilot request to every outbound platform-gateway call. `CLOUDLYNET_API_KEY` removed entirely — gateway requires `Authorization: Bearer <token>`, not an API key header.

**Token threading path:**
```
get_current_user() → CopilotUser.access_token
   → AgentQueryService(access_token=…)
   → orchestrator.run(auth_token=…) → state metadata["auth_token"]
   → debugger_node / data_generation_node / inference_explanation_node → Agent(auth_token=…)
   → tool factory closure (LLM-invisible)
   → CloudlyNetAPIClient._request → Authorization: Bearer <token>
```

**Key files:**
- `app/core/auth.py` — `CopilotUser.access_token` populated from inbound Bearer header
- `app/mcp_server/cloudlynet_client.py` — per-request Bearer injection via httpx
- `app/mcp_server/platform_tools.py` — `auth_token` captured in tool factory closures (LLM never sees it)
- `app/agents/{debugger,data_generation,inference_explanation}/agent.py` — forward `auth_token` to factories

**Implementation log:** [HISTORY §10.4](./COPILOT_HISTORY.md#104-jwt-forwarding-for-mcp-tool-calls).

---

## 23. Trial User Query Cap

Trial users (Cognito JWT `custom:role=trial_user` on the trial tenant) capped at 20 queries / 24 h via Redis atomic `INCR` + TTL auto-reset. Full subscribers unaffected. 429 returned before agent execution — no LLM tokens or platform API calls burned on rejected queries.

```
INCR copilot:trial_cap:{user_id}   (Redis key, TTL = 24h window)
├── role != "trial_user" → SKIP (not a trial user)
├── tenant_id != TRIAL_TENANT_ID → SKIP (not on the trial tenant)
├── count == 1 → SET TTL
├── count ≤ cap → PASS
└── count > cap → HTTP 429
```

**Config (env):** `TRIAL_TENANT_ID`, `TRIAL_QUERY_CAP` (default `20`), `TRIAL_QUERY_CAP_WINDOW_SECONDS` (default `86400`).

**Key files:** `app/core/redis.py` (shared async client + `init_redis` / `close_redis` lifecycle), `app/core/rate_limit.py` (`check_trial_query_limit()`), `app/api/v1/endpoints/agent_query.py` (cap check on `POST` + `PATCH /query`), `app/main.py` (Redis lifespan hooks).

**Dev gotcha:** `DEV_BYPASS_JWT=true` + `DEV_TENANT_ROLE=trial_user` causes copilot to receive no Authorization header → demo-user fallback → `role=None` → cap never trips. See §18.

**Implementation log:** [HISTORY §10.5](./COPILOT_HISTORY.md#105-trial-user-query-cap).

---

## 24. Inference Explanation Agent + Page Context

`InferenceExplanationAgent` — explains completed rApp inference results from the CloudlyNet Recommendation Review (single model) and Compare Outcomes (two models, day-scope) pages. Strict guardrails: no math, every claim cites a value, no rollout decisions. Supersedes the previous `analyze_rapp_kpis` tool (see [HISTORY §5](./COPILOT_HISTORY.md#5-kpi-analysis-mcp-tool-2026-03-05-implemented-2026-03-16)).

**Two MCP tools — page-bound (only the active page's tool is registered):**

| Tool | LLM-visible params | Closure-bound | Endpoint |
|------|---------------------|---------------|----------|
| `get_inference_report` | `scope`, `tick`, `run_id` (override) | `tenant_id`, `auth_token`, `page_context` UUIDs | `GET /v1/tenants/{t}/rapps/{r}/models/{m}/infer/{run_id}` |
| `compare_inference_models` | none | All compare model IDs + shared `baseline_id` / `bdt_id` / `ue_dataset_id` / `day` | `POST /v1/tenants/{t}/rapps/compare/infer` |

Both include in-tool deterministic layers (threshold pass/fail, worst-hour scan, hotspot / congested cell derivation, side-by-side guardrail compliance) so the LLM never does the math.

**Page context (`app/schemas/page_context.py`):** `PageContext` carries `page_type` (`recommendation_review` / `compare_outcomes` / `other`), populated identifiers (`run_id` for Recommendation Review; compare model IDs for Compare Outcomes), plus `page_name` and `filters`. FE only populates UUIDs when the matching report is **actively rendered on screen** — their presence is the "report visible" signal. Selection changes and page unmount clear the identifiers.

**Resolution order for `get_inference_report`:** explicit user `run_id` → `page_context.run_id` → structured refusal with chat-context recovery hint. No fallback to `POST /infer` without a `run_id`.

**Key files:** `app/agents/inference_explanation/{agent,prompts}.py`, `app/schemas/page_context.py`, `app/mcp_server/cloudlynet_client.py` (`get_inference_run`, `run_inference_report`, `compare_models` with `day` param), `app/mcp_server/platform_tools.py` (`create_inference_report_tool`, `create_inference_compare_tool`).

**Known limitations:**
- **MRO unsupported** — returns structured `mro_not_supported` refusal when `rapp_id == "mro"`. Needs MRO formatter branch + threshold dictionary + prompt section.
- **`knowledge_base/inference/` is empty** — RAG calls for inference-specific KPI docs return zero results until a doc lands and the indexer is re-run.
- **No mid-stream page-state detection** — clicking Run Review while a response is mid-stream uses the snapshot taken at request time.

**Implementation log:** [HISTORY §10.6](./COPILOT_HISTORY.md#106-inference-explanation-agent--page-context).

---

## 25. Per-Query Trace Logging

`QueryTraceCollector` (`AsyncCallbackHandler`) emits a structured trace block per agent invocation to docker stdout — tool calls with timing / outcome, RAG document refs, LLM token usage (per-call + per-session totals), overall query timing. Wired on both sync (`ReactiveAgent.invoke`) and streaming (`orchestrator.run_stream`) paths.

**Trace block format (one per query, end-of-turn):**

```
==> COPILOT QUERY TRACE [<iso-timestamp>] ==================================
    session       <uuid>
    message       <uuid>
    tenant        <tenant>
    user          <user>
    user_query    <truncated to 200 chars>
    page_context  page=… name=… rapp=… day=… run_id=…   (UUIDs shortened to 8 chars)
    routed_agent  <agent_name>
    tools         [1] <name>  <ms>  ok/err  <args>
                  [2] …
    rag_refs      [1] <path>  chunk=<id8>  score=<f>
    tokens        prompt=… completion=… total=… session_total=…
    duration      <ms>
    status        ok/error
<== END QUERY TRACE =================================================================
```

**Config:** `TOKEN_LOGGING_ENABLED=true` (Pydantic Settings flag). Disable in prod via env. Dedicated logger `netai_copilot.query_trace` with `propagate=False` so traces print at INFO regardless of root `LOG_LEVEL` and don't double-print.

**Key files:** `app/agents/callbacks.py` (`QueryTraceCollector`, module-level `_session_token_totals` in-memory dict), `app/core/query_log.py` (`format_query_trace`, `emit`, `is_enabled`), `app/rag/retriever.py` (`| Chunk: <id8>` in result headers for correlation).

**Tail in dev:** `docker logs -f copilot_backend | grep -A 14 "COPILOT QUERY TRACE"`.

**Known limitations:** dev-grade only — in-memory token totals reset on backend restart; no DB persistence; no API surface; `chunk_id` is an 8-char UUID prefix.

**Implementation log:** [HISTORY §10.7](./COPILOT_HISTORY.md#107-per-query-trace-logging).

---

## 26. Response Length Calibration + Structured Output Payloads

Two coupled output behaviours, both inherited by every subclass of `ReactiveAgent`.

**Response length calibration** — `## Response Length` block in every prompt variant:

| Query type | Length target |
|---|---|
| Factual / definition (*"what is MRO?"*) | 1–3 sentences, no headings |
| How-to / explanation (*"how does BDT work?"*) | 1–3 short sections, ≤300 words |
| Diagnostic / comparison / analysis (*"why is latency high?"*, *"compare X vs Y"*) | Full sectioned report with headings |

Data-generation gets a slight variant (catalog-status questions get a short table; recommendations ≤400 words). Inference agent (§24) inherits automatically.

**Structured payloads** — `AgentResponse.structured: StructuredPayload | None` (Pydantic-validated discriminated union):

| Label | Source tool(s) | FE renderer |
|---|---|---|
| `rapp_comparison` | `compare_rapp_policies` (debugger) | policy diff card |
| `dataset_comparison` | `compare_datasets` (data_generation) | stat delta table |
| `validation` | `validate_baseline_params`, `validate_dataset_params` | VALID / INVALID + error list |
| `baseline_list` | `query_existing_baselines` | baseline catalog card |

Tool-name inference (not query regex) selects the label; malformed tool output returns `None` (markdown content is always valid regardless of structured output success).

**Key files:** `app/agents/schemas.py` (`StructuredLabel`, 4 typed payloads, `LABEL_PAYLOAD_MAP`, extended `AgentResponse`), `app/agents/reactive/agent.py` (`_LABEL_CONFIG`, `_TOOL_LABEL_MAP`, `_build_structured()`), all `*/prompts.py` (response-length + structured-data blocks).

**Note:** `get_inference_report` / `compare_inference_models` are **not** in `_TOOL_LABEL_MAP` — inference responses are markdown-only today. Adding `inference_report` / `inference_comparison` labels is a follow-up if/when the FE wants typed cards for inference output.

**Implementation log:** [HISTORY §10.8](./COPILOT_HISTORY.md#108-response-length-calibration--structured-output-payloads).

---

## 27. Guardrail Pipeline (Input Safety)

Input-side safety pipeline that intercepts user queries before any agent runs. PII redaction (regex) → Safeguard-20B classification (`@before_agent` hook). **Distinct from the planned output-side hallucination pipeline** (still planned — see §9).

```
User input
    → PII layer  (CRITICAL block: SSN, credit card | MEDIUM redact: api_key, email, phone, public IP)
    → Safeguard layer (Groq openai/gpt-oss-safeguard-20b, @before_agent)
        ├── violation=0 → pass through silently
        └── violation=1 → short-circuit with BLOCK_MESSAGE (rationale logged, not user-facing)
    → Agent runs as normal
```

**Config (env):**

| Setting | Default | Purpose |
|---------|---------|---------|
| `GUARDRAIL_ENABLED` | `true` | Master kill switch — `false` returns `[]` from `build_middleware_stack()` |
| `GUARDRAIL_MODE` | `shadow` | `disabled` / `shadow` (log only) / `enforce` (block) |
| `GUARDRAIL_SAFEGUARD_MODEL` | `openai/gpt-oss-safeguard-20b` | Groq model ID |
| `GUARDRAIL_SAFEGUARD_TIMEOUT_S` | `5.0` | Per-call timeout |
| `GUARDRAIL_FAIL_OPEN` | `true` | On Groq error or timeout, allow the query through |
| `GUARDRAIL_PII_INPUT_ENABLED` | `true` | Toggle PII layer only |
| `GUARDRAIL_SAFEGUARD_INPUT_ENABLED` | `true` | Toggle Safeguard layer only |

**Audit log:** every decision (safe or violation) → `conversation.guardrail_decision_log` (sha256 query hash, verdict, category, rationale, mode, model, timing). Logging failures never raise.

**Wiring:** the reactive agent is the single integration point — `_get_agent()` calls `create_agent(..., middleware=build_middleware_stack())`. All subclasses (`DebuggerAgent`, `DataGenerationAgent`, `InferenceExplanationAgent`) inherit the guardrails. `generic/agent.py` and `offline_debugging/agent.py` are **not** wired — internal fallbacks only.

**Key files:** `app/guardrails/{config,pii,safeguard,__init__}.py`. **Tests:** `tests/guardrails/{test_config,test_safeguard,test_stack}.py`.

**Known limitations:** input-only scope; single model family (Safeguard-20B only — cross-provider judge is a candidate if accuracy plateaus); `shadow` mode by default in prod — flip to `enforce` only after the audit log validates precision.

**Implementation log:** [HISTORY §10.9](./COPILOT_HISTORY.md#109-guardrail-pipeline-input-safety).

---

## 28. Routing Prompt Disambiguation

Routing prompt rules + eval harness that prevent inference-keyword bleed and ambiguity between agents. Two real misroutes (`RSRP` and `guardrail` definition queries hitting `inference_explanation_agent`) drove the fix; the eval corpus exists so future regressions don't slip in.

**Three rule additions in `app/agents/routing/prompts.py`:**

1. **Inference-keyword qualifier** — terms like `RSRP`, `SINR`, `guardrail`, `outage`, `coverage`, `energy saving`, `cells switched off` only count as inference signals when the user is asking about a **completed run result**. Otherwise route to `reactive_agent` (concept question) or `data_generation_agent` (dataset / simulation intent).
2. **Definition-phrasing override** — *"what does X mean / what is X / what does X tell us / what happens to X / how is X calculated / why does X matter"* → `reactive_agent`, regardless of inference keywords in X.
3. **Action-phrasing override** — *"how do I configure / generate / create / set up"* + simulation / dataset intent → `data_generation_agent`, regardless of inference keywords.

**Eval corpus:** `scripts/eval_routing.py` runs a 35-query corpus against the live routing agent (precision, recall, confusion matrix, accuracy by difficulty + category). Baseline: 35/35 (100%) accuracy. Manual run: `GROQ_API_KEY=… python scripts/eval_routing.py --tag <tag>`. Results → `results/routing_*.json`.

**Unit tests:** `tests/routing/test_routing.py` — 3 classes (`TestRoutingAgentParsing`, `TestRoutingAgentFallback`, `TestRoutingAgentOutput`), fully mocked (no `GROQ_API_KEY` required). `VALID_AGENTS` = the four-agent pool.

**Known limitations:** no CI gate on the corpus harness (regressions only caught if `eval_routing.py` runs before merge); single-model eval (`llama-3.1-8b-instant`); no confidence calibration; results JSON files only (no DB / dashboard). See §9.

**Implementation log:** [HISTORY §10.10](./COPILOT_HISTORY.md#1010-routing-prompt-disambiguation).

---

## 29. User-Facing Output Rules

`USER_OUTPUT_RULES` constant appended to every system prompt at `ReactiveAgent._get_agent()` — single integration point, all subclasses inherit. Stops internal content from leaking to the user. Replaced the previous `## MANDATORY References Section` block (which was appending `Source: … | File: … | Chunk:` after every response).

**The five rules:**

1. **No internal RAG citations** — never reveal source file paths, chunk IDs, or relevance scores. *External* / internet links are explicitly permitted.
2. **No runnable commands or code** — never tell the user to run something; never paste `curl` / shell / SQL / Python they're expected to execute.
3. **Tool-failure vs error-content distinction** — when a tool fails or returns 4xx / 5xx, acknowledge the limitation in plain language; never paste the raw error body.
4. **No internal identifiers** — never surface UUIDs, tenant IDs, model IDs, BDT IDs, run IDs, or any closure-bound identifier.
5. **Plain language always** — explain in user-comprehensible terms; no jargon dump.

**Key files:** `app/agents/reactive/agent.py` (`USER_OUTPUT_RULES` + `_get_agent()` integration), `app/agents/reactive/prompts.py` (References section removed).

**Tests:** `tests/agents/test_reactive_agent.py` — `TestUserOutputRules` (6), `TestSystemPromptComposition` (3), `TestMandatoryReferencesRemoved` (4 regression tests preventing re-introduction).

**Scope:** `generic/agent.py` and `offline_debugging/agent.py` are out of scope because they are legacy / dead code — not wired into routing, never invoked, and will not be exposed (see §1 admonition). The rules apply to every agent reachable at runtime via inheritance from `ReactiveAgent`. RAG still runs internally; tool traces remain in `AgentResponse.metadata`; structured payloads (§26) and FE cards unaffected.

**Implementation log:** [HISTORY §10.11](./COPILOT_HISTORY.md#1011-user-facing-output-rules).

---

## 30. Orchestrator mypy Fixes + CI Scoping (2026-07-30)

A prior dry-run mypy pass on `orchestrator.py` reported 119 errors. Isolating the check with `--follow-imports=silent` (checking the file on its own, not following imports into 18 unrelated files) showed the true local count is **10**. All 10 fixed on `fix/orchestrator-mypy-errors`.

**One real bug (not just typing):** `debugger_node`, `data_generation_node`, and `inference_explanation_node` (`app/agents/orchestrator.py`) each have a both-agents-failed branch that previously built `AgentResponse(metadata={...})` from a plain dict with keys like `debugger_error` / `fallback_error`. `AgentMetadata` (`app/agents/schemas.py`) is a Pydantic model with the default `extra="ignore"` — those extra keys were silently dropped at construction, so when both the primary agent and its ReactiveAgent fallback failed, the actual exception strings never reached logs, the DB, or the API response — only the generic `"error": "both_agents_failed"` code survived. **Fix:** added a `details: dict[str, str] | None` field to `AgentMetadata` and rewrote the 3 call sites to construct a real `AgentMetadata(error=..., details={...})` instead of a raw dict.

**Remaining 7 were annotation/narrowing gaps, no behavior change:**
- `RoutingAgent.route()` (`app/agents/routing/agent.py`) was typed `-> dict[str, str | float]`; added a `RoutingResult` `TypedDict` (`agent: str`, `confidence: float`, `reasoning: str`) — fixed 3 errors (2 assignment sites in `run()`/`run_stream()`, 1 cascaded `arg-type` at `_create_agent_for_streaming`).
- `run()`'s `return final_state["final_response"]` triggered `no-any-return` because `create_orchestrator_graph() -> Any` (LangGraph has no useful stubs; `langgraph.*` is already `ignore_missing_imports`d in `pyproject.toml`). Fixed with `cast(AgentResponse, ...)` — an explicit narrowing assertion, not a suppression.
- `router_node`'s `state.get("current_agent", "reactive_agent")` didn't narrow away `None` because `AgentState.current_agent` is itself `str | None` — a `TypedDict.get(key, default)` default doesn't change the declared value type. Fixed with `state.get("current_agent") or "reactive_agent"`.
- `run_diagnostic`/`run_generic` (legacy pass-through wrappers) needed `*args: Any, **kwargs: Any` — `disallow_untyped_defs = true` requires it even on trivial wrappers.

**CI scope decision:** `orchestrator.py` is clean under `--follow-imports=silent` but **not** under plain `mypy app/agents/orchestrator.py` — that follows imports into `app/agents/reactive/agent.py`, `debugger/agent.py`, `data_generation/agent.py`, `inference_explanation/agent.py`, which construct `AgentMetadata` from raw dicts the same unsafe way (e.g. `reactive/agent.py` passes `guardrail_blocked`/`guardrail_name` keys that aren't on the model at all — a **larger, unaudited instance of the same bug class**). Repo-wide mypy CI is blocked on auditing those files first. If/when this file joins a CI gate, it needs a per-module `follow_imports = "silent"` override in `pyproject.toml`, not a bare invocation.

**Not done, flagged for follow-up:** (1) audit `AgentMetadata` dict-drop pattern across `reactive/agent.py`, `debugger/agent.py`, `data_generation/agent.py`, `inference_explanation/agent.py` — likely more silently-dropped diagnostic fields; (2) `generic/agent.py` / `offline_debugging/agent.py` are confirmed dead code (§1, §29) and were deliberately left out of this mypy sweep rather than excluded via a mypy override — the correct fix there is deletion, not a type-check carve-out.

**Local environment note:** `.venv/bin/mypy`'s shebang points at a now-nonexistent path (repo directory was renamed `CloudlyNetAI` → `CloudlyAI` at some point) — use `uv run mypy ...` instead of the `.venv` binary directly. Separately, `uv run pytest` on this machine falls back to a system Python 3.11 with an incompatible `langchain` (missing `langchain.agents.create_agent`), which pre-existingly breaks collection for any test importing `app.agents` (confirmed via `git stash` that this fails identically on unmodified `main`) — this blocks running the test suite locally until the environment is repaired; not caused by and out of scope for this PR.

---

## 31. MCP Domain Coverage (2026-08-20)

EPIC-8. Full record — the frozen decision with its revisit trigger, the complete tool inventory, and
the deviations from the epic text — is `artifacts/copilot/mcp-domain-coverage.md` in the parent repo.
This section is the service-side summary.

**One server, per-domain tool modules.** The standing question was whether the copilot needs an MCP
server per platform layer. It does not: one process, one port, one registry, with each layer a module
under `app/mcp_server/domains/` registering its own tools via `register_all(mcp)`. `server.py` now holds
**zero** `@mcp.tool` decorators. Domain separation is code layout, not deployment topology — nothing new
to deploy, route or monitor.

| Module | Domain | Tools |
|---|---|---|
| `domains/data_tools.py` | ingest | 12 |
| `domains/actuation_tools.py` | actuation | 9 (7 read + 2 gated mutations) |
| `domains/observability_tools.py` | observability | 5 registered, 2 defined-but-unregistered |
| `domains/optimization_tools.py` | optimization | 5 |
| `domains/ndt_tools.py` | ndt | 3 |
| `domains/policy_tools.py` | policy | 2 (1 conditionally registered) |
| `domains/diagnostics_tools.py` | observability | 1 |

**Registry by flag:** 34 by default → +2 with `MCP_ENABLE_MUTATING_TOOLS` → +1 with the ops DSN *and*
`CLOUDLYIO_ORG_UUID` → 37 with all. Asserted as a programmatic tool-name set built from the domain
modules, never a hand-counted total.

**Identity is never an LLM-visible argument.** `context.py` builds a per-invocation `ToolContext` with
five fields off the inbound connection: `tenant_id` (the `custom:tenant_id` claim), `auth_token` (the
bearer, forwarded per request), `role` (the raw `custom:role` claim — there is no role mapping),
`correlation_id` (`X-Correlation-ID`, echoed back verbatim) and `request_id` (`X-Request-ID`, kept
separate). Four hardcoded tenant defaults are gone, and every gateway factory guards an empty or
non-UUID tenant before building a URL. `:8082` decodes the JWT **without verifying** it, purely to build
tenant-scoped URLs; the gateway remains the sole enforcement point, deliberately, so no second authority
can drift from it on key rotation or clock skew. A missing bearer returns `AUTH_CONTEXT_MISSING` and
makes zero outbound calls.

**One envelope on every tool** — `cloudlynet.mcp.response.v1`, built only through the builders in
`envelope.py`, so `kind: "empty"` with `success: true` (a finding) can never be confused with
`success: false` (a failure). A registry-wide parametrised test invokes every registered tool against
the vendored schema, so a non-conforming tool cannot ship.

**Mutations, three gates.** `approve_recommendation` and `reject_recommendation` act only on
recommendations the platform itself generated — the copilot cannot compose a change of its own. **Env:**
`MCP_ENABLE_MUTATING_TOOLS` defaults false, and false means absent from the registry rather than
present-and-refusing. **Role:** `trial_user` is refused before any outbound call, even with
`confirm=true`. **Confirm:** `confirm` defaults false and that path never writes — it reads current state
and returns an `action_preview` a human must be shown. Every attempt is audited, and a forbidden-path
test pins direct device commands, optimize-mode, key regeneration and everything under `/v1/agent/**` as
unreachable.

**The `copilot_ops` read path** is the only direct database access in the MCP server, because the
guardrail decision log is copilot's own table and the gateway serves no route to it. Its gate is
therefore the only authorization in front of a log that **spans every tenant**, so it needs both
`MCP_COPILOT_OPS_DATABASE_URL` and `CLOUDLYIO_ORG_UUID` or the tool does not register at all; the DSN
must name copilot's own database or registration is refused; the read runs as a SELECT-only role; and the
projection omits `query_hash`, `session_id`, `reviewer_id` and `reviewer_note`.

**Placeholder retirement.** `get_model_accuracy` and `list_available_models` returned hardcoded values
and are deleted. They were the offline-debugging agent's entire toolset, so that agent now has none and
its system prompt was rewritten — leaving it would have had the agent hallucinate calls to tools that no
longer exist.

**Deliberately unregistered.** `search_device_logs` and `fetch_raw_log_window` are written but absent
from the registry: they need a parsed-log-line store and an archive writer, neither of which exists.
`get_observability_capabilities` is the machine-readable probe that says so, because zero rows would read
to a customer as "your network is quiet" rather than "this is not built."

**Verification worth knowing about.** The layer was validated against a live stack before the PR: the
first run found six real defects including a server that did not start under its own compose service, and
a second run passed 21/21. The lesson recorded for future epics is that mocking gateway responses to a
shape read out of `openapi.yaml` is not testing — four of the six defects lived in the gap between the
spec and what the services actually return.

---

## 32. MCP Server Lifecycle Tracing (2026-08-27)

The standalone MCP server was effectively silent. Every startup record was discarded, no successful
`tools/call` produced a line, and the whole outbound surface logged one DEBUG line with no status,
duration or outcome. With the RCA team as the first external consumer of `:8082`, their first
connection failure would have been undiagnosable from our side.

**The root cause of the lost startup records was import order, not a missing log call.**
`app/mcp_server/__init__.py` re-exported from `server`, so `register_all()` and all seven
registration banners ran during *package* import — before any entrypoint could install a handler,
while root sat at WARNING. Importing a submodule imports its parent package first, so no statement
order inside `server_docker.py` could fix it. The package is now lazy (PEP 562 `__getattr__`) and
`configure_logging()` runs above the `server` import. This is the second occurrence of the bug
`logging_setup.py` was originally written for; the laziness closes the class, not just the instance.
Side effect, deliberate: the copilot backend container no longer builds a 34-tool registry it never
serves.

**What the container emits now.** `mcp_boot` (a block, once — the registry it built plus one
`gated_off` line per withheld tool *with the reason*), `mcp_session_open` / `mcp_handshake` /
`mcp_list` / `mcp_session_close`, one `mcp_call` per invocation, `mcp_http_error` for the
unknown-session case, and `mcp_shutdown`. `mcp_call` carries identity (tenant prefix, role,
`xcorr`), envelope facts (`kind`, `n`, `total`, `trunc`, `cursor`, `ign`, `bytes`, `code`) and
upstream accounting (`up`, `up_att`, `up_ms`, `up_status`). Response bodies are never logged at any
level; `MCP_TRACE_DETAIL=full` widens argument *keys* to values and is documented as raising the
confidentiality class of the logs.

Implementation notes worth keeping:

- **`on_call_tool` is the seam**, not `wrap()`. Every tool returns `str`, so the middleware recovers
  the entire envelope from `ToolResult.content[0].text` — all 34 tools, zero domain-module edits.
- **`CallTrace` is a mutable object behind a ContextVar**, mutated in place at the leaf. A leaf
  calling `ContextVar.set()` would be lost: `observability_tools` fans out through `asyncio.gather`,
  which copies the context per child task.
- **fastmcp's own `LoggingMiddleware`/`TimingMiddleware` were rejected.** They implement `on_message`
  only, so they never see the `ToolResult`; their one route to detail serialises request arguments,
  which the payload rule forbids by default.

Four latent defects surfaced, each caught by a test rather than by reading:

1. **The gateway client's `@retry` had never fired.** `httpx.TimeoutException`/`NetworkError` are
   subclasses of `httpx.RequestError`, which the function's own handler caught and converted to
   `ServiceUnavailableError` — a type the predicate could not match. Three attempts were always one.
   Fixed, and scoped to idempotent methods: `httpx.RequestError` cannot distinguish "never sent"
   from "read timed out after the gateway acted", and two of the four POSTs are
   `recommendations/{id}:approve`/`:reject`, which materialise a TR-069 command on real hardware.
2. **`reraise=True` was missing.** With retries live, the exhausted path would raise
   `tenacity.RetryError`, which has no `code`/`details`, so `classify_upstream_error()` would report
   `INTERNAL_ERROR` for an unreachable gateway. That path had never executed before.
3. **Four of the 34 tools were dead on the wire.** `platform_tools._cfg()` imports the backend
   `Settings` at call time; the container sets 3 of its 7 required vars, so the first call to any
   cache-backed tool raised `ValidationError`, `wrap()` swallowed it, and the caller got
   `INTERNAL_ERROR`. Deferring the import had only moved the failure from import time to call time.
   `_cfg()` now falls back to cache-disabled, which is also correct rather than a workaround: the
   container has no `REDIS_URL`, so caching was never possible there.
4. **httpx leaked tenant UUIDs.** Giving root a handler made `httpx` audible for the first time, and
   it logs full request URLs at INFO — every gateway URL is `/v1/tenants/<uuid>/...`. `httpx`,
   `httpcore` and `mcp.server.lowlevel.server` are now quieted to WARNING by default and released
   at DEBUG.

Also fixed: `mcp_shutdown` never fired, because uvicorn's `capture_signals` restores the default
handler and re-raises the captured signal, so the process dies *inside* `serve()` and any `finally`
after it is unreachable — the container was exiting 143 silently. Our handler is installed first, so
uvicorn's re-raise lands on us.

**Verified against the live stack**, not only under pytest: boot report with `tools=34` and both
`gated_off` reasons; a full session traced end to end; `AUTH_CONTEXT_MISSING` with no `up=` fields,
proving zero outbound HTTP on a refusal; the trace surviving `MCP_LOG_LEVEL=WARNING`;
`MCP_TRACE_DETAIL=off` leaving only the boot line; and a confidentiality sweep of the container log
finding zero tenant UUIDs, zero JWT fragments and zero response-body fields.

**Known limitation:** `mcp_handshake` reports `tsid=-`. The transport session id is not in scope
during `on_initialize` under SSE, so no single line carries both `conn` and `tsid`; joining a
session bracket to its calls means using the timestamp and `peer`.

---

## 33. Backend MCP Client — Copilot Consumes the MCP Server (Milestone 1) (2026-08-28)

**PR:** `feat/mcp-integration` (copilot), branched from `feat/epic-8` @ `089ee26`. Parent-repo half is
one `docker-compose.yaml` env line (`cloudlynet_ai` `feat/mcp-integration`, `0a2e770`). Full PR text:
`claude_contexts/PR/PR_MCP_Client_Integration.md`.

**What it is.** The first time the backend connects to the standalone MCP server (`copilot-mcp-server`,
FastMCP over SSE, `:8082`). Before this, agents reached the platform only through direct-gateway tools
(`app/mcp_server/platform_tools.py`); nothing in-house dialed `:8082`. This adds an **outbound MCP
client** so agents can call that server's registry.

**Files.**
- `app/mcp_client.py` (new) — `call_mcp_tool` / `list_mcp_tool_names` over `fastmcp.Client` +
  `SSETransport`; `build_mcp_tools(server_url, tenant_id, auth_token)` returns **8 read-only** LangChain
  `StructuredTool`s: `get_observability_capabilities`, `get_device_timeline`, `search_device_events`,
  `get_active_alarms`, `get_alarm_history`, `get_device_config`, `list_devices`, `list_edges`.
- `app/core/config.py` — new `COPILOT_MCP_SERVER_URL` (None = client off).
- `app/agents/orchestrator.py` — module-level `_mcp_server_url`, threaded into **both** `DebuggerAgent`
  construction sites (streaming `_create_agent_for_streaming` + `debugger_node`).
- `app/agents/debugger/agent.py` — new `mcp_server_url` param; `_build_tools()` appends the MCP-client
  tools when set, guarded so wiring failure never breaks construction.
- `.env.example`; `tests/test_mcp_client.py` (6 tests).
- Parent `docker-compose.yaml` — `COPILOT_MCP_SERVER_URL` on `copilot-backend`, default
  `http://copilot-mcp-server:8080/sse`. The backend reads env from this compose block, **not** the
  module `.env`, so this line is what actually reaches the container.

**Design decisions.**
- **Auth = one SSE connection per tool call.** MCP-over-SSE authenticates at connection time (the
  direct tools forward the JWT per request), so the client opens a connection per call carrying the
  caller's Cognito JWT + a per-session `X-Correlation-ID`. Pooling within a session is deferred.
- **Hand-rolled `fastmcp` wrappers**, not `langchain-mcp-adapters` — `fastmcp` is already a backend
  dep, this gives exact per-request auth control and mirrors the `platform_tools.py` closure pattern.
- **Read-only, no mutating tools** exposed. Fail-safe: URL unset → client off, behavior unchanged; a
  transport failure returns a `DEPENDENCY_ERROR` envelope, never an exception.

**Available vs wired — LOAD-BEARING for Milestone 2.** All **34** tools are *reachable* through the
client (proven). Only the **Debugger** agent has been handed tools, and only **8** of them. The other
agents (Reactive, DataGeneration, InferenceExplanation) have **none** yet. An agent uses only the tools
in its own `_build_tools()` list. Deciding which of the 34 each agent gets, and tuning their
prompts/behavior, is Milestone 2.

**Verified (live local stack).** Client lists **34** tools; the DebuggerAgent carries the 8 +
`rag_search`; `get_observability_capabilities` returns `success=true` (count=6) through the agent's own
tool object; the full chain to the gateway returns real envelopes with auth enforced
(`AUTH_CONTEXT_MISSING` no bearer → `UNAUTHORIZED` unsigned token → `FORBIDDEN` role `trial_user` /
`NOT_FOUND` empty `fm_alarms` with dev-bypass on). Unit 6/6; `black` + `ruff` clean.

**Caveats.**
- Device-plane data needs a real Cognito token (or gateway `DEV_BYPASS_JWT=true`) **and** an
  authorized role — `trial_user` is `FORBIDDEN` from device reads; use `tenant_admin`. A gateway env
  matter, not a copilot one.
- A gateway startup panic — `/v1/agent/*path` registered twice in `cmd/gateway/main.go`, Gin panics on
  the duplicate wildcard — was fixed **locally, not pushed**, to unblock testing. A prod gateway
  rebuilt from current `main` will panic until that fix lands in the gateway repo.

**Milestone 2 (next).** Ship the RCA loop; decide which of the 34 tools each copilot agent gets and how
their behaviors/prompts adapt. Entry point: `claude_contexts/MASTER_OnDemand_RCA_Context.md`.

---

## 34. RCA Tool Wiring + LLM-Driven Loop (Milestone 2, Part 1) (2026-09-03)

**What shipped.** The full **34-tool** MCP surface is wired into the Debugger, and the Debugger runs
an **LLM-driven RCA loop** over it — it decides what evidence it needs, calls the tools it chooses,
and loops, with clean operator-facing output. Branch `feat/mcp-integration` (copilot).

### Tool wiring (`app/mcp_client.py`, `app/agents/debugger/agent.py`)
- `_CURATED_TOOLS` grown 8 → **12** — the pinned RCA set: Tier 1 (RCA core: capabilities, timeline,
  events, alarms) + Tier 2 (device-plane: config, kpis, health, command, recommendations, devices,
  edges).
- New `_POOL_TOOLS` (**22**) + `build_pool_tools()` — the Tier-3 general pool (NDT, optimization,
  data/ingest, policy, diagnostics). The Debugger builds pin + pool = **34** tools.
- The old `api_client` direct-gateway tools (`compare_rapp_policies`, `get_platform_error_logs`)
  were **folded into the MCP surface** — they were being added twice under one name. The api_client
  tool-adding block is removed from `_build_tools`.
- The 3 gated tools (`approve_recommendation`, `reject_recommendation`, `get_guardrail_decisions`)
  are never wired.

### The LLM-driven RCA loop (new `app/agents/debugger/rca.py`)
Keeps the model's agency (it picks the tools) but makes it reliable. Three pieces:
- **Gate** — `classify_needs_live_data(query)`: a dedicated decision — does this query need live
  platform data, or is it concept/how-to? Rules fast-path (device id / keywords → yes; concept
  openers → no) + one cheap `openai/gpt-oss-20b` yes/no call, biased to yes.
- **Tool-forcing** — `RcaForceToolMiddleware` (a langchain `AgentMiddleware`): when gated in, sets
  `tool_choice="required"` per model turn until a non-rag ("evidence") tool has run, so the model
  cannot answer a device question from memory. `rag_search` is allowed first (planning) but does not
  satisfy the requirement. Best-effort: if the provider refuses (`tool choice required but model did
  not call a tool`) it falls back to an unforced call — never fatal.
- **Answer cleanup** — `clean_answer()`: the model ignores prompt rules about leaking internals, so
  the Debugger's answer is buffered, fenced code blocks stripped, then rewritten by gpt-oss-20b to
  remove tool names, endpoints, JSON, and token/auth talk. `ToolCallLimitMiddleware(run_limit=10)`
  caps the loop.

### Wiring seam (`app/agents/reactive/agent.py`, `app/agents/orchestrator.py`)
- New base hooks on `ReactiveAgent`: `aprepare_query(state)` (no-op) and `_build_middleware()`
  (returns the guardrail stack). The Debugger overrides both — `aprepare_query` runs the gate;
  `_build_middleware` appends the force + limit middleware.
- The gate runs in **both** paths: `invoke()` calls it (non-stream), and the orchestrator's
  streaming loop calls `agent.aprepare_query(...)` before building messages (the streaming path
  never calls `invoke`). The streaming loop also **buffers the Debugger's answer and cleans it**
  before sending (no live token stream for the Debugger; other agents unchanged).

### Prompt (`app/agents/debugger/prompts.py`)
- New RCA loop addendum (appended when `mcp_server_url` set): plan → fetch one tool the model
  chooses → judge "enough?" → loop → cited answer; never answer a device question from memory; never
  expose internals.
- Main FULL prompt de-emphasised `get_platform_error_logs` — it was named as *the* evidence tool, so
  the model defaulted to it — and now points to the tool most relevant per question; error-logs is
  clarified as a SERVICE tool, not device data.

### Cache fix — the broken RedisCache (`app/core/llm.py`, `app/core/config.py`, `backend/.env`)
The `RedisCache` LLM backend uses RedisJSON (`JSON.GET`/`SET`), which the standard Redis image does
not load, so any cached LLM call **raised fatally** and failed the agent (debugger → reactive
fallback → static error). Fixed: caching forced off in `build_llm` (`cache=False`);
`LLM_CACHE_ENABLED` default off (`config.py` + `backend/.env`). The routing agent also moved off the
unavailable `llama-3.1-8b-instant` to `openai/gpt-oss-20b` (its cached call was silently sending
every auto-routed query to the reactive fallback).

### Verification
- **API coverage sweep** (one targeted query per tool through `/query`, debugger agent): **30/34**
  tools called their expected tool; the RCA-relevant **16/16**. The 4 misses are data-generation
  "recommend / list / docs" tools out of the Debugger's lane (answered from knowledge); they belong
  to the DataGeneration agent's pool wiring (deferred).
- All 34 registry-reachable (client name → server handler, 0 missing).
- Frontend confirmed on 6 queries (gate + tool + clean output).
- Tests: `tests/test_mcp_client_wiring.py` **18 pass** (wiring, pool, gated absence, RCA prompt, gate
  rules, middleware). `black` + `ruff` clean on all changed files.

### Known limitations / follow-ups
- **Auto mode is deferred — select the Debugger explicitly for RCA.** Copilot does **not** yet
  reliably auto-route an RCA / device prompt to the Debugger, so it cannot autonomously decide to
  run RCA when a relevant prompt is made. For consistent RCA performance the user must **choose the
  Debugger agent**. (The earlier auto-mode failures were the cache/model bugs now fixed, but the
  router's RCA→Debugger classification itself is not yet validated.)
- **Only the Debugger is wired and tuned** for the new MCP tools. The other agents (Reactive,
  DataGeneration, InferenceExplanation) have **not** had the MCP tools wired, nor their
  prompts/behavior tuned — this applies to the **new MCP tools only**. It is intentionally **not
  committed** yet: it needs a design discussion first on each remaining agent's expected behavior,
  so the right tools go to the right agent with the correct tuning. (The 18 non-RCA pool tools are
  wired + reachable on the Debugger but belong, by domain, to those other agents.)
- Tool choice is the model's; the gate + forcing guarantee *a* live tool, not the *best* one — the
  prompt/description tuning got the RCA set to 16/16, but off-lane tools still vary.
- Answer cleanup adds one gpt-oss-20b call and buffers the Debugger answer (no live typing).
- LLM response caching is off platform-wide until a cache backend without RedisJSON is configured.

---

## 35. MCP Wiring Paging — Cursor Auto-Paging and Fields Projection (2026-09-08)

**The gap.** The MCP server's list tools expose four paging levers — `limit`, `cursor`, `sort`,
`fields` — and page each reply by both a row count (`limit`) and an ~8 KB byte budget
(`fit_to_budget`), minting a `result.page.next_cursor` when either binds. The Milestone-2 wiring
(`app/mcp_client.py`) forwarded **only `limit`**. So the Debugger could cap a page but could not
follow the cursor (stuck on page 1 when a reply truncated) and could not project columns
(every row came back full-width). The design required paging — `OnDemand_RCA_Design_Doc_v2` §5/§6
("the loop pages", `RCA_PAGE_BOUND = 4`, "paging does not charge the fetch cap") — so this closes a
miss against that spec, not a new feature.

**Fix 1 — internal cursor auto-paging (model-transparent).** `_make_coroutine` now wraps each
per-call SSE invocation in `_auto_paged`: after the first call it reads `result.truncated` +
`result.page.next_cursor`, and while truncated it re-calls with `{**arguments, "cursor": <next>}`,
concatenating `data.items`, up to `_PAGE_BOUND = 4` pages. It then returns **one** envelope with the
full item set, `next_cursor` stripped, `truncated` meaning "more remains past the bound", and a
`pages_fetched` count. The model never sees or supplies a cursor. Non-paged tools and error
envelopes fall straight through (the loop only fires when a tool actually returned a cursor, which
means it accepts one). Each page is still bounded by the server (count + byte budget), so a logical
fetch is complete **and** cheap — the "optimal fetch", not just next-page.

**Fix 2 — `fields` projection exposed on the list tools.** Added a `fields: list[str] | None`
parameter to the 11 list tools, each description **enumerating that tool's real fields** (pulled from
the server's field tuples — `_ALARM_FIELDS`, `_EVENT_FIELDS`, `_DEVICE_FIELDS`, `_EDGE_FIELDS`,
`_RECOMMENDATION_FIELDS`, `_MODEL_SUMMARY_FIELDS`, `_MODEL_FIELDS`, `_DATASET_FIELDS`,
`_UPLOAD_FIELDS`) so the model picks only the relevant ones. Tools: `get_device_timeline`,
`search_device_events`, `get_active_alarms`, `get_alarm_history`, `list_device_recommendations`,
`list_devices`, `list_edges`, `list_twin_models`, `list_rapp_models`, `list_ue_datasets`,
`get_nybsys_upload_status`. `list_devices`/`list_edges` previously used `_NoArgs` (no params at all,
under-exposing the server, which accepts `limit`/`cursor`/`fields` on them) — they now have real
schemas `_DevicesArgs`/`_EdgesArgs`.

**Deliberately skipped.** `get_device_kpis` (its existing `metric` filter is the projection for
performance samples); `query_existing_baselines` (offset-based, Tier-3, field tuple unconfirmed —
not guessed); and `sort` (only one server tool accepts it — unsafe to wire broadly). All are still
covered by the auto-pager for completeness.

**Verification.** Auto-pager unit-checked against a mocked transport — merges across pages and
drains to `truncated:false`; stops at `_PAGE_BOUND` with `truncated:true` when more remains; strips
the cursor; passes non-paged/error envelopes through unchanged. `fields` forwarding confirmed
(`list_devices` invoked with `fields=[...]` reaches `call_mcp_tool`). Registry still 34 tools;
`black`/`ruff` clean; 37 tests pass (`tests/test_mcp_client_wiring.py` 18 + `tests/agents/test_debugger_agent.py` 19). Not yet exercised end-to-end against live device data.

**Known limitations.**
- `_PAGE_BOUND = 4`: a logical fetch stitches at most 4 server pages; beyond that `truncated:true` is
  returned and the model is told more exists but cannot fetch it (bounded by design).
- `fields` is model-driven — wrong names degrade gracefully (server reports `unknown_field` and
  returns full rows), but the model must choose from the listed set to gain the projection.

---

## 36. KB v2 — Corpus Rebuild from `artifacts/`, and the Standing Include/Exclude Policy (2026-09-10)

**What this section is for.** The v1 knowledge base (491 chunks / 31 docs / 7 sources, §10) is
retired. This records the two v2 bundles built from the parent repo's `artifacts/` tree, and — more
importantly — **the policy that decided what went in**, so a future KB v3 does not re-litigate it.

### 36.1 Why v1 is retired, not refreshed

- The v1 corpus does not exist on disk. `knowledge_base/` is gitignored (`.gitignore`, "Knowledge
  Base") and absent from every checkout.
- The v1 sources were the five submodule READMEs plus `cloudlynet_ai/tree/main/design`. The
  READMEs are **not** platform-level documentation — verified by reading all five: every one is
  built from the same internal skeleton (`Project layout`, `Internal service auth`,
  `Database configuration`, `Object storage configuration`, `Schema migrations`) with an inline
  OpenAPI fragment, and none has a conceptual introduction. They are excluded from v2 by decision,
  not by omission.
- §10's "Known Retrieval Issues" B/C/D (missing rApp-type, BDT and SMO concept files) are moot —
  they described gaps in a corpus that no longer ships.
- §10's "Knowledge Base Quality Issues" list is **stale**, verified 2026-09-10:
  - rApp README port `8004` → now reads `localhost:8001` (README lines 194, 751, 752). Fixed.
  - bdt README `train_test_split` / `random_seed` "not implemented" → both ARE implemented
    (`bdt_worker.py:748-749`, read back at `894-895`).
  - rapp README CCO reuse via `input_signature` / `allow_reoptimization` → neither string exists in
    the README or in `rapp/app/`.

### 36.2 The include/exclude policy (the part to reuse for v3)

The `knowledge` tables have **no RLS** — `artifacts/db/init_copilot_rls.sql` states it plainly:
"Knowledge tables are intentionally excluded — they are globally accessible." The retriever has no
tenant filter either (`rag/retriever.py:387` — "no per-tenant scoping in this retriever"). So every
ingested chunk is readable by every copilot user. That single fact drives the whole policy.

**Two bars, applied in order.**

**Bar 1 — business / operational confidential. Out of EVERY bundle, no exceptions.**
Pricing, ICP, GTM, sales motion, roadmap, competitor framing; production deployment topology,
secrets inventories, production gap analyses, runbooks; internal delivery planning, handovers,
unshipped epics, session prompts; third-party vendor assessments; superseded designs; real customer
data.

**Bar 2 — platform and copilot internals. Out of the tenant-safe bundle only.**
The test: *can a paying customer already observe this through the product — the UI, or the API their
own integration calls?* If yes, it stays. If no, it goes. Concretely OUT under this bar: which APIs
connect the copilot to its tools, the tool inventory and count, rApp/RL hyperparameters, Kafka topic
names, DB table names, env var names, internal source paths, internal service auth, service
decomposition, cache tiering, deployment shape.

**Filename is not a filter — read the file.** The HLD/LLD label does not predict content:

- `artifacts/design/LLD.md:426-465` carries per-rApp RL reward weights (ES 0.2/0.1/1.0,
  LB 0.5/1.0/0.05, CCO 1.0/0.25/0.0), PPO `n_steps=512` / `batch_size=128` / `ent_coef=0.01` /
  `total_timesteps=30_000`, and the RLF/HO warning thresholds.
- `artifacts/copilot/copilot_HLD.md` is only 1,112 words but names the full agent roster
  (`reactive`, `debugger`, `data_generation`, `generic`, `offline_debugging`), states which two are
  concealed from the user (§6.1 step 6), and gives the MCP→gateway wiring (§6.2).
- `artifacts/frontend/HLD.md`, by contrast, is browser-side and almost entirely observable — it is
  kept in the tenant-safe bundle after removing §10 Deployment View and §11 High-Level Risks.

**Surgery is worth it only where the residue is real.** Measured: cutting the internal sections from
`design/LLD.md` leaves ~150 usable words out of 9,809 (1.5%), and those 150 duplicate
`frontend/API_Contracts.md` §4. Full-cut such files. Files with genuine residue —
`frontend/route.md`, `API_Contracts.md`, `loop_actions_api.md`, `HLD.md`,
`data-platform/canonical-schema.md`, `nanolink/femtocell_dashboard_data_contract.md` — get section
surgery instead.

### 36.3 Why architecture belongs in a KB at all

RAG is not answer-only. Verified in code:

| Use | Evidence |
|---|---|
| Mandatory pre-step before any tool call | `agents/debugger/prompts.py:12` ("ALWAYS call rag_search BEFORE calling any platform tool… non-negotiable"); same mandate `reactive/prompts.py:96`, `inference_explanation/prompts.py:33` |
| Planning input for tool choice in the RCA loop | `agents/debugger/rca.py:13` ("`rag_search` is allowed first (for planning)"); RCA addendum step 1 PLAN |
| Fallback answer source when live tools fail | `debugger/prompts.py` MCP-failure block |
| Supplementary grounding for guidance | `data_generation/prompts.py:134` |

Not used for routing (`RoutingAgent.route(self, query: str)` takes the query only, no retriever) and
not used by the live-data gate (`classify_needs_live_data` is rules + one `gpt-oss-20b` call).

That is why v1 carried `design/` and why bundle 2 exists.

### 36.4 The two bundles

Archived, zipped, under `artifacts/knowledge_base/` with a `README.md` naming convention and a
per-bundle `MANIFEST.md`. v1 is to be restored to the same directory.

| | `kb_v2_bundle1.zip` | `kb_v2_bundle2.zip` |
|---|---|---|
| Docs | 27 | 45 |
| Words | ~21,300 | ~66,600 |
| Bar 1 (business/ops) | excluded | excluded |
| Bar 2 (internals) | excluded | **included** |
| Source dirs | `frontend` `data_platform` `nanolink` `actuation` `ric` | + `design` `copilot` `deployment` |
| Safe on today's code | yes | **no** |
| Section surgery | 7 files edited | none — full originals |

Bundle 2 deliberately does **not** inherit bundle 1's surgery; those cuts removed architecture,
which is bundle 2's purpose. Bundle 2's only redaction is the real NybSys device serial
`2205609999`, replaced with the anonymised `2205609999` (the serial the fixture pack already uses).
`deployment/HLD.md` and `deployment/LLD.md` are in bundle 2; the other 11 `deployment/` files are
not (`secrets-hygiene.md` and `gaps_production.md` are the load-bearing reasons).

### 36.5 Bundle 2 cannot be ingested safely as-is

Two enforcement points were considered. **Retrieval-side filtering is the recommended one** —
content the retriever never returns cannot leak, and it preserves token streaming.

Output-side redaction is the weaker option and does **not** exist today:

- The guardrail pipeline (§27) is **input-only** — its own "Known limitations" say so.
  Default `GUARDRAIL_MODE=shadow`, `GUARDRAIL_FAIL_OPEN=true`.
- `USER_OUTPUT_RULES` (§29) bars RAG citations, code and internal identifiers by prompt text. It
  does not bar architecture prose, and it works by persuasion.
- `clean_answer()` (§34) is **Debugger-only and streaming-only** — `orchestrator.py:347` gates it
  on `selected_agent == "debugger_agent"`, and its sole call site is `orchestrator.py:412` inside
  `run_stream`. The non-streaming `run()` returns `final_state["final_response"]` unmodified
  (`orchestrator.py:215`).
- The output-side hallucination pipeline is still planned, not implemented (§9).

Consequence: the **reactive agent** is the default, has a mandatory `rag_search` first step, and
streams raw tokens with no output filter. Ingesting bundle 2 without a filter exposes architecture
to every tenant user.

Note also that turning streaming off does not help — it removes the one scrubber that exists.
Buffering is what enables a post-hoc filter, which is exactly why the Debugger buffers.

### 36.6 Pipeline gaps to handle before ingest

Verified against `backend/scripts/ingest_knowledge_base.py` and `app/rag/ingestion.py`:

1. **No stale-document prune.** `ingest_directory()` only inserts and updates. v1's 491 chunks
   survive a v2 ingest. Purge first.
2. **Hardcoded `SOURCES`.** The script's 7-entry list points at v1 subdirs. It skips every
   directory in these bundles until repointed.
3. **Markdown only.** `extensions=[".md"]`. `design/openapi.yaml` and `design/schemas.sql` are in
   neither bundle. Converting them to markdown is an open item.
4. **No redaction step.** No allow-list, deny-list or scrubber anywhere in the pipeline. The
   exclusion policy must be enforced by controlling the ingest directory contents.
5. **Egress at ingest.** `ChunkContextualizer` (`contextualizer.py:100`) sends every chunk plus a
   6,000-char parent excerpt to Groq. Bundle 2 ≈ 1,300–1,800 chunks at ~4 s/chunk → 1.5–2 hours.

### 36.7 Open items

- Roadmap disclosure: `artifacts/actuation/` (6 files) and 4 `artifacts/ric/` files are
  capability-status notes ("what is a placeholder and why"). They pass the observability test but
  disclose non-capability. Currently in **both** bundles; no ruling yet.
- Which enforcement point for bundle 2 — retrieval-side filter vs output-side layer.
- `artifacts/knowledge_base/` is **not** gitignored; the zips will be committed on `git add -A`.

**Extended narrative:** [COPILOT_HISTORY.md §11](./COPILOT_HISTORY.md#11-kb-v2-corpus-selection-audit-2026-09-10).

---

## 37. Output Redaction Layer (Tiers 0/1/2/4) (2026-09-14)

**Decision.** The model reasons over the full KB, architecture included. A single gate on the way
out removes internal design from the answer. This replaces the retrieval-side source filter floated
in §36 — that design withheld the architecture docs from the model, which defeats the reason for
ingesting them. Branch `feat/redaction-layer` (cut from `origin/main`, carries `feat/mcp-integration`).

**Why not tagging.** A per-document label cannot express the requirement: `design/LLD.md` holds a
safe API envelope and unsafe PPO hyperparameters in the same file. Tagging also needs a human
decision per new document, and a missed tag fails open silently. Rules cover new content by default.

### Tiers

| Tier | Where | Scope | Action |
|---|---|---|---|
| 0 | retrieval (`rag/retriever.py`) | credentials, real device serials, production/cluster hostnames | chunk withheld from the model; a hit in an answer blocks it |
| 1 | answer | Kafka topics, 38 MCP tool names, env-var shape, `app/**/*.py` paths, tuning tokens, internal ports, `X-API-Key`, service/container names | drop the span |
| 2 | answer | 35 compound table names always; 11 ambiguous single words (`baselines`, `commands`, `devices`, …) only in identifier shape — schema-qualified or backticked | drop the span |
| 4 | answer | LLM judge (`gpt-oss-120b`) catches paraphrase leaks that name nothing | reword the span, else drop it |

Tier 2's shape rule is the load-bearing part: "upload a baseline" survives, `public.baselines` does not.

### Tier 4 design

The judge **only reads and quotes** — it never rewrites. A separate focused call rewrites one
flagged sentence; code splices the replacement back by exact string match. This bounds a wrong
verdict to a single span and keeps the edit deterministic, unlike §34's `clean_answer()`, which
hands the whole answer to the model and takes back whatever it writes unverified.

Rewrite → re-judge, capped at `REDACTION_REWRITE_MAX_ATTEMPTS=2`; the rewriting model still holds
architecture in context and can leak again in new words. On cap, or when the judge's quote is not
verbatim, the span is dropped.

### Files

- `app/guardrails/redaction/{__init__,config,patterns,deterministic,judge}.py` — new package
- `app/agents/orchestrator.py` — `redact_answer()` at the non-streaming return (single exit point)
- `app/rag/retriever.py` — `_deny_chunks()` after fusion **and** concept expansion; filtering either
  search path alone would let a denied chunk back in through the other
- `tests/guardrails/test_redaction.py`

### Config

`REDACTION_ENABLED` (master), `REDACTION_DETERMINISTIC_ENABLED`, `REDACTION_JUDGE_ENABLED`,
`REDACTION_JUDGE_MODEL`, `REDACTION_JUDGE_TIMEOUT_S`, `REDACTION_REWRITE_MAX_ATTEMPTS`,
`REDACTION_FAIL_OPEN` (**default false**), `REDACTION_LOGGING_ENABLED`.

Fails **closed** — deliberately the opposite of `GUARDRAIL_FAIL_OPEN=true` (§27): that gate blocks
input, this one withholds output. Logging records rule + count, never content.

### Scope and known gaps

- **Streaming is not wired.** It is broken after the platform revamp and is fixed separately. Its
  Debugger-only `clean_answer()` (§34) is untouched. When streaming returns, `orchestrator.py:367`
  needs the same gate plus buffering.
- **No pre-check.** The judge runs on every answer. A pre-check can only skip the judge, so every
  mistake it makes is an unexamined leak — and the KB has never been ingested, so there is no data
  to tune one against. Add it once the hit-rate log exists.
- **Tests are unrun.** No Python interpreter or Docker daemon on this machine (`.venv` is empty,
  `python` resolves to the Store stub). `tests/guardrails/test_redaction.py` is written but has
  never executed. Run it before trusting any of the above.
- **Paraphrase residual.** Tiers 0–2 catch identifiers. Tier 4 is probabilistic. A description that
  names nothing can still pass. The deferred two-store split (reason over an unredacted store,
  answer from a redacted one, in two passes) is the upgrade path if this proves too weak.

### Unmeasured

Whether architecture docs improve copilot reasoning is **unproven**. The §34 sweep (30/34 tool
selection) ran against an empty KB on a local setup that was never ingested, and tool selection is
prompt-driven by design. Treat the reasoning benefit as expected, not established.
