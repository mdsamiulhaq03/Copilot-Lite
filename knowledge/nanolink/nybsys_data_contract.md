# Nybsys PM CSV Data Contract

Caller-facing **input contract** for the Nybsys PM CSV ingestion path
(`POST /v1/tenants/{tenant_id}/custom/nybsys/uploads` and the related
`/v1/tenants/{tenant_id}/custom/nybsys/**` upload endpoints). It defines the
exact format, constraints, and expectations for CSV files prepared by data
engineers, the upload UI, and integration testers.

For the end-to-end pipeline stages (load → hourly aggregation → topology
synthesis → UE placement → RSRP labeling) and their ORM/S3 wiring, see
[artifacts/design/LLD.md §5 — SMO Sim](../design/LLD.md) (subsection *Custom Ingestion —
`/custom/nybsys/**`*). This document is the authoritative reference for the
**caller-supplied CSV**; LLD §5 is the reference for what the service does with it.

> Source of truth: `app/lib/nybsys/pipeline.py` (+ `rules.py`, `defaults.py`,
> `app/services/nybsys_runner.py`, `app/api/v1/custom/nybsys/router.py`) in the
> `maveric_platform_smo_sim` submodule. Every claim here is derived from that code.

---

## 1. CSV Column Specification

The pipeline recognizes **14 columns** (4 required, 10 optional). Any additional columns in the CSV are silently ignored — the original Nybsys export has 84 columns and that is fine.

### Required Columns

| Column | Data Type | Aggregation | Description |
|--------|-----------|-------------|-------------|
| `siteId` | string | group key | Physical site identifier (e.g., `"NGBT1F"`). Multiple cells can share one siteId. |
| `cellId` | string | group key | Unique cell identifier (e.g., `"26538789"`). Numeric strings are common. |
| `_time` | datetime | group key (date + hour) | Measurement timestamp. Must be ISO 8601 (see §3, §5). |
| `RRC.ConnMean` | numeric (float) | **mean** (hourly) | Mean RRC connected users in the measurement interval. Primary metric driving UE generation. |

All four must be present (after normalization) or the pipeline fails.

### Optional Columns

These are carried through the hourly aggregation if present. They must match the **exact canonical name** (no fuzzy matching — see section 2).

| Column | Data Type | Aggregation |
|--------|-----------|-------------|
| `RRC.AttConnEstab` | numeric | sum |
| `RRC.SuccConnEstab` | numeric | sum |
| `CONTEXT.AttInitalSetup` | numeric | sum |
| `CONTEXT.SuccInitalSetup` | numeric | sum |
| `CONTEXT.AttRel.Normal` | numeric | sum |
| `CONTEXT.AttRel.Abnormal` | numeric | sum |
| `HO.IntraFreqOutAtt` | numeric | sum |
| `HO.InterFreqOutAtt` | numeric | sum |
| `HO.AttOutInterEnbS1` | numeric | sum |
| `HO.AttOutInterEnbX2` | numeric | sum |

> **Intentional vendor typo — do not "fix" it.** `CONTEXT.AttInitalSetup` and
> `CONTEXT.SuccInitalSetup` spell "Inital" (not "Initial"). This matches the
> Nybsys vendor export exactly and is **matched literally** in code — the
> optional-column sum list hard-codes these strings (`pipeline.py:182-183`),
> with no fuzzy matching. A file that "corrects" the spelling to `Initial` will
> have those columns silently dropped.

---

## 2. Column Name Normalization

The pipeline applies case-insensitive fuzzy matching **only for the 4 required columns** (`normalize_columns`, `pipeline.py:102-118`). Leading/trailing whitespace is stripped from **all** column headers first.

| If CSV header contains (case-insensitive) | Maps to | Condition |
|---|---|---|
| `siteid` | `siteId` | Only if `siteId` is not already present |
| `cellid` | `cellId` | Only if `cellId` is not already present |
| `time` or `timestamp` | `_time` | Only if `_time` is not already present |
| `rrc.connmean` | `RRC.ConnMean` | Only if `RRC.ConnMean` is not already present |

Optional columns (section 1) receive **no fuzzy matching**. They must appear with the exact canonical name shown in the table above.

---

## 3. Value Ranges and Constraints

| Field | Valid Range | Notes |
|-------|------------|-------|
| `siteId` | Any non-empty string | Alphanumeric typical. Example: `"NGBT1F"` |
| `cellId` | Any non-empty string | Numeric strings common. Example: `"26538789"` |
| `_time` | ISO 8601 timestamp | Parsed with `format="ISO8601"` (`pipeline.py:163`). ISO 8601 is **required**, not merely recommended (e.g., `"2025-12-29 00:00:00"`). Rows whose `_time` is not ISO 8601 (or otherwise unparseable) become `NaT` and are **silently dropped** |
| `RRC.ConnMean` | `[0, +inf)` | Hourly mean values `< 0.5` produce 0 synthetic UEs for that cell-tick. Networks with 70-80% zero values are normal (sparse/rural). Negative values are treated as 0 |
| Counter columns | `[0, +inf)` | Summed during hourly aggregation. Negative values are not rejected but are meaningless |

> **Correction vs original submodule doc:** the prior DATA_CONTRACT stated
> `_time` accepts "any value parseable by `pd.to_datetime`". The code now pins
> `format="ISO8601"` (`pipeline.py:163`: `pd.to_datetime(pm2["_time"],
> format="ISO8601", errors="coerce", utc=False)`), so non-ISO-8601 formats no
> longer parse and are dropped as `NaT`. Corrected here.

### Data Quality Observations (from real Nybsys data)

- 76.5% of `RRC.ConnMean` values are 0 in sparse networks — this is expected, not an error
- Cells with `RRC.ConnMean < 0.5` across all hours in all days will have zero organic UEs but still receive ≥ 50 synthetic-complement training points (Approach C, `is_fallback=True`)
- No nulls expected — the pipeline does not explicitly reject null values in non-required columns, but null / non-ISO-8601 `_time` rows are dropped

---

## 4. Multi-File and Multi-Day Handling

| Rule | Detail |
|------|--------|
| **Minimum files** | 1 CSV required |
| **Maximum files** | No hard limit (bounded by upload request list) |
| **Each file must have** | A header row + at least 1 data row |
| **Concatenation** | All files are loaded and row-concatenated into a single DataFrame |
| **Deduplication** | On `(siteId, cellId, _time)` — **first occurrence wins** (file order = order of `raw_s3_urls`) |
| **Multi-day in one file** | Supported. Day index is derived from the `_time` column, not from filenames |
| **Same day across files** | Supported. Overlapping timestamps are deduplicated |
| **File naming** | No strict convention. Date-based names recommended for readability (e.g., `2025-12-29.csv`) but not enforced |
| **File encoding** | UTF-8 (default for `pd.read_csv`) |
| **Delimiter** | Comma (standard CSV) |

### Key Flexibility

A single upload can contain:
- 1 file with 7 days of data, OR
- 7 files with 1 day each, OR
- 3 files with overlapping date ranges (dedup handles it)

The pipeline doesn't care — it merges everything and derives day/tick from the `_time` values.

---

## 5. Time and Day Processing

### Timestamp Parsing
- `_time` is parsed via `pd.to_datetime(_time, format="ISO8601", errors="coerce", utc=False)` (`pipeline.py:163`) — the `format="ISO8601"` constraint means only ISO 8601 timestamps parse; other formats coerce to `NaT`
- Rows where `_time` cannot be parsed become `NaT` and are **silently dropped** (count surfaced in ingest stats as `dropped_unparseable_rows`)
- If ALL rows are unparseable, the pipeline fails with: `"No valid timestamps after parsing"`

### Day Index (0-based)
1. Extract the date portion from each `_time` value
2. Collect all unique dates and sort chronologically
3. Assign: earliest date = day 0, next = day 1, etc.
4. The day column is an **integer**, not a date string

Example: files spanning 2025-12-29 to 2026-01-04 produce day values 0 through 6.

### Tick (Hour)
- The hour component (0-23) of `_time` becomes the `tick` column
- Sub-hourly data (e.g., 5-minute PM bins) is aggregated within each (siteId, cellId, day, tick) group

### Hourly Aggregation Rules
| Column | Aggregation |
|--------|-------------|
| `RRC.ConnMean` | **mean** of all sub-hourly values within the group |
| All optional counter columns | **sum** of all sub-hourly values within the group |

### Gaps
- Missing hours (no data for a cell at tick 15) are valid — the aggregator zero-fills to a full 24-tick grid per cell per day
- Missing days (no data for day 3) are valid — day indices remain contiguous for the dates that do appear
- Missing cells at certain ticks are valid — the cell simply has 0 UEs for that tick

---

## 6. Cell and Site Topology

The pipeline synthesizes topology entirely from the data — no external geometry input is needed or accepted.

### Cell-to-Site Relationship
- Derived from `(siteId, cellId)` pairs found in the data
- Sites can have **any number of cells** (1, 2, 3, or more) — the pipeline does NOT assume tri-sector
- Real Nybsys data: 41 single-cell sites, 22 dual-cell sites, 1 tri-sector site

### Azimuth Assignment
| Cells per site | Azimuths |
|----------------|----------|
| 1 | 0 degrees |
| 2 | 0, 180 degrees |
| 3 | 0, 120, 240 degrees |
| N | 0, 360/N, 2*360/N, ... (evenly spaced) |

### Clutter Classification
Cells are ranked by their overall mean `conn_mean` across all hours:
- Bottom 33rd percentile: `rural`
- 33rd to 66th percentile: `suburban`
- Top 66th percentile: `dense`

### Synthetic Geography
- Lat/lon are randomly generated within a configurable bounding box (default: NYC area, ~40.70-40.80 lat, -74.05 to -73.95 lon)
- eNodeB IDs are sequentially assigned (1-indexed)
- ECGI = `enodeb_id * 256 + sector_idx`

---

## 7. UE Distribution and Training Data

### Synthetic UE Count per Cell-Tick (Stage 2 — Stochastic Guardrail)
- `n_target` is drawn via Bernoulli rounding: `n = floor(conn) + Bernoulli(conn - floor(conn))`
- Preserves `E[n_target] = conn_mean` by construction (unbiased, unlike `round()`)
- **Slot-level guardrail**: if all cells in a (day, tick) slot stochastically round to 0 despite `Σconn_mean > 0`, one cell is promoted to 1 via μ-weighted selection — no slot with demand ever produces zero UEs
- Fully reproducible: controlled by `rng_seed` (persisted in `nybsys_uploads`)

### UE Placement — Approach C (Stage 4)

Three placement buckets per cell per (day, tick):

| Bucket | Sampler | Definition |
|--------|---------|------------|
| `served` | Uniform-in-Voronoi | UEs inside cell's Voronoi polygon (fallback: bbox ±0.005°) |
| `edge` | SINR-locus accept-reject | Deterministic SINR ∈ [0, 6] dB |
| `outage` | RSRP-target accept-reject | Deterministic RSRP (tr_38_901) ∈ [−130, −110] dBm |

Bucket counts per tick are drawn via `Multinomial(n_target, [f_served, f_edge, f_outage])`.

**Locked production placement mix:**

| Clutter | f_served | f_edge | f_outage |
|---------|----------|--------|----------|
| dense | 0.75 | 0.20 | 0.05 |
| suburban | 0.80 | 0.12 | 0.08 |
| rural | 0.70 | 0.05 | 0.25 |

Output column `placement_bucket ∈ {served, edge, outage}` is written to `synthetic_dataset.csv`.

### Deterministic vs Realized RSRP/SINR

- **Deterministic** (pre-shadow): RSRP/SINR computed from PL model + 3GPP antenna pattern only; no random shadow draw. Used as the accept-reject criterion in edge and outage samplers — by-construction guarantee that sampled positions satisfy the bucket definition.
- **Realized** (post-shadow): deterministic RSRP + `N(0, σ²)` shadow fading draw at RSRP labeling time. This is what `avg_rsrp` in `ue_training_data.csv` represents — the value BDT actually trains on.
- Shadow σ by clutter: dense=6.0 dB, suburban=5.0 dB, rural=4.0 dB.
- The gap between deterministic and realized (10–30%) is expected under realistic σ values; it does NOT indicate a sampler defect. The gate criterion in `audit/placement_v2.py` measures both views separately.

### Training Data (ue_training_data.csv) — Stage 5 Synthetic-Complement

Every cell is guaranteed ≥ 50 rows (floor) via synthetic-complement, capped at 500 (ceiling):

| Organic UEs available | Action |
|-----------------------|--------|
| 0 to 49 | Generate `floor − count` synthetic UEs via Approach C samplers (`is_fallback=True`) |
| 50 to 499 | Take all organic UEs (`is_fallback=False`) |
| ≥ 500 | Randomly downsample to 500 |

- `samples_per_cell` API param (default **200**, max 10 000) sets the per-cell training ceiling, hard-capped at `TRAINING_CEILING=500`. The synthetic-complement floor (`TRAINING_FLOOR=50`) is fixed and cannot be lowered via this param.
- `is_fallback=True` rows are Approach C synthetic; `is_fallback=False` rows are organic.
- `placement_bucket` is preserved for organic rows and assigned via multinomial split for synthetic rows.

### RSRP Labeling
- Model: `tr_38_901` (3GPP TR 38.901 §7.4) + 3GPP antenna pattern + shadow fading
- Shadow fading sigma by clutter: dense=6.0 dB, suburban=5.0 dB, rural=4.0 dB
- Output RSRP clipped to **[-140, -60] dBm**

### PL Model Configuration
- **Production default**: `tr_38_901` — 3GPP TR 38.901 §7.4.1/§7.4.2. Locked at `defaults.py:pl_model_name`.
  - Clutter dispatch: `dense` → UMa, `suburban`/`rural` → RMa, unknown → UMi (with warning).
  - **LOS realization (Gap 1 — Option B)**: when `rng` is provided, per-UE Bernoulli draw from P(LOS) (§7.4.2 Table 7.4.2-1) yields a bimodal RSRP distribution required by BDT/DT training. When `rng=None`, returns deterministic blend `p·PL_LOS + (1-p)·PL_NLOS` for backward-compatible audit callers.
  - d_3D computed as `sqrt(d_2D² + (h_BS − h_UE)²)` in all NLOS formulas.
  - NLOS lower-bounded by LOS PL (`max(PL_NLOS, PL_LOS)`) per spec mandate.
- **fspl baseline**: `fspl` model is registered and available via `pl_model_name="fspl"` config swap. No clutter correction, no height adjustment. Used as the pre-R&D-2 production baseline in audit comparisons.
- **cost231_hata**: registered and available for comparison; was the production default prior to #262.
- Model registry: `get_pl_model(name)` in `app/lib/nybsys/pl_models.py`. Registered models: `fspl`, `fspl_with_excess` (audit-only), `cost231_hata`, `tr_38_901`.

---

## 8. Upload API Request

### Endpoint
```
POST /v1/tenants/{tenant_id}/custom/nybsys/uploads
```

### Prerequisites
- Tenant must have `feature_flags = {"nybsys": true}` in the `tenants` table
- CSV files must be pre-uploaded to S3 before calling this endpoint

### Request Body

| Field | Type | Required | Default | Constraints | Description |
|-------|------|----------|---------|-------------|-------------|
| `upload_id` | string | yes | — | 1-128 chars, pattern: `^[a-zA-Z0-9][a-zA-Z0-9_.-]*$` | User-chosen identifier for this upload |
| `raw_s3_urls` | list of URLs | yes | — | Min 1 item. Each URL must be under `{tenant_id}/pm-data-ingestion/{upload_id}/raw/` | S3 URLs of pre-uploaded CSV files |
| `rng_seed` | integer | no | 42 | >= 0 | Random seed for reproducible topology/UE generation. Persisted as `nybsys_uploads.rng_seed` (INTEGER NULLABLE). Pre-existing uploads have NULL. |
| `samples_per_cell` | integer | no | 200 | 1-10,000 | Ceiling for training points per cell; floor is always 50 (TRAINING_FLOOR). Hard cap is 500 (TRAINING_CEILING). |

### S3 URL Prefix Requirement
Every URL in `raw_s3_urls` must resolve to an S3 key under:
```
{tenant_id}/pm-data-ingestion/{upload_id}/raw/
```
URLs outside this prefix are rejected with 422.

### Derived IDs
- `baseline_id` = `{upload_id}-topology`
- `dataset_id` = `{upload_id}-dataset`

### Status Lifecycle
```
uploading --> processing --> completed
                        \--> failed
```

---

## 9. Pipeline Output Artifacts

All paths are relative to the tenant's S3 prefix: `{tenant_id}/`

### Baseline Files

**S3 path:** `baselines/{upload_id}-topology/`

| File | Columns |
|------|---------|
| `topology.csv` | ecgi, site_id, cell_name, enodeb_id, cell_az_deg, tac, cell_lat, cell_lon, cell_id, cell_carrier_freq_mhz, h_bs_m, h_ue_m, tx_power_dbm, antenna_max_gain_dbi, hpbw_h_deg, hpbw_v_deg, front_back_db, max_att_db, feeder_loss_db, misc_loss_db, clutter_type |
| `config.csv` | cell_id, cell_el_deg, cell_carrier_freq_mhz, bw_mhz |
| `ue_training_data.csv` | cell_id, avg_rsrp, lon, lat, cell_el_deg, placement_bucket, is_fallback |

`placement_bucket ∈ {served, edge, outage}`. `is_fallback: bool` — True for Approach C synthetic-complement rows, False for organic rows.

### UE Dataset

**S3 path:** `ue/{upload_id}-dataset/`

| File | Columns |
|------|---------|
| `synthetic_dataset.csv` | ue_id, lon, lat, tick, day, clutter_type, serving_cell_id, placement_bucket |

`placement_bucket ∈ {served, edge, outage}`.

### Intermediate (debug/audit)

**S3 path:** `pm-data-ingestion/{upload_id}/`

| File | Columns |
|------|---------|
| `pm_hourly.csv` | siteId, cellId, day, tick, conn_mean, [optional counters if present in input] |

---

## 10. Audit vs Production Boundary

The `app/lib/nybsys/` package separates production pipeline logic from offline R&D-2 validation:

- **Production modules** (`rules.py`, `placement.py`, `models.py`, `pipeline.py`, `geo.py`, `pl_models.py`): on the API request path. Imported by the nybsys runner. No audit-only concerns.
- **Audit package** (`app/lib/nybsys/audit/`): offline R&D-2 gate-criterion validation only. Not on the request path. Imports *from* production modules (never the reverse). Audit functions re-export production symbols via `from X import Y as Y`.
- `audit/placement.py` (old approach) and `audit/placement_v2.py` (Approach C orchestration) are audit-only validation harnesses; `audit/report.py` generates comparison markdown.
- `audit/skew.py` and `audit/pm_quality.py` are data-quality inspection tools for offline analysis.

---

## 12. Error Conditions

| Condition | HTTP Status / Pipeline Status | Error Message |
|-----------|-------------------------------|---------------|
| Missing required CSV column (`siteId`, `cellId`, `_time`) | Pipeline failure -> `status=failed` | `"CSV(s) missing required columns: [...]"` |
| Missing `RRC.ConnMean` column | Pipeline failure -> `status=failed` | `"CSV missing required columns: ['RRC.ConnMean']"` |
| All timestamps unparseable | Pipeline failure -> `status=failed` | `"No valid timestamps after parsing"` |
| No CSV files in request | Pipeline failure -> `status=failed` | `"No CSV files provided"` |
| S3 file not downloadable | Pipeline failure -> `status=failed` | `"S3 file not found or inaccessible: {key} ({error_code})"` |
| S3 URL outside allowed prefix | 422 Unprocessable Entity | `"Invalid S3 URL: ..."` |
| Duplicate `upload_id` for tenant | 409 Conflict | `"Upload '{upload_id}' already exists for this tenant"` |
| Empty `raw_s3_urls` list | 422 Unprocessable Entity | Pydantic validation error |
| Invalid `upload_id` format | 422 Unprocessable Entity | Pydantic pattern validation error |
| Upload not found (GET / DELETE) | 404 Not Found | `"Upload not found"` |
| Delete while uploading/processing | 409 Conflict | `"Cannot delete upload while it is being processed"` |
| S3 deletion failure | 500 Internal Server Error | `"Failed to delete ingestion artifacts"` |
| Feature flag missing/false | 403 Forbidden | `"Feature 'nybsys' is not enabled for this tenant"` |

> **Correction vs original submodule doc:** the S3-download failure message
> interpolates the S3 **key**, not the full URL — `nybsys_runner.py:178` raises
> `f"S3 file not found or inaccessible: {key} ({error_code})"`. The `{url}`
> placeholder in the prior doc is corrected to `{key}` here. The 404 `"Upload
> not found"` row (`router.py:146,186`) was also absent from the prior doc.

---

## 13. Examples

### Minimal Valid CSV

The absolute minimum — 4 columns, 1 site, 1 cell, 2 rows:

```csv
siteId,cellId,_time,RRC.ConnMean
SITE_A,CELL_001,2025-12-29 00:00:00,3.5
SITE_A,CELL_001,2025-12-29 00:05:00,2.1
```

This produces: 1 day, 1 tick (hour 0), 1 cell, conn_mean = mean(3.5, 2.1) = 2.8, generating ~3 UEs.

### Realistic Excerpt (from actual Nybsys export)

The real data has 84 columns. The pipeline reads the 4 required + 10 optional and ignores the rest:

```csv
"serial","siteId","cellId","_time","RRC.ConnMean","RRC.ConnMax","RRC.AttConnEstab","RRC.SuccConnEstab","CONTEXT.AttInitalSetup","CONTEXT.SuccInitalSetup","HO.IntraFreqOutAtt","HO.InterFreqOutAtt","HO.AttOutInterEnbS1","HO.AttOutInterEnbX2","CONTEXT.AttRel.Abnormal","CONTEXT.AttRel.Normal",...70 more columns...
"00101000003","NGBT1F","26538789","2025-12-29 00:00:00",3,5,38,38,58,54,0,0,0,0,0,56,...
"00101000003","NGBT1F","26538789","2025-12-29 00:05:00",1,3,9,9,18,18,0,0,0,0,0,19,...
```

### Multi-Day Example (2 files)

**File: 2025-12-29.csv**
```csv
siteId,cellId,_time,RRC.ConnMean
SITE_A,CELL_001,2025-12-29 08:00:00,5.2
SITE_A,CELL_001,2025-12-29 09:00:00,7.1
SITE_B,CELL_002,2025-12-29 08:00:00,0.3
```

**File: 2025-12-30.csv**
```csv
siteId,cellId,_time,RRC.ConnMean
SITE_A,CELL_001,2025-12-30 08:00:00,4.8
SITE_B,CELL_002,2025-12-30 08:00:00,1.2
```

Result after merge and aggregation:
- Day 0 = 2025-12-29, Day 1 = 2025-12-30
- CELL_001 at day 0, tick 8: conn_mean = 5.2 -> 5 UEs
- CELL_002 at day 0, tick 8: conn_mean = 0.3 -> 0 UEs (rounds down)
- CELL_002 at day 1, tick 8: conn_mean = 1.2 -> 1 UE

### Column Name Variants (all valid)

```csv
siteid,cellid,time,rrc.connmean
SITE_A,CELL_001,2025-12-29 00:00:00,3.5
```

Normalized to `siteId`, `cellId`, `_time`, `RRC.ConnMean` automatically.
</content>
</invoke>
