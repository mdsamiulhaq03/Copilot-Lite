# Adapter: `nybsys_pm_csv`

**Status: implemented** (EPIC-1.S3). Vendor `nybsys`. Feature flag `nybsys`.

Parses NybSys NanoLink LTE PM CSV exports into canonical `pm_measurements` rows.

Input contract of record: [`../../nanolink/nybsys_data_contract.md`](../../nanolink/nybsys_data_contract.md).
That document owns the CSV column definitions and the user-visible error strings; this one owns the
mapping into the canonical store.

## Params

| Field | Notes |
| --- | --- |
| `upload_id` | Required. Pattern-constrained; also scopes the allowed S3 prefix |
| `raw_s3_urls` | Required, at least one. Each must sit under `{tenant_id}/pm-data-ingestion/{upload_id}/raw/` |
| `rng_seed` | Default 42. Pass-through to the feature-builder seam; unused by parsing |
| `samples_per_cell` | Default 200. Pass-through; unused by parsing |
| `legacy_upload_sync` | True when submitted via `/custom/nybsys/uploads`; drives the upload-row sync hooks |

Every URL is validated against the tenant's own upload prefix before anything is fetched. Without
that check a caller could name any key in the bucket and have the service read it.

## What it produces

Store-only. Two stages run: load and dedupe on `(siteId, cellId, _time)`, then aggregate 5-minute
samples into hourly `(day, tick)` buckets with a zero-filled 24-hour grid.

- `source = "nybsys_pm_csv"`, `vendor = "nybsys"`, `granularity_s = 3600`
- `dn = site=<siteId>,cell=<cellId>`
- `labels = {site_id, cell_id, upload_id}`
- `ts` is reconstructed as `unique_dates[day]` at hour `tick`. Vendor CSVs carry naive local time,
  which is interpreted **as UTC**; `ts` is therefore exact only to the vendor's own clock
- `raw_ref` points at the hourly audit CSV at `{tenant_id}/pm-data-ingestion/{upload_id}/pm_hourly.csv`
- `metric` mapped via `vendor_dictionaries` for vendor `nybsys`

## Explicitly not produced

Topology, config defaults, UE placement and RSRP labels. Those are synthesis, not ingestion. They
run behind the feature-builder seam (`legacy_inline` today, bdt_engine from E2) and are the reason
the old combined pipeline could not be re-run safely.

## Dictionary

11 seeded mappings (revision `0002_seed_nybsys_dictionary`). `RRC.AttConnEstab` and
`RRC.SuccConnEstab` are renamed to their TS 28.552 equivalents; the CONTEXT and HO counters keep the
`nybsys:` prefix because no clean equivalent exists. `CONTEXT.AttInitalSetup` preserves the vendor's
own spelling of "Inital" because the key must match the CSV column or the mapping never fires.
