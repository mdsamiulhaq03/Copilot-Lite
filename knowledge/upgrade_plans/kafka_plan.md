# Kafka Plan

Date: 2026-03-12
Status: Initial implementation completed; future SaaS scaling backlog remains open

## Scope

This document is now the implementation-state reference for Kafka-backed training across:

- `submodule/maveric_platform_rapp`
- `submodule/maveric_platform_bdt_engine`
- `submodule/maveric-deployment/argocd/maveric_platform_kafka`
- `submodule/maveric-deployment/argocd/staging-maveric_platform_kafka`
- `submodule/maveric-deployment/argocd/maveric-zookeeper`
- `submodule/maveric-deployment/argocd/staging-maveric-zookeeper`
- local Docker Compose (`docker-compose.yaml` — one consolidated file, profiles: infra default / apps / edgeagent / data-loaders)

## Inputs Reviewed

- Local repo code and deployment manifests
- `https://github.com/CloudlyIO/cloudlynet_ai/issues/102`
- `https://github.com/CloudlyIO/cloudlynet_ai/issues/103`
- `https://github.com/CloudlyIO/cloudlynet_ai/issues/107`
- `https://github.com/CloudlyIO/maveric_platform_rapp/pull/34`
- Artifact branches:
  - `rapp-7/kafka-scaling-scripts`
  - `rapp-7/kafka-scripts-v2`

## Executive Summary

1. The core direction from the issue threads was correct: Kafka should own training parallelism primarily through topic partitions plus worker replicas, not through a large in-process thread pool inside one consumer.
2. The merged rApp worker hardening from PR #34 is now reflected in the repo: partition-aware pause/resume, exact-offset commit, idempotent terminal-state skip, and explicit Kafka timeout knobs.
3. BDT has been aligned to the same consumer-loop model: raw polling, pause/resume, seek-back on overflow, exact per-record commits, producer `acks=all`, retries, and optional worker metrics.
4. Deployment assets now set an initial operational baseline instead of leaving Kafka scale to tribal knowledge:
   - `maveric.rapp.train.v1` starts at 2 partitions
   - `maveric.bdt.train.v1` starts at 2 partitions
   - rApp worker chart starts at 2 replicas with `RAPP_WORKER_MAX_JOBS=1`
   - BDT worker charts start at 2 replicas with `BDT_WORKER_CONCURRENCY=1`
5. Local Docker Compose now mirrors this better:
   - Kafka and ZooKeeper use named volumes
   - `kafka-init` creates or expands topics before workers start
   - worker services no longer block scaling through `container_name`
6. This is only the first rollout. Two partitions do not solve long-term SaaS growth. Two partitions mean at most two concurrent rApp trainings per consumer group for that topic, not two tenants, not two organizations, and not unlimited future scale.

## What Kafka Knobs Mean for This Platform

For this platform, one Kafka message maps to one long-running training job. That makes a few Kafka settings materially more important than others.

| Knob | What it controls | Why it matters here | Current direction |
| --- | --- | --- | --- |
| Partitions | Maximum parallel consumers per topic per consumer group | One partition can only be actively consumed by one group member at a time | Use partitions to define the initial training concurrency ceiling |
| Worker replicas | Number of consumer processes | True parallelism only appears when replicas can own different partitions | Scale replicas up to, but not blindly past, partition count |
| `enable_auto_commit` | Background offset commits | Unsafe for 2-3 hour jobs because Kafka can ack work before training finishes | Keep `False` |
| `max_poll_records` | Records returned per poll | Fetching more than the worker can safely own increases commit and rebalance risk | Keep `1` for long-running training |
| `max_poll_interval_ms` | Max time between polls before consumer eviction | A blocked loop on long jobs can trigger rebalance | Keep polling with pause/resume and set a large explicit timeout |
| `session_timeout_ms` | Failure detection window | Too low causes false consumer death under heavy work | Set explicitly in Helm/compose |
| `heartbeat_interval_ms` | Heartbeat cadence | Must stay safely below session timeout | Set explicitly with session timeout |
| Producer partitioner | Where jobs land | More partitions are useless if every event lands on one partition | Use round-robin while cross-job ordering is not required |
| `acks` / retries | Produce durability | Losing a train request is expensive | Use `acks=all` with retries |
| Producer `batch_size` / `linger_ms` | Throughput batching | Low impact because train events are small and sparse | Leave conservative unless profiling shows need |
| Retention | How long Kafka keeps unconsumed messages | Helps redelivery and debugging | Set explicitly in topic/broker config |
| DLQ / retry topics | Poison-message handling | Needed for cleaner failure isolation later | Future enhancement |

## Current Implemented Architecture

### rApp

- Topic: `maveric.rapp.train.v1`
- Initial partition count: `2`
- Initial worker replicas: `2`
- Initial jobs per pod: `1`
- Worker behavior:
  - `enable_auto_commit=False`
  - raw Kafka `poll()` loop
  - partition pause/resume while work is in flight
  - exact offset commit (`offset + 1`) after completion
  - idempotent skip when the model is already `ready|failed`
  - producer round-robin partitioning with `acks=all`, retries
  - explicit `KAFKA_MAX_POLL_INTERVAL_MS`, `KAFKA_SESSION_TIMEOUT_MS`, `KAFKA_HEARTBEAT_INTERVAL_MS`

### BDT

- Topic: `maveric.bdt.train.v1`
- Initial partition count: `2`
- Initial worker replicas: `2`
- Initial per-pod concurrency: `1`
- Worker behavior:
  - `enable_auto_commit=False`
  - raw Kafka `poll()` loop
  - pause/resume and seek-back handling when the worker is full
  - exact offset commit (`offset + 1`) after completion
  - idempotent skip for terminal-state redeliveries
  - producer round-robin partitioning with `acks=all`, retries
  - explicit `KAFKA_MAX_POLL_INTERVAL_MS`, `KAFKA_SESSION_TIMEOUT_MS`, `KAFKA_HEARTBEAT_INTERVAL_MS`
  - optional `WORKER_METRICS_PORT` for Prometheus exposure

### Deployment baseline

- Kafka and ZooKeeper now use persistent storage in both chart tracks. The current prod track reuses the shared `efs-pvc` claim already mounted by rApp/BDT, isolates broker/state data under `kafka/`, `zookeeper/data`, and `zookeeper/log`, and permission-bootstraps those shared directories before the Confluent `uid=1000` containers start; the staging track still renders chart-managed PVCs.
- Worker timeout env defaults are now stored as quoted decimal strings in Helm values so rendered manifests keep `14400000` instead of Helm's scientific-notation form (`1.44e+07`), which the current BDT/rApp worker images reject during consumer init.
- Kafka chart now consumes the values-driven broker config that previously existed largely as dead configuration.
- Kafka chart now runs a Helm hook job to create or expand the training topics.
- rApp and BDT worker charts now expose replica and Kafka timeout settings as declarative values instead of leaving them hardcoded or implicit.
- Local Docker Compose now runs a topic-init step and persists Kafka/ZooKeeper data.

## How Partition-Driven Parallelism Works Here

### Why partitions matter

- A topic with 1 partition can run only 1 active consumer for that partition inside a consumer group.
- A topic with 2 partitions can run up to 2 active consumers in that group.
- If each worker pod runs at most one long job at a time, then 2 partitions plus 2 worker pods means up to 2 concurrent jobs for that topic.

### Why internal thread pools are not the scaling primitive

Large in-process concurrency inside a single consumer creates harder correctness rules:

- do not commit past an unfinished lower offset
- do not stop polling long enough to trigger rebalance
- do not lose fetched-but-not-yet-dispatched work

That is why the platform has moved toward:

- one fetched record per poll
- manual exact-offset commits
- pause/resume instead of blocking the poll loop
- default per-pod concurrency of `1`
- scaling by partitions plus replicas

### Batch-size nuance

For this workload, "batch size" mostly means consumer fetch size, not producer throughput batching.

- Consumer side: `max_poll_records=1` remains the safe default for long-running training.
- Producer side: `batch_size` and `linger_ms` are not the primary tuning lever because the system emits small, infrequent control messages rather than a high-throughput stream.

## Review of `maveric_platform_rapp#34`

PR #34 was the correct technical direction, and it is now effectively the baseline behavior in the repo.

### What it fixed

- The worker no longer needs to block the main loop waiting for a free slot.
- Offset commit is exact, not just "commit current consumer position".
- Terminal-state redeliveries do not retrain already-finished models.
- Producer durability is stronger (`acks=all`, retries).
- Timeout knobs are explicit instead of relying on brittle defaults.

### Remaining caveat

The PR direction is correct, but the current rollout should still be treated as the initial scale tier:

- it is single-broker Kafka today
- replication factor is still effectively `1`
- there is not yet lag-based autoscaling
- there is not yet a retry-topic / DLQ strategy

So the worker-side logic is now materially better, but the cluster-level Kafka story is not "done".

## rApp Audit and Result

### Issue before hardening

The original risk was auto-commit acknowledging work before a 2-3 hour training finished. A pod crash after offset advance could permanently lose a job.

### Current result

- Manual commit is retained.
- Partition pause/resume keeps the consumer alive without blocking its poll loop.
- Exact per-message commits remove the "current position" ambiguity.
- Idempotency skip prevents repeated retraining of already terminal jobs.
- Worker chart now exposes a direct partition-to-replica scaling model.

### Operational meaning

rApp is now ready for the initial 2-partition / 2-replica rollout. It is not yet the final multi-tenant scale ceiling.

## BDT Audit and Result

### Issue before hardening

BDT already had better commit-order tracking than rApp, but it still mixed Kafka consumption with an older in-process concurrency model and did not expose the same worker-loop hardening or producer durability settings.

### Current result

- BDT now uses the same raw-poll, pause/resume, exact-offset pattern.
- The idle-topic commit gap is closed because completion handling is no longer tied to a later unrelated poll path.
- Overflow now seeks back instead of "owning" a message the worker cannot yet run.
- Producer durability and timeout settings now match the platform direction.
- Targeted worker-loop tests were added around dispatch, overflow, commit, and invalid payload handling.

### Operational meaning

BDT now fits the same deployment model as rApp: low per-pod concurrency and scale-out through partitions plus replicas.

## Kafka Helm and ZooKeeper Helm

### What is implemented now

- Prod and staging Kafka charts:
  - persistent broker storage
  - prod-track support for reusing the shared `efs-pvc` claim via `persistence.existingClaim`
  - writable-subpath bootstrap for shared-claim mode so Kafka can write `/var/lib/kafka/data`
  - values-driven runtime config wired into templates
  - topic-management hook job
  - initial training topics and partition counts in values
- Prod and staging ZooKeeper charts:
  - persistent data and log storage
  - prod-track support for reusing the shared `efs-pvc` claim via `persistence.existingClaim`
  - writable-subpath bootstrap for shared-claim mode so ZooKeeper can pass the `/var/lib/zookeeper/{data,log}` preflight
  - values-driven runtime config wired into templates
- rApp chart:
  - explicit worker replica settings
  - explicit Kafka timeout envs
  - `RAPP_WORKER_MAX_JOBS`
- BDT engine and BDT worker charts:
  - explicit worker replicas
  - `BDT_WORKER_CONCURRENCY`
  - explicit Kafka timeout envs
  - worker metrics port and health probes

### What is still not enough for long-term production scale

- Kafka is still a single-broker `Deployment`, not a multi-broker cluster.
- Replication factor is not providing broker-level fault tolerance yet.
- Partitions are only useful within the limits of one broker’s storage and throughput.
- There is no lag-based autoscaler yet.

## Local Docker Compose Status

### Implemented now

- Kafka and ZooKeeper volumes preserve local topic and broker state.
- `kafka-init` creates or expands training topics before workers start.
- Worker services can be scaled because `container_name` was removed.
- Worker envs now expose the same timeout and concurrency knobs used by Helm.

### Why this matters

Without local volumes and topic bootstrap, developers could not reproduce partition-count behavior reliably. Local testing now better matches the production intent.

## SaaS Scaling Scope Beyond The Initial Baseline

### Direct answer

No. Two partitions are not enough to represent the long-term scaling strategy for a SaaS platform.

Two partitions only mean:

- up to 2 concurrent rApp trainings for that consumer group on that topic
- no built-in fairness between tenants
- no headroom for noisy-neighbor isolation
- limited recovery bandwidth during backlog bursts

It does not mean:

- support for only 2 tenants
- support for only 2 users
- automatic scale for future customer growth

### Recommended future scaling path

1. Keep the current rollout as the first operational tier:
   - rApp `2` partitions / `2` worker replicas
   - BDT `2` partitions / `2` worker replicas
2. Add a monotonic partition growth policy by environment:
   - next likely tiers are `8`, `16`, then `32`, based on measured concurrent training demand and lag
3. Move from single-broker Kafka to a proper multi-broker deployment:
   - at least 3 brokers
   - replication factor `3`
   - min in-sync replicas `2`
   - persistent volumes sized for replay and retention windows
4. Add lag-based autoscaling:
   - KEDA or equivalent on worker consumer lag
   - HPA bounds aligned with partition counts
5. Add fairness controls:
   - queue admission limits per tenant
   - per-tenant or per-priority quotas
   - optional priority topics for premium or urgent work
6. Consider workload separation when volume increases:
   - separate rApp and BDT topics already exist
   - future split by training class, model family, or priority if hot spots emerge
7. Add failure-isolation patterns:
   - retry topic
   - DLQ
   - stale-job reaper / heartbeat supervision for jobs left in `training`

### Tenant-keying note

Do not key all training jobs by `tenant_id` by default.

That would serialize one tenant’s workload onto one partition and can reduce throughput badly. Use round-robin unless there is a strict per-tenant ordering requirement that outweighs the concurrency loss.

## Recommended Next Production Steps

1. Deploy the current Helm changes to staging and validate:
   - topic counts
   - worker replica ownership
   - consumer lag behavior
   - restart / redelivery behavior
2. Load test with realistic long-running jobs:
   - confirm 2 concurrent rApp jobs and 2 concurrent BDT jobs behave as expected
   - verify rebalance and restart behavior during active training
3. Decide the next partition tier from observed backlog, not guesswork.
4. Plan the broker migration before calling Kafka scale-out "production complete".

## Task Status Table

| Planned task | Status | Submodule |
| --- | --- | --- |
| Implement partition-aware pause/resume, exact-offset commit, idempotent redelivery handling, and timeout tuning for rApp worker | Completed | `submodule/maveric_platform_rapp` |
| Implement matching Kafka worker hardening for BDT, including producer durability and worker-loop tests | Completed | `submodule/maveric_platform_bdt_engine` |
| Expose rApp worker replicas and Kafka timeout knobs through Helm values | Completed | `submodule/maveric-deployment/argocd/maveric_platform_rapp`, `submodule/maveric-deployment/argocd/staging-maveric_platform_rapp` |
| Expose BDT worker replicas, concurrency, Kafka timeout knobs, and metrics through Helm values | Completed | `submodule/maveric-deployment/argocd/maveric_platform_bdt_engine`, `submodule/maveric-deployment/argocd/staging-maveric_platform_bdt_engine`, `submodule/maveric-deployment/argocd/maveric_platform_bdt_worker`, `submodule/maveric-deployment/argocd/staging-maveric_platform_bdt_worker` |
| Make Kafka Helm declarative for topic partitions and persistent broker storage | Completed (initial single-broker rollout) | `submodule/maveric-deployment/argocd/maveric_platform_kafka`, `submodule/maveric-deployment/argocd/staging-maveric_platform_kafka` |
| Make ZooKeeper Helm persistent and values-driven | Completed (initial single-node rollout) | `submodule/maveric-deployment/argocd/maveric-zookeeper`, `submodule/maveric-deployment/argocd/staging-maveric-zookeeper` |
| Replicate Kafka topic-init and persistence behavior in local Docker Compose | Completed | `docker-compose.yaml` (consolidated, profiled), `scripts/kafka/init-topics.sh` |
| Document current Kafka behavior, SaaS scaling implications, and rollout status | Completed | `kafka_plan.md`, root/service/deployment docs |
| Add multi-broker Kafka, replication factor >1, and broker-level HA | Planned | `submodule/maveric-deployment/argocd/maveric_platform_kafka`, `submodule/maveric-deployment/argocd/staging-maveric_platform_kafka` |
| Add lag-based autoscaling for workers | Planned | `submodule/maveric-deployment` |
| Add retry topics, DLQ handling, and stale-job supervision | Planned | `submodule/maveric_platform_rapp`, `submodule/maveric_platform_bdt_engine`, `submodule/maveric-deployment` |
| Add tenant fairness / quota controls for long-term SaaS growth | Planned | Platform-wide |
