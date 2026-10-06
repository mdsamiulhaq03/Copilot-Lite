# cloudlynet_ai — Design Bundle

`artifacts/` is the **single source of truth** for architecture, contracts, and schema across the
platform. Submodules do not keep their own design docs; each carries a `README.md` that points here.

## Layout

```text
artifacts/
  openapi.yaml        # API contract (gateway-fronted surface)
  schemas.sql         # physical schema (mirrored by gateway db/migrations/schemas.sql)
  HLD.md              # high-level design
  LLD.md              # low-level design, per service
  db/                 # bootstrap + RLS SQL
  copilot/            # AI copilot design bundle
  deployment/         # staging/production delivery, env inventory, runbooks
  frontend/           # frontend architecture, UI, brand, routes
  marketing/          # product doc, positioning, ICP, sales motion, GTM, claims guardrails
  nanolink/           # NanoLink / NybSys integration + PM CSV input contract
  ric/                # RIC integration layer (NONRTRIC A1-PMS lab, ports/adapters, OCUDU, R1 packaging)
  upgrade_plans/      # kafka, migrations, frontend runbooks
```

## Source of truth, by concern

| Concern | Document |
|---|---|
| API contract | [`openapi.yaml`](./design/openapi.yaml) |
| Physical schema | [`schemas.sql`](./design/schemas.sql) — mirrored by gateway `db/migrations/schemas.sql` |
| Architecture | [`HLD.md`](./design/HLD.md), [`LLD.md`](./design/LLD.md) |
| Deployment & ops | [`deployment/`](./deployment/README.md) |
| Frontend | [`frontend/`](./frontend/README.md) |
| RIC integration layer | [`ric/`](./ric/README.md) — REST/JSON integration with an O-RAN SC NONRTRIC A1-PMS; **no O-RAN conformance claims**. E2/R1 facade docs archived at [`legacy/oran/`](./legacy/oran/README.md) |
| NanoLink / NybSys | [`nanolink/`](./nanolink/) |
| Product, positioning & GTM | [`marketing/`](./marketing/README.md) — **read [`marketing/claims-guardrails.md`](./marketing/claims-guardrails.md) before making any external claim** |
| AI Copilot | [`copilot/`](./copilot/) — see also `submodule/cloudlynet_ai_copilot/COPILOT_IMPLEMENTATION_SUMMARY.md` |
| **MCP response contract** (every tool, every server, every layer) | [`copilot/mcp-master-payload.md`](./copilot/mcp-master-payload.md) + JSON Schema [`copilot/mcp-envelope.schema.json`](./copilot/mcp-envelope.schema.json) — built by EPIC-8 S0 |
| Kafka rollout state | [`upgrade_plans/kafka_plan.md`](./upgrade_plans/kafka_plan.md) |
| Data migration workflow | [`upgrade_plans/datamigration.md`](./upgrade_plans/datamigration.md) |

### Copilot bootstrap SQL

- `artifacts/db/init_copilot.sql` — idempotent role/DB/extension repair for shared Postgres
- `artifacts/db/init_copilot_rls.sql` — conversation-table tenant/user isolation
- Copilot production env SoT: `submodule/maveric-deployment/argocd/maveric_platform_copilot/values.yaml`

### Kafka rollout baseline

- Production Kafka and ZooKeeper charts now default `persistence.existingClaim` to the shared `efs-pvc` claim already used by rApp/BDT, while staging keeps chart-managed PVCs.
- Shared Kafka/ZooKeeper subpaths are now permission-bootstrappped by init containers so the Confluent `uid=1000` processes can pass their writable-path preflight checks on the reused claim.
- Current rollout baseline is `maveric.rapp.train.v1=2`, `maveric.bdt.train.v1=2`, and `worker.replicaCount=2` for the rApp worker chart.
- Worker Kafka timeout values are now stored as quoted decimal strings in Helm values so rendered env vars stay `14400000` instead of Helm's scientific-notation form (`1.44e+07`), which the current worker images reject during `int(...)` parsing.

---
## Dev Onboarding:
### Submodule:
- Initialize after clone: git submodule init
- Fetch contents: git submodule update --recursive
- One-shot init + update: git submodule update --init --recursive
- git submodule add:
```bash
git submodule add git@github.com:CloudlyIO/maveric_platform_data_sim.git submodule/maveric_platform_data_sim
git submodule add git@github.com:CloudlyIO/maveric_platform_bdt_engine.git submodule/maveric_platform_bdt_engine
git submodule add git@github.com:CloudlyIO/maveric_platform_smo_sim.git submodule/maveric_platform_smo_sim
git submodule add git@github.com:CloudlyIO/maveric_platform_rapp.git submodule/maveric_platform_rapp
git submodule add git@github.com:CloudlyIO/maveric_platform_gateway.git submodule/maveric_platform_gateway
git submodule add git@github.com:CloudlyIO/cloudlynet_ai_copilot.git submodule/cloudlynet_ai_copilot
git submodule add git@github.com:cloudly-io/maveric-deployment.git submodule/maveric-deployment
git submodule add git@github.com:CloudlyIO/cloudlynet_edgeagent.git submodule/cloudlynet_edgeagent
git submodule add git@github.com:CloudlyIO/maveric_platform_frontend.git submodule/maveric_platform_frontend
```

> `maveric_platform_frontend` is a registered submodule at `submodule/maveric_platform_frontend`;
> its design docs live here under [`artifacts/frontend/`](./frontend/README.md).

### Tests - maveric_platform_tests
Update contract tests to hit each service's openapi.yaml and stitched gateway surface if needed.


### Notes on DB ownership & migrations

- Gateway now runs unified GORM auto-migrations at startup using `db/migrations/schemas.sql`, aligning with `artifacts/design/schemas.sql`.
- Fresh installs only need `artifacts/design/schemas.sql` (canonical baseline); migrations `001`-`005` and `cognito.sql` are already inlined for new setups. Incremental deltas + `cognito.sql` live in `artifacts/migration/`; the older partial `init.sql` and one-off `alter.sql` are archived at `artifacts/legacy/sql/`.
- `tenant_memberships` enforces one email per org (global unique on `email`) and requires `user_name` on insert.
- Tables by service of record (for app logic):
  - Gateway: `tenants`, `tenant_memberships`
  - SMO Sim: `baselines`, `ue_datasets` (`url_to_smo_ue_data_csv` is the canonical UE upload field; legacy `url_to_trainingdata_csv` remains accepted).
  - BDT Engine: `bdt_models`
  - rApp Engine: `rapp_models`, `inference_runs`
  - Shared job orchestration: `training_jobs`
- See [`upgrade_plans/datamigration.md`](./upgrade_plans/datamigration.md) for end-to-end developer workflow on generating Alembic revisions and letting the gateway orchestrate schema updates across environments.

### Utils traffic generator update

- Requests to `POST /v1/tenants/{tenant_id}/utils/traffic-load/generate` now accept `days`, `num_ues`, optional `spatial_params`/`time_params`, and load the referenced baseline topology from S3 before invoking the RADP spatial generator.
- The traffic-load endpoint always executes inline (no Kafka fallback) and returns the created dataset descriptor on success.
- Generated datasets are written to `s3://{tenant_id}/ue/{dataset_id}/synthetic_dataset.csv`; the service persists both the canonical `url_to_smo_ue_data_csv` and the legacy training alias for backwards compatibility.

## Local python setup (optional)
- Create venv: `python3 -m venv venv`
- Install deps: `pip install -r requirements.txt`
- Export env vars as needed per service (see submodule `.env` files for defaults).
- Run a service locally with `uvicorn app.main:app --reload --host 0.0.0.0 --port <port>`.

## Docker workflows
1. **Create the shared network (one-time, safe to rerun)**
   ```bash
   docker network create maveric
   ```

2. **Start infra (Postgres, Redis, Mongo, Kafka, MinIO, pgAdmin)**
   ```bash
   docker compose up -d
   ```
   - Shared Postgres uses `pgvector/pgvector:pg15` so copilot schema migrations can create `vector(384)` columns.
   - First-time bootstrap calls `artifacts/db/init_copilot_databases.sh` -> `artifacts/db/init_copilot.sql`.
   - Existing Postgres volumes need the same SQL rerun manually before copilot `/v1/tenants/{tenant_id}/copilot/health` or the legacy direct `/api/v1/health` probe will pass.
   - Local compose now provisions Kafka topics through `kafka-init` and preserves Kafka/ZooKeeper state through named volumes; use [`upgrade_plans/kafka_plan.md`](./upgrade_plans/kafka_plan.md) for the current rollout values and the future scaling backlog.

3. **Apply copilot schema and RLS separately**
   ```bash
   docker compose exec -T postgres \
     psql -U netai_copilot_owner -d netai_copilot < artifacts/copilot/copilot_schemas.sql

   docker compose exec -T postgres \
     psql -U postgres -d netai_copilot < artifacts/db/init_copilot_rls.sql
   ```
   - Root compose intentionally does not auto-run copilot schema/RLS migrations.
   - If you override local copilot DB settings, keep these names aligned: `COPILOT_POSTGRES_OWNER_USER`, `COPILOT_POSTGRES_OWNER_PASSWORD`, `COPILOT_POSTGRES_APP_USER`, `COPILOT_POSTGRES_APP_PASSWORD`, `COPILOT_POSTGRES_RUNTIME_DB`, `COPILOT_POSTGRES_TEST_DB`.
   - Use `artifacts/copilot/copilot_prod.md` for the production SQL runbook.

4. **Start or rebuild all applications together**
   ```bash
   docker compose --profile apps up -d --build
   ```
   - After pulling gateway auth/proxy changes, force-recreate the compiled gateway container before localhost testing:
     `docker compose --profile apps up -d --build --force-recreate gateway`
     Otherwise the old binary can keep omitting the internal service `X-API-Key` headers and the frontend will see downstream `Missing API key` failures on proxied `/v1` routes even if the local env files are already aligned.
   - Local platform-admin flows (`POST /v1/admin/tenants`, platform-admin creation, tenant-admin creation) also require Cognito-capable AWS credentials inside the gateway container. Keep `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` in `submodule/maveric_platform_gateway/.env` aligned with `submodule/maveric-deployment/argocd/maveric_platform_gateway/values.yaml` `secretData` (or the matching staging chart).

5. **Rebuild a single service without touching infra** (example: `bdt-worker`)
   ```bash
   docker compose --profile apps up --no-deps --build bdt-worker
   ```

6. **Stop only the application layer**
   ```bash
   docker compose --profile apps stop gateway bdt-engine bdt-worker rapp rapp-worker smo-sim data-sim
   ```

7. **Shut everything down (apps + infra)**
   ```bash
   docker compose --profile apps down
   ```

8. **Check Postgres tables**
   ```bash
   docker exec -it postgres psql -U postgres -d maveric -c "\\dt"
   ```
