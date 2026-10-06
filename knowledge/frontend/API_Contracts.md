# API Contracts and Integration Rules

## 1. Purpose

This document standardizes frontend-to-backend integration behavior across all services.

Customer-facing labels may differ from technical route and payload names. API contracts remain anchored to technical resources such as `baselines`, `ue-data`, `bdt`, and `rapps`; see `artifacts/ui-label-mapping.md` for the presentation-layer mapping used by the UI.

## 2. Base URL and Routing

- Base URL: `NEXT_PUBLIC_API_BASEURL`
- Expected gateway form: `https://<gateway>/v1`
- Tenant resources: `/tenants/{tenant_id}/...`
- Admin resources: `/admin/...`
- Public trial resources: `/trial/...`

## 3. Authentication Contract

- Browser requests attach Cognito ID token:
  - `Authorization: Bearer <idToken>`
- Token source:
  - Session storage (`cloudly.auth.tokens`), managed by `lib/auth/tokens.ts`
- Public endpoints such as `POST /v1/trial/signup` and `GET /v1/tenants/lookup` do not require auth.

## 4. Response Envelope Contract

Preferred success envelope:

```json
{
	"success": true,
	"timestamp": "2026-03-06T00:00:00Z",
	"message": "optional",
	"data": {},
	"errors": [],
	"request_id": "optional"
}
```

Preferred error envelope:

```json
{
	"success": false,
	"timestamp": "2026-03-06T00:00:00Z",
	"message": "Request failed",
	"data": {},
	"errors": [
		{
			"code": "VALIDATION_ERROR",
			"details": {
				"field": "baseline_id"
			}
		}
	],
	"request_id": "optional"
}
```

Implementation behavior:

- `ApiClient` returns `payload.data` for standard success responses.
- `ApiClient.getResponse` and `ApiClient.postResponse` expose HTTP status and headers for flows that need `200` vs `202` handling, such as MRO inference.
- `CopilotClient` supports both envelope and direct payload response variants.

## 5. Error Mapping Contract

## 5.1 Generic `ApiClient`

- Handles 401 with forced sign-out and redirect.
- Converts failures to `ApiError` with:
  - `message`
  - `code`
  - `status`
  - `details`

Known friendly message overrides:

- `TENANT_FORBIDDEN`
- `PLATFORM_ADMIN_MEMBERSHIP_REQUIRED`
- `COGNITO_ERROR` (non-dev friendly message)
- `EMAIL_ALREADY_EXISTS`
- `TRIAL_CAP_REACHED`
- `TRIAL_READ_ONLY`
- `RATE_LIMITED` with `retry_after_seconds` when the gateway returns `Retry-After`

## 5.2 Copilot Error Mapping

`CopilotClient` status mappings:

- 401 -> `UNAUTHORIZED`
- 403 -> `FORBIDDEN`
- 404 -> `NOT_FOUND`
- 422 -> `VALIDATION_ERROR`
- 429 -> `RATE_LIMITED`
- 500 -> `INTERNAL_ERROR`
- 502 -> `DEPENDENCY_ERROR`
- 503 -> `SERVICE_UNAVAILABLE`
- 504 -> `TIMEOUT`

Includes `requestId` where available.

## 6. Pagination Contracts

## 6.1 Offset/limit style

Used in legacy list APIs:

```json
{
	"items": [],
	"total": 0
}
```

## 6.2 Cursor style

Used in Copilot session/message APIs:

```json
{
	"items": [],
	"next_cursor": "cursor-token",
	"prev_cursor": "cursor-token",
	"has_more": true
}
```

`CopilotClient` normalizes variants (`sessions`, `messages`, nested `data.items`, etc.) into `CopilotCursorPage<T>`.

## 7. Async Operation Contracts

## 7.0 Trial Signup and Admin Listing

Fixed trial tenant: name `netai trial` · slug `netai-trial` · UUID
`00000000-0000-0000-3029-000000000001`. The signup response returns `tenant_id`; reuse it directly
for post-signup login state.

**Public signup — `POST /v1/trial/signup`** · Auth: none · Rate limit: `5/min` per IP.

```json
// request
{ "name": "Test User", "email": "trial-user@example.com", "phone": "+1234567890",
  "company_name": "Acme Wireless", "designation": "CTO" }
// 201 success (envelope `data`)
{ "message": "signup successful, check your email for login credentials",
  "tenant_id": "00000000-0000-0000-3029-000000000001", "user_id": "…",
  "user_email": "trial-user@example.com", "user_name": "Test User", "temp_password": "TempPass1!" }
```

- `designation` is optional (backend persists empty string when absent). Envelope carries
  `timestamp`; there is no separate top-level success `message`.
- Frontend: show returned credentials immediately; keep the Cognito-email notice in copy; reuse
  `tenant_id` for hosted sign-in bootstrap; expose a returning-user sign-in on `/trial` that
  resolves the shared trial tenant and starts the same hosted login flow without resubmitting.
- Error → UI mapping:

  | Status | Code | Frontend handling |
  | --- | --- | --- |
  | `400` | `INVALID_REQUEST` | Field validation errors from the envelope message/details. |
  | `409` | `EMAIL_ALREADY_EXISTS` | "This email is already associated with a CloudlyNet account." (duplicate may come from `tenant_memberships.email` or Cognito). |
  | `403` | `TRIAL_CAP_REACHED` | "Trial signup capacity reached. Contact sales." |
  | `429` | `RATE_LIMITED` | Throttling state; respect `Retry-After: 60`. |
  | `502` | `COGNITO_ERROR` | Generic retry/support message; do not surface raw backend detail. |

**Admin lead listing — `GET /v1/admin/trial-signups?page=1&page_size=20`** · Auth: `cloudly_admin` ·
`page_size` default `20`, max `100`.

```json
// data
{ "items": [ { "id": "…", "email": "…", "name": "…", "phone": "…",
    "company": "Acme Wireless", "designation": "CTO", "created_at": "…" } ],
  "total": 1, "page": 1, "page_size": 20 }
```

Admin row keys are exactly `company` and `created_at`; `designation` may be empty.

- Trial-user auth rules: allow all tenant-scoped `GET`; allow BDT infer `POST`, rApp infer `POST`,
  compare `POST`, and all Copilot endpoints; block create/train/delete/generate/data-generation/
  user-management with `403 TRIAL_READ_ONLY`. Do not hide inference/compare just because they are `POST`.
- Dependencies: `artifacts/migration/007_trial_org.sql` applied; trial tenant seeded (demo baselines/BDTs/
  rApp models); Cognito pool configured for trial-user creation; gateway CORS allow-lists the
  `/trial` origin; `NEXT_PUBLIC_WHATSAPP_SALES_URL` powers the sales CTA.
- Acceptance: `/trial` renders + submits without auth; success screen shows `temp_password` +
  `user_email` + login CTA; `trial_user` guards switch the dashboard to read-only; infer/compare/
  copilot still work; `cloudly_admin` can paginate the leads list; signup errors cover `400/403/
  409/429/502`.

> Folded in from the former root `frontend_agent_handover.md` (2026-04-07). UI/UX flow, navigation,
> and layout live in [`route.md`](./route.md), [`UI_Design.md`](./UI_Design.md), and
> [`execution_runbook.md`](./execution_runbook.md).

## 7.1 Digital Twin Inference (BDT)

- Start request: `POST /v1/tenants/{tenant_id}/bdt/models/{bdt_id}/infer`
  - request payload includes `ue_dataset_id`, `tick`, and optional `baseline_id`.
  - response body includes `run_id` and initial `status`.
  - backend may also return `Location` header for poll URL.
- Poll request: `GET /v1/tenants/{tenant_id}/bdt/models/{bdt_id}/infer/{run_id}`
  - terminal success: `completed`
  - terminal failure: `failed`
- Frontend implementation:
  - route: `/bdt/models/[bdtId]/infer`
  - service handlers: `startBdtInference`, `getBdtInferenceRun`
  - UI polls every 4s until terminal state.

## 7.2 Network Optimisation Inference (rApp)

- Start request returns `run_id` and initial status.
- Frontend polls infer result endpoint until terminal status:
  - terminal success: `completed` or `ready`
  - terminal failure: `failed` or `error`
- Shared Non-MRO tick payload contract for ES/LB/CCO:
  - `result.text.tick`
  - `result.text.items[]`
  - each item contains `cell_id`, `el_degree`, and `on_off`
- Day-scope Non-MRO evaluation contract additionally exposes:
  - `result.per_tick_recommendations[{ tick, items[] }]`
  - optional `result.raw_tick_data[tick].tilt_by_cell`
  - optional `result.raw_tick_data[tick].recommendations`
- Frontend reuses the same recommendation table for ES, LB, and CCO instead of branching by rApp-specific text schemas, including selected-tick day diagnostics.

Poll helpers:

- `isRunningStatus`
- `isReadyStatus`
- `isFailedStatus`

## 7.3 Compare Models (rApp Compare)

- `/compare` remains the day-scope compare surface in frontend. (updated 2026-08-06: `/compare` is now a server redirect to `/rapp?tab=models&view=compare`; the compare surface is the embedded `Compare Models` view on `/rapp`, same `InferenceCompare` component and backend contract. Frontend `fd40b1e`.)
- Model selection allows cross-rApp ES/LB/CCO combinations, including CCO as either base or compare target.
- MRO remains excluded from compare UI even though the backend compare contract still types `rapp_id` broadly.

## 7.4 Mobility Optimisation (MRO) Training and Inference

- Training request: `POST /v1/tenants/{tenant_id}/rapps/mro/train`
  - request payload must send explicit `params.mro_type`
  - frontend emits canonical `params.total_timesteps`
  - frontend builds a deterministic `Idempotency-Key`
  - browser submission only sends the `Idempotency-Key` header when `NEXT_PUBLIC_ENABLE_MRO_IDEMPOTENCY_HEADER=true`, because the current local gateway CORS allow-list does not include `Idempotency-Key`
- MRO model detail route polls `GET /v1/tenants/{tenant_id}/rapps/mro/models/{rapp_model_id}` until model status reaches `ready` or `failed`
- Inference start request: `POST /v1/tenants/{tenant_id}/rapps/mro/models/{rapp_model_id}/infer`
  - request payload includes `baseline_id`, `bdt_id`, `ue_dataset_id`, and `params.baseline_hyst` / `params.baseline_ttt`
  - `200 OK` means a completed cached/deduplicated run was returned immediately
  - `202 Accepted` means the run is queued or running and frontend polling must start
  - `409 Conflict` maps to a model-not-ready UI state
- Inference poll request: `GET /v1/tenants/{tenant_id}/rapps/mro/models/{rapp_model_id}/infer/{run_id}`
  - terminal success: `completed`
  - terminal failure: `failed`
- MRO UI rules:
  - no tick control
  - no day control
  - no compare flow
  - MRO dataset selectors are not baseline-filtered or baseline-validated in frontend until dataset-topology mapping is defined
  - when dataset metadata does not positively identify mobility-compatible options, frontend falls back to listing tenant datasets and leaves final mobility validation to submit-time checks/backend validation
  - render backend-provided `delta` instead of recomputing it in frontend

## 7.5 Copilot Session and Query

- First message must create session first, then query using returned `session_id`.
- `GET /v1/tenants/{tenant_id}/copilot/agents` returns only user-selectable agents for the picker; frontend must not inject hidden internal agents into that list.
- Auto mode keeps agent selection optional and omits `agent_id` from `POST` / `PATCH /copilot/agents/query`.
- Edit flow uses `PATCH /copilot/agents/query` with `message_id`.
- Chat rendering must tolerate backend response `agent_response.agent_id` values that are not present in the picker list, including `reactive_agent` and `generic_agent`.

## 7.6 Nybsys Custom PM Ingestion

(updated 2026-08-06: this contract is LEGACY, EPIC-11 S1. The PM Upload page now submits through the vendor-neutral ingest contract — `POST /v1/tenants/{tenant_id}/ingest/uploads` (202, `IngestJobCreate`: `job_id?`, `source_type`, adapter-specific `params`) polled via `GET /v1/tenants/{tenant_id}/ingest/jobs/{job_id}` (`IngestJobOut`: `status` queued|running|completed|failed, adapter-specific `stats`). The S3-presign step below is unchanged. Of the endpoints below, only the uploads list `GET` is still called, as the history/count source. Frontend `dff7e05`.)

- Upload flow:
  - raw PM CSV files request a presigned PUT URL through `/api/s3/upload`
  - browser uploads the file body directly to S3-compatible storage
  - frontend writes tenant-scoped S3 keys under `tenants/{tenant_id}/pm-data-ingestion/{upload_id}/raw/{filename}.csv`
  - frontend then submits `POST /v1/tenants/{tenant_id}/custom/nybsys/uploads`
- Create request payload:
  - `upload_id`
  - `raw_s3_urls[]`
  - optional `rng_seed`
  - optional `samples_per_cell`
- Create response:
  - backend returns the upload record immediately and frontend treats the job as asynchronous
- Poll request:
  - `GET /v1/tenants/{tenant_id}/custom/nybsys/uploads/{upload_id}`
  - terminal success: `completed`
  - terminal failure: `failed`
- Delete request:
  - `DELETE /v1/tenants/{tenant_id}/custom/nybsys/uploads/{upload_id}`
  - `DELETE /v1/tenants/{tenant_id}/custom/nybsys/uploads/{upload_id}?delete_derived=true`
- UI rules:
  - runtime `403` is the feature-disabled source of truth for this branch
  - show backend `error` verbatim on failed uploads
  - treat `uploading` as queued/accepted and `processing` as actively running
  - expose derived `baseline_id` and `dataset_id` as read-only outputs
  - keep delete actions disabled until the upload reaches a terminal state

## 7.7 NybSys NanoLink Device Management

- Operator API under `/v1/tenants/{tenant_id}/custom/nybsys/**`, consumed via `useNybsysDeviceService` (separate from 7.6 uploads). Standard success envelope; `403` when the `nybsys` feature flag is off.
- List endpoints return `{ items, total }`; KPIs return `{ samples, total }`; create-command returns `{ command_id, status }`.
- Enrollment: `POST /edge-devices` and `POST /edge-devices/{edge_id}:regenerate-key` return `EnrollmentData` with a one-time `enrollment_token` that is **never returned again** — UI must reveal it once with a copy action and a clear warning.
- Config commands: `POST /devices/{device_id}/commands` with `{ type: "configure", payload: { writes: [{path, value}], rollback_on_fail: true } }`; server validates writes against the managed-param catalogue (`422` on out-of-bounds). Frontend pre-validates client-side from the mirrored catalogue (`lib/nybsys/managed-params.ts`). Command history treats `rolled_back` as a terminal status because `/v1/agent/commands/{id}/ack` may persist `applied|failed|rolled_back`.
- `GET /devices/{device_id}/config` returns the latest materialized non-empty snapshot. Server-side partial periodic reads and one-field command read-backs merge into that map; frontend counts catalogue paths and labels zero/partial values rather than interpreting blank controls as device values.
- `GET /commands/{command_id}` returns agent verification evidence in `result`: `readback` plus `mismatch[{path, expected, actual, missing}]`. A `failed` command leaves the Current snapshot unchanged; frontend retains the Proposed update for correction and displays the actual value instead of rendering an undefined placeholder.
- Command lifecycle to surface: `pending → dispatched → applied | failed` (+ auto `rolled_back`); full `payload`/`prev_values`/`result`/`error` only come from `GET /commands/{command_id}` (list omits them).
- Telemetry: `GET /devices/{device_id}/events` (`severity`, `since`, `limit`), `GET /devices/{device_id}/kpis` (`tier`, `since`, `limit`), `GET /devices/{device_id}/health` (rollup `{health, op_state, rf_tx_status, last_inform_at, recent_critical, recent_major}` — reason/freshness derived client-side).
- Optimisation: `PATCH /devices/{device_id}/optimize-mode` `{ mode: off|approval|auto }` (updated 2026-08-06: returns `410 Gone` — loop mode is tenant-wide via `PUT /v1/tenants/{tenant_id}/ndt/loop/policy`, and device responses carry an `optimize_mode` DERIVED from that policy; smo_sim `5d31d65`, EPIC-11 S3); recommendations `GET /devices/{device_id}/recommendations`, `POST /recommendations/{reco_id}:approve` (creates an optimise command), `POST /recommendations/{reco_id}:reject`.
- UI polling cadences: device table 15s, command history 5s (while in-flight), events 10s, KPIs 30s, health 15s, recommendations 20s; polling pauses when the tab is hidden.

## 8. Header Contracts

- `Content-Type: application/json` for JSON endpoints.
- `Idempotency-Key` support for browser MRO training is env-gated until gateway CORS allows that header.
- `Idempotency-Key` for BDT training is required by runbook but not yet implemented in current BDT service wrapper.
- `NEXT_PUBLIC_WHATSAPP_SALES_URL` powers the inline and floating trial workspace CTA surfaces and defaults to `https://api.whatsapp.com/send/?phone=16507052005` when unset.

## 9. File Upload Contracts

- Frontend requests signed uploads through internal route `/api/s3/upload`.
- Internal route signs direct browser PUT uploads to S3-compatible storage using AWS SDK.
- Object storage must allow browser `PUT` uploads from the frontend origin via CORS.
- Uploaded URI is passed to service APIs as `s3://bucket/key` style references.

## 10. Contract Deviations to Resolve

- UE dataset create route currently uses `/ue-data/upload` instead of runbook `/ue-data/datasets`.
- BDT training idempotency header support is still pending in the service wrapper.
- Generic envelope parser does not yet expose `request_id` diagnostics globally outside selective flows such as the MRO detail page.
