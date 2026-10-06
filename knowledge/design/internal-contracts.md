# Internal Contracts (east-west, storage, and data-layer)

**Version:** 1.0 · **Status:** binding during the re-architecture transition (frozen HLD §3.3)
**Evidence date:** 2026-07-29 · **Story:** EPIC-0.S3

Every claim below carries a `file:line` citation that was opened and read. Claims were gathered by
five independent sweeps and then audited by an adversarial pass that re-opened 54 citations and ran
six omission greps; 50 were exact, 2 were off-by-one, and 4 substantive corrections were applied
before this document was written. Where evidence was absent the cell says **NOT FOUND** rather than
repeating what a design doc asserts. Design docs are not evidence here; only source, SQL and chart
YAML are.

> **Read §1.1 first.** The single most consequential finding is that the gateway does not create the
> shared schema, despite `artifacts/upgrade_plans/datamigration.md` stating that it does.

---

## 1. Shared-table ownership matrix

Seven tables are shared across services through duplicated partial ORM definitions. "Writer" means a
service that issues INSERT/UPDATE/DELETE; "reader" means SELECT only.

| Table (`schemas.sql`) | Writers today | Readers today | Owner after re-arch | Transition rule |
|---|---|---|---|---|
| `baselines` (:153) | smo_sim (REST CRUD, NybSys runner, cascade delete), data_sim (INSERT, raw SQL, synthetic-topology endpoint) | smo_sim, data_sim, rapp (RO `BaselineRef`), bdt_engine (RO `BaselineRef`) | bdt_engine feature builder writes new rows (HLD §4.6); smo_sim legacy writer retained until E2 | additive columns only, no renames |
| `ue_datasets` (:169) | smo_sim (INSERT/DELETE, NybSys runner, cascade delete), data_sim (`INSERT … ON CONFLICT DO NOTHING` + legacy-schema fallback) | smo_sim, data_sim, rapp (RO `UEDatasetRef`), copilot (HTTP GET via smo_sim, never SQL) | bdt_engine feature builder + data_sim factory | additive only. **No UPDATE path exists in any service** |
| `bdt_models` (:187) | bdt_engine only (API INSERT/DELETE; bdt_worker UPDATEs status, retry_count, metrics, artifacts_uri) | bdt_engine, rapp (RO `BDTModel`) | unchanged | single-writer, keep it that way |
| `rapp_models` (:222) | rapp only (API INSERT/DELETE; rapp_worker UPDATEs status/metrics/artifacts_uri) | rapp only | unchanged | single-writer |
| `training_jobs` (:242) | **three services**: bdt_engine (`kind='bdt'`), rapp (`kind='rapp'`), data_sim (raw INSERT) | bdt_engine, rapp | unchanged | the `kind` column is the only thing separating three writers; never widen it implicitly |
| `inference_runs` (:272) | rapp only (`INSERT … ON CONFLICT (id) DO NOTHING`, UPDATE from six sites, bulk stale-run reset at startup) | rapp; gateway issues one backfill statement | unchanged | single-writer |
| `bdt_inference_runs` (:205) | bdt_engine only (API INSERT `queued`; inference_runner UPDATEs running/completed/failed) | bdt_engine only | unchanged | single-writer. **See §1.2, RLS gap** |

### 1.1 The gateway does not own the schema (correction to `datamigration.md`)

`artifacts/upgrade_plans/datamigration.md:3` states: *"The gateway is now the sole component that
performs schema migrations, using GORM auto-migration."* **This is not true of the code.**

- `submodule/maveric_platform_gateway/internal/db/migrate.go:229` reads
  `// AutoMigrate disabled: schema managed externally to avoid unexpected drift.` The entire
  `gdb.AutoMigrate(...)` call over the eight migrator structs is commented out (`:230-241`).
- The migrator structs cited throughout this section (`:38`, `:53`, `:68`, `:85`, `:104`, `:121`)
  therefore **create nothing**. They survive only as `TableName()` map keys.
- The per-table trigger / index / ALTER statements are gated at `migrate.go:316` by
  `if gdb.Migrator().HasTable(table)`.

The consequence is a startup race, not a migration: on a fresh database, whichever service's
SQLAlchemy `create_all` runs first defines the table shape (bdt_engine does this at
`app/main.py:162` → `db/sql_handler.py:143`), and every gateway index, trigger and constraint
statement for a table that does not yet exist **silently skips**.

**Ownership in practice today: whichever service starts first declares the table, and the gateway
only decorates what already exists.** E1.S1 moves the canonical PM/FM/CM tables to an explicit
alembic revision owned by data_sim, which is the first time any of this becomes deterministic.

### 1.2 RLS is defined in three places and they disagree

| Definition | Tables | ENABLE | FORCE |
|---|---|---|---|
| `artifacts/design/schemas.sql:482` | 18 | yes | yes |
| `gateway internal/db/migrate.go:328` | 8 | yes | **yes** |
| `gateway db/migrations/schemas.sql:247` | 9 (adds `rapp_evaluation_results`) | yes | **NO** |

Two facts follow, both load-bearing:

1. **The gateway's Go list is a strict subset of the design list.** Drift is one-directional
   (gateway ⊂ design), not two-directional. `bdt_inference_runs` has **no migrator struct and is
   absent from the gateway's RLS list entirely**, so tenant isolation on that table depends solely on
   `artifacts/design/schemas.sql` having been applied by hand.
2. **The gateway's checked-in SQL path omits `FORCE`.** Without `FORCE ROW LEVEL SECURITY`, the
   table owner role bypasses RLS completely. Whether a deployment is isolated therefore depends on
   which of the two gateway paths ran. This is a security-relevant divergence, not a style one.

---

## 2. S3 key conventions (contract v1)

All keys are wrapped by a configured bucket prefix before hitting S3 (`S3_PREFIX`, deployed as
base64 `dGVuYW50cw==` = `tenants`). **The prefix helper is implemented five independent times** with
no shared test pinning them together: `smo_sim app/lib/s3wrap.py:60`,
`data_sim app/utils/s3wrap.py:346`, `rapp app/services/utils/data_loader.py:65`, plus the frontend's
client-side builder and the Next.js signing route.

| Key template | Writers | Readers |
|---|---|---|
| `{tenant_id}/baselines/{baseline_id}/topology.csv` | data_sim `sim_utils.py:215`, smo_sim `nybsys_runner.py:100` | rapp inference + worker |
| `{tenant_id}/baselines/{baseline_id}/config.csv` | data_sim `sim_utils.py:216`, smo_sim `nybsys_runner.py:101` | rapp |
| `{tenant_id}/baselines/{baseline_id}/ue_training_data.csv` | data_sim `sim_utils.py:217`, smo_sim `nybsys_runner.py:102` | rapp, bdt_engine |
| `{tenant_id}/baselines/{baseline_id}/{original_file_name}` | frontend direct upload `AddBaselineModal.tsx:82-88` | by URL only |
| `{tenant_id}/ue/{dataset_id}/synthetic_dataset.csv` | data_sim `sim_utils.py:449`, smo_sim runner | rapp inference + worker |
| `{tenant_id}/ue/{dataset_id}/synthetic_dataset_mobility.csv` | data_sim `sim_utils.py:581` | rapp `data_loader.py:233` |
| `{tenant_id}/models/rapps/{rapp_id}/{rapp_model_id}{ext}` | rapp_worker `rapp_worker.py:717-721` (suffix appended at PUT, `artifact_io.py:331`) | rapp inference |
| `{tenant_id}/bdt/{bdt_id}/{bdt_id}.pickle` | bdt_worker `bdt_worker.py:818` | rapp worker (re-materialises into EFS) |

**Rules.** Keys are append-only contracts. New artifact types add NEW templates and bump to v1.1;
never repurpose an existing template. Feature-builder outputs (E2) MUST reuse the `baselines/` and
`ue/` templates unchanged (frozen HLD §4.6).

### 2.1 Dead and orphaned templates (do not build on these)

- `{tenant}/pm-data-ingestion/{upload_id}/pm_hourly.csv`: written at `nybsys_runner.py:104`, but
  **the return value is not assigned**, so the URL is never persisted anywhere. Write-only.
- `{tenant}/ue/{dataset_id}/profile.json`: written at `sim_utils.py:455`; **no reader**.
- `{tenant}/bdt/{bdt_id}/{bdt_id}_holdout.csv`: written at `bdt_worker.py:873`; **no reader**.
- `{tenant}/ue/{dataset_id}/trainingdata.csv`: `smo_sim s3wrap.py:160` constructs it; **zero call
  sites repo-wide** (independently verified).
- `{tenant}/datasets/**`: four legacy fallback templates that rapp still *reads*
  (`data_loader.py:158/196/227`, `rapp_worker.py:626`); **nothing writes under `datasets/`**.

---

## 3. Shared model volume (EFS `/app/var/models`)

- **Mounted by four pods**: rapp + rapp-worker (`maveric_platform_rapp/templates/deployment.yaml:78`),
  bdt-engine + bdt-worker (`maveric_platform_bdt_engine/templates/deployment.yaml:80`,
  `bdt-worker.yaml:78`). Local equivalent: docker named volume `app_volume`, same four containers
  (`docker-compose.yaml:239`).
- **Not mounted by** smo_sim, data_sim, gateway, copilot, frontend, edge-agent.
- **Contents**: BDT Gaussian-process pickles (`bdt_worker.py:824`), SB3 RL agent `.zip` archives for
  ES/LB/CCO (`radplib/non_mro/profiles.py:25`), and MRO's artifact which is **JSON, not a zip**
  (`radplib/mro/manager.py:129`, default `mro_training_result.json`).
- **Layout**: `<base>/var/models/<tenant_id>/bdt/<file>` and
  `<base>/var/models/<tenant_id>/rapps/<rapp_id>/<file>` (`radplib/utils/paths.py:28,53`).
- **Contract**: the directory layout is shared state between two image streams; changes require a
  coordinated release of both. Never store per-request temp files here.

### 3.1 Three structural hazards

1. **The PV and PVC are created only by the rApp chart**
   (`maveric_platform_rapp/templates/efs.yaml:1`, guarded by `.Values.efs.enabled`). The BDT chart
   mounts `efs-pvc` but has **no `efs.yaml`**. In **staging this is already inconsistent**: staging
   rapp sets `efs.enabled: false` (`staging-maveric_platform_rapp/values.yaml:108`) while staging bdt
   sets `efs.enabled: true` (`staging-maveric_platform_bdt_engine/values.yaml:165`) and claims
   `efs-pvc`. Staging BDT therefore references a claim no chart renders.
2. **Kafka and ZooKeeper share the same `efs-pvc`** via subPaths
   (`maveric_platform_kafka/values.yaml:40-46`). This is not a model volume; it is a shared
   everything volume, and a models-driven resize affects the brokers.
3. **No base-dir override is configured anywhere** (no `*_MODEL_BASE_DIR` in compose or any chart
   values), and `radplib/utils/paths.py:31` falls back to `Path("var/models").resolve()`, which is
   **CWD-relative, not `/app/var/models`**. Correct behaviour depends on the container's working
   directory rather than on configuration.

---

## 4. East-west service auth (API-key pattern)

- **North-south**: the gateway injects `X-API-Key` per upstream target, resolved once per handler by
  host equality (`internal/proxy/proxy.go:73-86`, `:130`), from
  `BDT_API_KEY` / `RAPP_API_KEY` / `SMO_API_KEY` / `DATA_API_KEY` / `COPILOT_BACKEND_API`. It also
  sets `X-Tenant-Id` from the path (`proxy.go:179`). **No `Header.Del` exists anywhere in the proxy**,
  so client-supplied headers are not stripped before forwarding.
- **Callee validation**: all four Python services validate with a plain `!=` comparison
  (`app/utils/security.py:59-64` in each) against `settings.API_KEY`, whose **default value is
  `"changeme"`** in all four (`app/core/config.py:14/14/16/14`).
- **Edge plane** (separate auth domain): `X-Edge-Key`, minted and hashed in
  `smo_sim app/services/nybsys/edge_auth.py:30-72`. The gateway bypasses Cognito for `/v1/agent/`
  at `internal/middleware/middleware.go:179`. Note the bypass test requires a **trailing slash**,
  while `main.go` registers a bare `/v1/agent` as well, so the two do not cover identical path sets.
- **Service-to-service HTTP inside the Python mesh: none exists today.** No `httpx`, `requests` or
  `aiohttp` import appears anywhere in the four services' `app/` trees (independently verified).
  E2's `rapp -> NDT` call will be the **first**, and it should follow the pattern declared here:
  caller holds `<CALLEE>_BASE_URL` + `<CALLEE>_API_KEY` and sends `X-API-Key`; the callee's existing
  key dependency validates it. `NDT_API_KEY`'s value IS the bdt service key. No new key material is
  minted.

### 4.1 The MCP server is an unauthenticated network surface

`submodule/cloudlynet_ai_copilot/backend/app/mcp_server/server_docker.py:32-34` binds the MCP app
with `transport="sse", host="0.0.0.0", port=8080`, published to the host as `:8082`
(`docker-compose.yaml:437`). There is **no API-key check, no JWT check, and no middleware** on it; a
grep for `x-api-key` across `mcp_server/` returns only exception classes and docstrings. The
container holds an `httpx` client pointed at the gateway (`cloudlynet_client.py:52`).

This is the only service surface in the mesh with no authentication of any kind. EPIC-8.S1 addresses
the token-threading half of this; the listener exposure itself should be treated as a separate
finding and is recorded in the secrets/exposure note (`artifacts/deployment/secrets-hygiene.md`).

---

## 5. Kafka topic index (defined in frozen HLD §4.1; listed here verbatim, never redefined)

Existing: `maveric.bdt.train.v1`, `maveric.rapp.train.v1`.
New (E1-E5): `maveric.ingest.pm.v1`, `maveric.loop.proposal.v1`, `maveric.loop.action.v1`,
`maveric.loop.feedback.v1`.

Provisioned via the existing kafka chart topics-job plus `scripts/kafka/init-topics.sh`. **E5.S1 is
the owner-of-record for topic provisioning**; other stories add a topic line only if E5.S1 has not
landed. Payload shapes are frozen in HLD Appendix A.

---

## 6. Actuator/adapter key registry (the contract of record)

Frozen HLD Appendix A.4 names this section as the adapter-key contract of record. It was missing
until EPIC-4 (the HLD pointed here, and there was nothing to point at), so the table below is
reproduced from A.4 with the as-built status added.

**One namespace**, shared by three things that must never disagree: the `adapter` field on
`maveric.loop.action.v1`, the `target_adapter_hint` on `maveric.loop.proposal.v1`, and every
executor-side registry. **Bare `nanolink` is NOT a valid key** and is rejected on all three sides.

| Key | Owner | Plane | As-built status |
| --- | --- | --- | --- |
| `nanolink_tr069` | smo_sim `app/actuators/` | TR-069/CWMP device plane | IMPLEMENTED (E4.S2). The only key that can apply a change. |
| `o1_netconf` | smo_sim | NETCONF/YANG via the OCUDU `ocudu_netconf` companion | Declared placeholder (E4.S5). Restart semantics; maintenance-window track, never the live loop. |
| `ocudu_ws_collector` | smo_sim | data plane only, no apply | Implemented, gated off (E4.S5). `collect=True, apply=False`. |
| `open_mplane` | smo_sim | Open Fronthaul M-Plane | Declared placeholder (E4.S5). |
| `sas_domain_proxy` | smo_sim | CBRS SAS Domain Proxy | Models and state machine implemented (E4.S5); no certified SAS attached. |
| `nms_northbound` | smo_sim | third-party NMS northbound | Declared placeholder (E4.S5). |
| `a1_policy` | rapp `app/ric/` | A1-policy-aligned intents via the open non-RT RIC | IMPLEMENTED (E3.S3), live-verified against NONRTRIC A1-PMS 2.11.0. |
| `nearrt_xapp` | rapp `app/ric/adapters/nearrt/` | xApp-mediated control | RESERVED (E3.S7). Registration and lookup raise by default; frozen HLD v1.2 D5 activates it for LAB use only through an explicit `allow_reserved=True` opt-in used by EPIC-7. |

Two rules that fall out of the single namespace, both enforced in code:

1. **Executors skip foreign keys silently.** smo_sim's loop consumer commits and skips
   `a1_policy` and `nearrt_xapp`; the rApp's executor does the same for the six smo_sim keys.
   Both consume the whole topic in separate consumer groups, so without this filter every action
   would draw a spurious `rejected` feedback from the executor that does not own it, alongside the
   real feedback from the one that does. `rejected` therefore means "a key I own, or a key nobody
   owns", never "a key someone else owns".
2. **A reserved key is never emitted as a hint.** `target_adapter_hint` is validated against this
   namespace minus the reserved keys, so `nearrt_xapp` cannot reach a proposal.

Registry locations: `submodule/maveric_platform_smo_sim/app/actuators/registry.py`
(`SMO_ADAPTER_KEYS`, `FOREIGN_ADAPTER_KEYS`) and
`submodule/maveric_platform_rapp/app/ric/registry.py` (`ADAPTER_KEYS`,
`RESERVED_ADAPTER_KEYS`). Per-plane contracts live in `artifacts/actuation/`.

---

## 7. What this document does not cover

Per E0.S3 scope: no code change, no schema change, and no redefinition of frozen HLD §4 contracts
(topic names, API routes and table names are quoted verbatim from the frozen HLD). The `.context/`
graph refresh belongs to E6.
