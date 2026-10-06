# Data Platform bundle

The canonical PM/FM/CM store and the ingestion framework that fills it. Owned by `data_sim`
(frozen HLD 4.3). Created by EPIC-1.

| Document | Covers |
| --- | --- |
| [`canonical-schema.md`](./canonical-schema.md) | Table semantics, the `dn` convention, label conventions, partitioning, idempotency keys |
| [`ingest-topic-contract.md`](./ingest-topic-contract.md) | The `maveric.ingest.pm.v1` message contract, durability, consumer-group scale-out |
| [`adapters/`](./adapters/) | One contract document per source adapter, implemented or planned |

## The canonical vocabulary rule

Metric names use the TS 28.552 name **where one maps cleanly**. Where it does not, the canonical
name keeps a `<vendor>:` prefix.

This is deliberate and it is the most important rule in the bundle. A vendor counter renamed to a
standard name it does not actually implement is worse than an obviously vendor-scoped one, because
downstream code will treat it as comparable across vendors when it is not. An unmapped metric is
never dropped: it falls back to `<vendor>:<source_metric>` and lands in the store, so reclassifying
later is a dictionary UPDATE plus a re-ingest rather than lost data.

Mappings live in `public.vendor_dictionaries` (global, no RLS) and are seeded per vendor by an
alembic revision.

## Scale-out

No new deployable. The ingest consumer is a daemon thread inside the `data_sim` API process and
joins consumer group `data-sim-ingest`. Running N replicas gives N consumers sharing the topic's
partitions; messages keyed by `tenant_id` keep one tenant's work ordered. Throughput is raised by
adding partitions, not services.

## Scope boundary

This bundle describes ingestion and storage. It does not describe protocol implementations. Nothing
here is an O-RAN, O1, A1, E2 or RIC interface, and nothing here claims conformance to one. See
`artifacts/marketing/claims-guardrails.md`.

---

## Cutover and decommission (EPIC-1.S7)

Durable record of the transition. The step-by-step runbook with rollbacks lives at
`docs/task_docs/cloudlynet-rearchitecture/epics/E1-cutover-runbook.md` (local, gitignored); the
parts that must survive are here.

### Order

1. Deploy E1.S1-S6 to lab; keep E0's gateway route split available but **not** flipped.
2. Dark-launch soak: one production-shaped upload straight at data_sim (`:8003`, `X-API-Key`).
   Verify canonical PM rows, the four derived artifacts, and that BDT can train on the produced
   baseline.
3. Flip the gateway: `/v1/tenants/:tid/custom/nybsys/uploads*` to DATA (with `DATA_API_KEY`).
   **Everything else under `/custom/**` stays on SMO** (edge-devices, devices, commands,
   recommendations). Rollback is flipping the mapping back; the smo_sim path stays fully functional
   until step 5.
4. Soak: frontend regression on the PM-ingestion page (upload, poll, list, delete including
   `delete_derived`). Confirm `nybsys_uploads` is now written only by data_sim.
5. **Decommission smo_sim's upload path: HANDED OVER to E4.S6.**
6. Optional per-tenant backfill (below).

### The step-5 handover

**E4.S6 is the sole owner of every smo_sim deletion.** EPIC-1 deletes nothing in smo_sim, and
`git -C submodule/maveric_platform_smo_sim status` is clean at the end of this epic.

E4.S6 must not start until step 4's soak is confirmed. What it removes:
`app/api/v1/custom/nybsys/router.py` and `schemas.py`, `app/services/nybsys_runner.py`, the
`reset_stale_uploads` startup sweep, and conditionally `app/lib/nybsys/`.

| Gate | Value |
| --- | --- |
| Soak confirmed on | _pending_ |
| Confirmed by | _pending_ |

What smo_sim keeps regardless: `/baselines`, `/ue-data`, and the whole NanoLink device plane.

**Shared tables are never dropped.** `nybsys_uploads`, `baselines` and `ue_datasets` stay exactly as
they are (HLD 3.3), along with the S3 key conventions, because bdt_engine and rApp read them
directly.

### Backfill

```bash
python scripts/backfill_pm_from_audit.py --tenant <uuid> [--upload <id>] [--dry-run]
```

Replays `{tenant}/pm-data-ingestion/*/pm_hourly.csv` audit CSVs into `pm_measurements` with
`labels.backfill = true`. Idempotent: it goes through the same canonical writer, so the PM primary
key makes a re-run insert zero rows.

Two honest limits:

- **The audit CSV is the only historical PM source.** No PM counter reached Postgres before this
  epic, so an upload whose audit CSV was deleted is unrecoverable. Those are logged and skipped.
- **The audit CSV stores the 0-based `day` index, not dates.** Real timestamps are reconstructed
  from `nybsys_uploads.date_range`. An upload with no usable `date_range`, or one whose `num_days`
  disagrees with the min-to-max span (implying gaps), is **skipped rather than mis-dated**: a wrong
  timestamp is worse than a missing row.
