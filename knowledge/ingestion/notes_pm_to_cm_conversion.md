# PM-to-CM Conversion in the NybSys PM Upload Flow (Approach C)

## Why it exists
NybSys NanoLink customers can provide ONLY periodic PM CSV exports (5-min counters, 84 columns) — no site
database, no geo coordinates, no antenna/RF configuration, and no UE-level measurements (no drive test / MDT).
The Maveric-descended BDT (Network Digital Twin) cannot train on that alone: it needs (a) a topology/config
record (cell positions, azimuth, tilt, RF parameters) and (b) per-UE (lat, lon) -> RSRP training rows.
The pipeline therefore SYNTHESIZES topology, config, and a UE training set from the single PM signal, so a
bare PM export becomes a trainable twin. That synthesis is what the flow calls "PM to CM conversion"
(pipeline.py:1-33 module docstring; artifacts/nanolink/nybsys_data_contract.md section 6: "The pipeline
synthesizes topology entirely from the data — no external geometry input is needed or accepted").

## Step-by-step: what is derived from what
1. **Stage 1 — load_and_merge_csvs (pipeline.py:125-143):** concat all CSVs, normalize headers (fuzzy match
   for the 4 required columns only, pipeline.py:102-118), dedupe on (siteId, cellId, _time). Only 14 of the
   84 vendor columns are recognized; the rest are silently ignored.
2. **Stage 2 — aggregate_pm_to_day_tick (pipeline.py:150-214):** _time -> 0-based `day` + hour `tick`;
   RRC.ConnMean -> hourly MEAN `conn_mean`; the 10 optional counters -> hourly SUMs; zero-fill to a full
   24-tick grid. Output pm_hourly.csv — the only artifact that stays genuinely PM.
3. **Stage 3 — build_topology_and_config (pipeline.py:221-307), the actual PM->CM step:**
   - distinct (siteId, cellId) pairs -> cell/site inventory; cells-per-site count -> `cell_az_deg`
     (evenly spaced 360/N) and `sector_idx`/`cell_name` (pipeline.py:248-261);
   - per-cell mean `conn_mean` ranked at 33rd/66th percentiles -> `clutter_type` dense/suburban/rural
     (pipeline.py:233-238) — the ONLY RF characteristic actually derived from PM;
   - clutter_type -> `cell_el_deg` downtilt sampled N(mean,2) clipped per TILT_PROFILE_BY_CLUTTER
     (pipeline.py:287-298) and shadow-fading sigma at labeling time (defaults.py:10-17);
   - siteId enumeration -> `enodeb_id` (sequential 1-indexed) -> `ecgi = enodeb_id*256 + sector_idx`
     (pipeline.py:255-257);
   - `cell_lat`/`cell_lon`: RNG-uniform inside a default NYC bounding box (pipeline.py:242-244,
     defaults.py:30-33) — FABRICATED, the PM export has no geography;
   - every other RF field (tac=1, 2100 MHz carrier, h_bs 25 m, h_ue 1.5 m, 43 dBm, 17 dBi, HPBW 65/10 deg,
     losses, front/back 25 dB, bw 20 MHz) is a TopologyDefaults constant (defaults.py:27-51) — NOT from PM.
4. **Stage 4 — stochastic guardrail + generate_ue_data (rules.py:26; pipeline.py:422-507):** `conn_mean` ->
   `n_target` UEs per (cell, day, tick) via Bernoulli rounding preserving E[n]=conn_mean, with mu-weighted
   slot promotion so no demanded slot yields zero UEs; each cell's UEs split multinomially into
   served (uniform-in-Voronoi of the synthetic positions) / edge (deterministic SINR in [0,6] dB) /
   outage (deterministic RSRP in [-130,-110] dBm) buckets -> synthetic_dataset.csv.
5. **Stage 5 — generate_ue_training_data (pipeline.py:709-753):** per-cell stratification with floor
   TRAINING_FLOOR=50 (synthetic complement, is_fallback=True) and ceiling min(samples_per_cell, 500);
   every row labeled `avg_rsrp` = TR 38.901 path loss (UMa/RMa by clutter) + 3GPP antenna pattern +
   shadow fading N(0, sigma_clutter), clipped [-140,-60] dBm -> ue_training_data.csv, the BDT training set.
Determinism end-to-end is governed by `rng_seed` persisted on nybsys_uploads (pipeline.py:32).

## What is genuinely CM vs what is training data
- Genuinely real (from PM): site_id/cell_id identity, cells-per-site, day/tick load profile, relative load
  ranking (clutter). Everything else in topology.csv/config.csv is defaults or RNG — these artifacts are
  CM-SHAPED but synthetic; they must not be presented as the network's actual configuration.
- Genuinely CM in the platform lives elsewhere: the NanoLink TR-069 device parameters (24-path
  managed-parameter catalogue, `commands` table, EPIC-4) and the planned `cm_records` table
  (EPIC-1-data-platform.md:108-117, origin 'ingest'|'read_back'|'operator').
- synthetic_dataset.csv and ue_training_data.csv are TRAINING data (synthetic UE observations); `avg_rsrp`
  is a model-computed label, never a measured PM KPI. Do not label these as PM counters.
- FM: nothing in this flow is fault data; the planned `fm_alarms` table (EPIC-1:93-106) is a separate,
  not-yet-fed surface.

## EPIC-1 / E0 / E4 movement (planned)
- E0.S2: gateway env-gated split — `/custom/nybsys/uploads*` -> DATA when CUSTOM_UPLOADS_TARGET=data;
  all other `/custom/nybsys/**` (devices/edge/commands) stays SMO (EPIC-0-platform-hygiene.md:142-170).
- E1: data_sim serves the legacy uploads contract byte-compatibly via `NybsysPmCsvAdapter`
  ("Store-only: NO topology/UE synthesis here", EPIC-1:507): stages 1-2 lifted verbatim into
  `pm_stages.py` (error strings byte-identical, EPIC-1:456), canonical `pm_measurements` rows
  (source='nybsys_pm_csv', vendor='nybsys', granularity_s=3600, dn='site=..,cell=..',
  TS 28.552-mapped metric names via the vendor_dictionaries seed, EPIC-1:476-498); topology/UE synthesis
  moves behind the E2 feature-builder seam producing the same baselines + ue_datasets artifacts (EPIC-1:14).
- E4.S6 (blocked on E1 cutover): smo_sim's uploads router, schemas, nybsys_runner, upload repository and
  stale-upload sweep are DELETED; `app/lib/nybsys/` pipeline deleted only once E2's feature builder has
  landed; device/edge routers untouched; `nybsys_uploads` table ownership transfers to data_sim without a
  drop (EPIC-4-actuation-integration.md:1164-1184, epic DoD line 12).
