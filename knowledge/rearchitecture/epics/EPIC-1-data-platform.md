# EPIC 1: Data Platform (data_sim = ingestion + canonical store)

**Epic ID:** E1
**Title:** Data Platform: canonical PM/FM/CM schema, ingestion framework, NanoLink store-only adapter, ingest API move
**Depends on:** E0 (gateway duplicate-route panic fix + the `/custom/nybsys/uploads*` -> DATA route split + `/ingest/**`, `/data/**` -> DATA route registration)
**Frozen HLD:** `docs/task_docs/cloudlynet-rearchitecture/01-hld-frozen.md` (conform to §3 hard constraints and §4.3 exactly)

**Goal.** Turn `maveric_platform_data_sim` into the Data Platform service (frozen HLD D3): per-vendor ingestion adapters write canonical PM/FM/CM rows to Postgres (raw payloads stay in S3), driven by durable Kafka-backed ingest jobs on `maveric.ingest.pm.v1` consumed by a background thread inside the existing data_sim API container. The NybSys NanoLink PM CSV upload endpoint moves from smo_sim to data_sim with a byte-compatible public contract, becomes store-only (stages 1-2 of the old pipeline), and hands semi-synthetic enrichment to the NDT twin feature builder via an explicit, feature-flagged seam (built in E2; a transitional inline builder preserves today's behavior until then). The synthetic data factory (`/utils/**`) is untouched.

**Definition of done (epic).**
- `pm_measurements` (monthly-partitioned), `fm_alarms`, `cm_records`, `ingest_jobs`, `vendor_dictionaries` exist with FORCE RLS, created by a real alembic migration in data_sim, mirrored in `artifacts/design/schemas.sql` and `artifacts/migration/011_data_platform_canonical.sql`.
- `POST /v1/tenants/{t}/ingest/uploads` + `GET /v1/tenants/{t}/ingest/jobs/{id}` live; jobs ride `maveric.ingest.pm.v1`; a data_sim pod restart mid-job never leaves a permanently stuck job (Kafka redelivery + idempotent terminal-skip replaces the smo_sim thread-pool durability gap).
- The consumer also stores `kind="records"` inline batches (HLD Appendix A.5; producer: E4's OCUDU collector today; `nearrt_kpm_stream` is RESERVED for the deferred near-RT track) directly into `pm_measurements` via the E1.S8 branch.
- A NybSys PM CSV upload through the **unchanged** `POST /v1/tenants/{t}/custom/nybsys/uploads` contract produces: canonical `pm_measurements` rows (dictionary-mapped metric names), raw CSVs + `pm_hourly.csv` audit in S3 at today's keys, and (via the builder seam) the same `baselines` + `ue_datasets` artifacts the frontend/BDT/rApp consume today. Frontend requires zero changes.
- `GET /v1/tenants/{t}/data/pm|fm|cm` query APIs live with dn/metric/time filters.
- Future-adapter registry stubs (`3gpp_xml_pm`, `ves_listener`, `ocudu_ws`) + contract docs exist; posting them returns a clean 422.
- Cutover runbook executed in lab: gateway re-pointed, smo_sim upload router/runner decommission plan written, backfill script available.
- Zero CI/CD change: no new containers/charts/images/ports; consumer runs inside the data_sim API process; new topic rides the existing topics-job/`init-topics.sh`.

**Recon evidence used:** data_sim has NO Kafka wiring today (`app/event_handlers/kafka_handler.py` is dead code, `UTILS_KAFKA_TOPIC` referenced by nothing) and no alembic versions dir (`alembic/` holds only `env.py`, which imports a broken `sqlalchemy.ext.asyncio.async_engine` and the example Base). The NybSys pipeline lives in smo_sim (`app/lib/nybsys/pipeline.py`, `app/services/nybsys_runner.py` ThreadPoolExecutor(max_workers=2), `app/api/v1/custom/nybsys/router.py`). Gateway maps `/custom/**` -> SMO and `/utils/**` -> DATA (`cmd/gateway/main.go:224-234`).

---

## E1.S1: Canonical PM/FM/CM schema + ingest_jobs + vendor_dictionaries (alembic, RLS, monthly partitions)

**Why.** The platform has no canonical telemetry store: no PM counter ever lands in Postgres today (S3 audit CSV only). Frozen HLD §4.3 makes data_sim the owner of the canonical schema; everything else in this epic writes to or reads from these tables.

**Size:** M

**Scope**
- In: alembic bootstrap for data_sim (fix `env.py`, create `alembic/versions/`), revision `0001_data_platform_canonical` creating the five tables + RLS + partition helper; update `artifacts/design/schemas.sql`; add `artifacts/migration/011_data_platform_canonical.sql` mirror + README entry; add the five canonical tables to the gateway's boot-time RLS re-application list (`submodule/maveric_platform_gateway/internal/db/migrate.go:323-334`) so dev stacks get RLS even when tables were created outside the migration path (`pm_measurements` partitions are covered by `ensure_pm_partition()`, which must apply the policy per partition).
- Out: any data writes (S2/S3), dictionary seed rows (S3), query endpoints (S5), gateway changes (E0).

**Files**
- `submodule/maveric_platform_data_sim/alembic/env.py` (modify: sync engine, remove broken `from sqlalchemy.ext.asyncio import async_engine` import; `target_metadata = None`, migrations are hand-written DDL)
- `submodule/maveric_platform_data_sim/alembic/versions/__init__.py` (create dir; alembic does not need the `__init__.py` but keep the dir committed via the revision file itself)
- `submodule/maveric_platform_data_sim/alembic/versions/0001_data_platform_canonical.py` (create)
- `submodule/maveric_platform_data_sim/alembic.ini` (verify `script_location = alembic`; no functional change expected)
- `artifacts/design/schemas.sql` (modify: append tables + extend the RLS DO-block list at lines ~475-497)
- `artifacts/migration/011_data_platform_canonical.sql` (create: manual-execution mirror of the alembic DDL)
- `artifacts/migration/README.md` (modify: add 011 entry to the execution index)

**Contract** (SQL DDL; §4.3 columns are verbatim, keys/indexes/partitioning are this epic's detail)

```sql
-- Canonical PM measurements: monthly range partitions on ts.
-- Canonical vocabulary: TS 28.552 measurement names where mappable, else 'vendor:<name>'.
CREATE TABLE IF NOT EXISTS public.pm_measurements (
  tenant_id      uuid NOT NULL,
  source         text NOT NULL,                 -- adapter source_type, e.g. 'nybsys_pm_csv'
  vendor         text NOT NULL,                 -- e.g. 'nybsys'
  dn             text NOT NULL,                 -- 'site=<site_id>,cell=<cell_id>' (convention doc: artifacts/data-platform/canonical-schema.md)
  metric         text NOT NULL,
  value          double precision NOT NULL,
  unit           text,
  granularity_s  integer NOT NULL,
  ts             timestamptz NOT NULL,
  day            integer,                       -- 0-based dataset-relative day index (nullable for streaming sources)
  tick           integer,                       -- hour 0..23 (nullable for streaming sources)
  labels         jsonb NOT NULL DEFAULT '{}'::jsonb,
  raw_ref        text,                          -- S3 key of the raw/audit artifact this row derives from
  PRIMARY KEY (tenant_id, source, dn, metric, ts)   -- includes partition key; idempotency anchor
) PARTITION BY RANGE (ts);

CREATE INDEX IF NOT EXISTS idx_pm_tenant_metric_ts ON public.pm_measurements (tenant_id, metric, ts);
CREATE INDEX IF NOT EXISTS idx_pm_tenant_dn_ts     ON public.pm_measurements (tenant_id, dn, ts);
CREATE INDEX IF NOT EXISTS idx_pm_labels           ON public.pm_measurements USING gin (labels);

-- Monthly partition creator. Writers call this before batch insert (create-if-missing);
-- it also applies ENABLE+FORCE RLS and the tenant policy to the new partition so a direct
-- partition query can never bypass isolation.
CREATE OR REPLACE FUNCTION public.ensure_pm_partition(p_ts timestamptz) RETURNS void
LANGUAGE plpgsql AS $$
DECLARE
  p_start date := date_trunc('month', p_ts)::date;
  p_end   date := (date_trunc('month', p_ts) + interval '1 month')::date;
  p_name  text := format('pm_measurements_y%sm%s', to_char(p_start, 'YYYY'), to_char(p_start, 'MM'));
BEGIN
  EXECUTE format(
    'CREATE TABLE IF NOT EXISTS public.%I PARTITION OF public.pm_measurements FOR VALUES FROM (%L) TO (%L);',
    p_name, p_start, p_end);
  EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY;', p_name);
  EXECUTE format('ALTER TABLE public.%I FORCE ROW LEVEL SECURITY;', p_name);
  EXECUTE format('DROP POLICY IF EXISTS %I_rls ON public.%I;', p_name, p_name);
  EXECUTE format($fmt$
    CREATE POLICY %1$s_rls ON public.%1$s
    AS PERMISSIVE FOR ALL TO public
    USING (tenant_id = (current_setting('app.current_tenant', true))::uuid)
    WITH CHECK (tenant_id = (current_setting('app.current_tenant', true))::uuid)
  $fmt$, p_name);
END $$;

CREATE TABLE IF NOT EXISTS public.fm_alarms (
  tenant_id      uuid NOT NULL,
  source         text NOT NULL,
  dn             text NOT NULL,
  alarm_id       text NOT NULL,
  severity       text NOT NULL,                 -- critical|major|minor|warning|indeterminate|cleared
  probable_cause text,
  raised_at      timestamptz NOT NULL,
  cleared_at     timestamptz,
  state          text NOT NULL DEFAULT 'active',  -- active|cleared
  raw            jsonb NOT NULL DEFAULT '{}'::jsonb,
  PRIMARY KEY (tenant_id, source, dn, alarm_id, raised_at)
);
CREATE INDEX IF NOT EXISTS idx_fm_tenant_state_raised ON public.fm_alarms (tenant_id, state, raised_at);

CREATE TABLE IF NOT EXISTS public.cm_records (
  tenant_id      uuid NOT NULL,
  source         text NOT NULL,
  dn             text NOT NULL,
  params         jsonb NOT NULL,
  captured_at    timestamptz NOT NULL,
  origin         text,                          -- 'ingest'|'read_back'|'operator'
  PRIMARY KEY (tenant_id, source, dn, captured_at)
);
CREATE INDEX IF NOT EXISTS idx_cm_tenant_dn_captured ON public.cm_records (tenant_id, dn, captured_at);

-- Durable replacement for the smo_sim ThreadPoolExecutor: one row per ingest job.
CREATE TABLE IF NOT EXISTS public.ingest_jobs (
  tenant_id    uuid NOT NULL,
  job_id       text NOT NULL,
  source_type  text NOT NULL,
  status       text NOT NULL DEFAULT 'queued',  -- queued|running|completed|failed
  stats        jsonb NOT NULL DEFAULT '{}'::jsonb,
  error        text,
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, job_id)
);
CREATE INDEX IF NOT EXISTS idx_ingest_jobs_status ON public.ingest_jobs (tenant_id, status, updated_at);

-- Global (NOT tenant-scoped, NO RLS) vendor->canonical metric mapping. Read-only at runtime.
CREATE TABLE IF NOT EXISTS public.vendor_dictionaries (
  vendor           text NOT NULL,
  source_metric    text NOT NULL,
  canonical_metric text NOT NULL,
  transform        text NOT NULL DEFAULT 'identity',  -- 'identity' | 'scale:<factor>'
  unit             text,
  PRIMARY KEY (vendor, source_metric)
);
```

RLS: add `'pm_measurements','fm_alarms','cm_records','ingest_jobs'` to the existing enable+force RLS DO-block table list in `artifacts/design/schemas.sql` (the block at the end of the file); the alembic revision executes the equivalent `ENABLE/FORCE ROW LEVEL SECURITY` + `CREATE POLICY <t>_rls` statements inline for the four tenant tables (policy body identical to the existing block: `USING (tenant_id = (current_setting('app.current_tenant', true))::uuid)` with matching `WITH CHECK`). `vendor_dictionaries` gets **no** RLS (global). Add `'ingest_jobs'` to the `set_updated_at` trigger DO-block list as well. The revision also pre-creates partitions for the current and next month via `SELECT public.ensure_pm_partition(now()); SELECT public.ensure_pm_partition(now() + interval '1 month');`.

**Key snippets**

`alembic/versions/0001_data_platform_canonical.py` skeleton:

```python
"""data platform canonical schema

Revision ID: 0001_data_platform_canonical
Revises:
"""
from __future__ import annotations

from alembic import op

revision = "0001_data_platform_canonical"
down_revision = None

def upgrade() -> None:
    op.execute(DDL)          # the full SQL block above, one op.execute per statement group
    op.execute(RLS_DDL)      # enable+force+policy for the 4 tenant tables
    op.execute("SELECT public.ensure_pm_partition(now());")
    op.execute("SELECT public.ensure_pm_partition(now() + interval '1 month');")

def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS public.pm_measurements CASCADE;")
    op.execute("DROP TABLE IF EXISTS public.fm_alarms;")
    op.execute("DROP TABLE IF EXISTS public.cm_records;")
    op.execute("DROP TABLE IF EXISTS public.ingest_jobs;")
    op.execute("DROP TABLE IF EXISTS public.vendor_dictionaries;")
    op.execute("DROP FUNCTION IF EXISTS public.ensure_pm_partition(timestamptz);")
```

`alembic/env.py` fix (sync only):

```python
from sqlalchemy import create_engine, pool
# delete: import asyncio / from sqlalchemy.ext.asyncio import async_engine / example Base import
target_metadata = None  # hand-written DDL migrations; no autogenerate

def run_migrations_online() -> None:
    connectable = create_engine(get_url(), poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
```

**Acceptance criteria**
- `uv run alembic upgrade head` against a fresh lab Postgres creates all five tables, the partition function, two monthly partitions, and RLS policies; `uv run alembic downgrade base` removes them.
- With `SET app.current_tenant = '<uuid-A>'`, inserts/selects on `pm_measurements` for tenant B return 0 rows / fail the WITH CHECK (verified via psql as the non-superuser app role).
- Inserting a row whose `ts` falls in a month with no partition fails; after `SELECT ensure_pm_partition(ts)` it succeeds (writers own partition creation).
- `artifacts/design/schemas.sql` applied to an empty DB is idempotent and equivalent (CREATE IF NOT EXISTS discipline preserved); `artifacts/migration/011_data_platform_canonical.sql` matches the alembic DDL statement-for-statement.
- No em dash characters in any touched artifacts/ file.

**Test plan**
- Unit (data_sim, `uv run pytest`): `tests/test_canonical_schema.py`: partition-name computation for edge months (Dec->Jan), DDL string constants compile (sqlparse or simple execute against a dockerized pg if available in lab; else assert statement inventory).
- Integration (lab, compose infra up): apply alembic, run the RLS matrix above via a fixture using two tenant UUIDs; verify `\d+ pm_measurements` shows RANGE partitioning.

**Coding-agent prompt**

```
You are working in the CloudlyNet monorepo (repo root: cloudlynet_ai). Read
docs/task_docs/cloudlynet-rearchitecture/01-hld-frozen.md first; you are implementing story E1.S1
of EPIC-1 (docs/task_docs/cloudlynet-rearchitecture/epics/EPIC-1-data-platform.md), section E1.S1.

TASK: Create the canonical Data Platform schema owned by data_sim.
1) In submodule/maveric_platform_data_sim: fix alembic/env.py (pure sync SQLAlchemy engine,
   remove the broken `from sqlalchemy.ext.asyncio import async_engine` and the example Base
   import; target_metadata=None), create alembic/versions/, add revision
   0001_data_platform_canonical implementing EXACTLY the DDL in the epic file's E1.S1 Contract
   section: pm_measurements (RANGE-partitioned monthly on ts, PK (tenant_id,source,dn,metric,ts)),
   ensure_pm_partition() function (creates partition + RLS on it), fm_alarms, cm_records,
   ingest_jobs, vendor_dictionaries (global, NO RLS), indexes, ENABLE+FORCE RLS + <table>_rls
   policies on the 4 tenant tables (policy body copied from artifacts/design/schemas.sql's
   existing RLS DO block), pre-create current+next month partitions, updated_at trigger for
   ingest_jobs reusing set_updated_at(). Provide a working downgrade.
2) Update artifacts/design/schemas.sql: append the same tables/function/indexes and add the four
   tenant table names to the existing RLS DO-block list and ingest_jobs to the updated_at
   trigger list. Keep CREATE IF NOT EXISTS idempotency style.
3) Create artifacts/migration/011_data_platform_canonical.sql mirroring the DDL for manual
   execution, and add a 011 entry to artifacts/migration/README.md following the existing format.
CONSTRAINTS: cd into the submodule before any git op. tenant_id is uuid everywhere. Do not touch
any existing table. No new services/ports/images. Never use the em dash character in artifacts/
files. Follow CLAUDE.md conventions (type hints, one-line docstrings).
DONE WHEN: `uv run alembic upgrade head && uv run alembic downgrade base && uv run alembic
upgrade head` succeeds against the compose Postgres (scripts/kafka/compose.sh infra), the RLS
isolation matrix in the epic's E1.S1 acceptance criteria passes, and `uv run pytest` passes in
the data_sim submodule.
```

---

## E1.S2: Ingestion framework: SourceAdapter protocol, dictionary mapper, Kafka-backed ingest jobs, ingest API

**Why.** Replaces the smo_sim in-process ThreadPoolExecutor (jobs lost on restart, rows stuck `processing`) with a durable Kafka job flow, and gives every future vendor source one pluggable entry point. data_sim's Kafka handlers are dead code today; this story wires them for real.

**Size:** L

**Scope**
- In: `app/ingest/` package (protocol, registry, dictionary mapper, service, consumer thread), `app/db/ingest_repo.py` (jobs CRUD + canonical batch writers), producer publish on `maveric.ingest.pm.v1`, `POST /v1/tenants/{t}/ingest/uploads` + `GET /v1/tenants/{t}/ingest/jobs/{id}`, config additions, topic in `scripts/kafka/init-topics.sh`, scale-out documentation.
- Out: any concrete adapter (S3 = NanoLink, S6 = stubs), legacy `/custom` route (S4), query APIs (S5). No changes to `/utils/**` generators. No new deployable: the consumer is a daemon thread in the API process.

**Files**
- `submodule/maveric_platform_data_sim/app/ingest/__init__.py` (create)
- `submodule/maveric_platform_data_sim/app/ingest/models.py` (create: Pydantic contracts)
- `submodule/maveric_platform_data_sim/app/ingest/adapters/__init__.py` (create)
- `submodule/maveric_platform_data_sim/app/ingest/adapters/base.py` (create: `SourceAdapter` protocol, `ParseResult`)
- `submodule/maveric_platform_data_sim/app/ingest/registry.py` (create)
- `submodule/maveric_platform_data_sim/app/ingest/dictionary.py` (create: vendor_dictionaries mapper)
- `submodule/maveric_platform_data_sim/app/ingest/service.py` (create: job orchestration)
- `submodule/maveric_platform_data_sim/app/ingest/consumer.py` (create: background consumer thread)
- `submodule/maveric_platform_data_sim/app/db/ingest_repo.py` (create: raw SQL, `SET LOCAL app.current_tenant` pattern copied from `app/db/baseline_repo.py`)
- `submodule/maveric_platform_data_sim/app/api/v1/endpoints/ingest.py` (create)
- `submodule/maveric_platform_data_sim/app/api/v1/routes.py` (modify: include ingest router)
- `submodule/maveric_platform_data_sim/app/main.py` (modify: start/stop consumer thread on startup/shutdown)
- `submodule/maveric_platform_data_sim/app/core/config.py` (modify: new settings)
- `submodule/maveric_platform_data_sim/app/event_handlers/kafka_handler.py` (modify: `KafkaConsumerManager` gains `enable_auto_commit: bool = True` param; producer gains a `send_json(topic, key, payload)` helper)
- `scripts/kafka/init-topics.sh` (modify, parent repo: ensure the `maveric.ingest.pm.v1` topic line exists - add `ensure_topic "maveric.ingest.pm.v1" "${INGEST_PM_TOPIC_PARTITIONS:-2}"` ONLY if E5.S1, the owner-of-record for topic provisioning, has not landed; check for an existing entry first)
- `submodule/maveric_platform_data_sim/README.md` (modify: ingestion section incl. scale-out path)

**Contract**

Kafka message on `maveric.ingest.pm.v1` (JSON, key = `tenant_id` bytes for per-tenant ordering). The topic carries TWO message kinds discriminated by `kind` (frozen in HLD Appendix A.5); this story implements the job kind, E1.S8 implements the records kind:

```json
{
  "schema": "maveric.ingest.pm.v1",
  "kind": "job",
  "tenant_id": "3f8c9e4e-...",
  "job_id": "upl-2026-07-01",
  "source_type": "nybsys_pm_csv",
  "params": { "...adapter-specific, validated by adapter.validate_params..." : "..." },
  "requested_at": "2026-07-16T10:00:00Z"
}
```

(A message with no `kind` field is treated as `kind="job"` for backward compatibility. The consumer routes on `kind` and hands `kind="records"` messages to the E1.S8 branch; until E1.S8 lands, `kind="records"` messages are logged and skipped, never crashed on.)

API (X-API-Key auth like every data_sim `/v1` route; gateway adds `/v1/tenants/:tid/ingest/**` -> DATA in E0; envelope = data_sim `success_envelope`):

- `POST /v1/tenants/{tenant_id}/ingest/uploads` body `{"job_id"?: str, "source_type": str, "params": object}` -> `202` `{job_id, source_type, status: "queued", created_at}`. `409 INGEST_JOB_EXISTS` if (tenant, job_id) exists; `422 SOURCE_TYPE_UNKNOWN` / `422 SOURCE_TYPE_UNAVAILABLE` for unregistered/stub adapters; `403` if the adapter declares a feature flag the tenant lacks; `503 KAFKA_UNAVAILABLE` if publish fails (job row is then deleted; the POST is atomic-or-nothing).
- `GET /v1/tenants/{tenant_id}/ingest/jobs/{job_id}` -> `200` `{job_id, source_type, status, stats, error, created_at, updated_at}`; `404` unknown.

Durability semantics (documents the smo_sim gap fix):
1. API inserts `ingest_jobs` row (`queued`) then publishes; consumer processes with `enable_auto_commit=False` and commits the offset **only after** writing a terminal status (`completed`/`failed`).
2. Crash mid-job: offset uncommitted, Kafka redelivers, consumer re-claims (`queued`/`running` -> `running`) and re-runs; canonical writers are idempotent (`ON CONFLICT DO NOTHING` on the PM PK), so replays are safe.
3. Crash after terminal write but before commit: redelivery hits the terminal-state skip (same pattern as `bdt_worker`) and just commits.
4. Scale-out path (documented, not built): the consumer joins group `data-sim-ingest`; running N data_sim replicas yields N consumers over the topic's partitions; per-tenant ordering is preserved by the tenant_id key. Raising throughput = raise partitions via `INGEST_PM_TOPIC_PARTITIONS` on the existing topics-job. No new deployable ever needed for this.

**Key snippets**

```python
# app/ingest/adapters/base.py
from __future__ import annotations
from typing import Any, ClassVar, Protocol, runtime_checkable
from pydantic import BaseModel, Field

class CanonicalPMRecord(BaseModel):
    """One canonical PM row; mirrors public.pm_measurements."""
    tenant_id: str
    source: str
    vendor: str
    dn: str
    metric: str
    value: float
    unit: str | None = None
    granularity_s: int
    ts: datetime
    day: int | None = None
    tick: int | None = Field(default=None, ge=0, le=23)
    labels: dict[str, Any] = Field(default_factory=dict)
    raw_ref: str | None = None

class CanonicalFMRecord(BaseModel): ...   # mirrors fm_alarms columns
class CanonicalCMRecord(BaseModel): ...   # mirrors cm_records columns

class ParseResult(BaseModel):
    pm_records: list[CanonicalPMRecord] = Field(default_factory=list)
    fm_records: list[CanonicalFMRecord] = Field(default_factory=list)
    cm_records: list[CanonicalCMRecord] = Field(default_factory=list)
    raw_refs: list[str] = Field(default_factory=list)   # S3 keys written/consumed (audit)
    stats: dict[str, Any] = Field(default_factory=dict)

@runtime_checkable
class SourceAdapter(Protocol):
    """Parse one ingest job into canonical records + raw refs. Store is the framework's job."""
    source_type: ClassVar[str]
    vendor: ClassVar[str]
    available: ClassVar[bool]                 # False => registered stub, POST returns 422
    feature_flag: ClassVar[str | None]        # e.g. 'nybsys'; checked against tenants.feature_flags

    def validate_params(self, tenant_id: str, params: dict[str, Any]) -> BaseModel: ...
    def parse(self, tenant_id: str, job_id: str, params: BaseModel) -> ParseResult: ...
    # Optional lifecycle hooks (used by the nybsys adapter for legacy status sync + builder call):
    def on_job_running(self, tenant_id: str, job_id: str, params: BaseModel) -> None: ...
    def on_job_completed(self, tenant_id: str, job_id: str, params: BaseModel, result: ParseResult) -> None: ...
    def on_job_failed(self, tenant_id: str, job_id: str, params: BaseModel, error: str) -> None: ...
```

```python
# app/ingest/registry.py
_REGISTRY: dict[str, SourceAdapter] = {}

def register(adapter: SourceAdapter) -> None: ...
def get_adapter(source_type: str) -> SourceAdapter: ...   # KeyError -> 422 at the API layer
def list_adapters() -> dict[str, dict[str, Any]]: ...      # {source_type: {available, vendor, feature_flag}}
```

```python
# app/ingest/dictionary.py
class VendorDictionary:
    """Cached vendor_dictionaries lookups; fallback rule: unmapped -> '<vendor>:<source_metric>'."""
    def __init__(self, vendor: str, db: Session) -> None: ...
    def map(self, source_metric: str) -> tuple[str, str | None]:
        """Return (canonical_metric, unit). Applies transform 'identity' or 'scale:<f>' is applied by caller via .transform()."""
```

```python
# app/ingest/service.py
def submit_job(db: Session, *, tenant_id: str, job_id: str, source_type: str, params: dict) -> IngestJobOut:
    """Validate adapter+flag+params, insert queued row, publish Kafka message (atomic-or-delete)."""

def run_job(message: IngestJobMessage) -> None:
    """Consumer entry: claim (CAS queued|running->running; terminal->skip), parse, batch-store
    (ensure_pm_partition per distinct month, executemany INSERT ... ON CONFLICT DO NOTHING),
    finalize terminal status + stats, invoke adapter lifecycle hooks."""
```

```python
# app/ingest/consumer.py
class IngestConsumerThread(threading.Thread):
    """Daemon thread; owns a KafkaConsumerManager(topic=INGEST_KAFKA_TOPIC,
    group_id=INGEST_CONSUMER_GROUP, enable_auto_commit=False). Poll loop -> run_job -> commit.
    stop() sets an event and closes the consumer; wired to FastAPI shutdown."""
```

```python
# app/core/config.py additions
INGEST_KAFKA_TOPIC: str = Field(default="maveric.ingest.pm.v1")
INGEST_CONSUMER_ENABLED: bool = Field(default=True)
INGEST_CONSUMER_GROUP: str = Field(default="data-sim-ingest")
INGEST_BATCH_ROWS: int = Field(default=5000)
```

**Acceptance criteria**
- POST with a registered available adapter returns 202 and a `queued` row; the same job_id again returns 409; unknown source_type returns 422 with code `SOURCE_TYPE_UNKNOWN`.
- With Kafka down, POST returns 503 and leaves no `ingest_jobs` row.
- Consumer thread starts only when `INGEST_CONSUMER_ENABLED` and `KAFKA_BOOTSTRAP_SERVERS` are set; the API works fully without Kafka configured (lab parity with today).
- Kill -9 the data_sim container mid-job (test adapter with a sleep): on restart the job is redelivered, re-runs, and reaches `completed`; no duplicate pm rows (PK conflict count == 0 effect).
- Replaying an already-completed job's message results in terminal-skip and an offset commit (log line asserted).
- `scripts/kafka/init-topics.sh` creates `maveric.ingest.pm.v1`; README documents the scale-out path.
- The dead `UTILS_KAFKA_TOPIC` config stays untouched (removed later; out of scope here).

**Test plan**
- Unit (`uv run pytest` in data_sim): registry register/get/list; dictionary fallback rule + `scale:` transform; `submit_job` 409/422/flag-denied paths with a fake producer; `run_job` claim CAS + terminal-skip with a fake adapter and sqlite-stub or mocked repo; consumer thread start/stop lifecycle with a mocked KafkaConsumerManager.
- Integration (lab compose, `scripts/kafka/compose.sh infra` + data_sim): end-to-end POST -> Kafka -> consumer -> `completed` with a test adapter; kill/restart durability drill above.

**Coding-agent prompt**

```
You are working in the CloudlyNet monorepo (repo root: cloudlynet_ai). Read
docs/task_docs/cloudlynet-rearchitecture/01-hld-frozen.md (§3, §4.1, §4.3) and
docs/task_docs/cloudlynet-rearchitecture/epics/EPIC-1-data-platform.md story E1.S2. E1.S1
(canonical tables incl. ingest_jobs) is already merged.

TASK: Build the data_sim ingestion framework. In submodule/maveric_platform_data_sim create the
app/ingest/ package exactly as specified in E1.S2 (adapters/base.py SourceAdapter protocol +
ParseResult + CanonicalPMRecord/FMRecord/CMRecord Pydantic models; registry.py; dictionary.py
VendorDictionary with '<vendor>:<metric>' fallback; service.py submit_job/run_job; consumer.py
IngestConsumerThread daemon thread with manual offset commit AFTER terminal status), plus
app/db/ingest_repo.py (raw SQL, per-call `SELECT set_config('app.current_tenant', :tid, true)`
exactly like app/db/baseline_repo.py; batch PM insert must call ensure_pm_partition(month) for
each distinct month then executemany INSERT ... ON CONFLICT DO NOTHING), the API endpoints
POST /v1/tenants/{tenant_id}/ingest/uploads (202) and GET /v1/tenants/{tenant_id}/ingest/jobs/{job_id}
in app/api/v1/endpoints/ingest.py wired into app/api/v1/routes.py, config additions
(INGEST_KAFKA_TOPIC=maveric.ingest.pm.v1, INGEST_CONSUMER_ENABLED, INGEST_CONSUMER_GROUP,
INGEST_BATCH_ROWS), consumer start/stop in app/main.py startup/shutdown, and extend
app/event_handlers/kafka_handler.py (KafkaConsumerManager enable_auto_commit param; producer
send_json helper using json.dumps and key=tenant_id.encode()). Job messages carry
"kind": "job" (absent kind = job, backward compatible); the consumer routes on kind and
logs+skips "records" messages until E1.S8 lands (HLD Appendix A.5). In the PARENT repo,
scripts/kafka/init-topics.sh: E5.S1 is the owner-of-record for topic provisioning - check the
script first and ONLY IF the maveric.ingest.pm.v1 ensure_topic line is absent (E5.S1 not
landed), add `ensure_topic "maveric.ingest.pm.v1" "${INGEST_PM_TOPIC_PARTITIONS:-2}"`; never
duplicate an existing entry. Document durability semantics + scale-out (consumer group over
partitions, tenant_id key ordering) in the data_sim README.
CONSTRAINTS: NO new container/port/deployable; the consumer is a daemon thread inside the
existing API process. Topic name maveric.ingest.pm.v1 is frozen (HLD §4.1); API routes are frozen
(HLD §4.3). Use data_sim's success_envelope, platform logger (app/utils/logger.py), Pydantic-first
validation, full type hints. kafka-python==2.0.2 is already in requirements.txt. cd into the
submodule for git ops.
DONE WHEN: `uv run pytest` passes in data_sim with the new unit tests listed in E1.S2's test
plan, and the lab drill works: POST a job with Kafka up -> completed; kill data_sim mid-job ->
restart -> job replays to completed with zero duplicate rows.
```

---

## E1.S3: NanoLink PM CSV adapter (store-only, dictionary-mapped, feature-flag guarded)

**Why.** First real adapter; carries the real customer input (NybSys NanoLink LTE PM CSVs) into the canonical store. Reuses only stages 1-2 (load/dedupe + hourly day/tick aggregation) of the smo_sim pipeline; all synthesis is explicitly out (it moves to the NDT feature builder in E2).

**Size:** M

**Scope**
- In: adapter `nybsys_pm_csv` (parse -> canonical `pm_measurements` rows + `pm_hourly.csv` audit in S3), lifted stages 1-2 module, S3 helpers ported into data_sim's `s3wrap`, dictionary seed migration, tenant feature-flag guard support (`feature_flag = "nybsys"`).
- Out: topology synthesis, config defaults, UE placement, RSRP labeling (stages 3-6: E2 / transitional shim in S4); the legacy `/custom` route (S4); FM/CM records (NanoLink PM CSVs carry none).

**Files**
- `submodule/maveric_platform_data_sim/app/ingest/adapters/nybsys/__init__.py` (create)
- `submodule/maveric_platform_data_sim/app/ingest/adapters/nybsys/pm_stages.py` (create: lifted verbatim from `submodule/maveric_platform_smo_sim/app/lib/nybsys/pipeline.py` functions `normalize_columns`, `load_and_merge_csvs`, `aggregate_pm_to_day_tick` + `AggregateResult`; extend `AggregateResult` with `unique_dates: list[str]` so the adapter can compute real timestamps; keep error message strings byte-identical, they are part of the public failure contract in `artifacts/nanolink/nybsys_data_contract.md` §12)
- `submodule/maveric_platform_data_sim/app/ingest/adapters/nybsys/adapter.py` (create: `NybsysPmCsvAdapter`)
- `submodule/maveric_platform_data_sim/app/utils/s3wrap.py` (modify: port `download_s3_url`, `upload_dataframe_csv`, `assert_allowed_pm_ingestion_url`, `purge_ingestion_artifacts` from `submodule/maveric_platform_smo_sim/app/lib/s3wrap.py`, keeping key layouts identical)
- `submodule/maveric_platform_data_sim/app/api/v1/custom/feature_guard.py` (create: port of smo_sim `app/api/v1/custom/feature_guard.py` `require_feature_access`; read-only check on the gateway-owned `tenants.feature_flags`)
- `submodule/maveric_platform_data_sim/alembic/versions/0002_seed_nybsys_dictionary.py` (create)
- `artifacts/migration/011_data_platform_canonical.sql` (modify: append the dictionary seed INSERTs with ON CONFLICT DO NOTHING)

**Contract**

Adapter params (validated by `validate_params`):

```python
class NybsysPmCsvParams(BaseModel):
    upload_id: str = Field(..., min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")
    raw_s3_urls: list[AnyUrl] = Field(..., min_length=1)   # each under {tenant_id}/pm-data-ingestion/{upload_id}/raw/
    rng_seed: int = Field(42, ge=0)                          # pass-through for the builder seam (S4); unused by parse
    samples_per_cell: int = Field(200, ge=1, le=10000)       # pass-through for the builder seam (S4); unused by parse
    legacy_upload_sync: bool = False                          # True when submitted via /custom/nybsys/uploads (S4)
```

Canonical row mapping (one `pm_measurements` row per hourly bucket per metric present):
- `source = "nybsys_pm_csv"`, `vendor = "nybsys"`, `granularity_s = 3600`
- `dn = f"site={siteId},cell={cellId}"`; `labels = {"site_id": siteId, "cell_id": cellId, "upload_id": upload_id}` (the `upload_id` label is the E2 feature-builder query handle)
- `day`/`tick` = the stage-2 indices; `ts` = `unique_dates[day]` at hour `tick`, interpreted as UTC (vendor CSVs are naive local time; stored-as-UTC assumption documented in the adapter contract doc)
- `metric` via `VendorDictionary("nybsys")`: seeded mappings below; anything unmapped falls back to `nybsys:<source_metric>`
- `raw_ref = f"{tenant_id}/pm-data-ingestion/{upload_id}/pm_hourly.csv"` (audit CSV, written by the adapter exactly as today)
- `stats` = `{rows_in, dropped_unparseable, num_sites, num_cells, num_days, pm_rows_out, date_range}`

Dictionary seed (`vendor='nybsys'`, all `transform='identity'`):

| source_metric | canonical_metric | unit | rationale |
|---|---|---|---|
| RRC.ConnMean | RRC.ConnMean | ue | TS 28.552-aligned name (mean RRC connections) |
| RRC.AttConnEstab | RRC.ConnEstabAtt | count | TS 28.552-aligned name |
| RRC.SuccConnEstab | RRC.ConnEstabSucc | count | TS 28.552-aligned name |
| CONTEXT.AttInitalSetup | nybsys:CONTEXT.AttInitalSetup | count | vendor counter (intentional vendor typo preserved) |
| CONTEXT.SuccInitalSetup | nybsys:CONTEXT.SuccInitalSetup | count | vendor counter |
| CONTEXT.AttRel.Normal | nybsys:CONTEXT.AttRel.Normal | count | vendor counter |
| CONTEXT.AttRel.Abnormal | nybsys:CONTEXT.AttRel.Abnormal | count | vendor counter |
| HO.IntraFreqOutAtt | nybsys:HO.IntraFreqOutAtt | count | LTE-era counter, no clean TS 28.552 equivalent |
| HO.InterFreqOutAtt | nybsys:HO.InterFreqOutAtt | count | same |
| HO.AttOutInterEnbS1 | nybsys:HO.AttOutInterEnbS1 | count | same |
| HO.AttOutInterEnbX2 | nybsys:HO.AttOutInterEnbX2 | count | same |

Feature flag: `NybsysPmCsvAdapter.feature_flag = "nybsys"`. The ingest API (S2 framework) rejects POSTs with 403 when `tenants.feature_flags['nybsys']` is falsy, using the same read-only lookup smo_sim uses today (SELECT on the gateway-owned `tenants` table after setting the tenant GUC).

**Key snippets**

```python
# app/ingest/adapters/nybsys/adapter.py
class NybsysPmCsvAdapter:
    """NanoLink PM CSV -> canonical pm_measurements. Store-only: NO topology/UE synthesis here."""
    source_type: ClassVar[str] = "nybsys_pm_csv"
    vendor: ClassVar[str] = "nybsys"
    available: ClassVar[bool] = True
    feature_flag: ClassVar[str | None] = "nybsys"

    def validate_params(self, tenant_id: str, params: dict[str, Any]) -> NybsysPmCsvParams:
        p = NybsysPmCsvParams.model_validate(params)
        for url in p.raw_s3_urls:
            s3wrap.assert_allowed_pm_ingestion_url(str(url), tenant_id, p.upload_id)  # ValueError -> 422
        return p

    def parse(self, tenant_id: str, job_id: str, params: NybsysPmCsvParams) -> ParseResult:
        temp_paths = _download_raw_csvs(params.raw_s3_urls)     # error text: "S3 file not found or inaccessible: {key} ({error_code})"
        try:
            merged = pm_stages.load_and_merge_csvs(temp_paths)
            agg = pm_stages.aggregate_pm_to_day_tick(merged)
            audit_key = f"{tenant_id}/pm-data-ingestion/{params.upload_id}/pm_hourly.csv"
            s3wrap.upload_dataframe_csv(audit_key, agg.df)
            records = _to_canonical(tenant_id, params.upload_id, agg, VendorDictionary("nybsys", db))
            return ParseResult(pm_records=records, raw_refs=[audit_key], stats=_stats(agg, records))
        finally:
            _cleanup(temp_paths)
```

```python
def _to_canonical(tenant_id: str, upload_id: str, agg: AggregateResult, vdict: VendorDictionary) -> list[CanonicalPMRecord]:
    """Melt the hourly wide frame: conn_mean maps from source metric 'RRC.ConnMean';
    each optional counter column maps by its own name; ts = unique_dates[day] + tick hours (UTC)."""
```

**Acceptance criteria**
- Submitting the sample CSVs from `artifacts/nanolink/nybsys_data_contract.md` §13 yields: 24 x num_days x num_cells rows for `RRC.ConnMean` (zero-fill included), correct `dn`/`labels`/`ts`, canonical metric names per the seed table, and `pm_hourly.csv` at the exact legacy S3 key.
- A tenant without `feature_flags['nybsys']` gets 403 on POST with source_type `nybsys_pm_csv`.
- Re-running the same job (Kafka replay) inserts zero additional rows.
- Failure messages for missing columns / unparseable timestamps / bad S3 keys are byte-identical to the strings in `nybsys_data_contract.md` §12 (they surface in `ingest_jobs.error` and, from S4 onward, in `nybsys_uploads.error`).
- No `baselines` or `ue_datasets` writes from this adapter (grep-level assertion in review + test).

**Test plan**
- Unit (`uv run pytest` in data_sim): lift smo_sim's existing stage-1/2 test cases for `pm_stages` (dedupe on siteId/cellId/_time, ISO8601-only `_time`, 24-tick zero-fill, `unique_dates` extension); `_to_canonical` melt correctness incl. dictionary fallback + label/dn/ts computation across a month boundary; params validation (bad prefix 422 path).
- Integration (lab): end-to-end POST /ingest/uploads -> consumer -> psql assertions on pm_measurements counts + spot values vs a hand-computed fixture; S3 (MinIO) audit object exists.

**Coding-agent prompt**

```
You are working in the CloudlyNet monorepo (repo root: cloudlynet_ai). Read
docs/task_docs/cloudlynet-rearchitecture/01-hld-frozen.md (§4.3) and
docs/task_docs/cloudlynet-rearchitecture/epics/EPIC-1-data-platform.md story E1.S3. E1.S1 and
E1.S2 are merged (canonical tables + ingest framework exist in
submodule/maveric_platform_data_sim).

TASK: Implement the NanoLink PM CSV adapter, store-only.
1) Lift, verbatim, normalize_columns/load_and_merge_csvs/aggregate_pm_to_day_tick/AggregateResult
   from submodule/maveric_platform_smo_sim/app/lib/nybsys/pipeline.py (lines ~100-215) into
   submodule/maveric_platform_data_sim/app/ingest/adapters/nybsys/pm_stages.py. Keep every error
   message string identical. Extend AggregateResult with unique_dates: list[str] (the sorted
   date strings backing the 0-based day index).
2) Port download_s3_url, upload_dataframe_csv, assert_allowed_pm_ingestion_url,
   purge_ingestion_artifacts from smo_sim app/lib/s3wrap.py into data_sim app/utils/s3wrap.py
   (same key layouts: {tenant}/pm-data-ingestion/{upload_id}/...).
3) Implement NybsysPmCsvAdapter (source_type='nybsys_pm_csv', vendor='nybsys', available=True,
   feature_flag='nybsys') per the E1.S3 Contract: params model NybsysPmCsvParams, parse() =
   download -> stages 1-2 -> write pm_hourly.csv audit at the legacy key -> melt to
   CanonicalPMRecord rows (dn='site={siteId},cell={cellId}', labels {site_id, cell_id, upload_id},
   granularity_s=3600, ts=unique_dates[day] at hour tick as UTC, metric via VendorDictionary with
   'nybsys:<name>' fallback, raw_ref=the audit key). Register it in app/ingest/registry wiring.
   ABSOLUTELY NO topology/config/UE synthesis in this adapter.
4) Port smo_sim's require_feature_access into data_sim app/api/v1/custom/feature_guard.py and
   make the ingest framework enforce adapter.feature_flag on POST (403).
5) Add alembic revision 0002_seed_nybsys_dictionary seeding vendor_dictionaries with the 11 rows
   from the E1.S3 seed table (INSERT ... ON CONFLICT (vendor, source_metric) DO NOTHING), and
   append the same INSERTs to artifacts/migration/011_data_platform_canonical.sql.
CONSTRAINTS: canonical vocabulary rule is frozen (HLD §4.3): TS 28.552 names where mapped by the
dictionary, else 'nybsys:<name>'. Preserve the intentional vendor typo 'Inital'. Idempotent
inserts only. Type hints + platform logger + Pydantic-first per CLAUDE.md.
DONE WHEN: `uv run pytest` passes in data_sim including the new stage-1/2 and melt tests, and the
lab end-to-end run in E1.S3's test plan produces the expected pm_measurements rows and MinIO
audit object.
```

---

## E1.S4: Legacy `/custom/nybsys/uploads` contract on data_sim + NDT feature-builder seam

**Why.** Hard constraint (HLD §3.2): the frontend's upload contract must survive the move byte-for-byte. The upload must now ALSO produce canonical PM, and derived baseline/dataset artifacts must keep appearing until E2's NDT feature builder takes over; this story defines that seam explicitly and ships a transitional inline builder so nothing regresses.

**Size:** L

**Scope**
- In: data_sim serves `POST/GET/LIST/DELETE /v1/tenants/{t}/custom/nybsys/uploads*` with the exact request/response contract of `artifacts/nanolink/nybsys_data_contract.md` (§8, §12) and smo_sim's envelope; `nybsys_uploads` repo in data_sim; `FeatureBuilderHook` seam with `legacy_inline` (transitional lift of smo_sim stages 3-6) and `ndt_api` (dark until E2) implementations selected by `NDT_FEATURE_BUILDER_MODE`; baselines/ue_datasets registration + delete-cascade parity.
- Out: gateway re-point (E0 code, exercised in S7); deletion of the smo_sim originals (S7); the real NDT builder (E2); any change to the frontend or to `nybsys_uploads` DDL.

**Files**
- `submodule/maveric_platform_data_sim/app/models/envelope.py` (create: port smo_sim `app/models/envelope.py` `SuccessEnvelope[T]` so response JSON, incl. the `Z`-suffixed timestamp format, is byte-compatible)
- `submodule/maveric_platform_data_sim/app/api/v1/custom/__init__.py` (create: custom router with `require_feature_access` dependency, mirroring smo_sim `app/api/v1/custom/router.py`)
- `submodule/maveric_platform_data_sim/app/api/v1/custom/nybsys_uploads.py` (create: router; port of smo_sim `app/api/v1/custom/nybsys/router.py` with the runner replaced by ingest_jobs + Kafka publish)
- `submodule/maveric_platform_data_sim/app/api/v1/custom/nybsys_schemas.py` (create: port of smo_sim `app/api/v1/custom/nybsys/schemas.py`: `NybsysUploadRequest`, `NybsysUploadResponse`, `PaginatedNybsysUploads`, `UploadStatus`)
- `submodule/maveric_platform_data_sim/app/db/nybsys_uploads_repo.py` (create: raw SQL against the existing shared `nybsys_uploads` table; create/get/list/update/delete + startup `reset_stale_uploads` port)
- `submodule/maveric_platform_data_sim/app/ingest/builder_hook.py` (create: seam)
- `submodule/maveric_platform_data_sim/app/ingest/legacy_builder/` (create: temporary lift of smo_sim `app/lib/nybsys/{pipeline.py stages 3-6, placement.py, rules.py, models.py, geo.py, pl_models/}` refactored to a single entry `build_from_pm_hourly(...)`; delete in E2)
- `submodule/maveric_platform_data_sim/app/db/baseline_repo.py` + `app/db/utils_repo.py` (modify: add delete helpers for the DELETE-cascade path; registration insert helpers already exist)
- `submodule/maveric_platform_data_sim/app/utils/s3wrap.py` (modify: add `purge_baseline_artifacts`, `purge_dataset_artifacts` ports)
- `submodule/maveric_platform_data_sim/app/ingest/adapters/nybsys/adapter.py` (modify: implement `on_job_running/completed/failed` lifecycle hooks: sync `nybsys_uploads` status when `legacy_upload_sync=True`, then invoke the builder hook on success)
- `submodule/maveric_platform_data_sim/app/core/config.py` (modify: `NDT_BASE_URL`, `NDT_API_KEY`, `NDT_FEATURE_BUILDER_MODE`, `NDT_BUILD_TIMEOUT_S`)
- `submodule/maveric_platform_data_sim/app/main.py` (modify: startup `reset_stale_uploads` sweep, same semantics as smo_sim `main.py:40-45`)

**Contract**

1) Public API: byte-compatible with today. `POST /v1/tenants/{tenant_id}/custom/nybsys/uploads` accepts `{upload_id, raw_s3_urls, rng_seed=42, samples_per_cell=200}` -> `202` `SuccessEnvelope[NybsysUploadResponse]` with derived `baseline_id={upload_id}-topology`, `dataset_id={upload_id}-dataset`, status lifecycle `uploading -> processing -> completed|failed`, 409 on duplicate upload_id, 422 on S3 URLs outside `{tenant_id}/pm-data-ingestion/{upload_id}/raw/`. GET/LIST/DELETE (incl. `delete_derived`) exactly as `artifacts/nanolink/nybsys_data_contract.md` and the current smo_sim router. Feature-gated by `tenants.feature_flags['nybsys']` (403).

2) Internal flow change: POST creates the `nybsys_uploads` row, then submits an ingest job (`source_type="nybsys_pm_csv"`, `job_id=upload_id`, params incl. `legacy_upload_sync=True`, `rng_seed`, `samples_per_cell`) through the S2 framework. The consumer runs parse+store (canonical PM + audit CSV), then the builder hook, then finalizes both `ingest_jobs` and `nybsys_uploads`. `completed` on `nybsys_uploads` continues to mean "baseline + dataset exist", exactly as today.

3) **NDT feature-builder seam (NEW contract, implemented by E2 in bdt_engine; listed here as the definition of record until folded into `artifacts/design/openapi.yaml`):**

```
POST {NDT_BASE_URL}/v1/tenants/{tenant_id}/ndt/feature-builds     (header X-API-Key: NDT_API_KEY)
{
  "build_id": "<upload_id>",                       // idempotency key, unique per tenant
  "source_type": "nybsys_pm_csv",
  "pm_query": { "source": "nybsys_pm_csv", "labels": { "upload_id": "<upload_id>" } },
  "targets": { "baseline_id": "<upload_id>-topology", "ue_dataset_id": "<upload_id>-dataset" },
  "params": { "rng_seed": 42, "samples_per_cell": 200 }
}
-> 202 {"build_id": "...", "status": "queued"}    (409 if build_id exists in a non-failed state)

GET {NDT_BASE_URL}/v1/tenants/{tenant_id}/ndt/feature-builds/{build_id}
-> 200 {"build_id", "status": "queued|running|completed|failed", "error": null|str,
        "artifacts": {"baseline_id": str, "ue_dataset_id": str} | null}
```

The builder reads canonical PM via `GET /v1/tenants/{t}/data/pm` (E1.S5) using the `pm_query` filter, and writes `baselines` + `ue_datasets` rows and S3 artifacts under the existing key conventions (`{tenant}/baselines/{bid}/*`, `{tenant}/ue/{did}/synthetic_dataset.csv`), per frozen HLD §4.6.

4) Transition switch: `NDT_FEATURE_BUILDER_MODE`:
- `legacy_inline` (default until E2 ships): `LegacyInlineBuilder` runs the lifted stages 3-6 in-process on the stage-2 hourly frame, uploads topology/config/ue_training_data/synthetic_dataset CSVs to the legacy keys, registers `baselines` + `ue_datasets` rows (ports of `nybsys_runner._register_baseline/_register_dataset`, incl. `source_type='utils_traffic_load'` on the dataset and best-effort S3 purge on failure), and additionally sets `"semi_synthetic": true` inside `ue_datasets.stats` (additive, claims-honesty per HLD §4.6).
- `ndt_api`: `NdtApiBuilder` POSTs the feature-build, polls until terminal (bounded by `NDT_BUILD_TIMEOUT_S`, default 1800 s), maps terminal state onto `nybsys_uploads`. Flip to default in E2.S9 (the explicit cutover story in EPIC-2); `legacy_builder/` is then deleted there.
- `off`: skip the builder (canonical PM only; `nybsys_uploads` completes with `date_range` but no derived artifacts). Lab/testing only.

**Key snippets**

```python
# app/ingest/builder_hook.py
class BuildRequest(BaseModel):
    tenant_id: str
    build_id: str
    upload_id: str
    baseline_id: str
    ue_dataset_id: str
    rng_seed: int
    samples_per_cell: int
    pm_hourly_df_ref: str          # S3 key of pm_hourly.csv (legacy_inline reads this, not /data/pm)

class FeatureBuilderHook(Protocol):
    def trigger(self, req: BuildRequest) -> None:
        """Produce baselines+ue_datasets for this upload. Raises BuilderError on failure."""

def get_builder() -> FeatureBuilderHook:
    """Resolve from settings.NDT_FEATURE_BUILDER_MODE: legacy_inline | ndt_api | off."""
```

```python
# app/ingest/legacy_builder/__init__.py
def build_from_pm_hourly(pm_hourly: pd.DataFrame, *, rng_seed: int, samples_per_cell: int) -> BuildResult:
    """Stages 3-6 lifted from smo_sim pipeline.run_pipeline: build_topology_and_config ->
    apply_stochastic_guardrail -> generate_ue_data -> generate_ue_training_data.
    TEMPORARY: deleted when E2's bdt_engine feature builder is live (NDT_FEATURE_BUILDER_MODE=ndt_api)."""
```

Byte-compat note for the coding agent: response envelopes for these routes MUST use the ported `SuccessEnvelope` (`timestamp` = `datetime.utcnow().isoformat() + "Z"`), not data_sim's `success_envelope` (which emits `+00:00` offsets). Error responses flow through data_sim's existing HTTPException handler, which already matches smo_sim's error envelope shape (`{success:false, timestamp, message, data:null, errors:[{code:"HTTP_<n>"}]}`); add a parity test capturing 404/409/422 JSON key sets against the smo_sim shapes.

**Acceptance criteria**
- Contract parity: for POST/GET/LIST/DELETE, the JSON response bodies (field names, nesting, status codes, derived IDs, status lifecycle strings, error messages from `nybsys_data_contract.md` §12) are identical to smo_sim's, verified by a recorded-fixture parity test.
- With `NDT_FEATURE_BUILDER_MODE=legacy_inline`, a full upload produces: canonical PM rows AND the four derived CSVs at legacy S3 keys AND `baselines`/`ue_datasets` rows that bdt_engine/rApp can train from unchanged (S3 key conventions + table shapes per HLD §3.3), AND `ue_datasets.stats.semi_synthetic == true`.
- With `NDT_FEATURE_BUILDER_MODE=ndt_api` and a stub NDT server fixture, data_sim POSTs the exact seam body above, polls, and maps completed/failed onto `nybsys_uploads`; timeout marks the upload `failed` with a `BUILDER_TIMEOUT` error string.
- Builder failure (either mode) sets `nybsys_uploads.status='failed'` with the error, purges partial baseline/dataset S3 artifacts best-effort, but the canonical PM rows REMAIN (store-only data is never rolled back; documented).
- A data_sim restart mid-upload re-drives the job via Kafka redelivery; no upload is left in `processing` forever; the startup sweep resets stale `processing` rows older than the lease window to `failed` with a restart note only when the Kafka message is also gone (same defensive semantics as smo_sim's `reset_stale_uploads`).
- `rng_seed` determinism preserved: same input + seed -> identical topology/UE CSVs (hash compare with an smo_sim-generated fixture).

**Test plan**
- Unit (`uv run pytest` in data_sim): router parity tests with recorded smo_sim response fixtures (202/404/409/422 + list pagination `{items,total}`); builder resolution by mode; `NdtApiBuilder` against `respx`/mock HTTP (202 -> poll -> completed/failed/timeout); `LegacyInlineBuilder` determinism vs fixture hashes; lifecycle hooks update `nybsys_uploads` correctly on parse failure vs builder failure.
- Integration (lab): full browser-path simulation: presigned PUT to MinIO -> POST /custom/nybsys/uploads (direct to data_sim :8003 with X-API-Key, pre-gateway-re-point) -> poll GET until completed -> assert PM rows + S3 artifacts + baselines/ue_datasets rows; then run a BDT training against the produced baseline to prove downstream compatibility.

**Coding-agent prompt**

```
You are working in the CloudlyNet monorepo (repo root: cloudlynet_ai). Read
docs/task_docs/cloudlynet-rearchitecture/01-hld-frozen.md (§3 hard constraints, §4.3, §4.6),
artifacts/nanolink/nybsys_data_contract.md (§8 request contract, §12 error strings), and
docs/task_docs/cloudlynet-rearchitecture/epics/EPIC-1-data-platform.md story E1.S4. E1.S1-S3 are
merged. The reference implementation you are porting FROM is
submodule/maveric_platform_smo_sim (app/api/v1/custom/nybsys/router.py + schemas.py,
app/services/nybsys_runner.py, app/lib/nybsys/pipeline.py, app/lib/s3wrap.py,
app/models/envelope.py). Do NOT modify smo_sim in this story.

TASK: Serve the legacy NybSys upload contract from data_sim, backed by the ingest framework, and
build the NDT feature-builder seam.
1) Port SuccessEnvelope, the nybsys upload router (all 4 endpoints incl. delete_derived cascade),
   schemas, and a raw-SQL nybsys_uploads repo into submodule/maveric_platform_data_sim at the
   paths listed in E1.S4 Files. POST must: feature-guard, validate URLs, insert nybsys_uploads
   (status 'uploading'), submit ingest job source_type='nybsys_pm_csv' with
   job_id=upload_id and params {upload_id, raw_s3_urls, rng_seed, samples_per_cell,
   legacy_upload_sync: true}, return 202 with the exact legacy envelope. Response/error JSON must
   be byte-compatible: write parity tests from recorded fixtures of the smo_sim responses.
2) Implement app/ingest/builder_hook.py (BuildRequest, FeatureBuilderHook protocol, get_builder()
   switching on settings.NDT_FEATURE_BUILDER_MODE in {legacy_inline, ndt_api, off}).
3) legacy_inline: lift smo_sim pipeline stages 3-6 + placement.py/rules.py/models.py/geo.py/
   pl_models/ into app/ingest/legacy_builder/ exposing
   build_from_pm_hourly(pm_hourly_df, rng_seed, samples_per_cell); upload the 4 derived CSVs to
   the EXACT legacy keys ({tenant}/baselines/{bid}/topology|config|ue_training_data.csv,
   {tenant}/ue/{did}/synthetic_dataset.csv), register baselines + ue_datasets rows (port
   _register_baseline/_register_dataset from nybsys_runner.py; dataset source_type
   'utils_traffic_load'), add "semi_synthetic": true into ue_datasets.stats. Mark the package
   docstring TEMPORARY (deleted in E2).
4) ndt_api: POST {NDT_BASE_URL}/v1/tenants/{t}/ndt/feature-builds with the exact JSON body in
   E1.S4 Contract item 3, header X-API-Key: NDT_API_KEY; poll GET .../feature-builds/{build_id}
   until terminal or NDT_BUILD_TIMEOUT_S (default 1800); map onto nybsys_uploads.
5) Wire the nybsys adapter lifecycle hooks: on_job_running -> nybsys_uploads 'processing';
   on_job_completed -> run builder then 'completed' with date_range; on_job_failed/builder error
   -> 'failed' + error text; canonical PM rows are never deleted on builder failure.
6) Config: NDT_BASE_URL, NDT_API_KEY, NDT_FEATURE_BUILDER_MODE (default 'legacy_inline'),
   NDT_BUILD_TIMEOUT_S. Startup sweep port of reset_stale_uploads.
CONSTRAINTS: public contract byte-compatibility is a frozen hard constraint; derived IDs stay
{upload_id}-topology / {upload_id}-dataset; S3 key conventions are shared contracts and must not
change; determinism via rng_seed must match smo_sim output (hash-compare fixtures). Never claim
O-RAN/RIC/SMO compliance in any docstring or doc text; no em dashes in artifacts/ files.
DONE WHEN: `uv run pytest` passes in data_sim incl. parity + determinism tests, and the lab
end-to-end in E1.S4's test plan (upload -> completed -> BDT trains on the produced baseline)
succeeds with NDT_FEATURE_BUILDER_MODE=legacy_inline.
```

---

## E1.S5: Query APIs `GET /data/pm|fm|cm`

**Why.** The canonical store is only useful if the NDT feature builder (E2), the loop feedback path (E5), and operators can read it. Frozen HLD §4.3 names these routes; the E2 builder's `pm_query` (S4 seam) depends on the labels filter.

**Size:** M

**Scope**
- In: three read endpoints with dn/metric/time/label filters, keyset-friendly pagination, RLS-scoped raw SQL.
- Out: aggregation/rollups (later epic), gateway registration (E0 adds `/v1/tenants/:tid/data/**` -> DATA), any write path.

**Files**
- `submodule/maveric_platform_data_sim/app/api/v1/endpoints/data_query.py` (create)
- `submodule/maveric_platform_data_sim/app/db/ingest_repo.py` (modify: add `query_pm/query_fm/query_cm` functions)
- `submodule/maveric_platform_data_sim/app/api/v1/routes.py` (modify: include router)

**Contract**

`GET /v1/tenants/{tenant_id}/data/pm`
Query params: `dn` (repeatable, exact), `dn_prefix` (single), `metric` (repeatable), `source`, `vendor`, `from_ts`/`to_ts` (ISO 8601, filter on `ts`), `day`, `tick`, `upload_id` (sugar for `labels->>'upload_id'`), `order` (`ts_asc` default | `ts_desc`), `limit` (default 1000, max 10000), `offset` (default 0).
-> `200` data_sim `success_envelope` with data:

```json
{
  "items": [
    {"source": "nybsys_pm_csv", "vendor": "nybsys", "dn": "site=S1,cell=C1",
     "metric": "RRC.ConnMean", "value": 3.5, "unit": "ue", "granularity_s": 3600,
     "ts": "2025-12-29T00:00:00+00:00", "day": 0, "tick": 0,
     "labels": {"site_id": "S1", "cell_id": "C1", "upload_id": "u1"},
     "raw_ref": "t1/pm-data-ingestion/u1/pm_hourly.csv"}
  ],
  "limit": 1000, "offset": 0, "returned": 1, "has_more": false
}
```

(`tenant_id` is omitted from items: it is the path scope. No `total` count: unbounded count(*) on a partitioned fact table is a footgun; `has_more` = fetched limit+1.)

`GET /v1/tenants/{tenant_id}/data/fm`: filters `dn`, `dn_prefix`, `source`, `state`, `severity`, `from_ts`/`to_ts` on `raised_at`; same pagination; items mirror `fm_alarms` columns.
`GET /v1/tenants/{tenant_id}/data/cm`: filters `dn`, `dn_prefix`, `source`, `origin`, `from_ts`/`to_ts` on `captured_at`; same pagination; items mirror `cm_records` columns.

Errors: `422` invalid timestamp/limit; `404` never (empty list is a valid answer).

**Key snippets**

```python
class PMQueryParams(BaseModel):
    """Validated /data/pm filters; assembled from FastAPI Query() params."""
    dn: list[str] = Field(default_factory=list)
    dn_prefix: str | None = None
    metric: list[str] = Field(default_factory=list)
    source: str | None = None
    vendor: str | None = None
    from_ts: datetime | None = None
    to_ts: datetime | None = None
    day: int | None = None
    tick: int | None = Field(default=None, ge=0, le=23)
    upload_id: str | None = None
    order: Literal["ts_asc", "ts_desc"] = "ts_asc"
    limit: int = Field(default=1000, ge=1, le=10000)
    offset: int = Field(default=0, ge=0)

def query_pm(db: Session, tenant_id: str, q: PMQueryParams) -> tuple[list[dict], bool]:
    """SET LOCAL app.current_tenant, build WHERE from bound params only (no f-string SQL),
    fetch limit+1 rows, return (rows[:limit], has_more)."""
```

**Acceptance criteria**
- Filters compose correctly (dn + metric + time window + upload_id); results ordered by ts; `has_more` correct at the boundary.
- Query for tenant A with tenant B's GUC set returns zero rows (RLS enforced through the partitioned parent).
- `upload_id` filter returns exactly the rows one S3/S4 upload produced (this is the E2 builder's read path).
- P95 under 500 ms on a lab dataset of 1M rows across 3 monthly partitions for a one-day, one-cell query (indexes prove out; record the numbers in the PR).
- All SQL uses bound parameters; no string interpolation of user input.

**Test plan**
- Unit (`uv run pytest`): PMQueryParams validation edges; SQL builder produces expected WHERE fragments + params for each filter combination (assert against the generated statement/params, not the DB).
- Integration (lab): seed via the S3 adapter, run the filter matrix + RLS cross-tenant probe + the perf spot-check.

**Coding-agent prompt**

```
You are working in the CloudlyNet monorepo (repo root: cloudlynet_ai). Read
docs/task_docs/cloudlynet-rearchitecture/01-hld-frozen.md (§4.3) and
docs/task_docs/cloudlynet-rearchitecture/epics/EPIC-1-data-platform.md story E1.S5. E1.S1-S4 are
merged in submodule/maveric_platform_data_sim.

TASK: Implement GET /v1/tenants/{tenant_id}/data/pm, /data/fm, /data/cm in
app/api/v1/endpoints/data_query.py with the exact query params, response shape
({items, limit, offset, returned, has_more} inside data_sim's success_envelope), and pagination
semantics (fetch limit+1, no total count) defined in E1.S5's Contract. Add
query_pm/query_fm/query_cm to app/db/ingest_repo.py: raw SQL with bound parameters only,
per-call SELECT set_config('app.current_tenant', :tid, true) like app/db/baseline_repo.py,
dynamic WHERE assembled from a whitelist of filter fragments. upload_id filters
labels->>'upload_id'. Wire the router into app/api/v1/routes.py under the authed /v1 router.
CONSTRAINTS: read-only; no new tables; route paths frozen by HLD §4.3; X-API-Key auth inherited
from the /v1 router; type hints + Pydantic params model per CLAUDE.md.
DONE WHEN: `uv run pytest` passes with the new unit tests (params validation + SQL builder), and
the lab filter matrix + cross-tenant RLS probe in E1.S5's test plan passes.
```

---

## E1.S6: Future adapter stubs: `3gpp_xml_pm`, `ves_listener`, `ocudu_ws` (registry + contract docs only)

**Why.** The recon (pm_fm_cm report) is unambiguous: vendors do not ship uniform PM/FM/CM, so the roadmap is per-vendor adapters over one canonical schema. Registering named stubs now locks the extension seams and gives sales/solutioning honest, citable contract docs.

**Size:** S

**Scope**
- In: three stub adapter classes (`available=False`), registry entries, `422 SOURCE_TYPE_UNAVAILABLE` behavior (already framework-provided by S2), contract docs under a new `artifacts/data-platform/` bundle + bundle README + CLAUDE.md bundle-table row.
- Out: any parsing/protocol code; any listener endpoint; any smo_sim collector work (that is E4's `ocudu_ws_collector`).

**Files**
- `submodule/maveric_platform_data_sim/app/ingest/adapters/stubs.py` (create: `ThreeGppXmlPmAdapter`, `VesListenerAdapter`, `OcuduWsAdapter`)
- `artifacts/data-platform/README.md` (create: bundle index + canonical vocabulary rule + scale-out note)
- `artifacts/data-platform/canonical-schema.md` (create: table semantics, dn convention `site=<site_id>,cell=<cell_id>`, labels conventions, partition policy, idempotency keys)
- `artifacts/data-platform/ingest-topic-contract.md` (create: `maveric.ingest.pm.v1` message schema from S2, durability + consumer-group scale-out)
- `artifacts/data-platform/adapters/nybsys_pm_csv.md` (create: the S3 adapter contract, cross-linking `artifacts/nanolink/nybsys_data_contract.md` as the input contract of record)
- `artifacts/data-platform/adapters/3gpp_xml_pm.md` (create: PLANNED; parses TS 32.435 XML measCollec PM files, per the TS 32.432 file concept; per-vendor counter names map via vendor_dictionaries)
- `artifacts/data-platform/adapters/ves_listener.md` (create: PLANNED; accepts VES-style JSON event batches pushed to the ingest API/topic)
- `artifacts/data-platform/adapters/ocudu_ws.md` (create: PLANNED; sink for OCUDU JSON metrics forwarded by smo_sim's `ocudu_ws_collector` actuator-framework placeholder, HLD §4.5; messages arrive on `maveric.ingest.pm.v1` with `source_type=ocudu_ws`)
- `CLAUDE.md` (modify: add `artifacts/data-platform/` row to the Bundles table)

**Contract**

```python
class ThreeGppXmlPmAdapter:
    """PLANNED: TS 32.435 XML (measCollec) PM file parsing. Registered stub; not yet available."""
    source_type: ClassVar[str] = "3gpp_xml_pm"
    vendor: ClassVar[str] = "3gpp"          # per-file vendor resolved from measType dictionaries when implemented
    available: ClassVar[bool] = False
    feature_flag: ClassVar[str | None] = None
    def validate_params(self, tenant_id: str, params: dict[str, Any]) -> BaseModel:
        raise SourceTypeUnavailable(self.source_type)   # framework maps to 422 SOURCE_TYPE_UNAVAILABLE
    def parse(self, *a: Any, **k: Any) -> ParseResult:
        raise SourceTypeUnavailable(self.source_type)
```

(`VesListenerAdapter`: `source_type="ves_listener"`, `vendor="ves"`. `OcuduWsAdapter`: `source_type="ocudu_ws"`, `vendor="ocudu"`.)

Doc wording constraints (claims guardrails, binding for the artifacts/ files): describe `3gpp_xml_pm` as "parses the TS 32.435 XML PM file format"; NEVER "O1 compliant" or "O-RAN compliant". Describe `ves_listener` as "accepts VES-style JSON event payloads"; NEVER "ONAP/VES certified". Describe `ocudu_ws` as "JSON metrics stream sink for the OCUDU WebSocket collector"; NEVER an E2/RIC interface. No em dash characters anywhere in these docs.

**Acceptance criteria**
- `GET`-side: `list_adapters()` (and any debug surface) shows the three stubs with `available: false`.
- `POST /ingest/uploads` with each stub source_type returns 422 with code `SOURCE_TYPE_UNAVAILABLE` and a message naming the adapter.
- The four adapter docs + schema + topic docs exist, cross-linked from the bundle README; CLAUDE.md bundle table updated; wording passes a manual claims-guardrails check (no O-RAN/RIC/SMO compliance claims, no U+2014).

**Test plan**
- Unit (`uv run pytest`): registry contains the three stubs; POST path returns 422 for each; a lint-style test asserts the U+2014 character never appears in `artifacts/data-platform/**.md` (read from repo root fixture path).

**Coding-agent prompt**

```
You are working in the CloudlyNet monorepo (repo root: cloudlynet_ai). Read
docs/task_docs/cloudlynet-rearchitecture/01-hld-frozen.md (§4.3, §4.5),
artifacts/marketing/claims-guardrails.md, and
docs/task_docs/cloudlynet-rearchitecture/epics/EPIC-1-data-platform.md story E1.S6. E1.S2's
framework (SourceAdapter protocol, registry, 422 SOURCE_TYPE_UNAVAILABLE) is merged.

TASK: 1) Add app/ingest/adapters/stubs.py in submodule/maveric_platform_data_sim with three
registered stub adapters (3gpp_xml_pm, ves_listener, ocudu_ws), available=False, raising
SourceTypeUnavailable from validate_params/parse. Register them at startup next to the nybsys
adapter. 2) Create the artifacts/data-platform/ doc bundle in the PARENT repo per the E1.S6
Files list: README.md, canonical-schema.md, ingest-topic-contract.md, adapters/nybsys_pm_csv.md,
adapters/3gpp_xml_pm.md, adapters/ves_listener.md, adapters/ocudu_ws.md. Content: canonical
vocabulary rule (TS 28.552 names where mappable else vendor:<name>), dn/labels conventions,
maveric.ingest.pm.v1 message schema, durability + consumer-group scale-out path, per-adapter
input contracts (planned adapters clearly marked PLANNED). 3) Add an artifacts/data-platform/
row to the Bundles table in CLAUDE.md.
CONSTRAINTS: docs are engineering contracts but externally quotable: NEVER claim O-RAN, O1, RIC,
SMO, ONAP, or VES compliance; say "parses the TS 32.435 XML PM file format" style wording. NO em
dash (U+2014) characters anywhere. No protocol code, no new endpoints.
DONE WHEN: `uv run pytest` in data_sim passes incl. the three 422 tests and the no-em-dash doc
lint test, and all seven markdown files exist and cross-link.
```

---

## E1.S7: Cutover: gateway re-point, smo_sim decommission plan, backfill

**Why.** The move is only done when the frontend traffic flows through data_sim, smo_sim's duplicated upload path is retired without breaking anything, and historical PM (locked in S3 audit CSVs) is loadable into the canonical store.

**Size:** M

**Scope**
- In: cutover runbook (uses E0's gateway split; this story executes and verifies it in lab), backfill script + note, README/Agent.md drift fixes in data_sim.
- Out: the gateway code change itself (E0 owns `custom/nybsys/uploads*` -> DATA split, device/edge ops stay SMO, plus the duplicate-route panic fix); ALL smo_sim deletions (router, runner, schemas, repository, `reset_stale_uploads` sweep, `app/lib/nybsys/`) - E4.S6 is the SOLE owner of the smo_sim upload decommission; this story only records the gate and hands over; design-doc/openapi updates (E6).

**Files**
- `docs/task_docs/cloudlynet-rearchitecture/epics/E1-cutover-runbook.md` (create: the runbook below, kept next to the epic; task docs are gitignored-local per CLAUDE.md, so ALSO mirror the durable decommission/backfill notes into `artifacts/data-platform/README.md`)
- `submodule/maveric_platform_data_sim/scripts/backfill_pm_from_audit.py` (create)
- NO smo_sim file is touched by this story: the decommission changeset (delete `app/api/v1/custom/nybsys/router.py`/`schemas.py`, `app/services/nybsys_runner.py`, the `reset_stale_uploads` sweep, conditional `app/lib/nybsys/`) is owned entirely by E4.S6, gated on this runbook's step-4 soak.
- `submodule/maveric_platform_data_sim/README.md` + `Agent.md` (modify: fix the documented-but-nonexistent layout drift noted in recon; describe the real Data Platform role)

**Contract** (runbook order; each step has a rollback)

1. **Pre-checks**: E1.S1-S6 deployed to lab; E0 gateway image with the route split available but NOT yet flipped; parity suite green against data_sim direct (`:8003` with `X-API-Key`).
2. **Dark-launch soak**: run one production-shaped upload against data_sim direct; verify canonical PM + derived artifacts + BDT trainability.
3. **Gateway re-point** (E0 deliverable, executed here): `/v1/tenants/:tid/custom/nybsys/uploads*` -> DATA (with `DATA_API_KEY` injection); ALL other `/custom/**` (edge-devices, devices, commands, recommendations) stays -> SMO. Lab: compose env/gateway config only. Rollback = flip the route mapping back; smo_sim path is still fully functional until step 5.
4. **Soak window**: frontend regression pass on the `/custom-pm-ingestion` page (upload, poll, list, delete incl. `delete_derived`); both services healthy; `nybsys_uploads` written only by data_sim now (verify by `updated_at` provenance in logs).
5. **Decommission smo_sim upload path**: HANDOVER to E4.S6 (the sole owner of all smo_sim deletions). This runbook records the gate: E4.S6 must not start until step 4's soak is confirmed; the runbook entry links the E4.S6 story and the confirmation date. `nybsys_uploads`, `baselines`, `ue_datasets` tables are untouched (shared-table contract, HLD §3.3). smo_sim keeps serving `/baselines`, `/ue-data`, and the NanoLink device plane.
6. **Backfill (optional, per-tenant)**: `uv run python scripts/backfill_pm_from_audit.py --tenant <uuid> [--upload <id>]` lists `{tenant}/pm-data-ingestion/*/pm_hourly.csv` audit objects in S3, replays each through the canonical melt (`_to_canonical` with `labels.backfill=true`, `source='nybsys_pm_csv'`), idempotent via the PM PK. Note: audit CSVs are the ONLY historical PM source (no PM counter ever landed in Postgres before this epic); uploads whose audit CSV was deleted are unrecoverable and are logged + skipped.

**Key snippets**

```python
# scripts/backfill_pm_from_audit.py
def backfill_tenant(tenant_id: str, upload_id: str | None = None, *, dry_run: bool = False) -> BackfillReport:
    """List {tenant}/pm-data-ingestion/{upload}/pm_hourly.csv audit objects, melt each to
    CanonicalPMRecord rows (labels.backfill=true), ensure partitions, INSERT ... ON CONFLICT
    DO NOTHING. Prints per-upload counts; never touches nybsys_uploads status."""
```

**Acceptance criteria**
- Runbook executed through step 4 in lab compose: after step 3, the frontend upload page works unchanged through the gateway; step 5 is recorded as a documented handover to E4.S6 (gate + link + confirmation date in the runbook), with zero smo_sim files changed by this story (verify: `git -C submodule/maveric_platform_smo_sim status` clean).
- Backfill on a tenant with 2 historical uploads inserts the expected row counts; re-running inserts 0; `--dry-run` inserts 0 and reports.
- data_sim README/Agent.md describe the real service (Data Platform role, ingest framework, canonical tables) and no longer reference nonexistent files (`app/workers/generate_worker.py`, `db/migrations/`).
- Durable notes (decommission rationale, backfill instructions, cutover date) mirrored into `artifacts/data-platform/README.md`.

**Test plan**
- Unit (`uv run pytest` in data_sim): backfill melt reuses the S3 adapter's `_to_canonical` (shared function, no copy); dry-run/idempotency logic with mocked S3 + repo.
- Integration (lab): the runbook through step 4 as scripted steps (the deletion regression belongs to E4.S6's test plan); gateway smoke: `go test ./...` in `submodule/maveric_platform_gateway` if any route-table fixture changed in E0.

**Coding-agent prompt**

```
You are working in the CloudlyNet monorepo (repo root: cloudlynet_ai). Read
docs/task_docs/cloudlynet-rearchitecture/01-hld-frozen.md (§3, §4.3 route-split rule) and
docs/task_docs/cloudlynet-rearchitecture/epics/EPIC-1-data-platform.md story E1.S7. E1.S1-S6 are
merged and verified in lab; E0's gateway split (custom/nybsys/uploads* -> DATA, device/edge ops
stay SMO) is deployed but can be toggled.

TASK: 1) Write docs/task_docs/cloudlynet-rearchitecture/epics/E1-cutover-runbook.md with the
6-step order + rollbacks from E1.S7's Contract (step 5 is a documented HANDOVER: the smo_sim
decommission is owned entirely by EPIC-4 story E4.S6, gated on step 4's soak - record the gate,
the E4.S6 link, and the confirmation date; delete NOTHING in smo_sim yourself), and mirror the
durable decommission + backfill notes into artifacts/data-platform/README.md. 2) Add
submodule/maveric_platform_data_sim/scripts/backfill_pm_from_audit.py per the E1.S7 snippet:
per-tenant replay of {tenant}/pm-data-ingestion/*/pm_hourly.csv audit CSVs into pm_measurements
(labels.backfill=true, source='nybsys_pm_csv', ON CONFLICT DO NOTHING, --dry-run flag), REUSING
the nybsys adapter's _to_canonical (refactor it to a shared function if needed, no copy-paste).
3) Update data_sim README.md and Agent.md to describe the Data Platform role and remove
references to files that do not exist.
CONSTRAINTS: this story touches data_sim and parent-repo docs ONLY - zero smo_sim changes
(E4.S6 owns all smo_sim deletions); cd into each submodule for git ops; separate commits per
submodule; no submodule pointer commits in the parent repo. Shared tables (nybsys_uploads,
baselines, ue_datasets) and S3 key conventions stay valid throughout (HLD §3.3). Zero CI/CD
change.
DONE WHEN: backfill unit tests pass (`uv run pytest` in data_sim), `git -C
submodule/maveric_platform_smo_sim status` is clean, and the runbook document is complete with
rollback steps for every stage plus the step-5 handover record.
```

---

## E1.S8: Inline-records ingest branch (streaming sources: OCUDU WS collector; reserved near-RT KPM stream)

**Why.** Streaming producers publish inline record batches onto `maveric.ingest.pm.v1` (E4.S5's OCUDU collector with `source_type=ocudu_ws` is the live producer; `source_type=nearrt_kpm_stream` is RESERVED for the deferred near-RT placeholder track and is never emitted until that track opens), and without a consumer branch those records never reach `pm_measurements`. The envelope is frozen in HLD Appendix A.5 (`kind="records"` discriminator, field name `source_type`); this story implements the direct-store branch in the E1.S2 consumer.

**Size:** M

**Scope**
- In: `RecordsEnvelope` Pydantic model (Appendix A.5); `kind` routing in the S2 consumer (`job` -> existing adapter flow, `records` -> this branch); direct-store semantics: dictionary-map each record's `metric` via `VendorDictionary(vendor)`, ensure partitions per distinct month, batch `INSERT ... ON CONFLICT DO NOTHING`; NO `validate_params`, NO adapter registry lookup, NO `ingest_jobs` row (batches are fire-and-forget with logged stats).
- Out: the producer (E4.S5); dictionary seed rows for `ocudu` (they ride E4's contract doc follow-up; no seed exists for the reserved near-RT source, that vendor slot stays empty until the deferred near-RT track opens); any aggregation/rollup.

**Files**
- `submodule/maveric_platform_data_sim/app/ingest/models.py` (modify: add `RecordsEnvelope`, `InlineRecord`)
- `submodule/maveric_platform_data_sim/app/ingest/service.py` (modify: add `store_records(envelope)`)
- `submodule/maveric_platform_data_sim/app/ingest/consumer.py` (modify: route on `kind`; absent `kind` = `job`)
- `submodule/maveric_platform_data_sim/app/db/ingest_repo.py` (modify: reuse the batch PM writer)
- `submodule/maveric_platform_data_sim/tests/test_records_ingest.py` (create)

**Contract** (HLD Appendix A.5, verbatim - never accept `event`/`version` dialects or a `source` field name)

```json
{
  "schema": "maveric.ingest.pm.v1",
  "kind": "records",
  "tenant_id": "<uuid>",
  "batch_id": "<uuid4>",
  "source_type": "ocudu_ws",
  "vendor": "ocudu",
  "records": [
    {"dn": "gnb/3584/cell/12345", "metric": "DRB.UEThpDl", "value": 12.34, "unit": null,
     "granularity_s": 1, "ts": "2026-07-16T10:00:00Z", "labels": {"gnb_id": "3584"}}
  ]
}
```

Store rules: one `pm_measurements` row per record with `source = source_type`, `vendor = vendor`, `metric` mapped via `VendorDictionary(vendor)` (fallback `<vendor>:<source_metric>`), `day`/`tick` NULL (streaming sources carry no dataset-relative indices), `raw_ref` NULL, `labels` passed through plus `batch_id`. `tenant_id` must coerce to uuid; a non-uuid tenant fails the whole batch (logged, committed, skipped - poison tolerance). Replayed batches are idempotent via the PM PK.

**Acceptance criteria**
- A valid `kind="records"` message produces the expected `pm_measurements` rows (dictionary-mapped metric names, labels incl. `batch_id`); replaying it inserts zero additional rows.
- `kind="job"` messages (and messages with no `kind`) still flow through the S2 adapter path unchanged (regression).
- Malformed records envelopes (missing `source_type`, non-uuid `tenant_id`, empty `records`) are logged, committed, and skipped; the consumer keeps running.
- A message using the retired dialects (`event: "ingest.pm"` or a `source` field) fails validation and is skipped with a log line naming Appendix A.5.
- RLS: rows land under the envelope's `tenant_id` only (GUC set per batch, same pattern as `run_job`).

**Test plan**
- Unit (`uv run pytest` in data_sim): `test_records_ingest.py` - envelope validation happy/sad paths, kind routing (job vs records vs absent), dictionary mapping + fallback, idempotent replay, poison tolerance (mocked repo/producer).
- Integration (lab): publish a canned records batch with `kafka-console-producer`, assert rows via psql; then re-publish and assert zero new rows.

**Coding-agent prompt**

```
You are working in the CloudlyNet monorepo (repo root: cloudlynet_ai). Read
docs/task_docs/cloudlynet-rearchitecture/01-hld-frozen.md (§4.3 and Appendix A.5 - the
inline-records envelope is FROZEN there) and
docs/task_docs/cloudlynet-rearchitecture/epics/EPIC-1-data-platform.md story E1.S8. E1.S1-S3
are merged (canonical tables, ingest framework with the kind="job" consumer, VendorDictionary).

TASK: Implement the kind="records" branch of the maveric.ingest.pm.v1 consumer in
submodule/maveric_platform_data_sim.
1) app/ingest/models.py: RecordsEnvelope + InlineRecord Pydantic models exactly per Appendix
   A.5 ({schema, kind: Literal["records"], tenant_id uuid, batch_id, source_type, vendor,
   records[{dn, metric, value, unit, granularity_s, ts, labels}]}); reject envelopes carrying
   an "event" field or a "source" field name.
2) app/ingest/consumer.py: route on message "kind" - absent or "job" -> the existing run_job
   path; "records" -> service.store_records.
3) app/ingest/service.py store_records(envelope): set the tenant GUC, map each record's metric
   via VendorDictionary(envelope.vendor) with the '<vendor>:<metric>' fallback, build
   CanonicalPMRecord rows (source=source_type, day/tick/raw_ref None, labels + batch_id),
   ensure_pm_partition per distinct month, batch INSERT ... ON CONFLICT DO NOTHING via the
   existing ingest_repo writer. NO validate_params, NO adapter registry, NO ingest_jobs row;
   log stats (rows_in/rows_stored) per batch.
4) tests/test_records_ingest.py per the E1.S8 test plan.
CONSTRAINTS: the envelope shape is frozen (HLD Appendix A.5) - never accept or emit the retired
event/version/source dialects; poison messages are logged, committed, skipped; idempotent via
the PM PK; Pydantic-first, type hints, platform logger per CLAUDE.md.
DONE WHEN: `uv run pytest` passes in data_sim including test_records_ingest.py, and the lab
drill (publish canned batch -> rows land; replay -> zero new rows) succeeds.
```

---

## Rollout / migration notes

**Order** (each step independently shippable, no CI/CD change at any point):
1. E1.S1 schema (alembic in data_sim; manual mirror `011_data_platform_canonical.sql` for staged/prod per the repo's manual-migration practice). Purely additive: no existing table or reader is affected.
2. E1.S2 framework + topic. The consumer thread is inert until `KAFKA_BOOTSTRAP_SERVERS` + `INGEST_CONSUMER_ENABLED` are set (compose already wires data_sim `depends_on: kafka`; staging/prod get the env via the existing gateway-style secretData env edit, a config change, not a pipeline change). New topic rides `scripts/kafka/init-topics.sh` locally and the existing kafka chart topics-job in cluster (values-level addition).
3. E1.S3 adapter + dictionary seed; E1.S5 query APIs; E1.S6 stubs/docs. All additive.
4. E1.S4 legacy route goes live on data_sim but is NOT gateway-reachable until cutover (dark launch); smo_sim keeps serving production traffic. Backward-compat shims active: `NDT_FEATURE_BUILDER_MODE=legacy_inline` reproduces today's derived artifacts exactly (determinism fixtures), so BDT/rApp/frontend see no difference regardless of which service handled an upload.
5. E1.S7 cutover: gateway re-point (E0's split), soak, then HANDOVER to E4.S6 for the smo_sim router/runner deletion (E4.S6 is the sole decommission owner). Rollback at any point before the E4.S6 deletion is a pure gateway route flip.
6. Data migration: none required for correctness (no historical PM exists in Postgres). Optional backfill from S3 `pm_hourly.csv` audits via `scripts/backfill_pm_from_audit.py`, idempotent, per-tenant.
7. E2 handoff: when the bdt_engine feature builder ships against the seam defined in E1.S4 (POST `/v1/tenants/{t}/ndt/feature-builds`, implemented exactly by E2.S4), the explicit cutover story E2.S9 flips `NDT_FEATURE_BUILDER_MODE=ndt_api`, soaks, and deletes `app/ingest/legacy_builder/`. The `labels.upload_id` on every canonical row plus the `/data/pm` labels filter is the builder's data path; both ship in this epic. Migration numbering note (HLD Appendix A.6): this epic owns `011_data_platform_canonical.sql`; 012/013 are E4's, 014 is E2's, 015 is E5's - apply in numeric order.

**Transition invariants (must hold at every step):** `POST /v1/tenants/{t}/custom/nybsys/uploads` request/response byte-compatible; derived IDs `{upload_id}-topology` / `{upload_id}-dataset`; S3 keys `{tenant}/baselines/{bid}/*`, `{tenant}/ue/{did}/synthetic_dataset.csv`, `{tenant}/pm-data-ingestion/{uid}/*` unchanged; shared tables `baselines`/`ue_datasets`/`nybsys_uploads` schema untouched; `tenants.feature_flags['nybsys']` gate honored; no new deployable/port/image.

## Epic-level risks

1. **Dual-writer window on `nybsys_uploads`/`baselines`/`ue_datasets`.** Between S4 dark-launch and S7 cutover, both services CAN write these tables. Mitigation: gateway routes to exactly one service at a time; dark-launch testing uses dedicated tenants; runbook verifies single-writer provenance before decommission.
2. **Determinism drift in the lifted stages 3-6.** If the `legacy_builder` lift diverges (pandas version, import order of RNG consumption), derived CSVs change and BDT retrains differently. Mitigation: hash-compare fixtures generated by smo_sim are a hard acceptance gate; the lift is verbatim, refactor-minimal.
3. **Envelope byte-compatibility subtleties.** smo_sim emits `Z`-suffixed UTC timestamps and `{items,total}` pagination; data_sim's native envelope differs in timestamp format. Mitigation: ported `SuccessEnvelope` for the `/custom` routes + recorded-fixture parity tests including error shapes.
4. **RLS on partitioned tables.** Policies on the parent do not automatically cover direct-partition access. Mitigation: `ensure_pm_partition()` applies ENABLE+FORCE+policy to every partition it creates; all app SQL targets the parent; superuser-DSN-disables-RLS footgun re-documented in the bundle.
5. **kafka-python consumer in a uvicorn process.** A blocking poll loop in a daemon thread must not wedge shutdown or starve the event loop. Mitigation: dedicated thread with stop-event + consumer close on FastAPI shutdown, poll timeouts, and the framework works with the consumer disabled (INGEST_CONSUMER_ENABLED=false) as a kill switch.
6. **Feature-builder seam is a new cross-epic contract.** E2 must implement `POST /v1/tenants/{t}/ndt/feature-builds` exactly as defined in E1.S4; drift breaks the `ndt_api` mode. Mitigation: the seam contract lives in this epic + `artifacts/data-platform/` and E1 ships a stub-server test double; `legacy_inline` remains a working fallback indefinitely.
7. **Backfill data quality.** Audit CSVs predate the dictionary; deleted uploads are unrecoverable. Mitigation: backfill is optional, per-tenant, idempotent, dry-runnable, and labeled (`labels.backfill=true`) so consumers can exclude it.
8. **Claims exposure via new docs.** The adapter contract docs name 3GPP/VES/OCUDU surfaces. Mitigation: wording rules baked into E1.S6 acceptance (no O-RAN/O1/RIC/SMO/ONAP compliance claims; "parses the TS 32.435 XML PM file format" phrasing; no em dashes), plus E6's claims re-verification gate.
