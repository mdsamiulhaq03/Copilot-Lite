# Route and Endpoint Matrix

## 1. URL Conventions

- API base URL is configured via `NEXT_PUBLIC_API_BASEURL` (default expected: `/v1` gateway).
- Tenant-scoped APIs should follow: `/v1/tenants/{tenant_id}/...`.
- Browser clients must not call internal backend-only routes such as `/api/v1/**`.
- Frontend currently derives tenant ID from auth/store, not from URL path segment.
- Customer-facing navigation labels are documented in `artifacts/ui-label-mapping.md`; technical routes remain the source of truth for implementation and deep-links.
- Sidebar IA is **sectioned** (`SIDEBAR_DATA: SidebarSection[]` in `lib/app.config.ts`): `Dashboard` (unlabeled section); **Simulate · Network Digital Twin** — `Ingest` (`/ingest`, navigable parent with children `Topology & Configuration` `/baseline`, `Training Data` `/smo`, `PM Upload` `/custom-pm-ingestion`, `Data Platform` `/data`), `Twin Library` (`/bdt`, `matchPrefixes: ["/infer"]`), `Evaluate` (`/ndt/evaluate`), `Optimization Models` (`/rapp` — no `Compare Models` child anymore: compare is embedded at `/rapp?tab=models&view=compare` since the 2026-08-06 IA realignment, frontend `fd40b1e`), `KPI History` (`/ndt/kpis`); **Actuate · Actuator Adapters** — `Adapters` (`/actuators`, `matchPrefixes: ["/devices"]` so device detail routes keep the item lit), `Policy & Guardrails` (`/policy`), `Closed Loop` (`/closed-loop`); `Administration` and `Logging & Monitoring` unchanged. `Copilot` stays a top-bar entry, never in the side nav.
- The loop flow strip (`components/widgets/LoopFlowStrip.tsx`) is mounted **once in the dashboard shell** (`components/dashboard-shell.tsx`): route-aware and clickable on every dashboard page, `full` variant on `/`, `compact` elsewhere (frontend `dff7e05`).
- Dev auth bypass: `NEXT_PUBLIC_AUTH_MODE=bypass` (`lib/auth/bypass.ts`) short-circuits login into a synthetic `tenant_admin` session (`NEXT_PUBLIC_DEV_TENANT_ID`, default `00000000-0000-0000-3029-000000000001`) and `ApiClient` sends no `Authorization` header; pairs with the gateway's `DEV_BYPASS_JWT=true`. Local e2e only.

## 2. Frontend Page Routes

| Route                       | Access                 | Visible Label / Entry                       | Primary Component(s)                    | Notes                                                                                            |
| --------------------------- | ---------------------- | ------------------------------------------- | --------------------------------------- | ------------------------------------------------------------------------------------------------ |
| `/select-tenant`            | Public                 | Tenant entry                                | `TenantForm`                            | Tenant lookup then hosted Cognito login, persisting validated organization display name          |
| `/login`                    | Public                 | Login compatibility route                   | Proxies to `select-tenant`              | Compatibility route                                                                              |
| `/trial`                    | Public                 | Trial signup / returning-user sign in       | `TrialSignupForm`                       | Self-service trial signup, returning-user sign-in CTA, success credentials state, and hosted Cognito bootstrap |
| `/signup`                   | Public                 | Signup compatibility route                  | Proxies to `trial`                      | Compatibility route                                                                              |
| `/forgot-password`          | Public                 | Forgot password                             | `ForgotPasswordForm`                    | Redirects to Cognito hosted reset                                                                |
| `/reset-password`           | Public                 | Reset password                              | `ResetPasswordForm`                     | Redirects to Cognito hosted reset                                                                |
| `/auth/callback`            | Public callback        | Auth callback                               | `AuthCallbackClient`                    | Exchanges code, restores tenant display name, and stores tokens                                  |
| `/auth/auth-code-error`     | Public                 | Auth fallback                               | Error card                              | Auth fallback UX                                                                                 |
| `/`                         | Authenticated          | `Operations Overview`                       | Dashboard widgets                       | Summary + quick train/table widgets                                                              |
| `/ingest`                   | Authenticated          | `Intelligence -> Ingest`                    | `PipelineRail`, `CategoryCard`          | Ingest landing: PM/CM/FM category cards + training-data band; counts via `listNybsysUploads` (LEGACY count source, EPIC-11 S1), `listBaselines`, `listUeDatasets` (per-card degrade, FM has no source) |
| `/baseline`                 | Authenticated          | `Ingest -> Topology & Configuration`        | `AddBaselineModal`, `BaselineDataTable` | Technical baseline route preserved                                                               |
| `/smo`                      | Authenticated          | `Ingest -> Training Data`                   | `AddSMOModal`, `SMODataTable`           | Technical SMO dataset route preserved                                                            |
| `/custom-pm-ingestion`      | Authenticated          | `Ingest -> PM Upload`                       | `PmUploadPage`                          | Vendor-neutral PM CSV upload (frontend `dff7e05`): posts `POST /ingest/uploads`, polls `GET /ingest/jobs/{id}`; hosts the `IngestAdaptersCard` (moved here from `/data`); history table still reads `listNybsysUploads` (LEGACY, EPIC-11 S1). The old `NybsysIngestionPage` conversion UI is unmounted LEGACY code |
| `/data`                     | Authenticated          | `Ingest -> Data Platform`                   | Data browse page                        | Canonical PM/FM/CM browse via `GET /data/{kind}`: newest-first, time-window picker, offset Load more (cursor adoption pending, EPIC-11 S5)                   |
| `/bdt`                      | Authenticated          | `Intelligence -> Network Digital Twin`      | `TrainBDTModal`, `BDTDataTable`         | Technical BDT route preserved                                                                    |
| `/bdt/models/[bdtId]/infer` | Authenticated          | `Network Digital Twin Simulation`           | `BdtInferenceDashboard`                 | LEGACY (EPIC-11 S2, frontend `d55ec13`): deprecation banner links to `/ndt/evaluate?bdt_id=...`; removal gated on the spatial-scatter port into Evaluate                                                                |
| `/ndt/evaluate`             | Authenticated          | `Simulate -> Evaluate`                      | `EvaluateForm`, `EvaluateResult`, `PerTickKpiTable` | Twin evaluate (tick 200 / day 202+poll); honors `?bdt_id=` so the Twin Library row action lands with that twin pre-selected (frontend `d55ec13`)                                                                |
| `/ndt/kpis`                 | Authenticated          | `Simulate -> KPI History`                   | `KpiHistoryExplorer`, `KpiHistoryChart` | KPI history rebuilt (frontend `fd40b1e`): gate baseline->candidate pairs vs evaluate envelope, breach marking vs live loop policy, time windows + Load older via `GET /ndt/kpis` `from_ts`/`to_ts`/`offset`/`bdt_id`; `KpiTrendChart` kept as LEGACY                                                                |
| `/rapp`                     | Authenticated          | `Simulate -> Optimization Models`           | `TrainRappModal`, `RAPPDataTable`, `InferenceCompare`, `RicConnectPanel` | Two-path tabs (frontend `fd40b1e`): `?tab=models\|ric` and, under `models`, `?view=library\|compare` (URL-synced). `Compare Models` is the embedded compare view; `Connect to RIC` renders `RicConnectPanel` — still no RIC backend call |
| `/rapp/mro/[rappModelId]`   | Authenticated          | `Mobility Optimization Detail / Simulation` | `MroModelDetailPage`                    | MRO model detail, status polling, and async evaluation                                           |
| `/infer`                    | Authenticated          | `Run Model`                                 | `DayInferenceDashboard`                 | ES/LB/CCO day-scope inference and polling; reached contextually from model actions; sidebar lights `Network Digital Twin` via `matchPrefixes` |
| `/compare`                  | Authenticated          | (redirect)                                  | Redirect page                           | LEGACY (EPIC-11 S8): server `redirect()` to `/rapp?tab=models&view=compare` (frontend `fd40b1e`); compare UI (`InferenceCompare`) now lives inside `/rapp`                          |
| `/actuators`                | Authenticated          | `Actuate -> Adapters`                       | `AdapterRegistry`                       | `Actuator Adapters` landing is now the adapter grid alone (frontend `887a396`): the TR-069 (CWMP) tile links through to `/actuators/tr069`; every other tile opens an adapter info dialog (rung/capabilities/health) — no backend call |
| `/actuators/tr069`          | Authenticated          | `TR-069 (CWMP)`                             | `EdgeDevicesPanel`, `DevicesTable`, `AddEdgeModal` | Dedicated TR-069 estate page (frontend `887a396`): edge/device flow relocated from `/actuators` (`listEdges` + `listDevices`, 15s poll, one-time enrollment-token reveal); backend `403` renders the feature-disabled card |
| `/policy`                   | Authenticated          | `Actuate -> Policy & Guardrails`            | `LoopPolicyEditor`                      | Single tenant-wide loop mode control + guardrail editor (frontend `887a396`); the `Device policies` section (`PolicyDeviceTable`) is unmounted LEGACY (EPIC-11 S3); device Optimize tab shows the tenant mode read-only |
| `/devices`                  | Authenticated          | (redirect)                                  | Redirect page                           | Landing relocated to `/actuators/tr069` (frontend `887a396`); route kept as a redirect so old bookmarks work; `lib/breadcrumbs.ts` parents `/devices/*` under `TR-069 (CWMP)`                |
| `/devices/edge/[edgeId]`    | Authenticated          | `Edge Device`                               | Edge detail page                        | Status, regenerate-key (token reveal), cascade delete with confirm; back-link `Back to TR-069 (CWMP)` -> `/actuators/tr069` |
| `/devices/[deviceId]`       | Authenticated          | `Device`                                    | `DeviceConfigPanel`, `DeviceMonitoringPanel`, `DeviceOptimisePanel` | Tabbed shell: Config / Monitoring / Optimize; `?tab=` (`config \| monitoring \| optimise`) selects the initial tab; back-link -> `/actuators/tr069` |
| `/copilot`                  | Authenticated + tenant | `Copilot`                                   | `CopilotShell`                          | Session-first copilot panel, entered from top bar rather than side nav                           |
| `/error-logs`               | Authenticated          | `Error Logs`                                | `ErrorLogsDataTable`                    | Module tabs + resolve; side-nav visibility limited to `cloudly_admin`                            |
| `/organizations`            | `cloudly_admin`        | `Organization Management`                   | `OrganizationDataTable`                 | Role-guarded                                                                                     |
| `/organizations`            | `cloudly_admin`        | `Trial Pipeline`                            | `TrialSignupsTable`                     | Same page also lists paginated trial leads from `/admin/trial-signups`                           |
| `/users`                    | `tenant_admin`         | `User Management`                           | `UserDataTable`                         | Role-guarded                                                                                     |
| `/account/profile`          | Authenticated          | Account profile                             | `PersonalInfoCard`                      | Read-only profile                                                                                |
| `/account/settings`         | Authenticated          | Account settings                            | `PasswordChangeCard`                    | Hosted reset handoff                                                                             |
| `/rapp/inference/[id]`      | Authenticated          | Legacy redirect to `Run Model`              | Redirect page                           | Redirects to `/infer?model_id=...&day=0`                                                         |
| `/opex-estimate`            | Authenticated          | Placeholder                                 | Placeholder                             | No UI implementation                                                                             |
| `/proposal`                 | Authenticated          | Placeholder                                 | Placeholder                             | No UI implementation                                                                             |

## 3. API Endpoints by Service

Status legend:

- `Implemented`: actively called by current frontend.
- `Partial`: endpoint exists but runbook behavior is only partly covered.
- `Missing`: listed in runbook but no current frontend implementation.
- `Legacy`: still wired but superseded; kept deliberately, removal tracked in `EPIC-11-legacy-phaseout.md`.

## 3.1 Gateway and Shared Contracts

| Endpoint                                            | Method | Status      | Used In                                                                      |
| --------------------------------------------------- | ------ | ----------- | ---------------------------------------------------------------------------- |
| `/v1/tenants/{tenant_id}/...`                       | all    | Implemented | All tenant service modules                                                   |
| Envelope parsing (`success/data/errors/request_id`) | n/a    | Partial     | Generic `ApiClient` parses `data`; Copilot parses envelope/errors thoroughly |
| `/v1/trial/signup`                                  | POST   | Implemented | `trialService.signup`                                                        |
| `/v1/admin/trial-signups`                           | GET    | Implemented | `platformAdminService.listTrialSignups`                                      |

## 3.2 Copilot

| Runbook Endpoint                                                 | Method | Status      | Current Handler        |
| ---------------------------------------------------------------- | ------ | ----------- | ---------------------- |
| `/v1/tenants/{tenant_id}/copilot/health`                         | GET    | Implemented | `getCopilotHealth`     |
| `/v1/tenants/{tenant_id}/copilot/agents`                         | GET    | Implemented | `listCopilotAgents`    |
| `/v1/tenants/{tenant_id}/copilot/sessions`                       | POST   | Implemented | `createCopilotSession` |
| `/v1/tenants/{tenant_id}/copilot/sessions`                       | GET    | Implemented | `listCopilotSessions`  |
| `/v1/tenants/{tenant_id}/copilot/sessions/{session_id}`          | PATCH  | Implemented | `updateCopilotSession` |
| `/v1/tenants/{tenant_id}/copilot/sessions/{session_id}`          | DELETE | Implemented | `deleteCopilotSession` |
| `/v1/tenants/{tenant_id}/copilot/sessions/{session_id}/messages` | GET    | Implemented | `getCopilotMessages`   |
| `/v1/tenants/{tenant_id}/copilot/agents/query`                   | POST   | Implemented | `createCopilotQuery`   |
| `/v1/tenants/{tenant_id}/copilot/agents/query`                   | PATCH  | Implemented | `updateCopilotQuery`   |

Copilot agent contract notes:

- `GET /v1/tenants/{tenant_id}/copilot/agents` feeds the user-selectable picker only.
- Auto mode is the default-safe composer state and omits `agent_id` from create/update query payloads.
- Hidden backend IDs such as `reactive_agent` and `generic_agent` may still appear in response payloads and must render safely in the chat thread.

## 3.3 BDT

| Runbook Endpoint                                             | Method | Status      | Current Handler                                    |
| ------------------------------------------------------------ | ------ | ----------- | -------------------------------------------------- |
| `/v1/tenants/{tenant_id}/bdt/train`                          | POST   | Implemented | `trainBDT`                                         |
| `/v1/tenants/{tenant_id}/bdt`                                | GET    | Implemented | `listBDT`                                          |
| `/v1/tenants/{tenant_id}/bdt/models/{bdt_id}`                | GET    | Implemented | `getSingleBDT`                                     |
| `/v1/tenants/{tenant_id}/bdt/models/{bdt_id}/infer`          | POST   | Implemented | `startBdtInference`, `startBdtInferenceEnvelope`   |
| `/v1/tenants/{tenant_id}/bdt/models/{bdt_id}/infer/{run_id}` | GET    | Implemented | `getBdtInferenceRun`, `getBdtInferenceRunEnvelope` |

Additional implemented endpoint:

| Endpoint                                      | Method | Status      | Current Handler |
| --------------------------------------------- | ------ | ----------- | --------------- |
| `/v1/tenants/{tenant_id}/bdt/models/{bdt_id}` | DELETE | Implemented | `deleteBDT`     |

## 3.4 rApp

| Runbook Endpoint                                                                | Method | Status      | Current Handler                                  |
| ------------------------------------------------------------------------------- | ------ | ----------- | ------------------------------------------------ |
| `/v1/tenants/{tenant_id}/rapps/{rapp_id}/train`                                 | POST   | Implemented | `trainRappModel`                                 |
| `/v1/tenants/{tenant_id}/rapps/{rapp_id}/models`                                | GET    | Implemented | `getRappModels`                                  |
| `/v1/tenants/{tenant_id}/rapps/{rapp_id}/models/{rapp_model_id}/infer`          | POST   | Implemented | `generateInference`, `generateInferenceEnvelope` |
| `/v1/tenants/{tenant_id}/rapps/{rapp_id}/models/{rapp_model_id}/infer/{run_id}` | GET    | Implemented | `getInferResult`, `getInferResultEnvelope`       |
| `/v1/tenants/{tenant_id}/rapps/compare/infer`                                   | POST   | Implemented | `generateCompareInference`                       |

MRO-specialized handlers implemented on top of gateway tenant routes:

| Endpoint                                                                  | Method | Status      | Current Handler      |
| ------------------------------------------------------------------------- | ------ | ----------- | -------------------- |
| `/v1/tenants/{tenant_id}/rapps/mro/models`                                | GET    | Implemented | `listMroModels`      |
| `/v1/tenants/{tenant_id}/rapps/mro/models/{rapp_model_id}`                | GET    | Implemented | `getMroModel`        |
| `/v1/tenants/{tenant_id}/rapps/mro/train`                                 | POST   | Implemented | `startMroTraining`   |
| `/v1/tenants/{tenant_id}/rapps/mro/models/{rapp_model_id}/infer`          | POST   | Implemented | `startMroInference`  |
| `/v1/tenants/{tenant_id}/rapps/mro/models/{rapp_model_id}/infer/{run_id}` | GET    | Implemented | `getMroInferenceRun` |

Additional implemented endpoints:

| Endpoint                                                    | Method | Status      | Current Handler                      |
| ----------------------------------------------------------- | ------ | ----------- | ------------------------------------ |
| `/v1/tenants/{tenant_id}/rapps`                             | GET    | Implemented | `listAvailableRapps`, `listAllRapps` |
| `/v1/tenants/{tenant_id}/rapps/{rapp_id}/models/{model_id}` | GET    | Implemented | `getRappModelById`                   |
| `/v1/tenants/{tenant_id}/rapps/{rapp_id}/models/{model_id}` | DELETE | Implemented | `deleteRappModel`                    |

## 3.5 SMO and Data Sim

| Runbook Endpoint                                            | Method | Status      | Current Handler                           |
| ----------------------------------------------------------- | ------ | ----------- | ----------------------------------------- |
| `/v1/tenants/{tenant_id}/baselines`                         | POST   | Implemented | `createBaseline`                          |
| `/v1/tenants/{tenant_id}/baselines`                         | GET    | Implemented | `listBaselines`                           |
| `/v1/tenants/{tenant_id}/baselines/{baseline_id}`           | PUT    | Missing     | No update baseline handler/UI             |
| `/v1/tenants/{tenant_id}/baselines/{baseline_id}`           | DELETE | Implemented | `deleteBaseline`                          |
| `/v1/tenants/{tenant_id}/ue-data/datasets`                  | POST   | Partial     | Frontend currently uses `/ue-data/upload` |
| `/v1/tenants/{tenant_id}/ue-data/datasets/{dataset_id}`     | DELETE | Implemented | `deleteUeDataset`                         |
| `/v1/tenants/{tenant_id}/utils/topology/generate`           | POST   | Implemented | `generateBaseline`                        |
| `/v1/tenants/{tenant_id}/utils/traffic-load/generate`       | POST   | Implemented | `generateUeDataset`                       |
| `/v1/tenants/{tenant_id}/utils/mobility/generate`           | POST   | Implemented | `generateMobilityDataset`                 |
| `/v1/tenants/{tenant_id}/custom/nybsys/uploads`             | GET    | Legacy      | `listNybsysUploads` — uploads-history/count source only (EPIC-11 S1) |
| `/v1/tenants/{tenant_id}/custom/nybsys/uploads`             | POST   | Legacy      | `createNybsysUpload` — superseded by `POST /ingest/uploads` (§3.5c); only reachable from the unmounted `NybsysIngestionPage` |
| `/v1/tenants/{tenant_id}/custom/nybsys/uploads/{upload_id}` | GET    | Legacy      | `getNybsysUpload` — same, unmounted caller only |
| `/v1/tenants/{tenant_id}/custom/nybsys/uploads/{upload_id}` | DELETE | Legacy      | `deleteNybsysUpload` — same, unmounted caller only |

Additional implemented endpoint:

| Endpoint                                   | Method | Status      | Current Handler   |
| ------------------------------------------ | ------ | ----------- | ----------------- |
| `/v1/tenants/{tenant_id}/ue-data/datasets` | GET    | Implemented | `listUeDatasets`  |
| `/v1/tenants/{tenant_id}/ue-data/upload`   | POST   | Implemented | `createUeDataset` |

## 3.5a Data Platform (Neutral Ingest + Canonical Store) and NDT

Consumed via `useDataPlatformService` (`lib/api/services/data-platform.ts`), `useNdtEvaluateService` (`lib/api/services/ndt-evaluate.ts`), and `useNdtLoopService` (`lib/api/services/ndt-loop.ts`). The ingest rows became the PM Upload submission path in the 2026-08-06 IA realignment (frontend `dff7e05`), replacing the nybsys conversion flow.

| Endpoint                                             | Method | Status      | Current Handler                           |
| ---------------------------------------------------- | ------ | ----------- | ----------------------------------------- |
| `/v1/tenants/{tenant_id}/ingest/uploads`             | POST   | Implemented | `createIngestJob` — queues a durable ingest job (202) |
| `/v1/tenants/{tenant_id}/ingest/jobs/{job_id}`       | GET    | Implemented | `getIngestJob` — polled until `completed`/`failed` |
| `/v1/tenants/{tenant_id}/ingest/adapters`            | GET    | Implemented | `listAdapters` — feeds the `IngestAdaptersCard` source-adapter selector |
| `/v1/tenants/{tenant_id}/data/{pm\|fm\|cm}`          | GET    | Implemented | `query` — `/data/pm` also accepts keyset `cursor` and returns `next_cursor` since data_sim `f895006` (offset kept; frontend Load-more still offset-based, EPIC-11 S5) |
| `/v1/tenants/{tenant_id}/ndt/evaluate`               | POST   | Implemented | `evaluate`, `discoverCells`               |
| `/v1/tenants/{tenant_id}/ndt/evaluate/{run_id}`      | GET    | Implemented | `getRun`                                  |
| `/v1/tenants/{tenant_id}/ndt/kpis`                   | GET    | Implemented | `listKpiSnapshots` — KPI History queries with `from_ts`/`to_ts`/`limit`/`offset`/`bdt_id` (frontend `fd40b1e`) |
| `/v1/tenants/{tenant_id}/ndt/loop/policy`            | GET    | Implemented | `getPolicy`                               |
| `/v1/tenants/{tenant_id}/ndt/loop/policy`            | PUT    | Implemented | `updatePolicy` — full replace; the single tenant-wide loop mode lives here (supersedes per-device optimize-mode) |

## 3.5b NybSys NanoLink — Device Management (Operator API)

All consumed via `useNybsysDeviceService` (`lib/api/services/nybsys-devices.ts`); base `/v1/tenants/{tenant_id}/custom/nybsys`. Separate from the PM Upload (custom-pm-ingestion) nybsys service. Consumers: `/actuators`, `/policy`, and the `/devices/**` detail routes.

| Endpoint                                       | Method | Status      | Current Handler       |
| ---------------------------------------------- | ------ | ----------- | --------------------- |
| `/edge-devices`                                | GET    | Implemented | `listEdges`           |
| `/edge-devices`                                | POST   | Implemented | `createEdge`          |
| `/edge-devices/{edge_id}`                      | GET    | Implemented | `getEdge`             |
| `/edge-devices/{edge_id}`                      | DELETE | Implemented | `deleteEdge`          |
| `/edge-devices/{edge_id}:regenerate-key`       | POST   | Implemented | `regenerateKey`       |
| `/devices`                                     | GET    | Implemented | `listDevices`         |
| `/devices/{device_id}`                         | GET    | Implemented | `getDevice`           |
| `/devices/{device_id}/config`                  | GET    | Implemented | `getConfig`           |
| `/devices/{device_id}/optimize-mode`           | PATCH  | Legacy      | `setOptimizeMode` — backend returns `410 Gone` since smo_sim `5d31d65` (EPIC-11 S3); mode is tenant-wide via `PUT /ndt/loop/policy`, and device responses carry a derived `optimize_mode` |
| `/devices/{device_id}/commands`                | POST   | Implemented | `createCommand`       |
| `/devices/{device_id}/commands`                | GET    | Implemented | `listCommands`        |
| `/commands/{command_id}`                       | GET    | Implemented | `getCommand`          |
| `/devices/{device_id}/events`                  | GET    | Implemented | `getEvents`           |
| `/devices/{device_id}/kpis`                    | GET    | Implemented | `getKpis`             |
| `/devices/{device_id}/health`                  | GET    | Implemented | `getHealth`           |
| `/devices/{device_id}/recommendations`         | GET    | Implemented | `getRecommendations`  |
| `/recommendations/{reco_id}:approve`           | POST   | Implemented | `approveReco`         |
| `/recommendations/{reco_id}:reject`            | POST   | Implemented | `rejectReco`          |

## 3.6 Error Logs

| Endpoint Pattern                                            | Method | Status      | Current Handler            |
| ----------------------------------------------------------- | ------ | ----------- | -------------------------- |
| `/v1/tenants/{tenant_id}/{module}/logs/errors`              | GET    | Implemented | `getErrorLogsByModule`     |
| `/v1/tenants/{tenant_id}/{module}/logs/stats`               | GET    | Implemented | `getErrorLogStatsByModule` |
| `/v1/tenants/{tenant_id}/{module}/logs/errors/{id}`         | GET    | Implemented | `getErrorLogById`          |
| `/v1/tenants/{tenant_id}/{module}/logs/errors/{id}`         | DELETE | Implemented | `deleteErrorLog`           |
| `/v1/tenants/{tenant_id}/{module}/logs/errors`              | DELETE | Implemented | `clearErrorLogsByModule`   |
| `/v1/tenants/{tenant_id}/{module}/logs/errors/{id}/resolve` | PATCH  | Implemented | `resolveErrorLog`          |

## 3.7 Platform Admin and Tenant Directory

| Endpoint                                  | Method           | Status      | Current Handler                             |
| ----------------------------------------- | ---------------- | ----------- | ------------------------------------------- |
| `/v1/admin/tenants`                       | GET/POST         | Implemented | `platformAdminService`, `tenantService`     |
| `/v1/admin/tenants/{tenant_id}`           | GET/PATCH/DELETE | Implemented | `platformAdminService`, `tenantService`     |
| `/v1/admin/tenants/{tenant_id}/admins`    | POST             | Implemented | `createTenantAdmin`                         |
| `/v1/admin/platform-admins`               | GET/POST         | Implemented | `listPlatformAdmins`, `createPlatformAdmin` |
| `/v1/admin/platform-admins/{id}`          | DELETE           | Implemented | `deletePlatformAdmin`                       |
| `/v1/tenants/lookup`                      | GET              | Implemented | `tenantDirectoryService.lookup`             |
| `/v1/tenants/{tenant_id}/users`           | GET/POST         | Implemented | `tenantUserService`, `useTenantUserService` |
| `/v1/tenants/{tenant_id}/users/{user_id}` | GET/PATCH/DELETE | Implemented | `tenantUserService`, `useTenantUserService` |

## 3.8 Internal Next.js API Routes

| Route             | Method | Purpose                                              |
| ----------------- | ------ | ---------------------------------------------------- |
| `/api/auth/token` | POST   | Server-side Cognito token exchange fallback          |
| `/api/s3/upload`  | POST   | Sign direct browser uploads to S3-compatible storage |

## 4. Session-First Copilot Flow Contract

First-send contract implemented in `CopilotShell`:

1. `POST /copilot/sessions` with query.
2. Read returned `session_id`.
3. `POST /copilot/agents/query` with `session_id` + same query, plus `agent_id` only when the user explicitly selected one.
4. Reuse `session_id` for subsequent turns.

## 5. Route-Level Gaps to Track

- Tenant in URL path (`/tenants/[tenantId]/...`) is not currently used; tenant is auth/store-driven.
- Baseline `PUT` update handler/UI is not yet implemented.
- UE dataset create endpoint differs from runbook (`/ue-data/upload` currently used).
- `/rapp/inference/[id]` remains a legacy redirect for generic day-scope inference; MRO now uses `/rapp/mro/[rappModelId]`; `/compare` is likewise now a redirect stub (`/rapp?tab=models&view=compare`).
- `/devices` remains a redirect to `/actuators/tr069`; only the detail routes (`/devices/[deviceId]`, `/devices/edge/[edgeId]`) still render under `/devices`.
- The non-TR-069 adapter tiles on `/actuators` and the `Connect to RIC` tab on `/rapp` call no backend endpoint; tiles open an adapter info dialog, the RIC tab renders `RicConnectPanel` (`NotEnabledDialog` is now fully unmounted, EPIC-11 S8).
- `/data` Load-more still pages by `offset`; adopting `next_cursor` from `/data/pm` is EPIC-11 S5.
- The uploads-history table on `/custom-pm-ingestion` still reads the legacy `/custom/nybsys/uploads` list — the neutral ingest contract has no jobs-list endpoint yet (EPIC-11 S1).
- Trial dashboard restrictions are implemented on primary create/delete surfaces, but broader automated regression coverage for `trial_user` mode is still missing.

## 6. Route Definition Verification Checklist

Use this checklist when adding or changing routes:

1. Confirm endpoint exists in `artifacts/design/openapi.yaml` or document why it is intentionally frontend-only.
2. Confirm service wrapper path in `lib/api/services/*` matches this document.
3. Confirm page route and deep-links (for example table action links) match actual App Router paths.
4. Confirm tenant-scoped routes use `/v1/tenants/{tenant_id}/...` where required.
5. Confirm customer-facing labels match `lib/ui-content.ts` and `artifacts/ui-label-mapping.md` when visible UI terminology changes.
6. Update this file and `commit.md` in the same change set.
