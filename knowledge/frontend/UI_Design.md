# UI Design Specification

## 1. Purpose

This document describes the behavior and UX contract for all implemented frontend pages.

## 2. Global Layout

Dashboard pages use a shared shell:

- Topbar with logo, notifications, Copilot entry, and user menu.
- Left sidebar with role-filtered grouped navigation.
- Main content area with consistent padding and section spacing.

Shared patterns:

- Page header via `PageTitle`, pairing a clear title with a short layman-friendly subtitle on major pages.
- CRUD-heavy sections via `GenericDataTable` wrappers.
- Confirmation dialogs for destructive actions.
- Toast notifications for async results.
- Sidebar organization label prefers the validated tenant display name captured during login and only falls back to raw tenant ID when no display name is available.
- Sidebar information architecture is **sectioned** (`SIDEBAR_DATA: SidebarSection[]` in `lib/app.config.ts`, rendered one `SidebarGroup` per section in `nav-main.tsx`) and mirrors the product flow `Ingest -> Network Digital Twin -> Optimization -> Policy & Guardrails -> Actuator Adapter`:
  - `Dashboard` (`/`, unlabeled section).
  - **Intelligence**: `Ingest` (`/ingest`, a navigable parent with children `Topology & Configuration` `/baseline`, `Training Data` `/smo`, `PM Upload` `/custom-pm-ingestion`), `Network Digital Twin` (`/bdt`), `Optimization` (`/rapp`), and `Policy & Guardrails` (`/policy`). (updated 2026-08-06: `Compare Models` is no longer a sidebar child of the twin — `/compare` redirects to `/rapp?tab=models&view=compare`, frontend `fd40b1e`.)
  - **Actuators**: `Connections` (`/actuators`).
  - `Administration` and `Logging & Monitoring` keep their previous grouped behavior and role gating.
- Section labels render as uppercase `SidebarGroupLabel` text, hidden in icon-collapsed mode; items carry the navigation.
- Items may declare `matchPrefixes` (extra pathname prefixes that mark them active): `/infer` lights `Network Digital Twin`, `/devices/**` lights `Connections`. Active top-level links set `aria-current="page"`.
- Topbar brand strings read `CloudlyNet` with the subtitle `RAN intelligence by Cloudly`.
- `Copilot` remains in the top bar rather than the side nav.
- `Error Logs` remain route-accessible but only appear in side navigation for Cloudly internal admins.

## 2.1 Shared Table and Filter-Rail Pattern

Purpose:

- Keep data-library pages visually consistent across Network Digital Twin, Optimization, administration, and upload-monitoring surfaces.
- Avoid page-specific filter chrome when the shared table pattern already defines the interaction model.

Composition:

- Search remains the primary left-aligned control and should scan naturally before any secondary controls.
- Secondary controls such as status filters, type tabs, and refresh actions live in the same filter rail and align to the right on wider viewports.
- Controls wrap onto additional rows on smaller screens instead of collapsing into truncated labels or icon-only maintenance actions.
- `Select` controls keep stable widths so status terms such as `In Progress` and `Training` remain legible.
- Refresh actions remain explicit text buttons, not icon-only controls, on library-management pages.

Behavior:

- Search must filter the currently loaded library data without changing route state.
- Status or type filters should preserve the shared table rhythm: change filter, refresh dataset if required by the page contract, then render the filtered result set inside the same table frame.
- Filter rails should be implemented through shared `GenericDataTable` / `ControlledGenericDataTable` hooks and props so BDT and rApp libraries do not drift into bespoke layouts.
- JSX inside these shared control rails must stay formatter-clean because the production Docker build executes `next build`, which includes linting and fails on TS/TSX Prettier violations.

## 2.2 `NotEnabledDialog` Pattern

Purpose:

- One shared, honest way to explain a capability that exists in the IA but is not enabled in this deployment, without "coming soon" promises or compliance claims.

Composition (`components/common/NotEnabledDialog.tsx`):

- shadcn `Dialog` (not `AlertDialog`; nothing destructive is confirmed), `sm:max-w-[420px]`.
- Title `Not enabled` with a muted `Lock` icon.
- Description defaults to "This actuator adapter is not enabled in this deployment. Contact your administrator."; consumers may pass a variant message.
- Footer holds a single outline `Close` button — no primary action, because there is no next step to promote. Esc / overlay dismiss stay enabled.

Consumers:

- The five disabled adapter tiles on `/actuators` (default message).
- The `Connect RIC` button on `/rapp` (message: "RIC integration is not enabled in this deployment. Contact your administrator.").
- Triggers are real focusable `<button>`s with `aria-haspopup="dialog"`, never `disabled` attributes, so they can explain themselves.

## 3. Authentication and Entry Pages

Dev auth-bypass mode (local e2e only):

- `NEXT_PUBLIC_AUTH_MODE=bypass` is centralized in `lib/auth/bypass.ts`: the login / tenant-select flow short-circuits into the dashboard, the store initializes with a synthetic `tenant_admin` session (`NEXT_PUBLIC_DEV_TENANT_ID`, default seeded trial tenant `00000000-0000-0000-3029-000000000001`), and `ApiClient` sends no `Authorization` header — the gateway's `DEV_BYPASS_JWT` fabricates claims server-side.
- The sections below describe the normal hosted-Cognito mode; bypass never ships to production.

## 3.1 `/select-tenant`

Purpose:

- Collect organization name/slug before hosted login redirect.
- Present the entry experience with enterprise workspace messaging aligned to `artifacts/marketing.md`, while preserving the existing tenant-first auth flow.

Composition:

- Responsive split auth shell with brand context on larger screens and the tenant form as the primary action surface.
- Reuse `Logo-Horizontal.png` for the auth identity mark and `Logomark-on dark bg.png` as a subtle background accent.

Primary interactions:

- Tenant lookup by name, then slug fallback.
- Persist validated organization display name for post-login dashboard rendering.
- Cognito redirect start on success.
- Error banners for missing tenant or config issues.
- Keep customer-facing copy focused on organization access and workspace continuity instead of backend terms like tenant routing or hosted auth internals.

## 3.2 `/trial`

Purpose:

- Provide a self-service trial signup surface outside the authenticated shell.
- Reuse the same brand system and hosted Cognito bootstrap patterns as the existing auth entry flow.

Composition:

- Dark enterprise hero with product-capability framing grounded in `artifacts/marketing.md`.
- Minimal signup form collecting name, work email, phone, company, and optional designation.
- Returning-user sign-in action inside the access card so existing trial users can enter the workspace without resubmitting signup details.
- Success state showing `user_email`, `temp_password`, and a CTA to continue into hosted sign-in using returned `tenant_id`.

Primary interactions:

- Submit `POST /v1/trial/signup`.
- Map `409`, `403`, `429`, and `502` into polished trial-specific error messaging.
- Allow returning users to start hosted sign-in directly from `/trial` by resolving the shared trial tenant and reusing the Cognito bootstrap.
- Prefer returned `tenant_id` for hosted sign-in bootstrap and fall back to `GET /v1/tenants/lookup?slug=netai-trial` only if needed.

## 3.3 `/auth/callback`

Purpose:

- Complete authorization code exchange.

Primary interactions:

- Validate callback `state`.
- Exchange code for tokens.
- Validate tenant claim alignment.
- Restore tenant display name from the validated auth state before redirecting into the dashboard shell.
- Initialize auth state and redirect to dashboard.

## 3.4 `/signup`, `/forgot-password`, `/reset-password`, `/auth/auth-code-error`

Purpose:

- Hosted identity flow support and fallback messaging.

## 4. Dashboard Home

## 4.1 `/`

Purpose:

- Operational summary and quick entry into optimisation model management.

Composition:

- Statistics widgets.
- `TrainRappWidget` quick training form for standard workspaces.
- `TrialModeBanner` plus `TrialExperienceWidget` for `trial_user` workspaces.
- Recent model table (`RAPPDataTable` short mode).
- CTA cards for key modules.

Trial-specific behavior:

- Trial mode keeps compare, model-run, and Copilot flows prominent.
- Trial mode does not surface quick training as the primary dashboard CTA.
- Trial mode banners include a clear `Book a Call` CTA for teams that want a dedicated workspace provisioned by Cloudly.

## 5. Ingest

## 5.0 `/ingest`

Purpose:

- One landing page that answers "what data does CloudlyNet have, and where do I put more"; the navigable parent for the ingest child pages.
- Teaches the product mental model once via the pipeline rail; other pages stay quiet.

UI elements:

- `PipelineRail` (`components/common/PipelineRail.tsx`): a static one-line strip of the product flow `Ingest -> Network Digital Twin -> Optimization -> Policy + Guardrails -> Actuator Adapter`, current step rendered as a primary-tinted pill; non-interactive, horizontally scrollable when cramped.
- Three `CategoryCard`s (`components/ingest/CategoryCard.tsx`) on an FCAPS-derived split:
  - Performance (PM): `PM counters`, count from `listNybsysUploads`, CTA `Open PM Upload` -> `/custom-pm-ingestion`.
  - Configuration (CM): `Topology & configuration`, count from `listBaselines`, CTA `Open Topology & Configuration` -> `/baseline`.
  - Fault (FM): `Fault data`, honest empty state (`No sources` badge, no CTA, inert card) — no fault sources exist yet.
- Full-width training-data band (horizontal `CategoryCard`): `Training data (UE measurements)`, count from `listUeDatasets`, CTA `Open Training Data` -> `/smo`. Kept apart from PM/CM/FM on purpose: these are training inputs, not PM counters.

Key states:

- Counts are decoration, not blockers: each card loads, empties (`No ... yet.` with CTA still enabled), or degrades to `Count unavailable` independently; the page never hard-fails on a count fetch.
- Trial workspaces see the page fully (read-only counts); source pages keep their existing trial banners.

## 5.1 `/baseline`

Presented as `Topology & Configuration` (Ingest child).

Purpose:

- Create and manage topology artifacts used across digital twin and optimisation workflows.

UI elements:

- Header with service health icon.
- Create modal (`AddBaselineModal`) with:
  - ID and description fields.
  - Toggle for generation via utils vs file upload.
  - File pickers for topology/config/training CSVs.
- Table (`BaselineDataTable`) with search, sort, and delete, using customer-facing `Topology` copy while preserving baseline contracts.

Key states:

- Loading and upload progress (button-state based).
- Validation messages (Zod + React Hook Form).
- Delete confirmation modal.
- `trial_user` keeps the page readable but cannot create or delete topology records; banner explains full-platform unlock.

## 5.2 `/smo`

Presented as `Training Data` (Ingest child); H1 `Training Data`.

Purpose:

- Create and manage the synthetic UE measurement (training) datasets.

UI elements:

- Create modal (`AddSMOModal`) with:
  - Dataset ID and baseline selector.
  - Toggle for utils generation vs upload.
  - Dataset type selection for generated mode (`mro` vs `others`).
- Table (`SMODataTable`) with search and delete, using `Mobility Data` and `Mobility Dataset` terminology on primary surfaces.

Key states:

- Baseline list sorted by latest creation.
- Delete confirmation modal.
- `trial_user` keeps dataset review enabled while upload/generate/delete actions stay disabled.

## 5.3 `/custom-pm-ingestion`

Presented as `PM Upload` (Ingest child); H1 `PM Upload`.

Purpose:

- Start and monitor Nybsys PM counter CSV uploads that create derived topology and mobility data artifacts. (updated 2026-08-06: the conversion flow is retired — the page is now the vendor-neutral `PmUploadPage` posting `POST /ingest/uploads` + polling `GET /ingest/jobs/{id}` into the canonical PM store; no derived topology/mobility artifacts. It also hosts the `IngestAdaptersCard` source-adapter selector, moved here from `/data`. The `Nybsys*` component family below is unmounted LEGACY, EPIC-11 S1; frontend `dff7e05`.)

UI elements:

- `NybsysUploadForm` with:
  - upload ID
  - multi-file raw PM CSV picker
  - `rng_seed`
  - `samples_per_cell`
  - read-only preview of derived topology and mobility dataset IDs
- `NybsysUploadStatusCard` with:
  - queued/processing/completed/failed state messaging
  - polling indicator
  - read-only derived topology and mobility dataset IDs
  - raw file list
  - plain delete and delete-with-derived-cascade confirmations
- `NybsysUploadsTable` with search, inspect action, and queue refresh

Key states:

- Runtime `403` renders a feature-disabled card instead of a generic toast-only failure.
- Raw CSV files upload to S3 before backend submission.
- `uploading` renders as accepted/queued; `processing` renders as active processing.
- `completed` exposes navigation actions back to topology and mobility data management pages.
- `failed` shows the backend `error` string verbatim and leaves retry user-driven via a new upload ID.
- `trial_user` sees a locked-state card instead of the upload form and cannot delete uploads from the status panel.

## 6. Network Digital Twin and Optimization

## 6.1 `/bdt`

Presented as `Network Digital Twin`; H1 `Network Digital Twin`.

Purpose:

- Create and manage digital twins for the network.

UI elements:

- Train modal (`TrainBDTModal`) using selected baseline/topology.
- Table (`BDTDataTable`) with:
  - Search across digital twin ID, description, and topology/baseline lineage text already present in the row payload.
  - Status filter using the shared select control with:
    - `All Status`
    - `Queued`
    - `Training`
    - `In Progress`
    - `Ready`
    - `Failed`
  - `Refresh All` action kept adjacent to the status filter inside the shared table rail.
  - Row actions:
    - open digital twin simulation
    - refresh an individual digital twin
    - delete when workspace permissions allow it

Interaction notes:

- The Digital Twin page should feel like a managed library rather than a dashboard tile grid.
- Search is client-side against the currently loaded BDT dataset.
- Changing the status filter preserves the current page shell and reuses the same table component rather than remounting the page.
- `Refresh All` reloads the visible Digital Twin collection and keeps the current filter selection intact.
- On smaller screens, the filter rail may wrap but should retain the order: search first, then status filter, then refresh.

Trial-specific behavior:

- `trial_user` can open ready digital twins for simulation and refresh model status.
- Trial mode disables create/delete actions and explains the full-platform upgrade path.

## 6.2 `/bdt/models/[bdtId]/infer`

Purpose:

- Submit digital twin simulation runs and monitor async completion.

UI elements:

- `BdtInferenceForm`:
  - model id (read-only)
  - mobility dataset selector
  - tick input (0-23)
  - optional topology override
- `BdtInferenceRunStatus`:
  - run id, status badge, timestamps, error surface
  - polling indicator while run is active
- `BdtInferencePlot`:
  - scatter plot rendered from `result.plot.groups`
- `BdtInferenceMetrics`:
  - simulation metric
  - key-value metrics and text summary

Async behavior:

- Starts run via `POST /bdt/models/{bdt_id}/infer`.
- Polls `GET /bdt/models/{bdt_id}/infer/{run_id}` every 4s.
- Stops at terminal states `completed` or `failed`.

## 6.3 `/rapp`

Presented as `Optimization`; H1 `Optimization` (US spelling per marketing canon).

Purpose:

- Create, manage, and run optimisation models.

UI elements:

- Header action row ordered `[Connect RIC] [Compare Models] [Create Model]`; primary stays `Create Model`. (updated 2026-08-06: replaced by URL-synced primary tabs `Use CloudlyNet Models` | `Connect to RIC` (`?tab=models|ric`); under `models`, `?view=library|compare` switches between the library and the embedded `Compare Models` view; `Create Model` lives inside the models tab. Frontend `fd40b1e`.)
- `Connect RIC` (outline button, `RadioTower` icon) opens `NotEnabledDialog` with the RIC message — integration framing only, no RIC backend call and no other RIC copy on the page. (updated 2026-08-06: the RIC entry is now the `Connect to RIC` tab rendering `RicConnectPanel` — still no RIC backend call.)
- Train modal/widget (`TrainRappModal`, `TrainRappWidget`) requiring:
  - Model ID
  - Optimisation type
  - topology selector
  - digital twin selector filtered by topology
  - mobility dataset selector filtered by topology for non-MRO flows
  - MRO-only controls:
    - `RL (Recommended)` / `Simple`
    - `total_timesteps`
- Table (`RAPPDataTable`) with:
  - Optimisation type tabs
  - Status filter
  - Refresh all
  - MRO metrics summary column
  - Row actions:
    - MRO detail/evaluation deep-link for Mobility Optimisation rows
    - contextual `Run Model` deep-link for non-MRO ready rows
    - refresh training status
    - delete

Trial-specific behavior:

- `trial_user` can still open `Run Model`, MRO detail, compare, and refresh actions.
- `trial_user` cannot open create-model training flows or delete models.

MRO-specific behavior:

- training form blocks non-mobility datasets for MRO
- training form shows mobility-compatible datasets for MRO even when dataset-to-baseline linkage is absent
- when dataset metadata does not identify any mobility-compatible options, the training form falls back to all tenant datasets and keeps mobility validation at submit time
- selected MRO mode persists across refresh via browser storage
- MRO submit routes to model detail page after success

## 6.4 `/rapp/mro/[rappModelId]`

Purpose:

- Show MRO model lineage/metrics and run async simulator-based evaluation.
- The route now uses a guided mobility-simulation workspace while preserving the existing technical contract.

UI elements:

- Sticky context bar with mobility-simulation breadcrumbs plus baseline, digital twin, and dataset context chips.
- Workflow banner that explains the simulation path in business language before detailed controls appear.
- Model detail card with:
  - status badge
  - topology / digital twin / mobility dataset lineage
  - MRO metrics when present
- Workflow stepper for `Configure`, `Run`, and `Review`
- `MroInferenceForm`:
  - `Reference Baseline`
  - `Digital Twin`
  - `Mobility Dataset`
  - `Reference Hysteresis`
  - `Reference TTT`
  - `Run Simulation` action
- `MroInferenceRunStatus`
- Outcome tab with:
  - completion/warning verdict card
  - predicted-vs-baseline parameter comparison
  - next-step guidance cards
- `MroParamSummary`
- `MroNetworkKpiGrid`
- `MroRappKpiGrid`
- `MroDeltaTable`
- `MroWarningsPanel`
- Diagnostics tab with execution record and technical metadata.

Trial-specific behavior:

- MRO evaluation stays available to `trial_user` because it is part of the demo-ready read/evaluate experience.

Async behavior:

- model status auto-refreshes until `ready` or `failed`
- MRO inference respects:
  - `200` immediate completed result rendering
  - `202` queued/running state with polling every 5s
- MRO dataset selection is not baseline-filtered until product mapping is defined and falls back to all tenant datasets when mobility metadata is missing
- retry button resubmits the last failed payload

## 8. Administration

## 8.1 `/organizations`

Purpose:

- Manage customer organizations.
- Review trial leads captured through the public onboarding page.

UI elements:

- Existing organization management table and add-organization modal.
- `TrialSignupsTable` with paginated `page` / `page_size` controls for `/admin/trial-signups`.
- `MroDiagnosticsDrawer`

## 7. Model Execution and Comparison

## 7.1 `/infer`

Purpose:

- Single-model ES/LB/CCO day-scope execution and diagnostics.
- Route is presented to users as `Run Model` and is reached contextually from Optimization rather than through a dedicated sidebar item; the sidebar lights `Network Digital Twin` on `/infer` via `matchPrefixes`.

Primary controls:

- Model selector.
- Mobility dataset selector.
- Day selector.
- `Run Review` action.

Major result surfaces:

- Sticky context bar with baseline, model, optimisation focus, day, and run/verdict badges.
- Workflow banner plus page-level `Compare Models` CTA (updated 2026-08-06: label was `Compare Outcomes`; links to `/rapp?tab=models&view=compare`, frontend `fd40b1e`).
- Scenario-selection card with selected model, dataset, day, and contextual model lineage strip.
- Summary verdict card with warnings, cache/fresh-run status, and headline KPI cards.
- Tabbed review workspace:
  - `Summary`
    - worst-hour table
    - operating-context cards
    - hourly guardrail / signal / value charts
  - `Recommendations`
    - selected-hour recommendation metrics
    - recommendation table
    - top congested cells
  - `Validation`
    - KPI threshold table
    - signal trend and histograms
    - preserved selected-hour snapshot with:
      - recommendations
      - KPI payload
      - serving-cell load
      - raw RSRP/SINR summaries
    - cell x hour heatmap
  - `Diagnostics`
    - execution record
    - metadata table
    - per-hour KPI payload with expand/collapse behavior
- Compatible fallback view when a tick-scope payload is returned on the day route.

Async behavior:

- Starts infer run.
- Polls until terminal status.
- Shows compatibility hints for baseline mismatch errors.
- MRO is intentionally excluded from this route.
- The selected-hour snapshot intentionally preserves the `e7894119cb4674aed088bff514af31426d714f2d` cleanup boundary and does not reintroduce separate selected-hour cell-state or `tilt_by_cell` tables.

## 7.2 `/compare`

(updated 2026-08-06: `/compare` is no longer a page — it server-redirects to `/rapp?tab=models&view=compare`, where `InferenceCompare` renders as the embedded `Compare Models` view. The controls and result surfaces below still describe that embedded view. Frontend `fd40b1e`.)

Purpose:

- ES/LB/CCO day-scope comparison of model A vs model B.
- Route is presented to users as `Compare Models`, a sidebar child of `Network Digital Twin`; also reachable from the `/rapp` header. (now false — see the note above)

Primary controls:

- Candidate model selector.
- Comparator model selector.
- Mobility dataset selector.
- Day selector.
- Model selectors allow any ready ES/LB/CCO pairing, including CCO as candidate or comparator.
- `Start Comparison` action with explicit same-baseline validation.

Major result surfaces:

- Setup state with centered comparison card and baseline mismatch guidance before any result is shown.
- Result workspace with candidate/comparator summary cards and a decision-summary hero.
- Tabbed comparison workspace:
  - `Summary`
    - Pareto scatter
    - worst-hour comparison
    - warning panels
    - recommended next steps
  - `Metric Detail`
    - segment switcher for guardrails, signal quality, and optimisation outcomes
    - overlay hourly charts
    - full delta table
  - `Risks`
    - deployment-review banner
    - candidate/comparator risk review
    - operational considerations
  - `Metadata`
    - model lineage
    - backend delta payload
    - flattened metadata tables for both models

Restrictions:

- MRO compare is intentionally not exposed on this page.

## 8. Copilot Experience

## 8.1 `/copilot`

Purpose:

- Tenant-scoped assistant with session memory, agent selection, and action cards.
- Agent selection remains optional; composer defaults to `Auto`.
- Entered from the top bar instead of the left navigation.

Desktop layout:

- Main context area on left.
- Right panel (`max-width ~440px`) with border-left.

Panel sections:

1. Header with availability badge and close action.
2. Agent picker with `Auto`, `Debugger Agent`, `Data Generation Agent`, and any other backend-returned public agents.
3. Session list with search/paging/rename/delete.
4. Message list with pagination controls.
5. Composer with editing mode and send controls.

Mobile layout:

- Right-side full-width sheet.

Keyboard behavior:

- `Esc` closes panel.
- `Enter` sends.
- `Shift+Enter` inserts newline.

Agent-selection UX:

- `Auto` omits `agent_id` on query create/update payloads.
- `Data Generation Agent` includes helper text for topology, traffic-load, mobility, and UE dataset guidance.
- Assistant bubble labels can show backend response agents even when they are not present in the picker list; internal `reactive_agent` and `generic_agent` render as an auto-routed assistant label.

Action metadata UX:

- Assistant action cards classify actions as read/mutating.
- Mutating actions require explicit confirmation click.
- Operation badges show `queued`, `running`, `completed`, `failed`.

## 9. Error Logs

## 9.1 `/error-logs`

Purpose:

- Cross-module operational error inspection for Cloudly internal admin workflows.

UI elements:

- Module tabs for `Baseline`, `BDT`, `RAPP`, `Utils`.
- Per-module refresh button.
- Expandable log cards with stack trace syntax highlight.
- Copy stack trace action.
- Resolve action for each log.
- Side-nav visibility is intentionally limited to Cloudly internal admins, even though the route remains available.

## 10. Admin and User Management

## 10.1 `/organizations`

Purpose:

- Cloudly admin organization lifecycle management.
- Presented as `Organization Management`.

UI elements:

- Add organization modal.
- Organization table with search and delete.
- Role guard wrapper.

## 10.2 `/users`

Purpose:

- Tenant admin user lifecycle management.
- Presented as `User Management`.

UI elements:

- Add user modal.
- User table with role badges and delete.
- Temp password modal on user creation response.
- Role guard wrapper.

## 11. Account Pages

## 11.1 `/account/profile`

- Read-only personal info card.

## 11.2 `/account/settings`

- Hosted password reset handoff.

## 12. Legacy and Placeholder Pages

- `/rapp/inference/[id]` redirects to `/infer` with query params.
- `/opex-estimate` and `/proposal` are currently placeholders with no functional UI.

## 13. Actuator Adapters — NybSys NanoLink Device Management

Side-nav entry **Actuators → Connections** → `/actuators`; page H1 **Actuator Adapters**. Always visible; backend enforces the `nybsys` feature flag with `403` (rendered as the feature-disabled card, same pattern as PM Upload). Reuses shared shell, tokens, `GenericDataTable`, dialogs, and `LineChart`. The old `/devices` landing is a redirect to `/actuators`; detail routes stay under `/devices/**` and keep `Connections` lit via `matchPrefixes`. (updated 2026-08-06: `/actuators` is now the adapter grid alone — the edge/device estate described below moved to the dedicated `/actuators/tr069` page, reached through the TR-069 tile; `/devices` now redirects there and breadcrumbs parent `/devices/*` under `TR-069 (CWMP)`. Non-TR-069 tiles open an adapter info dialog instead of `NotEnabledDialog`. Frontend `887a396`.)

### 13.1 `/actuators` (landing)

- **Featured TR-069 (CWMP) tile** (full-width glass panel): heading `TR-069 (CWMP)` + success `Active` badge, helper line "Manages NybSys NanoLink small cells through the in-agent ACS running on your edge device.", and the primary CTA **Add TR-069 (CWMP) Connection** — the relocated add-device flow, opening the existing `AddEdgeModal` unchanged.
  - Create returns an **enrollment token shown once** with copy-to-clipboard and a "won't be shown again" warning plus the `agent.yaml` paste hint (`TokenReveal`). Destructive/irreversible token semantics surfaced clearly.
  - Body 1 — **Edge connections**: relocated `EdgeDevicesPanel` status-card grid (headerless `bare` mode; cards link to `/devices/edge/[edgeId]`).
  - Body 2 — **Connected devices**: relocated `DevicesTable` (15s poll of `listEdges` + `listDevices`): Cell ID, Edge (name lookup), Health badge (🟢/🟡/🔴), RF Tx ✓/✗, SW Version, Last Inform (relative; red when >5 min stale), Optimize Mode chip; row → device shell. Poll failures keep last good data.
- **More adapters** grid: exactly five disabled `AdapterTile`s — `NETCONF/YANG (O1)`, `Open M-Plane`, `CBRS SAS Domain Proxy`, `NMS Northbound`, `A1 Policy (via Non-RT RIC)` — each a focusable button with a `Not enabled` badge that opens the shared `NotEnabledDialog` (§2.2). No "coming soon" wording and no O-RAN/RIC/SMO/NMS compliance claims anywhere on the page.

### 13.2 `/devices/edge/[edgeId]`

- Edge status, agent version, last-seen, created. **Regenerate key** (new one-time token) and **Delete** (cascade, explicit confirm dialog). Back-link `Back to Actuator Adapters` → `/actuators`.

### 13.3 `/devices/[deviceId]` (Config | Monitoring | Optimize tabs)

Supports `?tab=` deep-links (`config | monitoring | optimise`) as the initial tab — used by `/policy` row actions. Back-link `Back to Actuator Adapters` → `/actuators`.

- **Config**: each managed parameter presents a read-only **Current value** from the last confirmed agent snapshot and a separate **Proposed update** control. The former grey `observed` copy was firmware-reference guidance and is not used as a runtime value. Controls by dtype (number with min/max, toggle, enum select, text); read-only params have no proposal control; client-side bounds/enum validation appears inline. An explicit Refresh action reloads `/config`; an amber status explains zero or partial managed values so blank controls are never mistaken for confirmed empty device settings. **Push** sends only explicit proposal fields as a `configure` command; on terminal state, an applied command refreshes Current values while a failed command retains its proposal and shows `expected` versus actual device read-back. Command history auto-polls every 5s while any command is pending/dispatched, showing `pending → dispatched → applied/failed/rolled_back`, readback, mismatch, auto-rollback, and errors on expand.
- **Monitoring**: severity-filterable **event timeline** (10s poll, friendly event labels, severity colours), **health rollup card** (15s), and the **KPI chart set** (30s) — connected UEs, SINR, PRB utilisation, RRC success, throughput, CPU/memory — each with a `<90s` freshness badge.
- **Optimize** (tab value `optimise`): **Policy mode** selector (off | approval | auto, persisted immediately) with an auto-rollback guardrail note, and **recommendation cards** (20s poll) showing rationale, before→after change diff, expected deltas, confidence, and Approve/Reject with status transitions. Panel heading and toasts say "Policy mode", aligning with `/policy` language.

State conventions follow the rest of the app: explicit loading, empty, and error states; toasts via `sonner`; polling pauses when the tab is hidden (`hooks/useIntervalPoll.ts`).

## 14. Policy & Guardrails

### 14.1 `/policy`

Side-nav entry **Intelligence → Policy & Guardrails**; H1 `Policy & Guardrails`.

Purpose:

- The post-connection view over connected radios: set the operating policy per device, see the guardrail model once, and jump into config/recommendation approval. (updated 2026-08-06: policy mode is no longer per-device — `/policy` carries ONE tenant-wide loop mode plus the guardrail editor (`LoopPolicyEditor`, `GET`/`PUT /ndt/loop/policy`). The device Optimize tab shows that mode read-only, `PATCH /custom/nybsys/devices/{id}/optimize-mode` returns `410`, and smo_sim's device self-optimizer reads `loop_policies.mode`. Frontend `887a396`, smo_sim `5d31d65`.)

UI elements:

- **Policy mode explainer strip**: three quiet cards defining the modes once so the table stays dense: (updated 2026-08-06: strip removed with the per-device table — mode explanation now lives inside `LoopPolicyEditor`)
  - `Off` — "CloudlyNet observes only. No changes are proposed for this device."
  - `Approval` — "Every recommended change waits for an operator to approve or reject it."
  - `Autonomous` — "Approved change types apply automatically, and auto-rollback reverts any change the device read-back does not confirm."
- `PolicyDeviceTable` (`components/policy/PolicyDeviceTable.tsx`): same data source as `/actuators` (`listDevices` + `listEdges`, 15s poll) with a policy-oriented column set — Cell ID (mono), Edge, Health badge, **Policy** (existing `OptimizeModeBadge`), Last Inform (relative, red when stale), and two ghost icon row actions with aria-labels deep-linking `/devices/{id}?tab=optimise` and `/devices/{id}?tab=config`. (updated 2026-08-06: the `Device policies` section is gone — `PolicyDeviceTable` is unmounted LEGACY, EPIC-11 S3)

Key states:

(updated 2026-08-06: the table states below applied to the removed device table; the page no longer polls devices.)

- Loading: explainer strip renders immediately; table area shows skeletons.
- Empty: centered block — "No TR-069 (CWMP) devices connected yet." with an outline `Open Actuator Adapters` CTA → `/actuators`.
- Error: poll failures keep last good data; backend `403` renders the feature-disabled card (same pattern as §13).
- No per-row pending-recommendation counts in this pass: `getRecommendations` is per-device and no batch endpoint exists yet (tracked follow-up).
