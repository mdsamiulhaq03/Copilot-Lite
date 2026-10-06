# EPIC 2 - Network Digital Twin consolidation (maveric_platform_bdt_engine)

**Epic ID:** E2
**Title:** NDT consolidation: evaluate API, feature builder, KPI tracking, decision hub
**Depends on:** E0 (gateway route fix, hygiene). E2.S4 additionally depends on E1 (data platform `/data/pm` API + canonical `pm_measurements`).
**Frozen HLD:** `docs/task_docs/cloudlynet-rearchitecture/01-hld-frozen.md` (conform to §3 and §4 exactly).

**Goal.** Turn `maveric_platform_bdt_engine` into the Network Digital Twin (NDT) service: it owns twin evaluation (GP predict + attachment) and KPI aggregation behind `POST /v1/tenants/{t}/ndt/evaluate`, the twin feature builder (semi-synthetic enrichment lifted from smo_sim's NybSys pipeline stages 3-6), evaluation KPI tracking, and the closed-loop decision hub (loop policy, proposal intake, evaluation gate, action dispatch, feedback watch with rollback, approval mode). rapp delegates twin evaluation to NDT while keeping its public `/rapps/**` contract byte-compatible and keeps producing the Recommendation Table locally.

**Definition of done (epic).**
- `POST /v1/tenants/{t}/ndt/evaluate` serves tick (200 sync) and day (202 + poll) with response field shapes byte-identical to what rapp's `kpi_calculator` produces today (`guardrail_kpis`, `objective_kpis`, `per_tick_kpis`, `worst_tick_stats`, `raw_tick_data`).
- rapp `/infer` day + tick paths call NDT via `NDT_BASE_URL`; golden-response regression tests prove old in-process vs new NDT path parity; duplicated twin-eval code is deleted from rapp only after parity tests pass; `/rapps/**` infer and compare responses are byte-compatible before/after.
- `bdt_engine/app/feature_builder/` consumes canonical PM via `/data/pm` and produces `baselines` + `ue_datasets` rows + S3 artifacts under the existing key conventions, labeled `semi_synthetic=true` in stats.
- `ndt_kpi_snapshots` persists evaluation KPI summaries and serves trend queries.
- Decision hub: per-tenant loop policy CRUD; `maveric.loop.proposal.v1` consumed inside the existing bdt-worker process (no new deployable); evaluation gate; dispatch on `maveric.loop.action.v1`; feedback watch on `maveric.loop.feedback.v1` with watch-window rollback ordering; audit trail in `loop_actions`; approval mode with list + approve/reject endpoints mirroring smo_sim recommendation semantics.
- Zero CI/CD change: no new charts, pipelines, images, or ports. All new env vars are env-only changes (compose + k8s `secretData` note). Shared tables and S3 key conventions stay valid throughout.

**Hard constraints inherited from the frozen HLD §3 (apply to every story):**
1. No new containers/charts/images/ports. New code rides the existing `bdt_engine`/`bdt_worker` and `rapp` image streams.
2. Gateway-routed public API contracts stay byte-compatible (`/rapps/**` infer/compare). NDT APIs are internal in this epic (X-API-Key on :8000, reached via `NDT_BASE_URL`); gateway exposure of `/ndt/**` is a later optional story, not here.
3. Shared tables (`baselines`, `ue_datasets`, `bdt_models`, `training_jobs`) and S3 key conventions (`{tenant}/baselines/{bid}/*`, `{tenant}/ue/{did}/synthetic_dataset[_mobility].csv`, `{tenant}/bdt/{bdt_id}/{bdt_id}.pickle`, `{tenant}/models/rapps/{rapp_id}/{model}.zip`) stay valid; EFS `/app/var/models` sharing persists.
4. Never copy RIC source code (amended D1: NONRTRIC is consumed as container images + REST only; the near-RT tier is a reserved placeholder). Preserve the Meta/Maveric file-level attribution in any moved twin code (`engine.py`, `cell_selection.py` headers). CLAUDE.md conventions: Pydantic-first, type hints, platform logger, DRY. Product name CloudlyNet; solution term Network Digital Twin.

**Pickle-compat rule (applies to S1, S2, S6):** BDT pickles are written by `bdt_worker` with the module path `app.radp.digital_twin.rf.bayesian.engine.BayesianDigitalTwin`, which is NATIVE inside bdt_engine. Two vendored twin copies exist in rapp (`app/radplib/dependencies/bayesian/bayesian_engine.py` and `app/radplib/dependencies/radp/digital_twin/rf/bayesian/bayesian_engine.py`) that need a module-path remap shim to unpickle. All NDT evaluation loads pickles inside bdt_engine where they are native - no remap shim, no import of rapp's vendored copies, ever. A pickle-compat regression test is mandatory (S1 acceptance).

---

## E2.S1 - NDT evaluate API: twin evaluation + KPI aggregation in bdt_engine

**Why.** The frozen HLD §4.2 moves twin-KPI scoring out of rapp into the NDT so one service owns "what would the network look like if this config were applied". bdt_engine already has the native twin (`app/radp/...`), `perform_attachment`, S3 CSV loaders, thread-pool async runner, and Redis/Mongo cache layering - the move is a lift of rapp's pure logic onto that base.

**Size:** L

**Scope**
- In: `POST /v1/tenants/{t}/ndt/evaluate` (tick sync 200; day async 202 + `GET /v1/tenants/{t}/ndt/evaluate/{run_id}`); KPI calculator module (copy of rapp's pure functions, non-MRO subset); per-tick twin evaluation service; deterministic run ids; Redis L1 + Mongo L2 + Postgres L3 caching in bdt_engine's existing pattern; new `ndt_evaluation_runs` table; pickle-compat test.
- Out: any rapp change (S2); loop/policy endpoints (S6); MRO evaluation (stays in rapp; `perform_attachment_hyst_ttt` is not part of this API); gateway routes.

**Files**
- Create `submodule/maveric_platform_bdt_engine/app/models/ndt_models.py` (Pydantic contracts)
- Create `submodule/maveric_platform_bdt_engine/app/services/kpi_calculator.py` (lifted from `submodule/maveric_platform_rapp/app/services/kpi_calculator.py`, non-MRO subset, function bodies verbatim)
- Create `submodule/maveric_platform_bdt_engine/app/services/ndt_evaluator.py` (scope orchestration + per-tick twin step)
- Create `submodule/maveric_platform_bdt_engine/app/services/ndt_evaluation_cache.py` (mirror of `app/services/inference_cache.py` for evaluation runs)
- Create `submodule/maveric_platform_bdt_engine/app/api/v1/endpoints/ndt.py`
- Modify `submodule/maveric_platform_bdt_engine/app/api/v1/routes.py` (register router; same X-API-Key dependency as `bdt.py`, see lines 6-9)
- Modify `submodule/maveric_platform_bdt_engine/app/schemas/bdt_schema.py` (add `NDTEvaluationRun` ORM; startup `create_tables` in `app/main.py:158-163` picks it up)
- Modify `artifacts/design/schemas.sql` (add `ndt_evaluation_runs`; append to updated_at trigger array)
- Create `artifacts/migration/014_ndt_loop.sql` (DDL for this epic's tables; extended by S5/S6) + update `artifacts/migration/README.md` index
- Create `submodule/maveric_platform_bdt_engine/tests/test_ndt_evaluate_api.py`, `tests/test_kpi_calculator.py`, `tests/test_ndt_pickle_compat.py`

**Contract** (HLD §4.2, verbatim; response shapes pinned from `rapp/app/services/rapp_evaluator.py:347-455` and `kpi_calculator.py`)

Request `POST /v1/tenants/{t}/ndt/evaluate`:
```json
{
  "baseline_id": "b-1", "bdt_id": "bdt-1", "ue_dataset_id": "d-1",
  "scope": {"type": "tick", "tick": 7},
  "cell_configs": [{"tick": 7, "items": [{"cell_id": "c1", "cell_el_deg": 6.0, "on_off": true}]}],
  "options": {"thresholds": {}, "energy_params": {}, "include": ["raw_ue_arrays", "ue_frames"]}
}
```
- `scope.type="day"` requires `scope.day` (int >= 0) and `cell_configs` entries carrying `tick` per entry; returns 202 `{run_id, status:"queued"}` + `Location` header; poll `GET /v1/tenants/{t}/ndt/evaluate/{run_id}` -> `{run_id, status: queued|running|completed|failed, result?, error?}`.
- `scope.type="tick"` requires `scope.tick` (0-23); a single `cell_configs` entry (its `tick` may be omitted); returns 200 sync with the result body.
- Responses use bdt_engine's standard envelope (same wrapper as `bdt.py` endpoints).

Result body (field shapes byte-identical to today's rapp output):
```json
{
  "scope": "day", "day": 0,
  "guardrail_kpis": {"outage_rate": 0.0, "coverage_rate": 0.0, "rsrp_p5": 0.0, "rsrp_p50": 0.0, "rsrp_p95": 0.0, "sinr_p5": 0.0, "sinr_p50": 0.0, "sinr_p95": 0.0, "samples": 0.0},
  "objective_kpis": {"active_cells_ratio": 0.0, "energy_saving_ratio": 0.0, "estimated_kwh_saved": 0.0, "estimated_cost_saved_monthly": 0.0, "jains_fairness_index": 0.0, "max_ue_per_cell": 0.0, "p95_ue_per_cell": 0.0},
  "per_tick_kpis": [{"tick": 0, "...guardrail keys...": 0.0, "...objective keys...": 0.0}],
  "worst_tick_stats": {"highest_outage_tick": 0, "highest_outage_rate": 0.0, "lowest_coverage_tick": 0, "lowest_coverage_rate": 0.0},
  "warnings": ["Dataset day=0 missing ticks: [...]. Evaluated available ticks only."],
  "raw_tick_data": {"7": {"rsrp": [], "sinr": [], "serving_cells": [], "cell_states": {}, "tilt_by_cell": {}, "ue_frame": {"loc_x": [], "loc_y": [], "rsrp_dbm": [], "sinr_db": [], "serving_cell_id": []}}},
  "metadata": {"tenant_id": "...", "bdt_id": "...", "baseline_id": "...", "ue_dataset_id": "...", "ticks_evaluated": 1, "thresholds": {}, "energy_params": {}, "cache_hit": false, "run_id": "..."}
}
```
Rules that guarantee byte-compat downstream:
- Day aggregation exactly mirrors `rapp_evaluator.py`: pooled rsrp/sinr across ticks -> `compute_guardrail_kpis`; `objective_kpis = average_kpis(per_tick_objectives)`; `per_tick_kpis[i] = {"tick": t, **tick_guardrails, **tick_objectives}` (guardrail keys before objective keys); `worst_tick_stats = compute_worst_tick(per_tick_guardrails)`; warnings = missing-ticks warning + `build_guardrail_warnings(guardrail_kpis, thresholds)`. Ticks absent from the dataset day slice are skipped, not zero-filled.
- `raw_tick_data` keys are STRING tick numbers. Included only when `include` contains `"raw_ue_arrays"`. NDT never emits a `"recommendations"` key inside `raw_tick_data` entries (rapp injects it locally). `"ue_frame"` is additive, present only when `include` contains `"ue_frames"`; rapp's tick path uses it to rebuild plot/diagnostics.
- `DEFAULT_THRESHOLDS` and `DEFAULT_ENERGY_PARAMS` copied verbatim from rapp `kpi_calculator.py:11-22`; `merge_thresholds`/`merge_energy_params` semantics identical (non-float overrides silently skipped).
- Day-index resolution mirrors `rapp_evaluator._resolve_effective_day`: if the requested day is absent, fall back to the first available day and append the same warning text.

Deterministic run id / cache layering (mirror `inference_cache.py:36-50` and rapp `build_evaluation_cache_key`):
```python
def generate_run_id(tenant_id: str, req: NDTEvaluateRequest) -> str:
    scope_val = req.scope.day if req.scope.type == "day" else req.scope.tick
    seed = (
        f"ndt-eval:{tenant_id}:{req.bdt_id}:{req.baseline_id}:{req.ue_dataset_id}"
        f":{req.scope.type}:{scope_val}"
        f":{sha256(canonical_json(req.cell_configs))[:16]}"
        f":{sha256(canonical_json(req.options or {}))[:16]}"
    )
    return str(uuid.uuid5(uuid.NAMESPACE_URL, seed))
# db_key = sha256(run_id); Redis key f"ndt_eval:{db_key}" TTL 7 days; Mongo collection "ndt_evaluation_cache";
# write order on completion: Mongo -> Redis -> Postgres row update (same as existing bdt inference cache).
```

SQL DDL (`ndt_evaluation_runs`, bdt_engine-owned, RLS like every tenant table):
```sql
CREATE TABLE IF NOT EXISTS public.ndt_evaluation_runs (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     uuid NOT NULL,
  run_id        text NOT NULL,
  db_key        text NOT NULL,
  bdt_id        text NOT NULL,
  baseline_id   text NOT NULL,
  ue_dataset_id text NOT NULL,
  scope         text NOT NULL,          -- 'tick' | 'day'
  scope_value   int  NOT NULL,          -- tick 0-23 or day index
  request       jsonb,
  result        jsonb,                  -- persisted WITHOUT raw_tick_data
  status        text NOT NULL DEFAULT 'queued',
  error         text,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, db_key)
);
CREATE INDEX IF NOT EXISTS idx_ndt_eval_tenant ON public.ndt_evaluation_runs (tenant_id, created_at DESC);
```

**Key snippets**

```python
# app/models/ndt_models.py
from __future__ import annotations
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, model_validator

class CellConfigItem(BaseModel):
    cell_id: str
    cell_el_deg: float
    on_off: bool

class CellConfigTick(BaseModel):
    tick: Optional[int] = Field(None, ge=0, le=23)
    items: List[CellConfigItem]

class EvaluationScope(BaseModel):
    type: Literal["tick", "day"]
    tick: Optional[int] = Field(None, ge=0, le=23)
    day: Optional[int] = Field(None, ge=0)

    @model_validator(mode="after")
    def _check(self) -> "EvaluationScope":
        if self.type == "tick" and self.tick is None:
            raise ValueError("scope.tick required when type='tick'")
        if self.type == "day" and self.day is None:
            raise ValueError("scope.day required when type='day'")
        return self

class EvaluateOptions(BaseModel):
    thresholds: Optional[Dict[str, float]] = None
    energy_params: Optional[Dict[str, float]] = None
    include: List[str] = Field(default_factory=list)  # "raw_ue_arrays", "ue_frames"

class NDTEvaluateRequest(BaseModel):
    baseline_id: str
    bdt_id: str
    ue_dataset_id: str
    scope: EvaluationScope
    cell_configs: List[CellConfigTick]
    options: Optional[EvaluateOptions] = None

class NDTEvaluationResult(BaseModel):
    scope: str
    day: Optional[int] = None
    tick: Optional[int] = None
    guardrail_kpis: Dict[str, Any]
    objective_kpis: Dict[str, Any]
    per_tick_kpis: List[Dict[str, Any]]
    worst_tick_stats: Dict[str, Any]
    warnings: List[str] = Field(default_factory=list)
    raw_tick_data: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
```

```python
# app/services/ndt_evaluator.py (core seam; twin step lifted from rapp plot_builder._run_bdt_attachment
# at rapp/app/services/utils/plot_builder.py:233-305, re-based on bdt_engine natives)
from app.radp.digital_twin.rf.bayesian.engine import BayesianDigitalTwin      # native, no remap
from app.services.utils.cell_selection import perform_attachment              # already in bdt_engine
from app.services.utils.data_loader import load_topology_df, load_config_df, load_ue_dataset_df  # reuse existing loaders/templates
from app.services import kpi_calculator

def evaluate_tick(
    *, bdt_model_map: dict[str, BayesianDigitalTwin],
    ue_tick_df: "pd.DataFrame",
    cell_config_df: "pd.DataFrame",          # active (on_off=True) cells with cell_el_deg, joined to topology
    thresholds: dict[str, float],
    energy_params: dict[str, float],
    total_cells: int,
) -> "TickEvaluation":
    """GP predict per active cell -> perform_attachment -> guardrail/objective KPIs + diagnostics."""
    ...

def evaluate_scope(*, tenant_id: str, request: NDTEvaluateRequest, run_id: str) -> NDTEvaluationResult:
    """Load pickle natively (local /app/var/models path then S3 artifacts_uri), loop requested ticks,
    aggregate exactly as rapp_evaluator did (pooled guardrails, averaged objectives, worst tick)."""
    ...
```

```python
# app/api/v1/endpoints/ndt.py (dispatch pattern mirrors bdt.py infer: cache hit -> 200; day miss -> 202 + InferenceJobRunner)
@router.post("/tenants/{tenant_id}/ndt/evaluate")
def ndt_evaluate(tenant_id: str, body: NDTEvaluateRequest, response: Response, db: Session = Depends(get_db)): ...

@router.get("/tenants/{tenant_id}/ndt/evaluate/{run_id}")
def ndt_evaluate_status(tenant_id: str, run_id: str, db: Session = Depends(get_db)): ...
```

**Acceptance criteria**
- Tick scope returns 200 synchronously; day scope returns 202 with `Location` and is pollable to `completed`; repeated identical day POST after completion returns 200 with the cached result (cache-hit path), matching bdt_engine's existing infer semantics.
- All five §4.2 response fields match rapp's current shapes key-for-key and ordering rules above; `kpi_calculator` unit tests assert numeric equality against fixture vectors computed by rapp's implementation.
- Pickle-compat test: unpickle a committed fixture pickle whose class path is `app.radp.digital_twin.rf.bayesian.engine.BayesianDigitalTwin` and run one `evaluate_tick`; no remap shim exists anywhere in bdt_engine.
- Meta/Maveric file-level attribution retained on any moved twin-adjacent code.
- `ndt_evaluation_runs` created at startup by `create_tables`; RLS DDL added to `artifacts/migration/014_ndt_loop.sql` and `artifacts/design/schemas.sql`.
- API-key enforcement identical to `/bdt/**` (router-level dependency).

**Test plan**
- Unit (`cd submodule/maveric_platform_bdt_engine && uv run pytest`): `test_kpi_calculator.py` (guardrail/objective/average/worst-tick/warnings parity vectors, empty-input zeros); `test_ndt_evaluate_api.py` (validation 422s, tick sync 200, day 202 + poll with runner mocked, cache-hit 200, envelope shape); `test_ndt_pickle_compat.py`.
- Integration (lab): compose up infra + bdt stack, train a small BDT, POST evaluate tick and day against seeded S3 CSVs, assert response fields.

**Coding-agent prompt**
```
You are working in the CloudlyNet monorepo (repo root = cloudlynet_ai). Read
docs/task_docs/cloudlynet-rearchitecture/01-hld-frozen.md sections 3 and 4.2 first.

TASK: Add the Network Digital Twin evaluate API to submodule/maveric_platform_bdt_engine.
This moves twin evaluation (GP predict + perform_attachment) and KPI aggregation from rapp
into bdt_engine. Do NOT modify the rapp submodule in this task.

CONTEXT:
- bdt_engine already contains the native twin (app/radp/digital_twin/rf/bayesian/engine.py),
  attachment (app/services/utils/cell_selection.py), S3 CSV loaders
  (app/services/utils/data_loader.py), a ThreadPoolExecutor async runner
  (app/services/inference_runner.py), Redis L1 + Mongo L2 caching
  (app/services/inference_cache.py), and X-API-Key routing (app/api/v1/routes.py).
- The KPI math to lift verbatim lives in
  submodule/maveric_platform_rapp/app/services/kpi_calculator.py (non-MRO functions only:
  merge_thresholds, merge_energy_params, as_float_list, percentile, compute_guardrail_kpis,
  compute_jains_fairness_index, compute_objective_kpis, average_kpis, compute_worst_tick,
  build_guardrail_warnings, plus DEFAULT_THRESHOLDS and DEFAULT_ENERGY_PARAMS constants).
- The day-loop aggregation semantics to replicate exactly are in
  submodule/maveric_platform_rapp/app/services/rapp_evaluator.py lines 347-455
  (pooled rsrp/sinr guardrails, average_kpis objectives, per_tick_kpis dict merge order,
  string tick keys in raw_tick_data, missing-tick skip + warning, effective-day fallback).
- The per-tick twin step to replicate is
  submodule/maveric_platform_rapp/app/services/utils/plot_builder.py lines 233-305
  (_run_bdt_attachment), re-based on bdt_engine's own BayesianDigitalTwin and
  perform_attachment. Load pickles ONLY via bdt_engine's native class path; never import
  anything from the rapp submodule; add tests/test_ndt_pickle_compat.py proving a fixture
  pickle with module path app.radp.digital_twin.rf.bayesian.engine loads without any remap.

FILES (create): app/models/ndt_models.py, app/services/kpi_calculator.py,
app/services/ndt_evaluator.py, app/services/ndt_evaluation_cache.py,
app/api/v1/endpoints/ndt.py, tests/test_ndt_evaluate_api.py, tests/test_kpi_calculator.py,
tests/test_ndt_pickle_compat.py (all under submodule/maveric_platform_bdt_engine).
FILES (modify): app/api/v1/routes.py (register router with the same API-key dependency as
bdt endpoints), app/schemas/bdt_schema.py (NDTEvaluationRun ORM; startup create_tables in
app/main.py picks it up), and in the PARENT repo artifacts/design/schemas.sql +
artifacts/migration/014_ndt_loop.sql (create) + artifacts/migration/README.md (index entry).

API CONTRACT (frozen HLD 4.2): POST /v1/tenants/{t}/ndt/evaluate with body
{baseline_id, bdt_id, ue_dataset_id, scope:{type:"tick"|"day", tick?, day?},
 cell_configs:[{tick?, items:[{cell_id, cell_el_deg, on_off}]}],
 options?:{thresholds, energy_params, include}}.
tick -> 200 sync; day -> 202 {run_id} + Location, poll GET /v1/tenants/{t}/ndt/evaluate/{run_id}.
Result carries guardrail_kpis, objective_kpis, per_tick_kpis, worst_tick_stats, warnings,
raw_tick_data (only when include has "raw_ue_arrays"; add "ue_frame" per tick only when
include has "ue_frames": {loc_x[], loc_y[], rsrp_dbm[], sinr_db[], serving_cell_id[]}),
metadata. Field shapes must be byte-identical to rapp's current kpi_calculator output.
Never emit a "recommendations" key inside raw_tick_data. Deterministic run_id = UUIDv5 over
"ndt-eval:{tenant}:{bdt}:{baseline}:{dataset}:{scope_type}:{scope_val}:
{sha256(canonical_json(cell_configs))[:16]}:{sha256(canonical_json(options))[:16]}";
db_key = sha256(run_id); Redis key ndt_eval:{db_key} TTL 7d; Mongo collection
ndt_evaluation_cache; Postgres table ndt_evaluation_runs (DDL in the epic doc
docs/task_docs/cloudlynet-rearchitecture/epics/EPIC-2-ndt-consolidation.md, story E2.S1).
Persist result WITHOUT raw_tick_data.

CONSTRAINTS: zero CI/CD change (no new services/ports); Pydantic-first models; type hints;
platform logger (app/utils/logger.py); preserve Meta/Maveric attribution headers on moved
twin code; X-API-Key required on all /v1 routes.

DONE WHEN: cd submodule/maveric_platform_bdt_engine && uv run pytest passes including the
three new test files; tick returns 200 sync and day 202+poll; the response JSON for a
seeded fixture matches the committed golden fixture key-for-key.
```

---

## E2.S2 - rapp delegation: NDT client + dual-path flag + golden parity tests

**Why.** rapp's public `/rapps/**/infer` contract must stay byte-compatible while the heavy twin step moves out. A dual-path flag plus recorded golden responses is the only safe way to prove parity before deleting anything.

**Size:** L

**Scope**
- In: `NDT_BASE_URL`/`NDT_API_KEY` env (rapp README env table, compose env, k8s secretData note); `app/services/ndt_client.py`; delegation in the non-MRO day path (`rapp_evaluator.evaluate_rapp`) and tick path (`real_inference._build_inference_result_non_mro`) selected by `RAPP_TWIN_EVAL_MODE=local|ndt` (default `local`); golden-response regression tests comparing both paths; per_tick_recommendations remain locally produced from PPO predictions.
- Out: deleting any rapp code (S3); MRO evaluation path (`_evaluate_mro`, `perform_attachment_hyst_ttt`) - unchanged, stays in-process; training paths (rapp-worker still copies BDT pickles for RL envs - untouched).

**Files**
- Create `submodule/maveric_platform_rapp/app/services/ndt_client.py`
- Modify `submodule/maveric_platform_rapp/app/services/rapp_evaluator.py` (day loop: replace the per-tick `build_real_inference_result(include_debug=True)` + kpi aggregation block, lines 356-455, with: generate PPO recommendations per tick -> build `cell_configs` -> one NDT day evaluate -> merge)
- Modify `submodule/maveric_platform_rapp/app/services/real_inference.py` (tick path `_build_inference_result_non_mro`: steps 5-7 - BDT pickle resolve, `_run_bdt_attachment`, diagnostics - replaced by NDT tick evaluate with `include=["raw_ue_arrays","ue_frames"]`; plot payload, `metrics.diagnostics`, and `optimization_metric` rebuilt locally from `ue_frame`)
- Modify `submodule/maveric_platform_rapp/app/core/config.py` (the repo's actual settings module, accessed via `get_settings()`; settings: `NDT_BASE_URL`, `NDT_API_KEY`, `RAPP_TWIN_EVAL_MODE`, `NDT_EVAL_TIMEOUT_S` default 900, `NDT_POLL_INTERVAL_S` default 2.0)
- Modify `docker-compose.yaml` (rapp service: add `environment:` entries `NDT_BASE_URL: http://bdt_engine:8000`, `NDT_API_KEY: ${BDT_API_KEY:-...}`, `RAPP_TWIN_EVAL_MODE: ${RAPP_TWIN_EVAL_MODE:-local}`; rapp currently uses only `env_file`)
- Modify `submodule/maveric_platform_rapp/README.md` (env table)
- Create `submodule/maveric_platform_rapp/tests/golden/` fixtures + `tests/test_ndt_parity.py`, `tests/test_ndt_client.py`

**Contract**
- rapp -> NDT hop: `POST {NDT_BASE_URL}/v1/tenants/{t}/ndt/evaluate` with header `X-API-Key: {NDT_API_KEY}` (`NDT_API_KEY` = the bdt service key, per HLD §4.2). Day: submit then poll `GET .../evaluate/{run_id}` every `NDT_POLL_INTERVAL_S` up to `NDT_EVAL_TIMEOUT_S`; rapp's public day `/infer` stays synchronous 200.
- Merge rules that keep `/rapps/**` byte-compatible (`DayEvaluationResult` in `app/models/rapp.py:253-264` unchanged):
  - `guardrail_kpis`, `objective_kpis`, `per_tick_kpis`, `worst_tick_stats`, `warnings` taken verbatim from the NDT result; rapp appends nothing except its existing day-load warnings that occur before the NDT call.
  - `per_tick_recommendations` built locally from PPO `text` payloads exactly as today (`rapp_evaluator.py:401-406`).
  - `raw_tick_data`: passthrough of NDT's entries with rapp injecting `"recommendations": <that tick's recommendation dict>` into each tick entry and stripping `"ue_frame"` (never exposed publicly).
  - `metadata` remains rapp-assembled (model_hash, dataset_hash, cache_key, thresholds, energy_params etc. - unchanged keys).
  - Evaluation cache: `rapp_evaluation_results` + Redis `rapp_eval:{sha256}` keying is untouched (`build_evaluation_cache_key` unchanged; `merge_thresholds`/`merge_energy_params` stay in rapp so cache keys are stable).

**Key snippets**
```python
# app/services/ndt_client.py
from __future__ import annotations
import httpx
from app.core.config import get_settings
from app.utils.logger import get_logger

class NDTClientError(RuntimeError): ...
class NDTEvaluationTimeout(NDTClientError): ...

class NDTClient:
    """Thin client for the Network Digital Twin evaluate API (frozen HLD 4.2)."""
    def __init__(self, base_url: str | None = None, api_key: str | None = None) -> None:
        settings = get_settings()
        self._base_url = (base_url or settings.NDT_BASE_URL).rstrip("/")
        self._headers = {"X-API-Key": api_key or settings.NDT_API_KEY}

    def evaluate_tick(self, *, tenant_id: str, payload: dict) -> dict:
        """Sync tick evaluation; returns the unwrapped result body."""
        ...

    def evaluate_day(self, *, tenant_id: str, payload: dict,
                     timeout_s: float | None = None) -> dict:
        """Submit day evaluation (202) and poll GET .../evaluate/{run_id} to completion."""
        ...
```
```python
# rapp_evaluator.py day path (mode == "ndt")
cell_configs = [
    {"tick": tick, "items": [i for i in per_tick_text[tick]["items"]]}
    for tick in ticks_with_predictions
]
ndt_result = NDT_CLIENT.evaluate_day(tenant_id=tenant_id, payload={
    "baseline_id": baseline_id, "bdt_id": bdt_id, "ue_dataset_id": ue_dataset_id,
    "scope": {"type": "day", "day": resolved_day},
    "cell_configs": cell_configs,
    "options": {"thresholds": merged_thresholds, "energy_params": merged_energy,
                "include": (["raw_ue_arrays"] if include_raw_arrays else [])},
})
```

**Acceptance criteria**
- With `RAPP_TWIN_EVAL_MODE=local` behavior is bit-for-bit today's (default; zero risk on deploy).
- With `RAPP_TWIN_EVAL_MODE=ndt`, `/rapps/**/infer` (tick + day, ES/LB/CCO) and `/rapps/compare/infer` responses deep-equal the local path on the golden fixtures, excluding only `metadata.cache_key`-adjacent timing fields explicitly listed in the test.
- MRO `/infer` behavior unchanged in both modes.
- New env vars documented in rapp README; compose entries added; k8s note recorded in this epic's rollout section (secretData addition is env-only, no chart change).
- Golden fixtures are committed and generated by a reproducible script (seeded inputs).

**Test plan**
- Unit (`cd submodule/maveric_platform_rapp && PYTHONPATH=app:app/radplib/dependencies uv run pytest`): `test_ndt_client.py` (httpx MockTransport: 200 tick, 202+poll day, timeout -> NDTEvaluationTimeout, non-2xx -> NDTClientError); `test_ndt_parity.py` (NDT response fixture -> merge -> DayEvaluationResult equals committed golden JSON; raw_tick_data recommendation injection; ue_frame stripping).
- Integration (lab, gates S3): compose up full stack; run the same day + tick `/infer` calls once per mode; diff JSON byte-wise (script `scripts/` or test marked `integration`).

**Coding-agent prompt**
```
You are working in the CloudlyNet monorepo (repo root = cloudlynet_ai). Read
docs/task_docs/cloudlynet-rearchitecture/01-hld-frozen.md sections 3 and 4.2, then story
E2.S2 in docs/task_docs/cloudlynet-rearchitecture/epics/EPIC-2-ndt-consolidation.md.

TASK: Make rapp delegate twin evaluation to the NDT evaluate API behind a dual-path env
flag, with golden-response parity tests. Do NOT delete any existing rapp code in this task.

CONTEXT:
- The NDT evaluate API already exists in bdt_engine (story E2.S1):
  POST /v1/tenants/{t}/ndt/evaluate (tick 200 sync, day 202 + poll GET .../evaluate/{run_id}),
  X-API-Key auth. Response fields: guardrail_kpis, objective_kpis, per_tick_kpis,
  worst_tick_stats, warnings, raw_tick_data (string tick keys; optional per-tick "ue_frame"
  {loc_x[], loc_y[], rsrp_dbm[], sinr_db[], serving_cell_id[]} when include has "ue_frames").
- rapp's day loop is submodule/maveric_platform_rapp/app/services/rapp_evaluator.py
  (evaluate_rapp, lines 188-495); the tick pipeline is
  app/services/real_inference.py (_build_inference_result_non_mro); the twin step it
  currently runs in-process is app/services/utils/plot_builder.py (_run_bdt_attachment).
- rapp KEEPS: PPO recommendation generation (per_tick_recommendations / text payloads),
  metadata assembly, rapp_evaluation_results + Redis caching and cache keys
  (merge_thresholds/merge_energy_params stay), the MRO path (_evaluate_mro) untouched,
  and all rapp-worker training code untouched.
- httpx==0.26.0 is already a rapp dependency.

IMPLEMENT:
1. app/services/ndt_client.py: NDTClient.evaluate_tick / evaluate_day (submit+poll),
   settings NDT_BASE_URL, NDT_API_KEY, RAPP_TWIN_EVAL_MODE (local|ndt, default local),
   NDT_EVAL_TIMEOUT_S=900, NDT_POLL_INTERVAL_S=2.0 in app/core/config.py (the repo's
   actual settings module; access via the existing get_settings() accessor - there is
   NO app/config.py, do not create one).
2. rapp_evaluator.evaluate_rapp: when mode=ndt, generate PPO predictions per tick first
   (existing code), build cell_configs [{tick, items:[{cell_id, cell_el_deg, on_off}]}]
   from predictions_to_cell_configs output, call evaluate_day once, then assemble
   DayEvaluationResult: NDT fields verbatim; per_tick_recommendations local; inject
   "recommendations" into each raw_tick_data tick entry; strip "ue_frame"; metadata as
   today. When mode=local, code path is exactly today's.
3. real_inference._build_inference_result_non_mro: when mode=ndt, replace BDT pickle
   resolution + _run_bdt_attachment + diagnostics with one evaluate_tick call
   (include=["raw_ue_arrays","ue_frames"]); rebuild attached_data DataFrame from ue_frame
   (columns loc_x, loc_y, rsrp_dbm, sinr_db, cell_id=serving_cell_id) and feed the existing
   _generate_plot_payload / metrics_builder code so plot, metrics.diagnostics,
   optimization_metric, and text are byte-identical.
4. docker-compose.yaml (repo root): add environment entries to the rapp service:
   NDT_BASE_URL: http://bdt_engine:8000, NDT_API_KEY: ${BDT_API_KEY:-<existing bdt key var>},
   RAPP_TWIN_EVAL_MODE: ${RAPP_TWIN_EVAL_MODE:-local}. Update the rapp README env table.
   Do not touch charts, ports, images, or CI.
5. Tests: tests/test_ndt_client.py (httpx.MockTransport), tests/test_ndt_parity.py with
   committed golden fixtures under tests/golden/ comparing local-path output vs
   ndt-path output (NDT mocked with the recorded evaluate response) for ES day scope,
   ES tick scope, and compare/infer.

CONSTRAINTS: public /rapps/** responses byte-compatible; default mode local so deploys are
inert; Pydantic-first, type hints, platform logger; no new services/ports; never import
bdt_engine code into rapp.

DONE WHEN: cd submodule/maveric_platform_rapp &&
PYTHONPATH=app:app/radplib/dependencies uv run pytest passes; parity test proves
deep-equality of both modes on the golden fixtures.
```

---

## E2.S3 - Delete rapp's duplicated twin-eval path (after parity)

**Why.** Two copies of twin evaluation is the exact duplication the re-architecture kills; once parity is proven the local path is dead weight and a drift hazard.

**Size:** M

**Scope**
- In: flip `RAPP_TWIN_EVAL_MODE` default to `ndt`, then remove the flag and the local path; delete inference-path twin code from rapp; keep everything training-time and MRO.
- Out: `app/radplib/dependencies` (stays - rapp-worker RL training envs and MRO evaluation still unpickle BDTs there); `app/workers/utils/bdt_resolver.py` (training); MRO functions in `kpi_calculator.py`.

**Files (modify/delete within `submodule/maveric_platform_rapp/`)**
- `app/services/utils/plot_builder.py`: delete `_run_bdt_attachment` (233-305), `_load_bdt_model_map_cached` (36-41), and BDT-touching branches of `build_plot_data`; keep `predictions_to_cell_configs`, `_create_default_config`, plot payload generation.
- `app/services/utils/data_loader.py`: delete the API-side BDT pickle resolution block (lines 341-516); keep CSV loaders and the RL agent .zip resolution (519-780).
- `app/services/kpi_calculator.py`: delete non-MRO aggregation functions (`compute_guardrail_kpis`, `compute_objective_kpis`, `compute_jains_fairness_index`, `average_kpis`, `compute_worst_tick`, `build_guardrail_warnings`); KEEP shared helpers (`as_float_list`, `percentile`), `merge_thresholds`/`merge_energy_params` (cache keys), and all MRO functions (`merge_mro_thresholds`, `compute_mro_guardrail_kpis`, `compute_mro_objective_kpis`, `build_mro_warnings`).
- `app/services/rapp_evaluator.py`, `app/services/real_inference.py`, `app/core/config.py`: remove `RAPP_TWIN_EVAL_MODE` and the `local` branches; NDT path becomes the only path.
- `docker-compose.yaml`: drop the `RAPP_TWIN_EVAL_MODE` entry.
- Tests: update/remove tests that exercised the local twin path; parity tests become NDT-fixture regression tests.

**Contract.** No external contract change; `/rapps/**` responses remain byte-identical (guarded by the golden fixtures from S2, now asserted against the NDT path only).

**Acceptance criteria**
- Grep-clean: no `predict_distributed_gpmodel`, `create_prediction_frames`, or `perform_attachment(` call remains under `app/services/` (MRO's `perform_attachment_hyst_ttt` in `rapp_evaluator._evaluate_mro` remains, and `app/radplib/**` is exempt).
- Golden regression suite passes against the NDT path.
- MRO train/infer and non-MRO training (`rapp-worker`) still pass their existing tests unchanged.

**Test plan**
- `cd submodule/maveric_platform_rapp && PYTHONPATH=app:app/radplib/dependencies uv run pytest` full suite green.
- Integration: one full compose run of ES day `/infer`, tick `/infer`, `compare/infer`, MRO `/infer` against the golden expectations.

**Coding-agent prompt**
```
You are working in the CloudlyNet monorepo (repo root = cloudlynet_ai). Read story E2.S3 in
docs/task_docs/cloudlynet-rearchitecture/epics/EPIC-2-ndt-consolidation.md and the frozen
HLD docs/task_docs/cloudlynet-rearchitecture/01-hld-frozen.md section 3.

PRECONDITION (verify before changing anything): rapp's NDT delegation exists
(app/services/ndt_client.py) and tests/test_ndt_parity.py passes. If not, STOP and report.

TASK: In submodule/maveric_platform_rapp, remove the now-duplicated in-process twin
evaluation path and make the NDT path the only inference-time evaluation path.

DELETE (inference path only): plot_builder._run_bdt_attachment and
_load_bdt_model_map_cached; the BDT pickle resolution block in
app/services/utils/data_loader.py lines ~341-516; non-MRO aggregation functions in
app/services/kpi_calculator.py (compute_guardrail_kpis, compute_objective_kpis,
compute_jains_fairness_index, average_kpis, compute_worst_tick, build_guardrail_warnings);
the RAPP_TWIN_EVAL_MODE flag and all mode=local branches in rapp_evaluator.py,
real_inference.py, app/core/config.py, and the repo-root docker-compose.yaml rapp service.

KEEP UNTOUCHED: app/radplib/** (vendored twin needed by rapp-worker RL training envs and
MRO), app/workers/** including workers/utils/bdt_resolver.py, MRO evaluation
(_evaluate_mro, perform_attachment_hyst_ttt), merge_thresholds/merge_energy_params and
as_float_list/percentile helpers (cache keys + MRO use them), predictions_to_cell_configs,
plot payload generation, all caching (rapp_evaluation_results, Redis, inference_runs).

DONE WHEN: cd submodule/maveric_platform_rapp &&
PYTHONPATH=app:app/radplib/dependencies uv run pytest is green; grep confirms no
predict_distributed_gpmodel / create_prediction_frames / perform_attachment( usage under
app/services/ (perform_attachment_hyst_ttt exempt; app/radplib exempt); the golden
regression tests still assert byte-identical /rapps/** responses.
```

---

## E2.S4 - Twin feature builder in bdt_engine (pipeline stages 3-6 + shared placement lib)

**Why.** HLD D3/§4.6: the semi-synthetic enrichment (topology synthesis, stochastic guardrail, UE placement, RSRP labeling) belongs to the Network Digital Twin, consuming canonical PM from the data platform instead of raw vendor CSVs, and the smo_sim/data_sim placement duplication dies.

**Size:** L

**Scope**
- In: `bdt_engine/app/feature_builder/` package lifted from `smo_sim/app/lib/nybsys/` stages 3-6 (`build_topology_and_config`, `apply_stochastic_guardrail`, `generate_ue_data`, `generate_ue_training_data`) plus their support modules (`defaults.py`, `geo.py`, `models.py`, `rules.py`, `pl_models/`); one canonical placement/geometry lib vendored at `app/feature_builder/placement/` (seeded from `data_sim/app/utils/placement/`, the structured mirror of smo_sim's `placement.py`); PM source client for `GET /data/pm`; build API 202 + poll; `baselines` + `ue_datasets` rows + S3 artifacts under existing key conventions; `semi_synthetic=true` labeling; additive `baselines.stats jsonb` column.
- Out: deleting smo_sim's pipeline (E1 moves the upload API to data_sim store-only; ALL smo_sim code removal is owned by E4.S6, the sole decommission owner - this story only copies); deleting data_sim's `app/ingest/legacy_builder/` (that is E2.S9, the cutover story); data_sim changes (it keeps its golden generators and its own placement copy - only add a header comment in data_sim pointing to the canonical copy, optional and non-functional); any Kafka trigger (API-initiated only in this epic).

**Files**
- Create `submodule/maveric_platform_bdt_engine/app/feature_builder/__init__.py`, `pipeline.py`, `rules.py`, `defaults.py`, `geo.py`, `models.py`, `pl_models/` (lift from `submodule/maveric_platform_smo_sim/app/lib/nybsys/{pipeline.py,rules.py,defaults.py,geo.py,models.py,pl_models/}` - stages 3-6 only: pipeline functions `build_topology_and_config` (:221), `apply_stochastic_guardrail` (rules.py), `generate_ue_data` (:422), `generate_ue_training_data` (:709), `build_voronoi_polygons` (:326) and their private helpers; drop stages 1-2 `load_and_merge_csvs`/`aggregate_pm_to_day_tick` - E1's store-only adapter owns raw parsing)
- Create `submodule/maveric_platform_bdt_engine/app/feature_builder/placement/` (vendor `submodule/maveric_platform_data_sim/app/utils/placement/{samplers.py,context.py,geo.py,models.py,calibration.py}`; header comment: canonical home, data_sim keeps its own copy for golden generators)
- Create `submodule/maveric_platform_bdt_engine/app/feature_builder/pm_source.py` (data platform client)
- Create `submodule/maveric_platform_bdt_engine/app/services/feature_build_runner.py` (job orchestration on the existing `InferenceJobRunner` thread pool)
- Modify `submodule/maveric_platform_bdt_engine/app/api/v1/endpoints/ndt.py` (add build endpoints)
- Modify `submodule/maveric_platform_bdt_engine/app/schemas/bdt_schema.py` (`NDTFeatureBuild` ORM), `app/config.py` (`DATA_PLATFORM_BASE_URL`, `DATA_PLATFORM_API_KEY`, `FEATURE_BUILDER_CONN_METRIC` default `"RRC.ConnMean"`), `requirements.txt` (add `scipy`, `shapely` - the lifted pipeline uses Voronoi placement; optional-import fallback preserved)
- Modify `docker-compose.yaml` (bdt_engine service env: `DATA_PLATFORM_BASE_URL: http://data_sim:8003`, `DATA_PLATFORM_API_KEY: ${DATA_API_KEY:-...}`)
- Modify `artifacts/design/schemas.sql` + `artifacts/migration/014_ndt_loop.sql` (add `ndt_feature_builds`; `ALTER TABLE public.baselines ADD COLUMN IF NOT EXISTS stats jsonb;` - additive, keeps the shared table valid)
- Create `submodule/maveric_platform_bdt_engine/tests/test_feature_builder.py`, `tests/test_pm_source.py`

**Contract**

API (the E1.S4 feature-builder seam, implemented EXACTLY as E1.S4 defines it - E1's `NdtApiBuilder` drives these routes; do not invent an alternative route or body):
```
POST /v1/tenants/{t}/ndt/feature-builds              -> 202 {build_id, status: "queued"} + Location
GET  /v1/tenants/{t}/ndt/feature-builds/{build_id}   -> {build_id, status: queued|running|completed|failed,
                                                         error: null|str, stats?,
                                                         artifacts: {baseline_id, ue_dataset_id} | null}
```
Request (byte-for-byte the E1.S4 seam body):
```json
{
  "build_id": "<upload_id or operator-chosen id>",
  "source_type": "nybsys_pm_csv",
  "pm_query": {"source": "nybsys_pm_csv", "vendor": "nybsys", "dn_prefix": "", "from_ts": "2026-07-01T00:00:00Z", "to_ts": "2026-07-08T00:00:00Z", "labels": {"upload_id": "<upload_id>"}},
  "targets": {"baseline_id": "b-2026w28", "ue_dataset_id": "d-2026w28"},
  "params": {"rng_seed": 42, "samples_per_cell": 200, "bbox": null, "conn_metric": "RRC.ConnMean"}
}
```
- `build_id` is the idempotency key, unique per tenant: `409 BUILD_EXISTS` if it exists in a non-failed state (a failed build may be resubmitted under the same id); repeated GETs poll the same run. All `pm_query` filters are optional individually, but at least one of `labels.upload_id` or `from_ts`/`to_ts` is required; `labels.upload_id` filters via the `/data/pm` `upload_id` query param (E1.S5) and is the path the legacy upload flow uses.
- 409 also if `targets.baseline_id` or `targets.ue_dataset_id` already exists for the tenant (mirrors data_sim/smo_sim behavior).
- Input: canonical PM rows from `GET {DATA_PLATFORM_BASE_URL}/v1/tenants/{t}/data/pm` (E1, §4.3) filtered by `pm_query` (incl. `upload_id`), paginated. The builder reconstructs the per (site, cell, day, tick) `conn_mean` grid from rows whose `metric` equals `params.conn_metric` (canonical vocabulary per §4.3: TS 28.552 name where mapped, else `vendor:<name>`); `dn` carries site/cell identity; `day`/`tick` come from the canonical columns (no re-aggregation - stage 2 already ran in the data platform).
- Output (existing conventions, unchanged consumers): S3 `{tenant}/baselines/{bid}/topology.csv|config.csv|ue_training_data.csv` and `{tenant}/ue/{did}/synthetic_dataset.csv`; Postgres `baselines` row (with `stats` jsonb) and `ue_datasets` row (`source_type='utils_traffic_load'`, same as today's nybsys_runner, so rApp training is untouched).
- Labeling (claims honesty, §4.6): `baselines.stats` and `ue_datasets.stats` both include `{"semi_synthetic": true, "synthesis": {"geometry": "synthetic", "ue_positions": "synthetic", "rsrp_labels": "tr38901_model", "real_inputs": ["site_cell_inventory", "time_range", "conn_mean"]}, "rng_seed": <seed>}`.
- Determinism: `rng_seed` recorded in `ndt_feature_builds.request` and in stats; identical inputs + seed produce identical CSVs.

DDL:
```sql
CREATE TABLE IF NOT EXISTS public.ndt_feature_builds (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL,
  build_id    text NOT NULL,                    -- E1.S4 seam idempotency key
  baseline_id text NOT NULL,
  dataset_id  text NOT NULL,
  request     jsonb,
  stats       jsonb,
  status      text NOT NULL DEFAULT 'queued',   -- queued|running|completed|failed
  error       text,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, build_id)
);
```

**Key snippets**
```python
# app/feature_builder/pm_source.py
class PMQuery(BaseModel):
    source: Optional[str] = None
    vendor: Optional[str] = None
    dn_prefix: Optional[str] = None
    from_ts: Optional[datetime] = None
    to_ts: Optional[datetime] = None
    labels: Optional[Dict[str, str]] = None   # {"upload_id": ...} -> /data/pm ?upload_id= filter (E1.S5)

def fetch_conn_mean_grid(*, tenant_id: str, query: PMQuery, conn_metric: str) -> pd.DataFrame:
    """Page through GET /data/pm and pivot to columns [siteId, cellId, day, tick, conn_mean].

    dn convention (E1): 'site={siteId},cell={cellId}'. labels.upload_id maps to the
    upload_id query param. Rows with other metrics are ignored.
    Raises FeatureBuildInputError when zero rows match.
    """
    ...
```
```python
# app/feature_builder/pipeline.py (lifted signatures kept intact so smo_sim tests port over)
def build_topology_and_config(agg: pd.DataFrame, *, bbox: Bounds | None, rng: np.random.Generator, defaults: TopologyDefaults) -> tuple[pd.DataFrame, pd.DataFrame]: ...
def generate_ue_data(...) -> pd.DataFrame: ...
def generate_ue_training_data(...) -> pd.DataFrame: ...

def run_feature_build(*, tenant_id: str, request: FeatureBuildRequest, build_id: str) -> FeatureBuildStats:
    """conn_mean grid (pm_source) -> stages 3-6 -> S3 uploads -> baselines + ue_datasets rows."""
    ...
```

**Acceptance criteria**
- The routes and request/response bodies match E1.S4's seam contract byte-for-byte (`POST /ndt/feature-builds` body `{build_id, source_type, pm_query, targets, params}` -> 202 `{build_id, status}`; E1 ships a stub-server test double - its parity fixtures must pass against this implementation); `pm_query.labels.upload_id` selects exactly one upload's canonical rows.
- Given a seeded canonical PM fixture, the builder emits topology.csv (same 21-column schema as `artifacts/nanolink/nybsys_data_contract.md`), config.csv, ue_training_data.csv, synthetic_dataset.csv byte-stable under a fixed `rng_seed`, at the exact existing S3 keys.
- A BDT train job on the produced baseline and an rApp train on the produced dataset run without any change to bdt-worker/rapp-worker (schema-identical artifacts).
- `baselines.stats` and `ue_datasets.stats` carry `semi_synthetic: true` with the synthesis breakdown.
- 409 on duplicate baseline/dataset ids; failed builds mark status `failed` and best-effort purge partial S3 artifacts (mirror `nybsys_runner` failure path).
- No user-facing copy claims real geometry or drive-test data (claims-guardrails).

**Test plan**
- Unit (`cd submodule/maveric_platform_bdt_engine && uv run pytest`): `test_pm_source.py` (pagination, pivot, dn parsing, empty -> error); `test_feature_builder.py` (stage parity against fixtures ported from smo_sim's pipeline tests where they exist; determinism under seed; stats labeling; 409s; failure purge).
- Integration (lab): compose with E1's data platform seeded via a NanoLink CSV ingest, run a build, then a BDT train + rApp train end-to-end.

**Coding-agent prompt**
```
You are working in the CloudlyNet monorepo (repo root = cloudlynet_ai). Read
docs/task_docs/cloudlynet-rearchitecture/01-hld-frozen.md sections 3, 4.3, 4.6, then story
E2.S4 in docs/task_docs/cloudlynet-rearchitecture/epics/EPIC-2-ndt-consolidation.md.

TASK: Build the twin feature builder inside submodule/maveric_platform_bdt_engine at
app/feature_builder/, lifting the semi-synthetic enrichment stages 3-6 from
submodule/maveric_platform_smo_sim/app/lib/nybsys/ (pipeline.py functions
build_topology_and_config, generate_ue_data, generate_ue_training_data,
build_voronoi_polygons + rules.py apply_stochastic_guardrail + defaults.py, geo.py,
models.py, pl_models/). Do NOT modify smo_sim or data_sim. Do NOT lift stages 1-2
(load_and_merge_csvs, aggregate_pm_to_day_tick) - the data platform owns those.

INPUT: canonical PM via GET {DATA_PLATFORM_BASE_URL}/v1/tenants/{t}/data/pm (Epic 1 API;
schema per frozen HLD 4.3: pm_measurements with dn, metric, value, day, tick). Build a
conn_mean grid [siteId, cellId, day, tick, conn_mean] from rows where metric ==
options.conn_metric (default "RRC.ConnMean"); dn format 'site={siteId},cell={cellId}'.
New settings in app/config.py: DATA_PLATFORM_BASE_URL, DATA_PLATFORM_API_KEY,
FEATURE_BUILDER_CONN_METRIC. Add scipy and shapely to requirements.txt (keep the
pipeline's optional-import graceful fallback).

PLACEMENT LIB: vendor submodule/maveric_platform_data_sim/app/utils/placement/
(samplers.py, context.py, geo.py, models.py, calibration.py) into
app/feature_builder/placement/ as the canonical copy; adjust imports; add a header noting
data_sim keeps its own copy for the golden generators.

API: implement the E1.S4 feature-builder seam EXACTLY (read EPIC-1 story E1.S4 Contract
item 3 - it is the definition of record; data_sim's NdtApiBuilder drives it):
POST /v1/tenants/{t}/ndt/feature-builds with body {build_id, source_type,
pm_query:{source, vendor?, dn_prefix?, from_ts?, to_ts?, labels?:{upload_id}},
targets:{baseline_id, ue_dataset_id}, params:{rng_seed, samples_per_cell, bbox?,
conn_metric?}} -> 202 {build_id, status:"queued"} + Location; poll
GET /v1/tenants/{t}/ndt/feature-builds/{build_id} -> {build_id, status, error, artifacts}.
409 BUILD_EXISTS when build_id exists in a non-failed state; 409 when a target
baseline/dataset id already exists. pm_query.labels.upload_id filters /data/pm via its
upload_id query param. DDL per the epic doc (table ndt_feature_builds keyed on
(tenant_id, build_id); also ALTER TABLE public.baselines ADD COLUMN IF NOT EXISTS stats
jsonb in artifacts/design/schemas.sql + artifacts/migration/014_ndt_loop.sql). Execute
builds on the existing InferenceJobRunner thread pool (no new deployable, no Kafka).

OUTPUT (existing conventions, byte-level consumer compatibility):
S3 {tenant}/baselines/{bid}/topology.csv|config.csv|ue_training_data.csv and
{tenant}/ue/{did}/synthetic_dataset.csv; Postgres baselines row + ue_datasets row
(source_type='utils_traffic_load'). Column schemas must match
artifacts/nanolink/nybsys_data_contract.md sections on outputs. Label
{"semi_synthetic": true, ...synthesis breakdown..., "rng_seed": seed} in both stats
columns. 409 on existing baseline_id/dataset_id; on failure set status failed and
best-effort purge partial S3 artifacts (mirror
smo_sim/app/services/nybsys_runner.py failure handling).

CONSTRAINTS: deterministic under rng_seed; Pydantic-first; type hints; platform logger;
no new containers/ports; preserve any upstream attribution headers on moved code; never
describe outputs as real network geometry or drive-test data in docstrings or copy.

DONE WHEN: cd submodule/maveric_platform_bdt_engine && uv run pytest passes including
tests/test_feature_builder.py and tests/test_pm_source.py; a fixture-driven build produces
byte-stable CSVs at the exact S3 keys and correctly labeled registry rows.
```

---

## E2.S5 - KPI tracking: `ndt_kpi_snapshots` + trend query API

**Why.** Every evaluation currently evaporates into caches; persisting KPI summaries gives operators trend lines and gives the decision hub (S6) an audit-quality KPI record per gate decision.

**Size:** S

**Scope**
- In: `ndt_kpi_snapshots` table; snapshot write on every completed evaluation (S1 path) and later from the loop gate (S6, `source='loop_gate'`); `GET /v1/tenants/{t}/ndt/kpis` with filters.
- Out: frontend/gateway exposure (later story); retention jobs (note only).

**Files**
- Create `submodule/maveric_platform_bdt_engine/app/services/ndt_kpi_store.py`
- Modify `submodule/maveric_platform_bdt_engine/app/services/ndt_evaluator.py` (write snapshot on completion), `app/api/v1/endpoints/ndt.py` (GET), `app/schemas/bdt_schema.py` (ORM)
- Modify `artifacts/design/schemas.sql` + `artifacts/migration/014_ndt_loop.sql`
- Create `submodule/maveric_platform_bdt_engine/tests/test_ndt_kpi_store.py`

**Contract**
```sql
CREATE TABLE IF NOT EXISTS public.ndt_kpi_snapshots (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        uuid NOT NULL,
  run_id           text NOT NULL,
  source           text NOT NULL DEFAULT 'evaluate',  -- 'evaluate' | 'loop_gate'
  bdt_id           text,
  baseline_id      text,
  ue_dataset_id    text,
  scope            text NOT NULL,
  scope_value      int,
  guardrail_kpis   jsonb NOT NULL,
  objective_kpis   jsonb,
  worst_tick_stats jsonb,
  semi_synthetic   boolean NOT NULL DEFAULT false,   -- true when the baseline stats say so
  created_at       timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, run_id, source)
);
CREATE INDEX IF NOT EXISTS idx_ndt_kpi_tenant_time ON public.ndt_kpi_snapshots (tenant_id, created_at DESC);
```
API: `GET /v1/tenants/{t}/ndt/kpis?bdt_id=&baseline_id=&source=&from_ts=&to_ts=&limit=100&offset=0` -> envelope `{items: [...rows...], total: n}` ordered `created_at DESC`. Upsert on conflict (idempotent re-completion).

**Key snippets**
```python
def record_snapshot(db: Session, *, tenant_id: str, run_id: str, source: str,
                    result: NDTEvaluationResult, ids: EvaluationIds,
                    semi_synthetic: bool) -> None:
    """INSERT ... ON CONFLICT (tenant_id, run_id, source) DO UPDATE. Never raises into the
    evaluation path: failures are logged at error level and swallowed."""
```

**Acceptance criteria**
- Completed tick and day evaluations each produce exactly one snapshot row (idempotent on cache-hit replays).
- `semi_synthetic` is true when the evaluated baseline's `stats.semi_synthetic` is true.
- Trend query filters and pagination work; RLS enforced.
- Snapshot failure never fails an evaluation.

**Test plan**
- Unit (`uv run pytest`): store upsert idempotency; filter combinations; error-swallowing; API pagination and envelope.

**Coding-agent prompt**
```
You are working in the CloudlyNet monorepo (repo root = cloudlynet_ai). Read story E2.S5 in
docs/task_docs/cloudlynet-rearchitecture/epics/EPIC-2-ndt-consolidation.md (DDL and API are
specified there) and the frozen HLD docs/task_docs/cloudlynet-rearchitecture/01-hld-frozen.md
section 3.

TASK: In submodule/maveric_platform_bdt_engine add evaluation KPI persistence.
1. Table ndt_kpi_snapshots (DDL per the epic doc) - add to app/schemas/bdt_schema.py ORM,
   artifacts/design/schemas.sql, artifacts/migration/014_ndt_loop.sql (append; the file
   exists from earlier stories).
2. app/services/ndt_kpi_store.py: record_snapshot(...) with
   INSERT ... ON CONFLICT (tenant_id, run_id, source) DO UPDATE; failures logged and
   swallowed so evaluations never fail on snapshot writes.
3. Call record_snapshot(source='evaluate') when an evaluation completes in
   app/services/ndt_evaluator.py (both tick sync and day async paths); set semi_synthetic
   from the baseline row's stats jsonb (baselines.stats ->> 'semi_synthetic').
4. GET /v1/tenants/{t}/ndt/kpis?bdt_id=&baseline_id=&source=&from_ts=&to_ts=&limit=&offset=
   in app/api/v1/endpoints/ndt.py returning {items, total}, created_at DESC, standard
   envelope, X-API-Key enforced.
CONSTRAINTS: Pydantic-first, type hints, platform logger, RLS tenant scoping like the other
bdt tables. No gateway changes.
DONE WHEN: cd submodule/maveric_platform_bdt_engine && uv run pytest passes including
tests/test_ndt_kpi_store.py.
```

---

## E2.S6 - Decision hub: loop policy CRUD, proposal intake, evaluation gate, action dispatch

**Why.** The closed loop needs a single brain: NDT receives recommendation proposals, scores them on the twin, gates them against tenant policy, and dispatches approved actions - with a full audit trail (marketing blocker #3 depends on this via E5).

**Size:** L

**Scope**
- In: `loop_policies` + `loop_actions` + `loop_proposals` + `loop_feedback` tables (the latter two persist raw payloads for lineage; `loop_feedback` is written by S7); `GET|PUT /v1/tenants/{t}/ndt/loop/policy`; `POST /v1/tenants/{t}/ndt/loop/proposals` (REST intake) and a `maveric.loop.proposal.v1` Kafka consumer running INSIDE the existing bdt-worker process (second topic on a consumer thread - no new deployable); evaluation gate (twin eval + policy thresholds); dispatch to `maveric.loop.action.v1`; `GET /v1/tenants/{t}/ndt/loop/actions/{id}`; loop topic lines ensured in `scripts/kafka/init-topics.sh` (only if E5.S1 has not landed; E5.S1 owns topic provisioning); add this epic's tables (`ndt_evaluation_runs`, `ndt_feature_builds`, `ndt_kpi_snapshots`, `loop_policies`, `loop_actions`, `loop_proposals`, `loop_feedback`) to the gateway's boot-time RLS re-application list (`submodule/maveric_platform_gateway/internal/db/migrate.go:323-334`) so dev stacks whose tables were created by bdt_engine startup `create_tables` (which applies no RLS) still get RLS enforced at gateway boot.
- Out: feedback/rollback (S7); approve/reject endpoints (S8); executors (smo_sim adapters = E4, RIC layer = E3); end-to-end wiring (E5); gateway exposure.

**Files**
- Create `submodule/maveric_platform_bdt_engine/app/services/loop/__init__.py`, `app/services/loop/decision_hub.py`, `app/services/loop/policy_store.py`, `app/services/loop/action_store.py`
- Create `submodule/maveric_platform_bdt_engine/app/workers/loop_consumer.py`
- Create `submodule/maveric_platform_bdt_engine/app/api/v1/endpoints/ndt_loop.py`
- Modify `submodule/maveric_platform_bdt_engine/app/workers/bdt_worker.py` (`__main__`: start `LoopConsumer` daemon thread alongside `BDTWorker().run_forever()`; guarded by env `NDT_LOOP_CONSUMER_ENABLED` default `true`)
- Modify `submodule/maveric_platform_bdt_engine/app/event_handlers/kafka_handler.py` (`KafkaConsumerManager.__init__` accepts `topic: str | Sequence[str]` - backward compatible)
- Modify `submodule/maveric_platform_bdt_engine/app/api/v1/routes.py`, `app/schemas/bdt_schema.py`, `app/models/ndt_models.py`
- Modify `scripts/kafka/init-topics.sh` (ensure the `maveric.loop.proposal.v1`, `maveric.loop.action.v1`, `maveric.loop.feedback.v1` topic lines exist - add ONLY if E5.S1, the owner-of-record for topic provisioning, has not landed; check for existing entries first)
- Modify `artifacts/design/schemas.sql` + `artifacts/migration/014_ndt_loop.sql`
- Create `submodule/maveric_platform_bdt_engine/tests/test_loop_policy_api.py`, `tests/test_decision_hub.py`, `tests/test_loop_consumer.py`

**Contract**

Policy (HLD §4.2 verbatim): `GET|PUT /v1/tenants/{t}/ndt/loop/policy`
```json
{"mode": "off", "guardrails": {"min_sinr_db": 0.0, "min_rrc_success_pct": 95.0, "max_outage_rate": 0.1}, "watch_window_min": 15}
```
GET returns the stored row or these defaults when none exists (`mode=off`). PUT upserts and returns the stored policy.

Proposal intake - topic `maveric.loop.proposal.v1` payload, FROZEN in HLD Appendix A.1 (also the REST body for `POST /v1/tenants/{t}/ndt/loop/proposals`, which returns 202 `{proposal_id, action_ids}`):
```json
{
  "event": "loop.proposal",
  "version": 1,
  "proposal_id": "uuid",
  "tenant_id": "uuid",
  "source": {"service": "rapp", "rapp_id": "es", "rapp_model_id": "m-1", "run_id": "..."},
  "refs": {
    "baseline_id": "b-1", "bdt_id": "bdt-1", "ue_dataset_id": "d-1",
    "scope": {"type": "day", "day": 0}
  },
  "per_tick_recommendations": [{"tick": 0, "items": [{"cell_id": "c1", "el_degree": 6.0, "on_off": true}]}],
  "kpi_summary": {"guardrail_kpis": {}, "objective_kpis": {}},
  "target_adapter_hint": "nanolink_tr069",
  "created_at": "2026-07-16T00:00:00Z"
}
```
(`per_tick_recommendations` items reuse rapp's Recommendation Table field names `el_degree`/`on_off` exactly, so rapp can forward its `per_tick_recommendations` unmodified; `tick` is an integer 0-23. E3.S5 is the producer of this exact shape; do not accept or invent any other proposal dialect. The raw payload is persisted into `loop_proposals` on intake (lineage, consumed by E5.S3).)

Gate semantics:
0. Persist the raw proposal payload into `loop_proposals` (`ON CONFLICT DO NOTHING` on `(tenant_id, proposal_id)`; lineage source for E5.S3).
1. Load tenant policy. `mode=off` -> record actions with status `suppressed` (audit only), stop.
2. Run NDT evaluation (S1 code path; `cell_configs` derived from `per_tick_recommendations`, mapping `el_degree` -> `cell_el_deg`; ids from `refs`) and `record_snapshot(source='loop_gate')`.
3. Twin-checkable guardrails: `guardrail_kpis.sinr_p5 >= min_sinr_db` and `guardrail_kpis.outage_rate <= max_outage_rate`. (`min_rrc_success_pct` is not twin-predictable; it is enforced at feedback watch, S7.) Fail -> all proposal actions status `rejected_by_gate` with reasons.
4. Pass + `mode=approval` -> status `pending_approval` (surfaced in S8). Pass + `mode=auto` -> dispatch.

Action rows: one `loop_actions` row per (tick, cell) recommendation item, deterministic `action_id = uuid5(NAMESPACE_URL, f"loop-action:{tenant_id}:{proposal_id}:{tick}:{cell_id}")`, inserted `ON CONFLICT DO NOTHING` (idempotent Kafka redelivery; if rows for `proposal_id` already exist, the message is skipped, mirroring bdt_worker's terminal-state skip).

Dispatch - topic `maveric.loop.action.v1` payload (HLD §4.1 exact envelope; field contents frozen in HLD Appendix A.2):
```json
{"action_id": "...", "tenant_id": "...", "adapter": "nanolink_tr069",
 "target": {"cell_id": "c1", "tick": 0},
 "payload": {"cell_el_deg": 6.0, "on_off": true, "rollback_of": null},
 "policy_ref": {"policy_id": "...", "mode": "auto", "watch_window_min": 15},
 "expires_at": "2026-07-16T01:00:00Z"}
```
`adapter` = `target_adapter_hint` or default `nanolink_tr069` (keys per HLD Appendix A.4); `policy_ref` is always a JSON object (the policy snapshot); `expires_at` = dispatch time + `NDT_ACTION_TTL_MIN` (default 60). Per the Appendix A.2 translation seam, the NDT dispatches the cell-scoped target and recommendation payload verbatim; the executor adapter (E4) resolves cell -> device and translates the recommendation to managed-parameter writes. Produced with the existing `KafkaProducerManager` (acks=all, retries).

DDL:
```sql
CREATE TABLE IF NOT EXISTS public.loop_policies (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        uuid NOT NULL UNIQUE,
  mode             text NOT NULL DEFAULT 'off' CHECK (mode IN ('off','approval','auto')),
  guardrails       jsonb NOT NULL DEFAULT '{}'::jsonb,
  watch_window_min int  NOT NULL DEFAULT 15,
  updated_by       uuid,
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.loop_actions (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       uuid NOT NULL,
  action_id       text NOT NULL,
  proposal_id     text,
  kind            text NOT NULL DEFAULT 'change' CHECK (kind IN ('change','rollback')),
  source          jsonb,                      -- proposal source block
  adapter         text NOT NULL,
  target          jsonb NOT NULL,             -- {"cell_id": ..., "tick": ...}
  payload         jsonb NOT NULL,
  policy_ref      jsonb,                      -- policy snapshot at decision time
  evaluation      jsonb,                      -- {"run_id":..., "verdict":"pass|fail", "reasons":[...]}
  status          text NOT NULL DEFAULT 'proposed',
  prev_action_id  text,                       -- rollback rows: the action being reverted
  expires_at      timestamptz,
  dispatched_at   timestamptz,
  applied_at      timestamptz,
  watch_deadline  timestamptz,
  error           text,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, action_id)
);
CREATE INDEX IF NOT EXISTS idx_loop_actions_tenant_status ON public.loop_actions (tenant_id, status, created_at DESC);

-- Lineage persistence (consumed by E5.S3's audit/lineage API and E5.S4's demo print):
CREATE TABLE IF NOT EXISTS public.loop_proposals (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL,
  proposal_id text NOT NULL,
  payload     jsonb NOT NULL,             -- raw maveric.loop.proposal.v1 message (HLD Appendix A.1)
  created_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, proposal_id)
);

CREATE TABLE IF NOT EXISTS public.loop_feedback (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL,
  action_id   text,                       -- null for unsolicited device events
  kind        text NOT NULL,              -- apply|kpi_window|guardrail_breach|rollback
  status      text,
  payload     jsonb NOT NULL,             -- raw maveric.loop.feedback.v1 message (HLD Appendix A.3)
  observed_at timestamptz,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_loop_feedback_tenant_action ON public.loop_feedback (tenant_id, action_id, created_at);
```
Status machine (S6 owns through `dispatched`; S7 adds the rest):
`proposed -> suppressed | rejected_by_gate | pending_approval | dispatched`;
`pending_approval -> approved -> dispatched | rejected` (S8);
`dispatched -> applied | failed` and `applied -> watching -> completed | rolled_back` (S7).

`GET /v1/tenants/{t}/ndt/loop/actions/{id}` -> the full row (envelope-wrapped), 404 `ACTION_NOT_FOUND`.

**Key snippets**
```python
# app/services/loop/decision_hub.py  (parses the FROZEN shape, HLD Appendix A.1)
class ProposalSource(BaseModel):
    service: str = "rapp"
    rapp_id: Optional[str] = None
    rapp_model_id: Optional[str] = None
    run_id: Optional[str] = None

class ProposalRefs(BaseModel):
    baseline_id: str
    bdt_id: str
    ue_dataset_id: str
    scope: EvaluationScope

class LoopProposal(BaseModel):
    event: Literal["loop.proposal"] = "loop.proposal"
    version: int = 1
    proposal_id: str
    tenant_id: str
    source: ProposalSource
    refs: ProposalRefs
    per_tick_recommendations: List[Dict[str, Any]]   # [{tick: int, items:[{cell_id, el_degree, on_off}]}]
    kpi_summary: Optional[Dict[str, Any]] = None
    target_adapter_hint: str = "nanolink_tr069"
    created_at: Optional[datetime] = None

def handle_proposal(db: Session, proposal: LoopProposal) -> List[str]:
    """Idempotent intake -> gate -> action rows -> dispatch/queue. Returns action_ids."""
    ...

def evaluate_gate(db: Session, proposal: LoopProposal, policy: LoopPolicy) -> GateVerdict:
    """Run NDT evaluation on the proposed cell_configs and compare guardrail_kpis against
    policy.guardrails (sinr_p5 >= min_sinr_db, outage_rate <= max_outage_rate)."""
    ...
```
```python
# app/workers/loop_consumer.py
class LoopConsumer:
    """Kafka consumer thread inside the bdt-worker process. Subscribes to
    maveric.loop.proposal.v1 (and maveric.loop.feedback.v1 from E2.S7); group_id 'ndt_loop';
    manual commit, at-least-once + idempotent handlers (ON CONFLICT DO NOTHING intake)."""
    TOPICS = ["maveric.loop.proposal.v1"]
    def run_forever(self) -> None: ...

# app/workers/bdt_worker.py __main__
if __name__ == "__main__":
    if os.getenv("NDT_LOOP_CONSUMER_ENABLED", "true").lower() == "true":
        threading.Thread(target=LoopConsumer().run_forever, name="ndt-loop-consumer", daemon=True).start()
    BDTWorker().run_forever()
```

**Acceptance criteria**
- Policy GET returns defaults (`mode=off`) with no row; PUT validates mode/guardrail keys and upserts; RLS scoping.
- Intake persists the raw proposal payload into `loop_proposals` exactly once per `(tenant_id, proposal_id)`; a proposal that fails Appendix A.1 validation is logged, committed, and skipped.
- A proposal in `mode=off` produces `suppressed` rows and no Kafka action; `mode=auto` + gate pass produces `dispatched` rows and exactly one `maveric.loop.action.v1` message per action with the §4.1 envelope (contents per HLD Appendix A.2, `policy_ref` always an object); gate fail produces `rejected_by_gate` with reasons in `evaluation`; `mode=approval` + pass produces `pending_approval` and no dispatch.
- Kafka redelivery of the same proposal produces no duplicate rows or messages.
- REST intake and topic intake execute the identical `handle_proposal` code path.
- bdt-worker training consumption (`maveric.bdt.train.v1`) is unaffected (separate thread, separate group id `ndt_loop`).
- Topics exist after `scripts/kafka/init-topics.sh` runs (compose infra); the k8s topics-job values addition is recorded as a values-only note, not made here.

**Test plan**
- Unit (`uv run pytest`): `test_loop_policy_api.py` (defaults, upsert, validation 422); `test_decision_hub.py` (all four mode/gate branches, idempotent replay, action_id determinism, dispatch payload shape vs §4.1); `test_loop_consumer.py` (message decode -> handle_proposal called with tenant context; malformed message committed and skipped, matching bdt_worker's decode-failure behavior).
- Integration (lab): compose up, publish a proposal onto the topic, observe `loop_actions` rows and the action message with `kafka-console-consumer`.

**Coding-agent prompt**
```
You are working in the CloudlyNet monorepo (repo root = cloudlynet_ai). Read
docs/task_docs/cloudlynet-rearchitecture/01-hld-frozen.md sections 3, 4.1, 4.2 AND Appendix A
(A.1 proposal payload, A.2 action field contents, A.4 adapter keys are FROZEN), then story
E2.S6 in docs/task_docs/cloudlynet-rearchitecture/epics/EPIC-2-ndt-consolidation.md (DDL,
gate semantics, status machine are specified there - follow them exactly; never rename the
§4.1 topic names or action envelope fields).

TASK: Implement the closed-loop decision hub in submodule/maveric_platform_bdt_engine.
1. Tables loop_policies + loop_actions + loop_proposals + loop_feedback (ORM in
   app/schemas/bdt_schema.py; DDL appended to artifacts/design/schemas.sql and
   artifacts/migration/014_ndt_loop.sql, including the updated_at trigger list).
2. app/api/v1/endpoints/ndt_loop.py: GET|PUT /v1/tenants/{t}/ndt/loop/policy (defaults
   mode=off, guardrails {min_sinr_db, min_rrc_success_pct, max_outage_rate},
   watch_window_min 15), POST /v1/tenants/{t}/ndt/loop/proposals (202, {proposal_id,
   action_ids}; body = the Appendix A.1 shape), GET /v1/tenants/{t}/ndt/loop/actions/{id}
   (404 ACTION_NOT_FOUND). Register in app/api/v1/routes.py with X-API-Key.
3. app/services/loop/: policy_store.py, action_store.py, decision_hub.py
   (handle_proposal: parse the Appendix A.1 payload with the LoopProposal/ProposalSource/
   ProposalRefs models from the epic doc; persist the raw payload into loop_proposals with
   ON CONFLICT DO NOTHING; idempotent intake with deterministic action_id
   uuid5("loop-action:{tenant}:{proposal_id}:{tick}:{cell_id}") and ON CONFLICT DO NOTHING;
   gate = run the existing NDT evaluation (app/services/ndt_evaluator.py) on cell_configs
   derived from per_tick_recommendations (el_degree -> cell_el_deg; ids from refs) +
   record_snapshot(source='loop_gate') via app/services/ndt_kpi_store.py; checks
   sinr_p5 >= min_sinr_db and outage_rate <= max_outage_rate; mode routing off->suppressed,
   approval->pending_approval, auto->dispatch on maveric.loop.action.v1 via the existing
   KafkaProducerManager with the exact envelope {action_id, tenant_id, adapter, target,
   payload, policy_ref, expires_at}; adapter = target_adapter_hint (Appendix A.4 key,
   default nanolink_tr069); policy_ref is a JSON object, never a string; target and payload
   stay cell-scoped per Appendix A.2 - the executor adapter owns device resolution).
4. app/workers/loop_consumer.py: LoopConsumer consuming maveric.loop.proposal.v1, group_id
   "ndt_loop", manual commit, per-message tenant RLS context, malformed messages committed
   and skipped. Extend app/event_handlers/kafka_handler.py KafkaConsumerManager to accept a
   list of topics (backward compatible with a single string). Start the consumer as a
   daemon thread from app/workers/bdt_worker.py __main__, gated by
   NDT_LOOP_CONSUMER_ENABLED (default true). The existing BDTWorker training loop must be
   completely unaffected.
5. scripts/kafka/init-topics.sh (repo root): E5.S1 is the owner-of-record for topic
   provisioning. Check the script first; ONLY IF the maveric.loop.proposal.v1 /
   maveric.loop.action.v1 / maveric.loop.feedback.v1 ensure_topic lines are not already
   present (E5.S1 not landed), add them; never duplicate an existing entry.

CONSTRAINTS: no new deployable/container/port (the consumer lives inside bdt-worker);
Pydantic-first; type hints; platform logger; at-least-once consumption with idempotent
handlers; do not implement feedback handling or approve/reject endpoints (later stories).

DONE WHEN: cd submodule/maveric_platform_bdt_engine && uv run pytest passes including
tests/test_loop_policy_api.py, tests/test_decision_hub.py, tests/test_loop_consumer.py.
```

---

## E2.S7 - Feedback watch + watch-window rollback ordering

**Why.** A loop that cannot verify and revert is a liability: the NDT must watch executor feedback for the policy's watch window and emit rollback actions (referencing the prior action) when guardrails breach - network-level defense above smo_sim's device-level watcher.

**Size:** M

**Scope**
- In: `maveric.loop.feedback.v1` consumption in the same LoopConsumer thread (payload per HLD Appendix A.3); persistence of every consumed feedback message into `loop_feedback` (lineage); apply/failure transitions; KPI-window guardrail checks (including `min_rrc_success_pct`); canonical-PM watch for A1-path actions (`adapter="a1_policy"` gets no executor-emitted KPI windows per E3.S4 - the watch tick queries the data platform `/data/pm` instead); watch-deadline sweep; rollback action emission (`kind='rollback'`, `prev_action_id`, LIFO ordering per target); status machine completion.
- Out: producing feedback (executors: smo_sim E4 / rapp E3); device-level rollback mechanics (smo_sim keeps its own).

**Files**
- Create `submodule/maveric_platform_bdt_engine/app/services/loop/feedback_watcher.py`
- Modify `submodule/maveric_platform_bdt_engine/app/workers/loop_consumer.py` (add topic; route by `message.topic`; run the watch tick - deadline sweep + canonical-PM watch - each poll iteration, throttled to once per `LOOP_WATCH_TICK_SECONDS`)
- Modify `submodule/maveric_platform_bdt_engine/app/services/loop/action_store.py`, `app/models/ndt_models.py`
- Modify `docker-compose.yaml` (bdt-worker service env: `DATA_PLATFORM_BASE_URL`, `DATA_PLATFORM_API_KEY` - same values S4 gives the bdt_engine service - plus `LOOP_WATCH_TICK_SECONDS`)
- Create `submodule/maveric_platform_bdt_engine/tests/test_feedback_watcher.py`

**Contract**

Feedback payload - topic `maveric.loop.feedback.v1` (executors publish; §4.1 names it, shape FROZEN in HLD Appendix A.3 - E4.S3 produces this exact shape):
```json
{"schema": "maveric.loop.feedback.v1", "feedback_id": "<uuid4>",
 "action_id": "...", "tenant_id": "...", "adapter": "nanolink_tr069",
 "kind": "apply", "status": "applied", "command_id": "...",
 "kpis": {"sinr_avg_db": 12.1, "rrc_success_pct": 97.2, "outage_rate": 0.01},
 "detail": {"readback": {}, "mismatch": {}, "error": "", "rollback_command_id": ""},
 "observed_at": "2026-07-16T00:05:00Z"}
```
- Every consumed message is persisted verbatim into `loop_feedback` (S6 table; lineage source for E5.S3) before transition handling.
- `kind="apply"`: `status` in `queued|applied|failed|rejected|duplicate|expired`. `applied` -> action `applied`, `applied_at=observed_at`, then `watching` with `watch_deadline = applied_at + policy_ref.watch_window_min`. `failed` -> action `failed` with `detail.error` in `error`. `queued|rejected|duplicate|expired` are audit-only (persisted, logged, no transition).
- `kind="kpi_window"`: `status` in `ok|breach`, `kpis` carries observed values. Breach evaluation (NDT-side, independent of the executor's verdict): `kpis.sinr_avg_db < min_sinr_db` OR `kpis.rrc_success_pct < min_rrc_success_pct` OR `kpis.outage_rate > max_outage_rate` (missing keys are skipped). Only actions in `watching` are affected.
- `kind="guardrail_breach"`: the executor's device-level watcher fired; treated as a breach signal for the referenced action if it is `watching` (check-and-skip when a rollback already happened).
- `kind="rollback"`: ack of a rollback command (`status` in `rolled_back|failed`); audit-only for the rollback row (rollback rows are never watched).
- Unknown `action_id` or terminal-state action: log warning, persist, commit, skip (idempotent).

Rollback ordering:
- On breach for a `watching` action A: gather ALL `watching` actions on the same `target.cell_id` (or identical `target` object) for the tenant, order by `applied_at` DESC (LIFO), and for each emit a rollback action: new `loop_actions` row `kind='rollback'`, `action_id = uuid5("loop-rollback:{tenant}:{prev_action_id}")`, `prev_action_id` = the reverted action's `action_id`, `payload = {"rollback_of": prev_action_id}` (the executor restores from its own `prev_values`, as the NanoLink plane already does), same `adapter`/`target`, status `dispatched`, published on `maveric.loop.action.v1` with the §4.1 envelope. Reverted actions -> status `rolled_back`. Rollback actions are never themselves watched (no `watch_deadline`).

Watch tick (deadline sweep + canonical-PM watch):
- The consumer poll loop runs the watch tick when at least `LOOP_WATCH_TICK_SECONDS` (new setting, default `60`) have elapsed since the last tick.
- Deadline sweep (every tick): `watching` rows with `watch_deadline < now()` -> `completed`. `dispatched` rows with `expires_at < now()` and no apply feedback -> `expired`.
- Canonical-PM watch (A1 path, every tick): `adapter="a1_policy"` actions get NO executor-emitted `kpi_window`/`guardrail_breach` feedback (E3.S4 emits only `apply`/`rollback`); their in-window guardrail check is NDT-side over canonical PM. For every `watching` action with `adapter="a1_policy"`: query `GET {DATA_PLATFORM_BASE_URL}/v1/tenants/{t}/data/pm` (reuse S4's data-platform client + `DATA_PLATFORM_BASE_URL`/`DATA_PLATFORM_API_KEY` settings) filtered by the action's `target.cell_id` (dn match) and `from_ts = applied_at`, aggregate the returned rows to `{sinr_avg_db, rrc_success_pct, outage_rate}` window means, and run the same `check_breach` against the tenant guardrails (same rule as the A.3 `kpi_window` evaluation; the watch window itself comes from the action's `policy_ref` snapshot); a breach feeds the same LIFO `emit_rollbacks` path. Missing metrics are skipped (same rule as the A.3 `kpi_window` check); an empty window is not a breach; data-platform errors are logged and retried next tick (the deadline sweep still completes healthy windows).

**Key snippets**
```python
# app/services/loop/feedback_watcher.py  (parses the FROZEN shape, HLD Appendix A.3)
class LoopFeedback(BaseModel):
    schema_: Literal["maveric.loop.feedback.v1"] = Field(default="maveric.loop.feedback.v1", alias="schema")
    feedback_id: Optional[str] = None
    action_id: Optional[str] = None          # null for unsolicited device events
    tenant_id: str
    adapter: Optional[str] = None
    kind: Literal["apply", "kpi_window", "guardrail_breach", "rollback"]
    status: str
    command_id: Optional[str] = None
    kpis: Optional[Dict[str, float]] = None
    detail: Optional[Dict[str, Any]] = None
    observed_at: datetime

def handle_feedback(db: Session, fb: LoopFeedback) -> None: ...
def check_breach(kpis: Mapping[str, float], guardrails: Mapping[str, float]) -> list[str]:
    """Returns breach reasons; empty list = healthy. Missing KPI keys are not breaches."""
def sweep_deadlines(db: Session) -> int:
    """watching past watch_deadline -> completed; dispatched past expires_at -> expired."""
def watch_canonical_pm(db: Session) -> int:
    """A1-path watch tick: /data/pm window aggregate per watching a1_policy action -> check_breach."""
def emit_rollbacks(db: Session, *, tenant_id: str, breached: LoopActionRow) -> list[str]:
    """LIFO rollback rows + action.v1 messages for all watching actions on the target."""
```

**Acceptance criteria**
- Every consumed feedback message (all four kinds) lands as one `loop_feedback` row with the raw payload; duplicates are tolerated (audit rows are append-only, transitions stay idempotent).
- Apply-success feedback (`kind="apply"`, `status="applied"`) moves `dispatched -> applied -> watching` with the correct deadline from the action's `policy_ref` snapshot (not the current policy); audit-only apply statuses (`queued|rejected|duplicate|expired`) cause no transition.
- A breach on any of the three guardrails emits rollback action(s) in LIFO order, marks originals `rolled_back`, and publishes correct §4.1 envelopes with `payload.rollback_of` set.
- Healthy window (`ok` feedbacks, deadline passes) -> `completed`; never rolls back after the deadline.
- A `watching` `a1_policy` action whose canonical-PM window aggregate breaches a guardrail triggers the same LIFO rollback path (data-platform client mocked); healthy or empty PM windows never roll back; the watch tick runs at most once per `LOOP_WATCH_TICK_SECONDS`.
- Duplicate/out-of-order feedback is idempotent (terminal states never regress).
- Sweep expires undelivered `dispatched` actions past `expires_at`.

**Test plan**
- Unit (`uv run pytest`): `test_feedback_watcher.py` - transition table coverage (apply ok/fail, kpi ok/breach per guardrail, unknown action, duplicate feedback, LIFO multi-action rollback, canonical-PM watch breach/healthy/empty window for `a1_policy` actions with the data-platform client mocked, deadline sweep, expiry sweep); Kafka producer mocked, payload asserted against §4.1.
- Integration (lab): publish proposal -> auto dispatch -> synthetic apply + breach feedback via console producer -> observe rollback message and row states.

**Coding-agent prompt**
```
You are working in the CloudlyNet monorepo (repo root = cloudlynet_ai). Read
docs/task_docs/cloudlynet-rearchitecture/01-hld-frozen.md sections 3, 4.1, 4.2 AND Appendix
A.3 (the feedback payload is FROZEN there; E4.S3 produces it), then story E2.S7 in
docs/task_docs/cloudlynet-rearchitecture/epics/EPIC-2-ndt-consolidation.md - the breach
rules, LIFO rollback ordering, and status machine are specified there; follow them exactly.

PRECONDITION: story E2.S6 is merged (loop_actions + loop_proposals + loop_feedback tables,
LoopConsumer thread in bdt-worker, decision hub, action dispatch). Verify
app/workers/loop_consumer.py exists; if not, STOP.

TASK: In submodule/maveric_platform_bdt_engine implement feedback watching and rollback.
1. app/services/loop/feedback_watcher.py: LoopFeedback Pydantic model parsing the Appendix
   A.3 shape ({schema, feedback_id, action_id, tenant_id, adapter, kind in apply|kpi_window|
   guardrail_breach|rollback, status, command_id, kpis, detail, observed_at}),
   handle_feedback (FIRST persist the raw message into loop_feedback, THEN transition:
   kind=apply status=applied/failed transitions the action; queued/rejected/duplicate/
   expired are audit-only; kind=kpi_window and kind=guardrail_breach feed check_breach;
   kind=rollback is audit-only), check_breach (kpis.sinr_avg_db < min_sinr_db OR
   kpis.rrc_success_pct < min_rrc_success_pct OR kpis.outage_rate > max_outage_rate;
   missing keys skipped), sweep_deadlines, watch_canonical_pm, emit_rollbacks
   (rollback rows kind='rollback', action_id uuid5("loop-rollback:{tenant}:{prev_action_id}"),
   prev_action_id set, payload {"rollback_of": prev_action_id}, published on
   maveric.loop.action.v1 with the exact HLD 4.1 envelope (policy_ref object, Appendix A.2);
   LIFO by applied_at over all watching actions sharing the target; reverted rows ->
   rolled_back; rollback rows are never watched).
2. watch_canonical_pm (A1 path): a1_policy actions get no executor-emitted kpi_window or
   guardrail_breach feedback (E3.S4 emits only apply/rollback), so for every watching
   action with adapter="a1_policy" query GET {DATA_PLATFORM_BASE_URL}/v1/tenants/{t}/data/pm
   (reuse S4's data-platform client and DATA_PLATFORM_BASE_URL/DATA_PLATFORM_API_KEY
   settings) filtered by target.cell_id and from_ts=applied_at, aggregate to
   {sinr_avg_db, rrc_success_pct, outage_rate} window means, and run the same check_breach
   against the tenant guardrails (watch window from the policy_ref snapshot as
   elsewhere); breach -> emit_rollbacks. Missing
   metrics skipped; empty window is not a breach; data-platform errors logged and retried
   next tick.
3. app/workers/loop_consumer.py: subscribe to maveric.loop.feedback.v1 in addition to the
   proposal topic, route handlers by message.topic, and run the watch tick (sweep_deadlines
   + watch_canonical_pm) in the poll loop at most once per LOOP_WATCH_TICK_SECONDS (new
   setting, default 60). Use the watch window from the action's stored policy_ref snapshot,
   not the live policy. Add DATA_PLATFORM_BASE_URL/DATA_PLATFORM_API_KEY and
   LOOP_WATCH_TICK_SECONDS to the bdt-worker service env in docker-compose.yaml.
4. Idempotency: unknown action_id or terminal-state rows are persisted, logged, and
   committed; states never regress.

DONE WHEN: cd submodule/maveric_platform_bdt_engine && uv run pytest passes including
tests/test_feedback_watcher.py covering the full transition table (apply ok/fail, breach
per guardrail, canonical-PM watch breach/healthy/empty for a1_policy actions with the
data-platform client mocked, LIFO multi-action rollback, deadline completion, expiry,
duplicates).
```

---

## E2.S8 - Approval mode: list actions + approve/reject endpoints

**Why.** `mode=approval` is the trust-building default for real customers: gate-passed actions must be visible and require an explicit operator decision, with the same `:approve`/`:reject` semantics operators already know from smo_sim's recommendation flow.

**Size:** S

**Scope**
- In: `GET /v1/tenants/{t}/ndt/loop/actions` (list + filters), `POST /v1/tenants/{t}/ndt/loop/actions/{id}:approve`, `POST /v1/tenants/{t}/ndt/loop/actions/{id}:reject` mirroring `smo_sim/app/api/v1/custom/nybsys_edge_router.py:190-211` semantics (404 not-found, 409 wrong-state).
- Out: gateway/frontend exposure (later optional `/ndt/**` story); notification/webhooks.

**Files**
- Modify `submodule/maveric_platform_bdt_engine/app/api/v1/endpoints/ndt_loop.py`, `app/services/loop/action_store.py`, `app/services/loop/decision_hub.py` (reuse the dispatch helper for approved actions)
- Create `submodule/maveric_platform_bdt_engine/tests/test_loop_approval_api.py`

**Contract**
```
GET  /v1/tenants/{t}/ndt/loop/actions?status=pending_approval&proposal_id=&kind=&limit=100&offset=0
     -> {items: [loop_action rows], total: n} ordered created_at DESC
POST /v1/tenants/{t}/ndt/loop/actions/{action_id}:approve
     -> 200 {"action_id": "...", "status": "dispatched"}
     -> 404 {"detail": "ACTION_NOT_FOUND"} | 409 {"detail": "ACTION_NOT_PENDING"}
POST /v1/tenants/{t}/ndt/loop/actions/{action_id}:reject
     -> 200 {"action_id": "...", "status": "rejected"}
     -> 404 ACTION_NOT_FOUND | 409 ACTION_NOT_PENDING
```
Approve: only `pending_approval` rows; transition `pending_approval -> approved -> dispatched` in one call (publish the §4.1 action message; `expires_at` computed at approval time). Reject: only `pending_approval` rows -> `rejected`. Both record `updated_by` when the gateway forwards a user id header (optional, nullable).

**Key snippets**
```python
@router.post("/tenants/{tenant_id}/ndt/loop/actions/{action_id}:approve")
def approve_action(tenant_id: str, action_id: str, db: Session = Depends(get_db)) -> dict:
    """Mirror of smo_sim recommendation approve: 404 unknown, 409 not pending, else
    approve + dispatch on maveric.loop.action.v1 and return the new status."""
```

**Acceptance criteria**
- Approve on a `pending_approval` action publishes exactly one action message and returns `dispatched`; reject publishes nothing.
- 404/409 semantics match the smo_sim recommendation endpoints (wrong-state 409, unknown 404); double-approve returns 409.
- List filters by status/proposal_id/kind with pagination; RLS enforced.

**Test plan**
- Unit (`uv run pytest`): `test_loop_approval_api.py` - list filters, approve happy path (producer mocked, envelope asserted), reject, 404, 409 on wrong state and on repeat calls.

**Coding-agent prompt**
```
You are working in the CloudlyNet monorepo (repo root = cloudlynet_ai). Read story E2.S8 in
docs/task_docs/cloudlynet-rearchitecture/epics/EPIC-2-ndt-consolidation.md and the frozen
HLD docs/task_docs/cloudlynet-rearchitecture/01-hld-frozen.md section 4.2.

PRECONDITION: stories E2.S6/S7 are merged (loop_actions, decision hub dispatch helper).

TASK: In submodule/maveric_platform_bdt_engine/app/api/v1/endpoints/ndt_loop.py add:
1. GET /v1/tenants/{t}/ndt/loop/actions with filters status, proposal_id, kind, limit,
   offset -> {items, total}, created_at DESC.
2. POST /v1/tenants/{t}/ndt/loop/actions/{action_id}:approve and :reject, mirroring the
   semantics of submodule/maveric_platform_smo_sim/app/api/v1/custom/nybsys_edge_router.py
   lines 190-211 (404 ACTION_NOT_FOUND when the row does not exist; 409 ACTION_NOT_PENDING
   when status != pending_approval). Approve transitions pending_approval -> approved ->
   dispatched in one call and publishes the HLD 4.1 action envelope on
   maveric.loop.action.v1 via the decision hub's existing dispatch helper (expires_at
   computed at approval time). Reject transitions to rejected and publishes nothing.
CONSTRAINTS: X-API-Key router dependency, standard envelope, RLS tenant scoping,
Pydantic-first, platform logger. No gateway changes.
DONE WHEN: cd submodule/maveric_platform_bdt_engine && uv run pytest passes including
tests/test_loop_approval_api.py.
```

---

## E2.S9 - Feature-builder cutover: flip `NDT_FEATURE_BUILDER_MODE=ndt_api`, soak, delete data_sim's `legacy_builder`

**Why.** E1.S4 ships a transitional inline copy of stages 3-6 (`data_sim app/ingest/legacy_builder/`) so uploads keep producing baselines/datasets until the NDT builder exists. Once S4 is live and proven, two copies of the synthesis pipeline is exactly the duplication this program kills; E1's rollout note 7 defers the flip and deletion to this story.

**Size:** S

**Scope**
- In: flip `NDT_FEATURE_BUILDER_MODE` default from `legacy_inline` to `ndt_api` in data_sim; lab + staging soak against the E1.S4 seam; after soak, delete `submodule/maveric_platform_data_sim/app/ingest/legacy_builder/` and the `legacy_inline` branch of `builder_hook.py`; keep `off` mode (lab/testing).
- Out: any smo_sim deletion (E4.S6 owns all smo_sim decommission); any seam-contract change (frozen by E1.S4); gateway or frontend changes.

**Files**
- Modify `submodule/maveric_platform_data_sim/app/core/config.py` (`NDT_FEATURE_BUILDER_MODE` default `ndt_api`)
- Modify `submodule/maveric_platform_data_sim/app/ingest/builder_hook.py` (drop the `legacy_inline` branch after soak; `get_builder()` resolves `ndt_api | off`)
- Delete `submodule/maveric_platform_data_sim/app/ingest/legacy_builder/` (whole package, plus its tests)
- Modify `docker-compose.yaml` (data_sim env: `NDT_FEATURE_BUILDER_MODE: ${NDT_FEATURE_BUILDER_MODE:-ndt_api}`)
- Modify `submodule/maveric_platform_data_sim/README.md` (builder-mode section)

**Contract.** No external contract change: `POST /custom/nybsys/uploads` responses stay byte-identical; derived artifacts are now produced by bdt_engine through the E1.S4 seam (`POST /ndt/feature-builds`) with identical schemas/S3 keys (S4 determinism fixtures are the gate).

**Acceptance criteria**
- Gate (verify before deleting anything): S4 merged; E1.S4's stub-server parity fixtures pass against the real NDT endpoint; one lab upload in `ndt_api` mode produces baselines/datasets hash-identical to the `legacy_inline` fixtures for the same `rng_seed`.
- After deletion: `grep -rn "legacy_builder\|legacy_inline" submodule/maveric_platform_data_sim/app` returns nothing except the `off` mode docstring; data_sim suite green; a full upload -> completed -> BDT train run passes in lab.
- Rollback path before deletion: set `NDT_FEATURE_BUILDER_MODE=legacy_inline` env (works until the deletion commit; after it, rollback = revert the deletion commit).

**Test plan**
- data_sim: `uv run pytest` (builder-hook resolution tests updated: `legacy_inline` now rejected as an unknown mode).
- Integration (lab): upload -> `ndt_api` build -> BDT + rApp train end-to-end; hash-compare derived CSVs against the E1.S4 determinism fixtures.

**Coding-agent prompt**
```
You are working in the CloudlyNet monorepo (repo root = cloudlynet_ai). Read
docs/task_docs/cloudlynet-rearchitecture/01-hld-frozen.md section 4.6, EPIC-1 story E1.S4
(the seam and the legacy_inline shim you are retiring), and story E2.S9 in
docs/task_docs/cloudlynet-rearchitecture/epics/EPIC-2-ndt-consolidation.md.

PRECONDITION (verify, else STOP and report): E2.S4's feature builder serves
POST /v1/tenants/{t}/ndt/feature-builds per the E1.S4 seam, and E1.S4's stub-server parity
fixtures pass against it; a lab upload in ndt_api mode produces hash-identical derived CSVs
vs the legacy_inline fixtures under the same rng_seed.

TASK: In submodule/maveric_platform_data_sim: 1) flip NDT_FEATURE_BUILDER_MODE default to
"ndt_api" (app/core/config.py + repo-root docker-compose.yaml data_sim env); 2) after the
user confirms the soak, delete app/ingest/legacy_builder/ entirely, remove the legacy_inline
branch from app/ingest/builder_hook.py (modes left: ndt_api | off), and delete the
legacy-builder tests; 3) update the data_sim README builder-mode section.
CONSTRAINTS: public upload contract byte-compatible (guarded by E1.S4 parity tests, which
must stay green); do NOT touch smo_sim (E4.S6 owns its decommission); no CI/CD change.
DONE WHEN: `uv run pytest` passes in data_sim, grep finds no legacy_builder/legacy_inline
references, and a lab upload completes end-to-end through the NDT builder.
```

---

## Execution status

**S1 — DONE** (bdt_engine `b1aabda`, parent `b3b2d16`). 78 new tests. bdt_engine suite 109 passed /
11 failed, the 11 being the recorded pre-existing baseline, verified byte-identical by re-running with
the changes stashed. `014_ndt_loop.sql` verified on a fresh database: applies twice cleanly, RLS
enabled AND forced.

Two defects in existing code were found and fixed because this story was the first to exercise them:
`data_loader.load_ue_dataset` always pinned to the first day with no way to request another (so
day-scope evaluation of any day but the first silently discarded every other day's rows), and
`main.py`'s `RequestValidationError` handler could not serialise a `@model_validator` failure,
turning every malformed scope into a 500 with a stack trace instead of a 422.

**S2 — DONE** (rapp `03c7196` + `7f0d70b`, parent `0a1c8bd`). 72 new tests. rapp suite 258 passed /
0 failed / 4 skipped / 5 errors, against a recorded baseline of 186 / 8 / 5. The 8 baseline failures
were `tests/test_rapps_openapi.py` pointing at the pre-move `design/openapi.yaml` and failing on
`FileNotFoundError` rather than comparing anything; repointed at `artifacts/design/`, and 25 checks
now genuinely verify the endpoints. The 5 errors are a pre-existing missing MRO fixture CSV.

### S4 IS DONE (2026-07-30), verified PM-to-baseline end to end.

`POST /ndt/feature-builds` -> **completed**: 9 cells, 3 sites, 4838 UE records, 360 training records
from 432 canonical PM rows, four CSVs at the existing S3 keys, and `baselines` + `ue_datasets` rows
written with `semi_synthetic=true`. bdt_engine `c8f0394` + `fce44e5`, parent `7666f71`.

Stages 3-6 are **byte-identical to data_sim's implementation** - all four output frames hash the same
in both containers on a fixed seeded grid. That is the acceptance criterion, and pinning the hashes
rather than merely re-running caught two things a "does it run" test would have passed:

- **`shapely` was absent from bdt_engine.** `pipeline.py` guards UE placement on
  `Voronoi is not None and Polygon is not None`, so it silently fell back to bbox scatter and produced
  7202 UE rows instead of 7200. `scipy==1.16.2` and `shapely==2.1.1` are now pinned to data_sim's
  exact versions.
- **A careless edit of mine** while removing `AggregateResult` changed the training hash; the pinned
  test caught it and the trim was redone from pristine source.

Also measured: the `training` frame's hash is **platform-sensitive** (macOS-arm64 vs Linux libm in the
path-loss evaluation). The test asserts shape everywhere, hashes exactly on Linux (what ships), and
skips `training` elsewhere with that explanation rather than reporting a lift defect it is not.

Three things the story's file list did not mention, each found by running it:

1. **`n_target` is derived between stages 3 and 4** by `apply_stochastic_guardrail`, inside the
   `run_pipeline` that S4 drops. Omitting it fails with a bare `KeyError: 'n_target'`. `runner.py`
   does it in the same position, and the guardrail's independent RNG is why that placement is safe.
2. **bdt_engine had no S3 writer** - `data_loader` only reads - so `artifacts.py` adds one at the
   EXISTING key conventions, which is what keeps a baseline built here consumable at cutover.
3. **`baselines` had no unique constraint on `(tenant_id, baseline_id)`** in the live database,
   although `schemas.sql` declares one. The registry write is an `ON CONFLICT` on exactly that key and
   fails outright without it. Added guarded to 014.

The **409 on `POST /ndt/feature-builds` is load-bearing**: data_sim's `NdtApiBuilder` ADOPTS a 409 and
polls, which is what makes a redelivered ingest job safe. A `failed` build is retried in place, or the
UNIQUE constraint would burn that `build_id` permanently.

**data_sim gained a mock NanoLink PM export** (`POST /utils/pm/generate`, commit `4cae111`), because
the chain now starts from PM counters and the existing generators start from a topology - which is now
an output. It goes through the REAL adapter rather than writing canonical rows, so the dn convention,
day/tick derivation and metric naming are all exercised. `scripts/seed_lab_tenant.sh` calls it, so the
whole chain seeds in one command; it also enables the `nybsys` feature flag, which the adapter requires
and no migration seeds.

**Remaining for S4:** nothing functional. `NDT_FEATURE_BUILDER_MODE=ndt_api` is E2.S9's flip.

### S3 IS UNBLOCKED (2026-07-30). The gate passes STRICT, bit-identical.

`scripts/ndt_parity_diff.sh` reports **STRICT PARITY OK (bit-identical)** for both day and tick scope,
with caches verified empty, NDT exercise proven (ndt mode writes `ndt_evaluation_runs` rows, local mode
writes none), and rapp on its **pinned** dependencies (torch 2.0.0 / gpytorch 1.9.1 — restored and
re-verified after an experimental upgrade, so the result is not an artefact of the lab). **No tolerance
relaxation was needed**; S3's gate is satisfied on the epic's original terms.

Getting there required fixing three causes, in order of size. Each was silent, and two of them were
rApp being wrong rather than merely different:

1. **CSV float precision.** pandas' default C parser drops the last significant digit of a float64,
   and which digit it drops changed between 1.x and 2.x. rapp runs pandas 1.5.3, bdt_engine 2.2.2, so a
   UE latitude of `37.739509875764824` parsed differently in each. Latitude feeds `log_distance`, a GP
   input. Fixed by pinning `float_precision="round_trip"` in both loaders.
2. **Reversed inference bearing in rApp's vendored twin.** `GISTools.get_relative_bearing` measured
   cell → UE while `preprocess_ue_training_data` in the same file measures UE → cell, so the
   `relative_bearing` GP feature was ~180° out of phase with how the twin was TRAINED. bdt_engine's copy
   already carried the correction; rapp's two vendored copies never received it. **This is precisely the
   drift the epic exists to eliminate.** MRO's third copy was deliberately left alone — MRO is
   self-consistent under its own convention and is out of epic scope; changing it broke
   `app/radplib/tests/mro/test_utils.py`, which is how the boundary was confirmed rather than assumed.
3. **oneDNN kernel selection.** With inputs then byte-identical (verified by hashing the GP input
   matrix), the two stacks still predicted ~0.003 dB apart, because torch dispatches float32 matmuls
   through oneDNN and its kernel choice changed between torch 2.0 and 2.3. That 0.003 dB flips
   `perform_attachment`'s argmax for UEs almost exactly on a cell boundary — 11 of 848 — which moved
   percentile KPIs up to 0.36 dB and Jain's index by 0.10 on affected ticks. Isolated by measurement:
   `set_float32_matmul_precision("highest")` changed nothing; `backends.mkldnn.enabled = False` made
   torch 2.3.1 reproduce 2.0.0 exactly. Disabled process-wide in bdt_engine, and it is ~20% **faster**
   on this workload, so there was no trade-off to weigh.

Worth keeping in mind beyond this epic: (3) means twin predictions were previously a function of which
torch build happened to be installed. These predictions gate automated network changes and are
persisted as audit KPIs in `ndt_kpi_snapshots`, so determinism there is a correctness property, not a
tidiness one.

Risk 9 (the cell-config enrichment asymmetry) remains real and is still handled by
`NDT_RF_ENRICHMENT=rapp_compat`, which reproduces rApp's flattening of every cell to boresight 0° and a
single 2100 MHz carrier. That flattening is a genuine rApp modelling defect, not something to preserve:
**flip the default to `baseline` once S3 lands**, since byte-compat then constrains nothing.

### What the gate found on its first run (2026-07-30), before the fixes above

A lab tenant was seeded (`scripts/seed_lab_tenant.sh`) and the live byte-diff executed
(`scripts/ndt_parity_diff.sh`). Result: **tick scope is byte-identical; day scope is not.**

Four defects in S1, all silent, all invisible to the unit suite because it runs against
DDL-created tables with every cache layer stubbed:

1. The store's INSERT omitted `id`, which only has a server default on the DDL path.
2. `set_status` mixed `json` and `jsonb` in a `COALESCE` (the ORM said `JSON`, the migration says
   `jsonb`). `CannotCoerce` was swallowed by the store's own error handling, so day runs wedged at
   `queued` forever with nothing logged.
3. The Mongo L2 cache was **entirely dead** - `_mongo_collection` read a non-existent
   `mongo_manager.db`, and every call site treats a `None` collection as "layer unavailable".
4. Day scope could never satisfy `include=["raw_ue_arrays"]`: the arrays were stripped before every
   layer, and a day poll reads persisted state. rApp's delegated day path returned an empty
   `raw_tick_data` while its local path returned all 24 ticks.

Plus the reason those were findable: the day dispatcher discarded the `Future` from `submit()`, so
anything escaping the worker's own `except` vanished. Retaining it (as `InferenceJobRunner` does)
surfaced defect 2 within one request.

**Risk 9 confirmed with a concrete mechanism, and it is worse than anticipated.**
`predictions_to_cell_configs` seeds `cell_az_deg: 0.0` and `cell_carrier_freq_mhz: 2100.0` and then
never overrides them - its own comment says "overridden by config if available", but the guard is
`if col not in cell_config or pd.isna(...)`, which is never true for those keys. So rApp flattens
every cell to boresight 0 and a single 2100 MHz carrier regardless of the baseline. On the lab
baseline (9 cells across 700/850/1800/1900/2100 MHz) that matters enormously, because
`perform_attachment` counts interference only among co-channel cells:

| | local (rApp) | NDT preserving the real spectrum |
|---|---|---|
| `sinr_p50` | -0.53 dB | +39.25 dB |
| `sinr_p95` | 6.66 dB | 91.57 dB |
| `rsrp_p5` | -94.20 dBm | -119.68 dBm |
| `outage_rate` | 0.00 | 0.45 |

A 91 dB SINR is physically impossible, so **rApp's local output is the wrong one** - but it is the
output the epic's byte-compat DoD is defined against. Resolved with
`NDT_RF_ENRICHMENT=rapp_compat|baseline`, defaulting to `rapp_compat`, which closed the gap from
**-25.5 dB to -0.09 dB** on `rsrp_p5`. **`baseline` is the physically correct mode and should become
the default the moment S3 removes rApp's local path**, since byte-compat then constrains nothing.
That flip is a deliberate, reviewable KPI change - which is why it is a named mode.

**Residual, still open:** day scope differs by under 0.3 dB on every percentile
(`rsrp_p5` -94.1999 vs -94.2897) and, more tellingly, UE attachment shifts - `max_ue_per_cell` 25 vs
21 at tick 0, `jains_fairness_index` 0.678 vs 0.821. Same 848 UEs, identical per-tick counts,
identical on/off decisions (the energy KPIs match exactly), and the day-0 fallback warning matches
verbatim. So the remaining divergence is in the twin's per-cell inputs or in attachment tie-breaking,
not in the data or the decision. Candidates not yet excluded: cell-config row order reaching
`perform_attachment`, dtype/precision differences between the two services' `load_ue_dataset`
implementations, and extra topology columns surviving into `create_prediction_frames`.

**S3 — DONE** (rapp `d718130`, bdt_engine `a3694c5`, parent below). rApp's in-process twin path is
gone; the NDT is the only implementation. Verified end to end after deletion: day `/infer` returns 200
with `rsrp_p50` matching the pre-deletion local value exactly, tick returns 202, and the NDT is
provably exercised (`ndt_evaluation_runs` + `ndt_kpi_snapshots` rows written). Suites: rapp 249 passed
/ 0 failed; bdt_engine 140 passed / 11 pre-existing.

Three corrections to S3's file list, each found by reading the code rather than trusting the plan:

1. **Three** non-MRO twin call sites needed delegating, not one. The story named only
   `_build_inference_result_non_mro`; `build_inference_result_compare` and
   `_build_baseline_inference_result_non_mro` also ran the twin locally, and the grep-clean criterion
   cannot pass while they do.
2. `compute_guardrail_kpis` is **not deletable**. `compute_mro_guardrail_kpis` calls it, so removing
   it broke every MRO guardrail test. MRO stays in-process, so it stays.
3. `resolve_bdt_model_path` in `data_loader` is **not deletable**. `_evaluate_mro` still resolves BDT
   pickles for `perform_attachment_hyst_ttt`, so "delete the BDT pickle resolution block" would have
   broken MRO.

**The `NDT_RF_ENRICHMENT` flip was measured and NOT taken.** The plan was to switch the default to
`baseline` once byte-compat stopped constraining anything. Measuring it produced SINR p50 +39.3 dB,
p95 +90.9 dB and 45.6% outage - physically impossible. The mode is not at fault; the baseline DATA is:
data_sim's topology generator spreads five carrier frequencies across nine cells, so honouring them
leaves ~2 cells per layer and almost no co-channel interference. `rapp_compat`'s flattening is wrong in
principle but lands on plausible numbers precisely because it forces one dense layer. Default stays
`rapp_compat`; **the real fix is the generator's carrier assignment**, which belongs with whoever owns
the synthetic topology. Flipping first would trade a pessimistic-but-plausible KPI set for an
impossible one.

**Deployment note, now load-bearing:** `NDT_BASE_URL` and `NDT_API_KEY` are REQUIRED for non-MRO
inference - there is no local fallback. A wrong `NDT_API_KEY` fails every non-MRO `/infer` with a 401,
observed during verification when `BDT_API_KEY` was unset and compose defaulted it to `changeme`. MRO
needs neither.

The two-mode parity harness is retired: `scripts/ndt_parity_diff.sh` refuses to run and says why (a
diff needs two implementations), and `tests/test_ndt_parity_integration.py` is a tombstone rather than
a permanently-skipping test. `scripts/seed_lab_tenant.sh` and `scripts/ndt_parity_compare.py` remain
useful. Live cover for the surviving path: `tests/test_ndt_only_path.py` (no fallback survives, and
S3's grep-clean criterion as an executable test), `tests/test_ndt_parity.py` (the translation layer),
`tests/test_ndt_client.py` (transport).

## Rollout / migration notes

**Order.** S1 -> S2 -> (parity gate) -> S3, with S4 and S5 parallelizable after S1 (S4 needs E1's `/data/pm` live), then S6 -> S7 -> S8; S9 (feature-builder cutover) runs last, after S4 has soaked in lab. E5 (closed-loop demo) consumes S6-S8 plus E3/E4 executors.

**DB migration.** Single additive migration `artifacts/migration/014_ndt_loop.sql`, grown across stories: `ndt_evaluation_runs` (S1), `ndt_feature_builds` + `ALTER TABLE baselines ADD COLUMN IF NOT EXISTS stats jsonb` (S4), `ndt_kpi_snapshots` (S5), `loop_policies` + `loop_actions` + `loop_proposals` + `loop_feedback` (S6). Cross-epic numbering is frozen in HLD Appendix A.6 (011=E1 canonical, 012/013=E4, 014=this epic, 015=E5 policy seed); apply in numeric order, and note 015 (E5's per-tenant policy seed) targets THIS migration's `loop_policies` table, so 014 must land first. All tables carry `tenant_id` and join the existing RLS + updated_at trigger blocks in `artifacts/design/schemas.sql`. Everything is additive; no shared-table column is altered or dropped, so `baselines`/`ue_datasets`/`bdt_models`/`training_jobs` readers in other services are untouched. bdt_engine's startup `create_tables` creates the new tables in dev; the migration file is the prod path (manual, per repo convention).

**Backward-compat shims.**
- `RAPP_TWIN_EVAL_MODE=local` (default at S2 deploy) keeps rapp fully in-process; flip to `ndt` per environment after the parity suite passes there; S3 removes the flag. Rollback at any point before S3 = set the env back to `local`.
- rapp's `rapp_evaluation_results`/Redis cache keys are unchanged, so cached day evaluations stay valid across the flip.
- The feature builder writes the same artifact schemas/S3 keys as smo_sim's pipeline, so baselines/datasets from either source remain interchangeable during E1/E4 transition; `ue_datasets.source_type` stays `utils_traffic_load`.
- `NDT_LOOP_CONSUMER_ENABLED=false` disables the loop consumer thread if it ever destabilizes bdt-worker training (training loop is isolated regardless).

**Env-only deployment changes (zero CI/CD).**
- rapp: `NDT_BASE_URL` (compose: `http://bdt_engine:8000`), `NDT_API_KEY` (= the bdt service key), `RAPP_TWIN_EVAL_MODE` (transitional). k8s: add `NDT_BASE_URL`/`NDT_API_KEY` to the rapp chart's `values.yaml secretData` in `maveric-deployment` (base64 env entries only; no chart/template/image/port change).
- bdt_engine/bdt-worker: `DATA_PLATFORM_BASE_URL`, `DATA_PLATFORM_API_KEY` (S4; S7's canonical-PM watch reuses them on bdt-worker), `NDT_LOOP_CONSUMER_ENABLED`, `NDT_ACTION_TTL_MIN` (S6), `LOOP_WATCH_TICK_SECONDS` (S7, default 60). Same secretData-only note.
- Kafka: three loop topics added to `scripts/kafka/init-topics.sh` (compose) and, at deploy time, to the existing kafka chart topics-job values (values-only edit, no pipeline change).

**Data migration.** None required. Existing BDT pickles remain loadable (native class path in bdt_engine; S1 compat test). No backfill of `ndt_kpi_snapshots` or `loop_actions`.

**Docs.** `artifacts/design/schemas.sql` is updated in-epic (data contract). LLD/openapi/`.context` updates are E6's gate; note that the NDT APIs are internal (not gateway-routed) in this epic, so `openapi.yaml` gains nothing yet.

### S6 IS DONE (2026-07-30), all four gate branches verified against the real twin.

89 new tests (45 decision hub, 29 consumer, 15 policy). bdt_engine suite **238 passed / 11 failed**,
the 11 being the recorded pre-existing baseline - verified identical by running the suite in a
worktree at HEAD and diffing the failure sets, not by inspection.

**Lab exercise, in order, on tenant `...3029-000000000001` with `lab-baseline-1` / `lab-bdt-1` /
`lab-dataset-1`:**

| Step | Result |
| --- | --- |
| `GET /ndt/loop/policy`, no row | HLD §4.2 defaults, `mode=off`, `policy_id: null` |
| REST intake, loop off | one `suppressed` row, no twin run, no Kafka message |
| `PUT` policy `mode=auto` with the DEFAULT guardrails | stored, `policy_id` returned |
| REST intake under those guardrails | **`rejected_by_gate`**: `sinr_p5 -3.0142 < min_sinr_db 0.0000` |
| the same under relaxed guardrails | `dispatched`, exactly one `maveric.loop.action.v1` message |
| Kafka intake (2 cells) | consumer thread handled it, 2 `dispatched` rows, topic depth 1 -> 3 |
| redelivery of the identical message | "already has action rows; skipping" - rows 2, topic still 3 |
| a malformed message and a wrong-dialect one behind it | both logged, committed, skipped; consumer alive |
| `mode=approval` | `pending_approval`, verdict `pass` recorded, topic still 3 |
| `GET /ndt/loop/actions/{id}` | full row with both snapshots; unknown id -> 404 `ACTION_NOT_FOUND` |

The rejection is worth keeping in mind for E5's demo: **the lab data does not clear the HLD default
`min_sinr_db=0.0`.** `sinr_p5` on `lab-baseline-1` at tick 7 is -3.01 dB, so a demo that expects a
dispatch needs either a permissive policy or a better baseline. That the gate said no, with the exact
number and threshold in `evaluation.reasons`, is the story working.

Consumer-group separation confirmed live: `ndt_loop` on `maveric.loop.proposal.v1` and `bdt_worker` on
`maveric.bdt.train.v1`, both at zero lag, in one process (epic risk 4).

**Three design decisions that deviate from the story text, each because the text does not fit the code:**

1. **Contracts live in `app/models/ndt_loop_models.py`, not in `decision_hub.py`.** The story's key
   snippet puts the Pydantic models in the service module. Keeping them separate is what lets the REST
   route and the Kafka consumer both parse with the same model without importing the hub - which
   matters because the hub imports `ndt_runner`, i.e. torch and the vendored twin. They are also
   deliberately NOT in `ndt_models.py`: that file's shapes are byte-compared against rapp's golden
   responses, and mixing a second contract surface into it would put loop edits one careless line away
   from a parity break.
2. **`insert_actions` returns the ids it actually inserted.** `ON CONFLICT DO NOTHING` alone makes the
   rows idempotent but not the dispatch: two concurrent deliveries can both pass the
   `existing_action_ids` pre-check, and without `RETURNING` neither learns it lost, so both produce a
   Kafka message for the same action. The pre-check saves a wasted gate evaluation; `RETURNING` is the
   exactly-once guarantee.
3. **The consumer commits per message, not per outcome.** A message that can never succeed
   (undecodable, wrong dialect) is committed and skipped, because redelivering it forever would block
   the partition. A message that failed for a reason outside itself (database unreachable) is NOT
   committed, so a restart replays it - committing there would discard a proposal that was never gated
   and leave no trace. The story text only specifies the first case.

**A dispatch that fails to produce lands on `failed`, terminally.** The redelivery guard skips a
proposal whose actions exist, so replaying it will not retry the dispatch; it needs a new proposal, or
S8's approve path. A visible `failed` row with the reason is honest about that, where leaving it at
`proposed` would look like work still queued somewhere.

**Two findings outside the story, both pinned by tests:**

- **A test-only trap, but a costly one.** The migration-section slicer used a bare `-- E2.S7` marker,
  which matched an S6 *comment* mentioning S7 and truncated the section at it - silently dropping the
  RLS and trigger blocks from every scratch database. Everything passed except the FORCE-RLS guard.
  Section markers are now matched in their colon form, and `tests/scratch_db.py` records why.
- **RLS is not observable as a superuser, FORCE or not.** `FORCE ROW LEVEL SECURITY` removes the table
  OWNER's bypass; it does nothing about `rolsuper` or `BYPASSRLS`. Two isolation tests here initially
  passed while proving nothing, because the scratch database is reached as `postgres`. They now run
  through a dedicated non-superuser probe role. Related and worth knowing before debugging one: once a
  custom GUC has been SET in a session, clearing it leaves it as the EMPTY STRING rather than NULL, so
  `(current_setting('app.current_tenant', true))::uuid` raises `DataError` instead of returning zero
  rows. Still fail-closed, but a confusing error rather than an empty result - and that is the shape
  every RLS policy in `artifacts/design/schemas.sql` uses, not something this story introduced.

**Remaining for S6:** nothing functional. `watch_deadline` is left NULL by design - the watch window
starts when a change is APPLIED, not when it is dispatched, so S7 sets it from the `watch_window_min`
already snapshotted in `policy_ref`. `loop_feedback` is created here so S7 needs no DDL.

### S7 IS DONE (2026-07-30), the full status machine demonstrated live.

103 new tests (69 watcher, 34 consumer). bdt_engine suite **312 passed / 11 failed** - the same
recorded pre-existing baseline, failure set diffed against it, and verified stable across three
consecutive runs.

**Lab exercise, on the same tenant and baseline as S6:**

| Step | Result |
| --- | --- |
| two changes dispatched on `cell_1` (ticks 3 and 9, day scope) | both `dispatched` |
| two `kind=apply status=applied` feedbacks on the topic | both `watching`, deadline = applied + **20 min** from each row's own `policy_ref` |
| one `kind=kpi_window` the executor labelled **`status: "ok"`** but carrying `rrc_success_pct: 61.5` | **both** actions `rolled_back`; two rollback rows `dispatched` |
| the two rollback messages on the wire | LIFO: `rollback_of` tick-9 at offset 5, tick-3 at offset 6, both with the frozen §4.1 key set |
| back-date `expires_at`, wait one tick | the watch tick fired unprompted inside the worker thread and expired 3 actions |

Two things worth pulling out of that. The executor said the window was **fine** and the NDT rolled back
anyway, because the breach check is NDT-side against the tenant's own guardrails - an executor that
mis-evaluates cannot suppress a rollback. And a breach reported against the OLDER of the two actions
still reverted **both**, newest applied first: reverting only the breached one would leave the cell in a
state no evaluation ever approved.

**The canonical-PM watch can only enforce one of the three guardrails, and it is not a choice.** The
nybsys canonical set is `RRC.ConnMean` plus `pm_stages.SUM_COLS`; it contains no SINR and nothing from
which outage can be derived. So on the A1 path `min_sinr_db` and `max_outage_rate` are twin-PREDICTED
and never measured, while `min_rrc_success_pct` - the one the twin cannot predict - is the only one
canonical PM can actually check. The story's "missing keys are skipped" rule composes with that
exactly: the watch computes what the data supports and stays silent about the rest. **E3.S4 and E4
should know that an A1-path action's SINR is never verified after the fact.** Closing that needs a SINR
counter in the ingest contract, which is an E1/adapter decision, not an E2 one.

**A defect this story surfaced in data_sim** (fixed, `eb49699`): the mock PM export emitted
`RRC.ConnEstabAtt`/`RRC.ConnEstabSucc` where the adapter sums `RRC.AttConnEstab`/`RRC.SuccConnEstab`.
`aggregate_pm_to_day_tick` filters `[c for c in SUM_COLS if c in df.columns]`, so the whole companion
set was dropped SILENTLY at ingestion - no warning, no error, just canonical PM containing one metric.
That made the multi-metric fan-out the mock claimed to exercise fictional, and made
`rrc_success_pct` - the one thing the A1 watch reads - permanently unavailable in a mocked lab.

**Three design decisions:**

1. **`fetch_pm_items` was promoted out of `pm_source`'s privates** rather than reimplemented. The
   auth header, the `has_more` pagination and the error translation are exactly the parts that must
   not exist twice. `_params` now takes a metric SEQUENCE, since `metric` is repeatable on the wire and
   the watch needs two.
2. **The watch tick lives in the consumer's poll loop**, throttled on `time.monotonic()` so an NTP step
   cannot skip or stall it, and it runs AFTER message handling so a just-applied action is not swept in
   the iteration that opened its window. A separate thread would mean two writers of action status for
   no gain.
3. **The sweep is the one place with no tenant pin.** It is driven by the clock, not a request, so
   there is no tenant to pin and iterating tenants would need a tenant list this service does not own.
   It touches no row contents beyond a status the clock already determined, and carries `tenant_id`
   back out so every subsequent write IS pinned.

**A flake in this story's own tests, worth recording because the diagnosis was not the obvious one.**
Four sweep tests failed together, exactly once, and passed on every rerun. The cause was not the code:
they seeded `watch_deadline` from the HOST clock and the sweep compares against Postgres `now()`, and
the Docker Desktop VM clock drifts. Anything the sweep judges is now seeded as
`now() + interval '...'` - evaluated by the database itself - while the LIFO ordering tests keep host
datetimes, because those compare rows only against each other and a shared skew cancels out.

**Remaining for S7:** nothing functional.

### S8 IS DONE (2026-07-30). S9 IS GATED-GREEN BUT ITS SOAK IS RED - DO NOT DELETE `legacy_builder` YET.

**S8** (bdt_engine `9b11d9c`, parent `1de632e`): 49 tests. Approval is one atomic
`UPDATE ... WHERE status = 'pending_approval' RETURNING`, so a double-click is a 409 rather than a
second dispatch. Lab: list -> approve (200, one message, `updated_by` recorded) -> double-approve 409
`ACTION_NOT_PENDING` -> unknown 404 `ACTION_NOT_FOUND`; topic depth 7 -> 8. The dispatch helper is now
shared by all three producers (auto, approve, rollback) so the §4.1 envelope cannot drift.

**S9's GATE IS MET, and meeting it exposed a serious defect.** The two determinism suites each pinned
their OWN builder against their OWN input, so between them both could be self-consistently wrong - and
were. Running both implementations on the SAME real nybsys grid at seed 42 showed `topology`/`config`
byte-identical but `ue_data` and `training` DIVERGENT. The cause was not the lift: **`shapely` was in
`requirements.txt` but absent from the running bdt_engine IMAGE**, which predated that commit. UE
placement silently degraded from Voronoi polygons to a bounding-box scatter - positions out by up to
0.15 degrees (kilometres) and training RSRP labels by up to 69 dB. With shapely installed all four
frames are byte-identical across numpy 2.3.2/pandas 2.3.1 and numpy 1.26.4/pandas 2.2.2.

The pytest guard could not have caught it: `importorskip` means it SKIPS in the one environment where
shapely is missing. `runner.require_voronoi()` now refuses the build at the point of use and stamps
`placement_mode` into `stats` (and therefore `baselines.stats`), so a degraded baseline is
self-identifying. `tests/test_feature_builder_cross_service.py` pins the gate permanently - it matters
most AFTER S9 deletes data_sim's copy, because from then on the comparison cannot be re-derived.

**The soak is NOT green. Three findings, and the third is a behavioural regression of the flip:**

1. **Both service keys must be exported or the seam 401s in both directions.** `NDT_API_KEY` and
   `DATA_PLATFORM_API_KEY` default to `changeme`; the lab reproduced a 401 data_sim->bdt_engine and
   then a 401 bdt_engine->data_sim. Compose now wires both from `${BDT_API_KEY}` / `${DATA_SIM_API_KEY}`,
   which operators must export - the root `.env` is tracked and must not carry them.
2. **Canonical PM dedups on the natural key, so an overlapping re-upload is invisible to a builder
   scoped by `upload_id`.** Two uploads covering the same hour for the same `dn` produce one canonical
   row, labelled with whichever landed FIRST; the second upload's feature build then finds zero
   `RRC.ConnMean` rows and fails. This is correct idempotency, not a bug, but it is a sharp edge for
   E1's ingest contract and it will bite a real operator re-exporting a corrected file.
3. **The seam never read bdt_engine's response envelope, so EVERY build timed out** (fixed, data_sim
   `0553448`). `NdtApiBuilder.trigger` polled `GET /ndt/feature-builds/{id}` and read
   `payload["status"]`, but bdt_engine wraps every response in its service-wide envelope - the real
   body is `{success, timestamp, message, data: {build_id, status, ...}, errors}`. So `status` was
   ALWAYS `""`, the loop never saw a terminal state, and every ndt_api build spun for the full
   `NDT_BUILD_TIMEOUT_S` (30 minutes by default) before failing as a timeout - whether the build had
   completed or failed.

   This is worth recording carefully because the first diagnosis was WRONG. The symptom - an upload
   sitting at `processing` while its build had already failed - reads exactly like a missing
   reconciler, and that is what it was initially written up as. It is not: `trigger()` already polls
   to completion and already syncs the upload status. It simply could not see the answer. **Neither
   service's unit tests could have caught it**, because each stubbed the other side with the shape it
   expected; the two only met on the wire, which is the entire argument for the soak existing. The poll
   loop had no test coverage at all; it now has nine tests driving the real enveloped body through
   `trigger()` over `httpx.MockTransport`. An unrecognised status also now fails fast and names the keys
   it received, rather than being waited out for 30 minutes and blamed on a timeout - the silent
   patience was the more expensive half of the defect.

**S9's SOAK IS NOW GREEN.** End to end through the flipped seam on the lab tenant: upload ->
`completed`, build -> `completed`, 9 cells / 3 sites / 4811 UE records / 450 training records,
`placement_mode: "voronoi"`, `semi_synthetic: true`, all four CSVs at the existing S3 keys, and both
the `baselines` and `ue_datasets` rows written with `source_type: utils_traffic_load` - so datasets
from either producer remain interchangeable, as the story requires.

**`NDT_FEATURE_BUILDER_MODE` default is flipped to `ndt_api`; `app/ingest/legacy_builder/` is still
NOT deleted.** Every gate condition is now met - S4 merged, cross-service hash-identity proven and
pinned, a lab upload completed through the seam - so the deletion is UNBLOCKED. It is held only because
removing the package also removes the documented rollback path (`NDT_FEATURE_BUILDER_MODE=
legacy_inline`), and the story asks for a staging soak in addition to the lab one. Deleting is a single
commit whose revert is the rollback, and it needs an explicit go-ahead rather than being inferred.

### Adversarial review of S6/S7/S8 (2026-07-30): 27 agents, 33 findings, 6 real defects fixed

Six independent lenses (status machine, concurrency, tenancy/injection, wire contract,
failure-observability, test integrity) over ~2000 lines, each finding then attacked by two diverse
skeptics instructed to default to refuted. Three criticals were CONFIRMED by both skeptics with
executed reproductions. All six are fixed in bdt_engine `ba3b72f`; every one shared the same shape -
**a change stays live on the network while the audit trail records the healthy outcome.**

1. **CRITICAL - one transient broker failure made a breach permanently un-revertible.** Rollback ids
   are deterministic, so a failed produce leaves the row present; `ON CONFLICT` then returned nothing
   for every later breach, `emit_rollbacks` skipped it, and the sweep promoted the still-`watching`
   breached action to `completed`. `claim_rollback_retry` now separates "a concurrent breach owns this"
   from "an earlier attempt never went out", moving the row to `dispatching` (writing back `proposed`
   left it claimable again - the test caught that on the first pass).
2. **CRITICAL - the sweep and the A1 watch failed CLOSED, silently, and only worked in dev by
   accident.** Three statements ran with no tenant GUC under a comment claiming RLS was "bypassed
   deliberately". Omitting the GUC does not bypass a policy, it FAILS it - zero rows on a fresh
   connection, and `DataError` on a pooled one because Postgres resets a custom GUC to the EMPTY
   STRING, not NULL. Both were swallowed, and `sweep_deadlines` only logged on a non-zero count. Under
   the non-superuser role the deployment docs mandate, **no window would ever have closed and the A1
   watch would have examined nothing, forever, with no log line.** Fixed with an explicit
   `<table>_maintenance_rls` policy and `maintenance_transaction()`, proven through the suite's
   non-superuser probe role. Dev never saw it because dev connects as `postgres`.
3. **CRITICAL - a change reached the network with a `pass` verdict from a twin run that never applied
   it.** `_tick_config_items` returns the FIRST entry matching the evaluated tick, else `[]`, so a
   tick-scope proposal whose recommendation carried a different tick was scored against the untouched
   baseline, and a day-scope proposal with two entries on one tick had the second silently dropped -
   both then dispatched every item as gate-passed. One of this suite's OWN fixtures was exercising the
   mismatch.
4. **HIGH** - `mark_failed` was unguarded, so a late apply/failed could overwrite an operator's
   `rejected`, a `suppressed` audit row, or a `rejected_by_gate` verdict.
5. **HIGH** - a rollback could enter `watching` and then be rolled back itself, re-applying the change
   the gate rejected and chaining without end. Now excluded in SQL rather than trusting every executor
   to route on `payload.rollback_of` first.
6. **HIGH** - `watch_deadline` was anchored to the executor's `observed_at` with no clamp, so a lagged
   replay produced an already-past deadline and the next sweep completed the action unwatched.

Separately, the soak found that **the canonical-PM watch queried VENDOR metric names against a
CANONICAL store**: `vendor_dictionaries` maps nybsys `RRC.AttConnEstab` -> `RRC.ConnEstabAtt`, so the
A1 watch fetched zero rows, an empty window is not a breach, and it would have passed everything
forever. Only `RRC.ConnMean` is identity-mapped, which is why S4's feature builder was unaffected.

**20 findings were NOT verified** (the run capped verification at the top 10 by severity). They are
listed in the workflow output and several look worth a follow-up pass - notably whether the loop
consumer can commit past an uncommitted failed message, and whether apply feedback arriving while an
action is still `proposed`/`approved` is dropped.

### Running this epic's chain in a local lab: two prerequisites that are easy to miss

Both cost real time during S9's soak, and neither fails in a way that points at itself.

**1. Export the service API keys before `compose up`.** compose references `${BDT_API_KEY}` and
`${DATA_SIM_API_KEY}` rather than inlining them, because the root `.env` is TRACKED. Unset, they
default to `changeme` and the seam 401s in BOTH directions - data_sim -> bdt_engine on the feature-build
POST, and bdt_engine -> data_sim on the `/data/pm` read. Capture them from the containers without
printing them:

    export BDT_API_KEY="$(docker exec bdt_engine printenv API_KEY)"
    export DATA_SIM_API_KEY="$(docker exec data_sim printenv API_KEY)"
    docker compose --profile apps up -d --force-recreate --no-deps bdt-engine bdt-worker data-sim

**2. Apply `artifacts/migration/014_ndt_loop.sql` by hand on an existing volume.**
`docker-entrypoint-initdb.d` runs only on first cluster init, so a stack whose volume predates any of
014's sections never receives them. Symptoms differ per section and none of them names the migration:
missing loop tables, a missing `updated_by`, or - worst - a watch sweep that silently moves nothing
because the maintenance policy is absent. It is idempotent:

    docker exec -i postgres psql -U postgres -d maveric -v ON_ERROR_STOP=1 < artifacts/migration/014_ndt_loop.sql

**Rebuild the image after a `requirements.txt` change, do not just restart.** `compose.sh restart`
reuses the existing image. That is how `shapely` came to be listed as a dependency while absent from
the running bdt_engine container, silently degrading UE placement. Use
`docker compose build <svc> && docker compose up -d --force-recreate --no-deps <svc>`.

## Epic-level risks

1. **Parity drift between duplicated defaults.** `DEFAULT_THRESHOLDS`/`DEFAULT_ENERGY_PARAMS` and `merge_*` exist in both rapp (cache keys) and NDT (evaluation) between S2 and S3. Mitigation: parity tests pin both; S3 shrinks rapp's copy to cache-key use only.
2. **Day-scope latency over HTTP.** The 24-tick GP loop moves behind an HTTP hop with 202/poll while rapp's public day `/infer` stays synchronous; total compute is unchanged, but polling overhead plus gateway timeout budgets must be validated in the lab before flipping `RAPP_TWIN_EVAL_MODE` (mitigations: `NDT_EVAL_TIMEOUT_S`, NDT-side cache hits, rapp's existing `rapp_evaluation_results` cache in front).
3. **Pickle class-path coupling persists.** Any rename of `app/radp/digital_twin/rf/bayesian/engine.py` in bdt_engine breaks every stored model; the S1 compat test guards it, and this epic deliberately does not touch the module path.
4. **bdt-worker stability.** A second consumer thread in the training worker shares the process; a crash loop in the loop consumer must not take training down (daemon thread, per-message exception isolation, `NDT_LOOP_CONSUMER_ENABLED` kill switch).
5. **Feature builder depends on E1 semantics.** `dn` format and canonical metric naming (`RRC.ConnMean` vs a TS 28.552 mapping) are E1 decisions; the builder parameterizes the metric name (`FEATURE_BUILDER_CONN_METRIC`) and pins the dn convention in one function (`pm_source.py`) to localize any reconciliation.
6. **Loop executors do not exist yet.** Until E3/E4 land, dispatched actions have no consumer; `expires_at` + the expiry sweep keep the audit trail honest, and E5 owns the end-to-end wiring.
7. **Approval-surface reachability. RESOLVED by E5.S7 (2026-08-04).** Approval endpoints were internal-only until the gateway `/ndt/**` story, which was unowned by any epic until E5 claimed it. `/v1/tenants/{t}/ndt/**` is now gateway-routed under Cognito + RequireMembership, so the frontend approvals surface can reach it. Lab demos may still hit bdt_engine directly with the service key.
8. **Shared-table additive change.** `baselines.stats` is new; data_sim/smo_sim writers that INSERT with explicit column lists are unaffected, but any `SELECT *`-into-ORM strictness must be checked in the S4 integration run (rapp/bdt map `baselines` with explicit columns today, so risk is low).
9. **Cell-config enrichment asymmetry between the two twin inputs (found during S2; this is what the parity gate is looking for).** rApp sends only the decision — `{cell_id, cell_el_deg, on_off}` — and the NDT applies it to the topology **it** loads from `baseline_id`. rApp's local `cell_configs` frame is additionally enriched by `predictions_to_cell_configs` from the baseline cell-config CSV (`hTx`, `hRx`, `cell_az_deg`, `cell_carrier_freq_mhz`, plus any extra topology columns). If that enrichment contributes an RF parameter the NDT's `load_topology` does not have, the twin sees different inputs and predicts different RSRP — with no error anywhere. Nothing unit-testable detects it, which is precisely why S3 is gated on the live byte-diff rather than on the unit suite. Signature: a shift in `guardrail_kpis` RSRP percentiles. If it fires, the fix is to align the NDT's topology load with rApp's enrichment (or to widen the payload contract), **not** to loosen the diff.
10. **Two known silent-degradation traps in the rebuilt attachment frame (mitigated in S2, listed so S3 does not reintroduce them).** `_generate_plot_payload` emits zero UE groups when `serving_cell_id` is absent, and the CCO coverage maths reads `cell_id` — neither raises. Separately, JSON forces cell ids to strings, so a numeric-cell_id deployment would get `"1"` where the local path had `1`, changing plot group titles and making `value_counts().reindex(active_ids)` miss entirely. Both are covered by tests in `tests/test_ndt_parity.py`; keep those tests when S3 converts the parity suite to NDT-only.
