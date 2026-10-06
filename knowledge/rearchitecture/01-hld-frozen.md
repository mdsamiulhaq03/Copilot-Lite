# CloudlyNet Re-architecture: FROZEN HLD

Date frozen: 2026-07-16 · Decisions by: product owner (Q1–Q4) · Basis: `00-hld-assessment.md`
Amended 2026-07-16 (v1.1), product-owner directive: **the RIC track is re-focused on the non-RT
tier** (where market progress is). D1, §4.4, A.4, and A.5 were amended; the near-RT RIC is now a
reserved placeholder. Grounding research: O-RAN SC NONRTRIC survey appended to
`00-hld-assessment.md` §8.
Amended 2026-07-17 (v1.2), product-owner directive: **working with OCUDU is of paramount strategic
importance.** New D5 + §4.7 (demo-lab contract) + EPIC-7. The near-RT placeholder is ACTIVATED FOR
LAB USE ONLY (dockerized O-RAN SC RIC + a thin CloudlyNet xApp) because OCUDU's verified,
code-mature RAN-control surface is E2, while its O1 surface is a code-confirmed gap in the gNB
(sidecar-based config-rewrite + restart only). Grounding: `artifacts/ocudu/` bundle (code-validated
against OCUDU 26.04 HEAD 050a2bb72e) + `00-hld-assessment.md` §9.
This document is the constitution for all LLD/epic work. Epic authors MUST conform to the shared
contracts in §4; deviations require re-opening the freeze.

## 1. Decisions (final)

| # | Decision |
|---|---|
| D1 (amended v1.1) | **The integrated open RIC is O-RAN SC NONRTRIC, at the non-RT tier, consumed component-wise as container images + REST** (never by copying source): the **A1 Policy Management Service** (Apache-2.0; upstream-active in ONAP CCSDK-ORAN; OSC M-release 2.11.0) plus the **OSC A1 Simulator** (2.8.1) as the lab stand-in for a near-RT RIC's A1 termination. Apache-2.0 means this open RIC MAY ship with commercial deployments (mirror the `nexus3.o-ran-sc.org:10002` images into our registry; keep the O-RAN ALLIANCE attribution notice if the pms-api-v3 OpenAPI file is vendored; never use O-RAN compliance/certification language). **The near-RT RIC is a reserved placeholder** (adapter key `nearrt_xapp`): no submodule, no xApp code, no E42 bridge now; FlexRIC (CSSL v1.0, lab-only patent grant) or a commercial RIC's own SDK is the candidate when that track opens, and the CSSL/FRAND caveat recorded in `00-hld-assessment.md` §3 still governs it. NONRTRIC's rApp Manager (pre-spec, "not intended for production"), SME/CAPIF, and RANPM (drags AGPLv3 MinIO) are tracked as roadmap, not integrated. |
| D2 | **rapp = RAN Intelligence service**: rApp/xApp model registry + Kafka training (unchanged) + recommendation inference + the **RIC integration layer** (ports/adapters). smo_sim gets every non-RIC actuator. |
| D3 | **data_sim = Data Platform**: per-vendor ingestion adapters → canonical PM/FM/CM tables in Postgres (+ raw in S3); store-only. The semi-synthetic enrichment (topology synthesis, UE placement, RSRP labeling) moves to bdt_engine as the **twin feature builder**. Synthetic data factory stays in data_sim. |
| D4 | **smo_sim's E2/R1 REST facades are deleted** (routers, schemas/tables, e2test/r1test harnesses). Their docs move to `artifacts/legacy/`. Claims-guardrails engineering blocker #2 (`/e2ap` route naming) is thereby resolved. |
| D5 (added v1.2) | **OCUDU compatibility is a strategic requirement, and the committed demo is: OCUDU gNB + mock UE (srsUE over ZMQ) + Open5GS + our RIC stack (NONRTRIC A1-PMS) driving a non-RT rApp closed loop.** Evidence basis (product owner's code-validated `artifacts/ocudu/` bundle + web verification): OCUDU 26.04's E2 is mature and Verified (E2SM-KPM v3 all report styles + E2SM-RC with real CU/DU control-action executors; live KPM demonstrated in the official tutorial against the dockerized O-RAN SC near-RT RIC), while **O1 in the OCUDU gNB tree is a code-confirmed GAP** (`lib/o1/` absent, zero NETCONF/YANG matches; the companion `ocudu_netconf` + `ocudu_o1_adapter` sidecars manage config by REWRITING the gNB config file and RESTARTING the gNB). Therefore: (a) the live closed-loop path to OCUDU is **E2 via the dockerized OSC near-RT RIC** (`github.com/srsran/oran-sc-ric`, compose-only, 7 containers, i-release images from `nexus3.o-ran-sc.org:10002`) with a thin CloudlyNet xApp executing **E2SM-RC Style 2 / Action 2 slice-level PRB-quota control** (the verified actuation surface; RC handover-trigger and E2SM-CCC also available); (b) the **near-RT placeholder (`nearrt_xapp`) is activated for LAB ONLY** as that xApp + compose stack — production near-RT remains deferred; (c) **O1 is the maintenance-window config track** (restart semantics), owned by smo_sim's `o1_netconf` adapter with corrected semantics, NOT the live loop; (d) the A1 leg lands via a spike: add the OSC `ric-plt-a1` mediator to the compose (it ships without one) with NONRTRIC A1-PMS's OSC southbound driving it; documented fallback if the mediator glue fights back: A1-PMS → OSC A1 Simulator as the A1-protocol record + direct xApp control API (labeled honestly). OCUDU-side code changes are NOT required for the demo; the enumerated optional-changes plan (E7.S7) covers richer actuation (E2SM-RC action coverage, runtime config in `remote_control`) and O1-in-gNB (graded weeks-to-months by the bundle — avoided, contribute-upstream path documented). |

## 2. Target service roles (containers, charts, images, ports UNCHANGED)

```
                       ┌──────────────────────── CloudlyNet core ────────────────────────┐
 vendors' PM/FM/CM ───►│ data_sim            bdt_engine                rapp              │
 (NanoLink CSV,        │ DATA PLATFORM ────► NETWORK DIGITAL TWIN ◄─── RAN INTELLIGENCE  │
  3GPP XML, VES,       │ adapters → canon    twin engines · feature    models (ES/LB/CCO/│
  OCUDU stream)        │ PG tables + raw S3  builder · evaluate API    MRO) · training   │
                       │ + synthetic factory · KPI tracking            worker · RIC layer│
                       │                     · LOOP DECISION HUB       (A1/xApp/R1 ports)│
                       └───────────┬──────────────────┬────────────────────┬─────────────┘
                                   │ canonical PM     │ loop.action        │ A1 policy intents
                                   │ feedback         ▼                    ▼
                       ┌─────────────────────── smo_sim ─────────────────┐ ┌─ non-RT RIC ──────┐
                       │ ACTUATION & INTEGRATION: NanoLink TR-069 plane  │ │ OSC NONRTRIC      │
                       │ (commands queue + edge agent), O1/NETCONF(OCUDU)│ │ A1-PMS (open) or  │
                       │ OCUDU WS metrics collector, Open M-Plane, CBRS  │ │ commercial SMO    │
                       │ SAS Domain Proxy, NMS northbound, agent mgmt    │ └───────┬───────────┘
                       └─────────────────────────────────────────────────┘         │ A1
                                                                        near-RT RIC (PLACEHOLDER;
                                                                        lab: OSC A1 Simulator) ─E2─► OCUDU
```

- `maveric_platform_bdt_engine` → **Network Digital Twin (NDT)**: twin engines (Maveric BDT GP;
  commercial engine slot), twin feature builder (from smo_sim pipeline stages 3–6), evaluation API
  (twin-KPI scoring moved from rapp), KPI tracking, and the closed-loop **decision hub** (policy +
  guardrail gates, route decision, feedback watch, rollback ordering).
- `maveric_platform_rapp` → **RAN Intelligence**: model lifecycle as today; day/tick `/infer` API
  contract preserved but twin evaluation delegated to NDT; RIC integration layer (§4.4),
  **non-RT-first**: the NONRTRIC A1-PMS connector is the first real RIC-plane executor, the
  near-RT tier stays a placeholder.
- `maveric_platform_smo_sim` → **Actuation & Integration**: NanoLink control plane as-is; actuator
  adapter framework with wired placeholders (O1/NETCONF via ocudu_netconf, OCUDU WebSocket
  collector, Open M-Plane, WINNF-TS-0016 SAS Domain Proxy, NMS northbound). E2/R1 deleted (D4).
  PM-ingestion API relocates to data_sim (gateway `/custom/**` re-pointed; frontend unchanged).
- `maveric_platform_data_sim` → **Data Platform**: ingestion framework + canonical store +
  synthetic factory.

**Closed loop:** rapp emits recommendation proposals → NDT evaluates on the twin + tenant loop
policy (`off|approval|auto`, mirroring `optimize_mode`) → dispatches: device config via smo_sim
adapters, or RAN policy via rapp RIC layer → feedback (device KPIs from smo_sim, canonical PM from
data_sim) → NDT guardrail watch → rollback through the same adapter. Defense in depth: smo_sim's
existing device-level guardrail watcher + auto-rollback stays.

## 3. Hard constraints

1. **Zero CI/CD change**, precisely: no NEW charts, pipelines, images, or ports, and no renames of
   any of them; lab-only components are compose-profile-only (like the edge agent). Code moves ride
   existing image streams. Helm `values.yaml` secretData env additions and kafka-chart topic values
   edits ARE allowed (the deployment recon's "moderate" class); reviewers must not reject those as
   CI/CD changes.
2. **Public API stability**: every gateway-routed endpoint the frontend uses keeps its contract
   (`/rapps/**` infer responses byte-compatible; `/custom/nybsys/**` request/response preserved
   even after re-pointing to data_sim). Internal refactors must not change envelope shapes.
3. **Data-layer contracts preserved during transition**: shared tables (`baselines`, `ue_datasets`,
   `bdt_models`, `training_jobs`) and S3 key conventions stay valid; EFS `/app/var/models` sharing
   between rapp and bdt persists (pickle/agent artifacts).
4. CLAUDE.md code conventions (Pydantic-first, type hints, platform logger, DRY), commit
   conventions, claims-guardrails for any user-facing copy. Product name: **CloudlyNet**;
   solution term: **Network Digital Twin**.
5. **Merge order is a hard constraint**: E0.S4 (the parent-repo naming commit: CLAUDE.md +
   marketing naming rules) merges BEFORE any other epic work starts, so every subsequent coding
   agent reads current naming guidance. Then E0 (gateway fix + contracts) → E1 → E2, with E3/E4 in
   parallel after E0, E5 and E7 after E2+E3+E4 (E7's lab-stack stories E7.S1/S2 may start earlier;
   its loop stories need E2/E3/E4 contracts), E6 continuous with its final gate last.

## 4. Shared contracts (all epics conform)

### 4.1 Kafka topics (provisioned via existing kafka chart topics-job + init-topics.sh)
- `maveric.ingest.pm.v1` — data_sim ingestion jobs (durable replacement for the thread pool) plus
  inline record batches from streaming sources (envelope frozen in Appendix A.5).
- `maveric.loop.proposal.v1` — rapp → NDT: recommendation proposals (payload frozen in Appendix A.1).
- `maveric.loop.action.v1` — NDT → executors: approved actions `{action_id, tenant_id, adapter,
  target, payload, policy_ref, expires_at}` (field contents frozen in Appendix A.2).
- `maveric.loop.feedback.v1` — executors → NDT: apply results + KPI windows (payload frozen in
  Appendix A.3).
- Existing `maveric.bdt.train.v1`, `maveric.rapp.train.v1` unchanged.

### 4.2 NDT APIs (bdt_engine :8000, X-API-Key; rapp reaches it via new env `NDT_BASE_URL` +
`NDT_API_KEY` = the bdt service key; gateway exposure of `/ndt/**` was "a later optional story"
here — **AMENDED 2026-08-04, E5.S7: it has landed.** `/v1/tenants/{t}/ndt/**` now proxies to
bdt_engine on the same group as `/bdt` and `/rapps`, under Cognito + `RequireMembership`, with
`BDT_API_KEY` injected server-side. It stopped being optional when E5.S5's approvals surface was
built: the browser reaches the platform only through the gateway, so without the route that screen
could not fetch a single row. bdt_engine still also accepts a direct `X-API-Key` on :8000 for
service-to-service callers)
- `POST /v1/tenants/{t}/ndt/evaluate` — body `{baseline_id, bdt_id, ue_dataset_id,
  scope: {"type": "tick"|"day", "tick"?: int, "day"?: int}, cell_configs: [{tick?, items:
  [{cell_id, cell_el_deg, on_off}]}], options?: {thresholds, energy_params, include}}` →
  tick: 200 sync; day: 202 + poll `GET /ndt/evaluate/{run_id}`. Response carries
  `guardrail_kpis, objective_kpis, per_tick_kpis, worst_tick_stats, raw_tick_data?` with the exact
  field shapes currently produced by rapp's `kpi_calculator` (so rapp's public response stays
  byte-compatible).
- `POST /v1/tenants/{t}/ndt/loop/proposals` (also via topic) · `GET /v1/tenants/{t}/ndt/loop/actions/{id}`
  · `GET|PUT /v1/tenants/{t}/ndt/loop/policy` (per-tenant `{mode: off|approval|auto, guardrails:
  {min_sinr_db, min_rrc_success_pct, max_outage_rate}, watch_window_min}`).

### 4.3 Canonical data schema (data_sim-owned, RLS-forced, in `artifacts/design/schemas.sql`)
- `pm_measurements(tenant_id, source, vendor, dn, metric, value double precision, unit,
  granularity_s int, ts timestamptz, day int, tick int, labels jsonb, raw_ref text)` — canonical
  vocabulary: TS 28.552 names where mappable, else `vendor:<name>`; monthly partitions.
- `fm_alarms(tenant_id, source, dn, alarm_id, severity, probable_cause, raised_at, cleared_at,
  state, raw jsonb)` · `cm_records(tenant_id, source, dn, params jsonb, captured_at, origin)`
- `ingest_jobs(tenant_id, job_id, source_type, status, stats jsonb, error, created_at, updated_at)`
- `vendor_dictionaries(vendor, source_metric, canonical_metric, transform, unit)`
- APIs: `POST /v1/tenants/{t}/ingest/uploads` (generalized; `source_type=nybsys_pm_csv` first),
  `GET /v1/tenants/{t}/ingest/jobs/{id}`, `GET /v1/tenants/{t}/data/pm` (+`/fm`,`/cm`) with
  dn/metric/time filters. Gateway adds `/v1/tenants/:tid/ingest/**` and `/data/**` → DATA;
  `/custom/**` re-points SMO→DATA (data_sim serves the legacy `/custom/nybsys/uploads` contract
  verbatim; smo_sim keeps the NanoLink device/edge `/custom/nybsys/edge-devices|devices/**` routes —
  **split rule: `custom/nybsys/uploads*` → DATA, device/edge ops stay SMO**; gateway needs a
  finer-grained route split here and this is the one deliberate gateway code change, plus the
  duplicate-route panic fix).
- Ingestion consumer runs **inside the data_sim API container** (background Kafka consumer thread;
  no new deployable). NanoLink adapter = parse/dedupe/aggregate + store canonical rows + raw S3;
  **no synthesis**.
- Feature-flag guard (`tenants.feature_flags['nybsys']`) is honored by data_sim the same way
  smo_sim honors it today (read-only check on the gateway-owned table).

### 4.4 RIC integration layer (rapp `app/ric/`) — non-RT-first (amended v1.1)
- `ports.py`: `RanControlPort` (submit_policy_intent / delete_policy_intent / policy_status /
  capabilities) and `RanDataPort` (subscribe → normalized records emitted to
  `maveric.ingest.pm.v1` via data platform API or topic). Pydantic `PolicyIntent` maps 1:1 onto an
  A1 policy-instance body.
- `adapters/nonrtric/`: the **OSC NONRTRIC A1-PMS connector** (Python, httpx): policy-type
  discovery, policy-instance CRUD, status. Pinned API: **v3, base path
  `{apiRoot}/a1-policy-management/v1`** (R1-AP v5.0-aligned; create = `POST /policies`;
  `GET /rics`, `/policy-types`, `/policies/{id}`, `/policies/{id}/status`), with an
  env-switchable fallback `A1PMS_API_MODE=v2` (`/a1-policy/v2`, create = `PUT`). Env:
  `A1PMS_BASE_URL`, `A1PMS_API_MODE` (default `v3`), `A1PMS_SERVICE_ID` (PMS `/services`
  registration + keepalive).
- **`a1_policy` loop-action executor lives here**: a background consumer inside the rapp
  container (no new deployable) consumes `maveric.loop.action.v1`, filters `adapter=a1_policy`,
  translates the A.2 recommendation payload into a CloudlyNet policy-type instance, applies it via
  A1-PMS, and publishes `maveric.loop.feedback.v1` (kind=`apply` from policy status; rollback per
  A.2 = `payload.rollback_of` set → DELETE the policy instance or re-apply the previous instance
  body).
- **Policy types**: CloudlyNet registers its own policy type (JSON schema derived from the
  Recommendation Table item shape: cell scope + `el_degree`/`on_off` targets) on the lab
  simulators; against commercial SMOs/RICs the connector discovers the RIC's advertised types and
  negotiates per RIC (the OSC multi-version southbound pattern).
- **Lab profile `ric-lab` (compose-only, images not source)**:
  `nexus3.o-ran-sc.org:10002/o-ran-sc/nonrtric-plt-a1policymanagementservice:2.11.0` + two
  `o-ran-sc/a1-simulator:2.8.1` containers (one `STD_2.0.0`, one `OSC_2.1.0`) modeled on the
  upstream `nonrtric/docker-compose` samples with tags re-pinned (upstream `.env` pins are stale);
  PMS rics configuration points at the simulators. Production posture: mirror images into our own
  registry; customer K8s installs use upstream charts, documented in `artifacts/ric/`, never a
  chart in our pipelines.
- `adapters/nearrt/`: **placeholder, LAB-ACTIVATED by D5/E7** — reserved adapter key
  `nearrt_xapp`; the E3.S7 contract doc stands, and EPIC-7 adds the lab executor: the
  **cloudlynet-xapp** (Python, forked from the `oran-sc-ric` `simple_rc_xapp` lineage) running in
  the dockerized OSC RIC's `python_xapp_runner`, executing E2SM-RC Style 2 / Action 2 PRB-quota
  control against OCUDU and reporting results back to the platform (A.3 feedback). Production
  near-RT integration remains deferred; FlexRIC findings in the contract doc unchanged (E42 + C
  SDK, CSSL lab-only terms).
- `packaging/r1/`: R1-shaped rApp manifest (metadata facade; loosely aligned to the OSC rApp
  Manager ASD prototype and CAPIF/Service Manager registration, both ROADMAP: rApp Manager is
  pre-spec and "not intended for production use").
- Claims wording: "we integrate O-RAN SC NONRTRIC, the open-source non-RT RIC" (label Today-lab
  once landed) · "A1-policy-aligned intents" · never "O-RAN compliant/certified".

### 4.5 Actuator adapter framework (smo_sim `app/actuators/`)
- `base.py`: `ActuatorAdapter` protocol — `capabilities()`, `apply(action) -> ack`,
  `read_back(target)`, `rollback(action)`, `health()`; command router keyed by
  `adapter` field on loop actions; NanoLink TR-069 refactored to implement it (no behavior change).
- Placeholders wired (module + registry entry + health endpoint + contract doc, no protocol code):
  `o1_netconf` (OCUDU via ocudu_netconf companion), `ocudu_ws_collector` (JSON metrics → data
  platform), `open_mplane`, `sas_domain_proxy` (WINNF-TS-0016 six-method client + grant state
  machine skeleton + 60 s transmit-shutdown rule), `nms_northbound`.
- Loop feedback hook: command ack/guardrail events also publish `maveric.loop.feedback.v1`.

### 4.7 OCUDU demo-lab contract (added v1.2; owned by EPIC-7)

Two compose profiles, both lab-only, zero CI/CD change:
- **`ran-lab`** (the RAN under test): Open5GS (dockerized, the tutorial-verified core pairing) +
  **OCUDU gNB** pinned to 26.04 / HEAD `050a2bb72e` (built from `gitlab.com/ocudu/ocudu.git`; ZMQ
  virtual RF; `enable_du_e2` + `enable_cu_cp_e2` pointed at the RIC's e2term; `metrics.enable_json`
  + `remote_control` on) + **srsUE** (srsRAN_4G repo, ZMQ, the RIC tutorial's documented UE
  pairing; OAI nrUE is the recorded alternative for the NTN variant) + the **dockerized OSC
  near-RT RIC** (`github.com/srsran/oran-sc-ric`: dbaas, rtmgr_sim, submgr, e2term, appmgr, e2mgr,
  python_xapp_runner; i-release images from `nexus3.o-ran-sc.org:10002`; version pins recorded in
  our own `.env`).
- **`ric-lab`** (§4.4, unchanged): NONRTRIC A1-PMS 2.11.0 + OSC A1 Simulators.

Bindings:
- **cloudlynet-xapp** (Python, `simple_rc_xapp` lineage, runs in `python_xapp_runner`): consumes a
  policy (A1 callback when the mediator spike lands; REST control endpoint as fallback), executes
  **E2SM-RC Style 2 / Action 2 slice PRB-quota control** on OCUDU, exposes its apply/read state;
  the rapp RIC layer bridges xApp state to `maveric.loop.feedback.v1` (A.3 shapes). This is the
  LAB executor for adapter key `nearrt_xapp` (A.4 note updated).
- **A1 spike (E7.S4)**: add OSC `ric-plt-a1` (a1mediator) to the oran-sc-ric compose (it ships
  WITHOUT one) + rtmgr_sim route entries for the A1 RMR message types; NONRTRIC A1-PMS reaches it
  via the OSC southbound. Timeboxed; fallback = A1-PMS → A1 Simulator as the A1-protocol record
  while the xApp is driven via its REST control (every demo asset labels which variant ran).
- **PM in**: OCUDU JSON metrics over WebSocket → `ocudu_ws` adapter (E4, promoted implementable)
  → canonical `pm_measurements`; optionally KPM indications via kpm_mon_xapp for comparison.
- **O1 (maintenance-window track, NOT the live loop)**: `ocudu_netconf` + `ocudu_o1_adapter`
  sidecars manage config by rewriting the gNB config file and RESTARTING the gNB; smo_sim's
  `o1_netconf` placeholder contract carries these restart semantics explicitly.
- Wording rule for every demo asset: "integrates the O-RAN SC near-RT RIC and NONRTRIC (open
  source)", "E2SM-RC-based control executed by the RIC we integrate"; never "O-RAN
  compliant/certified"; results labeled Simulation/Lab rung.

### 4.6 Twin feature builder (bdt_engine `app/feature_builder/`)
- Input: canonical PM via data platform API (`/data/pm`); output: `baselines` + `ue_datasets`
  rows + S3 artifacts in the existing key conventions (so BDT/rApp training is untouched).
- Logic moved from `smo_sim/app/lib/nybsys/pipeline.py` stages 3–6 and reconciled with data_sim's
  golden generators (one shared placement/geometry library; the duplication noted in recon dies).
- Every derived artifact is labeled `semi_synthetic=true` in `baselines.stats` (claims honesty).

## 5. Epic map (authoring in `epics/`)

| Epic | Title | Depends on |
|---|---|---|
| E0 | Platform hygiene: gateway route fix, contract docs, repo-wide CloudlyNet rebrand | — |
| E1 | Data Platform: canonical schema, adapter framework, NanoLink store-only adapter, ingest API move | E0 |
| E2 | NDT consolidation: evaluate API, feature builder, KPI tracking, decision hub | E1 |
| E3 | RAN Intelligence: RIC layer (non-RT-first), NONRTRIC A1-PMS connector + ric-lab profile, a1_policy executor, near-RT placeholder, R1 facade | E0 |
| E4 | Actuation & Integration: adapter framework, E2/R1 deletion, placeholders, scale-out fixes | E0 |
| E5 | Closed loop end-to-end + rollback demo (marketing blocker #3) | E2, E3, E4 |
| E7 | OCUDU end-to-end demo: ran-lab stack, OSC RIC integration, cloudlynet-xapp, A1 spike, OCUDU PM ingestion, demo script, O1 track + OCUDU-changes contingency | E1, E2, E3, E4 |
| E6 | Docs/design/context updates + claims re-verification | continuous, final gate |

## Appendix A. Frozen cross-epic message contracts (payload detail for §4.1)

Added 2026-07-16 to close cross-epic payload drift found in E2/E3/E4/E5 review. These shapes are
part of the freeze: every producer and consumer conforms verbatim. Additive OPTIONAL fields are
allowed (consumers ignore unknown fields); renames, type changes, and discriminator changes are
deviations that re-open the freeze.

### A.1 `maveric.loop.proposal.v1` (rapp -> NDT; also the REST body of `POST /v1/tenants/{t}/ndt/loop/proposals`)

```json
{
  "event": "loop.proposal",
  "version": 1,
  "proposal_id": "<uuid5(NAMESPACE_URL, 'loop-proposal:' + run_id)>",
  "tenant_id": "<uuid>",
  "source": {"service": "rapp", "rapp_id": "es", "rapp_model_id": "...", "run_id": "<inference run id>"},
  "refs": {
    "baseline_id": "baseline-01",
    "bdt_id": "bdt-01",
    "ue_dataset_id": "dataset-01",
    "scope": {"type": "day", "day": 0}
  },
  "per_tick_recommendations": [
    {"tick": 0, "items": [{"cell_id": "cell_1", "el_degree": 4.0, "on_off": true}]}
  ],
  "kpi_summary": {"guardrail_kpis": {}, "objective_kpis": {}},
  "target_adapter_hint": "nanolink_tr069",
  "created_at": "2026-07-16T10:00:00Z"
}
```

Rules:
- `tick` is an INTEGER 0-23, never a string. `scope` uses the §4.2 shape (`{"type": "tick", "tick": 3}` for tick scope).
- `items` reuse rapp's public Recommendation Table field names (`cell_id`, `el_degree`, `on_off`)
  so rapp forwards its `per_tick_recommendations` unmodified; the NDT consumer maps
  `el_degree` -> `cell_el_deg` when it builds §4.2 `cell_configs`.
- `target_adapter_hint` takes values from the A.4 registry; producer default `nanolink_tr069`.
- `kpi_summary` is optional and carries the already-computed `guardrail_kpis`/`objective_kpis`
  dicts verbatim (no recomputation). Optional additive fields: `request_id`.
- Kafka message key = `tenant_id` bytes.

### A.2 `maveric.loop.action.v1` field contents + executor translation seam

The §4.1 envelope `{action_id, tenant_id, adapter, target, payload, policy_ref, expires_at}` is
fixed; this appendix pins the field CONTENTS:

- `adapter`: a key from the A.4 registry. NDT default: `nanolink_tr069`.
- `target`: JSON OBJECT. NDT dispatches cell-scoped targets `{"cell_id": "c1", "tick": 0}`;
  executors must also accept device-scoped `{"device_id": "..."}` targets (used by canned/demo
  proposals). Executors never receive a bare string.
- `payload` for change actions: EITHER the recommendation form
  `{"cell_el_deg": 6.0, "on_off": true, "rollback_of": null}` OR an explicit write set
  `{"writes": [{"path": "...", "value": "..."}], "rollback_on_fail": true}`. Adapters accept both.
- `payload` for rollback actions: `{"rollback_of": "<the reverted action_id>"}`.
- `policy_ref`: JSON OBJECT, never a string: `{"policy_id": "...", "mode": "auto",
  "watch_window_min": 15}` (the tenant policy snapshot at decision time). Executor-side
  persistence of `policy_ref` uses jsonb.

Translation seam (binding): the EXECUTOR ADAPTER owns cell -> device resolution and
recommendation -> managed-parameter write translation, because the executor service owns the
device registry and the managed-params catalogue. For `nanolink_tr069` (smo_sim): `target.cell_id`
resolves to a device via setting `NANOLINK_CELL_DEVICE_MAP` (JSON `{"<cell_id>": "<device_id>"}`);
the recommendation form translates to writes (`on_off=false` -> ReferenceSignalPower =
`LOOP_ES_POWER_SAVE_DBM`, `on_off=true` -> ReferenceSignalPower = `LOOP_ES_POWER_NORMAL_DBM`;
`cell_el_deg` has no NanoLink managed parameter and is recorded as skipped in the ack detail).
The NDT dispatches recommendations verbatim and never embeds device or catalogue knowledge.

Rollback routing (binding): the executor's dispatch router inspects `payload.rollback_of`; when it
is set the router calls `adapter.rollback(action)`, never `apply()`.

### A.3 `maveric.loop.feedback.v1` (executors -> NDT)

```json
{
  "schema": "maveric.loop.feedback.v1",
  "feedback_id": "<uuid4>",
  "action_id": "<loop action id, or null for unsolicited device events>",
  "tenant_id": "<uuid>",
  "adapter": "nanolink_tr069",
  "kind": "apply",
  "status": "applied",
  "command_id": "<executor-side command id or null>",
  "kpis": {"sinr_avg_db": 12.1, "rrc_success_pct": 97.2, "outage_rate": 0.01},
  "detail": {"readback": {}, "mismatch": {}, "error": "", "rollback_command_id": ""},
  "observed_at": "2026-07-16T00:05:00Z"
}
```

Kind/status matrix (one contract covers apply acks, KPI windows, breaches, and rollbacks):
- `kind="apply"`: dispatch and agent-ack results; `status` in
  `queued|applied|failed|rejected|duplicate|expired`. The NDT transitions actions only on
  `applied`/`failed`; the other statuses are audit-only (logged, committed, skipped).
- `kind="kpi_window"`: periodic KPI observation, published by the executor's telemetry path for
  every device holding a loop action inside its watch window; `status` in `ok|breach` (the
  executor's own verdict); `kpis` REQUIRED. The NDT re-evaluates breach independently against the
  tenant guardrails; this is where `min_rrc_success_pct` is enforced.
- `kind="guardrail_breach"`: the executor's device-level watcher fired and rolled back locally;
  `kpis` carries the breach values. The NDT treats it as a breach signal for the watch.
- `kind="rollback"`: ack of a rollback command; `status` in `rolled_back|failed`.
- `kpis`/`detail` sub-fields are optional per kind; `observed_at` is RFC3339 UTC. Kafka message
  key = `tenant_id` bytes. Optional additive fields: `request_id`.

### A.4 Actuator/adapter key registry (one namespace)

One namespace shared by the action `adapter` field, the proposal `target_adapter_hint`, and every
executor-side registry. Bare `nanolink` is NOT a valid key.

| Key | Executor | Plane |
|---|---|---|
| `nanolink_tr069` | smo_sim NanoLink adapter (E4) | TR-069/CWMP device plane |
| `o1_netconf` | smo_sim placeholder (E4) | NETCONF/YANG via ocudu_netconf |
| `ocudu_ws_collector` | smo_sim collector (E4) | data plane only (no apply) |
| `open_mplane` | smo_sim placeholder (E4) | Open M-Plane |
| `sas_domain_proxy` | smo_sim placeholder (E4) | CBRS SAS Domain Proxy |
| `nms_northbound` | smo_sim placeholder (E4) | NMS northbound |
| `a1_policy` | rapp RIC layer: NONRTRIC A1-PMS connector (E3) | A1 policy intents via the open non-RT RIC |
| `nearrt_xapp` | LAB executor: rapp `NearRtLabExecutor` → cloudlynet-xapp on the dockerized OSC RIC (E7, v1.2); production near-RT still deferred (was `flexric_xapp` pre-v1.1) | xApp-mediated control (E2SM-RC PRB quota in lab) |

E0.S3's `artifacts/design/internal-contracts.md` records this table (section 6) as the
adapter-key contract of record.

### A.5 `maveric.ingest.pm.v1` inline-records envelope (streaming sources)

The topic carries two message kinds, discriminated by the single field `kind`:
- `kind="job"` (default when the field is absent, for backward compatibility): the E1.S2
  ingest-job message `{schema, kind, tenant_id, job_id, source_type, params, requested_at}`.
- `kind="records"`: inline record batches from streaming sources (E4's OCUDU WS collector today;
  the deferred near-RT KPM stream later), stored directly by the data platform (no adapter
  `validate_params`, no `ingest_jobs` row; E1.S8 owns the consumer branch):

```json
{
  "schema": "maveric.ingest.pm.v1",
  "kind": "records",
  "tenant_id": "<uuid>",
  "batch_id": "<uuid4>",
  "source_type": "ocudu_ws",
  "vendor": "ocudu",
  "records": [
    {"dn": "gnb/3584/cell/12345", "metric": "DRB.UEThpDl", "value": 12.34, "unit": null,
     "granularity_s": 1, "ts": "2026-07-16T10:00:00Z", "labels": {"gnb_id": "3584"}}
  ]
}
```

Rules: the discriminator is always `kind` and the source field is always named `source_type`
(never `source`, never an `event` field). `metric` carries the SOURCE metric name; the data
platform maps it to the canonical vocabulary via `vendor_dictionaries` at store time. Known
streaming `source_type` values: `ocudu_ws` (vendor `ocudu`, E4); `nearrt_kpm_stream` is RESERVED
for the deferred near-RT placeholder track (was `flexric_kpm_stream` pre-v1.1; never emit it until
that track opens). Kafka message key = `tenant_id` bytes.

### A.6 Migration numbering (cross-epic order)

`artifacts/migration/` numbering is assigned here to prevent collisions; each epic's rollout
section repeats its own entries:

| Number | File | Owner |
|---|---|---|
| 011 | `011_data_platform_canonical.sql` | E1 |
| 012 | `012_drop_e2_r1.sql` | E4 |
| 013 | `013_commands_loop_columns.sql` | E4 |
| 014 | `014_ndt_loop.sql` | E2 |
| 015 | `015_ndt_loop_policy.sql` (seed-only, against E2's `loop_policies`) | E5 |
