# Frontend Execution Runbook

Execution runbook for implementation agents working in the `maveric_platform_frontend` repo.
Salvaged from that repo's `Agent.md`. Paths below are **frontend-repo-relative** unless prefixed
with `artifacts/`. The frontend consumes `artifacts/design/openapi.yaml` unchanged and does not define its own
contract.

## 1. Mission

Deliver tenant-scoped frontend features aligned to gateway contracts, with consistent UX and
typed integrations across:

- Public trial onboarding (`/trial`)
- Network Setup (`/baseline`, `/smo`, `/custom-pm-ingestion`)
- Digital Twin (`/bdt`)
- Network Optimisation (`/rapp`, `/infer`, `/compare`)
- Device Management — NybSys NanoLink (`/devices`)
- Error Logs
- Copilot
- Platform and tenant administration

## 2. Non-Negotiable Integration Rules

1. All browser API traffic must go through the gateway base URL.
2. For tenant resources, use `/v1/tenants/{tenant_id}/...` style paths.
3. Always attach the Cognito bearer token through shared client behavior.
4. Treat backend responses as envelope-first contracts (`{ success, timestamp, data, errors }`).
5. Handle status-code outcomes explicitly in UI states: `401`, `403`, `404`, `422`, `429`, `5xx`.
6. Preserve tenant isolation. Do not allow cross-tenant navigation side effects.
7. Copilot first-send must remain session-first.
8. MRO must stay on its dedicated async simulation path; do not reuse ES/LB/CCO tick/day or the
   compare UI for MRO.
9. Customer-facing labels stay centralized in `lib/ui-content.ts` and documented in
   `artifacts/ui-label-mapping.md`; presentation-layer renames do not justify route or API changes.
10. Copilot stays top-bar only and Error Logs stay Cloudly-admin-only in side navigation unless
    product requirements explicitly change.
11. `trial_user` workspaces stay read-only for create/train/delete/generate actions, while infer,
    compare, and Copilot remain available.

## 3. Current Architecture Snapshot

- Framework: Next.js App Router (`app/(auth)`, `app/(dashboard)`).
- State: persisted Zustand store (`lib/store/*`).
- API: `ApiClient` and specialized `CopilotClient`.
- Presentation layer: shared customer-facing labels in `lib/ui-content.ts`, role-aware IA in
  `lib/app.config.ts`, and enterprise shell components in `components/app-sidebar.tsx`,
  `components/nav-main.tsx`, `components/app-topbar.tsx`, and `components/common/PageTitle.tsx`.
- Shell:
  - `StoreProvider` initializes auth.
  - `ApplicationProvider` preloads tenant data.
  - `DashboardShell` enforces authenticated access.

## 4. Feature Ownership Map

### 4.1 Auth and Tenant Bootstrap

- Tenant lookup: `tenantDirectoryService.lookup`.
- Hosted login bootstrap: `startCognitoLogin`.
- Callback token exchange: `/api/auth/token` (server mode fallback).
- Keep `/select-tenant` on the existing split-shell auth pattern: branded context panel, shared
  card primitives, existing logo assets only; copy aligned to `artifacts/marketing.md`, favoring
  enterprise workspace language over backend implementation terms.
- Keep `/trial` on the same brand system, reuse the hosted Cognito bootstrap, and prefer the
  returned `tenant_id` from `POST /v1/trial/signup` over slug lookup. Keep it explicit for both
  first-time signup and returning-user sign-in.
- Persist the validated tenant display name alongside `tenantId` so the shell can render the
  organization name after hosted login returns.
- Files: `components/auth/TenantForm.tsx`, `components/trial/TrialSignupForm.tsx`,
  `app/auth/callback/AuthCallbackClient.tsx`, `lib/auth/*`.

### 4.2 Network Setup (Topology, Mobility Data, Custom Upload)

- Customer-facing navigation groups `/baseline`, `/smo`, and `/custom-pm-ingestion` under
  **Network Setup**.
- Topology create/list/delete and utils generation; mobility dataset create/list/delete and utils
  generation.
- Nybsys custom PM ingestion at `/custom-pm-ingestion` using gateway-routed
  `/v1/tenants/{tenant_id}/custom/nybsys/uploads`. Upload raw PM CSVs to S3 first and submit only
  `raw_s3_urls` to the backend. File uploads via `/api/s3/upload`.
- Nybsys availability is runtime-checked from backend `403`; keep the flow page-local and do not
  preload it in `ApplicationProvider`.

### 4.3 Digital Twin (BDT)

- BDT train/list/get/delete.
- Async inference route `/bdt/models/[bdtId]/infer`; handlers `startBdtInference`,
  `getBdtInferenceRun` (UI polling).
- Keep the Digital Twin library on the shared `ControlledGenericDataTable` pattern: search, status
  filter, refresh-all, and row actions belong in the table filter rail, not bespoke page chrome.

### 4.4 Network Optimisation and Model Execution

- Customer-facing labels: `/rapp` = **Network Optimisation**, `/compare` = **Compare Models**.
  `/infer` is exposed contextually as **Run Model** from optimisation model actions — do not
  reintroduce it as a standalone side-nav item.
- Trial mode must keep compare and model-run flows discoverable even while training/delete are
  disabled.
- rApp model train/list/get/delete; generic day-scope infer start + polling for ES/LB/CCO via
  `/infer`.
- Shared Non-MRO recommendations for ES/LB/CCO use one text contract
  (`tick + items[{cell_id, el_degree, on_off}]`) across tick payloads and day-scope
  `per_tick_recommendations`.
- Keep `/infer` on the compact selected-hour review layout (commit
  `e7894119cb4674aed088bff514af31426d714f2d`): recommendations, KPI payload, serving-cell load,
  and raw RSRP/SINR summaries remain; separate selected-hour cell-state and `tilt_by_cell` tables
  stay out unless the contract changes.
- Compare inference for ES/LB/CCO via `/compare`, including cross-rApp ES/LB/CCO pairings while
  keeping MRO excluded.
- MRO training handlers carry explicit `mro_type`, canonical `total_timesteps`, and
  `Idempotency-Key`. MRO detail/evaluation route `/rapp/mro/[rappModelId]`. MRO inference uses
  `200` cached-complete vs `202` async-poll semantics.
- Until product mapping is defined, MRO dataset selectors are not baseline-filtered/validated in
  the frontend and fall back to all tenant datasets when mobility metadata is missing.
- Browser-side MRO training only sends `Idempotency-Key` when
  `NEXT_PUBLIC_ENABLE_MRO_IDEMPOTENCY_HEADER=true`, because the local gateway CORS allow-list
  currently omits that header.
- Keep `/infer`, `/compare`, and `/rapp/mro/[rappModelId]` on the shared enterprise workspace
  pattern: sticky context bar, one workflow banner, summary-first outcome framing, tabs for
  drill-down evidence.

### 4.4b Device Management — NybSys NanoLink (`/devices`)

- New top-level **"Add Device"** side-nav entry (`lib/app.config.ts`, id `devices`) → `/devices`.
  Always visible (consistent with the ungated `/custom-pm-ingestion` nybsys flow); backend still
  enforces the `nybsys` feature flag via `403`.
- Operator API consumed via `useNybsysDeviceService` (`lib/api/services/nybsys-devices.ts`),
  gateway-routed under `/tenants/{tenant_id}/custom/nybsys/**` (edge-devices, devices, commands,
  events, kpis, health, recommendations). This is **separate** from `useNybsysService` (Custom
  Upload synthesis) — do not merge the two.
- Routes (flat; `tenantId` from store, not in the URL):
  - `/devices` — landing: edge-device cards + "Add edge device" modal (one-time enrollment-token
    reveal) + NanoLink device table (15s poll).
  - `/devices/edge/[edgeId]` — edge detail: status, regenerate-key (token reveal), cascade delete
    (confirm).
  - `/devices/[deviceId]` — device shell with `Config | Monitoring | Optimise` tabs.
- Config tab edits the **managed-param catalogue mirrored client-side** in
  `lib/nybsys/managed-params.ts` (no backend endpoint exposes param metadata; `/config` returns
  values only). Keep this list in sync with smo-sim `app/services/nybsys/managed_params.py` and the
  agent snapshot catalogue. Client-side bounds/enum validation; read-only params disabled; diff →
  `createCommand`; command history auto-polls (5s while pending/dispatched) and treats
  `rolled_back` as a **terminal** status from the agent ack contract. An empty or partial `/config`
  result is explicitly labelled and refreshable — never present blank controls as a confirmed empty
  device configuration.
- Current values are read-only, last-confirmed edge snapshots; Proposed updates are a separate
  draft map and the only fields sent in a configure command. Firmware-dump "observed" values must
  never appear as live data. When the watched command settles, Config reloads only after the result
  is available; an applied result clears the proposal, a failed proposal remains visible beside its
  actual read-back for correction.
- Monitoring tab: severity-filtered event timeline (10s), health rollup card (15s), full KPI chart
  set (30s) reusing `components/inference/charts/LineChart.tsx` with a `<90s` freshness badge.
- Optimise tab: mode selector (off|approval|auto, persisted via `setOptimizeMode`) +
  recommendation cards with approve/reject (20s poll).
- Live polling uses `hooks/useIntervalPoll.ts` (pauses on tab-hidden). Shared presentation helpers
  live in `lib/nybsys/device-ui.ts`; badges in `components/devices/badges.tsx`.

### 4.5 Copilot

- Health, agents, sessions, messages, query create/update.
- Session-first send sequence (see §6).
- Optional Auto agent mode that omits `agent_id` on query create/update.
- Public agent picker populated only from `GET /copilot/agents`, including `data_generation_agent`.
- Session/message cursor pagination; edit-and-rerun; hidden backend response-agent label mapping;
  action-card rendering.
- Route remains `/copilot`, but user entry stays in the top bar, not side navigation.

### 4.6 Error Logs

- Module-based log retrieval and resolve actions; tabs for Baseline/BDT/RAPP/Utils.
- Keep Error Logs out of non-Cloudly side navigation while preserving the route and handlers.

### 4.7 Administration

- Platform admin organization management via `/admin/tenants`.
- Tenant admin user management via `/tenants/{tenant_id}/users`.

## 5. How to Implement Changes

1. Identify the domain owner module in `components/<domain>` and `lib/api/services/<domain>.ts`.
2. Add or update typed contracts in `types/*`.
3. Implement the API handler in the service module first.
4. Wire UI behavior in the feature component/page.
5. Ensure loading, empty, success, and failure states are explicit.
6. Confirm role and tenant constraints.
7. Keep customer-facing copy/labels aligned with `lib/ui-content.ts` and
   `artifacts/ui-label-mapping.md`.
8. Update docs in `artifacts/` for route/contract/UI changes.
9. Keep TS/TSX formatter-clean; `next build` inside Docker runs linting and will fail container
   builds on Prettier regressions in shared UI components.

### 5.1 Branch Sync Procedure

When the branch diverges from `main`:

1. `git fetch origin main`
2. `git rebase origin/main`
3. resolve conflicts without dropping intended feature behavior
4. update docs and `commit.md` when behavior/contracts changed
5. push with `--force-with-lease` to update the remote feature branch

## 6. Copilot-Specific Contract

On first prompt in a new conversation:

1. `POST /copilot/sessions` with the query.
2. Read `session_id`.
3. `POST /copilot/agents/query` with `session_id` and the same query.
4. Reuse `session_id` for follow-up turns.

Required behaviors:

- Recover from missing sessions/messages (`404`); surface access denied (`403`).
- Persist the selected explicit agent by tenant where possible, while clearing cached IDs that
  disappear from the backend agent list.
- Keep agent selection optional; when Auto is selected, omit `agent_id` from `POST` and
  `PATCH /copilot/agents/query`.
- Render assistant turns safely even when payloads use hidden internal agent IDs such as
  `reactive_agent` or `generic_agent`.
- Respect desktop right-panel and mobile full-screen-sheet behavior.
- Keep `CopilotShell`, `CopilotPanel`, and `CopilotSessionList` aligned on `sessionSearchValue`
  and `onSearchChange`.
- Run `npm run build` after Copilot UI composition changes to catch type-contract regressions.

## 7. Brand and UX Constraints

- Reuse existing tokens and shared primitives.
- Keep the UI enterprise-grade, non-technical, and demo-friendly; prefer product language over
  backend terminology on primary surfaces.
- Keep trial mode visually explicit with restrained bannering and a clear sales conversion path,
  rather than surfacing backend-style permission errors as the primary UX.
- Keep trial upgrade CTAs in enterprise language and route them through the configured or default
  WhatsApp sales link.
- Keep data-heavy views scannable; keep inference/simulation routes guided (verdict first,
  validation second, diagnostics last).
- Use the existing page-header pattern (clear title + short layman-friendly subtitle) on major
  pages; use shared table patterns for CRUD; require explicit confirmation for destructive actions.
- Reuse existing brand assets from `public/` before adding new ones.
- Accessibility: visible focus styles, keyboard path support, aria labels for icon-only buttons.

See also: `artifacts/frontend/Brand.md` and `artifacts/frontend/UI_Design.md`.

## 8. Definition of Done for Agent Work

A change is complete only when:

1. Handler and UI are both implemented and wired.
2. Tenant and role behavior is correct.
3. Error handling is explicit and user-visible.
4. Route and contract docs are updated.
5. Lint/type checks are clean or deviations are documented.
6. For Docker/delivery work, `docker compose up --build` completes cleanly after local checks.

## 9. Documentation Update Policy

When changing functionality, update at least:

- `artifacts/frontend/route.md` for route/endpoint changes.
- `artifacts/frontend/API_Contracts.md` for payload/envelope/error changes.
- `artifacts/frontend/UI_Design.md` for user-visible behavior changes.
- `artifacts/frontend/ui-label-mapping.md` for customer-facing label/navigation terminology changes.
- `artifacts/frontend/Brand.md` when shell, visual hierarchy, or asset usage changes.
- `artifacts/frontend/Gap_Analysis.md` if requirement coverage changed.

Do not frontend-edit `artifacts/design/openapi.yaml` or `artifacts/copilot/*_openapi.yaml` for UI-only work;
those are backend-synced references.

## 10. Backlog Priorities (Current)

1. Add a unified envelope and status error-mapping utility.
2. Introduce a test runner and baseline automated coverage.
3. Align the UE dataset create endpoint with the runbook contract if backend supports
   `/ue-data/datasets`.
4. Add BDT training `Idempotency-Key` header support.

## Trial signup contract

The full public trial-signup request/response JSON examples and the `trial_user` authorization
table live in the root handover — do not duplicate them here:

- [trial-signup contract → API_Contracts.md §7.0](./API_Contracts.md) — `POST /v1/trial/signup`
  request/response, error-code table, `GET /v1/admin/trial-signups` shape, `trial_user`
  authorization rules, required frontend flow, and acceptance checks.

Backend enforcement of these rules is documented in `artifacts/design/LLD.md` §2 (Gateway `TrialWriteGuard`,
trial signup route, `trial_user` role).
