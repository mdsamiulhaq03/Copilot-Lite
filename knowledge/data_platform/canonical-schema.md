# Canonical schema

Created by EPIC-1.S1. Authoritative migration:
`submodule/maveric_platform_data_sim/alembic/versions/0001_data_platform_canonical.py`, mirrored
for manual execution at `artifacts/migration/011_data_platform_canonical.sql`.

Five tables. Four are tenant-scoped with RLS **enabled and forced**; `vendor_dictionaries` is
global with none.

| Table | Holds | Primary key |
| --- | --- | --- |
| `pm_measurements` | performance counters, monthly RANGE partitions on `ts` | `(tenant_id, source, dn, metric, ts)` |
| `fm_alarms` | faults | `(tenant_id, source, dn, alarm_id, raised_at)` |
| `cm_records` | configuration snapshots | `(tenant_id, source, dn, captured_at)` |
| `ingest_jobs` | one row per ingest job | `(tenant_id, job_id)` |
| `vendor_dictionaries` | vendor to canonical metric mapping | `(vendor, source_metric)` |

## The `dn` convention

`dn` is the distinguished name of the measured object. For NanoLink femtocells it is
`site=<site_id>,cell=<cell_id>`. Streaming sources use their own native form (for example
`gnb/<gnb_id>/cell/<cell_id>`), which is why `dn` is free text rather than a parsed structure:
forcing one vendor's addressing onto another loses information.

`dn_prefix` filtering on the read API relies on this being a stable, left-anchored string.

## Labels

`labels` is a JSONB bag with a GIN index. Conventions:

- `upload_id` on rows produced by a NanoLink upload. **This is the E2 feature builder's query
  handle** and the reason `GET /data/pm?upload_id=` exists. Losing it orphans the rows.
- `batch_id` on rows from an inline-records batch, so a batch stays traceable after the fact.
- `site_id` / `cell_id` as the decomposed parts of `dn`, for convenience.

## Partitioning

`pm_measurements` is RANGE-partitioned monthly on `ts`. Writers call
`public.ensure_pm_partition(ts)` before inserting; an insert into a month with no partition fails.

`ensure_pm_partition` is `SECURITY DEFINER` with `SET search_path = public, pg_temp`. Creating a
partition requires `CREATE` on schema `public`, which unprivileged ingest roles must not hold;
definer rights expose exactly that one narrow operation instead of a broad grant. It also applies
ENABLE + FORCE RLS and the tenant policy to each new partition, because a partition created without
a policy is directly queryable and would bypass tenant isolation.

## Idempotency

The PM primary key **is** the idempotency anchor. Writers use
`INSERT ... ON CONFLICT DO NOTHING`, which is what makes a redelivered Kafka message safe: a
replayed job or batch inserts zero additional rows. Ingest correctness therefore does not depend on
exactly-once delivery, which Kafka does not provide.

## Value typing

`pm_measurements.value` is `double precision`, not text. This is not cosmetic: the pre-canonical
`device_kpis` table stored values as strings, which is why several dashboard charts could not plot
them.
