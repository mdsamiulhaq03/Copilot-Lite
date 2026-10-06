# EPIC-11 — Legacy phase-out after the IA realignment

Status: OPEN (inventory frozen 2026-08-06; removal deliberately deferred)
Owner: platform
Origin: the 12-item IA realignment (2026-08-06) converted several backend + frontend
surfaces to new contracts. Per direction, converted-but-superseded code was NOT deleted
in that pass — it is marked in-code with `LEGACY (EPIC-11)` comments and inventoried
here for staged removal. Grep for `LEGACY (EPIC-11)` across submodules to find every
marker.

Rule for every story: removal ships only after the replacement is proven on the live
local stack (and staging where applicable), and each story states its proof.

## Stories

### E11.S1 — NybSys upload conversion path (frontend + data_sim + gateway)
Superseded by: vendor-neutral `POST /tenants/{t}/ingest/uploads` + `GET /ingest/jobs/{id}`
+ canonical PM store (frontend cut over in IA Phase A).
Remove:
- frontend: `components/smo/Nybsys*` family, `lib/api/services/nybsys.ts`,
  `lib/nybsys.ts` (buildNybsysDerivedIds), `lib/schemas/nybsys.ts` rng_seed /
  samples_per_cell, `types/nybsys.ts` conversion fields.
- data_sim: `app/api/v1/custom/nybsys_uploads.py` (POST/GET/DELETE incl. delete_derived
  cascade), `nybsys_schemas.py`, `app/db/nybsys_uploads_repo.py`, `legacy_upload_sync`
  hooks in the nybsys ingest adapter; `nybsys_uploads` table (drop migration).
- gateway: `customDispatchHandler` nybsys split + `CUSTOM_UPLOADS_TARGET` env (reverts
  `/custom/**` to SMO-only).
- docs at cutover: HLD §3.2/§4.3 + `artifacts/nanolink/nybsys_data_contract.md` freeze
  this contract — update both.
Proof: an upload through the neutral path lands in pm_measurements on staging; the
uploads-history view no longer reads the legacy table.

### E11.S2 — BDT inference (Digital Twin Simulation) retirement
Superseded by: NDT Evaluate (same twin; zero-change tick evaluate ≡ simulation run).
Precondition (feature port, do FIRST): per-UE spatial scatter + attachment counts into
Evaluate via `options.include ["raw_ue_arrays","ue_frames"]` — reuse
InferenceScatterChart; mind the result-cache bypass when options.include is non-empty
(needs an explicit opt-in or follow-up fetch so plots don't double twin compute).
Remove after port:
- frontend: `app/(dashboard)/bdt/models/[bdtId]/infer/` + `components/bdt/BdtInference*`
  family + the four BDT-infer service methods in `lib/api/services/bdt.ts` +
  bdt-columns Eye-link (repointed to Evaluate in Phase B).
- bdt_engine: `start_bdt_inference`/`get_bdt_inference` endpoints,
  `services/bdt_inference.py` InferenceJob path; gateway route pattern;
  `artifacts/design/openapi.yaml` entries.
Proof: Twin Library row action opens Evaluate pre-selected; scatter renders there.

### E11.S3 — Device optimize-mode write path (smo_sim + frontend)
Superseded by: single loop mode in `loop_policies.mode` (device self-optimizer reads the
tenant policy since IA Phase D; tenant `auto` maps to device `approval` — device
auto-apply keeps requiring explicit RF sign-off per self_optimizer OD4).
Remove:
- smo_sim: `PATCH /custom/nybsys/devices/{id}/optimize-mode` (410 stub today) +
  `OptimizeModeIn` DTO; `nanolink_devices.optimize_mode` column (drop migration after
  the derived read-model no longer selects it).
- frontend: `setOptimizeMode` in `lib/api/services/nybsys-devices.ts`;
  `components/policy/PolicyDeviceTable.tsx` (Device policies section, unmounted in
  Phase D).
Note: device-loop GUARDRAILS are still the hard-coded GUARD dict in self_optimizer.py,
NOT the tenant guardrail document — centralizing those is a separate decision recorded
here so nobody assumes it happened.
Proof: mode changes on /policy visibly gate device recommendations on the live stack.

### E11.S4 — BDT training-data plumbing → dataset-driven contract
Superseded by (to build in this story): `/bdt/train` accepting `dataset_id`; bdt_worker
resolves the CSV from `ue_datasets` (keeping the baseline-column fallback during
migration; it hard-fails "Missing required dataset URLs" if neither resolves — keep a
path for in-flight Kafka events).
Remove after cutover:
- `baselines.url_to_trainingdata_csv` column + all 4 ORM mirrors (smo_sim
  smo_schemas.py, bdt_engine BaselineRef, rapp BaselineRef, data_sim baseline_repo) +
  backfill into ue_datasets first + drop migration.
- frontend: TrainBDTModal URL-copy pattern; baseline form/table training-CSV surfaces
  (label unified + made optional in Phase B).
- `ue_datasets.url_to_trainingdata_csv` naming fossil (aliases url_to_smo_ue_data_csv;
  rationalize the two-URL pair — smo_sim prefers smo_ue_data, rapp reads only it).
Proof: BDT training runs dataset-driven on the live stack for a new + a pre-existing
baseline.

### E11.S5 — Data-platform offset consumers → cursor
Superseded by: keyset cursor on `GET /data/pm` (added IA Phase A; offset kept working).
Migrate then remove offset dependence:
- bdt_engine `app/feature_builder/pm_source.py` (PAGE_LIMIT offset loop — O(offset)
  re-scan each page) and `app/services/loop/feedback_watcher.py`.
- frontend interim offset Load-more on /data (TODO marker in code) → next_cursor.
Then the offset param itself can be deprecated on the endpoint.
Proof: feature build over a multi-week PM store shows flat per-page latency.

### E11.S6 — KPI snapshot semantics + enrichment
From the KPI-history redesign findings:
- Enrich snapshots at write time with what was evaluated: proposal_id and/or a config
  summary (cells_changed count) — today a snapshot cannot say WHAT change produced it.
- Fix upsert keeping stale `created_at` while replacing KPI values (silent history
  mutation at old timestamps).
- Stop persisting all-zero guardrail KPIs when sample_count <= 0.
- Consider distinct source values for loop-gate baseline vs candidate passes.
- frontend: drop dead `NdtKpiSnapshot.captured_at`; retire the superseded
  `KpiTrendChart.tsx` once the redesigned page has burned in.
Proof: a gate run's pair renders as an explicit baseline→candidate comparison.

### E11.S7 — Evaluate time model
From the tick-invariance findings (grid datasets: identical KPIs for all 24 tick
values, each costing a full twin run):
- Dataset `stats.tick_variant`/`ticks_present` landed in Phase B; extend to a declared
  `time_semantics` (none | tick_hour_of_day | tick_index).
- Wall-clock anchor on evaluation snapshots (join to same-hour real PM in /data/pm).
- Canonicalize tick→0 in `generate_run_id` for tick-invariant datasets (kills the
  24-identical-runs cost).
- CAUTION: any new NDTEvaluateRequest field changes canonical_json → every run_id →
  breaks decision-hub baseline caching. Needs an explicit contract-version bump.
Proof: evaluating a static grid at two ticks returns the same cached run.

### E11.S8 — Small orphans
- `components/app-breadcrumbs.tsx` (mounted nowhere; superseded by the global flow
  strip) — wire it or delete it.
- `components/actuators/AdapterTile.tsx` — became the shared tile in Phase D or dies.
- `app/(dashboard)/devices/page.tsx` redirect shim → retire once bookmarks age out.
- `app/(dashboard)/compare/page.tsx` redirect stub → keep (cheap) or drop with a
  sidebar cleanup.
- `types/ue-dataset.ts` speculative UEDatasetStats keys (is_mobility, dataset_type)
  never produced by any backend — superseded by tick_variant/time_semantics.

### E11.S9 — Post-execution addenda (actuals from the IA pass)

- The migration mirror landed as `016_pm_ts_browse_index.sql` (012–015 were taken;
  the sequence is append-only).
- smo_sim `tests/conftest.py` does not apply `014_ndt_loop.sql`, so the new
  loop-policy-mode tests skip on a 009-only DB (they ran for real against the compose
  DB). Fix the conftest schema set when touching smo_sim tests.
- `artifacts/design/openapi.yaml` still documents `PATCH …/optimize-mode` — update at
  S3 removal (it 410s today).
- Evaluate's twin dropdown filters to status `ready` while the Twin Library Eye action
  also shows for `COMPLETED`; a `?bdt_id=` pointing at a non-ready twin silently falls
  back to the first ready twin — align the two filters.
- KPI history follow-ups: URL-sync filter/KPI/window state; breach marking uses the
  CURRENT loop policy (snapshot carries no frozen policy_ref — add one with S6);
  browser-visual QA of the new chart still pending.
- `components/common/NotEnabledDialog.tsx` is now fully unmounted (AdapterInfoDialog
  replaced its last consumer) — fold into S8 orphan cleanup.

## Sequencing

S1 and S3 are independent and first (their replacements shipped in the IA pass).
S2 waits on the scatter port. S4 is the largest (train contract + 4 repos + backfill).
S5 after cursor burn-in. S6/S7 are contract work — bundle with the next bdt_engine
contract rev. S8 rides along with whichever story touches the area.
