# artifacts/ingestion/ — Data-Requirements Bundle (current vs industry standard)

Audit of every data point CloudlyNet ingests or consumes today (PM / CM / FM / training data),
against the industry-standard data set a C-SON / RAN Optimization platform with a Network Digital
Twin needs, with a per-field gap analysis and per-model verdict.

Compiled 2026-07-23. All "current" rows are code-extracted with `file:line` evidence; all
"industry" rows are web/spec-researched with `spec_ref` + `source_url` (3GPP counter and attribute
names verified against downloaded spec text — TS 28.552, TS 32.425, TS 28.541, TS 28.658,
TS 28.662, TS 28.628, TS 32.522, TS 37.320, TS 28.623/_3gpp-common-fm.yang — not from memory).

## Files

| File | Rows | What it is |
| --- | --- | --- |
| `current_pm_counters.csv` | 88 | Every PM field the platform accepts today: NybSys NanoLink CSV (4 required + 10 optional counters + vendor-column disposition incl. the ~68 ignored columns), upload-flow control fields, edge-agent telemetry metrics (tiers 1–3), `device_kpis` columns; EPIC-1 `pm_measurements` rows marked `planned` |
| `current_cm_fields.csv` | 129 | Topology/config surface: data_sim synthetic topology/config columns, the 24 TR-069 (CWMP) managed parameters (device CM write path), PM-synthesized topology.csv/config.csv columns, edge config snapshots + device inventory; EPIC-1 `cm_records`/`vendor_dictionaries` marked `planned` |
| `current_fm_fields.csv` | 57 | Edge-agent alarm GPV set + `AlarmIn` wire DTO, event parser outputs, `device_events` columns; `notes` column carries the **not-persisted alarm-history caveat**; EPIC-1 `fm_alarms` marked `planned` |
| `current_training_data_fields.csv` | 275 | Field-by-field inputs of the Bayesian Digital Twin (BDT) training/inference and the rApp models (MRO, ES/LB/CCO RL), with `consumer` and `role` columns (`model-input` vs `synthetic-production`); includes PLANNED future-rApp inputs (`status=planned-epic`, consumer `future rApp (E3/E7)`): EPIC-3 loop proposal/a1_policy action payloads, EPIC-7 E2SM-KPM-fed metrics + E2SM-RC Style 2/Action 2 PRB-quota (lab rung) |
| `industry_pm_counters.csv` | 191 | Merged + deduped standard PM set (TS 28.552 NR, TS 32.425 LTE, TS 28.554/32.450 KPIs, per-relation MRO counters, UE reports, E2SM-KPM styles) |
| `industry_cm_fields.csv` | 159 | Standard CM set (TS 28.541 NR NRM, TS 28.658 E-UTRAN NRM incl. `EUtranCellNMCentralizedSON`, TS 28.662 antenna model, TS 28.628/32.522 SON policy, BBF TR-196/TR-181) |
| `industry_fm_fields.csv` | 57 | Standard FM model (ITU-T X.733 lineage: 3GPP AlarmRecord/TS 28.532, VES faultFields, o-ran-fm, BBF TR-181 FaultMgmt) |
| `industry_training_data_fields.csv` | 47 | What the industry trains twins + Optimization models on: MDT (TS 37.320), drive-test/crowdsourced, RLF reports, trace/CTR, geodata, traffic maps, per-relation HO matrices, power-vs-load curves — with a `consumer` column (DT-train/DT-eval/MRO/MLB/CCO/ES) |
| `gap_analysis.csv` | 376 | One row per industry **mandatory/recommended** field: `our_equivalent`, `status` (have\|partial\|planned-epic\|missing), `impact`, `remediation_hint` (E1 data platform / E2 NDT / E4 actuation / E3/E7 where applicable) |
| `notes_pm_to_cm_conversion.md` | — | Why the NybSys PM upload derives topology/config, what is real vs fabricated, EPIC-1 direction |
| `notes_verdict.md` | — | The frank per-model answer to "are we even 50% correct?" |
| `notes_es_rapp_pipeline.md` | — | Industry-standard energy-saving rApp pipeline end-to-end, mapped stage-by-stage to CloudlyNet |
| `notes_mro_xapp.md` | — | Standard MRO (non-RT rApp vs near-RT xApp), minimal datasets, frank mapping of our MRO |

Total: 1,379 CSV data rows.

## Methodology

- **Code-extracted (high confidence):** four dumps walked the actual code paths — smo_sim
  `managed_params.py` + NybSys pipeline, data_sim generators, bdt_engine trainer/inference, rApp
  MRO + ES/LB/CCO trainers, edge-agent GPV/telemetry, `artifacts/design/schemas.sql`. Every row
  carries `file:line` evidence.
- **Web/spec-researched (verified):** seven research dumps; 3GPP names checked against downloaded
  spec text (ETSI portals were bot-gated; 3GPP archive .docx/.yang used). Competitor claims are
  evidence-graded in the source dump (vendor brochure > vendor page > press).
- **Planned rows** come from the frozen re-architecture epics (E1 data platform, E2 NDT
  consolidation, E3 RAN intelligence, E4 actuation, E7 OCUDU demo). Planned ≠ built; they score 0
  in today's coverage.
- **Scoring:** `have` = 1, `partial` = 0.5, `planned-epic` = 0, `missing` = 0. `partial` means a
  genuine but degraded equivalent exists (audit-only column, dashboard-only gauge, synthetic
  stand-in, read-only where write is needed). Coverage = (have + 0.5×partial) / N.
- **Scope caveat:** industry rows DESCRIBE the standards. Gap rows never imply CloudlyNet
  implements 3GPP SA5 interfaces, VES, O-RAN E2/A1/O1, or a RIC. The device plane is a
  single-vendor (NybSys NanoLink), single-cell TR-069 (CWMP) EMS; E3/E7 RIC-stack work is
  compose-lab, Simulation/Lab rung.

## Headline numbers (computed from gap_analysis.csv)

Per category, over industry **mandatory** fields (mandatory+recommended in parentheses):

| Category | N mandatory | have | partial | planned-epic | missing | Coverage today |
| --- | --- | --- | --- | --- | --- | --- |
| PM | 74 | 1 | 33 | 3 | 37 | (1 + 0.5×33)/74 = **23.6%** (20.4% over N=159) |
| CM | 86 | 13 | 42 | 0 | 31 | (13 + 0.5×42)/86 = **39.5%** (30.5% over N=141) |
| FM | 33 | 1 | 12 | 8 | 12 | (1 + 0.5×12)/33 = **21.2%** (18.4% over N=49) |
| TRAINING | 11 | 0 | 8 | 0 | 3 | (0 + 0.5×8)/11 = **36.4%** (22.2% over N=27) |

Per use case (mandatory fields across all four categories; mandatory+recommended in parentheses):

| Use case | N mandatory | Coverage today |
| --- | --- | --- |
| DT-train (Network Digital Twin training) | 78 | **41.0%** (34.5% over N=126) |
| DT-eval (twin evaluation/scoreboard) | 79 | **34.2%** (28.9% over N=109) |
| MRO | 66 | **24.2%** (19.4% over N=126) |
| MLB (load balancing) | 51 | **33.3%** (28.0% over N=100) |
| ES (energy saving) | 67 | **36.6%** (32.1% over N=106) |
| CCO | 47 | **48.9%** (36.8% over N=87) |
| self-healing | 69 | **34.1%** (25.7% over N=105) |

Read `notes_verdict.md` for what these numbers mean per model — including where partial credit
hides synthetic stand-ins (the twin's RSRP labels are TR 38.901-computed, not measured; upload-flow
site coordinates are RNG-fabricated) and where our approach genuinely IS the standard one
(RADP-style per-UE RSRP + config schema for a coverage twin; twin-replay synthetic labels for RL).

## The three structural facts behind the numbers

1. **One measured counter drives everything.** Of the NybSys CSV, only `RRC.ConnMean` is consumed
   in production; 10 optional counters are audit passthrough; ~68 vendor columns are ignored. All
   topology/config/UE-training artifacts for upload tenants are synthesized from that one signal
   (see `notes_pm_to_cm_conversion.md`).
2. **Alarms are not persisted.** The edge agent reads 5 TR-069 FaultMgmt params (cap 16 alarms)
   and folds worst severity into a device health field. There is no alarm history table until
   EPIC-1 `fm_alarms`.
3. **Actuation is narrower than recommendation.** The RL models recommend tilt and cell on/off;
   the writable device surface (23 of 24 TR-069 params) contains neither a tilt/RET path nor an
   AdminState write. EPIC-4 owns closing this.
