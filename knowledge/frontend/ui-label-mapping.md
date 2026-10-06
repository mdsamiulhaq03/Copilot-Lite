# UI Label Mapping

This document tracks presentation-layer label updates introduced in the enterprise UI refresh.

Routes, APIs, state models, and workflow behavior remain unchanged unless explicitly noted as a navigation visibility update.

| Old UI Label                | New UI Label                               | Underlying Component / Meaning                                                     |
| --------------------------- | ------------------------------------------ | ---------------------------------------------------------------------------------- |
| Baseline Topology           | Topology                                   | Baseline topology page and route remain unchanged                                  |
| Baseline List               | Topology Records                           | Existing baseline table with unchanged data model                                  |
| Baseline ID                 | Topology / Topology ID                     | Existing baseline identifier field                                                 |
| SMO Connect                 | Mobility Data                              | Existing SMO dataset page and route remain unchanged                               |
| SMO List                    | Mobility Datasets                          | Existing dataset table with unchanged data model                                   |
| SMO Dataset ID              | Mobility Dataset                           | Existing dataset identifier and linkage                                            |
| Custom PM Ingestion         | Custom Upload                              | Existing Nybsys ingestion page and route remain unchanged                          |
| Nybsys Upload Queue         | Upload Activity                            | Existing upload queue table and workflow                                           |
| Derived Baseline            | Derived Topology                           | Existing Nybsys-derived baseline output                                            |
| Derived Dataset             | Derived Mobility Dataset                   | Existing Nybsys-derived dataset output                                             |
| BDT                         | Digital Twin                               | Existing BDT page and route remain unchanged                                       |
| Bayesian Digital Twin (BDT) | Digital Twin                               | Customer-facing rename only                                                        |
| BDT List                    | Digital Twin Library                       | Existing BDT table and workflow                                                    |
| BDT ID                      | Digital Twin                               | Existing BDT identifier and linkage                                                |
| BDT Inference               | Digital Twin Simulation                    | Existing BDT inference route and workflow                                          |
| rApp                        | Network Optimisation                       | Existing rApp page and route remain unchanged                                      |
| Feature Model Training      | Optimisation Models / Network Optimisation | Existing rApp model management and training experience                             |
| Rapp Type                   | Optimisation Type                          | Existing rApp type field and data model                                            |
| ES                          | Energy Saving Model                        | Existing ES model type                                                             |
| MRO                         | Mobility Optimisation Model                | Existing MRO model type                                                            |
| CCO                         | Coverage Optimisation Model                | Existing CCO model type                                                            |
| LB                          | Load Balancing Model                       | Existing LB model type                                                             |
| Infer                       | Run Model                                  | Route preserved, removed from side nav, exposed contextually from model actions    |
| Single Model Inference      | Run Model                                  | Existing `/infer` route and day-evaluation workflow                                |
| Compare                     | Compare Models                             | Existing compare page and route remain unchanged                                   |
| Model Comparison            | Compare Models                             | Existing compare workflow with presentation-only rename                            |
| Error Logs                  | Error Logs                                 | Navigation hidden for customer workspaces and retained for Cloudly internal admins |
| Copilot                     | Copilot                                    | Route preserved and entry retained in top bar only                                 |
| Trial Signup                | CloudlyNet trial access                         | Public onboarding route for self-service trial signup and hosted login bootstrap   |
| trial_user                  | Trial User                                 | New customer-visible role label for guided read-only demo workspaces               |
| Trial Signups               | Trial Pipeline                             | Cloudly admin table for public trial lead review                                   |
| Users                       | User Management                            | Existing tenant user management page                                               |
| Organizations               | Organization Management                    | Existing Cloudly admin organization page                                           |
| —                           | Add Device                                 | New `/devices` NanoLink device-management section (edge enrollment, config, monitoring, optimise) |
| Edge Device                 | Edge Device                                | GO Agent host that manages NanoLink cells; enrolled via one-time token             |
| NanoLink / Cell             | Device                                     | A managed LTE small-cell discovered by an edge device                              |

## IA Restructure Updates (2026-07)

Second rename wave: the sidebar became sectioned (`Intelligence` / `Actuators`) to mirror the product flow `Ingest -> Network Digital Twin -> Optimization -> Policy & Guardrails -> Actuator Adapter`. Rows below supersede the matching rows above; routes and APIs remain unchanged unless noted.

| Previous UI Label            | Current UI Label                             | Underlying Component / Meaning                                                     |
| ---------------------------- | -------------------------------------------- | ---------------------------------------------------------------------------------- |
| Network Setup (nav group)    | Intelligence -> Ingest                       | `/ingest` is a new navigable parent page; children keep their routes               |
| Topology                     | Topology & Configuration                     | `/baseline` unchanged                                                              |
| Mobility Data                | Training Data                                | `/smo` unchanged; datasets are training inputs (UE measurements), never PM counters |
| Custom Upload                | PM Upload                                    | `/custom-pm-ingestion` unchanged                                                   |
| Digital Twin                 | Network Digital Twin                         | `/bdt` unchanged; solution term per claims guardrails                              |
| Network Optimisation         | Optimization                                 | `/rapp` unchanged; US spelling across visible copy (`Optimization Type`, `Mobility/Coverage Optimization Model`) |
| Add Device                   | Actuators -> Connections                     | Landing relocated to `/actuators` (H1 `Actuator Adapters`); `/devices` kept as redirect |
| —                            | Policy & Guardrails                          | New `/policy` page; device panel heading `Optimisation mode` is now `Policy mode`  |
| Optimise (device tab)        | Optimize                                     | Tab value stays `optimise` for `?tab=` deep-links                                  |
| NetAI (topbar)               | CloudlyNet                                   | Brand rename; subtitle `RAN intelligence by Cloudly`                               |

## IA Realignment Updates (2026-08-06)

Third wave, from the 12-item IA realignment (frontend commits `dff7e05`/`d55ec13`/`fd40b1e`/`887a396`). Rows below supersede the matching rows above.

| Previous UI Label            | Current UI Label                             | Underlying Component / Meaning                                                     |
| ---------------------------- | -------------------------------------------- | ---------------------------------------------------------------------------------- |
| Compare Outcomes             | Compare Models                               | `/compare` is now a server redirect to `/rapp?tab=models&view=compare`; compare is the embedded `Compare Models` view on the Optimization page (route label kept for the redirect) |
| Training UE Data (CSV) *     | BDT training data (CSV)                      | Baseline modal field (`AddBaselineModal`); now **optional** — per-UE measurements that TRAIN the twin, not needed when a UE dataset is registered separately |
| Training data (Evaluate)     | UE dataset (evaluation points)               | Evaluate form dataset select (`EvaluateForm`); it is the twin's query points, not training input |
| Tick                         | Tick / Hour of day (0-23)                    | Evaluate tick input: **disabled** for static snapshots (`stats.tick_variant === false`, "tick has no effect"); relabeled `Hour of day (0-23)` for tick-variant datasets |
| Connect RIC (header button)  | Connect to RIC (tab)                         | `/rapp` primary tabs `Use CloudlyNet Models` \| `Connect to RIC`; RIC tab renders `RicConnectPanel`, still no backend call |
| Custom PM Ingestion (meaning) | PM Upload                                   | Meaning updated in `lib/ui-content.ts`: vendor-neutral PM upload posting to the canonical ingest pipeline; route remains unchanged |
