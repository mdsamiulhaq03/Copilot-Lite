# Copilot Integration Plan (Gateway-Routed, Production Approach)

**Date:** 2026-02-16  
**Scope:** Integrate `cloudlynet_ai_copilot` into `cloudlynet_ai` with gateway-first access, strict tenant/RBAC enforcement, and controlled cross-service CRUD/action execution.

Platform note:
- The 2026-03-12 Kafka training rollout changed the underlying rApp/BDT worker and deployment behavior, but did not change the copilot API contract. Root `kafka_plan.md` is the platform source of truth for those long-running training execution details, including the current `2`-partition / `2`-worker rApp baseline and the quoted-decimal timeout-env fix in deployment values.
- The 2026-03-20 Non-MRO rApp unification also introduced no direct copilot API change, but copilot-triggered rApp inference/comparison flows should now expect the aligned ES/LB/CCO text payload `tick + items[{cell_id, el_degree, on_off}]`.
- The 2026-03-22 Non-MRO day-scope payload fix still introduced no copilot API path change, but copilot-triggered day evaluations can now surface `per_tick_recommendations[{tick, items[]}]` and raw tick recommendation mirrors under `raw_tick_data[*].recommendations`.

## 1. Goals
- Make **Gateway** the single ingress for copilot APIs.
- Keep copilot data plane isolated from primary platform DB.
- Use shared platform infra (single source of truth) with dedicated copilot databases, not duplicated copilot infra containers.
- Allow copilot to perform safe CRUD/action calls on platform services (BDT, rApp, SMO, Data Sim) through governed interfaces.
- Preserve tenant isolation, auditability, and operational safety.

## 2. Target Access Pattern
- **Frontend -> Gateway -> Copilot Backend** for chatbot/session APIs.
- **Copilot Action Calls -> Gateway -> Platform Services** for operational tasks.
- No direct frontend calls to copilot backend in production.

Canonical external route prefix:
- `/v1/tenants/{tenant_id}/copilot/**`

Internal copilot service route prefix:
- `/v1/tenants/{tenant_id}/copilot/**`
- Legacy direct `/api/v1/**` aliases remain available for rollout/debug and compose/container probes.

### Frontend chat sequence (mandatory)
For a brand new conversation:
1. `POST /v1/tenants/{tenant_id}/copilot/sessions` with initial user prompt (`query`)
2. read `session_id` from response
3. `POST /v1/tenants/{tenant_id}/copilot/agents/query` with `{session_id, query}`

For follow-up turns:
1. reuse existing `session_id`
2. call `POST /v1/tenants/{tenant_id}/copilot/agents/query`

Notes:
- `POST /copilot/sessions` creates session record only (no assistant response).
- `POST /copilot/agents/query` is the message-generation endpoint.
- `GET /copilot/agents` returns only the user-selectable picker values:
  `debugger_agent`, `data_generation_agent`, `offline_debugging_agent`.
- Frontend should omit `agent_id` to use backend auto-routing. Internal
  `reactive_agent` and `generic_agent` remain implemented and may still appear
  in returned `agent_response.agent_id`.
- Browser must never call copilot internal `/api/v1/**` routes directly.
- Frontend origin must be allowed by gateway `CORS_ALLOW_ORIGINS` (CSV) for each deployment environment.

## 3. Network and Trust Boundaries
- Keep copilot databases isolated (`netai_copilot`, `netai_copilot_test`) on shared postgres infra.
- Keep root compose as the single source of truth for infra containers (no standalone copilot infra stack).
- Root `.env` is now the local bootstrap source of truth for copilot DB inputs: `COPILOT_POSTGRES_OWNER_*`, `COPILOT_POSTGRES_APP_*`, `COPILOT_POSTGRES_RUNTIME_DB`, `COPILOT_POSTGRES_TEST_DB`.
- Existing shared Postgres volumes or cluster DBs must run `artifacts/db/init_copilot.sql` before copilot is expected to pass `/v1/tenants/{tenant_id}/copilot/health` or the legacy direct `/api/v1/health` probe.
- Copilot schema rollout is three-step: shared-Postgres bootstrap first, schema bundle second, conversation-table RLS third.
- Root compose intentionally does not auto-run the copilot schema or RLS steps; run them separately before expecting local copilot health to pass.
- Production SQL rollout details, including tenant-isolation migration queries and runtime grants for `netai_copilot_app`, are documented in `artifacts/copilot/copilot_prod.md`.
- Shared Postgres must expose `pgvector` before the knowledge schema can be applied.
- Gateway and copilot backend must have controlled east-west connectivity.
- Preferred trust model:
  - Gateway validates Cognito JWT and RBAC.
  - Gateway forwards trusted identity context headers to copilot.
  - Copilot accepts calls only from gateway network segment (plus optional signed internal header).

Recommended forwarded headers:
- `X-Authenticated-User-Id`
- `X-Authenticated-User-Email`
- `X-Authenticated-Tenant-Id`
- `X-Authenticated-Role`
- `X-API-Key` (from gateway env `COPILOT_BACKEND_API`, default dev secret in local)
- `X-Request-ID`
- `traceparent`

## 4. Gateway Routing Contract
Add proxy routes in gateway for copilot:
- `GET    /v1/tenants/{tenant_id}/copilot/health          -> /v1/tenants/{tenant_id}/copilot/health`
- `GET    /v1/tenants/{tenant_id}/copilot/agents          -> /v1/tenants/{tenant_id}/copilot/agents`
- `POST   /v1/tenants/{tenant_id}/copilot/agents/query    -> /v1/tenants/{tenant_id}/copilot/agents/query`
- `PATCH  /v1/tenants/{tenant_id}/copilot/agents/query    -> /v1/tenants/{tenant_id}/copilot/agents/query`
- `POST   /v1/tenants/{tenant_id}/copilot/sessions        -> /v1/tenants/{tenant_id}/copilot/sessions`
- `GET    /v1/tenants/{tenant_id}/copilot/sessions        -> /v1/tenants/{tenant_id}/copilot/sessions`
- `GET    /v1/tenants/{tenant_id}/copilot/sessions/{id}/messages -> /v1/tenants/{tenant_id}/copilot/sessions/{id}/messages`
- `PATCH  /v1/tenants/{tenant_id}/copilot/sessions/{id}   -> /v1/tenants/{tenant_id}/copilot/sessions/{id}`
- `DELETE /v1/tenants/{tenant_id}/copilot/sessions/{id}   -> /v1/tenants/{tenant_id}/copilot/sessions/{id}`

Legacy direct `/api/v1/**` aliases remain available on the backend for rollout/debug and compose/container probes, but gateway no longer depends on them.

Gateway auth policy for copilot routes:
- Require same tenant match policy as other `/v1/tenants/{tenant_id}/**` routes.
- Allow `tenant_admin` and `tenant_user` (plus `cloudly_admin` with explicit tenant scope).

### Current implementation status (2026-02-16)
- Gateway copilot proxy routes are implemented.
- Gateway now forwards `/v1/tenants/{tenant_id}/copilot/**` unchanged to the copilot backend native tenant routes.
- Copilot backend now mounts tenant-prefixed routes directly under `/v1/tenants/{tenant_id}/copilot/...`, with direct `/api/v1/**` aliases retained for rollout/debug and compose probes.
- CORS ownership is gateway-first; copilot backend CORS middleware is disabled by default to avoid duplicate `Access-Control-*` headers through proxying.
- Gateway CORS middleware reads `CORS_ALLOW_ORIGINS` in all modes; release mode requires explicit values (no localhost fallback).
- Dependency-aware readiness should use copilot `/v1/tenants/{tenant_id}/copilot/health`; the direct alias `/api/v1/health` remains available for container probes, while `/health` is still the lightweight process check.
- Production chart env remediation (2026-03-10): `argocd/maveric_platform_copilot/values.yaml` now carries concrete asyncpg-style runtime env values instead of `REPLACE_ME_*` placeholders. The target rollout shape is a dedicated copilot runtime DB with a restricted app role; the SQL bootstrap/migration sequence is captured in `artifacts/copilot/copilot_prod.md`.
- Production knowledge-base remediation (2026-04-18): `argocd/maveric_platform_copilot` now also packages `files/knowledge_base.tgz` and runs a dedicated `copilot-backend-knowledge-base` hook after SQL migration so production RAG uses the same curated KB ingestion/contextualization flow as local Docker.
- Production gateway env remediation (2026-03-10): `argocd/maveric_platform_gateway/values.yaml` now points `COPILOT_BASE_URL` at the namespace-qualified backend Service DNS (`copilot-backend.<namespace>.svc.cluster.local:8000`), matching the rendered copilot chart service name.
- Platform Kafka note (2026-03-12): no copilot route or schema change was needed for the training-scale analysis. Root `kafka_plan.md` is the source of truth for the current rApp/BDT worker audit, Kafka Helm review, and local compose scaling plan that should guide copilot-triggered training actions, including the current `2`-partition / `2`-worker rApp baseline and the quoted-decimal timeout-env fix in deployment values.
- Platform Kafka infra note (2026-03-12): the sibling deployment repo now lets production Kafka/ZooKeeper reuse the shared `efs-pvc` claim already used by rApp/BDT and bootstraps those shared subpaths writable for Confluent's `uid=1000` runtime, so broker claims do not remain Pending or fail writable preflight in that cluster.
- Gateway runtime auth remediation (2026-03-10): prod/staging gateway values now set `DEV_BYPASS_JWT=false` and carry the internal microservice API keys (`BDT_API_KEY`, `RAPP_API_KEY`, `SMO_API_KEY`, `DATA_API_KEY`) required for gateway-mediated platform actions to reach the secured FastAPI services.
- Local Docker auth remediation (2026-03-12): if localhost starts returning downstream `Missing API key` on proxied routes after pulling gateway changes, rebuild/recreate `gateway`. The compose gateway is a compiled Go image and will otherwise keep running the stale binary.
- Local Docker Cognito remediation (2026-03-12): gateway platform-admin actions should use `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` copied from the deployment Helm gateway `secretData`, so local add-org tests mirror the working cluster runtime without depending on a developer `~/.aws` login.

## 5. Copilot-to-Platform Interaction Model
Use **Action Executor** inside copilot (or MCP tool adapter) that calls only gateway endpoints on an allowlist.

### 5.1 Action Categories
- **Read actions** (safe): list/status/health/log retrieval.
- **Write actions** (mutating): create/update/delete/train/infer/generate.

### 5.2 Guardrails
- Enforce per-action allowlist (method + path + JSON schema).
- Require confirmation for mutating actions (chat confirmation token or explicit "execute").
- Add idempotency keys for training/generation/inference triggers.
- Deny any call outside approved path templates.
- Apply timeout, retry policy, and circuit breaker per service.

## 6. Cross-Service CRUD/Action Matrix

### SMO Sim (Baselines / UE Data)
- Create baseline: `POST /v1/tenants/{tenant_id}/baselines`
- List baselines: `GET /v1/tenants/{tenant_id}/baselines`
- Update baseline: `PUT /v1/tenants/{tenant_id}/baselines/{baseline_id}`
- Delete baseline: `DELETE /v1/tenants/{tenant_id}/baselines/{baseline_id}`
- Upload/register UE dataset: `POST /v1/tenants/{tenant_id}/ue-data/datasets`
- Delete UE dataset: `DELETE /v1/tenants/{tenant_id}/ue-data/datasets/{dataset_id}`

### Data Sim (Synthetic Data Generation)
- Topology generation: `POST /v1/tenants/{tenant_id}/utils/topology/generate`
- Traffic-load generation: `POST /v1/tenants/{tenant_id}/utils/traffic-load/generate`
- Mobility generation: `POST /v1/tenants/{tenant_id}/utils/mobility/generate`

### BDT Engine
- Trigger train: `POST /v1/tenants/{tenant_id}/bdt/train`
- List models: `GET /v1/tenants/{tenant_id}/bdt`
- Get model: `GET /v1/tenants/{tenant_id}/bdt/models/{bdt_id}`
- Trigger inference: `POST /v1/tenants/{tenant_id}/bdt/models/{bdt_id}/infer`
- Poll inference: `GET /v1/tenants/{tenant_id}/bdt/models/{bdt_id}/infer/{run_id}`
- Training action guidance:
  - include `Idempotency-Key` for retrigger-safe train requests.
  - treat duplicate/train redelivery outcomes as non-fatal when model status is already terminal (`ready|failed`).

### rApp Engine
- Trigger train: `POST /v1/tenants/{tenant_id}/rapps/{rapp_id}/train`
- List models: `GET /v1/tenants/{tenant_id}/rapps/{rapp_id}/models`
- Trigger inference: `POST /v1/tenants/{tenant_id}/rapps/{rapp_id}/models/{rapp_model_id}/infer`
- Poll inference: `GET /v1/tenants/{tenant_id}/rapps/{rapp_id}/models/{rapp_model_id}/infer/{run_id}`
- Compare inference: `POST /v1/tenants/{tenant_id}/rapps/compare/infer`

### Logs / Diagnostics
- Service log queries through gateway log endpoints:
  - `/v1/tenants/{tenant_id}/utils/logs/errors`
  - `/v1/tenants/{tenant_id}/baselines/logs/errors`
  - `/v1/tenants/{tenant_id}/bdt/logs/errors`
  - `/v1/tenants/{tenant_id}/rapps/logs/errors`

## 7. Security and Compliance Controls
- Gateway remains policy enforcement point (JWT + RBAC + tenant match).
- Copilot action executor enforces a second policy layer (allowlist + schema validation).
- Persist immutable action audit logs in copilot DB (recommended new table):
  - `action_id`, `tenant_id`, `user_id`, `role`, `action_name`, `http_method`, `target_path`, `request_payload_hash`, `status_code`, `response_summary`, `created_at`.
- Redact secrets/PII in stored prompts, tool outputs, and traces.

## 8. Observability
- Propagate `X-Request-ID` and trace context end-to-end:
  - Frontend -> Gateway -> Copilot -> Gateway -> Target service.
- Metrics:
  - `copilot_action_requests_total{service,action,status}`
  - `copilot_action_latency_seconds{service,action}`
  - `copilot_action_denied_total{reason}`
- Structured logs with tenant/user/action identifiers.

## 9. Implementation Phases

### Phase P0 (Contract + Routing)
- Add gateway proxy routes for `/v1/tenants/{tenant_id}/copilot/**`.
- Add `COPILOT_BASE_URL` config in gateway.
- Update API contract and docs.

**Acceptance:** frontend can create session/query copilot only via gateway.

### Phase P1 (Identity + Auth Hardening)
- Replace demo user in copilot with gateway-forwarded identity context.
- Validate tenant/user context on every copilot request.

**Acceptance:** copilot writes session/message rows scoped to real user and tenant.

### Phase P2 (Action Executor + Safety)
- Implement allowlisted action executor for CRUD/train/infer/generate operations.
- Add mutating-action confirmation flow and idempotency keys.
- Add action audit log persistence.

**Acceptance:** copilot can safely trigger platform operations with full audit trail.

### Phase P3 (Production Hardening)
- Network policies (only gateway -> copilot ingress).
- Rate limits/quotas per tenant and per action class.
- SLOs, dashboards, alerting, failure playbooks.
- GitOps delivery assets:
  - unified Helm chart: `submodule/maveric-deployment/argocd/maveric_platform_copilot`
  - production Jenkins pipeline: `submodule/maveric-deployment/jenkins/maveric_platform_copilot.groovy`
  - chart must consume existing cluster Postgres, Redis, and object storage rather than provisioning duplicate infra
  - chart must also bootstrap the curated copilot knowledge base before backend/MCP rollout so RAG is usable immediately after sync
  - cluster Postgres must already have the copilot role/databases created and `pgvector` enabled before ArgoCD sync

**Acceptance:** production readiness checklist complete.

## 10. Rollback Strategy
- Feature flag in gateway: `ENABLE_COPILOT_PROXY=false` to disable routing instantly.
- Action executor kill switch: `COPILOT_ACTIONS_ENABLED=false` (chat-only mode).
- Keep direct copilot service endpoint internal-only for emergency diagnostics.

## 11. Open Decisions
- Final auth transport between gateway and copilot (signed headers vs mTLS + headers).
- Whether copilot mutating actions require dual confirmation for `tenant_user` role.
- Exact schema for action audit log and retention policy.

## 12. Frontend Execution Reference
- Frontend implementation tasks, route-by-route API coverage, and acceptance checklist are maintained in:
  - `artifacts/upgrade_plans/frontend_agent.md` (root repository, segmented by microservice: gateway/copilot/bdt/rapp/smo/data-sim).
  - `../frontend/API_Contracts.md` §7.0 (trial signup handoff plus `trial_user` access constraints, including copilot availability).
- Frontend must treat BDT inference as an async action:
  1. create run (`POST .../bdt/models/{bdt_id}/infer`);
  2. track `Location`/`run_id`;
  3. poll run status until `completed|failed`;
  4. render returned D3 plot groups + attachment metrics.
- No new frontend API route is required for BDT training stability hardening; existing `/bdt/train` + model status polling flow remains valid.
- Copilot branch rebase validation (2026-02-28) introduced no additional public copilot API route; frontend should continue using the same session-first contract.
