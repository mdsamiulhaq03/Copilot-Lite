# CloudlyNet Technical Capabilities

> **Product:** CloudlyNet · **Company:** CloudlyIO · **Network Digital Twin built on:** Maveric (Linux Foundation Connectivity)
> **Last verified against code:** 2026-07-09; O-RAN/RIC scope re-verified 2026-08-10 (re-architecture epics E0-E5, commit eec8203)

This is the implementation-aware capability catalog: what is verifiable **today** in the CloudlyNet
codebase, API contracts, schemas, and deployment assets. It is the **current-state ground truth**
beneath the target-state positioning: the three solutions **Network Digital Twin (C-SON)**, **Copilot**, and
**Actuator Adapters** ([`positioning.md`](./positioning.md)) rest on what is catalogued here. Anything
that is *Building* or *Vision* lives in [`roadmap.md`](./roadmap.md), not here. Written for product,
marketing, solutioning, and leadership teams.

> ⚠️ **Before quoting anything here externally, read [`claims-guardrails.md`](./claims-guardrails.md).**
> Some capabilities below are real but must be *scoped precisely* in public material, in particular
> the O-RAN E2/R1 surfaces (§1.4), which are REST resource models and **not** protocol
> implementations, and the Copilot (§4), which is Groq-cloud-only and ships with a demo-mode
> authentication fallback.
>
> For narrative and strategy, see [`product.md`](./product.md) and [`positioning.md`](./positioning.md).

---

## Status Legend

- **Implemented** – verified in current code, API contracts, schema, or deployment assets
- **Partially implemented** – present in code/design, but incomplete, constrained, or not fully production-enforced
- **Planned / target-state** – documented architecture direction, not fully implemented in the current repo state

### Proof rung

Separate from implementation status, every *performance* claim carries the rung it was proven on:
**simulation** → **lab hardware** → **field** → **scale**. As of 2026-08-10 CloudlyNet has **no field or
scale evidence**. Never present a simulation number as a field number.

---

## 1. SaaS Platform

### 1.1 Multi-tenancy

**Capability:** Multi-tenant SaaS platform for telecom and RAN optimization workflows.  
**Status:** **Implemented**

#### What it does
- Supports multiple operator or customer tenants in one platform.
- Separates platform administration from tenant administration and tenant user access.
- Scopes baselines, UE datasets, BDT models, rApp models, training jobs, inference runs, and log access by tenant.

#### Technical details
- Tenant model:
  - `tenants` table stores `tenant_id`, `name`, `status`, `auth_provider`, and optional `auth_config`.
- Tenant membership model:
  - `tenant_memberships` stores `tenant_id`, `user_id`, `email`, `user_name`, `role`, and `status`.
  - Supported roles are `cloudly_admin`, `tenant_admin`, `tenant_user`, and `trial_user` (four-tier).
    `trial_user` grants read-only access plus inference/compare execution and full copilot access;
    it cannot create, update, delete, or train artifacts. Write restrictions are enforced at the
    gateway proxy layer by `TrialWriteGuard`.
  - The CloudlyIO platform-admin tenant is a fixed organization UUID: `00000000-0000-0000-3029-000000000000`.
  - A pre-seeded shared trial tenant (`netai trial`) backs self-service signup via the public,
    rate-limited `POST /v1/trial/signup`; leads land in `trial_signups` (platform-scoped, no RLS).
- Per-module feature gating:
  - `tenants.feature_flags` (JSONB) gates custom-capability routes per tenant, e.g. `{"nybsys": true}`
    guards the `/custom/**` router, returning 403 when absent. This is the mechanism that makes
    per-customer adapters commercially separable.
- Tenant-scoped API model:
  - Tenant APIs are exposed under `/v1/tenants/{tenant_id}/...`.
  - Platform-admin APIs are exposed under `/v1/admin/...`.
  - Public pre-auth tenant lookup is exposed as `/v1/tenants/lookup`.
- Tenant isolation enforcement:
  - Gateway enforces tenant membership and role checks from JWT claims.
  - Python services set `app.current_tenant` in Postgres at request start.
  - Postgres Row Level Security is enabled and forced on tenant-owned tables such as `baselines`, `ue_datasets`, `bdt_models`, `rapp_models`, `training_jobs`, `inference_runs`, and `rapp_evaluation_results`.

#### Why it matters
- Supports a true multi-customer deployment model without duplicating the full stack per customer.
- Allows tenant-specific datasets, models, workflows, and operational visibility.

### 1.2 OIDC and Authentication

**Capability:** AWS Cognito based authentication with tenant and role claims, enforced primarily at the gateway.  
**Status:** **Implemented** for the platform gateway, **Partially implemented** for Copilot

#### What it does
- Uses AWS Cognito as the external identity provider.
- Accepts Cognito JWTs at the gateway and rejects non-ID tokens for platform APIs.
- Applies role-aware and tenant-aware authorization before proxying or handling requests.

#### Technical details
- Identity provider:
  - AWS Cognito.
- Token handling:
  - Gateway validates Cognito JWTs using JWKS, issuer, audience, and `token_use == "id"`.
  - Gateway consumes custom claims `custom:tenant_id` and `custom:role`.
- Authorization model:
  - `/v1/admin/**` requires `cloudly_admin`.
  - `/v1/tenants/{tenant_id}/users/**` requires `tenant_admin`.
  - Other tenant routes require membership in the referenced tenant.
- Token consumers:
  - Browser and API clients send Cognito JWTs to the gateway.
  - Downstream FastAPI services do not use Cognito JWTs directly in the normal platform path.
  - Gateway injects service-specific `X-API-Key` headers on proxied calls to BDT, rApp, SMO Sim, Data Sim, and Copilot.
- User lifecycle:
  - Gateway provisions users and admins through Cognito Admin APIs and returns temporary passwords while Cognito sends invite emails.
- Copilot caveat:
  - Copilot routes are tenant-scoped and gateway-routable, but the Copilot backend currently uses demo-mode identity (`ClerkUser` stub) internally. Full production auth and tenant enforcement inside Copilot data tables remain partial.

#### Why it matters
- Provides a verifiable enterprise identity and authorization model for tenant-scoped SaaS usage.
- Keeps downstream services private and reduces repeated auth logic in each microservice.

### 1.3 API Architecture

**Capability:** Contract-first microservice API architecture with a gateway as the main external entry point.  
**Status:** **Implemented**

#### What it does
- Exposes platform capabilities through one gateway and multiple internal services.
- Uses shared OpenAPI and SQL schema artifacts as cross-service contracts.
- Normalizes response envelopes and tenant-scoped routing patterns.

#### Technical details
- Gateway:
  - Implemented in Go with Gin.
  - Handles JWT verification, RBAC, rate limiting, CORS, request IDs, proxy routing, and upstream API-key injection.
- Contract-first artifacts:
  - `artifacts/design/openapi.yaml` is the root API contract source of truth.
  - `artifacts/design/schemas.sql` is the root relational schema bundle and mirrors the tables and RLS posture expected by the services.
- Service exposure model:
  - Frontend and clients call the gateway.
  - Gateway handles local admin flows directly and proxies tenant service routes to FastAPI services.
- Route families:
  - Admin: `/v1/admin/**`
  - Tenant users: `/v1/tenants/{tenant_id}/users/**`
  - Baselines and UE data: `/v1/tenants/{tenant_id}/baselines/**`, `/v1/tenants/{tenant_id}/ue-data/**`
  - Data Sim: `/v1/tenants/{tenant_id}/utils/**`
  - BDT: `/v1/tenants/{tenant_id}/bdt/**`
  - rApps: `/v1/tenants/{tenant_id}/rapps/**`
  - Copilot: `/v1/tenants/{tenant_id}/copilot/**`

#### Why it matters
- Keeps the external API surface stable while allowing internal services to evolve independently.
- Simplifies frontend integration and tenant-aware governance.

### 1.4 Core backend services

| Service | Tech stack | Main responsibility | Key inputs | Key outputs |
|---------|------------|---------------------|------------|-------------|
| Gateway | Go, Gin | JWT validation, RBAC, tenant/user admin APIs, rate limiting, proxy routing, response envelopes | Cognito ID tokens, tenant/admin/user payloads, client API calls | Admin/user records, routed service calls, normalized API responses |
| BDT Engine | FastAPI, SQLAlchemy, Kafka worker | BDT model registry, training submission, asynchronous BDT inference | `bdt_id`, `baseline_id`, topology/training/config CSV URLs, UE dataset ID, tick | BDT model records, training metrics, model artifacts, async inference results |
| rApp Engine | FastAPI, SQLAlchemy, Kafka worker | rApp registry, rApp training, async tick inference, sync day evaluation, comparison inference | `rapp_id`, `rapp_model_id`, `bdt_id`, `baseline_id`, `dataset_id`, thresholds, energy params, tick/day | rApp model records, KPI summaries, recommended configs/actions, comparison outputs |
| SMO Sim | FastAPI, SQLAlchemy | Baseline CRUD, UE dataset registration, NanoLink edge↔cloud control plane, nybsys PM ingestion (the old O-RAN-shaped E2/R1 resource models are **deleted**; see note below) | Baseline IDs and artifact URLs, UE dataset IDs and URLs, agent telemetry/commands, PM CSVs | Baseline records, UE dataset records, device/command/KPI records |
| Data Sim | FastAPI, RADP utilities | Synthetic topology generation, traffic-load generation, mobility generation, utility logs | Baseline generation params, baseline IDs, dataset IDs, spatial/time params, mobility params | Synthetic baseline artifacts, generated UE datasets, dataset stats, Mongo-backed log entries |
| AI Copilot backend | FastAPI, LangGraph, pgvector-backed RAG | Session and message lifecycle, agent routing, knowledge search, tenant-scoped Copilot APIs | Session/query payloads, optional agent IDs, relevant files, knowledge source URLs | Conversation sessions, versioned agent responses, semantic search results |
| AI Copilot MCP server | FastMCP SSE | Allowlisted platform tool execution for Copilot agents | Tool arguments for rApp comparison, error-log retrieval, inference reporting | Structured tool results for agents and SSE clients |
| Edge Agent | Go (`CGO_ENABLED=0`), embedded SQLite | Outbound-only on-device TR-069 actuator + telemetry collector | Enrollment token, pending commands | Verified config read-backs, tiered KPIs, deduped events, config snapshots |

> **O-RAN scope note (load-bearing, re-verified 2026-08-10).** The old smo-sim `e2_interface.py`
> and `r1_interface.py` REST resource models were **deleted** (re-architecture decision D4, epic
> E4; tables dropped in `artifacts/migration/012_drop_e2_r1.sql`). CloudlyNet still implements
> **no O-RAN wire protocol itself**: no SCTP, no ASN.1/APER codec, no E2AP, no E2SM encoding, no
> O1/NETCONF, and no xApp framework anywhere in the repo. What exists now is a RIC integration
> layer in the rApp (`app/ric/`): an `a1_policy` adapter carrying A1-policy-aligned intents to an
> integrated **O-RAN SC NONRTRIC** A1-PMS, lab-verified via the `ric-lab` compose profile
> (**Today, Lab rung**); the near-RT tier is a reserved placeholder. The RIC, not CloudlyNet,
> terminates the interfaces. Public phrasing is constrained by
> [`claims-guardrails.md`](./claims-guardrails.md) §2.

---

## 2. Data Pipeline

### 2.1 Baseline Topology Data

**Capability:** Baseline network topology registration and synthetic topology generation.  
**Status:** **Implemented**

#### What it is
- Baseline topology represents the structural network context used for model training, simulation, and optimization.
- In the current platform contract, a baseline record can point to:
  - `url_to_topo_csv`
  - optional `url_to_trainingdata_csv`
  - optional `url_to_config_csv`

#### Ingestion
- Real baseline ingestion:
  - Clients upload CSVs to S3 or MinIO first, then register the URLs through SMO Sim.
  - API payload: `baseline_id`, `details`, `url_to_topo_csv`, optional `url_to_trainingdata_csv`, optional `url_to_config_csv`.
- Synthetic baseline generation:
  - Data Sim can generate a baseline directly from geographic bounds and topology parameters.
  - Input fields are verified: `min_lat`, `min_long`, `max_lat`, `max_long`, `num_cell_sites`, `cells_per_site`, `azimuth_degree`, `tower_height_min`, `tower_height_max`.
  - Generated artifacts are stored as `topology.csv`, `config.csv`, and `ue_training_data.csv`.

#### CSV support and validation
- CSV support is implemented through URL registration rather than direct multipart upload in the service layer.
- SMO Sim validates that baseline URLs stay within allowed S3 or object-storage paths for the tenant and baseline.
- Duplicate baseline IDs return HTTP 409.
- Exact real topology CSV column validation is **not** centrally enforced in the SMO Sim API contract.

#### Expected fields / important columns
- Verified baseline registration fields:
  - `baseline_id`
  - `url_to_topo_csv`
  - `url_to_trainingdata_csv`
  - `url_to_config_csv`
- Verified downstream topology/config columns referenced in current code:
  - `cell_id`
  - `cell_lat`
  - `cell_lon`
  - `cell_az_deg`
  - `cell_carrier_freq_mhz`
  - `hTx`
- Full real topology CSV schema:
  - **TBD – verify from current parser/schema**

#### Where it is used downstream
- Data Sim traffic-load generation loads the baseline topology from `url_to_topo_csv`.
- BDT training resolves topology, config, and optional UE training CSVs from the baseline record.
- rApp training and inference use the baseline as the structural context for optimization and KPI evaluation.

#### Why it matters
- Provides the persistent network context required for repeatable training, simulation, and policy comparison.

### 2.2 SMO Dataset

**Capability:** Tenant-scoped UE dataset registration for real or generated UE data.  
**Status:** **Implemented**

#### What it is
- The platform stores UE datasets in `ue_datasets` with:
  - `dataset_id`
  - `source_type` = `real`, `utils_traffic_load`, or `utils_mobility`
  - optional `baseline_id`
  - `url_to_trainingdata_csv`
  - optional `url_to_smo_ue_data_csv`
  - `stats`
- This dataset acts as the dynamic input for BDT inference, rApp inference, and day-scope evaluation.

#### Ingestion
- Real UE dataset ingestion:
  - Clients upload CSVs to object storage and register the URL through SMO Sim.
  - API payload: `dataset_id`, `baseline_id`, and one of `url_to_trainingdata_csv` or `url_to_smo_ue_data_csv`.
- Synthetic UE dataset generation:
  - Data Sim writes generated datasets back into `ue_datasets` using the same record model.

#### CSV support and validation
- Real upload validation:
  - `dataset_id` is required.
  - One of `url_to_trainingdata_csv` or `url_to_smo_ue_data_csv` must be present.
- Synthetic generation validation:
  - `dataset_id` is optional; if supplied it must not be empty and must not contain `/`.
  - Duplicate tenant/dataset combinations return HTTP 409.
- Exact real UE CSV schema is not centrally enforced by the upload API.

#### Expected fields / important columns
- Verified synthetic traffic dataset columns:
  - `ue_id`, `lon`, `lat`, `tick`, `clutter_type`, `day`
- Verified synthetic mobility dataset columns:
  - `mock_ue_id`, `longitude`, `latitude`, `tick`
- Verified downstream evaluation requirements:
  - ES/LB/CCO day evaluation requires `tick`; `day` is used when available.
  - MRO evaluation requires `latitude`, `longitude`, `mock_ue_id`, and `tick`.
- Compatibility behavior:
  - rApp loaders can derive `loc_x`, `loc_y`, and `mock_ue_id` from legacy `lon`, `lat`, and `ue_id` columns.
- Full real uploaded UE CSV schema:
  - **TBD – verify from current parser/schema**

#### How it is used
- BDT inference uses `ue_dataset_id` and `tick`.
- rApp training uses `dataset_id` together with `bdt_id` and `baseline_id`.
- rApp day evaluation loops through available ticks in a UE dataset for a selected day.
- MRO simulation uses mobility-style UE datasets.

#### Why it matters
- Supplies the time-varying UE behavior and location data needed for realistic model evaluation and policy scoring.

### 2.3 Data Sim

**Capability:** Synthetic topology, traffic-load, and mobility generation service.  
**Status:** **Implemented**

#### What it does
- Generates synthetic baseline artifacts and UE datasets when real operator data is unavailable or when controlled scenario generation is required.

#### Inputs
- Topology generation:
  - `baseline_id`, optional `details`, and `topology_details`.
- Traffic-load generation:
  - `baseline_id`, optional `dataset_id`, `days`, `num_ues`, optional `spatial_params`, optional `time_params`, optional `random_seed`, optional `notes`.
- Mobility generation:
  - optional `dataset_id` and structured `ue_tracks_generation.params`.

#### Outputs
- Synthetic baseline artifacts:
  - `topology.csv`
  - `config.csv`
  - `ue_training_data.csv`
- Synthetic UE datasets:
  - traffic-load dataset stored as `synthetic_dataset.csv`
  - mobility dataset stored as `synthetic_dataset_mobility.csv`
- Registered baseline and UE dataset records in Postgres.
- Dataset statistics and optional Mongo log records.

#### How other services consume it
- BDT training can use synthetic baseline outputs.
- rApp training and evaluation can use Data Sim-generated UE datasets.
- SMO Sim and the broader platform reuse the same baseline and UE dataset records regardless of whether data is real or synthetic.

#### Why it matters
- Supports controlled experimentation, demos, and test scenarios without direct dependency on production network data.

### 2.4 BDT

**Capability:** Bayesian Digital Twin based model training and inference layer.  
**Status:** **Implemented**

#### What it is
- In the current codebase, BDT refers to a **Bayesian Digital Twin**: a Bayesian model map of the RF environment used for RF prediction and attachment logic.
- Concretely: an **exact Gaussian-process regression model**, `gpytorch.models.ExactGP` with a
  `ScaleKernel(RBFKernel)` covariance, fit by maximizing the exact marginal log-likelihood with Adam
  (`BayesianDigitalTwin.train_distributed_gpmodel`). Stack: `gpytorch` + `torch`. Not scikit-learn.
- **Lineage:** vendored from **Maveric**, the Linux Foundation Connectivity project that is the source
  of the RIC Algorithm Development Platform (RADP). MIT licensed, publicly readable at
  `github.com/lf-connectivity/maveric`. CloudlyIO contributes to Maveric, Magma, and Open M-Plane,
  all Linux Foundation Connectivity projects.
  *This is the platform's central proof asset: a prospect can audit the model before buying.*
- BDT is a reusable model layer that supports both direct inference and downstream rApp workflows.

#### What problem it solves
- Predicts radio and attachment behavior from baseline topology and UE context.
- Provides model-backed network state estimation used by rApp optimization logic.
- Supports asynchronous, tenant-scoped training and inference workflows.

#### Training pipeline overview
- Training request:
  - `bdt_id`, `baseline_id`, optional override URLs, optional `hyperparams`.
- Training data dependencies:
  - baseline topology CSV
  - baseline config CSV
  - baseline UE training CSV or supplied override
- Execution model:
  - API creates a BDT model stub and emits Kafka event `maveric.bdt.train.v1`.
  - Worker resolves artifacts from Postgres and S3 or MinIO.
  - Worker trains the model and updates `training_jobs` and `bdt_models`.
- Artifacts and outputs:
  - persisted BDT pickle under tenant-scoped local path
  - uploaded artifact in object storage
  - model status, metrics, and artifact URIs in Postgres

#### Inference use cases
- Direct BDT inference:
  - API accepts `ue_dataset_id`, optional `baseline_id`, and `tick`.
  - Returns async run status and, on completion, D3-ready plot payloads plus metrics and summary text.
- BDT output is also reused by rApp services to build plot data and attachment-aware KPI results.

#### How it is used
- Independently:
  - asynchronous BDT inference through `/v1/tenants/{tenant_id}/bdt/models/{bdt_id}/infer`
- In rApp training:
  - rApp training depends on a trained BDT artifact via `bdt_id`
- In evaluation and comparison:
  - rApp inference and comparison flows reuse BDT attachment logic and BDT-derived topology evaluation context

#### Why it matters
- Provides the predictive network model that other optimization services can build on instead of relying only on raw KPI tables.

### 2.5 Data flow summary

```text
Real baseline URLs or synthetic topology request
-> baseline record in Postgres + topology/config/training CSVs in object storage
-> real UE dataset registration or synthetic traffic/mobility generation
-> UE dataset record in Postgres + UE CSV in object storage
-> BDT training on baseline artifacts via Kafka worker
-> BDT artifact persisted locally and in object storage
-> rApp training on {baseline_id, bdt_id, dataset_id} via Kafka worker
-> tick-scope inference or day-scope evaluation through rApp APIs
-> comparison, KPI summaries, plots, and exported result payloads
```

---

## 3. rApps

### 3.1 What are rApps?

**Capability:** Tenant-scoped optimization applications built on top of baseline topology, UE datasets, and BDT-backed evaluation.  
**Status:** **Implemented**

- In the current platform, rApps are training-backed optimization applications rather than generic policy stubs.
- The verified rApp IDs are:
  - `mro` – Mobility Robustness Optimization
  - `cco` – Coverage and Capacity Optimization
  - `es` – Energy Saving
  - `lb` – Load Balancing
- Common training contract:
  - `rapp_model_id`, `bdt_id`, `baseline_id`, `dataset_id`, optional `params`
- Common runtime context:
  - baseline
  - BDT model
  - UE dataset
  - tick or day

#### Shared engine: describe this honestly

**ES, LB, and CCO are one reinforcement-learning engine, not three.** They share the same PPO trainer
(`stable-baselines3`), the same environment (`TickAwareEnergyEnv`), the same artifact format, and the
same inference path. They differ **only** in reward weights (`app/radplib/non_mro/profiles.py`):

| rApp | `cco_score` | `load_balance_score` | `energy_saving_score` |
| ---- | ----------- | -------------------- | --------------------- |
| ES | 0.2 | 0.1 | 1.0 |
| LB | 0.5 | 1.0 | 0.05 |
| CCO | 1.0 | 0.25 | 0.0 |

This is a design **strength**: one tested, maintained codebase serving three objectives. It must
never be marketed as "four independent AI models." The RL algorithm itself is open-source PPO from
`stable-baselines3`, not a proprietary algorithm. MRO is genuinely separate (see §3.4).

### 3.2 Energy Saving

- **Purpose:** Optimize energy consumption by recommending cell on/off and related control settings while preserving acceptable network KPIs.
- **Primary use case:** Reduce energy cost in lower-demand conditions without fully giving up coverage or service quality.
- **Inputs:** `rapp_model_id`, `bdt_id`, `baseline_id`, `dataset_id`; inference uses `baseline_id`, `bdt_id`, `ue_dataset_id`, and `tick` or `day`.
- **Inference/decision logic:** Uses a trained ES model plus BDT attachment logic to evaluate network behavior and produce per-cell recommendations. Day mode aggregates tick-level outcomes across a day.
- **Outputs:** D3-ready plots, optimization metrics, and `TextMetricsES` containing per-cell configuration with `cell_id`, `el_degree`, and `on_off`.
- **Dependencies:** Baseline topology and config, UE dataset, trained BDT model, trained ES model, thresholds and optional energy parameters.
- **Execution mode:** Kafka-backed training, async tick-scope API inference, synchronous day-scope evaluation, synchronous comparison inference.
- **Business outcome:** Lets operators test or apply energy-saving strategies with model-backed KPI tradeoff visibility.
- **Implementation status:** **Implemented**

### 3.3 Load Balancing

- **Purpose:** Improve traffic distribution and fairness across cells.
- **Primary use case:** Reduce hotspot congestion and improve overall resource utilization.
- **Inputs:** `rapp_model_id`, `bdt_id`, `baseline_id`, `dataset_id`; inference uses the same baseline/BDT/UE dataset context plus `tick` or `day`.
- **Inference/decision logic:** LB is now a shared Non-MRO RL profile backed by the ES environment. It reuses the same prediction, BDT attachment, and scoring pipeline as ES/CCO, with only the reward weights changed to prioritize load-balancing outcomes.
- **Outputs:** Plots, optimization metrics, and `TextMetricsLB` with `tick` plus per-cell `{cell_id, el_degree, on_off}` recommendations.
- **Dependencies:** Trained BDT model, baseline topology/config, UE dataset, trained LB model, thresholds.
- **Execution mode:** Kafka-backed training, async tick inference, synchronous day evaluation, synchronous comparison inference.
- **Business outcome:** Helps RAN teams evaluate whether a policy improves network utilization and fairness before rollout.
- **Implementation status:** **Implemented**

### 3.4 Mobility Robustness Optimization

- **Purpose:** Improve handover robustness by tuning hysteresis and time-to-trigger behavior.
- **Primary use case:** Reduce radio link failures, handover failures, and mobility-related service instability.
- **Inputs:** `rapp_model_id`, `bdt_id`, `baseline_id`, mobility-style `dataset_id`; MRO-specific params can include `baseline_hyst` and `baseline_ttt`.
- **Inference/decision logic:** MRO supports dual-mode training. The **default mode is `simple`**, an analytical random search over `(hyst, ttt)`, not machine learning. An optional `rl` mode uses PPO (`stable-baselines3`) over a continuous `(hyst, ttt)` action space. The `gpr` and `xgb` modes are declared but raise `NotImplementedError`. Inference is simulation-based and evaluates predicted versus baseline `hyst` and `ttt` settings. **Never claim unqualified "MRO uses deep reinforcement learning"**; the default path is analytical.
- **Outputs:** `TextMetricsMRO` with predicted `hyst` and `ttt`, plus `MROEvaluationResult` containing network KPIs and MRO-specific KPI deltas.
- **Dependencies:** Mobility UE dataset with `latitude`, `longitude`, `mock_ue_id`, and `tick`; trained BDT model; baseline topology; MRO model.
- **Execution mode:** Kafka-backed training and async simulation-based inference.
- **Business outcome:** Gives mobility teams a controlled way to evaluate handover parameter changes before operational rollout.
- **Implementation status:** **Implemented**

### 3.5 Coverage and Capacity Optimization

- **Purpose:** Optimize antenna and coverage-related settings to improve coverage and capacity balance.
- **Primary use case:** Improve weak-coverage and over-coverage conditions while maintaining usable capacity outcomes.
- **Inputs:** `rapp_model_id`, `bdt_id`, `baseline_id`, `dataset_id`; inference uses the same baseline/BDT/UE dataset context plus `tick` or `day`.
- **Inference/decision logic:** CCO is now a shared Non-MRO RL profile backed by the ES environment. It reuses the same model format, prediction flow, BDT attachment, and optimization scoring as ES/LB, with reward weights biased toward coverage/capacity objectives.
- **Outputs:** Plots, optimization score, and `TextMetricsCCO` with `tick` plus per-cell `{cell_id, el_degree, on_off}` recommendations.
- **Dependencies:** Baseline topology/config, UE dataset, trained BDT model, trained CCO model.
- **Execution mode:** Kafka-backed training, async tick inference, synchronous day evaluation, synchronous comparison inference.
- **Business outcome:** Supports engineering teams that need a model-backed way to evaluate coverage and capacity tuning options.
- **Implementation status:** **Implemented**

---

## 4. Copilot

### 4.1 What Copilot is

**Capability:** Conversational assistant and workflow-orchestration layer over the platform.  
**Status:** **Partially implemented**

#### Technical role
- Assistant layer:
  - session and message lifecycle
  - versioned agent responses
- Orchestration layer:
  - LangGraph-based agent routing and execution
- Knowledge layer:
  - pgvector-backed semantic retrieval over ingested platform documents
- API assistant layer:
  - MCP tools can call allowlisted platform APIs such as rApp comparison and error-log retrieval

#### What it consumes
- User queries
- Existing session history
- Optional `agent_id`
- Optional `relevant_files`
- Knowledge source URLs for ingestion and semantic search

#### What it produces
- Session records
- Versioned assistant responses
- Semantic search results
- Tool-backed analysis outputs for supported MCP tools

#### Why it matters
- Makes platform navigation, troubleshooting, and analysis more accessible without exposing internal microservices directly to users.

### 4.2 Agent types

Four agents are live and routed. An LLM router classifies each query and falls back to `reactive`.

#### Reactive Agent
- **Purpose:** Default general-purpose Copilot agent with RAG search.
- **Tools:** `rag_search`.
- **Typical flow:** create session -> query without specifying agent -> router defaults to `reactive_agent` for platform knowledge questions.

#### Debugger Agent
- **Purpose:** Diagnostics, troubleshooting, and policy comparison.
- **Tools:** `rag_search`, `compare_rapp_policies` (MCP), `get_platform_error_logs` (MCP).
- **Typical flow:** query about platform failures or model differences -> debugger uses RAG plus allowlisted platform tools through the gateway.
- **Scope caveat:** it reads **CloudlyNet's own** error logs, not the customer's network syslog. General log-ingestion RCA is roadmap, not shipped.

#### Data Generation Agent
- **Purpose:** Guidance for baseline and dataset generation. **Never mutates state**; it emits API-call templates.
- **Tools:** `validate_baseline_params`, `validate_dataset_params`, `recommend_baseline_config`, `recommend_dataset_config`, `estimate_impact`, `get_generation_docs` (in-memory), plus `query_existing_baselines` and `compare_datasets` (via gateway), plus `rag_search`.

#### Inference Explanation Agent
- **Purpose:** Explains a completed rApp inference in plain language: threshold pass/fail, worst hour, hotspot cells.
- **Tools:** `rag_search`, `get_inference_report` (MCP), `compare_inference_models` (MCP).
- **Safety design:** the deterministic math happens inside the tools; the model only narrates, and every claim cites the value it came from. Tools are page-bound, registered only when the matching CloudlyNet page is on screen.
- **Known gap:** MRO inference explanation is unsupported (returns `mro_not_supported`).

#### Dead code: do not document externally
`GenericAgent` and `OfflineDebuggingAgent` exist in the tree but are **not wired into routing and are
never invoked at runtime**. Per `COPILOT_IMPLEMENTATION_SUMMARY.md`, treat both as awaiting deletion.
They must not appear in any customer-facing material.

### 4.3 Copilot boundaries

#### What Copilot can do
- Expose tenant-scoped session, message, health, user-profile, and knowledge endpoints.
- Route queries across four named agent categories.
- Perform semantic search over ingested knowledge sources stored in the Copilot knowledge schema.
- Call allowlisted platform APIs through MCP tools for:
  - rApp comparison
  - platform error-log retrieval

#### What Copilot cannot be claimed to do
- It cannot be described as fully production-authenticated internally today; the backend still uses demo-mode identity internally.
- It cannot be described as fully tenant-enforced at the Copilot database layer; that is still listed as incomplete in Copilot design docs.
- It cannot be described as a general autonomous action engine across the full platform; broad CRUD and action executor flows are documented as target-state rather than fully implemented.

#### Scope constraints
- Tenant-scoped API paths: **Yes**
- Gateway-routed production path: **Yes**
- Internal auth and tenant enforcement inside Copilot DB: **Partially implemented**
- Reads semantic knowledge base: **Yes**
- Reads arbitrary platform datasets directly as a first-class Copilot feature: **No verified direct dataset API flow**
- Triggers limited platform workflows through allowlisted tools: **Yes, where MCP tools exist**

---

## 5. Device Control Plane: NanoLink Edge Agent

**Capability:** Outbound-only, closed-loop configuration and telemetry control plane for TR-069/CWMP
devices, with verified read-back and automatic rollback.
**Status:** **Implemented** · **Proof rung: lab hardware**

> This is the most operationally mature and least-marketed capability in the platform. It is what
> turns CloudlyNet from a simulator into a system that changes real networks.

### 5.1 What it is

A Go edge agent runs on a customer-premises host, speaks TR-069/CWMP to devices through its own
**self-contained in-agent ACS on `:7547`** (no GenieACS or external ACS/NMS dependency), and dials
outbound to CloudlyNet. Proven end-to-end on **NybSys NanoLink 2302-B3** femtocells (LTE FDD Band 3,
20 MHz, single cell, `MaxTxPower` 21 dBm).

**Not an NMS.** This is element-layer control. See [`toolchain-fit.md`](./toolchain-fit.md) §4.

### 5.2 Security and connectivity posture

- **No inbound production port.** The edge sits behind NAT; the cloud never dials in.
- Enrollment by **one-time token**; only `sha256(secret)` is stored as `api_key_hash`.
- Edge-Key authentication resolves edge → tenant before the Postgres tenant GUC is set, via a
  SELECT-only pre-auth RLS policy. **The deployed Postgres role must be non-superuser** or RLS is
  silently bypassed.
- Agent binary is `CGO_ENABLED=0` with embedded SQLite (`modernc.org/sqlite`) for outbound retry and
  applied-command dedupe. Native + systemd on Ubuntu 22.04, not Docker.

### 5.3 Closed-loop configuration: the differentiator

1. Operator proposes a value against a curated catalogue of **24 managed parameters**.
2. Agent issues TR-069 `setParameterValues` with a connection request.
3. Agent polls `getParameterValues` until the **read-back matches** the requested value or the
   verification timeout expires (15 s in production).
4. The acknowledgement carries the **actual** read-back. The UI never promotes a proposed value to
   "Current" until the ack is `applied`.

**Rollback fires in two independent ways:**
- On a failed `configure` with `rollback_on_fail`, a rollback command is auto-enqueued from
  `prev_values`.
- A guardrail watcher inspects the next KPI window and rolls back if `sinr_avg_db` falls below floor
  or `rrc_success_pct` drops under 95% within 15 minutes of an applied change.

**Command transport safety:** `SELECT … FOR UPDATE SKIP LOCKED` claim-on-fetch, 60 s lease, 5
attempts, dead-lettering, idempotent re-ack from the agent's local buffer.
Command types: `configure`, `optimise`, `query`, `reboot`, `rollback`.

### 5.4 Telemetry

| Tier | Interval | Contents |
|---|---|---|
| T1 | 30 s | `op_state`, `rf_tx_status`, `admin_state`, `s1_status`, `sctp_status`, `connected_ues`, `volte_ues` |
| T2 | 60 s | `rip_average`, `rip_prb`, `earfcn_dl_inuse`, `pci_inuse`, `rs_power`, `dl_bw`, `ul_bw` |
| T3 | 5 min | PM counters (`prb_dl_pct`, `prb_ul_pct`, `sinr_avg_db`, `rrc_conn_mean`, `thp_dl`, `thp_ul`), derived `rrc_success_pct`, hardware (`uptime`, `cpu_usage`, `mem_*`), and `Device.FaultMgmt` alarms |

PM counters are read from `Device.PeriodicStatistics.SampleSet.1`, whose on-device granularity is
900 s, so PM keys refresh roughly every 15 minutes regardless of poll cadence.

**Known constraint:** the NanoLink exposes **no serving-cell RSRP**; every RSRP path is a config
threshold or a handover-event value. The planned `median_rsrp` KPI was therefore dropped in favour of
`sinr_avg_db` from `RRU.Sinr.Average`.

### 5.5 Self-optimiser: rules-based, not ML

**Status: Partially implemented.** An EWMA z-score anomaly detector on `sinr_avg_db` (|z| > 3 raises
a `kpi_anomaly` event) plus exactly two guard-railed rules:

- **Energy saving**: cell idle (`prb_dl_pct < 15`, `connected_ues ≤ 2`) with SINR headroom and healthy
  RRC success → trim RS power 2 dB, relax DRX/paging. Confidence 0.7.
- **Coverage**: congested and under-powered (`prb_dl_pct > 70`, `rs_power < −10`) → restore RS power
  2 dB. Confidence 0.9.

Hard guardrails: `min_sinr_db`, `max_prb_dl_pct = 70`, `min_rrc_success_pct = 95`.

`optimize_mode` per device, the trust dial: `off` · `approval` (recommendation waits for a human) ·
`auto` (auto-applies within guardrails, rolls back on breach).

This is a **rules engine**, not the RL rApps, and it is **single-cell**. Its value is proving the
closed loop is safe, which is what eventually earns permission to run the RL models in `auto`.

**Caveat:** the EWMA state is per-process and in-memory; it resets on restart. `reset_stale_commands`
runs once at process startup rather than on a timer, so stale commands only reclaim on restart.

### 5.6 What is absent (an NMS/EMS buyer will ask)

Alarm acknowledge/clear lifecycle · alarm correlation and root cause · notification and escalation ·
**`heal` is a defined command type with a no-op handler** · accounting (no usage/session/CDR) ·
threshold-crossing alerts · historical PM rollups, reporting, or export · firmware upgrade · full
config backup/restore · golden-config drift detection · topology and neighbour map · **bulk/fleet
operations (every command targets one `device_id`)** · northbound OSS integration (no TMF Open API,
no SNMP trap forwarding, no ticketing).

### 5.7 Custom PM ingestion (nybsys)

**Status: Implemented.** A six-stage pipeline turns operator 3GPP PM CSVs into platform-canonical
baselines and UE datasets consumable by BDT and rApps with zero downstream change:
normalize → hourly aggregate → topology synthesis → config → UE placement (served/edge/outage) →
TR 38.901 RSRP labelling. Reproducible via a persisted `rng_seed`. Gated by the `nybsys` feature flag.

---

## 6. Logging, Monitoring, and Reliability

**Capability:** Structured logging, health visibility, metrics, and async workflow reliability.  
**Status:** **Implemented**, with some observability stack elements still **Planned / target-state**

### Logging
- Structured JSON logging is implemented across gateway and Python services.
- Python services use standard severity levels including `DEBUG`, `INFO`, `WARNING`, `ERROR`, and `CRITICAL`.
- FastAPI services attach `X-Request-ID` and enrich logs with tenant and request context.
- Data Sim, SMO Sim, rApp, and BDT persist application logs and error logs to MongoDB when configured, while continuing to log to STDOUT.
- Service-scoped error-log APIs are implemented for `utils`, `baselines`, `rapps`, and `bdt`.

### Monitoring
- Health endpoints are implemented across services.
- Copilot adds `/health`, `/live`, and `/ready` style checks.
- Prometheus metrics endpoints are implemented in gateway, BDT, rApp, and Copilot.
- Worker metrics ports are exposed for BDT and rApp workers when enabled.
- Gateway adds request-correlation headers including `X-Request-ID`; the broader platform design also uses `traceparent`, and OpenTelemetry instrumentation is present in service code and design docs, though trace coverage is not uniformly mature in every service.
- Grafana and Loki are described in architecture docs, but are not verified as deployed charts in the current workspace.

### Reliability
- Gateway rate limiting uses Redis.
- Training jobs use Kafka topics:
  - `maveric.bdt.train.v1`
  - `maveric.rapp.train.v1`
- rApp and BDT workers implement manual commit, partition pause/resume, exact-offset commit, and idempotent skip of terminal-state redeliveries.
- rApp inference deduplicates runs with deterministic run IDs and layered caching.
- BDT inference also uses Redis and Mongo-backed caching.

### Failure visibility and debugging support
- Log search and error-resolution endpoints are available per service family.
- rApp comparison and log inspection are also reachable through Copilot MCP tools.

---

## 7. Deployment and Runtime Architecture

**Capability:** Containerized microservice runtime with local Docker Compose and Kubernetes Helm deployment assets.  
**Status:** **Implemented**, with some scale and infra patterns still **Planned / target-state**

### Deployment overview
- Local runtime:
  - Docker Compose for shared infra and app services.
- Cluster runtime:
  - Kubernetes deployment assets are maintained in `submodule/maveric-deployment`.
  - Helm charts are used for service packaging.
  - ArgoCD is used for GitOps deployment.
  - Jenkins pipelines are used for image build and promotion.
- Target cloud:
  - AWS EKS is the documented production target.
  - S3 is the documented production object store.
- Secrets and config:
  - Local development uses `.env`.
  - Cluster runtime uses Helm values and Kubernetes secrets.
  - Architecture docs also reference AWS Secrets Manager with External Secrets Operator as the production secret target-state.
- Kafka and ZooKeeper:
  - Current deployment is an initial single-broker persistent rollout, not final HA topology.

| Area | Implementation |
|------|----------------|
| Frontend | Next.js 15 operator dashboard (App Router). Registered as a submodule at `submodule/maveric_platform_frontend`. Design docs live in `artifacts/frontend/`. |
| API gateway | Go + Gin gateway with Cognito JWT validation, RBAC, proxy routing, Prometheus metrics |
| ML/optimization services | FastAPI-based BDT Engine, rApp Engine, SMO Sim, Data Sim |
| Datastores | Postgres, MongoDB, Redis |
| Queue/stream | Kafka with versioned training topics and worker consumers |
| Object storage | AWS S3 in production target; MinIO or S3-compatible endpoint in local/dev |
| Deployment | Docker Compose locally; Kubernetes + Helm + ArgoCD in deployment repo |
| Auth | AWS Cognito at gateway; internal service API keys on east-west traffic |

---

## 8. Storage and Data Components

### Postgres
- **Why it exists:** System of record for platform metadata and tenant-scoped operational state.
- **What it stores:** tenants, tenant memberships, baselines, UE datasets, BDT models, rApp models, training jobs, inference runs, rApp day-evaluation summaries.
- **Which services use it:** gateway, SMO Sim, Data Sim, BDT Engine, rApp Engine, Copilot.

### MongoDB
- **Why it exists:** Persistent log and error store, plus an optional cache tier for some inference flows.
- **What it stores:** `application_logs`, `error_logs`, and cached inference payloads where configured.
- **Which services use it:** Data Sim, SMO Sim, BDT Engine, rApp Engine.

### Redis
- **Why it exists:** Fast state for rate limiting, idempotency, and caching.
- **What it stores:** gateway rate-limit counters, idempotency records, inference cache entries, optional helper state.
- **Which services use it:** gateway, rApp Engine, BDT Engine, Copilot, Data Sim optional hooks.

### Kafka
- **Why it exists:** Async job transport for long-running training workflows.
- **What it stores or moves:** versioned training events for BDT and rApp workers.
- **Which services use it:** BDT Engine training worker and rApp Engine training worker. Current topics are `maveric.bdt.train.v1` and `maveric.rapp.train.v1`.

### S3 / MinIO
- **Why it exists:** Canonical object storage for uploaded CSVs, generated datasets, and model artifacts.
- **What it stores:** baseline topology/config/training CSVs, UE datasets, BDT pickles, rApp model ZIP artifacts, synthetic generation outputs.
- **Which services use it:** SMO Sim, Data Sim, BDT Engine, rApp Engine, Copilot health and shared infra configuration.

---

## 9. Capability Summary for Marketing Head

| Capability Area | Exact technical capability | Why it matters commercially |
|-----------------|----------------------------|-----------------------------|
| Multi-tenancy | Tenant-scoped SaaS model with gateway RBAC and Postgres RLS | Supports multiple operators or customers on one platform without separate stacks |
| Authentication | AWS Cognito ID-token validation with tenant and role claims | Provides enterprise identity and controlled tenant access |
| API platform | Gateway-led, contract-first API model using OpenAPI and shared SQL schema bundles | Reduces integration friction for UI, internal teams, and partners |
| Baseline management | Registration and generation of topology, config, and training artifacts | Gives customers a reusable network context for repeated analysis and testing |
| UE data pipeline | Real and synthetic UE dataset registration with tenant-scoped lineage | Supports time-varying network analysis beyond static topology |
| Data Sim | Synthetic topology, traffic-load, and mobility generation | Enables demos, testing, and experimentation where real data is limited |
| BDT | Bayesian Digital Twin training and inference service | Provides a reusable predictive layer that multiple optimization workflows can build on |
| rApps | Implemented MRO, CCO, ES, and LB applications with train and inference APIs. ES/LB/CCO share one PPO engine differentiated by reward weights | Converts shared platform data into operator-facing optimization use cases |
| **Device control plane** | **Outbound-only TR-069 edge agent with verified config read-back and automatic rollback, proven on NanoLink hardware** | **The capability that turns simulation into a system that safely changes real networks. Under-marketed today.** |
| Open-source lineage | The BDT (Bayesian Digital Twin) descends from Maveric (Linux Foundation Connectivity), the source of RADP. CloudlyIO contributes to Maveric, Magma, Open M-Plane | **The strongest asset we have.** In a market gated by trust, an auditable Network Digital Twin governed by a neutral foundation outweighs any feature. Attribute Maveric to the twin, never the whole platform; see [`claims-guardrails.md`](./claims-guardrails.md) §6 |
| Copilot | Session-based assistant with agent routing, RAG search, and limited platform tool execution | Makes technical platform workflows easier to access and explain |
| Observability | Structured logs, health probes, Prometheus metrics, Mongo-backed error visibility, and Kafka worker hardening | Improves production supportability and reduces troubleshooting time |
| Deployment | Docker Compose locally, Kubernetes Helm deployment via ArgoCD and Jenkins in the deployment repo | Supports enterprise deployment, release control, and environment separation |
