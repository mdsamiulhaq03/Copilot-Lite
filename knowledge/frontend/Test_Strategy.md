# Frontend Test Strategy

## 1. Purpose

This strategy defines how to validate functional correctness, regression safety, and integration quality for the frontend.

## 2. Current State

- No test runner scripts are currently defined in `package.json`.
- Quality checks currently depend on:
  - Type safety (`tsc` when run manually)
  - Lint (`npm run lint`)
  - Production build (`npm run build`)
  - Container build verification (`docker compose up --build`) when Docker delivery or image-build stability is part of the task
  - Manual QA

## 3. Proposed Test Pyramid

## 3.1 Unit Tests

Targets:

- Utility functions:
  - `components/inference/day-eval-utils.ts`
  - `components/copilot/copilot-utils.ts`
- API client behavior:
  - envelope parsing
  - error mapping
  - status transitions and helper guards

Suggested stack:

- Vitest + Testing Library + jsdom

## 3.2 Component Tests

Targets:

- Form validation and submit gating:
  - Topology, Mobility Data, Digital Twin, and Network Optimisation training modals
- Table action flows:
  - delete confirmations
  - refresh actions
- Navigation and shell behavior:
  - `Network Setup`, `Digital Twin`, `Network Optimisation`, and `Administration` grouping
  - `Run Model` exposed contextually instead of as a side-nav item
  - `Copilot` top-bar only
  - `Error Logs` hidden from non-Cloudly admin side navigation
- Copilot panel:
  - send/edit/selection behavior
  - action-card confirmation UI

## 3.3 Integration Tests

Targets:

- Auth callback flow with mocked token exchange.
- Tenant preload pipeline in `ApplicationProvider`.
- Inference polling terminal-state behavior.
- Error logs module fetch/resolve flow.

## 3.4 End-to-End Tests

Targets:

- Tenant sign-in and dashboard entry.
- Topology -> Mobility Data -> Digital Twin -> Network Optimisation training lifecycle.
- Run Model and Compare Models end-to-end workflows.
- Copilot first-send session-first contract.

Suggested stack:

- Playwright

## 4. Microservice-Aligned Test Matrix

## 4.1 Gateway

- Validate tenant route construction.
- Validate auth header propagation.
- Validate envelope parsing and error fallback behavior.

## 4.2 Copilot

- Enforce session-first first send.
- Verify `CopilotShell -> CopilotPanel -> CopilotSessionList` prop contracts compile cleanly for session search behavior.
- Verify Auto mode omits `agent_id` from `POST` and `PATCH /copilot/agents/query`.
- Verify stale cached agent IDs are cleared when `GET /copilot/agents` no longer returns them.
- Verify `Data Generation Agent` is present in the picker while hidden `reactive_agent` and `generic_agent` are not.
- Cursor paging for sessions and messages.
- Edit-and-rerun behavior with missing session guard.
- Response rendering for hidden backend response-agent IDs.
- 403 and 404 recovery paths.

## 4.3 BDT

- Train request payload shape.
- Table refresh and delete side effects.
- Infer submit payload (`ue_dataset_id`, `tick`, optional `baseline_id`).
- Infer poll-to-terminal completion (`queued|running` -> `completed|failed`).
- Infer result rendering (plot groups + metrics/text cards).
- Customer-facing labels map BDT surfaces to `Digital Twin` and `Digital Twin Simulation` without changing route or payload behavior.

## 4.4 rApp

- Train flow with BDT-baseline dependency.
- Infer poll-to-terminal completion.
- Compare payload and response rendering.
- Customer-facing labels map rApp surfaces to `Network Optimisation`, `Run Model`, and `Compare Models` while keeping technical route behavior unchanged.
- ES/LB/CCO tick responses all deserialize to the shared Non-MRO text contract (`tick + items[{cell_id, el_degree, on_off}]`).
- Day-scope ES/LB/CCO evaluation maps `per_tick_recommendations` onto the selected-tick recommendation table.
- Raw day-scope `tilt_by_cell` expansions render electrical tilt diagnostics without dropping `on_off` recommendations.
- Shared recommendation table renders `on_off === false` consistently for ES, LB, and CCO.
- Compare selectors and day-scope rendering accept `cco` as either model A or model B when the model is ready.
- MRO training sends explicit `params.mro_type` and canonical `params.total_timesteps`.
- MRO training only sends browser `Idempotency-Key` when `NEXT_PUBLIC_ENABLE_MRO_IDEMPOTENCY_HEADER=true`.
- MRO RL/Simple toggle updates timesteps defaults correctly.
- MRO training blocks non-mobility datasets.
- MRO training continues to show mobility-compatible datasets even when dataset `baseline_id` does not match the selected baseline.
- MRO training falls back to tenant-wide dataset options when backend metadata does not mark any dataset as mobility-compatible.
- MRO detail route polls model status until `ready|failed`.
- MRO inference hides tick/day and compare affordances.
- MRO inference validates `baseline_hyst` and `baseline_ttt`.
- MRO inference accepts a mobility-compatible dataset without frontend baseline-linkage validation.
- MRO inference falls back to tenant-wide dataset options when mobility metadata is absent and still blocks non-mobility submit payloads.
- MRO inference handles `200` immediate complete vs `202` poll-to-terminal behavior.
- Repeated MRO submit reuses the returned deterministic `run_id` instead of creating duplicate local rows.
- Completed MRO result renders predicted vs baseline params, delta, warnings, and diagnostics metadata.
- `409` and `400` MRO error responses are rendered as typed actionable states.

## 4.5 SMO and Data Sim

- Dataset create in upload and generate modes.
- Delete confirmation flow.
- Utils generation payload validation.
- Nybsys custom PM ingestion uploads raw CSV files to S3 before calling `/custom/nybsys/uploads`.
- Nybsys upload polling stops on `completed` and `failed`.
- Nybsys runtime `403` renders the feature-disabled state cleanly.
- Nybsys delete flow differentiates plain upload deletion from delete-with-derived-cascade.

## 4.6 Error Logs

- Multi-module fetch behavior.
- Resolve action updates.
- Stack trace copy behavior.
- Side-nav visibility only for Cloudly internal admins.

## 5. Test Data Strategy

- Use deterministic fixture payloads for:
  - day-scope inference responses
  - compare deltas and pareto points
  - copilot message/version/action payloads
- Include negative fixtures:
  - baseline mismatch
  - malformed envelope
  - 401/403/404/429/5xx responses

## 6. CI Quality Gates (Recommended)

Minimum:

1. `npm run lint`
2. `npm run format:check`
3. `npm run build`
4. `npx tsc --noEmit`
5. `docker compose up --build` when Docker, compose, or production-image viability changes

Target (after test framework adoption):

6. `npm run test:unit`
7. `npm run test:integration`
8. `npm run test:e2e` for release branches

## 7. Definition of Done for New Features

- API contract documented in `artifacts/route.md` and `artifacts/API_Contracts.md`.
- Happy path and at least one failure path tested.
- Tenant and role constraints validated.
- Loading, empty, and error states explicitly handled.
- Accessibility keyboard path validated for new interactive controls.
