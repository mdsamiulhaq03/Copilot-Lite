# Net AI Copilot - Backend

FastAPI backend with multi-agent AI orchestration powered by LangGraph.

## Architecture

```
backend/
├── app/
│   ├── agents/                # AI agent implementations
│   ├── api/v1/endpoints/      # REST API endpoints
│   ├── core/                  # config, auth, database, exceptions
│   ├── models/                # SQLAlchemy ORM models
│   ├── schemas/               # Pydantic request/response schemas
│   ├── services/              # business logic layer
│   ├── mcp_server/            # MCP server + platform tools
│   └── main.py                # FastAPI entry point
├── alembic/                   # database migrations
├── scripts/
├── tests/
├── pyproject.toml
└── uv.lock
```

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Running shared root infra services: `postgres`, `redis`, `minio`

## Setup

```bash
cd submodule/cloudlynet_ai_copilot/backend
cp .env.example .env
uv sync --all-extras
```

## Run Server

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

- API: `http://localhost:8000`
- Docs: `http://localhost:8000/docs`
- Health: `http://localhost:8000/health`
- Platform-native dependency-aware health: `http://localhost:8000/v1/tenants/{tenant_id}/copilot/health`
- Legacy direct dependency-aware health: `http://localhost:8000/api/v1/health`

## Database Migrations

Copilot uses separate databases on shared root Postgres:
- runtime/staging-prod DB: `netai_copilot`
- test DB: `netai_copilot_test`

Bootstrap the shared Postgres role/databases/extensions first when the volume or cluster DB already existed before copilot was moved onto shared infra. In Kubernetes, the shared Postgres chart now includes a bootstrap Job that creates:
- owner role: `netai_copilot_owner`
- runtime role: `netai_copilot_app`
- dedicated databases: `netai_copilot`, `netai_copilot_test`

Local backend defaults keep using `netai_copilot_owner` in `.env.example` so Alembic and pytest can manage schema without a second DSN swap. The deployed runtime chart still uses `netai_copilot_app`.

For manual recovery, run:
Run this command from the root `cloudlynet_ai` repository.

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
```

Apply schema migrations:

```bash
uv run alembic upgrade head
```

Shared Postgres must expose `pgvector` before the knowledge-schema migration can succeed. Local root compose now uses `pgvector/pgvector:pg15`.

Create new migration:

```bash
uv run alembic revision --autogenerate -m "your message"
```

## Tests

```bash
uv run pytest tests/ -v
```

Default local test DSN assumes shared Postgres on `localhost:5432`, the `netai_copilot_test` database, and the owner role `netai_copilot_owner`. Override with `TEST_DATABASE_URL` when needed.

## Code Quality

```bash
uv run black --check app/ tests/
uv run ruff check app/ tests/
uv run mypy app/main.py app/core/config.py app/api/v1/router.py
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check (DB, Redis, S3) |
| GET | `/v1/tenants/{tenant_id}/copilot/health` | Dependency-aware health used by native platform traffic |
| GET | `/v1/tenants/{tenant_id}/copilot/agents` | List user-selectable agents |
| POST | `/v1/tenants/{tenant_id}/copilot/agents/query` | Send query to AI agents |
| PATCH | `/v1/tenants/{tenant_id}/copilot/agents/query` | Update an existing query version |
| GET | `/v1/tenants/{tenant_id}/copilot/sessions` | List conversation sessions |
| POST | `/v1/tenants/{tenant_id}/copilot/sessions` | Create new session |
| GET | `/v1/tenants/{tenant_id}/copilot/sessions/{session_id}/messages` | List session messages |
| PATCH | `/v1/tenants/{tenant_id}/copilot/sessions/{session_id}` | Update session title |
| DELETE | `/v1/tenants/{tenant_id}/copilot/sessions/{session_id}` | Delete session |
| GET | `/v1/tenants/{tenant_id}/copilot/users/profile` | Current user profile |
| GET | `/v1/tenants/{tenant_id}/copilot/users/settings` | Current user settings |

Gateway-routed production path:
- `/v1/tenants/{tenant_id}/copilot/**`
- Legacy direct aliases remain available under `/api/v1/**` for local probes and backend debugging.
- Public `/copilot/agents` now returns only `debugger_agent`,
  `data_generation_agent`, and `offline_debugging_agent`.
- Omit `agent_id` on `/copilot/agents/query` to use backend auto-routing.
  Internal `reactive_agent` and `generic_agent` remain implemented and may
  still appear in `agent_response.agent_id`.

## Deployment

Production deployment assets live outside this repo in the deployment submodule:
- Helm chart: `submodule/maveric-deployment/argocd/maveric_platform_copilot`
- Jenkins pipeline: `submodule/maveric-deployment/jenkins/maveric_platform_copilot.groovy`

The production chart deploys:
- `copilot-backend` on service port `8000`
- `copilot-mcp-server` on service port `8080`

It reuses existing cluster Postgres, Redis, and object-storage services via values-driven secret data.
- The target cluster Postgres service must already have the copilot role/databases created and `pgvector` installed or enabled before the chart is synced.
- The same chart now also runs a `copilot-backend-knowledge-base` hook job that expands the packaged `knowledge_base` snapshot and executes:
  - `uv run python scripts/ingest_knowledge_base.py`
  - `uv run python scripts/contextualize_chunks.py --skip-existing`
- The source-of-truth KB content remains `knowledge_base/`; the deployment chart carries a compressed copy for GitOps rollout.

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SECRET_KEY` | Yes | App secret key |
| `DATABASE_URL` | Yes | PostgreSQL connection URL |
| `TEST_DATABASE_URL` | No | Test DB URL |
| `REDIS_URL` | Yes | Redis connection URL |
| `S3_ENDPOINT` | Yes | S3/MinIO endpoint |
| `S3_ACCESS_KEY` | Yes | S3 access key |
| `S3_SECRET_KEY` | Yes | S3 secret key |
| `S3_BUCKET` | Yes | S3 bucket name |
| `GROQ_API_KEY` | Yes | Groq API key for LLM |
| `CLOUDLYNET_API_BASE_URL` | No | Gateway base URL used by backend-side platform clients. Auth is forwarded per-request as the caller's JWT |
| `MCP_CLOUDLYNET_BASE_URL` | No | Gateway base URL used by the MCP server. The standalone server needs no tenant variable: tenant and token both come from the connection JWT |
| `MCP_REQUEST_TIMEOUT` | No | MCP server gateway request timeout in seconds |
| `ENABLE_CORS` | No | Enable backend CORS (standalone mode only) |
| `CORS_ORIGINS` | No | Allowed CORS origins |
| `CORS_ALLOW_CREDENTIALS` | No | Backend CORS credentials toggle |

## Notes

- Keep `.env.example` non-secret (no real API keys).
- Root compose is the infrastructure source of truth; this backend does not ship standalone infra assets.
- Existing shared Postgres environments require `design/db/init_copilot.sql` plus Alembic before full copilot readiness.
- `build_version_prod.json` at the submodule root is used by the production Jenkins pipeline for image version promotion.
