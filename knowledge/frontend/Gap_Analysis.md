# Gap Analysis: Runbook vs Current Frontend

## 1. Scope

This analysis compares the frontend runbook requirements (2026-02-28 context) against the current implementation.

## 2. Summary

- Copilot session-first flow is implemented and aligned.
- Copilot agent selection now defaults to Auto, uses the backend public-agent list, and safely renders hidden backend response-agent IDs.
- Core Baseline/SMO/BDT/rApp management is implemented.
- Enterprise presentation-layer IA refresh is implemented, with customer-facing labels centralized in `lib/ui-content.ts` and documented in `artifacts/ui-label-mapping.md`.
- Public `/trial` onboarding, admin trial lead review, and primary `trial_user` dashboard restrictions are implemented.
- Nybsys custom PM ingestion route, async polling flow, and derived-artifact delete handling are implemented. (updated 2026-08-06: the conversion flow is retired LEGACY — `/custom-pm-ingestion` now submits via the vendor-neutral `POST /ingest/uploads` + `GET /ingest/jobs/{id}` and produces no derived artifacts; frontend `dff7e05`, EPIC-11 S1.)
- Inference and compare day-scope flows are implemented for rApp. (updated 2026-08-06: compare now renders as the embedded `Compare Models` view at `/rapp?tab=models&view=compare`; `/compare` is a redirect. Frontend `fd40b1e`.)
- Shared Non-MRO ES/LB/CCO response typing is aligned on `tick + items[{cell_id, el_degree, on_off}]`.
- Day-scope inference now surfaces `per_tick_recommendations` and raw `tilt_by_cell` diagnostics in the selected-tick view.
- BDT async inference route and polling flow are implemented.
- MRO-specific training, model detail, and async evaluation flows are implemented.
- MRO training idempotency is temporarily env-gated because the current local gateway CORS allow-list omits `Idempotency-Key`.
- MRO dataset-to-baseline mapping is still unresolved, so frontend currently avoids baseline-filtering MRO datasets and falls back to tenant-wide dataset selection when mobility metadata is missing.
- Several runbook targets remain partially implemented or missing.

## 3. Detailed Gap Matrix

| Requirement                                                                 | Status      | Evidence in Repo                                                                                                                                                                                                                                                                              | Action                                                                                                   |
| --------------------------------------------------------------------------- | ----------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| Gateway tenant route usage for browser calls                                | Partial     | Most services use `/tenants/{tenant_id}/...`; admin and lookup routes are non-tenant by design                                                                                                                                                                                                | Keep current, add central tenant route helper for consistency                                            |
| Strict envelope handling (`success/data/errors/request_id`)                 | Partial     | `ApiClient` extracts `data`; `CopilotClient` handles richer envelopes                                                                                                                                                                                                                         | Add shared envelope parser utility and propagate `request_id` diagnostics globally                       |
| Global typed error mapping (`401/403/404/422/429/5xx`)                      | Partial     | Strong mapping in `CopilotClient`; generic mapping in `ApiClient` is narrower                                                                                                                                                                                                                 | Normalize status mapping in generic API layer                                                            |
| Tenant-scoped not-authorized and not-found screens                          | Partial     | RoleGuard access denied exists; dedicated tenant-scoped 403/404 pages absent                                                                                                                                                                                                                  | Add tenant-scoped 403/404 route-level surfaces                                                           |
| Copilot routes and handlers                                                 | Implemented | `lib/api/services/copilot.ts`, `components/copilot/*`                                                                                                                                                                                                                                         | Maintain and add automated tests                                                                         |
| Copilot mandatory session-first first-send sequence                         | Implemented | `CopilotShell` creates session then sends query                                                                                                                                                                                                                                               | Keep contract tests to prevent regression                                                                |
| Copilot cursor pagination for sessions/messages                             | Implemented | `loadSessions`, `loadMessages` with cursor/direction                                                                                                                                                                                                                                          | Add tests for before/after cursor behavior                                                               |
| Copilot edit-and-rerun flow                                                 | Implemented | `updateCopilotQuery` path in `CopilotShell`                                                                                                                                                                                                                                                   | Add tests for missing-session edit guard                                                                 |
| Copilot public-agent picker with optional auto-routing                      | Implemented | `CopilotShell`, `CopilotComposer`, and `copilot-utils.ts` keep Auto as the default, source picker agents from backend, and clear stale cached agent IDs                                                                                                                                       | Add focused regression tests for agent-list refresh and omitted `agent_id` payloads                      |
| Enterprise IA refresh and shared UI label mapping                           | Implemented | `lib/app.config.ts`, `lib/ui-content.ts`, `components/app-sidebar.tsx`, `components/nav-main.tsx`, and `artifacts/ui-label-mapping.md` align visible labels while preserving technical routes                                                                                                    | Add regression coverage for nav visibility and customer-facing copy consistency                          |
| Public trial onboarding and `trial_user` dashboard mode                     | Implemented | `app/(auth)/trial/page.tsx`, `components/trial/*`, `lib/api/services/trial.ts`, `platformAdminService.listTrialSignups`, and trial-aware page/table gating across baseline/SMO/BDT/rApp/custom upload                                                                                    | Add automated regression coverage for `trial_user` route behavior and admin lead pagination              |
| BDT inference page `/bdt/models/[bdtId]/infer`                              | Implemented | Route exists with `BdtInferenceDashboard` and dedicated components                                                                                                                                                                                                                            | Add route-level tests for polling and terminal states                                                    |
| BDT inference handlers (`start/get inference run`)                          | Implemented | `startBdtInference`, `getBdtInferenceRun` and envelope variants in `lib/api/services/bdt.ts`                                                                                                                                                                                                  | Add unit tests for payload/status handling                                                               |
| BDT idempotency key support for training                                    | Missing     | `trainBDT` has no idempotency header option                                                                                                                                                                                                                                                   | Extend API client/service method signature                                                               |
| rApp train/infer/compare flows                                              | Implemented | `useRappService`, `/infer`, `/compare`, shared Non-MRO recommendation typing in `types/inference.ts`, unified table rendering in `components/inference/InferenceResultTable.tsx`, and selected-tick day recommendation / tilt diagnostics in `components/inference/DayInferenceDashboard.tsx` | Add stronger e2e coverage                                                                                |
| MRO dedicated training/detail/inference flow                                | Implemented | `components/rapp/RappTrainingForm.tsx`, `components/mro/*`, `/rapp/mro/[rappModelId]`, MRO service handlers in `lib/api/services/rapps.ts`                                                                                                                                                    | Add route-level tests for `200` cached vs `202` polling branches and dataset-metadata fallback selection |
| SMO baseline CRUD includes baseline update endpoint                         | Partial     | Create/list/delete baseline implemented, no baseline update method/UI                                                                                                                                                                                                                         | Add baseline update endpoint usage + UI edit flow                                                        |
| UE dataset create uses `/ue-data/datasets` route                            | Partial     | Current create path uses `/ue-data/upload`                                                                                                                                                                                                                                                    | Align endpoint with gateway contract if backend supports it                                              |
| Nybsys custom PM ingestion flow                                             | Implemented | `/custom-pm-ingestion`, `components/smo/Nybsys*`, and `lib/api/services/nybsys.ts` implement S3-first upload, async polling, and delete modes (updated 2026-08-06: superseded — the page renders `components/ingest/PmUploadPage.tsx` posting the neutral ingest contract; `Nybsys*` components are unmounted LEGACY and only the uploads-history list `GET` is still called, EPIC-11 S1) | Add automated coverage for runtime `403`, polling, and delete cascade behavior                           |
| Data Sim utility generators                                                 | Implemented | Topology/traffic/mobility generation handlers exist                                                                                                                                                                                                                                           | Add explicit status/result UX spec in UI docs                                                            |
| Copilot action cards by service with confirmation                           | Implemented | `CopilotMessageList` renders action cards and confirmation UX                                                                                                                                                                                                                                 | Add backend action execution and state sync if required                                                  |
| Standardized op states (`queued/running/completed/failed`) in Copilot cards | Implemented | Badge mapping present in action cards                                                                                                                                                                                                                                                         | Maintain enum alignment with backend                                                                     |
| Route-level and integration tests for each microservice                     | Missing     | No test scripts configured                                                                                                                                                                                                                                                                    | Introduce test framework and CI test jobs                                                                |

## 4. Priority Backlog

## Priority 1

- Add test framework and baseline smoke tests.
- Add automated coverage for MRO training defaults, async polling, and typed error states.
- Introduce shared envelope + error mapping helper for all services.
- Add BDT training idempotency header support.

## Priority 2

- Align UE dataset create endpoint with runbook target.
- Add baseline update flow.
- Add tenant-specific 403/404 route screens.
- Enable browser MRO `Idempotency-Key` once gateway CORS adds `Idempotency-Key` to `Access-Control-Allow-Headers`.
- Finalize product/backend treatment of MRO dataset-to-baseline linkage and emit durable mobility metadata so frontend can remove the tenant-wide fallback path.

## Priority 3

- Add deeper Copilot regression tests.
- Add request ID diagnostics surface beyond the MRO diagnostics drawer.

## 5. Exit Criteria for Gap Closure

- All runbook "required handlers" have matching service methods.
- All runbook "required pages/features" exist and are wired.
- Service-level tests pass for gateway, copilot, bdt, rapp, smo, and data-sim surfaces.
