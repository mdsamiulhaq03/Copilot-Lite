# Environment Variables and Secrets Inventory

This document tracks runtime environment variables and secret keys used by microservices in this deployment repository.

## Notes
- This inventory is generated from chart templates and values under `argocd/`.
- Values are intentionally not expanded here; only variable/key names and sources are listed.
- As of 2026-08-10, **staging is retired**: staging infra was deleted on 2026-08-10 and all `staging-*` charts and Jenkins pipelines were moved, unmaintained, to `backup/argocd/` and `backup/jenkins/`. Per-service `### Staging` sections below are reduced to a pointer.
- As of 2026-08-10 (re-architecture merge), prod secret payloads gained the cross-service Network Digital Twin loop keys: rApp and Data Sim carry `NDT_BASE_URL`/`NDT_API_KEY`; BDT engine and the dedicated BDT worker carry `DATA_PLATFORM_BASE_URL`/`DATA_PLATFORM_API_KEY`. Gateway carries `BDT_API_KEY`/`RAPP_API_KEY`/`SMO_API_KEY`/`DATA_API_KEY` for internal proxy hops. **Key-parity rule:** `NDT_API_KEY` (rApp, Data Sim) = bdt-engine `API_KEY` = gateway `BDT_API_KEY`; `DATA_PLATFORM_API_KEY` (BDT engine/worker) = data-sim `API_KEY` = gateway `DATA_API_KEY`.
- As of 2026-08-10, this doc also lists, per service, re-architecture env vars that exist in service code with safe defaults but are deliberately **not** set in charts (dark-launch switches and inert connectors). See each service's "Service-code env not yet surfaced in charts" subsection.
- As of 2026-03-06, production app charts follow the values-driven secret and runtime overlay model (`secretData`, `env`, `additionalEnvFromSecrets`, worker overlays).
- As of 2026-03-07, production copilot onboarding uses a single chart (`argocd/maveric_platform_copilot`) that deploys backend + MCP together against existing cluster infra services.
- As of 2026-03-10, production Python-service `MONGODB_URL` values derive from `mongo-auth-secret` with an escaped root password and explicit `authSource=admin`; the repo does not currently provision a separate app-user secret.
- As of 2026-03-17, frontend, BDT engine, BDT worker, rApp, Data Sim, and SMO Sim all use chart-specific secret objects and require explicit `secretName` values; templates no longer fall back to a shared `maveric-aws` object.

## 1) Gateway

### Production-Track
- Chart: `argocd/maveric_platform_gateway`
- Deployment source: `envFrom.secretRef: maveric-aws-gateway`
- Secret file: `argocd/maveric_platform_gateway/templates/secret.yaml`
- Secret payload source: `argocd/maveric_platform_gateway/values.yaml` -> `secretData`
- Optional runtime overrides: `values.yaml` -> `env`, `additionalEnvFromSecrets`
- Runtime note:
  - `COPILOT_BASE_URL` should target the copilot backend Service FQDN `http://copilot-backend.<namespace>.svc.cluster.local:8000`, whose service name is rendered by `argocd/maveric_platform_copilot/templates/backend-service.yaml` and `_helpers.tpl`.
  - The Deployment uses a `wait-for-postgres` init container that relies on the same `POSTGRES_DSN` secret value to gate startup on `pg_isready`.
  - `BDT_API_KEY` must equal bdt-engine `API_KEY` (and rApp/data-sim `NDT_API_KEY`); `DATA_API_KEY` must equal data-sim `API_KEY` (and BDT `DATA_PLATFORM_API_KEY`). See the key-parity rule in Notes.
- Keys:
  - `AWS_ACCESS_KEY_ID`
  - `AWS_SECRET_ACCESS_KEY`
  - `AWS_DEFAULT_REGION`
  - `S3_BUCKET`
  - `S3_REGION`
  - `S3_PREFIX`
  - `PORT`
  - `APP_ENV`
  - `GIN_MODE`
  - `LOG_LEVEL`
  - `DEV_BYPASS_JWT`
  - `DEV_TENANT_ROLE`
  - `DEBUG_DEFAULT_TENANT`
  - `CORS_ALLOW_ORIGINS`
  - `CLOUDLYIO_ORG_UUID`
  - `CLOUDLY_ADMIN_EMAIL`
  - `COGNITO_REGION`
  - `COGNITO_USER_POOL_ID`
  - `COGNITO_APP_CLIENT_ID`
  - `COGNITO_JWKS_URL`
  - `COGNITO_JWT_ISS`
  - `AWS_REGION`
  - `REQUIRE_ADMIN_MEMBERSHIP`
  - `POSTGRES_DSN`
  - `REDIS_URL`
  - `BDT_BASE_URL`
  - `RAPP_BASE_URL`
  - `SMO_BASE_URL`
  - `DATA_BASE_URL`
  - `BDT_API_KEY`
  - `RAPP_API_KEY`
  - `SMO_API_KEY`
  - `DATA_API_KEY`
  - `COPILOT_BASE_URL`
  - `COPILOT_BACKEND_API`

### Staging
- Retired 2026-08-10 (staging infra deleted); chart preserved unmaintained at `backup/argocd/staging-maveric_platform_gateway`.

## 2) Frontend

### Production-Track
- Chart: `argocd/maveric_platform_frontend`
- Deployment source: `envFrom.secretRef: maveric-aws-frontend`
- Secret file: `argocd/maveric_platform_frontend/templates/secret.yaml`
- Secret payload source: `argocd/maveric_platform_frontend/values.yaml` -> `secretData`
- Optional runtime overrides: `values.yaml` -> `env`, `additionalEnvFromSecrets`
- Keys:
  - `AWS_ACCESS_KEY_ID`
  - `AWS_SECRET_ACCESS_KEY`
  - `AWS_DEFAULT_REGION`
  - `NEXT_PUBLIC_API_BASEURL`
  - `NEXT_PUBLIC_COGNITO_DOMAIN`
  - `NEXT_PUBLIC_COGNITO_CLIENT_ID`
  - `NEXT_PUBLIC_COGNITO_SCOPES`
  - `NEXT_PUBLIC_COGNITO_USE_PKCE`
  - `NEXT_PUBLIC_COGNITO_TOKEN_EXCHANGE`
  - `NEXT_PUBLIC_COGNITO_REDIRECT_URI`
  - `NEXT_PUBLIC_COGNITO_LOGOUT_URI`
  - `COGNITO_CLIENT_SECRET`
  - `NEXT_PUBLIC_S3_ENDPOINT_URL`
  - `NEXT_PUBLIC_S3_BUCKET`
  - `NEXT_PUBLIC_S3_REGION`
  - `NEXT_PUBLIC_S3_PREFIX`
  - `S3_BUCKET`
  - `S3_REGION`
  - `S3_PREFIX`

### Staging
- Retired 2026-08-10 (staging infra deleted); chart preserved unmaintained at `backup/argocd/staging-maveric_platform_frontend`.

## 3) BDT Engine and Worker

### Production-Track
- Chart: `argocd/maveric_platform_bdt_engine`
- Deployment source: `envFrom.secretRef: maveric-aws-bdt-engine`
- Worker source: `templates/bdt-worker.yaml` uses same secret
- Secret payload source: `argocd/maveric_platform_bdt_engine/values.yaml` -> `secretData`
- Production `MONGODB_URL` derives from the repo-managed `mongo-auth-secret` root credential, with escaped password and `authSource=admin`.
- Optional runtime overrides:
  - engine: `values.yaml` -> `env`, `additionalEnvFromSecrets`
  - worker: `values.yaml` -> `bdtWorker.env`, `bdtWorker.additionalEnvFromSecrets`
- Static env:
  - `OTEL_SDK_DISABLED` (engine deployment)
  - `OTEL_EXPORTER_OTLP_ENDPOINT` (worker template)
- New re-architecture keys:
  - `DATA_PLATFORM_BASE_URL` — data-sim base URL the feature builder pulls canonical PM windows from (`app/feature_builder/pm_source.py`).
  - `DATA_PLATFORM_API_KEY` — X-API-Key presented to data-sim; must equal data-sim `API_KEY` and gateway `DATA_API_KEY` (key-parity rule).
- Secret keys (`maveric-aws-bdt-engine`):
  - `AWS_ACCESS_KEY_ID`
  - `AWS_SECRET_ACCESS_KEY`
  - `AWS_DEFAULT_REGION`
  - `APP_NAME`
  - `APP_ENV`
  - `HOST`
  - `PORT`
  - `API_KEY`
  - `LOG_LEVEL`
  - `OTEL_SDK_DISABLED`
  - `DATABASE_URL`
  - `MONGODB_URL`
  - `REDIS_URL`
  - `KAFKA_BOOTSTRAP_SERVERS`
  - `S3_BUCKET`
  - `S3_REGION`
  - `S3_PREFIX`
  - `S3_ENDPOINT_URL`
  - `S3_BUCKET_ARN`
  - `S3_ASSUME_ROLE_ARN`
  - `S3_ASSUME_ROLE_EXTERNAL_ID`
  - `S3_ASSUME_ROLE_SESSION_NAME`
  - `AWS_ENDPOINT_URL`
  - `AWS_ENDPOINT_URL_S3`
  - `DATA_PLATFORM_BASE_URL`
  - `DATA_PLATFORM_API_KEY`

### Staging
- Retired 2026-08-10 (staging infra deleted); chart preserved unmaintained at `backup/argocd/staging-maveric_platform_bdt_engine`.

### Dedicated BDT Worker Chart
- Chart: `argocd/maveric_platform_bdt_worker` (staging twin retired to `backup/argocd/staging-maveric_platform_bdt_worker`)
- Deployment source: `envFrom.secretRef: maveric-aws-bdt-worker`
- Optional runtime overrides: `values.yaml` -> `env`, `additionalEnvFromSecrets`
- Secret payload source: `argocd/maveric_platform_bdt_worker/values.yaml` -> `secretData`
- Secret keys mirror `maveric-aws-bdt-engine` above, including `DATA_PLATFORM_BASE_URL`/`DATA_PLATFORM_API_KEY` (the worker's feature builder makes the same data-sim calls).
- The worker pods use the same image stream as BDT engine (`image.repository: cloudlyio/maveric-platform-bdt-engine-staging`); the engine Jenkins pipeline bumps both charts' `image.tag` (see `rollout_notes.md`).
- Worker timeout env defaults should stay quoted decimal strings (`"14400000"`, `"30000"`, `"10000"`) so the rendered env remains parseable by the current image.

### Service-code env not yet surfaced in charts (engine + worker)
Re-architecture env read via raw `os.getenv` with safe defaults; deliberately unset in charts:
- `NDT_ACTION_TTL_MIN` (default `60`) — minutes a dispatched loop action stays actionable (`app/services/loop/decision_hub.py`). Read per call in both engine and worker; **if ever set, it must be set identically for engine and worker**.
- `NDT_LOOP_CONSUMER_ENABLED` (default `true`) — worker-side loop consumer toggle (`app/workers/loop_consumer.py`).
- `LOOP_WATCH_TICK_SECONDS`, `LOOP_WATCH_PM_ATT_METRICS`, `LOOP_WATCH_PM_SUCC_METRICS` — feedback-watcher tick and PM metric-name overrides; defaults request both canonical and vendor RRC spellings (`app/services/loop/feedback_watcher.py`).
- `FEATURE_BUILDER_CONN_METRIC` — feature-builder connection-metric override (`app/feature_builder/pm_source.py`).

## 4) Data Sim

### Production-Track
- Chart: `argocd/maveric_platform_data_sim`
- Deployment source: `envFrom.secretRef: maveric-aws-data-sim`
- Secret payload source: `argocd/maveric_platform_data_sim/values.yaml` -> `secretData`
- Production `MONGODB_URL` derives from the repo-managed `mongo-auth-secret` root credential, with escaped password and `authSource=admin`.
- Optional runtime overrides: `values.yaml` -> `env`, `additionalEnvFromSecrets`
- New re-architecture keys:
  - `NDT_BASE_URL` — bdt_engine base URL for Network Digital Twin feature builds (`app/core/config.py`).
  - `NDT_API_KEY` — X-API-Key presented to bdt_engine; must equal bdt-engine `API_KEY` and gateway `BDT_API_KEY` (key-parity rule).
- Secret keys:
  - `AWS_ACCESS_KEY_ID`
  - `AWS_SECRET_ACCESS_KEY`
  - `AWS_DEFAULT_REGION`
  - `APP_NAME`
  - `APP_ENV`
  - `HOST`
  - `PORT`
  - `API_KEY`
  - `LOG_LEVEL`
  - `DATABASE_URL`
  - `MONGODB_URL`
  - `REDIS_URL`
  - `KAFKA_BOOTSTRAP_SERVERS`
  - `S3_BUCKET`
  - `S3_REGION`
  - `S3_PREFIX`
  - `S3_ENDPOINT_URL`
  - `S3_BUCKET_ARN`
  - `S3_ASSUME_ROLE_ARN`
  - `S3_ASSUME_ROLE_EXTERNAL_ID`
  - `S3_ASSUME_ROLE_SESSION_NAME`
  - `UTILS_INLINE_MAX_ROWS`
  - `UTILS_KAFKA_TOPIC`
  - `AWS_ENDPOINT_URL`
  - `AWS_ENDPOINT_URL_S3`
  - `NDT_BASE_URL`
  - `NDT_API_KEY`

### Staging
- Retired 2026-08-10 (staging infra deleted); chart preserved unmaintained at `backup/argocd/staging-maveric_platform_data_sim`.

### Service-code env not yet surfaced in charts
Defined in `app/core/config.py` with safe defaults; deliberately unset in charts:
- `INGEST_KAFKA_TOPIC` (default `maveric.ingest.pm.v1`) — Kafka topic for ingest jobs.
- `INGEST_CONSUMER_ENABLED` (default `true`) — background ingest consumer thread.
- `INGEST_CONSUMER_GROUP` (default `data-sim-ingest`) — consumer group; replicas share it to split partitions.
- `INGEST_BATCH_ROWS` (default `5000`) — rows per executemany chunk when writing canonical records.
- `NDT_FEATURE_BUILDER_MODE` (default `ndt_api`; `off` disables) and `NDT_BUILD_TIMEOUT_S` (default `1800`).

## 5) rApp

### Production-Track
- Chart: `argocd/maveric_platform_rapp`
- Deployment source: `envFrom.secretRef: maveric-aws-rapp`
- Worker source: `templates/rapp-worker.yaml` uses same secret
- Secret payload source: `argocd/maveric_platform_rapp/values.yaml` -> `secretData`
- Production `MONGODB_URL` derives from the repo-managed `mongo-auth-secret` root credential, with escaped password and `authSource=admin`.
- Optional runtime overrides:
  - engine: `values.yaml` -> `env`, `additionalEnvFromSecrets`
  - worker: `values.yaml` -> `workerEnv`, `workerAdditionalEnvFromSecrets`
- Rollout defaults:
  - `worker.replicaCount=2`
  - `worker.maxJobsPerPod=1`
  - `worker.maxPollIntervalMs="14400000"`
  - `worker.sessionTimeoutMs="30000"`
  - `worker.heartbeatIntervalMs="10000"`
- Static env in worker:
  - `OTEL_EXPORTER_OTLP_ENDPOINT`
- New re-architecture keys:
  - `NDT_BASE_URL` — bdt_engine base URL for the Network Digital Twin evaluate API; required for non-MRO inference (no local fallback remains).
  - `NDT_API_KEY` — X-API-Key presented to bdt_engine (this is the bdt service key, not rApp's own `API_KEY`); must equal bdt-engine `API_KEY` and gateway `BDT_API_KEY` (key-parity rule).
- Secret keys:
  - `AWS_ACCESS_KEY_ID`
  - `AWS_SECRET_ACCESS_KEY`
  - `AWS_DEFAULT_REGION`
  - `APP_NAME`
  - `APP_ENV`
  - `HOST`
  - `PORT`
  - `API_KEY`
  - `LOG_LEVEL`
  - `DATABASE_URL`
  - `MONGODB_URL`
  - `REDIS_URL`
  - `KAFKA_BOOTSTRAP_SERVERS`
  - `S3_BUCKET`
  - `S3_REGION`
  - `S3_PREFIX`
  - `S3_ENDPOINT_URL`
  - `S3_ENDPOINT`
  - `S3_BUCKET_ARN`
  - `S3_ASSUME_ROLE_ARN`
  - `S3_ASSUME_ROLE_EXTERNAL_ID`
  - `S3_ASSUME_ROLE_SESSION_NAME`
  - `BASELINE_HYST`
  - `BASELINE_TTT`
  - `NDT_BASE_URL`
  - `NDT_API_KEY`

### Staging
- Retired 2026-08-10 (staging infra deleted); chart preserved unmaintained at `backup/argocd/staging-maveric_platform_rapp`.

### Service-code env not yet surfaced in charts
Defined in `app/core/config.py` with safe defaults; deliberately unset in charts (dark-launch):
- `LOOP_PROPOSALS_ENABLED` (default `false`) — master switch for `maveric.loop.proposal.v1` emission; double-gated with the per-tenant `feature_flags['loop_proposals']`.
- `A1_EXECUTOR_ENABLED` (default `false`) — kill switch for the in-container `maveric.loop.action.v1` consumer for `adapter=a1_policy`; off means no consumer thread and no policy-service connection.
- `A1PMS_*` (`A1PMS_BASE_URL` default `None` = **connector inert**; plus `A1PMS_API_MODE`, `A1PMS_SERVICE_ID`, `A1PMS_TIMEOUT_S`, `A1PMS_MAX_RETRIES`, `A1PMS_KEEPALIVE_S`, `A1PMS_DEFAULT_RIC_ID`, `A1PMS_POLICY_TYPE_ID`) — OSC NONRTRIC A1 Policy Management Service connector.
- `NDT_EVAL_TIMEOUT_S` (default `900.0`), `NDT_POLL_INTERVAL_S` (default `2.0`) — evaluate-API budgets.
- `A1_EXECUTOR_GROUP_ID`, `A1_EXECUTOR_POLL_TIMEOUT_S`, `LOOP_ACTION_TOPIC`, `LOOP_FEEDBACK_TOPIC`, `LOOP_PROPOSAL_TOPIC`, `LOOP_DEFAULT_ADAPTER_HINT` — frozen-contract topic names and executor tuning.

## 6) SMO Sim

### Production-Track
- Chart: `argocd/maveric_platform_smo_sim`
- Deployment source: `envFrom.secretRef: maveric-aws-smo-sim`
- Secret payload source: `argocd/maveric_platform_smo_sim/values.yaml` -> `secretData`
- Production `MONGODB_URL` derives from the repo-managed `mongo-auth-secret` root credential, with escaped password and `authSource=admin`.
- Optional runtime overrides: `values.yaml` -> `env`, `additionalEnvFromSecrets`
- Secret keys:
  - `AWS_ACCESS_KEY_ID`
  - `AWS_SECRET_ACCESS_KEY`
  - `AWS_DEFAULT_REGION`
  - `APP_NAME`
  - `APP_ENV`
  - `HOST`
  - `PORT`
  - `API_KEY`
  - `PUBLIC_BASE_URL`
  - `LOG_LEVEL`
  - `DATABASE_URL`
  - `MONGODB_URL`
  - `REDIS_URL`
  - `KAFKA_BOOTSTRAP_SERVERS`
  - `S3_BUCKET`
  - `S3_REGION`
  - `S3_PREFIX`
  - `S3_ENDPOINT_URL`
  - `S3_BUCKET_ARN`
  - `S3_ASSUME_ROLE_ARN`
  - `S3_ASSUME_ROLE_EXTERNAL_ID`
  - `S3_ASSUME_ROLE_SESSION_NAME`
  - `AWS_ENDPOINT_URL`
  - `AWS_ENDPOINT_URL_S3`

### Staging
- Retired 2026-08-10 (staging infra deleted); chart preserved unmaintained at `backup/argocd/staging-maveric_platform_smo_sim`.

### Service-code env not yet surfaced in charts
Defined in `app/core/config.py` with safe defaults; deliberately unset in charts:
- `NANOLINK_CELL_DEVICE_MAP` (default `{}`) — JSON object mapping `cell_id` to `device_id`; the actuator seam that makes cell-scoped loop actions routable. Empty map means cell-scoped actions are rejected (not errored).
- `OCUDU_WS_ENABLED` (default `false`) — dark-launch switch for the outbound OCUDU metrics WebSocket collector; `OCUDU_WS_URLS`/`OCUDU_WS_TENANT_ID` (default `None`) stay unset with it.
- `SAS_BASE_URL` (default `None` = adapter reports disabled) plus `SAS_VERSION`, `SAS_DP_CERT_FILE`, `SAS_DP_KEY_FILE`, `SAS_CA_BUNDLE` — CBRS SAS placeholder adapter.
- `LOOP_ES_POWER_SAVE_DBM` (default `-20`), `LOOP_ES_POWER_NORMAL_DBM` (default `-10`) — ReferenceSignalPower writes for loop on/off actions.
- `LOOP_CONSUMER_GROUP_ID` (default `smo-sim-loop-executor`), `LOOP_CONSUMER_POLL_TIMEOUT_S` (default `1.0`) — closed-loop executor, gated entirely on `KAFKA_BOOTSTRAP_SERVERS`.
- `NYBSYS_SWEEP_INTERVAL_SECONDS` (default `30`) — command lease sweep period.

## 7) PostgreSQL

### Production-Track
- Chart: `argocd/maveric_platform_postgres`
- Deployment env vars:
  - `POSTGRES_USER`
  - `POSTGRES_PASSWORD` (from `secretKeyRef`)
  - `POSTGRES_DB`
  - `PGDATA`
- Secret:
  - `postgres-secret` key `password`
- Hooked migration sources:
  - `files/006_nybsys_ingestion.sql`, `files/008_nybsys_rng_seed.sql`, `files/009_nybsys_nanolink.sql`, `files/010_nybsys_cwmp_id_rename.sql` via `templates/nybsys-migration-{configmap,job}.yaml`
  - `files/007_trial_org.sql` via `templates/trial-migration-{configmap,job}.yaml`
  - `files/011_data_platform_canonical.sql` … `files/016_pm_ts_browse_index.sql` via `templates/rearch-migration-{configmap,job}.yaml`
  - `templates/copilot-bootstrap-job.yaml` (copilot DB/role bootstrap)
- Migration note:
  - All migration Jobs are ArgoCD `Sync` hooks against the shared `maveric` database using `postgres-secret`, ordered by `sync-wave`: copilot bootstrap (wave 1) → nybsys `006`→`008`→`009`→`010` (wave 2) → re-architecture `011`–`016` (wave 3, runs as the postgres superuser; all files idempotent; the hook re-runs on every sync) → trial `007` (wave 4). See `rollout_notes.md` for detail.

### Staging
- Retired 2026-08-10 (staging infra deleted); chart preserved unmaintained at `backup/argocd/staging-maveric_platform_postgres`.

## 8) MongoDB

### Production-Track
- Chart: `argocd/maveric_platform_mongodb`
- Deployment env vars:
  - `MONGO_INITDB_ROOT_USERNAME` (secret)
  - `MONGO_INITDB_ROOT_PASSWORD` (secret)
  - `MONGO_INITDB_DATABASE` (from values)
- Secret `mongo-auth-secret` keys:
  - `mongodb-root-username`
  - `mongodb-root-password`

### Staging
- Retired 2026-08-10 (staging infra deleted); chart preserved unmaintained at `backup/argocd/staging-maveric_platform_mongodb`.

## 9) Kafka

### Production-Track
- Chart: `argocd/maveric_platform_kafka`
- Static env vars:
  - `KAFKA_BROKER_ID`
  - `KAFKA_ZOOKEEPER_CONNECT`
  - `KAFKA_LISTENERS`
  - `KAFKA_ADVERTISED_LISTENERS`
  - `KAFKA_LISTENER_SECURITY_PROTOCOL_MAP`
  - `KAFKA_INTER_BROKER_LISTENER_NAME`
  - `KAFKA_AUTO_CREATE_TOPICS_ENABLE`
  - `KAFKA_NUM_PARTITIONS`
  - `KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR`
  - `KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR`
  - `KAFKA_TRANSACTION_STATE_LOG_MIN_ISR`
  - `KAFKA_LOG_RETENTION_HOURS`
  - `KAFKA_LOG_RETENTION_BYTES`
  - `KAFKA_LOG_DIRS`
  - `KAFKA_MIN_INSYNC_REPLICAS`
  - `KAFKA_CONFLUENT_SUPPORT_METRICS_ENABLE`
- Persistence defaults:
  - `persistence.existingClaim=efs-pvc`
  - `persistence.subPath=kafka`
  - `config.numPartitions="2"`
  - shared subpath bootstrap `chmod 0777`s `/shared/kafka` when `existingClaim` is used
- Topic management (`topicManagement.topics`, 7 topics): see `rollout_notes.md` for the current list including the single-partition `maveric.loop.*` topics.

### Staging
- Retired 2026-08-10 (staging infra deleted); chart preserved unmaintained at `backup/argocd/staging-maveric_platform_kafka`.

## 10) Zookeeper

### Production-Track
- Chart: `argocd/maveric-zookeeper`
- Static env vars:
  - `ZOOKEEPER_CLIENT_PORT`
  - `ZOOKEEPER_TICK_TIME`
  - `ZOOKEEPER_SYNC_LIMIT`
- Persistence defaults:
  - `persistence.existingClaim=efs-pvc`
  - `persistence.data.subPath=zookeeper/data`
  - `persistence.log.subPath=zookeeper/log`
  - shared subpath bootstrap `chmod 0777`s those directories when `existingClaim` is used

### Staging
- Retired 2026-08-10 (staging infra deleted); chart preserved unmaintained at `backup/argocd/staging-maveric-zookeeper`.

## 11) pgAdmin

### Production-Track
- Chart: `argocd/maveric-platform-pgadmin`
- Static env vars:
  - `PGADMIN_DEFAULT_EMAIL`
  - `PGADMIN_DEFAULT_PASSWORD_FILE`
  - `PGADMIN_SERVER_JSON_FILE`
  - `PGADMIN_REPLACE_SERVERS_ON_STARTUP`
  - `PGADMIN_CONFIG_CHECK_EMAIL_DELIVERABILITY`
  - `PGADMIN_CONFIG_ALLOW_SPECIAL_EMAIL_DOMAINS`
  - `PGADMIN_CONFIG_GLOBALLY_DELIVERABLE`
  - `PYTHONWARNINGS`
- Secret:
  - `pgadmin-password-secret` key `password.txt`
- ConfigMap:
  - `*-servers` with `/pgadmin4/servers.json` payload for the shared platform Postgres server

### Staging
- Retired 2026-08-10 (staging infra deleted); chart preserved unmaintained at `backup/argocd/staging-maveric-platform-pgadmin`.

## 12) Redis
- Chart: `argocd/maveric_platform_redis` (staging twin retired to `backup/argocd/staging-maveric_platform_redis`)
- Current deployment templates do not define explicit env vars or secret refs.

## 13) Copilot

### Production-Track
- Chart: `argocd/maveric_platform_copilot`
- Deployments:
  - backend -> Service `copilot-backend:8000`
  - MCP server -> Service `copilot-mcp-server:8080`
- Service name source:
  - `argocd/maveric_platform_copilot/templates/backend-service.yaml`
  - `argocd/maveric_platform_copilot/templates/_helpers.tpl` -> `maveric_platform_copilot.backendFullname`
- In-cluster backend DNS form used by gateway production values:
  - `http://copilot-backend.<namespace>.svc.cluster.local:8000`
- Deployment source:
  - both workloads use `envFrom.secretRef: maveric-aws-copilot`
  - optional runtime overrides:
    - backend: `values.yaml` -> `backend.env`, `backend.additionalEnvFromSecrets`
    - MCP: `values.yaml` -> `mcpServer.env`, `mcpServer.additionalEnvFromSecrets`
- Secret payload source: `argocd/maveric_platform_copilot/values.yaml` -> `secretData`
- Guardrail env (chart-level `backend.env`, non-secret; defaults mirror the app's Pydantic defaults so operators can flip mode/toggles without a code or image change; `GROQ_API_KEY` still arrives via the copilot secret):
  - `GUARDRAIL_ENABLED`
  - `GUARDRAIL_MODE`
  - `GUARDRAIL_SAFEGUARD_MODEL`
  - `GUARDRAIL_SAFEGUARD_TIMEOUT_S`
  - `GUARDRAIL_FAIL_OPEN`
  - `GUARDRAIL_PII_INPUT_ENABLED`
  - `GUARDRAIL_SAFEGUARD_INPUT_ENABLED`
- Key runtime expectation:
  - `DATABASE_URL`, `REDIS_URL`, and `S3_*` values must target already-running cluster services or external managed endpoints; this chart does not provision new infra.
  - `DATABASE_URL` / `TEST_DATABASE_URL` must follow the backend contract (`postgresql+asyncpg://...`), even when the source production DSN was provided as `postgres://...`.
  - Current production runtime should use the dedicated `netai_copilot` database through `netai_copilot_app`.
  - Manual Argo sync order for DB changes is `maveric_platform_postgres` first, then `maveric_platform_copilot`.
  - `argocd/maveric_platform_gateway/values.yaml -> secretData.COPILOT_BASE_URL` must point at the namespace-qualified backend service DNS, not only the short service hostname.
  - **`CLOUDLYNET_API_KEY` is stale**: the backend code no longer reads it — auth is forwarded per-request as the caller's Cognito JWT, and only `CLOUDLYNET_API_BASE_URL` is read (`backend/app/core/config.py`). The key remains in `secretData` and is harmless. The MCP server reads `MCP_CLOUDLYNET_BASE_URL`; **`MCP_CLOUDLYNET_API_KEY` was removed in EPIC-8** — it was never read, and outbound auth is the caller's forwarded bearer.
- Migration hook source:
  - SQL pack: `argocd/maveric_platform_copilot/files/`
  - Job template: `argocd/maveric_platform_copilot/templates/migration-job.yaml`
  - ConfigMap template: `argocd/maveric_platform_copilot/templates/migration-configmap.yaml`
  - Knowledge-base archive: `argocd/maveric_platform_copilot/files/knowledge_base.tgz`
  - Knowledge-base ConfigMap template: `argocd/maveric_platform_copilot/templates/knowledge-base-configmap.yaml`
  - Knowledge-base Job template: `argocd/maveric_platform_copilot/templates/knowledge-base-job.yaml`
  - Superuser password source: `postgres-secret` key `password`
- Migration secret keys (`maveric-aws-copilot-migration`, from `values.yaml` -> `migration.secretData`):
  - `DATABASE_URL`
  - `COPILOT_DATABASE`
  - `COPILOT_TEST_DATABASE`
  - `COPILOT_OWNER_USER`
  - `COPILOT_OWNER_PASSWORD`
  - `COPILOT_APP_USER`
  - `COPILOT_APP_PASSWORD`
- Secret keys (`maveric-aws-copilot`):
  - `APP_NAME`
  - `APP_ENV`
  - `DEBUG`
  - `SECRET_KEY`
  - `API_V1_PREFIX`
  - `DATABASE_URL`
  - `DATABASE_POOL_SIZE`
  - `DATABASE_MAX_OVERFLOW`
  - `TEST_DATABASE_URL`
  - `REDIS_URL`
  - `REDIS_CACHE_TTL`
  - `S3_ENDPOINT`
  - `S3_ACCESS_KEY`
  - `S3_SECRET_KEY`
  - `S3_BUCKET`
  - `ENABLE_CORS`
  - `CORS_ORIGINS`
  - `CORS_ALLOW_CREDENTIALS`
  - `ENABLE_METRICS`
  - `LOG_LEVEL`
  - `HEALTH_CHECK_TIMEOUT_SECONDS`
  - `HEALTH_CRITICAL_SERVICES`
  - `CLOUDLYNET_API_BASE_URL`
  - `CLOUDLYNET_API_KEY` (stale; unread by code, see above)
  - `MCP_CLOUDLYNET_BASE_URL`
  - ~~`MCP_CLOUDLYNET_API_KEY`~~ — removed in EPIC-8; drop it from any chart that still sets it
  - `MCP_REQUEST_TIMEOUT`
  - `MCP_LOG_LEVEL` — default `INFO`. The whole lifecycle trace. The audit logger
    (`mcp_mutation_audit`) and the trace logger are pinned to INFO independently, so raising this to
    `WARNING` quiets the server without silencing either. `DEBUG` additionally un-quiets `httpx`,
    `httpcore` and the MCP SDK, which log full tenant-scoped request URLs and bodies — a debugging
    setting, not a standing one.
  - `MCP_TRACE_DETAIL` — `off` | `basic` | `full`, default `basic`. **Use `basic` in production.**
    `full` adds argument values and upstream paths to every line, which raises the confidentiality
    class of the container's logs. Response bodies are never logged at any level.
  - `FASTMCP_LOG_ENABLED` — set `"false"`. Leaves the `fastmcp` logger propagating to our handler
    instead of its own rich/stderr one, so the container speaks a single log format.
  - `FASTMCP_CHECK_FOR_UPDATES` — set `"off"`. Otherwise the startup banner makes a blocking PyPI
    request worth up to 2s of every boot, in a container whose cache may not persist.
  - `CLOUDLYIO_ORG_UUID` — deliberately un-prefixed: the same variable the gateway reads for
    `RequirePlatformAdmin`, so one value configures both rules and they cannot drift. Required for
    `get_guardrail_decisions`; the gate fails closed and the tool stays unregistered when blank.
  - `EMBEDDING_MODEL`
  - `EMBEDDING_DIMENSION`
  - `RAG_TOP_K`
  - `RAG_SIMILARITY_THRESHOLD`
  - `GROQ_API_KEY`

### Staging
- No copilot staging chart ever existed; staging as a whole was retired 2026-08-10 (see `backup/argocd/`).

## CI Build-Time Environment Notes
From Jenkins scripts:
- Production-track pipelines build without active runtime `.env` injection; runtime env is owned by Helm/Kubernetes.
- Copilot production pipeline follows the same rule and builds environment-agnostic backend + MCP images before updating the single production copilot chart values file.
- Staging pipelines are retired and preserved unmaintained under `backup/jenkins/`.
- The BDT engine pipeline (`jenkins/maveric_platform_bdt_engine.groovy`) writes the new image tag into **both** `argocd/maveric_platform_bdt_engine/values.yaml` and `argocd/maveric_platform_bdt_worker/values.yaml`; the standalone `jenkins/maveric_platform_bdt_worker.groovy` pushes an image (`cloudlyio/bdt-worker-staging`) that no chart references — do not trigger it to deploy the worker.
