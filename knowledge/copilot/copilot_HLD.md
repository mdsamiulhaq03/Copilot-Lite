# CloudlyNet Copilot - High-Level Design

**Version:** 0.1.0
**Status:** Active Development
**Scope:** Copilot backend + MCP server on shared platform infra with dedicated copilot data domains

Platform note:
- Platform-side rApp inference now unifies ES, LB, and CCO into one Non-MRO family. Copilot architecture is unchanged, but any surfaced Non-MRO recommendation payload should be treated as `tick + items[{cell_id, el_degree, on_off}]`.
- Day-scope Non-MRO `/infer` responses now also expose `per_tick_recommendations[{tick, items[]}]`; when raw tick expansions are requested, `raw_tick_data[*].recommendations` mirrors that same payload.

## 1. Goals and Scope
- Provide an AI copilot for platform operations with multi-agent orchestration.
- Use Gateway as production ingress for copilot APIs.
- Keep copilot data isolated from primary CloudlyNet platform schema/data.
- Expose REST APIs for sessions, messages, and agent queries.
- Support RAG with pgvector-based retrieval.
- Integrate with platform services via MCP tools through gateway APIs.

Out of scope (current phase):
- Production authentication/SSO (backend still demo identity).
- Gateway-signed identity propagation and service-to-service auth hardening beyond local/demo mode.
- Frontend delivery details (tracked separately in `artifacts/upgrade_plans/frontend_agent.md` and `../frontend/API_Contracts.md` §7.0).

## 2. System Context
Copilot submodule:
- `submodule/cloudlynet_ai_copilot`

Logical components:
- **Copilot Backend (FastAPI)**: native `/v1/tenants/{tenant_id}/copilot/**` session/message/agent endpoints, with legacy direct `/api/v1/**` aliases retained for rollout/debug and compose probes.
- **Gateway Copilot Routes**: `/v1/tenants/{tenant_id}/copilot/**` with auth/RBAC.
  - Gateway forwards the tenant-scoped path unchanged to the backend native route.
  - Gateway injects `X-API-Key` from `COPILOT_BACKEND_API`.
  - Gateway owns browser CORS policy (`CORS_ALLOW_ORIGINS`).
  - In local Docker, gateway Cognito-backed platform-admin actions should use `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` mirrored from the deployment Helm gateway `secretData`.
- **Agent Orchestrator (LangGraph)**: route + execute internal/public copilot agents (`reactive`, `debugger`, `data_generation`, `generic`, `offline_debugging`).
- **RAG Layer**: ingestion/retrieval over `knowledge.*`.
- **MCP Server (FastMCP SSE)**: calls gateway APIs for allowlisted platform operations.

Shared infra dependencies:
- `postgres` (shared instance; dedicated copilot DBs)
- `redis`
- `minio`
- In Kubernetes, these dependencies are consumed from existing cluster services; the copilot chart does not provision new DB/cache/object-store workloads.
- Existing shared Postgres volumes or cluster DBs must run `artifacts/db/init_copilot.sql` before copilot is expected to pass dependency health checks.
- Local compose and production rollout intentionally keep bootstrap, schema, and RLS separate:
  - `artifacts/db/init_copilot.sql`
  - `artifacts/copilot/copilot_schemas.sql`
  - `artifacts/db/init_copilot_rls.sql`
- Shared Postgres must expose `pgvector` before copilot knowledge-schema migration can run.

## 3. Deployment Topology
- Root compose is infra source of truth.
- Copilot backend + MCP server run on shared `maveric` network.
- Production Kubernetes/GitOps source of truth is `submodule/maveric-deployment/argocd/maveric_platform_copilot`, with image promotion from `submodule/maveric-deployment/jenkins/maveric_platform_copilot.groovy`.
- One Helm release deploys both `copilot-backend` and `copilot-mcp-server` so gateway proxy and MCP tooling remain version-aligned.
- The same Helm release now packages a compressed snapshot of `submodule/cloudlynet_ai_copilot/knowledge_base` and replays the local RAG bootstrap flow (`ingest_knowledge_base.py` + `contextualize_chunks.py --skip-existing`) as an ArgoCD hook before runtime pods roll.
- Production chart values now carry concrete shared-infra runtime envs instead of placeholders: asyncpg-formatted Postgres DSNs, shared Redis URL, shared S3 endpoint/credentials, and internal gateway base URLs. Provision the dedicated copilot DB/roles/grants first using `artifacts/copilot/copilot_prod.md`, then point runtime traffic at `netai_copilot`.
- Gateway production values should target the copilot backend via the rendered service DNS `http://copilot-backend.<namespace>.svc.cluster.local:8000`; the service name is emitted by `templates/backend-service.yaml` via `backendFullname`.
- Gateway cluster values must also keep `DEV_BYPASS_JWT=false` and carry the non-copilot microservice API keys (`BDT_API_KEY`, `RAPP_API_KEY`, `SMO_API_KEY`, `DATA_API_KEY`) so copilot-triggered platform actions still traverse the same authenticated gateway path used by the UI.
- Copilot isolation model:
  - dedicated roles: `netai_copilot_owner`, `netai_copilot_app`
  - dedicated databases: `netai_copilot`, `netai_copilot_test`
  - dedicated schema bundle: `artifacts/copilot/copilot_schemas.sql`
  - dedicated bucket namespace on shared MinIO: `netai-copilot-files`
  - production SQL rollout runbook: `artifacts/copilot/copilot_prod.md`
  - local env source of truth: root `.env` keys `COPILOT_POSTGRES_OWNER_USER`, `COPILOT_POSTGRES_OWNER_PASSWORD`, `COPILOT_POSTGRES_APP_USER`, `COPILOT_POSTGRES_APP_PASSWORD`, `COPILOT_POSTGRES_RUNTIME_DB`, `COPILOT_POSTGRES_TEST_DB`

## 4. Data Domains
Copilot schema domains:
- `conversation`
  - `conversation_session`
  - `conversation_message`
  - `conversation_message_version`
  - all three tables carry `tenant_id` and `user_id`
- `knowledge`
  - `document_source`
  - `document`
  - `document_chunk` (`vector(384)` embeddings)

## 5. API Surface
- Gateway-routed public APIs: `/v1/tenants/{tenant_id}/copilot/**`
- Backend native APIs: `/v1/tenants/{tenant_id}/copilot/**`
- Legacy direct backend aliases remain under `/api/v1/**` for rollout/debug and compose/container probes.
- Endpoints:
  - `GET /health`, `GET /`
  - `GET /v1/tenants/{tenant_id}/copilot/health`, `/live`, `/ready`
  - `GET /v1/tenants/{tenant_id}/copilot/users/profile`, `/settings`
  - `POST/GET /v1/tenants/{tenant_id}/copilot/sessions`
  - `PATCH/DELETE /v1/tenants/{tenant_id}/copilot/sessions/{session_id}`
  - `GET /v1/tenants/{tenant_id}/copilot/sessions/{session_id}/messages`
  - `GET /v1/tenants/{tenant_id}/copilot/agents`
  - `POST/PATCH /v1/tenants/{tenant_id}/copilot/agents/query`

Contract reference: `artifacts/copilot/copilot_openapi.yaml`.

## 6. Core Flows
### 6.1 Session-first frontend flow
1. `POST /v1/tenants/{tenant_id}/copilot/sessions` with `{query}`
2. read `session_id`
3. `POST /v1/tenants/{tenant_id}/copilot/agents/query` with `{session_id, query}`
4. reuse same `session_id` for follow-ups
5. `GET /v1/tenants/{tenant_id}/copilot/agents` returns only the user-selectable
   picker values: `debugger_agent`, `data_generation_agent`, `offline_debugging_agent`
6. omit `agent_id` to use backend auto-routing; hidden internal agents
   `reactive_agent` and `generic_agent` can still appear in `agent_response.agent_id`

### 6.2 MCP/platform actions
- MCP tools call gateway allowlisted endpoints (rApp compare, logs, inference actions).
- Mutating actions require explicit confirmation + policy checks.
- BDT train actions should forward `Idempotency-Key`.

## 7. Operational Notes
- Health validates DB, Redis, and S3 connectivity.
- Dependency-aware readiness is `/v1/tenants/{tenant_id}/copilot/health`; the direct alias `/api/v1/health` remains available for compose/container probes, and `/health` is only a lightweight process probe.
- Root compose intentionally does not auto-run copilot schema/RLS migration. Bootstrap the DB first, then apply `artifacts/copilot/copilot_schemas.sql`, then `artifacts/db/init_copilot_rls.sql`, then start or restart copilot services.
- Production GitOps now keeps the same sequencing model but adds a KB stage inside the chart: migration hook wave 1, knowledge-base hook wave 2, backend/MCP deployments wave 3.
- No copilot API or schema change was required for the 2026-03-12 Kafka training rollout. The underlying rApp/BDT worker, Kafka Helm, and local compose implementation status is tracked centrally in root `kafka_plan.md`, including the current `2`-partition / `2`-worker rApp baseline and the quoted-decimal worker timeout env fix in deployment values.
- The sibling deployment repo now lets Kafka/ZooKeeper reuse the shared production `efs-pvc` claim already used by rApp/BDT and bootstraps those subpaths writable for Confluent's `uid=1000` runtime, preventing copilot-triggered training flows from stalling behind Pending or non-writable broker storage in that cluster.
- Copilot branch rebase validation (2026-02-28) produced no net API/schema change.
- Tenant-isolation upgrade path for pre-RLS databases is documented in `artifacts/copilot/copilot_prod.md` and implemented for production by the ordered SQL migration pack in `submodule/maveric-deployment/argocd/maveric_platform_copilot/files/`.
- Env template guardrail: `backend/.env.example` keeps placeholder secrets and shared infra hosts (`postgres`, `redis`, `minio`).
- Local Docker guardrail: after gateway proxy/auth changes, rebuild/recreate `gateway` before browser testing. A stale gateway binary can keep missing the upstream `X-API-Key` injection and make copilot-adjacent dashboard calls fail even though env files are already aligned.
- Current production chart leaves `CLOUDLYNET_API_KEY` blank because no dedicated gateway service
  credential is stored in-repo. `MCP_CLOUDLYNET_API_KEY` was removed in EPIC-8 — the MCP server never
  read it, and forwards the caller's bearer per request.
- Frontend implementation checklist is `artifacts/upgrade_plans/frontend_agent.md` (microservice-segmented).
- Trial-user frontend delta, including trial access to copilot, is `../frontend/API_Contracts.md` §7.0.
