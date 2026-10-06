# CloudlyNet — Low‑Level Design

**Version:** 0.7.0
**Version lockstep:** the three canonical design docs (HLD.md, LLD.md, openapi.yaml) version-bump together. Any PR that changes one bumps all three to the same version.
**Covers:** repo layout, key modules, environment, request lifecycle, DB/RLS handling, metrics/logs, error model.

**Re-architected service roles** (containers/ports unchanged; see HLD §2): data_sim :8003 = **Data Platform**, bdt_engine :8000 = **Network Digital Twin** (+ loop decision hub), rapp :8001 = **RAN Intelligence** (+ RIC integration layer `app/ric/`), smo_sim :8002 = **Actuation & Integration** (actuator adapter framework; E2/R1 facades deleted).

-----

## 0\. Cross‑cutting

### Response Envelope (for every API)

**Success**

```json
{
  "success": true,
  "timestamp": "ISO-8601",
  "message": "optional",
  "data": { ... },
  "errors": []
}
```

**Error**

```json
{
  "success": false,
  "timestamp": "ISO-8601",
  "message": "details",
  "data": {},
  "errors": [{ "code": "VALIDATION_ERROR", "details": {...}}]
}
```

### Required headers

  - `Authorization: Bearer <Cognito ID token>` (except health). Gateway requires `token_use == "id"`.
  - Gateway attaches: `X-Request-ID`, `traceparent`.
  - Services include both in responses; Data Sim also emits `X-Request-ID` via middleware if the gateway is bypassed.

### Tenant handling in Python services

Extract `{tenant_id}` from the path; on request start:

```python
session.execute("SELECT set_config('app.current_tenant', :tid, true)", {"tid": tenant_id})
```

All SQL reads/writes happen after this call (RLS).

### Observability

  - **Tracing**: OTEL SDK; span attributes: `tenant_id`, `request_id`, `route`.
  - **Metrics**: Prom histograms for request durations; counters per status.
  - **Logs**: JSON; include `tenant_id`, `request_id`, `trace_id`, `user_id`. Each FastAPI service (BDT, rApp, SMO Sim, Data Sim) uses middleware to attach `X-Request-ID`, populate tenant/request contextvars for log enrichment, and emit request lifecycle logs to STDOUT **and** MongoDB `application_logs` (TTL by severity) when `MONGODB_URL` is set. HTTP/validation/unhandled errors are persisted via `log_error_to_mongodb()` into `error_logs` (90‑day TTL) with indexes on `{tenant_id, service_name, created_at}`. Log inspection endpoints are service-scoped: Data Sim `/v1/tenants/{tenant_id}/utils/logs/errors|.../resolve|/logs/stats`, SMO Sim `/v1/tenants/{tenant_id}/baselines/logs/errors|...`, rApp `/v1/tenants/{tenant_id}/rapps/logs/errors|...`, BDT `/v1/tenants/{tenant_id}/bdt/logs/errors|...`; Mongo health at `/v1/logs/health`. When Mongo is absent the services continue with STDOUT-only logging and still emit `X-Request-ID`. All services expose `/health` for container probes.

### Kafka topics (declaratively created by the kafka chart topics-job and compose init-topics.sh)

| Topic | Producer → Consumer | Notes |
|---|---|---|
| `maveric.bdt.train.v1` | bdt_engine API → bdt-worker | unchanged |
| `maveric.rapp.train.v1` | rapp API → rapp-worker | unchanged |
| `maveric.ingest.pm.v1` | producers → data_sim consumer (in the API container) | `kind=job` ingest jobs + `kind=records` streaming batches (frozen HLD A.5) |
| `maveric.loop.proposal.v1` | rapp → bdt_engine decision hub | frozen HLD A.1; REST mirror `POST /ndt/loop/proposals` |
| `maveric.loop.action.v1` | bdt_engine decision hub → executors (smo_sim actuators, rapp `a1_policy`) | frozen HLD A.2 |
| `maveric.loop.feedback.v1` | executors → bdt_engine decision hub | apply acks, KPI windows, breaches, rollbacks (frozen HLD A.3) |

-----

## 1\. Frontend — `maveric_platform_frontend`

Lives in the `maveric_platform_frontend` repository, registered as a submodule at `submodule/maveric_platform_frontend`. Full design bundle: `artifacts/frontend/`.

  - **Stack**: Next.js 15.5 (App Router), React 19.1, Tailwind v4, D3 v7, Zustand 5, Axios, TypeScript 5.9.
  - **Directory**: route groups at the repo root, not under `src/`.
    ```
    app/
      (auth)/                  # sign-in / signup surfaces
      (dashboard)/             # per-tenant screens
      (api)/ , api/            # route handlers
    components/ hooks/ lib/ providers/ types/
    ```
  - **API Base**: `NEXT_PUBLIC_API_BASE=/v1`.
  - **Auth**: Cognito Hosted UI/SDK on the client, or call Gateway with a Bearer token.
  - **Visualization**: D3 expects `plot.groups[{ title, data: [{x,y}] }]`.

-----

## 2\. Gateway — `maveric_platform_gateway` (Go, Gin)

### Multi-Tenancy Roles (Three-Tier RBAC)

  - **cloudly_admin** (Platform Admin)
    - Manages organizations (tenants)
    - Full access to `/v1/admin/**` endpoints
    - Stored in CloudlyIO org (UUID: `00000000-0000-0000-3029-000000000000`)
    - Can create/list/delete organizations
    - Can create/manage platform admins
  - **tenant_admin** (Organization Admin)
    - Manages users + resources within their tenant
    - Can create/list/delete users in their tenant
    - Can perform tenant-scoped operations (baselines, datasets, training, inference)
    - Cannot access `/v1/admin/**` endpoints
  - **tenant_user** (Regular User)
    - Access resources within their tenant (read/write, run inference)
    - Cannot manage users
    - Cannot perform admin operations
  - **trial_user** (Trial User)
    - Read-only access to all resources + inference/compare execution + full copilot access
    - Cannot create, update, delete, or train any artifacts
    - Assigned to the shared "netai trial" org (UUID: `00000000-0000-0000-3029-000000000001`)
    - Self-signup via `POST /v1/trial/signup` (public, rate-limited at 5/min per IP)

JWT carries `custom:tenant_id` and `custom:role` custom claims per tenant.

### Multi-tenancy hardening

  - A dedicated `tenant.Service` (DB + Cognito) backs all platform-admin (`/admin/tenants/**`) and tenant-admin (`/tenants/{tenant_id}/users/**`) flows; handlers are thin and reuse shared DTO mappers.
  - Cognito user creation uses `AdminCreateUser` with `MessageAction=RESEND`, so invite emails are sent; API responses still include `temp_password` for admin use.
  - Request/response fields use explicit prefixes: `tenant_name`/`tenant_status`, `admin_email`/`admin_name`, `user_email`/`user_name`/`user_role`/`user_status`; envelopes remain unchanged.
  - DEV bypass supports switching tenant roles via `DEV_TENANT_ROLE` while keeping Cloudly admin access restricted to `/admin/**`; tenant prechecks return `TENANT_NOT_FOUND`, user lookups return `USER_NOT_FOUND` with IDs in details.

### Responsibilities

  - Verify Cognito ID token via JWKS (`COGNITO_JWKS_URL`).
  - Authorize tenant membership & role (read `custom:tenant_id` + `custom:role`; reject non-ID tokens).
    - `/v1/admin/**` → requires `cloudly_admin` role
    - `/v1/tenants/:tenantID/users/**` → requires `tenant_admin` role
    - `/v1/tenants/:tenantID/**` → requires membership in tenant with any role
    - Optional: `REQUIRE_ADMIN_MEMBERSHIP=true` enforces a membership row for platform admins
  - Public lookup: `GET /v1/tenants/lookup?tenant_name=...` (or `slug`) returns tenant_id for pre-auth selection.
  - Public trial signup: `POST /v1/trial/signup` — self-service registration into the trial org. Rate-limited by IP (5/min) via `RateLimitByIP`. Creates Cognito user (`trial_user` role), inserts `trial_signups` lead capture row, creates `tenant_memberships` row. Rollback chain: if membership insert fails → delete trial_signups row + Cognito user.
  - Trial write guard: `TrialWriteGuard()` middleware on proxy routes blocks all POST/PUT/PATCH/DELETE for `trial_user` except whitelisted inference POSTs (`/bdt/models/*/infer`, `/rapps/*/models/*/infer`, `/rapps/compare/infer`) and all copilot endpoints (`/copilot/**`). GET always passes. Applied after `RequireMembership` in the proxy route group.
  - Admin trial lead listing: `GET /v1/admin/trial-signups` — paginated list of trial signups for sales pipeline (requires `cloudly_admin`).
  - Persist tenant metadata in Postgres (`tenants.auth_provider` defaults to `cognito`; optional `auth_config` holds provider-specific metadata).
  - Rate limiting in Redis; key: `ratelimit:{tenant}:{route}:{slot}`.
  - Inject service-specific `X-API-Key` headers when proxying to BDT, rApp, SMO Sim, and Data Sim; downstream `API_KEY` values must match gateway `BDT_API_KEY`, `RAPP_API_KEY`, `SMO_API_KEY`, and `DATA_API_KEY`.
  - Proxy/routing map:
      - `/v1/admin/**` → platform admin APIs (no proxy)
      - `/v1/tenants/:tenantID/users/**` → tenant user management (no proxy)
      - `/v1/tenants/:tenantID/bdt/**` → BDT Engine
      - `/v1/tenants/:tenantID/ndt/**` → BDT Engine (Network Digital Twin: evaluate, kpis, feature-builds, loop decision hub; same proxy group as `/bdt`, `BDT_API_KEY` injected — landed E5.S7)
      - `/v1/tenants/:tenantID/rapps/**` → rApp Engine
      - `/v1/tenants/:tenantID/baselines/**`, `/ue-data/**` → SMO Sim
      - `/v1/tenants/:tenantID/utils/**` → Data Sim
      - `/v1/tenants/:tenantID/ingest/**`, `/data/**` → Data Sim (Data Platform: ingest jobs + canonical PM/FM/CM queries, `DATA_API_KEY` injected — E1)
      - `/v1/actuators/**` → SMO Sim (actuator adapter registry/health surface; not tenant-scoped)
      - `/v1/tenants/:tenantID/copilot/**` → Copilot backend (unchanged tenant-prefixed route)
      - `/v1/tenants/:tenantID/custom/**` → split per request (EPIC-0.S2 `customDispatchHandler`): `custom/nybsys/uploads*` → Data Sim; NanoLink device/edge operations → SMO Sim (feature flag gating enforced at the downstream service layer, not gateway)
      - `/v1/agent/**` → SMO Sim NanoLink GO Agent API. Distinct route group: `RateLimitByIP` + inject `SMO_API_KEY`, but **no** `RequireMembership` and **no** Cognito — Edge-Key (`X-Edge-Key`) auth happens in SMO Sim. Requires a matching entry in the AuthN bypass allowlist (`internal/middleware/middleware.go:177`): the allowlist early-return precedes both the JWT verifier and the `DEV_BYPASS_JWT` branch, so without it agent calls 401 in prod even though the route group exists. Gateway is a compiled binary with no source mount → rebuild/recreate to pick up the group.
      - Gateway strips upstream `Access-Control-*` headers from proxy responses and applies the single browser CORS policy configured by `CORS_ALLOW_ORIGINS`.
  - Cluster Helm guardrail: staging/prod gateway charts now prepend a `pg_isready` init container driven by the existing `POSTGRES_DSN` secret so full-cluster restarts do not let the gateway fail fast before Postgres is ready.

### Key packages

  - `internal/auth/jwt.go`: JWKS fetch, token parsing with iss/aud checks.
  - `internal/cognito/client.go`: Cognito admin user lifecycle client.
  - `internal/middleware/middleware.go`: attach req id, check bearer, match tenant membership, set `tenant_id` in context.
  - `internal/proxy/proxy.go`: reverse proxy util.
  - `internal/utils/log.go`: zerolog with request/tenant fields.

### Metrics

Prometheus metrics registered in `internal/metrics/metrics.go`, exposed unauthenticated at `GET /metrics` (`cmd/gateway/main.go:102`):

  - `http_requests_total` — counter, labels `method`, `path`, `status`.
  - `http_request_duration_seconds` — histogram (Prometheus default buckets), labels `method`, `path`, `status`.
  - `gateway_rate_limit_hits_total` — counter of requests rejected by the rate limiter.
  - `gateway_idempotent_replays_total` — counter of responses served from the idempotency cache.

Distributed tracing is not yet real: `internal/lib/tracing/tracing.go` is a stub that only generates/propagates a W3C `traceparent` header (no OTEL spans exported).

### Env

```
PORT=8080
COGNITO_REGION=...
COGNITO_USER_POOL_ID=...
COGNITO_APP_CLIENT_ID=...
COGNITO_JWKS_URL=...
COGNITO_JWT_ISS=...
AWS_REGION=...
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
REQUIRE_ADMIN_MEMBERSHIP=false
DEV_BYPASS_JWT=true  # local only
DEBUG_DEFAULT_TENANT=1111...1111
CORS_ALLOW_ORIGINS=http://localhost:3000
BDT_BASE_URL=http://bdt-engine:8000
RAPP_BASE_URL=http://rapp:8001
SMO_BASE_URL=http://smo-sim:8002
DATA_BASE_URL=http://data-sim:8003
BDT_API_KEY=...
RAPP_API_KEY=...
SMO_API_KEY=...
DATA_API_KEY=...
COPILOT_BASE_URL=http://copilot-backend:8000
COPILOT_BACKEND_API=...
REDIS_URL=redis://redis:6379/0
```

Cluster note:
- `DEV_BYPASS_JWT` must be `false` in staging/prod Helm values; JWT bypass is only for local development.
- Local Docker note: after gateway auth/proxy changes, rebuild/recreate `gateway` because compose runs a compiled Go binary without a source bind-mount. A stale image will keep failing proxied `/v1` calls with downstream missing-API-key errors even when `.env` values are already correct.
- Local platform-admin note: for `/v1/admin/**`, populate `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` in the gateway local `.env` from the deployment Helm gateway `secretData`. That keeps local add-org E2E aligned with the working cluster runtime instead of depending on a developer-specific AWS profile.

-----

## 3\. BDT Engine / Network Digital Twin — `maveric_platform_bdt_engine` (FastAPI)

Role (re-architecture E2): **Network Digital Twin (NDT)** — twin engines (Maveric BDT GP; commercial slot), twin feature builder, evaluate API, KPI tracking, and the closed-loop decision hub — plus the legacy BDT model registry/training/inference surface.

### Endpoints (see `openapi.yaml`)

  - `GET /tenants/{t}/bdt` — list models.
  - `POST /tenants/{t}/bdt/train` — accept training (creates stub row, emits `maveric.bdt.train.v1` event).
  - `GET /tenants/{t}/bdt/models/{bdt_id}` — get one model.
  - `POST /tenants/{t}/bdt/models/{bdt_id}/infer` — enqueue asynchronous BDT inference (`202` + `Location`).
  - `GET /tenants/{t}/bdt/models/{bdt_id}/infer/{run_id}` — poll inference status/result.

### NDT endpoints (`app/api/v1/endpoints/ndt.py`, `ndt_loop.py`; gateway-routed under `/v1/tenants/{t}/ndt/**` since E5.S7, direct `X-API-Key` on :8000 for service callers)

  - `POST /tenants/{t}/ndt/evaluate` — evaluate a proposed configuration against the twin. Tick scope = synchronous 200 (one twin pass); day scope = 202 + `Location` poll (up to 24 passes, bounded `ThreadPoolExecutor` in the API process). Deterministic UUIDv5 `run_id`; identical inputs are a cache hit, not a second run. Result fields (`guardrail_kpis`, `objective_kpis`, `per_tick_kpis`, `worst_tick_stats`, `raw_tick_data?`) are byte-identical to rapp's `kpi_calculator` shapes so rapp's public responses stay byte-compatible. Rows in `ndt_evaluation_runs` (result stored without `raw_tick_data`; Mongo cache keeps the full payload).
  - `GET /tenants/{t}/ndt/evaluate/{run_id}` — poll: `{run_id, status, result?, error?}`.
  - `GET /tenants/{t}/ndt/kpis` — KPI snapshot trend (`ndt_kpi_snapshots`, E2.S5), newest first; filters `bdt_id, baseline_id, source (evaluate|loop_gate), from_ts, to_ts, limit, offset`.
  - `POST /tenants/{t}/ndt/feature-builds` — queue a semi-synthetic feature build (E2.S4; data_sim's ingest seam contract byte-for-byte). 202 `{build_id, status}` + Location; duplicate live `build_id` → 409 with the existing row (data_sim adopts it — redelivery-safe). `GET .../feature-builds/{build_id}` polls `{build_id, status, error, artifacts, stats}`. Artifacts labeled `semi_synthetic=true` in `baselines.stats`.
  - `POST /tenants/{t}/ndt/loop/proposals` — REST mirror of `maveric.loop.proposal.v1` (202 `{proposal_id, action_ids}`; path/body tenant mismatch → 422 `TENANT_MISMATCH`).
  - `GET /tenants/{t}/ndt/loop/actions` — list, filters `status, proposal_id, kind, target, since, until, limit, offset` (E2.S8/E5.S3).
  - `GET /tenants/{t}/ndt/loop/actions/{action_id}` — full action row with policy/evaluation snapshots; `?include=lineage` returns proposal → evaluation → action → feedback[] → rollback (E5.S3).
  - `POST /tenants/{t}/ndt/loop/actions/{action_id}:approve` — `pending_approval → approved → dispatched` in one call (gate NOT re-run; `expires_at` computed at approval time). 200 `{action_id, status: "dispatched"}`; 404 `ACTION_NOT_FOUND` / 409 `ACTION_NOT_PENDING`; 502 when publish fails (row marked `failed`).
  - `POST /tenants/{t}/ndt/loop/actions/{action_id}:reject` — terminal, nothing published; mirrors approve semantics.
  - `GET|PUT /tenants/{t}/ndt/loop/policy` — per-tenant `{mode: off|approval|auto, guardrails: {min_sinr_db, min_rrc_success_pct, max_outage_rate}, watch_window_min}`; missing row reads as `mode=off` (fails closed); PUT upserts. Seeding: `artifacts/migration/015_ndt_loop_policy.sql`.

### Decision hub internals (`app/services/loop/`, E2.S6–S8)

  - Proposal intake (topic + REST) stores the raw message in `loop_proposals`, gates each recommendation on the twin (evaluation snapshot) + tenant policy, and writes one `loop_actions` row per decision with `policy_ref`/`evaluation` snapshots at decision time. Status vocabulary: `proposed | suppressed | rejected_by_gate | pending_approval | approved | rejected | dispatched | applied | failed | watching | completed | rolled_back | expired` (application-enforced; migration 014 carries no CHECK on this column).
  - Approved/auto actions publish `maveric.loop.action.v1`; feedback (`maveric.loop.feedback.v1`) lands in `loop_feedback` (append-only, `action_id` nullable for unsolicited device events); guardrail watch re-evaluates KPI windows against tenant guardrails and orders rollback through the same adapter (`prev_action_id` links the pair). The clock-driven sweep runs under the `app.maintenance='on'` RLS maintenance policy (migration 014/E2.S7).

### Internals

  - **DB**: SQLAlchemy 2; `SessionLocal` with per-request `set_config` for tenant.
  - Requires caller-supplied `bdt_id`; enforce uniqueness per tenant and carry it through responses/events.
  - **Idempotency**: `POST /bdt/train` scopes the `Idempotency-Key` to `bdt_id`. Duplicate key + `bdt_id` returns the original queued model; changing `bdt_id` is treated as a new submission.
  - **Artifacts**: write to S3 prefix as `…/bdt/{bdt_id}/{bdt_id}.pickle` *and* persist a local pickle under `<base>/var/models/{tenant_id}/bdt/{bdt_id}.pickle` for fast reuse/debug. The base directory is resolved via `BDT_WORKER_MODEL_BASE_DIR` (falling back to `/app`) and shares the sanitised path builder used by the rApp worker so tenant-controlled identifiers cannot escape the expected folder hierarchy.
  - **Storage configuration**: `workers/bdt_worker.py` wires boto3 using `S3_REGION` plus the optional AWS-specific controls `S3_BUCKET_ARN`, `S3_ASSUME_ROLE_ARN`, and `S3_ASSUME_ROLE_EXTERNAL_ID`. When `S3_BUCKET_ARN` is present the worker derives the effective bucket/access point from the ARN and no longer requires `S3_ENDPOINT_URL` (still honoured for MinIO/dev). Startup logs print the configured bucket, ARN, prefix, region, endpoint, and assume-role ARN exactly once. Incoming CSV references may be HTTPS URLs, `s3://` URIs, full S3 ARNs, or bare keys like `baseline.csv`; the worker normalises them by trimming any leading bucket segment, prepending `S3_PREFIX` when callers omit it, and rejecting unrelated HTTP hosts so MinIO-style endpoints remain the only HTTP paths resolved through S3. Credentials are refreshed whenever boto3 raises `NoCredentialsError`.
  - **Events**: publish to Kafka `maveric.bdt.train.v1`; payload carries `job_id=bdt_id` for human-readable tracking plus `training_job_id` (the actual UUID PK) and the baseline id/optional CSV overrides so the worker can hydrate inputs.
  - **Training status alignment**: worker now updates both `training_jobs.status` and `bdt_models.status` through the same lifecycle (`queued -> training -> ready|failed`) and uses `TrainStatus` enum-backed assignments to reduce mismatch regressions.
  - **Redelivery guard**: worker treats messages as idempotent for terminal models; if a redelivered job targets a model already `ready|failed`, it is skipped instead of retraining.
  - **Parallel commit safety**: Kafka commits are tracked per `(topic, partition)` and advanced only to the highest contiguous completed offset. This prevents race conditions where out-of-order future completion could commit past unfinished work.
  - **Inference runner**: API writes a row to `bdt_inference_runs` and submits work to an internal `ThreadPoolExecutor` (`InferenceJobRunner`) instead of Kafka. Status transitions are `queued → running → completed|failed`, and completed rows persist D3-ready plot payload + attachment metrics (`total_ues`, `attached_ues`, `attachment_rate`) with `optimization_metric`.
  - **Inference input contract**: `ue_dataset_id` and `tick` are required (`tick` range: `0..23`); `baseline_id` is optional and defaults to the model baseline.
  - **Inference storage contract**: `bdt_inference_runs` stores `request`, `ue_dataset_id`, `tick`, `result`, and `error` for polling and auditability under tenant RLS context.
  - `kafka_plan.md` records the current implemented BDT rollout: the worker now uses the same pause/resume and exact-offset Kafka loop as rApp, while deployment defaults keep `BDT_WORKER_CONCURRENCY=1` so scale comes primarily from partitions plus replicas.

### Worker

  - `bdt_worker.py`: Kafka consumer, n partitions; configurable concurrency.
  - **Steps**: resolve baseline row + CSV URLs/keys (falling back to overrides) → fetch CSVs → train (call maveric bayesian engine) → write artifacts → metrics to Postgres → status `ready|failed`.

### Modules

```
app/
  main.py                 # app factory, OTEL, routers
  api/v1/routes.py        # FastAPI routers (bdt, ndt, ndt_loop)
  api/v1/endpoints/ndt.py        # NDT evaluate / kpis / feature-builds
  api/v1/endpoints/ndt_loop.py   # loop policy / proposals / actions (approve, reject, lineage)
  models/schemas.py       # Pydantic models
  models/ndt_models.py    # NDT evaluate contracts (byte-compatible with rapp kpi_calculator)
  db/sql_handler.py       # engine/session + set_tenant()
  db/mongo_handler.py     # if needed
  feature_builder/        # twin feature builder (semi-synthetic; moved from smo_sim nybsys stages 3-6)
  services/inference_runner.py
  services/bdt_inference.py
  services/loop/          # decision hub: gates, dispatch, feedback watch, rollback
  services/ndt_runner.py  # twin evaluation
  services/utils/data_loader.py
  services/utils/plot_builder.py
  utils/logger.py
  event_handlers/kafka_handler.py
  workers/bdt_worker.py   # consumer
```

-----

## 3.1 CloudlyNet Edge Agent — `cloudlynet_edgeagent` (Go)

### Responsibilities

  - Runs on an edge device and initiates all CloudlyNet traffic outbound.
  - Consumes the frozen Agent API from `artifacts/design/openapi.yaml`: register, poll, heartbeat, telemetry, config snapshot, and command ack.
  - Retries registration from the heartbeat loop until the platform accepts it, so transient gateway/port-forward startup order does not strand the edge offline.
  - Uses `X-Edge-Key` from the decoded enrollment token; Cognito is not used by the agent.
  - Production callback routing requires SMO Sim `PUBLIC_BASE_URL=https://<platform-host>/`, frontend ingress `/v1` routing to gateway, and a gateway `/v1/agent/**` proxy that bypasses Cognito while injecting `SMO_API_KEY` for SMO Sim.
  - **Hosts an in-agent TR-069/CWMP ACS on `:7547`** (`internal/cwmp`, replaces GenieACS) bound to the exact host:port the NanoLink already dials (`Device.ManagementServer.URL`), so cutover needs no device-side change. It answers `Inform`, the `AutonomousTransferComplete` (ATC) RPC with the empty `AutonomousTransferCompleteResponse` (never a Fault — the fault GenieACS returned killed the session before the ACS could read/write), `GetParameterValues`, `SetParameterValues`, a `GetParameterNames` writability walk once on first contact, and `Reboot`. An optional connection-request trigger fires on demand, otherwise the device's ~60 s inform cadence drives the session. The old `AutonomousTransferCompletePolicy=None` baseline SPV is no longer written — the ATC handler obsoletes it — though the path remains a read-only entry in the snapshot catalogue. Each ATC also emits an `autonomous_transfer_complete` device event into the telemetry batch.
  - Watches the FTP drop for NanoLink `.tgz` log bundles and maps FM/TR69/FILE_TRANS lines to telemetry events using local YAML rules; the processed-archive set is pruned to the directory contents to stay bounded.
  - Collects tiered telemetry (canonical metric keys, handover §3.4) via `goagent/internal/collector/metrics.go`:
    - **T1** (live): `op_state`, `rf_tx_status`, `admin_state`, `s1_status`, `sctp_status`, `connected_ues`, `volte_ues`.
    - **T2** (RF/coverage): `rip_average`, `rip_prb`, `rip_threshold`, `earfcn_dl_inuse`, `pci_inuse`, `rs_power`, `dl_bw`, `ul_bw`.
    - **T3** (PM + hardware + alarms): `prb_dl_pct`, `prb_ul_pct`, `sinr_avg_db`, `rrc_conn_mean`, `thp_dl`, `thp_ul`, derived `rrc_success_pct`, live `uptime`/`mem_free`/`mem_total`/`cpu_usage`, and `alarms[]` from bounded `Device.FaultMgmt.CurrentAlarm.{i}` rows using `CurrentAlarmNumberOfEntries`, `EventTime`, `PerceivedSeverity`, `EventType`, and `SpecificProblem`.
    - Each tier is one batched GPV read per device; absent keys are omitted (`MetricSample.metrics` is open). PM counter paths are pinned to the NanoLink `dmcli.new.conf` `Device.PeriodicStatistics.SampleSet.1.Parameter.{index}.X_8C1F64_CurrentValue` mapping; update the index constants in `goagent/internal/collector/metrics.go` if a firmware-specific SampleSet reorder is discovered.
    - **Cadence**: T1 30 s, T2 60 s, T3 5 min (PM counters carry 900 s granularity). Alarm scan bounded to `maxAlarmRows = 16`.
    - **PM SampleSet index map** (verbatim from `goagent/internal/collector/metrics.go`): `prb_dl_pct`→`Parameter.316` (RRU.TotalPrbUsageMeanDl), `prb_ul_pct`→`315` (RRU.TotalPrbUsageMeanUl), `sinr_avg_db`→`412` (RRU.Sinr.Average), `rrc_conn_mean`→`10` (RRC.ConnMean), `thp_dl`→`118` (MAC.ThroughputDl), `thp_ul`→`119` (MAC.ThroughputUl); derived `rrc_success_pct` = `Parameter.170` (SuccConnEstab) / `Parameter.168` (AttConnEstab) × 100. T1/T2 keys read live TR-069 paths under `Device.Services.FAPService.1.`; live-hardware T3 keys read `Device.DeviceInfo.{UpTime, MemoryStatus.Free, MemoryStatus.Total, ProcessStatus.CPUUsage}`.
  - Collects a separate configuration snapshot containing all 24 managed parameters mirrored by SMO Sim and the frontend catalogue. The agent requests a fresh GPV read from its in-agent ACS (best-effort connection request), waits up to 10 seconds (`snapshotAwait`) for a fresh value, and falls back to the last cached values; it logs and skips an all-empty result. SMO Sim ignores empty payloads and stores each non-empty periodic snapshot or command read-back as a merge over the prior snapshot, preserving operator-visible values when a delta only reports one field.
  - Uses the canonical `cwmp_id` (computed by `CanonicalID` from the Inform `DeviceID`, byte-identical to the id the previous ACS stored) as the cloud identity. For the config-snapshot route, it path-escapes the complete id before building the URL. This is required for NanoLink ids that contain literal percent sequences (for example `%2D`): FastAPI decodes URL paths once, so `%2D` must travel as `%252D` to match the id submitted by heartbeat/telemetry. Without this, snapshots auto-onboard a second decoded (`-`) device and the operator-selected encoded device remains blank.
  - Configure/optimise/heal/rollback commands call `setParameterValues`, wait `command_verify_delay`, then issue a fresh GPV and poll the cache until every expected write matches or `command_verify_timeout` expires (default/production `15s`). A timeout remains a failed command with `{path, expected, actual, missing}` mismatch evidence; it does not overwrite the Current-value snapshot. The Docker fixture uses `3s` to keep local tests fast.
  - Maintains local SQLite tables (single embedded DB):
    - `outbox(kind, body, created_at)` for telemetry retry.
    - `applied(command_id, status, result, applied_at)` for command idempotency.
    - `cwmp_devices` / `cwmp_params` / `cwmp_events` — the in-agent ACS device identity, parameter/writability cache, and ATC/event log.

### Modules

```text
goagent/
  cmd/agent/main.go
  internal/config      # YAML + enrollment token decode
  internal/cloud       # Agent API client and envelope unwrap
  internal/buffer      # SQLite outbox, applied-command dedupe, + CWMP device/param/event store (embedded modernc.org/sqlite)
  internal/cwmp        # in-agent TR-069/CWMP ACS (:7547): SOAP codec, session, ATC handler, connection-request trigger
  internal/rules       # FTP log rule engine
  internal/collector   # tiered KPI, snapshots, inventory from the CWMP cache, FTP archive parsing
  internal/worker      # ticker loop and command execution
deploy/
  cloudlynet-edgeagent.service  # hardened systemd unit (EnvironmentFile, ProtectSystem=strict)
  agent.yaml           # production config (no embedded token)
  agent.env.example    # runtime env template
scripts/
  install.sh           # Ubuntu 22.04 native install: Go bootstrap + build + systemd
  uninstall.sh
Makefile               # build/test/vet/run/install/uninstall/docker-*
testsuite/
  main.go              # mock CloudlyNet Agent API + mock NanoLink CWMP device dialing the agent's :7547 ACS (+ conn-request listener :30005); acsftp mode disables CloudlyNet mock
```

### Native Edge Install (Ubuntu 22.04)

`scripts/install.sh` (idempotent, root) is the production deployment path:

1. Ensure Go ≥ 1.23 — reuse an existing toolchain or download the official `go1.23.11` tarball to `/usr/local/go` (apt Go on 22.04 is too old for `go.mod`). No CGO/gcc needed — SQLite is pure Go.
2. Build `cloudlynet-agent` from source (`CGO_ENABLED=0`) → `/usr/local/bin`.
3. Create the `cloudlynet` system user, `/etc/cloudlynet-agent`, and `/var/lib/cloudlynet-agent` (SQLite buffer lives here).
4. Install `deploy/agent.yaml` + `config/rules.yaml` without clobbering operator edits (new versions land as `*.default`); create `agent.env` (mode 0600) for the enrollment token and endpoints.
5. Install + enable the systemd unit; start only once `CLOUDLYNET_ENROLLMENT_TOKEN` is set. `make install`/`make uninstall` delegate to these scripts. `uninstall.sh --purge` also removes config/data/user.

### Docker Validation

The submodule compose file starts the agent and a separate mock testsuite service. Root compose exposes the same pair only under the `edgeagent` profile, so normal platform startup is unchanged. For deployed CloudlyNet validation, run the testsuite with `TESTSUITE_MODE=acsftp` so only the local CWMP device + FTP are mocked and the agent calls the real `/v1/agent/**` platform endpoints.

-----

## 4\. rApp Engine / RAN Intelligence — `maveric_platform_rapp` (FastAPI)

Role (re-architecture E3): **RAN Intelligence** — rApp/xApp model registry + Kafka training (unchanged), recommendation inference with the public day/tick `/infer` contract preserved but **twin evaluation delegated to the NDT** (bdt_engine) via env `NDT_BASE_URL` + `NDT_API_KEY`, recommendation proposals published to the decision hub on `maveric.loop.proposal.v1`, and the **RIC integration layer** in `app/ric/`:

  - `ports.py` — `RanControlPort` (submit/delete/status policy intents, capabilities) and `RanDataPort` (subscribe → normalized records to `maveric.ingest.pm.v1`); Pydantic `PolicyIntent` maps 1:1 onto an A1 policy-instance body.
  - `adapters/nonrtric/` — O-RAN SC NONRTRIC A1-PMS connector (httpx): policy-type discovery, policy-instance CRUD, status. API v3 (`{apiRoot}/a1-policy-management/v1`) with env-switchable `A1PMS_API_MODE=v2` fallback; env `A1PMS_BASE_URL`, `A1PMS_SERVICE_ID`.
  - `executor.py` — the `a1_policy` loop-action executor: background consumer of `maveric.loop.action.v1` inside the rapp container (no new deployable); filters `adapter=a1_policy`, applies via A1-PMS, publishes `maveric.loop.feedback.v1`.
  - `adapters/nearrt/` — `nearrt_xapp` placeholder (lab-activated only for the OCUDU demo track; production near-RT deferred).
  - `r1_manifest.py` — R1-shaped rApp manifest (metadata facade; roadmap).
  - Lab profile `ric-lab` is compose-only (NONRTRIC A1-PMS 2.11.0 + OSC A1 simulators, container images + REST, never copied source). Design bundle: `artifacts/ric/`.

### Endpoints

  - `GET /tenants/{t}/rapps` — registry: mro, cco, es, lb.
  - `POST /tenants/{t}/rapps/{r}/train` — store model stub (persisting the caller supplied `rapp_model_id`) and emit `maveric.rapp.train.v1`.
      - Persist `dataset_id` on the row for downstream observability.
  - `GET /tenants/{t}/rapps/{r}/models` — list models for a rApp.
  - `GET /tenants/{t}/rapps/{r}/models/{rapp_model_id}` — get model.
  - `DELETE /tenants/{t}/rapps/{r}/models/{rapp_model_id}` — delete.
  - `POST /tenants/{t}/rapps/{r}/models/{rapp_model_id}/infer` — enqueue inference with `{baseline_id, bdt_id, ue_dataset_id, tick}` and return `202` with `{run_id, status, Location}` (initially `queued`). Poll `GET /tenants/{t}/rapps/{r}/models/{rapp_model_id}/infer/{run_id}` until `status ∈ {completed, failed}`. When completed the `result` envelope contains the RadP plot/text/metric payload consumed by the frontend. Every handler calls `set_current_tenant(db, tenant_id)` before talking to Postgres so RLS policies apply to the current request.
  - `POST /tenants/{t}/rapps/compare/infer` — synchronous comparison helper. Ensures the base model exists, optionally locates a compare model (unless `compare_rapp_model_id="BASELINE"`), then runs RadPLib inference twice using the shared `{baseline_id, bdt_id, ue_dataset_id, tick}` context. For cross-rApp comparisons the service resolves the compare model’s RadPLib ID and invokes the matching shared Non-MRO harness (ES, LB, or CCO) before funnelling the results through the base rApp’s optimisation pipeline so metrics stay comparable; unsupported overrides are limited to MRO. The `BASELINE` sentinel emits the raw topology comparison. Returns immediate `200 OK` with `ComparisonInferenceResult` containing paired plots, optimisation metrics, and text recommendations so UI clients can chart deltas without manual polling.

### Internals

  - Training depends on BDT outputs (pass `bdt_id`); the worker resolves models via RADP path helpers and hydrates missing pickles from the recorded artifact URIs (S3/HTTP) before continuing, while still supporting local development fixtures.
  - Non-MRO training is profile-driven — `train_es_rapp`, `train_lb_rapp`, and `train_cco_rapp` now all route through the same generic `app/radplib/non_mro` manager. LB and CCO no longer keep separate legacy trainers; they only swap reward weights/profile metadata, while `app/radplib/es` remains as an ES compatibility wrapper.
  - **Inference job runner**: API writes to `inference_runs` (capturing request, `baseline_id`, `bdt_id`, `ue_dataset_id`, `tick`) and submits work to an internal `ThreadPoolExecutor` (no Kafka). The background task updates status transitions (`queued`→`running`→`completed`/`failed`) and stores the RadP payload (plot/text/metrics).
  - **Inference caching & dedupe**:
      - `run_id` is now generated via UUIDv5 using the tuple `(tenant_id, rapp_model_id, baseline_id, bdt_id, ue_dataset_id, tick)` so identical requests deterministically map to the same identifier. A `db_key = sha256(run_id)` is derived for storage.
      - Request flow: probe Redis (L1) using the `db_key`; on miss probe MongoDB (L2); finally fall back to the Postgres `inference_runs` row (L3). Cache hits respond with `200 OK` (and skip job submission, instead persisting the response straight into Postgres), whereas cache misses retain the previous `202 Accepted` response and enqueue a single worker job. Duplicate POSTs while a run is `queued`/`running` reuse the existing row and return the current status rather than spawning redundant work. L1/L2 are optional: if `REDIS_URL`/`MONGODB_URL` are unset or the clients fail to initialise, the API simply bypasses that tier (using explicit `is None` checks to avoid PyMongo truthiness errors) and continues with the remaining layers.
      - When Redis/Mongo lack an entry but Postgres contains the completed payload the API warms the upper tiers before replying. Workers always write the completed RadP payload into Mongo first (durable) and Redis second (fast), so the data converges even if one tier is temporarily unavailable. Operators can disable the cache by setting `CACHE_ENABLED=false` and configure the stores via `REDIS_URL` / `MONGODB_URL`; absent URLs automatically degrade back to the Postgres-only flow.
      - The inference cache now supports three result types via scope-directed deserialization: `InferenceResult`, `DayEvaluationResult`, and `MROEvaluationResult`. The `scope` field (`"mro_simulation"`, `"day"`, or absent) determines which Pydantic model is tried first, with fallthrough to the others for legacy data compatibility.
      - **Failed run retry**: repeated POST on a run with `status=failed` resets it to `queued`, clears `result`/`error`, and re-submits to the job runner. No automatic retry loop — the client must explicitly POST again.
      - **Startup recovery**: on container start, `reset_stale_inference_runs()` marks all `running` rows and `queued` rows older than 30 minutes as `failed` with error `"Inference interrupted by container restart"`, preventing clients from polling indefinitely for runs that will never complete.
  - **Day-scope evaluation (`/infer` without `tick`)**:
      - `evaluate_rapp()` executes ticks `0..23` for a selected `day` (default `0`), computes pooled guardrail KPIs (`outage_rate`, `coverage_rate`, RSRP/SINR percentiles), per-tick objective KPIs (`active_cells_ratio`, `energy_saving_ratio`, `estimated_kwh_saved`, `estimated_cost_saved_monthly`, `jains_fairness_index`, `max_ue_per_cell`, `p95_ue_per_cell`), and worst-tick stats.
      - Backward compatibility for legacy datasets: if requested/default `day=0` is absent, evaluator retries using the dataset's first available day and returns a warning indicating the resolved day.
      - Tick-level diagnostics (RSRP/SINR arrays, serving cell IDs, UE-per-cell counts, cell states, tilt map, active/total cell counts) are extracted from the existing BDT attachment output and surfaced only when `include` flags request raw payload expansion.
      - Results are cached in Redis with a 7-day TTL under a hash key derived from `(tenant_id, rapp_id, rapp_model_id, baseline_id, ue_dataset_id, day, model_hash, dataset_hash, thresholds, energy_params, include, export)`, and persisted in Postgres `rapp_evaluation_results` for cache misses/restarts.
      - If `rapp_evaluation_results` is missing (migration not yet applied), evaluator rolls back the failed transaction, skips Postgres persistence/cache lookup, and still returns a completed day-evaluation payload with warnings.
  - **Day-scope compare (`/compare/infer` without `tick`)**:
      - Calls the same `evaluate_rapp()` path for base and compare models, then returns side-by-side KPI payloads, delta tables, and a pareto payload (`x/y/color` metric selectors).
      - Enforces model-baseline-dataset compatibility before execution; baseline mismatch returns a 400 with explicit IDs.
      - Dataset/day validation errors from evaluator are translated to HTTP 400 so request failures are user-actionable and do not surface as unhandled 500 responses.
      - `FileNotFoundError` from the evaluator (for example, a missing BDT model artifact) is translated to HTTP 404.
  - **Workers**: `rapp_worker.py` consumes `maveric.rapp.train.v1`, validates payloads, downloads UE/topology/config CSVs (S3 or configurable local paths), calls the appropriate RADP trainer, copies the BDT model into the tenant namespace when needed (downloading the pickle from the stored artifact URI if it is missing locally), and writes metrics/artifact URIs. Each successful training run persists the RL ZIP to `/app/var/models/{tenant_id}/rapps/{rapp_id}/{rapp_model_id}.zip` and mirrors the artifact to the canonical `s3://{bucket}/{prefix?}{tenant_id}/models/rapps/{rapp_id}/{rapp_model_id}.zip` key even when the worker operates purely on EFS, so every pod sees a consistent backup. Failures mark the row `failed` and capture structured error context. The synchronous inference loader shares the same resolver: it walks the stored `artifacts_uri` list (and, when necessary, derives the expected key from `RAPP_WORKER_S3_ARTIFACT_TEMPLATE`) to restore the ZIP into `/app/var/models/{tenant_id}/rapps/{rapp_id}/` before invoking RadP, providing a fail-safe when the shared volume loses the archive.
      - Legacy BDT pickles that refer to the old `app.radp.*` package tree are
        transparently remapped to `radplib.dependencies.radp.*` during load.
      - RADP helpers are exposed via the `radplib` package; the legacy
        `app.radplib` and `radp` imports remain as shims to ease migration.
      - Worker resolves dataset + baseline rows via Postgres to honour canonical S3 URLs (preferring `url_to_smo_ue_data_csv` / `url_to_config_csv`), falling back to legacy prefixes for backwards compatibility.
      - Workers and synchronous loaders share the ARN/assume-role aware S3 client; HTTPS URLs, `s3://` URIs, object ARNs, and bare keys are normalised via `S3_PREFIX`, and the boto3 client is refreshed when AWS reports `NoCredentialsError`. HTTP(S) URLs are treated as S3 only when they target the configured endpoint and expose the bucket/prefix segment; everything else is rejected early so the worker never fetches arbitrary public content.
      - Current Kafka operating mode is the merged worker-hardening path from `maveric_platform_rapp#34`: manual commit, `max_records=1`, partition pause/resume, exact-offset commit, idempotent terminal-state skip, and explicit Kafka timeout envs. Initial rollout uses 2 topic partitions with 2 worker replicas; further SaaS scaling guidance is captured in `kafka_plan.md`.
      - Gateway skips automatic GORM migrations; the shared schema pack (see `artifacts/design/schemas.sql`) must be applied via the deployment pipeline to keep columns such as `rapp_models.dataset_id` and `rapp_models.bdt_id` aligned. The pack also enforces global email uniqueness and non-null `user_name` on `tenant_memberships`. During startup the gateway only refreshes triggers and indexes when the tables already exist, preserving manual DDL ownership.
      - The shared UE loader coerces legacy datasets by selecting the first available `day` and deriving `loc_x`, `loc_y`, and `mock_ue_id` columns from `lon`, `lat`, and `ue_id`, ensuring the plot builder receives the expected schema even when older CSVs omit those fields. The attachment pipeline surfaces a `serving_cell_id` copy of `cell_id` so response payloads include per-cell UE point clusters and coverage scoring can still reference the canonical column. The optimisation metric now reuses the environment reward logic (`_calculate_reward`) by feeding the attached RF dataframe through `CcoEngine` for coverage scoring and load-balance statistics.
      - ES/LB/CCO tick inference now uses one shared Non-MRO flow: resolve RL `.zip`, run the generic `app/radplib/non_mro` prediction path, materialise active cell configs, refresh PlotData via the BDT attachment logic, and score the result with the base profile’s reward weights. Text payloads for all three expose `tick + items[{cell_id, el_degree, on_off}]` so operators receive both electrical tilt and activation state.
      - ES/LB/CCO day-scope evaluation now also emits `per_tick_recommendations[{tick, items[]}]`. When `include` contains `raw_ue_arrays`, `raw_tick_data[*]` additionally mirrors `tilt_by_cell` and `recommendations` alongside the UE-level diagnostics.
      - Topology/config frames are normalised before each BDT simulation so missing columns such as `cell_carrier_freq_mhz` fall back to safe defaults rather than raising attribute errors.

### Inference routing

```
POST /infer
  ├─ rapp_id == mro           → _infer_mro_async() → always 202 → INFERENCE_JOB_RUNNER → evaluate_rapp(MRO) → _evaluate_mro()
  ├─ tick omitted (es/lb/cco) → day-scope sync  → evaluate_rapp(ticks 0..23) → 200
  └─ tick present (es/lb/cco) → tick-scope async → 202
```

  - Model must be `status=ready`, else `409`. `mro` keeps a dedicated path; `es`/`lb`/`cco` share the generic `app/radplib/non_mro` RL engine. `/compare/infer` supports ES/LB/CCO (incl. cross-rApp overrides); MRO compare is deferred.

### Non-MRO reward profiles (`app/radplib/non_mro/profiles.py`)

Profile-driven, not code-path-driven — the three rApps differ only by the reward weights fed to the shared ES RL environment:

| rApp | `cco_score` | `load_balance_score` | `energy_saving_score` | agent artifact     |
| ---- | ----------- | -------------------- | --------------------- | ------------------ |
| ES   | 0.2         | 0.1                  | 1.0                   | `es_rl_agent.zip`  |
| LB   | 0.5         | 1.0                  | 0.05                  | `lb_rl_agent.zip`  |
| CCO  | 1.0         | 0.25                 | 0.0                   | `cco_rl_agent.zip` |

  - `default_total_timesteps = 30_000`. CCO no longer uses the legacy dGPCO stack/pickle — its artifact is the same RL `.zip` as ES/LB.

### MRO training & RL config

  - `mro_type` selects the trainer: `"simple"` (analytical, **default**) or `"rl"` (PPO); the `MROType` enum also carries `gpr`/`xgb`. Source: `app/workers/rapp_trainers/train_mro.py`, `app/radplib/mro/rl/rl_mro_training.py`.
  - **RL env** (`ReinforcedMROEnv`): continuous `action_space = Box([hyst_lo, ttt_lo], [hyst_hi, ttt_hi])` over `hyst ∈ [0.0, 15.0]`, `ttt ∈ [2, min(num_ticks, 6)]`; `observation_space = Box(0, 1, shape=(3,))` = `[hyst_norm, ttt_norm, last_reward_norm]`; `max_steps = 20` per episode.
  - **PPO hyperparameters** (`MlpPolicy`): `n_steps = 512`, `batch_size = 128`, `ent_coef = 0.01`, `total_timesteps` default `30_000`.
  - **Reward**: `clip((D - D_floor)/(D_ceiling - D_floor), 0, 1)`, where `D` is the MRO operational metric and `D_ceiling` is the tick count.
  - **Baseline params**: `baseline_hyst` (float, default `1.0` from env `BASELINE_HYST`), `baseline_ttt` (int, default `4` from env `BASELINE_TTT`).
  - **Dataset requirement**: MRO training/eval needs a mobility UE dataset with columns `{latitude, longitude, mock_ue_id, tick}`.

### MRO evaluation DTOs (`app/models/rapp.py`)

  - `MROInferenceParams`: `baseline_hyst` (float, 0.0–15.0, default 1.0), `baseline_ttt` (int, 2–6, default 4). Pydantic coerces types (`"5"`→5.0, `1.0`→1) for deterministic cache keys.
  - `MROSimulationKPIs` (one run — predicted or baseline): `hyst`, `ttt`, `network_kpis`, `rapp_kpis`.
      - `network_kpis`: `outage_rate`, `coverage_rate`, `rsrp_p5/p50/p95`, `sinr_p5/p50/p95`, `samples`.
      - `rapp_kpis`: `d_metric`, `rlf_rate`, `ho_rate`, `rlf_penalty_s`, `ho_penalty_s`, `n_rlf`, `n_ho`.
  - `MROEvaluationResult` (`scope="mro_simulation"`): `predicted`, `baseline` (both `MROSimulationKPIs`), `delta` (`Dict[str, float]`, predicted − baseline per KPI), `warnings` (`List[str]`), `status`, `metadata`.
  - MRO warning thresholds (`app/services/kpi_calculator.py`): RLF-rate `0.01`, HO-rate `0.05`, plus D-metric regression.

### Cell-ID normalization

Real-world/Nybsys numeric cell IDs (pandas `int64`) are coerced to `str` at three layers so cells are not silently dropped on dtype mismatch:

  1. **CSV load** — `_normalize_cell_id_column()` in `data_loader.py`, immediately after `pd.read_csv()`.
  2. **BDT model map** — pickle keys via `{str(k): v for k, v in raw_map.items()}` in `plot_builder.py`.
  3. **Plot builder** — `.astype(str)` topology/config lookups inside `predictions_to_cell_configs()`.

### RADP library, pickle compat & constants

  - Shared RL/RF logic is the vendored `radplib` package (`app/radplib/`); legacy `app.radplib` and `radp` imports remain as shims.
  - **Canonical Bayesian engine import**: `from radplib.dependencies.radp.digital_twin.rf.bayesian.bayesian_engine import BayesianDigitalTwin`.
  - **Legacy pickle remap** — `radplib.dependencies.radp.common.pickle_compat.CompatUnpickler` (invoked automatically by all pickle loaders) rewrites module prefixes so legacy models load without migration:

| Legacy prefix                     | Modern target                 |
| --------------------------------- | ----------------------------- |
| `app.radp.*`                      | `radplib.dependencies.radp.*` |
| `app.radplib.dependencies.radp.*` | `radplib.dependencies.radp.*` |
| `radplib.dependencies.bayesian.*` | `radplib.dependencies.radp.*` |
| `radp.*`                          | `radplib.dependencies.radp.*` |

  - The `radplib.dependencies.bayesian` `engine`/`bayesian_engine` submodules additionally resolve to `…radp.digital_twin.rf.bayesian.bayesian_engine`.

  - **3GPP-spec constants** (do not change without spec justification): `radplib/dependencies/radp/digital_twin/utils/constants.py` — e.g. `RLF_THRESHOLD = -4`. **Tunable** constants (PPO config, hysteresis ceiling `15.0`, TTT bounds) live under `app/radplib/mro/rl/`.
  - **Test invocation**: `PYTHONPATH=app:app/radplib/dependencies uv run pytest` (MRO + Kafka worker utils have the most complete coverage).

-----

## 5\. SMO Sim / Actuation & Integration — `maveric_platform_smo_sim` (FastAPI)

Role (re-architecture E4): **Actuation & Integration** — the NanoLink TR-069 control plane as-is, refactored onto the **actuator adapter framework** (`app/actuators/`):

  - `base.py` — `ActuatorAdapter` protocol: `capabilities()`, `apply(action) -> ack`, `read_back(target)`, `rollback(action)`, `health()`.
  - `dispatch.py`/`registry.py`/`wiring.py` — command router keyed by the `adapter` field on loop actions (`maveric.loop.action.v1`); rollback routing inspects `payload.rollback_of` and calls `adapter.rollback()`, never `apply()`.
  - `adapters/` — `nanolink_tr069` (real, no behavior change) plus wired placeholders `o1_netconf` (OCUDU sidecar restart semantics), `ocudu_ws_collector` (data plane only), `open_mplane`, `sas_domain_proxy`, `nms_northbound` (registry entry + health + contract doc, no protocol code).
  - Adapter registry/health surface: `app/api/v1/endpoints/actuators.py` (`GET /v1/actuators`, `GET /v1/actuators/{name}/health`), gateway-proxied at `/v1/actuators/**` (not tenant-scoped: the adapter set is a property of the deployment, not of a tenant).
  - Command acks and guardrail events also publish `maveric.loop.feedback.v1`; `commands.loop_action_id`/`policy_ref` (migration 013) correlate loop actions with NanoLink commands, with a partial unique index making at-least-once redelivery idempotent.
  - The E2/R1 REST facades, their `e2test/`/`r1test/` harnesses, and the `e2_*`/`r1_*` tables are **deleted** (frozen HLD D4; migration `012_drop_e2_r1.sql`). The nybsys PM-ingestion uploads router moved to data_sim (§6); smo_sim keeps the NanoLink device/edge `/custom/nybsys/**` operator + `/agent/**` routes.

### Endpoints

  - **Baselines**: list/get/put/delete; register real topology/training/config URLs; utils topology generator.
      - Config CSV captures additional radio parameters and is kept under the same tenant/baseline S3 prefix.
      - Migration: apply `ALTER TABLE baselines ADD COLUMN IF NOT EXISTS url_to_config_csv text;` before deploying code that expects the field.
      - Delete flow: `DELETE /tenants/{tenant_id}/baselines/{baseline_id}` removes the row and purges all S3 objects under `{prefix?}{tenant}/baselines/{baseline_id}/` (for the default prefix this is `s3://{bucket}/tenants/{tenant}/baselines/{baseline_id}/`); failures bubble up as 500 responses for operator visibility.
      - Implementation detail: baseline/UE dataset purges reuse the shared ARN/assume-role aware S3 client, prepend `S3_PREFIX`, and retry list/delete operations when AWS rotates credentials mid-call.
      - Gateway no longer issues GORM auto-migrations on startup; instead it expects the consolidated schema (`db/migrations/schemas.sql`) to be applied ahead of time and merely reapplies idempotent trigger/index guards when the tables are present so cross-service schemas stay consistent without drift.
      - **Response model**: `BaselineSummary` now includes `created_at` (ISO 8601 timestamp) for tracking baseline creation time alongside the existing `baseline_id`, `details`, and S3 URL fields.
  - **Delegated utils generation**: SMO Sim no longer mounts `/utils/traffic-load/generate` or `/utils/mobility/generate`; those paths are handled exclusively by Data Sim to avoid divergent behaviour between services.
  - **UE Data**: list; upload/register UE CSV URL; delete datasets. Payloads now require a caller-provided `dataset_id` that matches the `{prefix?}{tenant}/ue/{dataset_id}/...` prefix (default: `s3://{bucket}/tenants/{tenant}/ue/{dataset_id}/...`), and still accept `url_to_smo_ue_data_csv` (canonical) or the legacy `url_to_trainingdata_csv` alias.
  - **UE Data delete flow**: `DELETE /tenants/{tenant_id}/ue-data/datasets/{dataset_id}` removes the row after enforcing tenant scope and purges S3 objects beneath `{prefix?}{tenant}/ue/{dataset_id}/`. Failures to delete S3 artifacts surface as API errors so operators can remediate credentials or connectivity issues.
  - **Profiles**: background profiling to Mongo.

### Custom Ingestion — `/custom/nybsys/uploads*` (MOVED to data_sim, re-architecture E1)

**The uploads router no longer lives in smo_sim.** `/custom/nybsys/uploads*` is served by data_sim (`app/api/v1/custom/nybsys_uploads.py`) with a byte-compatible contract (field names, status vocabulary, derived id formats, status codes — frozen by HLD §3.2 because the browser talks to it directly); the gateway's `customDispatchHandler` splits uploads → DATA while the NanoLink device/edge operations below stay on SMO. Behind the contract: the POST records the `nybsys_uploads` row and queues a durable ingest job on `maveric.ingest.pm.v1` (replacing smo_sim's in-process `ThreadPoolExecutor`, whose in-flight work a restart used to lose); the NanoLink adapter stores canonical PM rows; the semi-synthetic enrichment (topology synthesis → config → UE placement → RSRP labeling) runs in bdt_engine's twin feature builder via the `/ndt/feature-builds` seam. The contract details below remain the contract of record (see `artifacts/nanolink/nybsys_data_contract.md`).

  - **Feature flag guard**: `require_feature_access` FastAPI dependency on the `/custom` parent router. Extracts module name from the URL (first segment after `/custom/`), validates it via regex, queries `tenants.feature_flags[module]`, returns 403 if absent. Dynamic module extraction — adding new gated modules requires no guard code changes.
  - **Endpoints** (all under `/v1/tenants/{tenant_id}/custom/nybsys`):
      - `POST /uploads` — request body: `upload_id`, `raw_s3_urls`, `rng_seed` (int, default 42), `samples_per_cell` (int, default 200). Validates S3 URLs against the tenant-scoped prefix (`{tenant_id}/pm-data-ingestion/{upload_id}/raw/`), inserts the `nybsys_uploads` row (status=uploading, rng_seed persisted), queues a durable ingest job on `maveric.ingest.pm.v1`, returns 202.
      - `GET /uploads/{upload_id}` — poll status (uploading → processing → completed | failed). Completed response includes derived `baseline_id` and `dataset_id`.
      - `GET /uploads?limit=50&offset=0` — paginated list.
      - `DELETE /uploads/{upload_id}?delete_derived=false` — remove upload row + purge S3 raw artifacts. Optional `?delete_derived=true` cascades to baseline + UE dataset (rows + S3).
  - **Pipeline** (stages 1–2 run in data_sim's `nybsys_pm_csv` adapter, `app/ingest/adapters/nybsys/`; stages 3–6 are the semi-synthetic enrichment, now in bdt_engine's `app/feature_builder/` — artifacts labeled `semi_synthetic=true` in `baselines.stats`):
      1. Load & normalize — read multiple daily 3GPP PM CSVs, fuzzy-match column names, deduplicate on (siteId, cellId, _time).
      2. Hourly PM aggregation — collapse 5-min measurements into (siteId, cellId, day, tick) buckets; 0-based day index sorted chronologically. Logs and fills any missing (cell, day, tick) slots with zero.
      3. Topology synthesis — generate synthetic site positions, derive azimuths from cell count per site, classify cells by `conn_mean` traffic tertiles into clutter types (`dense`/`suburban`/`rural`).
      4. Config generation — sample downtilt angles from clutter-dependent normal distributions.
      5. UE placement (`generate_ue_data`) — `stochastic_guardrail` rule converts `conn_mean` → `n_target` (Bernoulli rounding, slot guardrail prevents empty ticks); **Approach C** bucket assignment via per-clutter multinomial mix (`DEFAULT_PLACEMENT_MIX`: dense 0.75/0.20/0.05, suburban 0.80/0.12/0.08, rural 0.70/0.05/0.25); samplers: `sample_served_voronoi` (uniform-in-Voronoi), `sample_edge_sinr_locus` (accept-reject, SINR ∈ [0, 6] dB), `sample_outage_rsrp_target` (accept-reject, RSRP ∈ [−130, −110] dBm). Output: `synthetic_dataset.csv`.
      6. Stratified RSRP labeling (`generate_ue_training_data`) — PL model registry (FSPL / COST-231 Hata / TR 38.901, default `tr_38_901`); 3GPP antenna pattern; clutter-dependent shadow fading (dense=6 dB, suburban=5 dB, rural=4 dB); RSRP clipped to [−140, −60] dBm; synthetic-complement top-up to `TRAINING_FLOOR=50` rows/cell (`is_fallback=True`), ceiling at `min(samples_per_cell, TRAINING_CEILING=500)`. Output: `ue_training_data.csv`.
  - **Output CSV schemas**:
      - `synthetic_dataset.csv`: `ue_id` (int), `lon` (float), `lat` (float), `tick` (int, 0–23), `day` (int, 0-based), `clutter_type` (str: dense/suburban/rural), `serving_cell_id` (str), `placement_bucket` (str: served/edge/outage), `is_fallback` (bool).
      - `ue_training_data.csv`: `cell_id` (str), `avg_rsrp` (float, dBm), `lon` (float), `lat` (float), `cell_el_deg` (float), `placement_bucket` (str: served/edge/outage), `is_fallback` (bool). The 5-column BDT intersection (`cell_id, avg_rsrp, lon, lat, cell_el_deg`) is consumed by BDT; `placement_bucket` and `is_fallback` are audit/metadata.
  - **S3 layout**: raw under `pm-data-ingestion/{upload_id}/raw/`, hourly aggregate under `pm-data-ingestion/{upload_id}/pm_hourly.csv`, processed outputs under standard `baselines/` and `ue/` prefixes with upload-derived IDs (`{upload_id}-topology`, `{upload_id}-dataset`).
  - **Async execution**: the durable ingest framework (data_sim `app/ingest/service.py` + the in-container Kafka consumer) replaces the old smo_sim `IngestionJobRunner` `ThreadPoolExecutor` — a restart no longer loses in-flight work or strands rows in `processing`. Adapter lifecycle hooks advance `nybsys_uploads` as the job progresses; the enrichment leg polls bdt_engine's `/ndt/feature-builds/{build_id}` seam (409-adoption makes redelivery safe).
  - **Storage**: `nybsys_uploads` row tracking (with `rng_seed`, migration `008_nybsys_rng_seed.sql`); canonical PM rows in `pm_measurements` (migration 011); derived Baseline + UEDataset rows reuse the existing shared tables and S3 key conventions.

### NanoLink Edge Control Plane — `/custom/nybsys/{edge-devices,devices,…}` + `/agent/**`

Cloud counterpart to the on-prem GO Agent that manages NybSys NanoLink cells over an in-agent TR-069/CWMP server. Backed by migration `009_nybsys_nanolink.sql` (7 tenant-scoped tables, `FORCE` RLS). Gated by the same `nybsys` feature flag as Custom Ingestion. Reuses the Custom-Ingestion template patterns (repo singleton, startup `reset_stale_*` sweep, `wrap()` envelope, `require_feature_access` gate).

  - **Auth/contract:**
      - `edge_auth` — operator mints a one-time enrollment token / Edge-Key per edge; only `sha256(secret)` is stored as `edge_devices.api_key_hash`. `auth_edge` FastAPI dependency resolves `X-Edge-Key` → tenant by querying `edge_devices` **before** `app.current_tenant` is set (relies on the OD1 pre-auth SELECT policy; the pooled-connection empty-string GUC is mapped via `NULLIF(...,'')`), then sets the tenant GUC so all later work is RLS-scoped.
      - `managed_params` catalogue + `validate_write` — only allowlisted TR-069 parameter paths (with XSD type) may be written; rejects out-of-catalogue writes.
      - `kpi_keys` — single source of truth for tiered KPI metric names (OD2; e.g. `sinr_avg_db`, not `median_rsrp`).
      - 7 ORM models + frozen request/response DTOs. **Agent-facing shapes key on `cwmp_id`** (contract rev 2.1), not the internal `device_id`.
  - **Operator endpoints** (Cognito, under `/v1/tenants/{tenant_id}/custom/nybsys`):
      - Edge: `POST/GET/PATCH/DELETE /edge-devices[/{edge_id}]`, `POST /edge-devices/{edge_id}:regenerate-key` (re-mint Edge-Key).
      - Devices: `GET /devices`, `GET /devices/{device_id}`, `GET /devices/{device_id}/config`, `PUT /devices/{device_id}/optimize-mode` (`off|approval|auto`).
      - Commands: `POST /devices/{device_id}/commands` (origin=manual), `GET /commands/{command_id}`.
      - Telemetry views: `GET /devices/{device_id}/events|kpis|health`.
      - Recommendations: `GET /devices/{device_id}/recommendations`, `POST /recommendations/{reco_id}:approve|:reject`.
  - **Agent endpoints** (Edge-Key, under `/agent`, fronted by gateway `/v1/agent/**`): `POST /register`, `POST /heartbeat`, `POST /telemetry`, `POST /devices/{cwmp_id}/config-snapshot`, `POST /poll`, `POST /commands/{command_id}/ack`.
  - **Command lifecycle** (`command_service`): the `commands` table is an at-least-once + idempotent transport for `configure|heal|optimise|query|reboot`. Create → `pending`; `poll` claims via `SELECT … FOR UPDATE SKIP LOCKED` (WHERE `edge_id`, `status='pending'`) and marks `dispatched`; `ack` is guarded on `status='dispatched'` → `applied|failed`. Lease 60 s / 5 attempts (OD3); a lease sweep re-queues expired `dispatched` rows; on failure with `rollback_on_fail` a rollback command is auto-emitted from `prev_values` (`origin=rollback`).
  - **Telemetry** (`ingest_service`): `heartbeat` auto-onboards/updates `nanolink_devices` (keyed on `cwmp_id`); tiered KPIs → `device_kpis` (unique on `(tenant_id, device_id, ts, tier)`); events parsed by `event_parser` → `device_events` (dedup on `(tenant_id, dedup_key)`); alarm severities roll up into device `health`; managed-param snapshots → `device_config_snapshots`.
  - **Optimiser P1** (`self_optimizer`): EWMA anomaly detection (**z computed before the EWMA update** — the after-update ordering never fired) plus guard-railed energy/coverage rules → `optimization_recommendations`. `optimize_mode` gates materialisation: `auto` auto-materialises an optimise command, `approval` waits for operator approve, `off` no-ops; guardrail breach triggers rollback. EWMA state is in-memory (OD7). `healer.on_new_events` is a **no-op hook** in this scope.
  - **ORM**: `edge_devices`, `nanolink_devices`, `commands`, `device_config_snapshots`, `device_events`, `device_kpis`, `optimization_recommendations` (see `artifacts/design/schemas.sql` / migration 009 for authoritative columns). Deployed Postgres role **must be non-superuser** or RLS is silently disabled.

-----

## 6\. Data Sim / Data Platform — `maveric_platform_data_sim` (FastAPI)

Role (re-architecture E1): the **Data Platform** — per-vendor ingestion adapters → canonical PM/FM/CM tables + raw S3 (store-only), plus the synthetic data factory it always was.

### Data Platform endpoints (`app/api/v1/endpoints/ingest.py`, `data_query.py`; gateway-routed `/ingest/**`, `/data/**`)

  - `POST /tenants/{t}/ingest/uploads` — queue a generalized ingest job (`{job_id?, source_type, params}`; `source_type=nybsys_pm_csv` first). 202; atomic-or-nothing (Kafka publish failure removes the job row and returns 503). Work happens in the `maveric.ingest.pm.v1` consumer running inside the API container (no new deployable); the topic also carries `kind=records` inline batches from streaming sources (frozen HLD A.5).
  - `GET /tenants/{t}/ingest/jobs/{job_id}` — job state incl. `stats` and `error`; `GET /tenants/{t}/ingest/adapters` lists registered source types and whether each is implemented.
  - `GET /tenants/{t}/data/pm` — canonical PM query; filters `dn` (repeatable), `dn_prefix`, `metric` (repeatable), `source`, `vendor`, `from_ts`, `to_ts`, `day`, `tick`, `upload_id`, `order`; keyset pagination via `cursor`/`next_cursor` (index: migration 016) with legacy `offset` retained. An empty list is a valid answer, never a 404.
  - `GET /tenants/{t}/data/fm` — FM alarms (filters on `raised_at`; `state`, `severity` repeatable); `GET /tenants/{t}/data/cm` — CM records (filters on `captured_at`; `origin ingest|read_back|operator`).
  - Legacy `/custom/nybsys/uploads*` served verbatim (`app/api/v1/custom/nybsys_uploads.py`, see §5) with the same `tenants.feature_flags['nybsys']` guard smo_sim uses.
  - Ingestion framework (`app/ingest/`): adapter registry + `service.py` job lifecycle + `consumer.py` (Kafka) + `dictionary.py` (`vendor_dictionaries` vendor→canonical metric mapping, TS 28.552 names where mappable, else `vendor:<name>`) + `builder_hook.py` (`NdtApiBuilder` → bdt_engine `/ndt/feature-builds` seam). Tables: `pm_measurements` (monthly partitions), `fm_alarms`, `cm_records`, `ingest_jobs`, `vendor_dictionaries` (migration 011).

### Synthetic data factory endpoints

  - `POST /tenants/{t}/utils/topology/generate` — synthesize baseline artifacts (topology, config, UE training data) using 3GPP-compliant golden generators (`generate_golden_topology_from_bbox`, `generate_ue_training_data`) in S3 and persist the baseline row. Optional `TopologyDetails` fields (`site_type`, `rng_seed`, `vary_tilt`, `vary_power`, `vary_azimuth`, `carrier_frequencies_mhz`, `num_ues`, `top_k_cells`, `apply_shadow_fading`) control generator behavior; output column schemas are unchanged.
  - `POST /tenants/{t}/utils/traffic-load/generate` — accept `{baseline_id, dataset_id?, days, num_ues, spatial_params?, time_params?, random_seed?, notes?}` payloads; inline path loads the baseline topology from S3, invokes RADP’s `spatial_traffic_load_gen`, and writes the consolidated dataset back to `{prefix?}{tenant}/ue/{dataset_id}/synthetic_dataset.csv` (default: `s3://{bucket}/tenants/{tenant}/ue/{dataset_id}/synthetic_dataset.csv`).
  - `POST /tenants/{t}/utils/mobility/generate` — accept `{dataset_id?, ue_tracks_generation}` payloads mirroring the RADP mobility generator structure.

### Behavior

  - **Golden generator module flow**: `topology_generator.py` uses `generate_golden_topology_from_bbox()` → selects legacy 10-column topology_df and 3-column config_df → `generate_ue_training_data(GoldenUEConfig)` → maps golden UE output (`cell_rxpwr_dbm` → `avg_rsrp`, `longitude` → `lon`, `latitude` → `lat`) to legacy 5-column ue_training_df. Output schemas stay unchanged; only internal generation quality improves (3GPP path loss, antenna patterns, shadow fading, LOS probability).
  - **Golden-enhanced data generation (planned)**: Both traffic-load and mobility generators to be upgraded with golden 3GPP-compliant logic. Output schemas unchanged for both generators; only data quality improves. Enhancements: **(1) UE positioning** — traffic-load: replace uniform Voronoi polygon sampling with `generate_ue_positions_around_cells()` (distance-weighted near/mid/far bands around cell sites); mobility: apply cell-aware position anchoring to shift Gauss-Markov tracks so initial UE positions cluster around cell sites. **(2) RF-aware space_type** (traffic-load only) — derive `space_type` from actual inter-site distance using `ISD_RANGES_M` thresholds (dense_urban: 200-500m, urban: 500-1km, suburban: 1-3km, rural: 3-10km) instead of random proportion-based assignment. **(3) RSRP-weighted UE density** (traffic-load only) — bias UE distribution toward areas with better signal by computing per-polygon coverage quality via `calculate_ue_cell_rsrp()` and `RSRP_RANGES`; total UE count per tick stays the same, just redistributed toward good-coverage areas.
  - Traffic-load and mobility generation both run inline and respond with the created dataset envelope; callers may provide `dataset_id` to align with pre-created S3 prefixes. The service strips whitespace, forbids path separators, and rejects duplicate `(tenant_id, dataset_id)` pairs with HTTP 409. When `dataset_id` is omitted a UUID is generated before persisting artefacts and the Postgres record. No Kafka fallback is used for utils data.
  - Store generated CSV in S3 (UE datasets use the canonical `synthetic_dataset.csv` filename for traffic runs and `synthetic_dataset_mobility.csv` for mobility runs, populating both `url_to_smo_ue_data_csv` and the legacy training alias), register dataset in Postgres, profile to Mongo. The record is inserted with `source_type` set to `utils_mobility` for mobility flows. S3 uploads use the same ARN/assume-role aware client and normalise bare keys with `S3_PREFIX`.
  - Request logging middleware attaches `X-Request-ID`, logs request/response lifecycle events (including tenant, path, latency) to STDOUT + MongoDB `application_logs` (TTL by severity), and pushes domain failures into `error_logs` (90‑day TTL) with `{tenant_id, service_name, created_at}` indexes; Redis connectivity is wired for optional cache/rate-limit helpers but the service continues if the store is unavailable. Log search + resolution endpoints are exposed at `/v1/tenants/{tenant_id}/utils/logs/errors|.../resolve|/logs/stats` with `/v1/logs/health` for the Mongo TTL/index probe; `/health` backs Docker/K8s liveness checks.
  - Configuration: `DATABASE_URL` may be provided as `postgres://…` or `postgresql://…` and can contain reserved characters in credentials. The service normalises the DSN (percent-encoding as needed) before constructing the SQLAlchemy engine, preventing host parsing errors in production.

-----

## 6A\. AI Copilot — `cloudlynet_ai_copilot` (FastAPI + LangGraph + FastMCP)

### Endpoints

Gateway-routed public contract:
- `/v1/tenants/{tenant_id}/copilot/**`

Internal copilot service contract:
- `/v1/tenants/{tenant_id}/copilot/**`
- Gateway proxies copilot tenant routes unchanged; the backend also retains direct `/api/v1/**` aliases for rollout/debug and compose/container probes.
- Gateway forwards `X-API-Key` from `COPILOT_BACKEND_API` to copilot upstream.
- Copilot backend now mounts native tenant-scoped routes directly under `/v1/tenants/{tenant_id}/copilot/...`.
- Backend CORS middleware is opt-in (`ENABLE_CORS`), with gateway as the default CORS owner in platform mode (`CORS_ALLOW_ORIGINS` in all environments; localhost fallback only when gateway is not in release mode).
- Dependency-aware health checks should target `/v1/tenants/{tenant_id}/copilot/health`; legacy direct `/api/v1/health` remains available for local compose and container probes, while `/health` is only the lightweight process check.
- Frontend must execute a session-first sequence:
  1) `POST /v1/tenants/{tenant_id}/copilot/sessions`
  2) `POST /v1/tenants/{tenant_id}/copilot/agents/query` with returned `session_id`
- `POST /sessions` creates conversation session metadata only; assistant message generation occurs on `POST /agents/query`.
- `GET /v1/tenants/{tenant_id}/copilot/agents` now returns only the user-selectable picker values (`debugger_agent`, `data_generation_agent`, `offline_debugging_agent`). Internal `reactive_agent` and `generic_agent` remain backend-only auto-routing/fallback paths and may still appear in stored `agent_response.agent_id`.
- Branch validation/rebase note (2026-02-28): `submodule/cloudlynet_ai_copilot:epic/copilot` aligned with `main` and introduced no new public copilot API route.
- Copilot env template guardrail: `backend/.env.example` should keep placeholder `GROQ_API_KEY` values and shared infra hosts (`postgres`, `redis`, `minio`).
- Production Helm guardrail: `submodule/maveric-deployment/argocd/maveric_platform_copilot/values.yaml` must keep backend-style env names while translating prod DSNs to `postgresql+asyncpg://...` format and pointing runtime traffic at the dedicated copilot database/credentials documented in `artifacts/copilot/copilot_prod.md`.
- Gateway production guardrail: `submodule/maveric-deployment/argocd/maveric_platform_gateway/values.yaml -> secretData.COPILOT_BASE_URL` should point at `http://copilot-backend.<namespace>.svc.cluster.local:8000`, matching the rendered copilot Service DNS instead of relying on the short hostname.

  - `GET /health`, `GET /` (root service checks/info)
  - `GET /v1/tenants/{tenant_id}/copilot/health`, `/live`, `/ready`
  - `GET /v1/tenants/{tenant_id}/copilot/users/profile`, `/settings`
  - `POST/GET /v1/tenants/{tenant_id}/copilot/sessions`, `PATCH/DELETE /v1/tenants/{tenant_id}/copilot/sessions/{session_id}`
  - `GET /v1/tenants/{tenant_id}/copilot/sessions/{session_id}/messages`
  - `GET /v1/tenants/{tenant_id}/copilot/agents`, `POST/PATCH /v1/tenants/{tenant_id}/copilot/agents/query`

### Internals

  - `SessionService` persists conversation state across:
      - `conversation.conversation_session`
      - `conversation.conversation_message`
      - `conversation.conversation_message_version`
  - `AgentQueryService` executes multi-agent orchestration via LangGraph and stores versioned responses (`agent_response` JSONB).
  - Action execution path should be allowlist-driven and gateway-mediated:
      - copilot generates operation intent
      - mutating operations require explicit confirmation
      - executor calls approved gateway routes only (never direct service DB/API bypass)
  - RAG retrieval uses pgvector in `knowledge.document_chunk.embedding` (384 dimensions), plus source/document metadata tables.
  - MCP server (`app/mcp_server/server.py`) exposes:
      - `compare_rapp_policies`
      - `get_platform_error_logs`
    and calls the platform gateway APIs using `MCP_CLOUDLYNET_BASE_URL`.
  - Production deployment packaging lives in `submodule/maveric-deployment`:
      - ArgoCD Helm chart: `argocd/maveric_platform_copilot`
      - Jenkins promotion pipeline: `jenkins/maveric_platform_copilot.groovy`
      - one Helm release deploys both `copilot-backend` (service `copilot-backend:8000`) and `copilot-mcp-server` (service `copilot-mcp-server:8080`)
      - ordered rollout now also includes a chart-packaged `knowledge_base.tgz` archive and `copilot-backend-knowledge-base` ArgoCD `Sync` hook job; hook order is migration SQL first, knowledge-base bootstrap second, backend/MCP deployments third
      - chart secret payload is values-driven and points to already-running cluster Postgres, Redis, and object-storage services rather than provisioning new infra
      - production bootstrap/migration SQL is documented separately in `artifacts/copilot/copilot_prod.md`; runtime access should use the restricted app role after grants are applied
      - service name lookup path for the backend is `argocd/maveric_platform_copilot/templates/backend-service.yaml` plus `_helpers.tpl` (`backendFullname`), which currently renders `copilot-backend`

### Isolation Model

  - Copilot runtime is intentionally isolated from primary platform data:
      - dedicated databases on shared postgres: `netai_copilot`, `netai_copilot_test`
      - dedicated roles on shared postgres: `netai_copilot_owner`, `netai_copilot_app`
      - dedicated bucket namespace on shared MinIO (`netai-copilot-files`)
      - dedicated schema bundle: `artifacts/copilot/copilot_schemas.sql`
      - dedicated bootstrap/repair script for existing shared Postgres volumes/clusters: `artifacts/db/init_copilot.sql`
      - dedicated conversation-table RLS bundle: `artifacts/db/init_copilot_rls.sql`
      - `pgvector` must be installed or available on the shared Postgres service before copilot schema migrations run
      - local compose and prod rollout intentionally keep bootstrap, schema, and RLS as separate steps
      - tracked local env uses explicit role/database variable names (`COPILOT_POSTGRES_OWNER_*`, `COPILOT_POSTGRES_APP_*`, `COPILOT_POSTGRES_RUNTIME_DB`, `COPILOT_POSTGRES_TEST_DB`) rather than the older single-user `netai_copilot_dev` pattern
  - Copilot backend and MCP server run on shared `maveric` network in compose.
  - Gateway and copilot connectivity remains required for `/v1/tenants/{tenant_id}/copilot/**` proxying.
  - Detailed rollout steps and controls are documented in `artifacts/copilot/plan.md`.
  - Frontend implementation details are documented in `artifacts/upgrade_plans/frontend_agent.md` with separate sections per microservice.
  - Trial signup frontend behavior, `trial_user` restrictions, and admin lead-list expectations are documented in `artifacts/frontend/API_Contracts.md` §7.0.

-----

## 7\. Error Handling & Idempotency

  - `Idempotency-Key` header supported on training endpoints; unique per tenant.
  - **Canonical error codes**: `BAD_REQUEST`, `VALIDATION_ERROR`, `UNAUTHORIZED`, `FORBIDDEN`, `NOT_FOUND`, `CONFLICT`, `RATE_LIMITED`, `INTERNAL_ERROR`, `DEPENDENCY_ERROR`, `TIMEOUT`, `JOB_FAILED`, `TENANT_REQUIRED`, `TENANT_FORBIDDEN`, `TENANT_NOT_FOUND`.
  - **Multi-Tenancy error codes** (Gateway platform admin & tenant user endpoints):
    - `USER_NOT_FOUND` (404) — User not found in tenant
    - `ADMIN_NOT_FOUND` (404) — Platform admin not found
    - `TENANT_NOT_FOUND` (404) — Organization not found
    - `TENANT_FORBIDDEN` (403) — Insufficient role for action (requires `tenant_admin`)
    - `PLATFORM_ADMIN_REQUIRED` (403) — Not a platform admin (requires `cloudly_admin`)
    - `EMAIL_ALREADY_EXISTS` (409) — Email already exists in another org (1:1 constraint)
    - `CLOUDLYIO_ORG_PROTECTED` (403) — Cannot delete CloudlyIO platform org
    - `PROTECTED_ADMIN` (409) — Cannot delete primary admin (protected email)
  - The rApp inference endpoint surfaces malformed JSON as a 422 response with a guidance message reminding clients to wrap string identifiers (for example `baseline_id`, `bdt_id`, `ue_dataset_id`) in double quotes.

### Data Sim — Error Codes & Persistent Log Schema

Durable reference for `maveric_platform_data_sim` structured logging. Every failure emits an `error_logs` document with a machine-readable `error_code`; the middleware also writes an `application_logs` document per request. `service_name` defaults to `data-sim` (`config.py:APP_NAME`).

  - **Log API paths** (`app/api/v1/endpoints/error_logs.py`):
      - **Canonical**: `GET /v1/tenants/{tenant_id}/logs/errors`, `GET /v1/tenants/{tenant_id}/logs/errors/{error_id}`, `PATCH /v1/tenants/{tenant_id}/logs/errors/{error_id}/resolve`, `GET /v1/tenants/{tenant_id}/logs/stats`; public `GET /v1/logs/health` (Mongo TTL/index probe, no auth).
      - **Deprecated aliases** (`deprecated=True`, still routed): `/v1/tenants/{tenant_id}/utils/logs/errors`, `.../utils/logs/errors/{error_id}`, `.../utils/logs/errors/{error_id}/resolve`, `.../utils/logs/stats` (EPIC #300 §1.5).

  - **`error_logs` collection** (`app/db/mongo_handler.py`):
      - **Fields**: `tenant_id`, `service_name`, `severity` (`warning`|`error`|`critical`, defaulted/normalized), `error_code`, `error_message`, `error_type`, `stack_trace`, `context` (object), `metadata.environment`, `resolved` (bool), `resolved_at`, `resolved_by`, `notes`, `created_at`, `expires_at`.
      - **Indexes**: `(tenant_id, created_at desc)`, `(tenant_id, service_name, created_at desc)`, `(severity, created_at desc)`, `(tenant_id, resolved, created_at desc)`, `(tenant_id, service_name, resolved, created_at desc)`, `(context.request_id)`, `(expires_at)` TTL.
      - **TTL**: `expires_at = created_at + MONGODB_ERROR_LOG_RETENTION_DAYS` (default **90 days**, min 1).

  - **`application_logs` collection** (`app/utils/mongo_log_handler.py`, gated by `MONGODB_APPLICATION_LOG_ENABLED`, default true):
      - **Fields**: `tenant_id` (default `system`), `level`, `service_name`, `logger_name`, `message`, `context` (object; carries `request_id`, `method`, `status_code`, `duration_ms`, `event`), `file_path`, `line_number`, `function_name`, `process_id`, `thread_name`, `created_at`, `expires_at`, optional `exception.{type,message}`.
      - **Indexes**: `(tenant_id, service_name, created_at desc)`, `(level, created_at desc)`, `(context.request_id)`, `(logger_name, created_at desc)`, `(expires_at)` TTL.
      - **TTL**: per-level in the handler (authoritative) — CRITICAL 90d, ERROR 90d, WARNING 30d, INFO 30d, DEBUG 7d. `MONGODB_APPLICATION_LOG_RETENTION_DAYS` (default 30) is a config-parity field only.

  - **Error-code catalogue** (all `error_code` values raised via `log_error_to_mongodb`; message = the emitted `error_message`):

| Error Code | Source (`app/…`) | Meaning |
| --- | --- | --- |
| `HTTP_{status_code}` | `main.py:48` | HTTP exception handler; code is dynamic per status. Message = the HTTP detail |
| `REQUEST_VALIDATION_FAILED` | `main.py:81` | Request body/param validation error (422) |
| `UNHANDLED_EXCEPTION` | `main.py:114` | Uncaught exception in the app-level handler; message = `str(exc)` |
| `UNHANDLED_REQUEST_ERROR` | `middleware/logging_middleware.py:114` | Request failed in the middleware wrapper (`{method} {path} failed`) |
| `S3_CONFIG_INVALID` | `utils/s3wrap.py:50` | Invalid S3 configuration |
| `S3_CLIENT_INIT_FAILED` | `utils/s3wrap.py:80` | Failed to initialize S3 client |
| `S3_CLIENT_REFRESH_FAILED` | `utils/s3wrap.py:106` | Unable to refresh S3 client |
| `S3_NO_CREDENTIALS` | `utils/s3wrap.py:170,279` | AWS credentials unavailable for S3 upload/download |
| `S3_UPLOAD_FAILED_AFTER_REFRESH` | `utils/s3wrap.py:189` | S3 upload failed even after credential refresh |
| `S3_UPLOAD_FAILED_FALLBACK` | `utils/s3wrap.py:208` | S3 upload failed; falling back to local file |
| `S3_DOWNLOAD_FAILED_AFTER_REFRESH` | `utils/s3wrap.py:298` | S3 `get_object` failed after refresh |
| `S3_DOWNLOAD_FAILED_FALLBACK` | `utils/s3wrap.py:317` | S3 `get_object` failed; falling back to local file |
| `KAFKA_PRODUCER_INIT_FAILED` | `event_handlers/kafka_handler.py:63` | Failed to initialize Kafka producer |
| `KAFKA_SEND_MESSAGE_FAILED` | `event_handlers/kafka_handler.py:104` | Failed to send message to Kafka |
| `KAFKA_CONSUMER_INIT_FAILED` | `event_handlers/kafka_handler.py:181` | Failed to initialize Kafka consumer |
| `KAFKA_CONSUME_MESSAGES_FAILED` | `event_handlers/kafka_handler.py:230` | Error consuming messages from topic |
| `GRPC_CLIENT_CONNECT_FAILED` | `event_handlers/grpc_handler.py:27` | Failed to connect gRPC client |
| `GRPC_SERVER_INIT_FAILED` | `event_handlers/grpc_handler.py:66` | Failed to initialize gRPC server |
| `GRPC_SERVER_START_FAILED` | `event_handlers/grpc_handler.py:91` | Failed to start gRPC server |
| `GRPC_SERVER_STOP_FAILED` | `event_handlers/grpc_handler.py:114` | Error stopping gRPC server |
| `SQL_DATABASE_INIT_FAILED` | `db/sql_handler.py:127` | Failed to initialize SQL database |
| `SQL_CREATE_TABLES_FAILED` | `db/sql_handler.py:167` | Failed to create tables |
| `REDIS_INIT_FAILED` | `db/redis_handler.py:50` | Failed to initialize Redis |
| `BASELINE_QUERY_FAILED` | `db/baseline_repo.py:61` | Failed to query baselines |
| `BASELINE_INSERT_FAILED` | `db/baseline_repo.py:165` | Failed to insert baseline |
| `BASELINE_FETCH_FAILED` | `db/baseline_repo.py:218` | Failed to fetch baseline |
| `UE_DATASET_INSERT_FAILED` | `db/utils_repo.py:144` | Could not insert into `ue_datasets` (maybe schema missing) |
| `TRAINING_JOB_INSERT_FAILED` | `db/utils_repo.py:270` | Could not insert into `training_jobs` (maybe schema missing) |
| `MOBILITY_GENERATOR_IMPORT_FAILED` | `utils/mobility_generator.py:172` | Failed to import mobility generator |
| `MOBILITY_DATASET_GENERATION_FAILED` | `utils/mobility_generator.py:186` | Failed to generate mobility dataset (generator layer) |
| `TOPOLOGY_UPLOAD_FAILED` | `utils/error_logger.py:47`, `api/v1/endpoints/sim_utils.py:229` | Failed to upload topology artifacts for baseline |
| `BASELINE_NOT_FOUND` | `api/v1/endpoints/sim_utils.py:381` | Baseline not found for traffic generation |
| `MISSING_DEPENDENCY` | `api/v1/endpoints/sim_utils.py:398,535` | Spatial-traffic / mobility generator missing a required dependency |
| `TRAFFIC_GENERATION_FAILED` | `api/v1/endpoints/sim_utils.py:419` | Failed to generate spatial traffic dataset |
| `MOBILITY_GENERATION_FAILED` | `api/v1/endpoints/sim_utils.py:556` | Failed to generate mobility dataset (endpoint layer) |
| `API_KEY_NOT_CONFIGURED` | `utils/security.py:27` | Server misconfigured: API key is not set |
| `AUTH_MISSING_API_KEY` | `utils/security.py:47` | API key missing from request |
| `AUTH_INVALID_API_KEY` | `utils/security.py:69` | Invalid API key provided |

  - **Drift note** (verified against code, reconciling the deleted `LOGGING_STRATEGY.md` "26 error codes" list): the code has **37 static codes** plus the dynamic `HTTP_{status_code}`. Three doc-listed codes do **not** exist in code — `S3_UPLOAD_FAILED` and `S3_DOWNLOAD_FAILED` were each split into `*_AFTER_REFRESH`/`*_FALLBACK` pairs, and `S3_DELETE_FAILED` has no call site. Fourteen codes present in code were absent from that list (`HTTP_{status_code}`, `REQUEST_VALIDATION_FAILED`, `UNHANDLED_EXCEPTION`, `UNHANDLED_REQUEST_ERROR`, `S3_CLIENT_REFRESH_FAILED`, the four `S3_*_AFTER_REFRESH`/`*_FALLBACK` codes, `TOPOLOGY_UPLOAD_FAILED`, `BASELINE_NOT_FOUND`, `MISSING_DEPENDENCY`, `TRAFFIC_GENERATION_FAILED`, `MOBILITY_GENERATION_FAILED`). The table above is the reconciled, code-verified catalogue.

-----

## 8\. Local & Prod Configuration

  - **Local**: `docker‑compose` for all services including Postgres, Mongo, Redis, Kafka, MinIO.
  - **Prod**: EKS; use AWS S3 (no MinIO), still keep Postgres/Mongo/Redis/Kafka in pods as requested.
  - Current deployment status (`kafka_plan.md`) is an initial single-broker rollout with Kafka/ZooKeeper persistence, declarative training-topic creation, and matching local compose topic bootstrap. The sibling deployment charts now support `persistence.existingClaim`; production defaults to the shared `efs-pvc` claim already used by rApp/BDT, mounts isolated `kafka`, `zookeeper/data`, and `zookeeper/log` subpaths instead of creating new PVCs, uses init-container permission bootstrap so Confluent's writable-path preflight succeeds on the reused claim, and stores worker Kafka timeout defaults as quoted decimal strings so Helm cannot reserialize them as `1.44e+07`. Multi-broker HA and lag-based autoscaling remain future work.
  - All Python services (BDT, rApp, SMO Sim, Data Sim) normalise `DATABASE_URL` before initialising SQLAlchemy, and the Gateway does the same for `POSTGRES_DSN`, so production credentials with reserved characters work without manual escaping.
  - **Secrets**: `.env` in dev; AWS Secrets Manager via ESO in prod.

-----

## 9\. Testing Strategy

  - **Contract tests**: `schemathesis` against `openapi.yaml`.
  - **RLS tests**: cross‑tenant attempts must fail (psql harness).
  - **Load tests**: k6/Locust for list/train/infer endpoints.
  - **Integration**: end‑to‑end flow (baseline→BDT→rApp train→inference) with synthetic data.
