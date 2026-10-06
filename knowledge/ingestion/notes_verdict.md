# Verdict — are we even 50% correct in the data points we use?

Short answer: **no model reaches 50% of the industry-standard mandatory data set today.**
Computed from `gap_analysis.csv` (have = 1, partial = 0.5, planned = 0; arithmetic in README.md):

| Model / use case | Coverage of mandatory set | With recommended set |
| --- | --- | --- |
| CCO | **48.9%** | 36.8% |
| Network Digital Twin — training | **41.0%** | 34.5% |
| ES (energy saving) | **36.6%** | 32.1% |
| Network Digital Twin — evaluation | **34.2%** | 28.9% |
| Self-healing (FM-driven) | **34.1%** | 25.7% |
| MLB (load balancing) | **33.3%** | 28.0% |
| MRO | **24.2%** | 19.4% |

But the number alone misleads in both directions. The honest reading needs two axes:
**schema correctness** (are we collecting the right KINDS of fields?) and **data provenance**
(are the values measured or synthesized?).

## 1. Network Digital Twin (coverage twin) — schema right, provenance synthetic

- **What we use:** per-UE (lon, lat) → `avg_rsrp` training rows + topology/config features
  (cell position, azimuth, electrical tilt, carrier frequency, height). **This IS the standard
  coverage-twin schema** — RADP/Maveric-style geolocated UE measurement + config, the same shape
  the industry feeds from MDT (TS 37.320) / drive-test / crowdsourced data. On schema, the twin
  is well above 50% correct.
- **The catch:** for PM-upload tenants, every input except cell identity and the `RRC.ConnMean`
  load profile is *synthesized* — coordinates are RNG-drawn in a default bounding box, RF config
  is defaults, and `avg_rsrp` labels are TR 38.901-computed, not measured
  (see `notes_pm_to_cm_conversion.md`). Schema ≈ right; provenance ≈ simulation.
- **What that means practically:** the twin legitimately supports Simulation-rung work — demos,
  RL environment generation, method validation. It does **not yet model any real customer
  network**, and no result from upload-tenant twins may be quoted as a field number
  (claims-guardrails proof-rung discipline).

## 2. MRO (current rApp) — the weakest, at 24.2%

- We ingest cell-level aggregate HO counters (attempts by type), and today **only
  `RRC.ConnMean` is consumed in production** — the HO/CONTEXT counters land audit-only.
- Standard MRO (TS 32.522 / TS 28.313) requires per-neighbor-relation attempts/successes,
  too-early / too-late / wrong-cell failure classification, re-establishment causes, ping-pong
  detection, and CIO/hysteresis/TTT read-write. We have **none** of these
  (see `notes_mro_xapp.md` §e).
- Consequence: from cell-aggregate HOSR alone the *direction* of adjustment is unknowable
  (a low HOSR is compatible with both too-early and too-late regimes). Today's MRO is therefore
  honest to describe as **heuristic HO-KPI monitoring plus sim-trained RL**, not 3GPP MRO, and
  it cannot actuate mobility parameters on the TR-069 (CWMP) plane.

## 3. ES / MLB / CCO (current + future rApps)

- **ES 36.6%:** the loop shape is right (recommend → guarded actuate → auto-rollback exists on
  the NanoLink plane — a genuine industry-standard safeguard analogue), but the ES-defining
  inputs (PRB usage, traffic volume, PEE energy) and the ES action surface (AdminState /
  cell on/off write) are absent (`notes_es_rapp_pipeline.md`).
- **MLB 33.3%:** `RRC.ConnMean` is a legitimate load proxy but the standard set (PRB DL/UL,
  active UEs, per-relation HO for offload) is missing.
- **CCO 48.9% (best on paper):** the twin-driven tilt/coverage approach is the standard C-SON
  CCO method — but the partial credit leans on computed RSRP distributions, not measured ones,
  and tilt actuation (RET) has no write path in the current 24-parameter TR-069 catalogue.
- **Future rApps (EPIC-3 / EPIC-7):** the E7 OCUDU lab chain brings the first per-second,
  E2SM-KPM-shaped metric source and a PRB-quota action — Lab rung only, and correctly kept out
  of today's coverage numbers (`planned-epic` scores 0).

## 4. FM / self-healing — 21–34%, structurally blocked

Alarms are read from the device (5 FaultMgmt parameters) but **not persisted** — worst severity
folds into a health enum. Until EPIC-1 `fm_alarms` lands there is no alarm history to train or
reason over, so FM-aware optimization and self-healing are not data-supported at all.

## Bottom line

- **By schema, the platform is directionally right** — the twin's input shape, the
  guardrail/rollback loop, and the recommend-then-actuate architecture all match the standard
  pattern. This is a data-acquisition gap, not an architecture redesign.
- **By measured-data coverage, we are below 50% everywhere** — roughly 40% for the Network
  Digital Twin, a third for ES/MLB, and a quarter for MRO — and a meaningful share of the
  "partial" credit is synthetic stand-ins.

## Shortest path to close the highest-impact gaps

1. **NybSys vendor data ask (single highest value):** per-neighbor-relation HO
   attempts/successes + failure classification (too-early/too-late/wrong-cell), PRB usage,
   traffic volume. Upgrades MRO from heuristic to standard and ES/MLB from proxy to real.
   (Feeds EPIC-1 ingest.)
2. **Real site geometry:** ingest an actual site database (lat/lon, azimuth, height, tilt) via
   EPIC-1 `cm_records` + TR-069 read-back — removes the fabricated-geography limitation of
   upload-tenant twins.
3. **Persist FM:** EPIC-1 `fm_alarms` + extend the edge parser vocabulary (e.g. the SCM / DNN /
   NCM module tags observed in NanoLink logs) — unlocks self-healing and FM-aware training.
4. **Consume what we already ingest:** promote the 10 audit-only NybSys counters into canonical
   `pm_measurements` (EPIC-1) so models can read them.
5. **Close the actuation gap:** RET/tilt and AdminState write paths on the device plane
   (EPIC-4) — otherwise CCO/ES recommendations remain display-only.
