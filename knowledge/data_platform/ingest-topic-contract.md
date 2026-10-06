# `maveric.ingest.pm.v1` topic contract

Frozen in HLD 4.1 (topic name) and Appendix A.5 (message shapes). Implemented by EPIC-1.S2
(`kind="job"`) and EPIC-1.S8 (`kind="records"`).

Kafka message key is the `tenant_id` bytes, so one tenant's messages land on one partition and stay
ordered relative to each other.

## Two message kinds, one discriminator

The discriminator is always `kind`. The source field is always `source_type`. A message with **no**
`kind` is treated as `kind="job"` for backward compatibility with messages published before the
discriminator existed. Retired dialects (an `event` field, or a bare `source` instead of
`source_type`) fail validation and are skipped with a log line naming Appendix A.5. Accepting a
stale dialect leniently is how two incompatible producers both appear to work while writing
different things.

### `kind="job"`

```json
{
  "schema": "maveric.ingest.pm.v1",
  "kind": "job",
  "tenant_id": "<uuid>",
  "job_id": "upl-2026-07-01",
  "source_type": "nybsys_pm_csv",
  "params": { "...adapter-specific, validated by adapter.validate_params..." },
  "requested_at": "2026-07-16T10:00:00Z"
}
```

Drives the adapter flow: claim, parse, store, finalize. Tracked by an `ingest_jobs` row.

### `kind="records"`

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

Stored directly: no adapter lookup, no `validate_params`, no `ingest_jobs` row. Streaming batches
are fire-and-forget because the PM primary key already makes a replay a no-op, so there is nothing
to track. `metric` is the SOURCE name and is mapped at store time; `day` and `tick` are NULL because
streaming sources carry no dataset-relative indices.

## Durability

The ladder that replaces smo_sim's in-process executor, which lost in-flight work on restart:

1. The API inserts a `queued` row, **then** publishes. If the publish fails the row is deleted, so
   a job never exists without a message to drive it.
2. The consumer runs with `enable_auto_commit=False` and commits the offset **only after** a
   terminal status is written.
3. Crash before the commit: Kafka redelivers, the claim CAS (`queued|running -> running`) re-admits
   the job, and canonical writes are `ON CONFLICT DO NOTHING`, so the replay is harmless.
4. Crash after the terminal write but before the commit: redelivery hits the terminal-skip and just
   commits.

Poison tolerance: undecodable, malformed and unknown-`kind` messages are logged and **committed**,
never retried, so one bad message cannot wedge a partition. A storage error is the exception: it
withholds the commit, because it is usually transient and the batch should be retried.

## Scale-out

Consumer group `data-sim-ingest`. N `data_sim` replicas give N consumers over the topic's
partitions. Raise throughput with `INGEST_PM_TOPIC_PARTITIONS` on the existing topics job. No new
deployable is ever required.

## Provisioning

`scripts/kafka/init-topics.sh` creates the topic. **E5.S1 is the owner-of-record** for topic
provisioning; E1.S2 added the line only because E5.S1 had not landed. If both are present,
deduplicate rather than keeping two entries.
