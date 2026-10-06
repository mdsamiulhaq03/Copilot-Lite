# CloudlyNet — High‑Level Design (SaaS, AWS, Cognito)

**Version:** 0.7.0
**Version lockstep:** the three canonical design docs (HLD.md, LLD.md, openapi.yaml) version-bump together. Any PR that changes one bumps all three to the same version.
**API:** `openapi.yaml` (OpenAPI 3.0.3, auto-migration aligned schema)
**Auth & Tenancy:** AWS Cognito (User Pool ID tokens + custom claims)
**Hosting:** AWS (EKS for workloads, S3 for object storage). DBs/cache/broker **in pods** for portability (Postgres, MongoDB, Redis, Kafka).
**Related documents:** [`internal-contracts.md`](./internal-contracts.md) - the binding east-west, storage and data-layer contracts (shared-table ownership, S3 key templates, the shared model volume, service auth).

-----

## 1\. Goals & Scope

  - **SaaS, multi‑tenant** platform for cellular optimization built around a **Network Digital Twin**; its Bayesian Digital Twin (BDT) engine is derived from Maveric (Linux Foundation Connectivity).
  - **Contract‑first** implementation using the attached OpenAPI.
  - **Strict isolation** by tenant across API, storage, caching, and observability.
  - **Observability‑first:** structured JSON logs, OpenTelemetry tracing, Prometheus metrics.
  - **Separation of concerns:** four re-architected service roles — **Data Platform** (data_sim), **Network Digital Twin** (bdt_engine), **RAN Intelligence** (rapp), **Actuation & Integration** (smo_sim) — as independent repos & processes (see §2).

### Out‑of‑scope (for now)

  - Advanced billing/quotas UI (we expose internal counters).
  - GPU training. (Future: dedicated nodegroup/pool).

-----

## 2\. Services & Repositories

### Re-architected service roles (2026-08; containers, charts, images, ports UNCHANGED)

The four Python services were re-scoped by the re-architecture program (frozen HLD, `artifacts/docs/cloudlynet-rearchitecture/01-hld-frozen.md`). Deployables did not change — the roles did:

| Service (container/port unchanged) | Role |
|---|---|
| data_sim :8003 | Data Platform: per-vendor ingestion adapters -> canonical PM/FM/CM tables (Postgres) + raw S3; synthetic data factory; ingestion Kafka consumer runs inside the API container (no new deployable) |
| bdt_engine :8000 | Network Digital Twin: twin engines (Maveric BDT GP; commercial slot), twin feature builder, evaluate API, KPI tracking, loop decision hub |
| rapp :8001 | RAN Intelligence: rApp/xApp model registry + Kafka training, recommendation inference (twin evaluation delegated to NDT via NDT_BASE_URL/NDT_API_KEY), RIC integration layer (app/ric/) |
| smo_sim :8002 | Actuation & Integration: NanoLink TR-069 control plane, actuator adapter framework (app/actuators/), wired placeholders (o1_netconf, ocudu_ws_collector, open_mplane, sas_domain_proxy, nms_northbound). E2/R1 facades deleted (D4) |

**Closed loop:** rapp emits recommendation proposals → NDT evaluates on the twin + tenant loop policy (`off|approval|auto`, mirroring `optimize_mode`) → dispatches: device config via smo_sim adapters, or RAN policy via rapp RIC layer → feedback (device KPIs from smo_sim, canonical PM from data_sim) → NDT guardrail watch → rollback through the same adapter. Defense in depth: smo_sim's existing device-level guardrail watcher + auto-rollback stays.

  - **Frontend** — `maveric_platform_frontend` (Next.js, Tailwind, D3).
  - **Gateway** — `maveric_platform_gateway` (Go, Gin): AuthN/Z, rate limit, routing, response envelopes.
    - Public auth remains Cognito JWT at the gateway. For east-west traffic the gateway now injects service-specific `X-API-Key` headers on proxied BDT/rApp/SMO/Data Sim `/v1` calls, and those FastAPI services reject missing or invalid keys on their internal APIs.
    - Local Docker guardrail: the compose gateway runs as a compiled image without a source bind-mount, so after proxy/auth changes it must be rebuilt/recreated or stale binaries will keep dropping the new internal `X-API-Key` forwarding and cause downstream `AUTH_MISSING_API_KEY` failures.
    - Local Cognito admin guardrail: platform-admin flows (`/v1/admin/**`) require `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` in the gateway local `.env`. The deployment Helm gateway `secretData` is the source of truth for those credentials; do not point local compose at a developer-specific `~/.aws` profile.
    - **NanoLink agent ingress** (`/v1/agent/**`): a dedicated proxy group fronts the GO Agent API on SMO Sim with **no Cognito** — edge identity is established by Edge-Key (`X-Edge-Key`) auth inside SMO Sim. The gateway rate-limits by IP, **bypasses AuthN** (the path is on the AuthN allowlist), and injects the service `SMO_API_KEY`; it does **not** apply `RequireMembership`. Because the gateway is a compiled binary, the route group only takes effect after a rebuild/recreate.
  - **BDT Engine / Network Digital Twin (NDT)** — `maveric_platform_bdt_engine` (FastAPI): the Network Digital Twin service — twin engines (Maveric BDT GP; commercial engine slot), twin feature builder (`app/feature_builder/`, the semi-synthetic enrichment moved from smo_sim's nybsys pipeline stages 3–6; every derived artifact is labeled `semi_synthetic=true` in `baselines.stats`), twin evaluation API (`/ndt/evaluate`, tick sync / day async), KPI tracking (`/ndt/kpis`, `ndt_kpi_snapshots`), and the closed-loop **decision hub** (`/ndt/loop/**`: policy + guardrail gates, approve/reject, dispatch on `maveric.loop.action.v1`, feedback watch, rollback ordering). `/v1/tenants/{t}/ndt/**` is gateway-routed (Cognito + RequireMembership, `BDT_API_KEY` injected server-side) since E5.S7; bdt_engine still also accepts a direct `X-API-Key` on :8000 for service-to-service callers (rapp uses `NDT_BASE_URL`/`NDT_API_KEY`). It also keeps the legacy BDT model registry + training + asynchronous inference surface: `/bdt/**` including `POST/GET /bdt/models/{bdt_id}/infer[...]`. The worker normalises S3 object locations, accepting absolute URLs or keys relative to the configured `S3_PREFIX`, and prints the effective bucket/region/endpoint at boot for faster environment diagnostics. Trained model maps are persisted locally under `/app/var/models/{tenant_id}/bdt/{bdt_id}.pickle` (the base directory is now resolved via `BDT_WORKER_MODEL_BASE_DIR`/`RAPP_WORKER_MODEL_BASE_DIR` so we can relocate the shared volume without code changes) and uploaded to S3 as `…/bdt/{bdt_id}/{bdt_id}.pickle` so every consumer observes a single canonical filename (`*.pickle`) instead of the previous `model.bin` variance. The new BDT inference runner stores run lifecycle state in `bdt_inference_runs` (`queued|running|completed|failed`) and executes the prediction pipeline in a bounded `ThreadPoolExecutor` so HTTP requests return quickly with a pollable `run_id`. Training reliability hardening adds consistent model/job state transitions, idempotent skip for redelivered terminal jobs, and partition-scoped contiguous Kafka commits for parallel consumers.
    - S3 access now favours AWS-provided credentials + `S3_BUCKET_ARN` (optional `S3_ASSUME_ROLE_ARN` / `S3_ASSUME_ROLE_EXTERNAL_ID`) over static endpoints. Incoming CSV references may be HTTPS URLs, `s3://` URIs, or full S3 ARNs; the worker refreshes credentials when they expire and falls back to the configured tenant prefix when callers submit bare keys. HTTP endpoints that point at MinIO or other S3-compatible gateways are treated as S3 only when they include the configured bucket/prefix; unrelated HTTP hosts are rejected to avoid fetching arbitrary content.
  - **rApp Engine / RAN Intelligence** — `maveric_platform_rapp` (FastAPI): rApp/xApp model registry, Kafka training, and recommendation inference; exposes `/rapps/**`. Twin evaluation is delegated to the NDT (`NDT_BASE_URL`/`NDT_API_KEY`) while the public day/tick `/infer` response contract stays byte-compatible; recommendation proposals are emitted to the NDT decision hub on `maveric.loop.proposal.v1`. Hosts the **RIC integration layer** (`app/ric/`, non-RT-first): `RanControlPort`/`RanDataPort` ports, the O-RAN SC NONRTRIC A1-PMS connector (`adapters/nonrtric/`), the `a1_policy` loop-action executor (background consumer of `maveric.loop.action.v1` inside the rapp container), the lab-only `nearrt_xapp` placeholder, and the R1-shaped packaging facade (`app/ric/r1_manifest.py`) — design bundle `artifacts/ric/`. Each trained model now records the `dataset_id` and `bdt_id` used during training so downstream services can trace artefacts back to the UE dataset and BDT baseline. Inference POSTs now return `202 Accepted` with a polling URL; the engine stores the request in `inference_runs` (status \*queued/running/completed/failed\*) together with the submitted `baseline_id`, `bdt_id`, `ue_dataset_id`, and `tick` before executing the RadP integration in an internal thread pool so we avoid blocking the training Kafka consumer. Clients poll `/rapps/{id}/models/{model_id}/infer/{run_id}` until completion. A new synchronous comparison endpoint (`POST /tenants/{tenant_id}/rapps/compare/infer`) runs both models against the same baseline/BDT/UE context. When the compare model lives under a different rApp ID the service now resolves the override RadPLib identifier, dispatches to the matching shared Non-MRO inference harness (ES, LB, or CCO), and then reuses the base rApp’s optimisation/plotting pipeline so the returned metrics remain comparable; unsupported overrides are limited to MRO. The endpoint can still emit a baseline curve by passing `compare_rapp_model_id=BASELINE`. All request handlers set the Postgres tenant context (`set_current_tenant`) before touching the database so RLS remains enforced, and the API returns a clear 422 response when the JSON payload is malformed (common mistake: missing quotes around string identifiers). The inference data loader automatically pins UE samples to the first available `day`, synthesizes `loc_x`/`loc_y`/`mock_ue_id` columns from `lon`/`lat`/`ue_id` so older synthetic datasets continue to work without re-exporting CSVs, and the plot builder groups UE points under their serving cell IDs. Non-MRO architecture is now deliberately two-family: MRO remains separate, while ES/LB/CCO share one generic RL package (`app/radplib/non_mro`) and differ only by reward weights. Those shared Non-MRO optimisation metrics mirror the training reward calculation with profile-specific weights over coverage, load-balance, and energy-saving terms, the operator-facing tick payload is aligned on `tick + items[{cell_id, el_degree, on_off}]`, and day-scope evaluation now also returns `per_tick_recommendations` with that same shape. Layered inference caching now backs this flow: a deterministic UUIDv5 `run_id` derived from `(tenant_id, rapp_model_id, baseline_id, bdt_id, ue_dataset_id, tick)` probes Redis (L1) and MongoDB (L2) before falling back to Postgres (L3). Cache hits return `200 OK`, misses keep the `202 Accepted` semantics but avoid spawning duplicate workers, and when Redis/Mongo fall behind the API rewrites the tiers from Postgres to maintain consistency. The cache can be disabled via `CACHE_ENABLED=false`, and `REDIS_URL` / `MONGODB_URL` wire the external stores without code changes so dev environments without those services still function; hardening keeps the cache layer optional by explicitly skipping L1/L2 when clients are absent instead of raising truthiness errors from PyMongo collections. Kafka-backed training scale is now in its initial implemented state: the worker uses partition-aware pause/resume, exact-offset commit, idempotent terminal-state skip, and deployment-managed timeout/replica settings. The current rollout starts at 2 partitions / 2 worker replicas for `maveric.rapp.train.v1`, with further SaaS growth tracked in `kafka_plan.md`.
    - rApp workers and synchronous loaders now use the same ARN/assume-role aware S3 client as the BDT engine, accepting HTTPS URLs, `s3://` URIs, S3 ARNs, or bare keys and refreshing credentials when AWS rotates them. HTTP(S) URLs are only resolved via S3 when they target the configured MinIO/S3 endpoint and expose the bucket/prefix; other hosts bypass the S3 client and are rejected. When a BDT pickle is missing from the shared volume the worker (and synchronous inference loader) transparently download the artifact from the recorded S3 URI into `/app/var/models/{tenant_id}/bdt/` before continuing, guaranteeing cross-pod availability. Trained rApp agents are mirrored to object storage using the canonical `{tenant_id}/models/rapps/{rapp_id}/{rapp_model_id}.zip` key even when the worker is running in local/EFS mode, and inference now resolves the stored artifact URIs (or derives the key from the template) to repatriate the `.zip` into `/app/var/models/{tenant_id}/rapps/{rapp_id}/` when a pod is missing the file.
    - Request logging middleware now mirrors the Data Sim correlation pattern, emitting `X-Request-ID` and structured request/response logs to STDOUT for every rApp call alongside the existing OTEL spans and Prometheus latency histogram.
  - **SMO Sim / Actuation & Integration** — `maveric_platform_smo_sim` (FastAPI): the actuation plane — NanoLink TR-069 control plane as-is, plus the **actuator adapter framework** (`app/actuators/`: `ActuatorAdapter` protocol, dispatch router keyed on the loop action `adapter` field, NanoLink TR-069 refactored onto it with no behavior change; wired placeholders `o1_netconf`, `ocudu_ws_collector`, `open_mplane`, `sas_domain_proxy`, `nms_northbound`; adapter/health surface proxied by the gateway at `/v1/actuators`). Command acks and guardrail events also publish `maveric.loop.feedback.v1`. The E2/R1 REST facades are **deleted** (frozen HLD D4; see §12), and the nybsys PM-ingestion uploads API moved to data_sim. Still owns baselines & UE datasets; exposes `/baselines/**`, `/ue-data/**`. Baseline deletion `DELETE /tenants/{tenant_id}/baselines/{baseline_id}` purges the tenant/baseline S3 prefix, and UE dataset uploads now require a caller-provided `dataset_id` aligned with the S3 prefix and support deletion via `DELETE /tenants/{tenant_id}/ue-data/datasets/{dataset_id}`, which also purges the corresponding S3 prefix. `url_to_smo_ue_data_csv` remains the canonical payload field and UE datasets accept `source_type` values `real`, `utils_traffic_load`, or `utils_mobility` (for mobility generator runs). Baseline GET responses now include `created_at` timestamp for tracking baseline creation time.
    - Purge helpers derive the effective bucket/access point from `S3_BUCKET_ARN`, prepend `S3_PREFIX`, and retry list/delete operations when AWS returns `NoCredentialsError`.
    - **Custom ingestion moved (re-architecture E1)**: `/custom/nybsys/uploads*` is now **served by data_sim** (Data Platform) with a byte-compatible contract — the gateway splits `/custom/**` per request (uploads → DATA, NanoLink device/edge ops → SMO). The semi-synthetic enrichment (topology synthesis, UE placement, RSRP labeling) now runs in bdt_engine's twin feature builder. Feature flag gating stays: `tenants.feature_flags` JSONB gates `/custom/*` per module (e.g., `{"nybsys": true}`), honored by data_sim the same way smo_sim honors it for the device/edge routes.
    - **NanoLink edge↔cloud control plane** (`/custom/nybsys/{edge-devices,devices,...}` operator API + `/agent/**` agent API, also gated by the `nybsys` feature flag): the cloud counterpart to the on-prem GO Agent that manages NybSys NanoLink cells via an in-agent TR-069/CWMP server. Edge hosts enroll once (enrollment token → Edge-Key), then run a poll loop; SMO Sim authenticates the Edge-Key, queues device commands through the unified `commands` table (claim-on-fetch + lease + auto-rollback), ingests tiered telemetry (KPIs, deduped events, config snapshots, alarm→health rollup), and runs a Phase-1 self-optimiser (EWMA anomaly + guard-railed energy/coverage rules → `optimization_recommendations`, gated by per-device `optimize_mode`). Operators drive edge/device CRUD, optimize-mode, manual commands, and recommendation approve/reject. See §9.12 for the data flow and §4 for the 7 backing tables.
  - **Data Sim / Data Platform** — `maveric_platform_data_sim` (FastAPI): the Data Platform — per-vendor ingestion adapters (`app/ingest/`, `nybsys_pm_csv` first) that parse/dedupe/aggregate into the canonical PM/FM/CM tables (`pm_measurements`, `fm_alarms`, `cm_records`, `ingest_jobs`, `vendor_dictionaries`; store-only, no synthesis) plus raw artifacts in S3; the ingestion Kafka consumer (`maveric.ingest.pm.v1`) runs inside the API container (no new deployable). Gateway-routed APIs: `POST /ingest/uploads`, `GET /ingest/jobs/{job_id}`, `GET /data/pm|/fm|/cm`, plus the relocated legacy `/custom/nybsys/uploads*` contract served verbatim. It remains the **synthetic data factory**: `/utils/**` (including `/utils/topology/generate` for 3GPP-compliant synthetic baseline creation using golden topology and UE generators with proper path loss, antenna patterns, shadow fading, and LOS probability).
    - Synthetic writers reuse the shared ARN/assume-role S3 client, so baseline/UE datasets generated by the service can stream directly into AWS-managed buckets even when only an ARN is provided.
    - Traffic-load and mobility generators accept optional caller-supplied `dataset_id` values (normalised to strip whitespace and forbid path separators); conflicts return HTTP 409 while omitted identifiers fall back to freshly generated UUIDs prior to persisting artefacts to S3/Postgres.
    - `/utils/traffic-load` and `/utils/mobility` are now served exclusively by Data Sim; the duplicate SMO Sim handlers have been removed so Gateway always forwards generation requests to the dedicated service.
    - **3GPP-compliant golden topology generation** — the `/utils/topology/generate` endpoint uses `generate_golden_topology_from_bbox` and `generate_ue_training_data` modules with proper 3GPP path loss models (UMa/UMi), antenna gain patterns, shadow fading, and LOS probability. Optional `TopologyDetails` fields (`site_type`, `rng_seed`, `vary_tilt`, `vary_power`, `vary_azimuth`, `carrier_frequencies_mhz`, `num_ues`, `top_k_cells`, `apply_shadow_fading`) enable callers to tune generation quality while output column schemas remain unchanged.
    - Request logging middleware issues `X-Request-ID` on every response and streams request/response logs to MongoDB `application_logs` (TTL by severity) while persisting domain failures to `error_logs` (90‑day TTL) with indexes on `{tenant_id, service_name, created_at}`; Redis connectivity is wired for cache/rate-limit hooks and fails open when the store is unavailable. Log introspection endpoints: Data Sim → `/v1/tenants/{tenant_id}/utils/logs/errors|.../resolve|/logs/stats`, SMO Sim → `/v1/tenants/{tenant_id}/baselines/logs/errors|...`, rApp → `/v1/tenants/{tenant_id}/rapps/logs/errors|...`, BDT → `/v1/tenants/{tenant_id}/bdt/logs/errors|...`, plus `/v1/logs/health` for Mongo readiness; container health probes target `/health`.
  - **AI Copilot** — `cloudlynet_ai_copilot` (FastAPI + LangGraph + FastMCP): conversational operations assistant with gateway-routed ingress and matching backend-native tenant routes on `/v1/tenants/{tenant_id}/copilot/**`, plus an MCP SSE server for platform tooling.
    - Copilot state is isolated logically via dedicated copilot databases (`netai_copilot`, `netai_copilot_test`) on shared platform Postgres and does not share `artifacts/design/schemas.sql`.
    - Shared Postgres bootstrap only creates or repairs copilot roles, databases, and extensions (`artifacts/db/init_copilot.sql`); local compose and production rollout apply schema and RLS separately via `artifacts/copilot/copilot_schemas.sql` and `artifacts/db/init_copilot_rls.sql`.
    - Tracked local compose env now uses explicit owner/app/runtime/test names (`COPILOT_POSTGRES_OWNER_*`, `COPILOT_POSTGRES_APP_*`, `COPILOT_POSTGRES_RUNTIME_DB`, `COPILOT_POSTGRES_TEST_DB`); local backend defaults keep the owner role for Alembic/test ergonomics while deployed runtime uses the restricted app role.
    - Existing shared Postgres volumes or cluster databases must rerun `artifacts/db/init_copilot.sql` before copilot health/routes are expected to pass.
    - Copilot operations execute against an allowlisted action catalog and call platform services through Gateway APIs (CRUD + training + inference + data-generation), preserving RBAC and tenant boundaries.
    - Gateway forwards `/v1/tenants/{tenant_id}/copilot/**` unchanged to copilot backend native tenant routes; legacy direct `/api/v1/**` aliases are retained only for rollout/debug and container probes.
    - Gateway forwards `X-API-Key` from `COPILOT_BACKEND_API` on copilot upstream requests.
    - Frontend chat flow is session-first: create session (`POST /copilot/sessions`) then query with returned `session_id` (`POST /copilot/agents/query`).
    - Public agent discovery via `GET /copilot/agents` now returns only the user-selectable agents (`debugger_agent`, `data_generation_agent`, `offline_debugging_agent`). Internal `reactive_agent` and `generic_agent` remain backend-only auto-routing/fallback paths and may still appear in response metadata.
    - Dependency-aware copilot health can use `/v1/tenants/{tenant_id}/copilot/health`; legacy direct `/api/v1/health` is retained for compose/container checks, while the root `/health` endpoint remains a lightweight process check.
    - Production Kubernetes delivery is defined in `submodule/maveric-deployment` as a single Helm chart (`argocd/maveric_platform_copilot`) plus one Jenkins pipeline (`jenkins/maveric_platform_copilot.groovy`) that builds and promotes backend + MCP images together.
    - The production copilot chart now also packages a curated knowledge-base archive and runs a dedicated ArgoCD `Sync` hook job to ingest/contextualize RAG content before `copilot-backend` and `copilot-mcp-server` roll.
    - Production copilot SQL bootstrap/migration steps are documented separately in `artifacts/copilot/copilot_prod.md`; the target deployment shape uses dedicated copilot owner/app roles and a dedicated runtime DB.
    - Gateway production `COPILOT_BASE_URL` must target the rendered backend service DNS `http://copilot-backend.<namespace>.svc.cluster.local:8000`; the service name is defined by the copilot chart helper `maveric_platform_copilot.backendFullname`.
    - Branch validation/rebase note (2026-02-28): `submodule/cloudlynet_ai_copilot:epic/copilot` was rebased to `main` with no net copilot API/schema delta.
    - Copilot env template guardrail: `backend/.env.example` retains placeholder secrets and targets shared infra hosts (`postgres`, `redis`, `minio`).
    - Browser CORS policy is gateway-owned and configured through gateway `CORS_ALLOW_ORIGINS` (all environments; localhost fallback only outside release mode); copilot backend CORS middleware is disabled by default in platform compose.
    - Integration rollout reference: `artifacts/copilot/plan.md`.
    - Frontend implementation checklist reference: `artifacts/upgrade_plans/frontend_agent.md` (microservice-segmented execution plan).
    - Trial signup frontend handoff reference: `artifacts/frontend/API_Contracts.md` §7.0.
  - **CloudlyNet Edge Agent** — `cloudlynet_edgeagent` (Go): outbound-only edge process for attaching TR-069 RadioDevices to CloudlyNet through the existing `/v1/agent/**` contract.
    - Runs on the edge device with no production inbound port.
    - Decodes the dashboard enrollment token into CloudlyNet base URL and `X-Edge-Key`.
    - Registers itself, retries registration on heartbeat until the platform is reachable, heartbeats NanoLink inventory (built from its in-agent ACS parameter cache), polls pending commands, posts telemetry and curated config snapshots, and acks command results. Configuration is a distinct 24-path managed-parameter read: the agent waits briefly for a fresh device read from its in-agent ACS, falls back to the last cached values, and never posts an empty map; SMO Sim merges partial/read-back deltas into the latest known snapshot. The `cwmp_id` remains opaque across the boundary; literal percent escapes are path-escaped again for snapshot URLs so they do not decode into a duplicate cloud device.
    - A configuration change is closed-loop: the operator submits a proposed value, the agent issues `SetParameterValues` (optionally sharpened by a connection request), then reads back via `GetParameterValues` until the requested value is observed or its verification timeout expires. The acknowledgement contains the actual read-back; the UI never promotes a proposed value to Current until that acknowledgement is `applied`.
    - Production enrollment tokens use `https://<platform-host>/` as the public base URL; deployment must route `<platform-host>/v1/**` to the gateway before the frontend catch-all, and gateway must proxy `/v1/agent/**` to SMO Sim without Cognito while preserving `X-Edge-Key`.
    - **Is the ACS** (replaces GenieACS): it hosts an in-agent TR-069/CWMP ACS on `:7547` — the exact port the NanoLink already dials — and answers the device's `Inform` and, critically, the `AutonomousTransferComplete` (ATC) RPC with the empty `AutonomousTransferCompleteResponse` (never a Fault). GenieACS never handled ATC, so its CWMP session faulted and died right after the Inform; answering it keeps the session alive to the read/write turn. Over that same listener the agent reads via `GetParameterValues`, writes via `SetParameterValues`, walks `GetParameterNames` once on first contact for authoritative writability, and reboots. An optional connection-request trigger (`:30005`) sharpens apply latency below the device's ~60 s inform cadence. The former `AutonomousTransferCompletePolicy=None` stopgap is obsolete now that the agent answers ATC directly; the path stays in the snapshot catalogue as a read-only managed parameter.
    - Watches the FTP drop for NanoLink `.tgz` logs and converts FM/TR69/FILE_TRANS lines into deterministic telemetry events.
    - Pushes tiered telemetry (§3.4 canonical keys): T1 liveness/UE counts (30 s), T2 RF/coverage (60 s), T3 PM counters + live hardware + `FaultMgmt` alarms (5 min). PM counter paths are pinned to the NanoLink `dmcli.new.conf` `Device.PeriodicStatistics.SampleSet.1.Parameter.{index}.X_8C1F64_CurrentValue` mapping.
    - Uses **embedded** SQLite on the edge device (`modernc.org/sqlite`, pure Go, `CGO_ENABLED=0`) for outbound telemetry retry and applied-command dedupe — a local file under `/var/lib/cloudlynet-agent`, not a separate service.
    - Production edge deployment (Ubuntu 22.04) is **native + systemd**, not Docker: `Makefile` + `scripts/install.sh` bootstrap Go ≥ 1.23 (official tarball), build from source, and install the `cloudlynet-edgeagent` service with secrets/endpoints in an `EnvironmentFile` (`/etc/cloudlynet-agent/agent.env`). The FTP log-drop dir is assumed already present; because the agent binds `:7547`, any prior on-box ACS (e.g. GenieACS + its Mongo/Node runtime) must be stopped and disabled first — a server-side-only cutover the NanoLink never notices.
    - Ships a separate Docker `testsuite` mock service for CloudlyNet Agent API validation plus a mock NanoLink CWMP device that dials the agent's in-agent ACS on `:7547` (Inform → ATC → GPV/SPV/GPN/Reboot). `TESTSUITE_MODE=acsftp` disables the CloudlyNet mock for live platform validation with the local mock ACS device/FTP only.
  - **Workers (Kafka consumers)** — Each Python service has a `worker` process for long‑running jobs (training/simulation).

### Shared infrastructure (pods for portability)

  - **Postgres** (SQL, RLS per tenant), **MongoDB** (doc), **Redis** (cache/rate limit), **Kafka (KRaft)** (events), **MinIO** in dev (S3 in prod).
    - All Python services normalise Postgres connection strings (supporting raw `postgres://` DSNs and credentials with reserved characters such as `@`), and the Gateway applies the same logic before running auto migrations, so operators no longer need to percent-encode passwords manually.
  - **Copilot runtime (shared infra model)**: `copilot-backend` and `copilot-mcp-server` consume shared `postgres`, `redis`, and `minio` services with dedicated copilot DBs/bucket.
  - **OTEL Collector**, **Prometheus**, **Grafana**, **Loki** (or EFK).

-----

## 3\. Multi‑Tenancy

### Tenancy model

  - Cognito issues ID tokens; claims include `custom:tenant_id` + `custom:role`.
  - **Explicit tenant scope** in API paths: `/v1/tenants/{tenant_id}/…`.
  - Gateway enforces membership/role (tenant_id match + role checks). Platform admin routes can optionally require a DB membership row (`REQUIRE_ADMIN_MEMBERSHIP=true`).

### Roles (Four-Tier System)

  - **cloudly_admin**: Platform-wide tenant management (create/delete orgs, manage platform admins). Stored in CloudlyIO org (special UUID).
  - **tenant_admin**: Manage users within tenant, full resource access (CRUD). Legacy: merged `owner` + `admin` roles.
  - **tenant_user**: Read/write resources, run inference. Cannot manage users. Legacy: renamed `viewer`.
  - **trial_user**: Read-only platform access + inference/compare execution + full copilot access. Cannot create, update, delete, or train any artifacts. Used in the shared trial tenant for self-service signups.

**Legacy roles** (`owner`, `admin`, `viewer`) auto-migrated to new system via migration 002.

**Trial tenant**: "netai trial" (UUID: `00000000-0000-0000-3029-000000000001`) is a pre-seeded shared org for trial prospects. Admin is Cloudly-internal (`tenant_admin`). Trial users self-signup via `POST /v1/trial/signup` (public, rate-limited). Write restrictions enforced at gateway proxy layer via `TrialWriteGuard` middleware — inference POSTs and all copilot endpoints are whitelisted. Lead capture data stored in `trial_signups` table (platform-scoped, no RLS). Seeded via migration 007.

**Implementation**: Cognito ID token carries `custom:tenant_id` and `custom:role`; gateway rejects non-ID tokens by requiring `token_use == "id"` and enforces tenant membership before routing.

-----

## 4\. Data & Storage

### Postgres (authoritative)

  - Tables: `tenants` (includes `auth_provider` defaulting to Cognito, optional `auth_config`, and `feature_flags` JSONB for per-module custom-feature gating), `tenant_memberships` (stores `email`, `user_name`, and Cognito `user_id`; `email` is unique across tenants; roles include `trial_user` for trial signups), `trial_signups` (platform-scoped lead capture for sales pipeline; no RLS), `baselines`, `ue_datasets`, `bdt_models`, `bdt_inference_runs`, `rapp_models`, `training_jobs`, `inference_runs` (captures inference request payload: `baseline_id`, `bdt_id`, `ue_dataset_id`, `tick`, `status`, `result`, `error`, timestamps), `nybsys_uploads` (tracks custom PM ingestion jobs: `upload_id`, `status`, derived `baseline_id`/`dataset_id`, `file_count`, `date_range`; tenant-scoped with RLS).
  - NanoLink control-plane tables (migration `009_nybsys_nanolink.sql`, all tenant-scoped with `FORCE` RLS): `edge_devices` (GO Agent hosts; `api_key_hash`, `status`, `last_seen_at`), `nanolink_devices` (managed cells behind an edge, keyed on `(tenant_id, cwmp_id)`; `health`, `optimize_mode`, RF/op state), `commands` (unified transport primitive — `configure|heal|optimise|query|reboot`; `payload`/`prev_values`, `origin`, lifecycle `status`, lease/`attempts`, `created_by`), `device_config_snapshots` (curated managed-param snapshots), `device_events` (telemetry events, deduped on `(tenant_id, dedup_key)`), `device_kpis` (tiered KPI samples, unique on `(tenant_id, device_id, ts, tier)`), `optimization_recommendations` (optimiser proposals → optionally materialised to a `commands` row).
  - Canonical Data Platform tables (migration `011_data_platform_canonical.sql`, owner data_sim, frozen HLD §4.3): `pm_measurements` (monthly RANGE partitions on `ts`; partitions created by `ensure_pm_partition()`, which also forces RLS on each partition), `fm_alarms`, `cm_records`, `ingest_jobs` (all tenant-scoped, FORCE RLS) and `vendor_dictionaries` (global vendor→canonical metric mapping, deliberately no RLS).
  - Network Digital Twin + closed-loop tables (migration `014_ndt_loop.sql`, owner bdt_engine; per-tenant policy seeding in `015_ndt_loop_policy.sql`): `ndt_evaluation_runs`, `ndt_kpi_snapshots`, `ndt_feature_builds`, `loop_policies` (one row per tenant, `mode off|approval|auto`), `loop_proposals` (raw `maveric.loop.proposal.v1` messages), `loop_actions` (decision audit rows with policy/evaluation snapshots and `prev_action_id` rollback linkage), `loop_feedback` (append-only observations). All tenant-scoped with FORCE RLS; `loop_actions`/`loop_feedback` additionally carry a maintenance policy (`app.maintenance='on'`) for the clock-driven watch sweep.
  - The E2/R1 facade tables (`e2_*`, `r1_*`) are **dropped** (migration `012_drop_e2_r1.sql`, frozen HLD D4); no `e2_*`/`r1_*` DDL remains in `schemas.sql`.
  - **RLS** on all tenant tables — **ENABLE + FORCE ROW LEVEL SECURITY is the rule, not an option**: rows require `tenant_id = current_setting('app.current_tenant', true)::uuid`, and FORCE ensures even the table owner cannot bypass the policy (the deployed role must additionally be non-superuser).
  - **OD1 pre-auth read**: `edge_devices` additionally carries a SELECT-only permissive policy that activates only when `app.current_tenant` is unset (`NULLIF(...,'')` maps the pooled-connection empty string to NULL), letting Edge-Key auth resolve edge→tenant by `api_key_hash` before the tenant GUC is set; once a tenant is set the standard `FOR ALL` policy enforces isolation. The deployed Postgres role **must be non-superuser** or RLS is silently bypassed.
  - Indices: `(tenant_id, …)` compound on lookups & time series on jobs.

### Copilot Data Domain (shared infra, separate DBs)

  - Copilot uses separate databases on shared Postgres plus schema bundle: `artifacts/copilot/copilot_schemas.sql`.
  - Conversation tables are tenant- and user-scoped (`tenant_id`, `user_id`) and can be protected with conversation-table RLS policies from `artifacts/db/init_copilot_rls.sql`, using PostgreSQL session settings `app.current_tenant_id` and `app.current_user_id`.
  - Schemas: `conversation` (sessions/messages/versioning) and `knowledge` (RAG sources/documents/chunks with `vector(384)` embeddings).
  - Shared Postgres must expose `pgvector`; local compose uses `pgvector/pgvector:pg15`, and existing cluster DBs must have the extension installed or enabled before copilot rollout.
  - No shared tables or migrations with the primary platform schema; isolation is by dedicated databases/credentials.
  - Local compose intentionally keeps copilot schema/RLS application outside `docker compose up`; production rollout follows the same split model (`artifacts/copilot/copilot_prod.md`).

### MongoDB

  - Collections: `dataset_profiles`, `inference_summaries`, optional `forms`.
  - Every document embeds `tenant_id`. Index starts with `{tenant_id:1, …}`.

### Redis

  - Cache keys prefixed with `cache:{tenant_id}:…` and rate limits with `ratelimit:{tenant_id}:{route}:{slot}`.

### Object Storage

  - **Prod:** AWS S3; **Dev:** MinIO.
  - Prefixes per tenant (note: `dataset_id` is supplied by the caller when registering real UE datasets):
    - Objects land under `s3://{bucket}/{prefix?}{tenant_id}/…`; with the default `S3_PREFIX=tenants` that becomes `s3://maveric/tenants/{tenant_id}/…`.
    - Baselines: `…/baselines/{baseline_id}/topology.csv`, `…/ue_training_data.csv`, `…/config.csv`
    - UE datasets: `…/ue/{dataset_id}/synthetic_dataset.csv`
    - BDT models: `…/bdt/{bdt_id}/{bdt_id}.pickle`
    - rApp artifacts: `…/models/rapps/{rapp_id}/{rapp_model_id}.zip`
    - rApp inference outputs: `…/rapps/{rapp_id}/{rapp_model_id}/inference/{run_id}/plot.json`
    - PM ingestion raw data: `…/pm-data-ingestion/{upload_id}/raw/{date}.csv`
    - PM ingestion hourly aggregate: `…/pm-data-ingestion/{upload_id}/pm_hourly.csv` (debug/audit)
    - Derived baselines/datasets use existing prefixes with upload-derived IDs (e.g., `…/baselines/{upload_id}-topology/topology.csv`)
    - Local caches inside the containers for fast reuse:
      - BDT worker → `/app/var/models/{tenant_id}/bdt/{bdt_id}.pickle`
      - rApp worker → `/app/var/models/{tenant_id}/rapps/{rapp_id}/{rapp_model_id}.zip`
      - rApp worker hydrates `/app/var/models/{tenant_id}/bdt/{bdt_id}.pickle` from S3 automatically when the shared volume is missing the artifact.
      - rApp inference hydrates `/app/var/models/{tenant_id}/rapps/{rapp_id}/{rapp_model_id}.zip` from the recorded artifact URIs (or derived S3 key) whenever a pod cannot see the shared ZIP, ensuring fail-safe recovery.
      - Utils mobility generation mirrors the traffic-load path: requests are handled inline and persisted under the same `{tenant_id}/ue/{dataset_id}/synthetic_dataset.csv` prefix, so no Kafka/idempotency bookkeeping is required.
  - Ops note: **`artifacts/migration/` is the migration source of truth** (numbered files `001`–`016` + `cognito.sql`, with an execution index in `artifacts/migration/README.md`). Existing clusters apply the numbered migrations in order; fresh installs get the same end state from `artifacts/design/schemas.sql`, which inlines the landed migrations. When this document (or any doc) and a landed migration disagree, the migration wins. Inline ad-hoc ALTER TABLE patches are no longer documented here.
  - SMO Sim depends on `boto3` for S3 lifecycle (baseline & UE dataset deletions). The package ships with the service; wire AWS/MinIO credentials via env vars so DELETE flows do not fail with HTTP 500.
  - Gateway ships the consolidated `db/migrations/schemas.sql` mirroring `artifacts/design/schemas.sql`; operators must apply it (or an equivalent migration pack) ahead of deploys. Startup now skips GORM auto-migrations and only runs idempotent guard clauses (extension/enum checks, trigger/index refresh) when the tables already exist, so manual schema management stays authoritative while RLS policies remain enforced.
-----

## 5\. Message Bus

  - **Kafka topics** (provisioned declaratively by the kafka chart topics-job and local compose `init-topics.sh`):

| Topic | Producer → Consumer | Purpose |
|---|---|---|
| `maveric.bdt.train.v1` | bdt_engine API → bdt-worker | BDT training jobs (unchanged) |
| `maveric.rapp.train.v1` | rapp API → rapp-worker | rApp training jobs (unchanged) |
| `maveric.ingest.pm.v1` | any producer → data_sim in-container consumer | Data Platform ingestion: `kind=job` ingest jobs (durable replacement for the thread pool) and `kind=records` inline record batches from streaming sources (frozen HLD Appendix A.5) |
| `maveric.loop.proposal.v1` | rapp → bdt_engine (NDT) | Recommendation proposals for the decision hub (Appendix A.1; also mirrored by `POST /ndt/loop/proposals`) |
| `maveric.loop.action.v1` | bdt_engine (NDT) → executors (smo_sim actuators, rapp RIC layer) | Approved actions `{action_id, tenant_id, adapter, target, payload, policy_ref, expires_at}` (Appendix A.2) |
| `maveric.loop.feedback.v1` | executors → bdt_engine (NDT) | Apply results, KPI windows, guardrail breaches, rollback acks (Appendix A.3) |

  - Inference runs are handled inside the rApp engine itself (thread pool + Postgres) so we avoid introducing another Kafka topic while training workers are busy.
  - Workers persist state transitions to Postgres and consume the versioned training topics directly; local compose and Helm now create those topics declaratively.
  - Current platform Kafka rollout status is maintained in `kafka_plan.md`. The in-repo charts now provide initial persistent Kafka/ZooKeeper deployment plus declarative training-topic creation, and local compose now preserves broker state and bootstraps the training topics. In the current production track, Kafka and ZooKeeper reuse the shared `efs-pvc` claim already mounted by rApp/BDT, with isolated subpaths for broker and ZooKeeper state; init containers now mark those shared directories writable before Confluent's `uid=1000` processes start, and worker timeout env values are kept as quoted decimal strings so Helm does not emit scientific notation that the current worker images cannot parse. Kafka is still a single-broker initial rollout, not the final HA topology.

-----

## 6\. Security

  - **AuthN**: Cognito ID token (JWKS verify in Gateway; aud/iss validated; `token_use` must be `id`).
  - **AuthZ**: Gateway checks membership & role for `{tenant_id}`; services rely on RLS & also verify path tenant vs token tenant (defense in depth).
  - **Internal service auth**: Gateway-to-service proxy calls for BDT, rApp, SMO Sim, and Data Sim also carry a service-specific `X-API-Key`; deployment values must keep the gateway keys aligned with each downstream service `API_KEY`.
  - **User lifecycle**: Gateway provisions users via Cognito Admin APIs; invite emails send temporary passwords on creation.
  - **Transport**: TLS 1.2+ externally; mTLS intra‑cluster (or service mesh).
  - **At rest**: EBS encryption; S3 SSE‑KMS; Mongo & Redis with encrypted volumes.
  - **Secrets**: AWS Secrets Manager + External Secrets Operator.
  - **Rate limiting**: per tenant & per user at Gateway (Redis counters).
  - **Audit**: JSON audit logs: `{ts, request_id, trace_id, tenant_id, user_id, action, resource, before?, after?}`.

-----

## 7\. Observability

  - **OpenTelemetry**: traces across Gateway → services → workers. Attributes always include `tenant_id`, `request_id`.
  - **Prometheus metrics** (examples):
    API: `http_requests_total{service,route,method,status}`, latency histograms.
    Domain: `bdt_training_duration_seconds`, `rapp_training_duration_seconds`, `datasets_registered_total`.
  - **Logs**: structured JSON (python‑json‑logger / zerolog). Tenant‑labeled. All Python services (BDT Engine, rApp Engine, SMO Sim, Data Sim) run request/response logging middleware that issues `X-Request-ID` on every response, injects `tenant_id`/`request_id` into log records via contextvars, and writes request lifecycle entries to STDOUT **and** MongoDB `application_logs` (TTL per level) when configured. HTTP/validation/unhandled failures now flow through `log_error_to_mongodb()` into `error_logs` with `service_name` scoping and request context for correlation.
    - Log introspection endpoints: Data Sim → `/v1/tenants/{tenant_id}/utils/logs/errors|.../resolve|/logs/stats`, SMO Sim → `/v1/tenants/{tenant_id}/baselines/logs/errors|...`, rApp → `/v1/tenants/{tenant_id}/rapps/logs/errors|...`, BDT → `/v1/tenants/{tenant_id}/bdt/logs/errors|...`, plus `/v1/logs/health` for Mongo TTL/index readiness. When Mongo is absent the services continue with STDOUT-only logging. All services surface `/health` (enveloped) for container liveness/readiness checks.

-----

## 8\. Deployment (AWS)

  - **EKS**:
      - **Deployments**: gateway, frontend, *engines*, SMO Sim, Data Sim, Copilot backend, Copilot MCP, OTEL, Prom, Grafana, Loki.
      - **StatefulSets**: Postgres, Mongo, Kafka, Redis (or managed alternatives later).
      - **HPAs** for stateless services; **KEDA** for Kafka lag based scaling (workers).
      - Copilot deploys through a unified Helm release so `copilot-backend` and `copilot-mcp-server` stay version-aligned while reusing the existing cluster Postgres, Redis, and object-storage services.
      - Gateway charts now use a Postgres-ready init container so the API pod does not start until the shared database is accepting connections, and pgAdmin charts now declaratively import the platform Postgres server entry on every launch.
  - **Ingress**: ALB Ingress Controller (TLS); optional AWS WAF.
  - **Images**: ECR.
  - **CI/CD**: build → scan → helm deploy. Run contract tests vs `openapi.yaml` in pipeline.
  - **Cluster auth guardrail**: staging/prod gateway values must set `DEV_BYPASS_JWT=false`; JWT bypass is local-only.

-----

## 9\. Core Data Flows (ASCII)

### 9.1 Sign-in, tenant scoping, and request guardrails

```
User ──login──> Cognito
Cognito ──ID token──> Browser
Browser ──HTTPS /v1/tenants/{tenant_id}/... + Authorization: Bearer JWT──> Gateway
Gateway:
  - Verify JWT w/ Cognito JWKS
  - Authorize: user ∈ tenant_id? role ok?
  - Add X-Request-ID + trace ctx
  - Proceed (HTTP/gRPC to services or produce to Kafka)
```

### 9.2 Upload a real baseline (topology + training + config)

```
FE ──(1) get presigned URL(s) for topology/training/config──> Gateway ──> S3
FE ──(2) PUT CSVs to S3────────> S3
FE ──(3) POST /tenants/{t}/baselines (URLs)──> Gateway
Gateway ──validate & write──> Postgres (Baselines, tenant_id=t)
Gateway ──(optional: ping)──> SMO Sim (validate/parse async)
Gateway ──200/201───────────> FE (BaselineSummary)
```

### 9.3 Generate a synthetic dataset (Utils → Data Sim)

```
FE ──POST /tenants/{t}/utils/traffic-load/generate──> Gateway
Gateway ──HTTP──> Data Sim (inline)
Data Sim:
  - Resolve baseline topology from Postgres/S3
  - Generate CSV via 3GPP-compliant golden generators (golden topology + UE generators with proper path loss, antenna patterns, shadow fading)
  - Upload to S3 (tenant prefix)
  - If callers supplied `dataset_id`, ensure it is unique for the tenant and reuse it; otherwise generate a UUID
  - Create UEDataset row in Postgres
  - Return UEDataset
Gateway ──201 (UEDataset)──> FE
```

### 9.4 BDT training

```
FE ──POST /tenants/{t}/bdt/train (+Idempotency-Key)──> Gateway
Gateway:
  - Create BDT model stub in Postgres: status=queued, caller-supplied `bdt_id` (required per request)
  - Write idempotency record in Redis (keyed by header)
  - Produce Kafka: training_cmd {tenant_id, job_id=bdt_id, training_job_id, baseline_id, overrides}
BDT Engine (consumer, versioned training topic):
  - Resolve inputs (absolute URLs, S3 ARNs, or relative S3 keys) from Postgres baselines table (fall back to payload overrides), auto-prepending the configured tenant prefix when callers submit bare keys
  - Set both model and training job to `training` at worker start; skip redelivered messages that target models already in `ready|failed`
  - Pause/resume partitions around long-running work and commit exact Kafka offsets (`offset + 1`) after the matching message completes
  - Train, log metrics (OTel), write artifacts locally and to S3 (`…/bdt/{bdt_id}/{bdt_id}.pickle`)
  - Update Postgres: status=training→ready/failed, metrics
  - Publish Kafka: training_evt {bdt_id, status}
FE polls:
  - GET /tenants/{t}/bdt or /bdt/models/{bdt_id} until ready
```

### 9.4.1 BDT inference (async, pollable)

```
FE ──POST /tenants/{t}/bdt/models/{bdt_id}/infer {ue_dataset_id, tick, baseline_id?}──> Gateway
Gateway ──HTTP──> BDT Engine
BDT Engine:
  - Validate model exists and is `ready`
  - Resolve baseline_id (payload override or model baseline)
  - Insert `bdt_inference_runs` row (status=queued; stores request, dataset, tick)
  - Submit background thread job and return 202 with Location `/infer/{run_id}`
Gateway ──202 + Location──> FE

FE polls GET /tenants/{t}/bdt/models/{bdt_id}/infer/{run_id}
BDT Engine:
  - Return run status (`queued|running|completed|failed`)
  - When completed, include D3-ready plot groups + metrics + optimization_metric
```

### 9.5 rApp training (MRO/CCO/ES/LB)

```
FE ──POST /tenants/{t}/rapps/{rapp_id}/train──> Gateway
Gateway:
  - Validate bdt_id, dataset_id, baseline_id belong to tenant t
  - Create rApp model stub (Postgres) using the caller-supplied `rapp_model_id`
    (persisting `dataset_id` alongside the baseline reference)
  - Enqueue Kafka: train_cmd (tenant, rapp_id, rapp_model_id, baseline/dataset/bdt ids, params)
rApp Engine (consumer):
  - Resolve dataset + baseline metadata from Postgres (uses canonical
    `url_to_smo_ue_data_csv` / `url_to_config_csv` when present)
  - Load BDT/model, dataset from S3 (or local dev fixtures); if the shared volume lacks the requested BDT pickle the worker downloads it from the recorded artifact URI (S3/HTTP) before training proceeds
  - Load legacy BDT pickle files that reference the former `app.radp.*`
    package namespace via a compatibility unpickler
  - Train via RADP managers, persist artifacts (local + optional S3) under `tenants/{tenant_id}/rapps/{rapp_id}/{rapp_model_id}`
  - Update Postgres: status transitions + metrics/artifact URIs, emit train_evt
  - RADP helpers are vendored as a first-class Python package (`radplib`). The
    application still exposes the historical `app.radplib` path for backward
    compatibility, and registers the legacy `radp.*` alias expected by vendor
    modules, but new code should import from `radplib.*` directly.
FE ──GET /tenants/{t}/rapps/{rapp_id}/models or /models/{id} to track
```

### 9.6 Inference (+ D3 plot + text metrics + single KPI)

```
FE ──POST /tenants/{t}/rapps/{r}/models/{id}/infer {baseline_id, bdt_id, ue_dataset_id, tick}──> Gateway
Gateway ──HTTP──> rApp Engine
rApp Engine:
  - Persist row in `inference_runs` (status=queued; captures baseline, BDT, dataset, tick)
  - Dispatch background thread (mock payload for now, RadP later)
  - Return 202 with `run_id` + Location header `/infer/{run_id}`
Gateway ──202 + Location──> FE
FE polls GET /tenants/{t}/rapps/{r}/models/{id}/infer/{run_id}
Gateway ──HTTP──> rApp Engine
rApp Engine:
  - Reads run, returns status/metadata
  - When completed: include plot/text/metric payload in `result` field
FE renders plot via D3 once status=completed
```

### 9.7 Caching, idempotency, rate limits

```
Redis

Idempotency: `/bdt/train` scopes the caller's `Idempotency-Key` to the supplied `bdt_id`; duplicate submissions with the same key and `bdt_id` return the original queued model. Reusing the key with a different `bdt_id` queues a fresh job.

Cache: hot reads (e.g., /baselines, model lists) keyed by tenant_id. Invalidate on write.

Short-lived job status: if you want near-real-time job dashboards without hammering Postgres.

Rate limiting: token bucket at Gateway keyed by (tenant_id, user_id, route) to isolate tenants.
```

### 9.8 Multi-tenancy enforcement

```
Gateway extracts tenant_id from the path and verifies `custom:tenant_id` matches; admin endpoints can optionally confirm a matching `tenant_memberships` row for (`tenant_id`, `email` or `cognito_sub`).

Postgres: every tenant table carries tenant_id and is protected by ENABLE + FORCE ROW LEVEL SECURITY with the tenant policy — RLS is mandatory, not optional (see §4). Services set app.current_tenant per request; queries additionally filter by tenant_id as defense in depth.

S3: put content under s3://bucket/tenants/{tenant_id}/....

Kafka: use round-robin partitioning for training commands unless strict tenant ordering is explicitly required. Tenant-keying by default would serialize one tenant's jobs onto one partition and reduce concurrency.

Engines: re-validate tenant_id on every DB/S3 read.
```

Track 1 (gateway + Cognito + schema) specifics:
- Platform admin: `/admin/tenants/**`, `/admin/platform-admins` provision tenants/admins; tenant admin: `/tenants/{tenant_id}/users/**` handles user CRUD.
- Field naming is explicit (`tenant_name`, `tenant_status`, `admin_email`, `admin_name`, `user_email`, `user_name`, `user_role`, `user_status`); DTOs and OpenAPI match.
- Dev bypass can emulate tenant roles via `DEV_TENANT_ROLE` (`tenant_admin`/`tenant_user`) while `/v1/admin/**` stays Cloudly admin only.

### 9.9 Observability & ops

```
Every request/worker span is instrumented with OpenTelemetry; X-Request-ID and trace context propagate across Gateway → Engines → DB/Kafka.

Metrics: RPS, p95, queue lag, train duration, inference duration, S3 egress, per-tenant quotas.

Logs: structured (JSON), tenant_id always included (but never PII).

Alerts: failure rates, Kafka consumer lag, Redis memory pressure, disk IOPS on Postgres, pod restarts.
```

### 9.10 Copilot gateway-routed operations

```
Frontend ──POST /v1/tenants/{t}/copilot/agents/query──> Gateway
Gateway:
  - Verify Cognito JWT + tenant membership + role
  - Forward trusted identity context (tenant/user/role, request ID, trace)
  - Proxy `/v1/tenants/{tenant_id}/copilot/**` unchanged
  - Route directly to Copilot backend native tenant path (`/v1/tenants/{tenant_id}/copilot/agents/query`)
Copilot:
  - Generate response (chat-only) OR propose executable operation
  - For mutating actions, require explicit user confirmation
  - Invoke action executor/MCP adapter with allowlisted gateway API targets only
Action executor ──HTTP via Gateway──> BDT / rApp / SMO / Data Sim
Gateway:
  - Re-apply RBAC + rate limits + audit trail
  - Proxy to target microservice
Copilot:
  - Persist operation result into session context + action audit log
Frontend:
  - Displays status and poll links for async jobs (train/infer/generate)
```

### 9.11 Custom PM data ingestion (nybsys — served by data_sim since re-architecture E1)

```
Client ──(1) upload raw PM CSVs to S3──> S3 (pm-data-ingestion/{upload_id}/raw/)
Client ──(2) POST /tenants/{t}/custom/nybsys/uploads {upload_id, raw_s3_urls}──> Gateway
Gateway ──HTTP (custom/nybsys/uploads* → DATA; device/edge ops stay SMO)──> Data Sim
Data Sim (Data Platform):
  - Feature guard: check tenants.feature_flags["nybsys"] == true (else 403)
  - Validate S3 URLs (tenant-scoped prefix check)
  - Insert nybsys_uploads row (status=uploading)
  - Queue the ingest job on maveric.ingest.pm.v1 (durable; consumer runs in the API container)
  - Return 202 Accepted
Gateway ──202──> Client

Background (ingest consumer):
  - NanoLink adapter: parse/dedupe/aggregate raw CSVs → canonical pm_measurements rows + raw S3 (store-only, no synthesis)
  - Semi-synthetic enrichment delegated to bdt_engine: POST /ndt/feature-builds (topology synthesis →
    config → Approach C UE placement → TR 38.901 RSRP labeling; rng_seed persisted; artifacts labeled
    semi_synthetic=true in baselines.stats)
  - Feature builder uploads processed CSVs to S3 (baselines/{upload_id}-topology/, ue/{upload_id}-dataset/)
    and registers Baseline + UEDataset rows in Postgres (existing key conventions)
  - Update nybsys_uploads: status=completed, baseline_id, dataset_id

Client polls GET /tenants/{t}/custom/nybsys/uploads/{upload_id} until completed (contract unchanged)
  - Completed response includes derived baseline_id + dataset_id for downstream BDT/rApp use
```

-----

### 9.12 NanoLink edge↔cloud control plane (GO Agent)

```
Enrollment (operator, Cognito):
  Operator ──POST /custom/nybsys/edge-devices──> SMO Sim   (creates edge_devices row, status=pending)
  Operator ──POST .../edge-devices/{edge_id}:regenerate-key──> SMO Sim mints a one-time Edge-Key
  (secret returned once; only sha256(secret)=api_key_hash is stored)

Agent loop (edge host, Edge-Key — proxied via Gateway /v1/agent/**, no Cognito):
  Agent ──POST /agent/register {edge identity}──> Gateway ──(inject SMO_API_KEY)──> SMO Sim
    - auth_edge resolves X-Edge-Key -> tenant via edge_devices (OD1 pre-auth SELECT, tenant GUC unset)
    - then set app.current_tenant; all later work is RLS-scoped
  Agent ──POST /agent/heartbeat──> SMO Sim
    - auto-onboards/updates nanolink_devices (keyed on cwmp_id), refreshes status/last_seen_at
  Agent ──POST /agent/telemetry {tiered KPIs, events}──> SMO Sim
    - device_kpis (tier 1|2|3, unique on ts+tier), device_events (dedup on dedup_key), alarms → health rollup
  Agent ──POST /agent/devices/{cwmp_id}/config-snapshot──> SMO Sim  (device_config_snapshots)
  Agent ──POST /agent/poll {edge_id}──> SMO Sim
    - claim-on-fetch: SELECT ... FOR UPDATE SKIP LOCKED on commands WHERE edge_id,status='pending'
    - returns claimed commands as status=dispatched (lease 60s / 5 attempts, OD3)
  Agent ──POST /agent/commands/{command_id}/ack {result|error}──> SMO Sim
    - ack guarded on status='dispatched' → applied|failed; on failure + rollback_on_fail, auto-emit a
      rollback command from prev_values; lease sweep re-queues expired dispatched commands

Operator plane (Cognito, /custom/nybsys/**):
  - edge/device CRUD, GET devices/{id}/config|events|kpis|health, POST devices/{id}/commands (origin=manual)
  - PUT devices/{id}/optimize-mode (off|approval|auto) gates the optimiser
  - recommendations approve/reject; approve materialises an optimise command

Self-optimiser P1 (on new telemetry):
  - EWMA anomaly (z computed before update) + guard-railed energy/coverage rules
  - emits optimization_recommendations; optimize_mode=auto auto-materialises a command, =approval waits
    for operator approve, =off no-ops; guardrail breach triggers rollback. healer.on_new_events = no-op hook.
```

-----

## 10\. SLOs

  - **GET** p95 ≤ 200 ms.
  - **Job submit** p95 ≤ 400 ms.
  - **Inline inference** p95 ≤ 500 ms for standard payloads.
  - Error rate ≤ 1% 5‑min windows.

-----

## 11\. Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Large artifacts | slow responses | presigned URLs, downsample plots for UI |
| Cross‑tenant leakage | severe | Gateway RBAC + Postgres RLS + contract tests |
| Outages (Cognito) | auth failures | cache JWKS; short‑lived sessions; retries |
| Queue buildup | latency | KEDA autoscale; per‑tenant concurrency guardrails |

-----

## 12\. RIC integration layer (successor to the E2/R1 REST facades)

The E2/R1 REST/JSON facades SMO Sim used to serve were deleted per frozen re-architecture
decision D4 (epic E4): the routes were never gateway-routed, the measurement tables had no
writer, and R1 subscriptions never notified. Their design docs are archived at
[`artifacts/legacy/oran/`](../legacy/oran/README.md) and must not be cited as capability
evidence.

The design of record for RAN-intelligence integration is now
[`artifacts/ric/`](../ric/README.md): the rApp's `app/ric/` ports and adapters
(`RanControlPort` / `RanDataPort`, `a1_policy` implemented, `nearrt_xapp` reserved), the
NONRTRIC A1-PMS connector, the `ric-lab` compose profile (O-RAN SC NONRTRIC A1 Policy
Management Service 2.11.0 plus two A1 simulators, lab only), the OCUDU integration
surfaces, and the R1-shaped packaging facade.

CloudlyNet integrates a RIC over REST/JSON; it is not a RIC and does not implement E2
termination itself. No O-RAN conformance or certification is claimed (see
[`artifacts/marketing/claims-guardrails.md`](../marketing/claims-guardrails.md)).
