# Multi-Tenancy Database Migrations

## Execution Order

Migrations must be applied in strict sequence. Each migration builds on the previous state.

### 001_multi_tenancy_schema.sql

Introduces core multi-tenancy schema changes.

**Changes:**
- ADD `tenant_memberships.email` (TEXT) — Email of user in tenant (API: user_email)
- UPDATE role constraint: `('cloudly_admin', 'tenant_admin', 'tenant_user')` — New three-role system
- ADD `tenants.auth_provider` (TEXT, default 'supabase') — Auth provider choice (for future Cognito support)
- ADD `tenants.auth_config` (JSONB) — Provider-specific configuration

**Purpose:** Establish schema foundation for multi-tenancy, new roles, and future auth provider flexibility.

---

### 002_migrate_roles.sql

Migrates existing user roles to new system.

**Changes:**
- `owner` → `tenant_admin` (tenant admin)
- `admin` → `tenant_admin` (tenant admin, merged with owner)
- `viewer` → `tenant_user` (regular user)

**Purpose:** Unify role system to three tiers (platform admin, tenant admin, tenant user).

**Note:** Platform admins (cloudly_admin) created separately in migration 003.

---

### 003_cloudlyio_org.sql

Creates CloudlyIO platform tenant and first platform admin.

**⚠️ MANUAL STEP REQUIRED BEFORE RUNNING:**

Edit this migration file and replace:
- `{PLATFORM_ADMIN_USER_ID}` with your platform admin's Supabase user UUID
- `{PLATFORM_ADMIN_EMAIL}` with platform admin email (e.g., `ahnaftanjid@cloudly.io`)

**Changes:**
- INSERT CloudlyIO tenant (UUID: `00000000-0000-0000-3029-000000000000`)
- INSERT first platform admin membership with role `cloudly_admin`

**Purpose:** Bootstrap platform admin capabilities. All subsequent platform admins added via API (POST /v1/admin/platform-admins).

---

### 004_email_unique_constraint.sql

Enforces email uniqueness within tenant scope.

**Changes:**
- ADD UNIQUE constraint: `UNIQUE(tenant_id, email)` on `tenant_memberships` (API: user_email)

**Purpose:** Enforce 1:1 email-to-tenant mapping (one email cannot belong to multiple tenants in MVP).

**Note:** Supports future multi-org per user when JWT structure expanded.

---

### 005_add_user_name_column.sql

Adds user display name column with safe migration pattern.

**Changes:**
- ADD `tenant_memberships.user_name` (TEXT) — User display name (API: user_name)
- Backfill with email prefix: `SPLIT_PART(email, '@', 1)` (e.g., `john@example.com` → `john`)
- Verify backfill succeeded (manual verification step required)
- SET NOT NULL constraint and create B-tree index

**Critical Points:**
- Uses 5-step safe migration: nullable → backfill → verify → NOT NULL → index
- Migration includes verification SQL script (lines 15-30)
- **MUST manually verify backfill before proceeding** (see Verification section below)

**Purpose:** Store user display name (Supabase user_metadata.full_name with email prefix fallback).

---

### 006_nybsys_ingestion.sql

Adds nybsys ingestion support — feature flag and upload-tracking table.

**Changes:**
- ADD `tenants.feature_flags` (JSONB, NULLABLE) — Per-tenant feature toggles
- CREATE TABLE `nybsys_uploads` — Tracks PM ingestion jobs (upload_id, status, file_count, file_names, date_range, etc.) with RLS policies
- Seeds `feature_flags = {"nybsys_ingestion": true}` for the Nybsys tenant (tenant_id placeholder — update before running)

**Purpose:** Enable feature-gated nybsys PM ingestion (SMO-2, ticket #88) and persist per-job ingestion state.

---

### 007_trial_org.sql

Adds trial-user role, trial signups table, and seeds the trial org.

**Changes:**
- UPDATE role constraint: adds `'trial_user'` to allowed roles on `tenant_memberships`
- CREATE TABLE `trial_signups` — Lead-capture record (email, name, phone, company, designation) — platform-scoped, no RLS
- INSERT trial tenant + first trial admin

**Purpose:** Bootstrap the self-service trial flow (issue #207); separates sales-pipeline lead data from auth-system tenant memberships.

---

### 008_nybsys_rng_seed.sql

Persists the RNG seed used by `run_pipeline()` so each ingestion job is reproducible.

**Changes:**
- ADD `nybsys_uploads.rng_seed` (INTEGER, NULLABLE) — pre-existing rows remain NULL

**Purpose:** Determinism for the nybsys normalization pipeline (#262); the seed used to drive stochastic guardrail + Approach C samplers is now stored alongside the upload record.

---

### 009_nybsys_nanolink.sql

Adds the NanoLink edge↔cloud control-plane tables (CloudlyNet × NybSys integration).

**Changes:**
- CREATE 7 tenant-scoped tables: `edge_devices`, `nanolink_devices`, `commands`, `device_config_snapshots`, `device_events`, `device_kpis`, `optimization_recommendations` — all with `FORCE` RLS (per-tenant isolation) + `updated_at` triggers
- ADD OD1 pre-auth `edge_devices_preauth_lookup` SELECT policy (Edge-Key → tenant resolution before the tenant GUC is set), `NULLIF`-guarded so an unset tenant yields zero rows rather than erroring

**Purpose:** Backing schema for the NanoLink control plane (agent enrollment, command queue, tiered telemetry, self-optimiser). Depends on `set_updated_at()` + pgcrypto (`gen_random_uuid`).

---

### 010_nybsys_cwmp_id_rename.sql

Renames the NanoLink device-id column after GenieACS was replaced by an in-agent TR-069/CWMP server.

**Changes:**
- RENAME `nanolink_devices.genieacs_id` → `cwmp_id` (+ rename the auto-named `UNIQUE (tenant_id, …)` constraint to match, via a dynamic `pg_constraint` lookup)
- DELETE the stale phantom un-escaped id row `8C1F64-ENB-N03002-B3-2205609999` (no-op if absent)

**Purpose:** GenieACS is gone (replaced by an in-agent CWMP server; issues #337/#338), so the field is renamed from a legacy misnomer to `cwmp_id`. The value is byte-identical — the agent computes the same canonical id — so this is a pure name fix + a one-row cleanup. Transaction-wrapped and idempotent-guarded; **apply as the DB owner/superuser** (the phantom `DELETE` is RLS-scoped under `nanolink_devices`' `FORCE` RLS). Depends on 009.

---

### 011_data_platform_canonical.sql

Creates the canonical PM/FM/CM data platform owned by `data_sim` (EPIC-1.S1, frozen HLD §4.3).

**Changes:**
- ADD `pm_measurements` — canonical PM counters, **RANGE-partitioned monthly on `ts`**, PK `(tenant_id, source, dn, metric, ts)` which doubles as the idempotency anchor; GIN index on `labels`
- ADD `ensure_pm_partition(timestamptz)` — creates the month's partition if missing **and applies ENABLE + FORCE RLS plus the tenant policy to it**, so a direct partition query cannot bypass isolation
- ADD `fm_alarms`, `cm_records`, `ingest_jobs` (tenant-scoped) and `vendor_dictionaries` (global)
- ADD ENABLE + FORCE RLS + `<table>_rls` policy on the four tenant-scoped tables; `vendor_dictionaries` deliberately gets none
- ADD `updated_at` trigger on `ingest_jobs`, reusing `set_updated_at()`
- PRE-CREATE the current and next month's partitions

**Purpose:** the platform had no canonical telemetry store; no PM counter ever landed in Postgres. This is also the first schema in the repo with a deterministic owner: `artifacts/design/internal-contracts.md` §1.1 documents that the gateway's `AutoMigrate` is disabled and its remaining DDL is `HasTable`-gated, so until now table shape depended on whichever service's `create_all` won the startup race.

**Note on `ensure_pm_partition`:** it is `SECURITY DEFINER` with `SET search_path = public, pg_temp`. Creating a partition requires `CREATE` on schema `public`, which unprivileged ingest roles must not hold; definer rights expose exactly that one operation instead. The pinned `search_path` is mandatory for any definer function. This deviates from the epic's DDL, which omitted both and therefore could not be called by a writer at all (verified: `ERROR: permission denied for schema public`).

**Source of truth:** generated from `submodule/maveric_platform_data_sim/alembic/versions/0001_data_platform_canonical.py`. Regenerate rather than hand-editing. Apply as the DB owner. Idempotent; verified applying twice to a fresh database.

---

### 012_drop_e2_r1.sql

Drops the dead E2/R1 REST facade tables (EPIC-4.S1, frozen HLD decision D4). Owned by `smo_sim`.

**Changes:**
- DROP the 7 `e2_*` tables: `e2_control_actions`, `e2_cell_configs`, `e2_topology`,
  `e2_ue_measurements`, `e2_cell_measurements`, `e2_subscriptions`, `e2_nodes`
- DROP the 4 `r1_*` tables: `r1_bootstrap_endpoints`, `r1_service_subscriptions`,
  `r1_service_discoveries`, `r1_service_publications`

**Purpose:** the facades were dead scaffolding. Neither was gateway-routed, the measurement tables
never received an insert from anywhere, control actions stayed permanently `pending`, and
subscriptions never notified. Deleting them also resolves claims-guardrails engineering blocker #2
(the `/etwoint` and `/roneint` route naming implied an O-RAN protocol implementation that does not
exist).

**Note:** these tables were only ever created by smo_sim's startup `create_tables(Base)`, never by a
migration, so a database whose smo_sim never booted will not have them. Every statement is
`IF EXISTS`, so the file is idempotent and safe on both. The ORM classes are deleted in the same
change, so startup cannot recreate them.

---

### 013_commands_loop_columns.sql

Correlates loop actions (`maveric.loop.action.v1`) with NanoLink commands (EPIC-4.S2/S3). Owned by
`smo_sim`.

**Changes:**
- ADD `commands.loop_action_id text` and `commands.policy_ref jsonb` — both nullable and additive,
  so the operator and agent paths are unchanged
- ADD partial unique index `commands_loop_action_uq` on `(loop_action_id)` WHERE
  `loop_action_id IS NOT NULL AND origin <> 'rollback'`

**Purpose:** the partial unique index is what makes an at-least-once Kafka redelivery idempotent —
`action_id` is globally unique, so a second attempt to execute the same action collides instead of
enqueuing a duplicate command. It excludes `origin = 'rollback'` on purpose: a rollback command
carries the `loop_action_id` of the action it reverts (so `command_service.complete()` can emit the
Appendix A.3 `kind="rollback"` feedback against the right action), which is a SECOND row with the
same `loop_action_id`. A global unique index would make rollback impossible.

`commands.origin` gains the value `'loop'` alongside the existing `manual|optimizer|healer|rollback`;
safe because the column carries no CHECK constraint (`009_nybsys_nanolink.sql:63`). Idempotent.

---

### 014_ndt_loop.sql

Network Digital Twin evaluation and closed-loop tables (EPIC-2, frozen HLD §A.6). Owned by
`bdt_engine`. Created by E2.S1; **extended in place** by E2.S4 (`ndt_feature_builds`,
`baselines.stats`), E2.S5 (`ndt_kpi_snapshots`), E2.S6 (`loop_policies`, `loop_actions`,
`loop_proposals`, `loop_feedback`), E2.S7 (the maintenance policy) and E2.S8
(`loop_actions.updated_by`). Append to it; do not add 014a/016.

**APPLYING IT IS A MANUAL STEP AND IS EASY TO MISS.** `docker-entrypoint-initdb.d` runs only on FIRST
cluster init, so a dev or lab stack whose volume predates any of these sections never receives them.
`artifacts/design/schemas.sql` inlines the tables for a fresh cluster, and the gateway re-applies the
loop RLS policies at boot (`submodule/maveric_platform_gateway/internal/db/migrate.go`) as a safety
net - but on an existing volume you must run this file yourself:

    docker exec -i postgres psql -U postgres -d maveric -v ON_ERROR_STOP=1 < artifacts/migration/014_ndt_loop.sql

It is idempotent and safe to re-run.

**Changes (E2.S7 section — the maintenance policy):**
- ADD `loop_actions_maintenance_rls` and `loop_feedback_maintenance_rls`, permitting rows when
  `current_setting('app.maintenance', true) = 'on'`
- WHY: the clock-driven watch sweep has no tenant to pin and cannot enumerate tenants, because every
  table that would tell it is itself RLS-forced. Running with NO tenant GUC does not bypass the tenant
  policy - it FAILS it, matching zero rows on a fresh connection and raising
  `invalid input syntax for type uuid: ""` on a pooled one (Postgres resets a custom GUC to the empty
  string, not NULL). Without this policy the sweep is a permanent silent no-op under any
  non-superuser role
- NOTE: this weakens nothing. A client that can set `app.maintenance` can already set
  `app.current_tenant` to any value, so the isolation boundary was never the GUC - it is the
  application. The gain is that the maintenance path is DECLARED rather than depending on the
  connecting role being a superuser

**Changes (E2.S8 section):**
- ADD `loop_actions.updated_by uuid` — who approved or rejected. Nullable because nothing forwards an
  operator identity yet (the gateway has no `X-User-Id` header)

**Changes (E2.S1 section):**
- ADD `ndt_evaluation_runs` — one row per evaluation, keyed `UNIQUE (tenant_id, db_key)` where
  `db_key` derives from the deterministic `run_id` (uuid5 over tenant + bdt + baseline + dataset +
  scope + canonical-JSON hashes of cell_configs and options). That uniqueness is what makes a
  repeated identical evaluation a cache hit rather than a second twin run
- ADD `idx_ndt_eval_tenant (tenant_id, created_at DESC)` for the per-tenant recent-runs listing
- ADD ENABLE + FORCE RLS + `ndt_evaluation_runs_rls`
- ADD `updated_at` trigger, reusing `set_updated_at()`

**Purpose:** twin evaluation moved out of `rapp` into `bdt_engine`, where the model pickles are
native (see the pickle-compat rule below). Day-scope evaluation is asynchronous — up to 24 twin
passes — so it needs a durable run record to poll against; tick scope is synchronous and writes the
row only for history.

**Note on `result`:** persisted **without** `raw_tick_data`. That section is the bulk of a day
result (24 ticks of per-UE arrays), is reproducible from the same inputs, and would bloat the row
for no recovery value. Consequence, and it is load-bearing for callers: a **cache hit returns
aggregates only**, so a request asking for raw arrays deliberately bypasses the cache rather than
being served a stripped result.

**Note on RLS:** `ENABLE` alone is insufficient — the table owner bypasses the policy. Every writer
must `SET LOCAL app.current_tenant` inside its transaction; without it the policy compares against
NULL and the `WITH CHECK` rejects the write.

**Changes (E2.S5 section):**
- ADD `ndt_kpi_snapshots` — one KPI snapshot per completed evaluation, so history survives cache
  eviction and E2.S6's decision hub has an audit record per gate decision
- `UNIQUE (tenant_id, run_id, source)` — `source` is `evaluate` or `loop_gate`, and it is part of the
  key on purpose: the same run scored by the loop gate is a distinct observation from the same run
  scored directly. The writer upserts, so a genuine re-run refreshes rather than duplicates
- ADD `idx_ndt_kpi_tenant_time` and `idx_ndt_kpi_bdt_time (tenant_id, bdt_id, created_at DESC)`, the
  latter because trend queries filter by model then order by time
- ADD ENABLE + FORCE RLS + `ndt_kpi_snapshots_rls`. **The epic's S5 DDL block omitted RLS entirely**
  while its own acceptance criteria require it, so it is added here rather than assumed
- **No `updated_at` trigger, deliberately.** A snapshot is an immutable observation; this table is
  therefore absent from the `updated_at` trigger array in `schemas.sql`, unlike every other table here

**Note on `semi_synthetic`:** populated from `baselines.stats ->> 'semi_synthetic'` — a column
**E2.S4 adds**. The writer probes `information_schema` first and defaults to `false` when the column
is absent, which is what keeps S4 and S5 genuinely parallelizable; a bare `stats ->> ...` against a
database without the column is an `UndefinedColumn` error, not a NULL. False is the safe default:
claiming synthetic data is real would be a claims-guardrails problem, the reverse is conservative.

**Source of truth:** the DDL here is canonical, and the same statements are inlined into
`artifacts/design/schemas.sql` for fresh installs. `bdt_engine` has no Alembic tree, so unlike 011
this file is hand-maintained rather than generated. Idempotent; verified applying twice to a fresh
database, and verified `forced=true` afterwards for both tables.

**Retention:** none of these tables has a retention job. `ndt_kpi_snapshots` grows one row per
evaluation per source and is the one most likely to need one; recorded here rather than implemented,
per E2.S5's stated scope.

---

### 015_ndt_loop_policy.sql

Network Digital Twin closed-loop policy: per-tenant default seeding into E2's `loop_policies`
(EPIC-5.S6, frozen HLD §4.2). **SEED-ONLY — contains no DDL.** Apply after `014_ndt_loop.sql`,
which creates the table.

**Changes:**
- INSERT one `loop_policies` row per row in `tenants`: `mode='approval'`,
  `guardrails = {"min_sinr_db": 0, "min_rrc_success_pct": 95, "max_outage_rate": 0.05}`,
  `watch_window_min = 15`. `ON CONFLICT (tenant_id) DO NOTHING`, so it is idempotent

**Purpose:** the decision hub treats a missing policy row as `mode='off'` and fails closed, so
without this seed the first loop pass for an existing tenant is a silent no-op. The guardrails
mirror smo_sim's device-level `GUARD` constants
(`app/services/nybsys/self_optimizer.py:32`) so the NDT KPI watch and the device-level watcher
agree rather than argue. `min_sinr_db = 0` is the placeholder floor pending RF sign-off (smo_sim
OD4).

**It never seeds `auto`.** Seeded `approval` changes nothing behaviorally until an operator (or the
demo script) opts a tenant in. 014's column default stays `'off'` deliberately — the safe-onboarding
value is seeded per row, never baked into the DDL. Tenants created later get their row lazily on the
first policy read/write, because `PUT /ndt/loop/policy` upserts.

**Run it as a superuser** (or a `BYPASSRLS` role) — and the file now enforces that itself. `tenants`
carries FORCE RLS, so under any other role the source `SELECT` sees only the tenants matching
`app.current_tenant` (none, when it is unset). The seed would then report `INSERT 0 0` and exit 0,
indistinguishable from a successful idempotent re-run — silence, not an error. Verified by running
it as a plain role: it seeded nothing and raised nothing. A guard block at the top of the file now
converts that into an explicit `RAISE EXCEPTION`; it is procedural, not DDL.

Rollback = `DELETE FROM public.loop_policies` for the seeded rows; never drop the table here, it is
E2's. Note that `ON CONFLICT DO NOTHING` also means the seed never overwrites a policy an operator
has already set — including one already flipped to `auto`.

---

### 016_pm_ts_browse_index.sql

Browse index for keyset pagination on `GET /v1/tenants/{tid}/data/pm` (EPIC-11 A4). Owned by
`data_sim`.

**Changes:**
- ADD partitioned btree index `idx_pm_tenant_ts_dn_metric` on
  `pm_measurements (tenant_id, ts, dn, metric)`

**Purpose:** the PM read API now orders by the fully deterministic sort key
`(ts, dn, metric, source)` and continues pages with a row-value predicate (`cursor` /
`next_cursor`) instead of OFFSET. The existing indexes lead with `metric`/`dn`, so an unfiltered
time-ordered browse had no usable index. Creating the index on the partitioned parent cascades to
every existing partition; partitions created later by `ensure_pm_partition()` attach it
automatically.

**Source of truth:** generated from
`submodule/maveric_platform_data_sim/alembic/versions/0003_pm_ts_browse_index.py`. Regenerate
rather than hand-editing. Idempotent (`CREATE INDEX IF NOT EXISTS`).

---

### 017_fm_alarms_lifecycle_columns.sql

The seven `fm_alarms` lifecycle columns the platform's contracts already documented but which were
never created (EPIC-8). Owned by `data_sim`.

**Changes:**
- ADD `vendor`, `module`, `kind`, `specific_problem`, `source_ref`, `last_seen_at` (nullable) and
  `occurrence_count` (`integer NOT NULL DEFAULT 1`) to `public.fm_alarms`, with column comments
- ADD btree index `(tenant_id, state, occurrence_count DESC)` for "which alarms are storming"
- BACKFILL the seven from the `raw` JSONB where it holds them, defaulting `last_seen_at` to
  `raised_at`

**Purpose:** `fm_alarms` collapses flap and backoff series into one row plus a count, and
`occurrence_count` is what separates a single fault from a 31-line retry storm. The API schema
exposed 8 of the columns and the table only had 10, so a consumer could not tell them apart — the
copilot reported `occurrence_count: 1` for a 31-line ACS storm.

**The backfill is load-bearing, not cosmetic.** Rows written before this migration could only carry
these values inside `raw`. Once the column exists a reader prefers the column, so a defaulted `1`
silently shadows a truthful `31` — the storm went from reporting 31 to reporting 1, which is worse
than before because it now looks authoritative.

**Prerequisite:** `011_data_platform_canonical.sql`, which creates `fm_alarms`.

**Source of truth:** generated from
`submodule/maveric_platform_data_sim/alembic/versions/0004_fm_alarms_lifecycle_columns.py`.
Regenerate rather than hand-editing. Idempotent (`ADD COLUMN IF NOT EXISTS`, and the backfill only
touches rows still at the default); verified by running the full `0001→0004` chain against a database
that already had the columns applied by hand.

---

### cognito.sql  (standalone / auxiliary — not in the numbered sequence)

Flips `tenants.auth_provider` default to `cognito` and backfills existing rows (adds `auth_config`
JSONB). Idempotent — safe to run multiple times. It is already inlined into the fresh-install
baseline (`artifacts/design/schemas.sql`), so run it only to migrate an **existing** install off the old
`supabase` default. Folded here from the former top-level `dbmigration/`.

> **Baselines & archived seeds.** Fresh installs use the canonical `artifacts/design/schemas.sql`. The older
> partial baseline `init.sql` and the one-off `PROD → LOCAL` `alter.sql` are archived under
> `artifacts/legacy/sql/`. Copilot DB bootstrap (`artifacts/db/init_copilot*.sql`,
> `init_copilot_databases.sh`) is a separate rollout, deferred for convergence — see
> `artifacts/marketing/roadmap.md`.

---

## Verification

After all migrations complete, verify schema and data:

### Schema Verification

```sql
-- Check tenant_memberships schema
\d tenant_memberships

-- Expected columns:
-- - tenant_id (uuid)
-- - user_id (uuid)
-- - email (text)
-- - user_name (text) ← NEW in 005
-- - role (text) ← VALUES: cloudly_admin, tenant_admin, tenant_user
-- - status (text)
-- - joined_at (timestamp)

-- Check role values
SELECT DISTINCT role FROM tenant_memberships;
-- Expected: cloudly_admin, tenant_admin, tenant_user

-- Check indexes
\d tenant_memberships
-- Expected: PRIMARY KEY (tenant_id, user_id), UNIQUE (tenant_id, email), INDEX (tenant_id, user_name)
```

### Data Verification

```sql
-- Check CloudlyIO org exists
SELECT tenant_id, name, status FROM tenants
WHERE tenant_id = '00000000-0000-0000-3029-000000000000';

-- Expected: 1 row with name 'CloudlyIO' (or your custom name)

-- Check platform admin
SELECT user_id, email, user_name, role FROM tenant_memberships
WHERE tenant_id = '00000000-0000-0000-3029-000000000000'
AND role = 'cloudly_admin';

-- Expected: 1 row with your platform admin email and role 'cloudly_admin'

-- Check user_name backfill
SELECT COUNT(*) AS total,
       COUNT(CASE WHEN user_name = '' THEN 1 END) AS empty,
       COUNT(CASE WHEN user_name IS NULL THEN 1 END) AS null_count
FROM tenant_memberships;

-- Expected: empty = 0, null_count = 0 (all users have user_name)
```

---

## Rollback

**Not supported.** Migrations are destructive and cannot be safely rolled back:
- Migration 002 changes existing role values (cannot reverse without knowing original intent)
- Migration 003 creates bootstrap org (cannot safely delete)
- Migration 004 adds unique constraint (cannot reverse without potential data conflicts)

**Before running migrations:** Backup your database.

```bash
# PostgreSQL backup
pg_dump -U postgres -h localhost maveric_db > backup_before_migrations.sql

# Restore if needed
psql -U postgres -h localhost maveric_db < backup_before_migrations.sql
```

---

## Execution Steps

### 1. Backup Database

```bash
pg_dump -U postgres -h localhost maveric_db > maveric_backup_$(date +%Y%m%d_%H%M%S).sql
```

### 2. Edit migration 003 (Manual Step)

Open `003_cloudlyio_org.sql` and replace:
```sql
-- BEFORE:
INSERT INTO tenant_memberships (tenant_id, user_id, email, user_name, role, status)
VALUES ('00000000-0000-0000-3029-000000000000', '{PLATFORM_ADMIN_USER_ID}', '{PLATFORM_ADMIN_EMAIL}', ...);

-- AFTER (example):
INSERT INTO tenant_memberships (tenant_id, user_id, email, user_name, role, status)
VALUES ('00000000-0000-0000-3029-000000000000', 'd11799d4-81f4-4aaf-8674-231517d43682', 'ahnaftanjid@cloudly.io', ...);
```

### 3. Run Migrations in Sequence

Via Supabase SQL Editor or psql:

```bash
# Migration 001
psql -U postgres -h localhost maveric_db < artifacts/migration/001_multi_tenancy_schema.sql

# Migration 002
psql -U postgres -h localhost maveric_db < artifacts/migration/002_migrate_roles.sql

# Migration 003 (after manual edit)
psql -U postgres -h localhost maveric_db < artifacts/migration/003_cloudlyio_org.sql

# Migration 004
psql -U postgres -h localhost maveric_db < artifacts/migration/004_email_unique_constraint.sql

# Migration 005
psql -U postgres -h localhost maveric_db < artifacts/migration/005_add_user_name_column.sql
```

### 4. Verify All Migrations

Run verification queries above to confirm schema and data integrity.

### 5. Restart Gateway Service

```bash
# Docker
docker restart maveric_gateway

# Or rebuild & run
cd submodule/maveric_platform_gateway && docker build -t gateway . && docker run -p 8080:8080 --env-file .env gateway
```

---

## Troubleshooting

### Migration 005 Verification Fails

If `user_name` has empty strings after backfill:

```sql
-- Find problematic rows
SELECT user_id, email, user_name FROM tenant_memberships
WHERE user_name = '' OR user_name IS NULL;

-- Manually fix
UPDATE tenant_memberships
SET user_name = SPLIT_PART(email, '@', 1)
WHERE user_name = '' OR user_name IS NULL;

-- Re-run verification
SELECT COUNT(CASE WHEN user_name = '' THEN 1 END) FROM tenant_memberships;
-- Should return 0
```

### Role Constraint Violation

If migration 002 fails with constraint violation (old role values):

```sql
-- Check remaining old roles
SELECT DISTINCT role FROM tenant_memberships;

-- Manually migrate any stragglers
UPDATE tenant_memberships SET role = 'tenant_admin' WHERE role IN ('owner', 'admin');
UPDATE tenant_memberships SET role = 'tenant_user' WHERE role = 'viewer';

-- Re-run migration 002
```

### Email Uniqueness Constraint Violation

If migration 004 fails due to duplicate (tenant_id, email):

```sql
-- Find duplicates
SELECT tenant_id, email, COUNT(*)
FROM tenant_memberships
GROUP BY tenant_id, email
HAVING COUNT(*) > 1;

-- Decide which row to keep (typically most recent)
-- DELETE or UPDATE older rows, keeping one per (tenant_id, email)

-- Re-run migration 004
```

---

## Post-Migration Configuration

After migrations, configure gateway environment variables:

```bash
# .env for gateway

# CloudlyIO platform org UUID (from migration 003)
CLOUDLYIO_ORG_UUID=00000000-0000-0000-3029-000000000000

# Platform admin email for deletion protection
CLOUDLY_ADMIN_EMAIL=ahnaftanjid@cloudly.io

# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJhbGc...

# Database
POSTGRES_DSN=postgresql://user:password@host:5432/maveric_db
```

Restart gateway to load new environment variables.

---

## Reference

- **Schema Changes:** See `artifacts/design/schemas.sql` for the full canonical schema
- **API Documentation:** See `artifacts/design/LLD.md` (multi-tenancy / RLS) and `artifacts/design/openapi.yaml`
- **Testing:** See `test/README_Postman.md` for the current Postman collection
