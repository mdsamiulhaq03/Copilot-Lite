# Low-Level Design (LLD)

## 1. Purpose

This document defines concrete implementation details for the current frontend codebase: file ownership, data flow, service integration patterns, and key interaction logic.

## 2. Directory Ownership

## 2.1 App Router

- `app/layout.tsx`
  - Root HTML shell and global providers (`StoreProvider`).
- `app/(auth)/*`
  - Tenant entry, login proxy, signup/reset flows.
- `app/auth/callback/*`
  - Cognito authorization code callback and token persistence.
- `app/(dashboard)/layout.tsx`
  - Dashboard application shell with `ApplicationProvider` preload and toaster.
- `app/(dashboard)/*`
  - Feature pages for the enterprise IA (`Topology`, `Mobility Data`, `Custom Upload`, `Digital Twin`, `Network Optimisation`, `Run Model`, `Compare Models`, `Copilot`, administration, and error logs), while keeping technical route names unchanged.

## 2.2 Service Layer

- `lib/api/client.ts`
  - Generic fetch wrapper with auth header injection and envelope extraction.
- `lib/api/services/*.ts`
  - Domain service wrappers.
- `lib/api/services/copilot.ts`
  - Specialized parser and status mapping for Copilot.

## 2.3 Presentation Layer and IA

- `lib/app.config.ts`
  - Role-aware sidebar information architecture and dashboard CTA definitions.
- `lib/ui-content.ts`
  - Shared customer-facing label mapping and optimisation model display names.
- `components/app-sidebar.tsx`
  - Sidebar filtering, workspace summary card, and Cloudly-only Error Logs nav handling.
- `components/nav-main.tsx`
  - Nested navigation rendering for grouped enterprise IA.
- `components/app-topbar.tsx`
  - Top-bar brand chrome and Copilot entry.
- `components/common/PageTitle.tsx`
  - Standard page header pattern with title and layman-friendly subtitle.

## 2.4 State Layer

- `lib/store/index.ts`
  - Combined persisted Zustand store.
- Slices:
  - `auth.ts`
  - `tenant.ts`
  - `data.ts`
  - `ui.ts`
  - `users.ts`

## 2.5 Components

- `components/common/*`
  - Generic data table and confirmation patterns.
- `components/{baseline,smo,bdt,rapp,inference,error-logs,copilot}`
  - Feature-specific UI and orchestration.
- `components/copilot/*`
  - Copilot panel primitives and shell orchestration.

## 3. Authentication and Session Flow

1. User lands on `/select-tenant`.
2. `TenantForm` resolves tenant ID via `/tenants/lookup` and keeps the validated tenant display name from the lookup response (or validated input fallback).
3. Hosted Cognito login starts (`startCognitoLogin`).
4. Callback route exchanges auth code for tokens.
5. Token claims are validated and converted into `AuthUser`.
6. `authUser`, `tenantId`, and tenant display name hydrate Zustand persisted state.
7. Dashboard shell grants access and triggers initial data preload.

Implementation files:

- `components/auth/TenantForm.tsx`
- `lib/auth/cognito.ts`
- `app/auth/callback/AuthCallbackClient.tsx`
- `lib/store/auth.ts`

## 4. Data Preload Strategy

`ApplicationProvider` runs after tenant exists and fetches in parallel:

- Baselines (`Topology` in customer-facing UI)
- UE datasets (`Mobility Data` in customer-facing UI)
- BDT list (`Digital Twin` in customer-facing UI)
- rApp list, then models per rApp (`Network Optimisation` in customer-facing UI)

It commits data into Zustand stores for immediate table rendering across pages.

Nybsys custom ingestion is intentionally excluded from preload because the backend
feature flag is enforced by runtime `403` on `/custom/nybsys/*` routes.

Implementation file:

- `providers/ApplicationProvider.tsx`

## 5. API Client Internals

## 5.1 `ApiClient`

- Base URL from `NEXT_PUBLIC_API_BASEURL`.
- Automatically sends:
  - `Content-Type: application/json`
  - `Authorization: Bearer <idToken>` when available.
- Handles:
  - 401 -> clear auth + redirect to `/select-tenant?reason=session-expired`
  - envelope parsing (`SuccessEnvelope<T>` returns `data`)
  - `ApiError` with `code/status/details`

## 5.2 `CopilotClient`

- Tenant base path builder: `/tenants/{tenant}/copilot`.
- Accepts envelope and non-envelope payload variants.
- Normalizes cursor pages (`items`, `next_cursor`, `prev_cursor`).
- Maps status codes to typed Copilot errors.
- Supports abort signals for cancellation on rapid selection changes.

## 6. Feature-Level Implementation Details

## 6.1 Topology (`/baseline`)

- Create flow supports two modes:
  - File upload mode (presign via `/api/s3/upload`, direct S3 upload, then `/tenants/{tenant}/baselines`)
  - Utils generation mode (`/tenants/{tenant}/utils/topology/generate`)
- Customer-facing copy refers to baseline records as `Topology` or `Topology Records`, but technical payloads continue to use `baseline_id`.
- Delete flow uses shared confirmation modal.

Files:

- `components/baseline/AddBaselineModal.tsx`
- `components/baseline/BaselineDataTable.tsx`
- `lib/api/services/baselines.ts`

## 6.2 Mobility Data and Custom Upload (`/smo`, `/custom-pm-ingestion`)

- Create flow supports:
  - Upload mode (`/tenants/{tenant}/ue-data/upload`)
  - Utils traffic generation (`/utils/traffic-load/generate`)
  - Mobility generation (`/utils/mobility/generate`)
- Baseline selector is sorted by newest baseline.
- Customer-facing copy refers to SMO datasets as `Mobility Data`, `Mobility Datasets`, and `Mobility Dataset`.
- Dedicated Nybsys custom PM ingestion route: `/custom-pm-ingestion`
  - requests signed uploads through `/api/s3/upload`
  - uploads raw PM CSV files directly from the browser to S3-compatible storage
  - writes to tenant-scoped S3 keys under `pm-data-ingestion/{upload_id}/raw`
  - submits `raw_s3_urls` to `/tenants/{tenant}/custom/nybsys/uploads`
  - polls upload state until `completed` or `failed`
  - exposes plain delete vs delete-with-derived-cascade after terminal state
  - handles backend `403` as the source-of-truth disabled state
  - exposes derived outputs as `Derived Topology` and `Derived Mobility Dataset`

Files:

- `components/smo/AddSMOModal.tsx`
- `components/smo/SMODataTable.tsx`
- `lib/api/services/ue-datasets.ts`
- `components/smo/NybsysIngestionPage.tsx`
- `components/smo/NybsysUploadForm.tsx`
- `components/smo/NybsysUploadStatusCard.tsx`
- `components/smo/NybsysUploadsTable.tsx`
- `lib/api/services/nybsys.ts`
- `app/(dashboard)/custom-pm-ingestion/page.tsx`

## 6.3 Digital Twin (`/bdt`, `/bdt/models/[bdtId]/infer`)

- Training from selected baseline and baseline CSV links.
- Table includes simulation deep-link, refresh, and delete actions.
- Inference route: `/bdt/models/[bdtId]/infer`.
- Inference flow:
  - start async run (`POST /bdt/models/{bdt_id}/infer`)
  - poll run status (`GET /bdt/models/{bdt_id}/infer/{run_id}`)
  - render plot + metrics after completion
- Customer-facing copy removes `Bayesian` and `BDT` from primary headers while keeping technical route and payload naming unchanged.

Files:

- `components/bdt/TrainBDTModal.tsx`
- `components/bdt/BDTDataTable.tsx`
- `components/bdt/BdtInferenceDashboard.tsx`
- `components/bdt/BdtInferenceForm.tsx`
- `components/bdt/BdtInferenceRunStatus.tsx`
- `components/bdt/BdtInferencePlot.tsx`
- `components/bdt/BdtInferenceMetrics.tsx`
- `app/(dashboard)/bdt/models/[bdtId]/infer/page.tsx`
- `lib/api/services/bdt.ts`

## 6.4 Network Optimisation (`/rapp`)

- Training form requires model type, BDT, and dataset.
- Derives baseline from selected BDT.
- Model table supports type tabs, status filters, refresh, delete, and contextual `Run Model` / MRO detail links.
- Shared optimisation model display names are sourced from `lib/ui-content.ts`, mapping `ES`, `MRO`, `CCO`, and `LB` to customer-facing labels while preserving the underlying `rapp_id` values.

Files:

- `components/rapp/TrainRappModal.tsx`
- `components/rapp/RAPPDataTable.tsx`
- `components/rapp/TrainRappWidget.tsx`
- `lib/api/services/rapps.ts`

## 6.5 Run Model (`/infer`)

- Route: `/infer?model_id={id}&day={n}`.
- Starts infer run and polls until terminal status.
- Uses shared Non-MRO text typing for ES/LB/CCO tick payloads plus day-scope `per_tick_recommendations` and raw `tilt_by_cell` mirrors.
- The route is no longer a standalone side-nav destination; users reach it contextually from Network Optimisation model actions.
- Surfaces:
  - run metadata
  - warnings
  - guardrail/objective KPI cards
  - per-tick tables/charts
  - histogram and heatmap views
  - selected-tick recommendation and tilt diagnostics inside the existing tick snapshot panel
  - shared tick recommendation table when a Non-MRO tick payload is returned unexpectedly on the day-scope screen

Files:

- `components/inference/DayInferenceDashboard.tsx`
- `components/inference/InferenceResultTable.tsx`
- `components/inference/day-eval-utils.ts`

## 6.6 Compare Models (`/compare`)

- Route: `/compare`.
- Compares two models on a shared dataset/day.
- Allows cross-rApp ES/LB/CCO pairings, including CCO overrides, while leaving MRO out of compare.
- Surfaces:
  - delta cards/table
  - pareto chart
  - overlay time series
  - warnings and worst-tick comparison

File:

- `components/inference/InferenceCompare.tsx`

## 6.7 Error Logs (`/error-logs`)

- Tabbed module views (`Baseline`, `BDT`, `RAPP`, `Utils`).
- Supports refresh and resolve actions.
- Includes stack trace visualization and copy interaction.
- Route remains available, but side-nav exposure is limited to Cloudly internal admins.

Files:

- `app/(dashboard)/error-logs/page.tsx`
- `components/error-logs/ErrorLogsDataTable.tsx`
- `lib/api/services/error-logs.ts`

## 6.8 Copilot (Session-First, Top-Bar Entry)

- Route: `/copilot`.
- Shell behavior:
  - health fetch
  - agent list fetch
  - auto-routed agent default with tenant-local persistence only for explicit selections
  - session cursor paging
  - message cursor paging
  - URL session sync (`?session=`)
  - desktop right panel and mobile sheet
- Panel composition contract:
  - `CopilotShell` owns `sessionSearch`
  - `CopilotPanel` receives `sessionSearchValue` and `onSearchChange`
  - `CopilotSessionList` consumes the same `onSearchChange` handler
- First send flow:
  1. `createCopilotSession(query)`
  2. `createCopilotQuery({ session_id, query, agent_id? })`
- Edit flow:
  - `updateCopilotQuery({ message_id, query, agent_id? })`
- Agent behavior:
  - picker options come only from `GET /copilot/agents`
  - Auto mode omits `agent_id` on create/update query payloads
  - response rendering tolerates hidden backend IDs such as `reactive_agent` and `generic_agent`
- Recoveries:
  - Handles 403 access denied.
  - Handles 404 missing session/message by clearing selection and reloading sessions.
- Copilot remains accessible from the top bar and is intentionally omitted from the side navigation.

Files:

- `components/copilot/CopilotShell.tsx`
- `components/copilot/CopilotPanel.tsx`
- `lib/api/services/copilot.ts`

## 7. Shared Table Pattern

All major CRUD pages follow:

1. Typed column definitions in `lib/table/*`.
2. Generic data table wrapper for search/sort/filter/pagination.
3. Optional controlled mode when external filter controls are needed.
4. Delete confirmation modal before destructive operations.
5. `PageTitle` header with a clear title and short product-facing subtitle where the page is a major user surface.

Files:

- `components/common/GenericDataTable.tsx`
- `components/common/PageTitle.tsx`
- `hooks/useDataTable.ts`
- `components/common/DeleteConfirmationModal.tsx`

## 8. Error Handling and UI State

- Global behavior
  - API clients throw `ApiError`/`CopilotApiError`.
  - UI surfaces toast errors and inline messages.
- Typed status handling
  - Copilot explicitly maps `401/403/404/422/429/5xx`.
- Session expiry
  - Redirect to `/select-tenant` with query reason.

## 9. Responsive Behavior

- App shell
  - Desktop collapsible left sidebar
  - Mobile sheet sidebar with trigger
  - Grouped sidebar IA with `Network Setup`, `Digital Twin`, `Network Optimisation`, and `Administration`
- Copilot
  - Desktop fixed right panel
  - Mobile full screen right sheet
- Data-heavy pages
  - Chart/table sections stack vertically on smaller widths.

## 10. Known LLD Notes

- `Error Logs` page injects local dummy error data in addition to fetched data.
- Placeholder routes exist for `/opex-estimate` and `/proposal`.
- Test framework is not yet wired in package scripts.
