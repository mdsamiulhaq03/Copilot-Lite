# High-Level Design (HLD)

## 1. Purpose

This document defines the high-level frontend architecture for `maveric_platform_frontend`, including how UI domains map to backend microservices and shared platform contracts.

## 2. System Context

The frontend is a Next.js App Router application that:

- Uses Cognito for authentication.
- Stores auth and tenant scope in a persisted Zustand store.
- Calls backend APIs through a gateway base URL (`/v1`), primarily under tenant scope (`/v1/tenants/{tenant_id}/...`).
- Renders an enterprise SaaS-style workspace branded around Operations Overview, Network Setup, Digital Twin, Network Optimisation, administration, and Copilot, while preserving the underlying technical routes for baseline, SMO, BDT, rApp, infer, and compare flows.

## 3. Architecture Principles

- Tenant-first API routing.
- API envelope parsing as the default response contract.
- Role-aware navigation and route gating.
- Presentation-layer renaming is centralized and non-breaking.
- Reusable table/modals patterns for CRUD-heavy workflows.
- Polling-based handling for async model inference/training status.
- Progressive enhancement for responsive and mobile layouts.

## 4. Logical Architecture

```text
+--------------------------------------------------------------+
| Next.js App Router UI                                        |
|  - app/(auth)                                                |
|  - app/(dashboard)                                           |
+----------------------------+---------------------------------+
                             |
                             v
+--------------------------------------------------------------+
| Frontend Core                                                 |
|  - API clients: ApiClient, CopilotClient                     |
|  - State: Zustand slices (auth, tenant, data, ui, users)     |
|  - Presentation mapping: app.config + ui-content             |
|  - Providers: StoreProvider, ApplicationProvider             |
|  - Shared UI primitives: shadcn + Tailwind v4                |
+----------------------------+---------------------------------+
                             |
                             v
+--------------------------------------------------------------+
| Gateway + Services                                             |
|  /admin/* (platform admin)                                    |
|  /tenants/{tenant_id}/* (tenant-scoped services)              |
|    - baselines / ue-data / utils / custom                     |
|    - bdt                                                      |
|    - rapps / compare / infer                                  |
|    - logs                                                     |
|    - copilot                                                  |
+--------------------------------------------------------------+
```

## 5. Frontend Domain Modules

- **Auth and Tenant Entry**
  - Organization lookup (`/tenants/lookup`) then Cognito hosted flow.
- **Platform Admin**
  - Organization CRUD via `/admin/tenants`.
- **Tenant User Management**
  - User CRUD via `/tenants/{tenant_id}/users`.
- **Network Setup**
  - Customer-facing grouping for topology, mobility data, and custom upload.
  - Backed by baseline, UE dataset, utils, and Nybsys custom ingestion routes without route changes.
- **Digital Twin**
  - Customer-facing label for BDT training, management, and simulation.
- **Network Optimisation**
  - Customer-facing label for rApp model management, contextual `Run Model` execution, MRO detail, and `Compare Models`.
- **Model Execution and Comparison**
  - Day-scope model evaluation and cross-model comparison.
  - Shared Non-MRO operator recommendation contract for ES/LB/CCO (`tick + items[{cell_id, el_degree, on_off}]`), reused for day-scope `per_tick_recommendations` and raw `tilt_by_cell` diagnostics.
- **Error Logs**
  - Module-specific logs, resolve actions, and diagnostics for Cloudly internal admin workflows.
- **Copilot**
  - Session-first assistant workflow with tenant-scoped agent/session/message routes and top-bar entry.

## 6. Runtime Composition

### 6.1 Global Providers

- `StoreProvider`
  - Initializes auth state from token storage.
- `ApplicationProvider`
  - After tenant is known, preloads baseline, UE datasets, BDT list, rApp list and models.
  - Presentation labels shown on top of that preload are supplied separately by shared UI content and do not alter the fetched technical resources.
  - Nybsys custom ingestion stays page-local because availability is feature-flagged by backend `403` and should not be fetched on every dashboard load.

### 6.2 Shell

- `DashboardShell`
  - Auth guard for dashboard surfaces.
  - Sidebar + topbar layout.
  - Redirects unauthenticated users to `/select-tenant`.

### 6.3 Navigation and Roles

- Sidebar items are filtered by:
  - User role (`cloudly_admin`, `tenant_admin`, `tenant_user`).
  - Tenant scope availability.
- Sidebar IA groups major surfaces as `Dashboard`, `Network Setup`, `Digital Twin`, `Network Optimisation`, and `Administration`.
- Copilot remains available as a top-bar entry and is intentionally not duplicated in side navigation.
- Error Logs remain route-accessible but are only surfaced in side navigation for Cloudly internal admins.

## 7. API Integration Model

Two client patterns are used:

- `ApiClient`
  - Generic REST access, envelope extraction (`data`), default auth header injection.
- `CopilotClient`
  - Copilot-specific client with flexible envelope normalization, cursor normalization, and typed status mapping.
- `ui-content.ts`
  - Shared customer-facing label and model-name mapping used by navigation, tables, and page headers.

## 8. Security and Tenant Isolation

- Bearer token is attached from session token storage.
- Tenant ID is sourced from authenticated claims and Zustand tenant slice.
- Copilot and tenant routes are only invoked when tenant context exists.
- Auth callback validates tenant in state vs tenant in token claims.

## 9. Non-Functional Requirements

- **Availability:** Degraded and unavailable service states surfaced in UI (notably Copilot).
- **Resilience:** Polling and refresh patterns for async workflows.
- **Maintainability:** Feature modules under `components/*`, typed services in `lib/api/services/*`.
- **Usability:** Reusable table system for filter/search/sort/pagination across domains, plus page headers and navigation labels that are understandable to first-time non-technical users.
- **Accessibility:** Keyboard-accessible controls and aria labels for key controls (for example Copilot close/send).

## 10. Deployment View

- Local development: `npm run dev`.
- Containerized local/prod variants:
  - `local.Dockerfile` for compose-driven local runtime.
  - `Dockerfile` with runtime placeholder replacement for `NEXT_PUBLIC_*` variables.
- Auth token exchange route available at `/api/auth/token` for server-side exchange mode.

## 11. High-Level Risks

- Partial mismatch between runbook target routes and implemented routes in a few modules.
- Test runner not configured; current quality checks rely on lint/type-check/manual validation.
- Some legacy or placeholder routes exist (`/opex-estimate`, `/proposal`).

Detailed risk and gap tracking is in [Gap_Analysis.md](./Gap_Analysis.md).
