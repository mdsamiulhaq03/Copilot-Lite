# CloudlyNet Re-architecture: HLD Assessment (pre-freeze)

Date: 2026-07-16 · Author: Claude (recon: 13-agent workflow `wf_04cd3758-323`, per-agent reports in session scratchpad `reports/`)
Status: awaiting 4 strategic decisions, then FREEZE.

Grounding: latest marketing/product plan (`artifacts/marketing/`, repositioned 2026-07-13, renamed CloudlyNet 2026-07-16). The legacy KB (`artifacts/marketing/legacy_outdated/`) is reference-only and loses every conflict.

---

## 1. Plan-vs-reality corrections (from code recon)

These facts contradict assumptions in the stated plan and the HLD must be built on them:

1. **`/custom-pm-ingestion` lives in smo_sim, not data_sim.** The NybSys PM CSV pipeline is
   `smo_sim/app/lib/nybsys/pipeline.py` + `app/api/v1/custom/nybsys/` (gateway maps `/custom/**` to SMO).
   data_sim is pure synthetic generation only (topology / traffic / mobility, inline, no Kafka).
2. **The pipeline is 2 parts storage, 4 parts synthesis.** Stages: load+dedupe, hourly day/tick
   aggregation (real), then topology synthesis (random lat/lon!), config defaults, UE placement,
   TR 38.901 RSRP labeling (all synthetic). Only site/cell inventory, time range, and per-hour
   connection counts are real. No PM counter ever lands in Postgres today (S3 audit CSV only).
3. **`/infer?model_id=...&day=0` (rapp day-scope evaluation)** returns two separable things:
   twin-predicted network KPIs (`guardrail_kpis`, `objective_kpis`, `per_tick_kpis`, `worst_tick_stats`;
   computed by BDT GP prediction + attachment inside rapp's `plot_builder`/`kpi_calculator`) and the
   **Recommendation Table** (`per_tick_recommendations[{tick, items[{cell_id, el_degree, on_off}]}]`,
   from PPO predictions only). The seam is clean in code: recommendation generation vs twin
   evaluation vs KPI aggregation are separate modules.
4. **rApp/BDT never push anything to smo_sim.** No service-to-service HTTP anywhere in the Python
   mesh. Coupling is shared Postgres tables (`baselines`, `ue_datasets`, `bdt_models`,
   `training_jobs` read cross-service via duplicate ORM defs) + hardcoded S3 key conventions
   (`{tenant}/baselines/{bid}/*`, `{tenant}/ue/{did}/synthetic_dataset[_mobility].csv`) in 4 services
   + a shared EFS/`app_volume` at `/app/var/models` (BDT pickles, RL zips).
5. **smo_sim's E2/R1 endpoints are dead-end scaffolding**: not routed through the gateway,
   measurement tables have no writer, E2SM-RC control actions insert `pending` rows nothing
   processes, R1 subscriptions never notify. Deleting them breaks nothing.
6. **The only real closed loop is the NanoLink plane**: `commands` table (claim-on-fetch, 60 s
   lease, 5 attempts, dead-letter) → edge agent (in-agent CWMP ACS :7547; GPV/SPV/GPN/Reboot; no
   firmware Download RPC) → verified read-back ack → guardrail watcher (SINR floor / RRC ≥95%
   within 15 min) auto-rollback. Self-optimizer EWMA state is in-memory (single-replica assumption);
   lease sweep runs only at startup.
7. **Gateway HEAD panics at startup** (verified by build+run): duplicate `/v1/agent/*path`
   registration, `cmd/gateway/main.go:224-227` vs `:247`. Deployed images predate it. Must be fix #0.
8. **Training/inference pattern already matches the plan**: rapp-worker consumes
   `maveric.rapp.train.v1`, trains, uploads artifact to S3; inference downloads the model on first
   use (verified download-at-inference in `data_loader.py`). Same for bdt-worker on
   `maveric.bdt.train.v1`. No Kafka anywhere in smo_sim/data_sim (handlers are dead code).

## 2. CI/CD constraints (minimal-change mandate)

From `maveric-deployment` recon: ArgoCD apps point at chart paths; 15 Jenkins pipelines hardcode
image names + `yq` write-back paths; cross-service DNS and API keys are frozen base64 in
`values.yaml secretData`; prod deploys into namespace `staging` with images named `*-staging`
(rename forbidden by repo policy).

- **Cheap:** moving code *within* an image stream (bdt api↔worker, rapp api↔worker share images).
- **Moderate:** moving an endpoint between services (gateway secretData URL/key edits; ingress
  untouched since everything flows through `/v1` on the gateway).
- **Expensive (avoid):** new deployables, renaming services/charts/releases/ports, touching the
  shared EFS `/app/var/models` contract.

**Consequence: the four submodules keep their containers/charts/images; only their internal role
and module boundaries change.** New closed-loop Kafka topics ride the existing kafka chart
topics-job. FlexRIC (or any RIC) is compose/on-prem profile first (like edge agent, which has no
chart), promoted to a chart only when a customer deployment needs it.

## 3. External validation (specs, licenses, market)

- **FlexRIC (EURECOM)**: near-RT-only (no non-RT RIC, no rApp/A1/R1/O1). xApps are separate
  processes over the custom **E42** SCTP interface; C/C++ SDK covers KPM v2/v3 + RC v1.03; the
  Python SDK covers only custom SMs (MAC/RLC/PDCP/GTP/SLICE), **not KPM/RC**. Actively maintained
  (dev commits May 2026) but last tag v2.0.0 (Dec 2023); consumers pin dev commits.
  **LICENSE BLOCKER: `dev` = CSSL v1.0 (since 2026-03-31), master = OAI-PL v1.1 — Apache-derived
  text but the patent grant is royalty-free only for study/testing/research and requires FRAND
  negotiation for commercial use. GitLab's "Apache-2.0" badge is a misdetection. Vendoring the
  full codebase into our commercial repo is a legal exposure, not an engineering choice.**
- **OCUDU**: LF-hosted (OCUDU Ecosystem Foundation, NOT LF Networking), seeded from srsRAN
  Project, BSD-3-Clause (permissive), v26.04 (Apr 2026), next 26.10. Full gNB (CU-CP/CU-UP/DU+L1).
  Integration surfaces for us: E2 agents (E2SM-KPM v3.00, 27/287 metrics; RC limited style 2; CCC
  flag) via a real RIC; **JSON metrics over WebSocket + remote_control API (low-friction)**;
  O1/NETCONF via companion `ocudu_netconf` / `ocudu_o1_adapter`; single YAML static config.
  No TR-069 anywhere. Explicitly out of scope for OCUDU: SMO, RIC, RU.
- **RIC market (mid-2026)**: near-RT RIC merchant market nearly extinct (Broadcom killed VMware's,
  Juniper's sold to Nokia, Nokia deprioritized, "xApp ecosystem not developing meaningfully" per
  Telus). Commercial energy is at the **non-RT/SMO rApp tier**: Ericsson EIAP (60+ rApps, first
  live third-party rApp over R1 at AT&T July 2025), Nokia MantaRay SMO, Samsung CognitiV NOS.
  **xApp portability across RICs is effectively zero** (E2AP v1–v4 + E2SM version fragmentation;
  every RIC has its own SDK). A1 (JSON policy) is the most portable seam; R1 is young but real.
- **PM/FM/CM uniformity: NO.** 3GPP standardizes the container (TS 32.432/32.435 XML, TS 28.550
  streaming) and measurement definitions (TS 28.552), but vendors ship proprietary counters inside
  (Ericsson pmXxx), or proprietary formats (Nokia OMeS, Huawei OSS CSV/XML). TR-069/TR-196+TR-157
  femtocell world is separate again. Industry-converged answer (ONAP DCAE PM-Mapper→VES, O-RAN SC
  ranpm, TM Forum ODA, Bodastage): **canonical internal schema + per-vendor adapter plugins**, not
  one pipeline per vendor and not an assumption of uniformity.
- **CBRS SAS**: Domain Proxy per WINNF-TS-0016 (v1.2.7): six batched JSON/HTTPS methods
  (registration, spectrumInquiry, grant, heartbeat, relinquishment, deregistration), per-CBSD
  grant state machine (Idle→Granted→Authorized), 60 s transmit-shutdown, mutual-TLS with WInnForum
  PKI DP certs. Magma's Domain Proxy is the open-source reference. Femtocells = Category A.
  (WINNF-TS-0245 is the PAL DB spec, not the DP spec.)

## 4. Proposed target HLD (to freeze after Q1–Q4)

Same four containers, new roles ("the brain never changes; only the southbound does"):

| Submodule (unchanged chart/image) | New role |
|---|---|
| `maveric_platform_bdt_engine` | **Network Digital Twin (NDT) service** — twin engines (Maveric BDT GP today; commercial physics engine slot), **twin feature builder** (the semi-synthetic enrichment moves here from smo_sim's pipeline stages 3–6), **evaluation API** (twin KPI scoring moves here from rapp's plot_builder/kpi_calculator), KPI tracking, and the **closed-loop decision hub**: policy + guardrail evaluation, route decision (device actuation vs RIC path), feedback watch, rollback ordering. |
| `maveric_platform_rapp` | **RAN Intelligence service** — rApp/xApp model registry + Kafka training (unchanged), recommendation inference (Recommendation Table only; twin evaluation via NDT API), **RIC integration layer** (hexagonal `RanControlPort`/`RanDataPort`): A1-policy adapter family, per-RIC thin xApp adapters (FlexRIC E42 first), R1-shaped rApp packaging facade. The RIC itself deploys as external upstream containers, never vendored (license). |
| `maveric_platform_smo_sim` | **Actuation & Integration service** — NanoLink TR-069 control plane (as-is), actuator adapter framework with wired placeholders: O1/NETCONF (OCUDU via ocudu_netconf), OCUDU WebSocket metrics collector, Open M-Plane, CBRS SAS Domain Proxy (WINNF-TS-0016 state machine), northbound NMS/EMS connectors, edge/collector agent management. E2/R1 CRUD facades deleted (or archived behind a sim flag, Q4). |
| `maveric_platform_data_sim` | **Data Platform service** — multi-vendor ingestion framework: source adapters (NanoLink CSV first; 3GPP 32.435 XML PM, VES listener, OCUDU JSON stream next) → per-vendor mapping dictionaries → **canonical PM/FM/CM tables in Postgres** (+ raw payloads in S3). Synthetic data factory stays. Ingestion becomes store-only; enrichment leaves. |

**Closed loop (target):** rApp inference emits recommendations → NDT evaluates against the twin +
policy/guardrails → dispatch: device-level config via smo_sim adapters (TR-069 today, O1/M-Plane/
SAS next) or RAN-policy via rapp's RIC layer (A1/xApp) → feedback from canonical PM (data_sim) +
device KPIs (smo_sim) → NDT guardrail watcher → rollback through the same adapter that applied.
Defense in depth: NDT owns network-level policy gating; the actuator keeps its device-level
guardrail watcher + auto-rollback (already built and proven).

New Kafka topics (existing chart topics-job): `maveric.loop.recommendation.v1`,
`maveric.loop.action.v1`, `maveric.loop.feedback.v1`, `maveric.ingest.pm.v1` (names TBD in LLD).

**Answers to the plan's open questions:**
- *Uniform PM/FM/CM across vendors?* No (see §3). One ingestion service, pluggable per-vendor
  adapters, canonical schema. Prefer TS 28.552 measurement names + VES-style envelopes as the
  canonical vocabulary so O1-compliant vendors map near-1:1.
- *rApp as Kafka training consumer?* Already exactly how it works; keep. Train offline in
  rapp-worker, publish artifact, download-at-first-inference. xApp adapters follow the same
  pattern (model artifact loaded at adapter startup).
- *How rApps/xApps work in FlexRIC vs commercial RICs?* FlexRIC has no rApp tier at all; xApps are
  E42 processes on its SDK. Commercial rApp tiers (EIAP/MantaRay/CognitiV) each have their own SDK
  with R1 hardening underway. Hence: our intelligence stays at the non-RT tier in our own platform
  (we are the C-SON brain), and per-RIC thin adapters carry intents down (A1 policy preferred,
  bespoke xApp per RIC when sub-second enforcement is needed). Never port an xApp across RICs;
  write a thin new one per RIC SDK.

## 5. Open decisions (asked 2026-07-16)

- **Q1 FlexRIC licensing posture** — integrate-as-external vs vendor vs O-RAN SC default.
- **Q2 RIC integration home** — rapp (with models) vs smo_sim (with actuators).
- **Q3 Ingestion home** — data_sim Data Platform (+ NDT feature builder) vs keep in smo_sim vs into NDT.
- **Q4 E2/R1 facade disposal** — delete vs archive behind `/sim/e2-model` feature flag.

## 6. Marketing/plan drift register (legacy KB vs latest plan)

Authoritative: current pack. Applied 2026-07-16: CloudlyNet rename (management), Lite/Site/Advanced
offering ladder reinstated with rung labels, Network Digital Twin naming, claims-guardrails §8
added (NanoLink = LTE FDD Band-3 femtocell, never "5G NR TDD"; legacy figures <100W / $2K/node/yr /
15-min deploy / middleprise TAM are unverified legacy targets; NybSys FCC/field claims attributed
to NybSys). Dead legacy items (do not resurrect): "network optimization models, never rApps" rule
(inverted by the open-RIC narrative), SaaS-first posture (now on-prem-first, Building), brand triad
"Deploy in minutes · Optimize in hours · Prove ROI in days", Magma/Open5GS core-compatibility
claims (fail the wire-protocol test), named US carrier account list, "zero-touch"/"carrier-grade"
language, net@cloudly.io / cloudly.io/net contact block.

## 7. Debt/risks the epics must carry

- Gateway duplicate-route panic (fix first).
- Secrets in git (base64 secretData; Jenkins webhook tokens inline) — security story.
- Shared-table tri-ownership + S3 conventions: formalize contracts before moving owners.
- Single-replica assumptions in smo_sim (in-memory EWMA, thread-pool ingestion, startup-only sweeps).
- PM ingestion durability (thread pool, orphaned `processing` rows) — move to Kafka job.
- Claims blocker #2: `etwoint/e2ap` route naming (resolved by Q4 disposal).
- Repo-wide rebrand of non-marketing surfaces (frontend UI strings, design docs, `<platform-host>`
  domain migration) — pending story.

## 8. Addendum (2026-07-16, v1.1): non-RT RIC pivot research

Product-owner directive: focus the RIC track on the non-RT tier. Verified findings (full report:
session scratchpad `reports/nonrtric.md`):

- **O-RAN SC NONRTRIC is the only credible open-source non-RT RIC** (checked alternatives: ONAP
  CCSDK-ORAN is its upstream, not an alternative; OAI has none; ONF SD-RAN is near-RT only;
  BubbleRAN rapp_sdk is vendor-locked). Release train J/K/L/M, latest M = 2025-12-20.
- Minimal integration set: **A1 Policy Management Service 2.11.0** (Java, Apache-2.0, dev active
  upstream in ONAP) + **A1 Simulator 2.8.1** (Python; terminates A1 and simulates a near-RT RIC's
  policy behavior; supports OSC_2.1.0 / STD_1.1.3 / STD_2.0.0). Images from
  `nexus3.o-ran-sc.org:10002/o-ran-sc/*`; official docker-compose samples exist but pin stale
  tags, so we maintain our own compose.
- **API trap**: the recommended "v3" A1-PMS API (R1-AP v5.0-aligned) serves at base path
  `{apiRoot}/a1-policy-management/v1`; create is `POST /policies`. The older v2 API
  (`/a1-policy/v2`) uses PUT and has bulk `/policy-instances`.
- **License flip vs FlexRIC**: Apache-2.0, so the open RIC can ship with commercial deployments.
  Cautions: keep the O-RAN ALLIANCE attribution in the vendored pms-api-v3 spec file; RANPM drags
  AGPLv3 MinIO (do not ship RANPM); never use O-RAN compliance language; mirror images.
- **Not integrated (roadmap)**: rApp Manager (pre-spec, "not intended for production", requires
  ONAP ACM + K8s), SME/CAPIF (v0.2.x), RANPM, ICS (add only when EI/DME brokering is needed).
- **Near-RT tier = reserved placeholder** (`nearrt_xapp`): xApp SDKs are per-RIC and non-portable;
  FlexRIC remains the lab candidate under its CSSL lab-only terms (§3) when that track opens.

## 9. Addendum (2026-07-17, v1.2): OCUDU-first demo research

Product-owner directive: OCUDU compatibility is of paramount strategic importance; the committed
demo is OCUDU + mock UE + Open5GS + our RIC with a non-RT rApp. Findings (sources: the
code-validated `artifacts/ocudu/` bundle at OCUDU 26.04 HEAD `050a2bb72e`, plus web verification):

- **E2 is OCUDU's verified, code-mature control surface.** `lib/e2/` carries real E2SM-KPM
  (CU+DU measurement providers, styles 1–5, 27/287 metrics) and E2SM-RC service models including
  **separate CU/DU control-action executors**; the official near-RT RIC tutorial demonstrated a
  live KPM feed (`DRB.UEThpDl` indications) into the dockerized O-RAN SC RIC; community logs
  confirm E2AP connections (with version-pinning friction against some third-party RICs).
- **O1 in the OCUDU gNB is a code-confirmed GAP** (bundle Phase 3, exhaustive: `lib/o1/` absent,
  zero NETCONF/YANG matches in `lib/` + `apps/`; in-gNB O1 graded weeks-to-months). The companion
  `ocudu_netconf` + `ocudu_o1_adapter` sidecars implement O1 by **rewriting the gNB config file
  and restarting the gNB** — a maintenance-window surface, not live-loop actuation. One useful
  hook exists: a DU flag for SMO-commanded cell auto-activation.
- **The dockerized OSC near-RT RIC** (`github.com/srsran/oran-sc-ric`): compose-only (no K8s),
  7 containers (dbaas, rtmgr_sim, submgr, e2term, appmgr, e2mgr, python_xapp_runner), i-release
  images from `nexus3.o-ran-sc.org:10002`, five stock Python xApps — monitoring (KPM styles 1–5)
  and **control: `simple_rc_xapp` = slice-level PRB-quota (E2SM-RC Style 2, Action 2)**, an RC
  handover-trigger xApp, and an E2SM-CCC xApp. **No A1 mediator is included** — adding OSC
  `ric-plt-a1` + rtmgr routes is the enumerated glue (spike), with the A1-Simulator hybrid as the
  pre-approved fallback.
- **Mock UE**: srsUE (srsRAN_4G) over ZMQ is the RIC tutorial's documented pairing (`ue_zmq.conf`);
  repos archived but pinnable; OAI nrUE is the recorded alternative (and the bundle's NTN-track
  UE). Open5GS is the tutorial-verified core.
- **Verdict:** OCUDU works with an open-source RIC chain today (works-with-integration-effort:
  version pinning + A1-mediator glue); **no OCUDU code changes are required for the demo**. The
  optional-changes plan (richer E2SM-RC actions like cell on/off, runtime `remote_control` config,
  KPM coverage, sidecar hot-reload instead of restart) is written in EPIC-7 S7 with bundle-graded
  sizing. NTN context: the bundle is an NTN compliance investigation (xrcomm track); the GEO NTN
  tutorial variant needs a commercial NTN UE (Amarisoft), so the demo stays terrestrial ZMQ.
