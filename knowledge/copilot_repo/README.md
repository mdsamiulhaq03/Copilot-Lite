# Net AI Copilot

AI-powered network and infrastructure copilot with multi-agent orchestration.

## Platform Integration

This submodule is integrated into root `cloudlynet_ai` as an application service that uses the **shared platform infra**:
- `postgres` (shared instance)
- `redis`
- `minio`
- `copilot-backend` (`8100`)
- `copilot-mcp-server` (`8082`)

Copilot isolation is implemented with **separate databases/schemas** in shared Postgres:
- `netai_copilot`
- `netai_copilot_test`
- local backend defaults use `netai_copilot_owner` for Alembic/test ergonomics; deployed runtime uses `netai_copilot_app`
- schema bundle: `design/copilot/copilot_schemas.sql` (root repo)
- shared-Postgres bootstrap/repair: `design/db/init_copilot.sql` (root repo)
- shared Postgres must expose `pgvector`
- curated RAG source of truth: `knowledge_base/`

Production access pattern is gateway-first:
- Frontend -> `maveric_platform_gateway` -> `/v1/tenants/{tenant_id}/copilot/**`
- Gateway -> copilot backend native tenant-scoped `/v1/tenants/{tenant_id}/copilot/**`

Production Kubernetes deployment path:
- Helm chart: `submodule/maveric-deployment/argocd/maveric_platform_copilot`
- Jenkins pipeline: `submodule/maveric-deployment/jenkins/maveric_platform_copilot.groovy`
- One Helm release deploys both `copilot-backend` and `copilot-mcp-server`
- Chart values must point at existing cluster Postgres, Redis, and object-storage services; the chart does not provision duplicate infra
- Current production values now replace placeholder env strings with concrete shared-infra runtime values. The runtime backend uses the dedicated `netai_copilot` database through the restricted `netai_copilot_app` role, while Alembic runs through a separate migration secret/job using `netai_copilot_owner`.
- The production chart now also packages a compressed snapshot of `knowledge_base/` and runs `scripts/ingest_knowledge_base.py` plus `scripts/contextualize_chunks.py --skip-existing` as an ArgoCD hook before backend/MCP pods roll.
- Gateway production values should target the rendered backend service DNS `http://copilot-backend.<namespace>.svc.cluster.local:8000`; the service name is defined in `submodule/maveric-deployment/argocd/maveric_platform_copilot/templates/backend-service.yaml` via `_helpers.tpl`.
- `CLOUDLYNET_API_KEY` remains an optional blank in the production chart until a dedicated gateway
  service credential is provided. `MCP_CLOUDLYNET_API_KEY` was removed in EPIC-8 — the MCP server
  forwards the caller's bearer instead

## API Routing Contract

- Copilot backend serves internal routes on:
  - `/v1/tenants/{tenant_id}/copilot/**`
  - plus `/health` and `/`
- Legacy direct backend aliases remain available on `/api/v1/**` for rollout/debug, compose health checks, and backend-only tooling.
- External tenant-prefixed copilot routes remain gateway-first, but gateway now forwards them unchanged to the matching backend path.
- CORS ownership is gateway-first in platform mode; backend CORS defaults to `ENABLE_CORS=false`.
- Gateway forwards `X-API-Key` from `COPILOT_BACKEND_API` to copilot upstream.

## Frontend Chat Flow (Session First)
1. `POST /v1/tenants/{tenant_id}/copilot/sessions` with `{query}`
2. Read `session_id` from response
3. `POST /v1/tenants/{tenant_id}/copilot/agents/query` with `{session_id, query}`
4. Reuse `session_id` for follow-up prompts
5. Browser clients must not call internal `/api/v1/**` routes directly
6. `GET /v1/tenants/{tenant_id}/copilot/agents` returns only the user-selectable agents:
   `debugger_agent`, `data_generation_agent`, and `offline_debugging_agent`
7. Omit `agent_id` to use backend auto-routing. Internal `reactive_agent` and
   `generic_agent` remain active in the backend and may still appear in
   `agent_response.agent_id` for auto-routed turns.

## Project Structure

```
.
├── knowledge_base/   # Curated RAG source-of-truth content
├── backend/          # FastAPI backend (Python 3.12, uv)
├── scripts/          # Validation and utility scripts
├── Agent.md
└── README.md
```

## Quick Start (Root Repo Recommended)

From root `cloudlynet_ai` repository:

```bash
docker compose -f docker-compose.infra.yml up -d
docker compose -f docker-compose.infra.yml -f docker-compose.apps.yml up -d --build copilot-backend copilot-mcp-server
docker compose -f docker-compose.infra.yml -f docker-compose.apps.yml exec -T copilot-backend \
  uv run alembic upgrade head
```

If the shared Postgres volume predates the copilot infra revamp, bootstrap the dedicated copilot database/roles first and then run Alembic before expecting native `/v1/tenants/{tenant_id}/copilot/health`, legacy `/api/v1/health`, or gateway-routed health to pass:

```bash
docker compose -f docker-compose.infra.yml exec -T postgres \
  psql -U postgres -d maveric \
  -v copilot_owner_user=netai_copilot_owner \
  -v copilot_owner_password=dev_password_change_in_prod \
  -v copilot_app_user=netai_copilot_app \
  -v copilot_app_password=dev_password_change_in_prod \
  -v copilot_db=netai_copilot \
  -v copilot_test_db=netai_copilot_test \
  < design/db/init_copilot.sql

docker compose -f docker-compose.infra.yml -f docker-compose.apps.yml exec -T copilot-backend \
  uv run alembic upgrade head
```

Health checks:
- Backend simple probe: `http://localhost:8100/health`
- Backend platform-native dependency probe: `http://localhost:8100/v1/tenants/00000000-0000-0000-3029-000000000000/copilot/health`
- Backend legacy direct dependency probe: `http://localhost:8100/api/v1/health`
- MCP server: `http://localhost:8082/health`
- Gateway-routed copilot (example tenant):
  `http://localhost:8080/v1/tenants/00000000-0000-0000-3029-000000000000/copilot/health`

## Local Backend Development

```bash
cd submodule/cloudlynet_ai_copilot/backend
cp .env.example .env
uv sync --all-extras
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

API docs: `http://localhost:8000/docs`

## Configuration

- `backend/.env` - backend app config
- `backend/.env.example` defaults target shared root infra services (`postgres`, `redis`, `minio`) and the dedicated copilot owner/test DBs used for local Alembic + pytest
- `build_version_prod.json` is the Jenkins version source for production copilot image promotion

## Validation

```bash
./scripts/validate.sh
./scripts/validate.sh --fix
```

## Notes

- Standalone infra assets inside this submodule were removed; root compose is the single source of truth.
- Existing shared Postgres environments need two explicit steps for copilot rollout: `design/db/init_copilot.sql` for role/database/extensions, then Alembic/schema migration.
- Production GitOps rollout now adds a third explicit copilot step in the deployment repo: sync the chart-packaged KB bootstrap hook so RAG content is available without a manual post-deploy loader run.
- Keep placeholder secrets in examples (`GROQ_API_KEY=your-groq-api-key-here`).
- Kubernetes/GitOps deployment is now defined in the sibling deployment submodule rather than inside this service repo.
- Frontend integration baseline is `design/upgrade_plans/frontend_agent.md`; the
  copilot data-generation delta is documented in root `frontend_agent_handover.md`.
