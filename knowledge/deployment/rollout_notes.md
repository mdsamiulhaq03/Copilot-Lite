# Deployment Rollout Notes

Current-state notes on how charts, secrets, and migration hooks are wired.
Relocated from the root `README.md` doc index so the deployment bundle owns them.

## Staging retirement (2026-08-10)

- Staging infra was **deleted on 2026-08-10**. All `staging-*` charts and Jenkins pipelines were
  moved to `backup/argocd/` and `backup/jenkins/` in `maveric-deployment` — preserved but
  unmaintained. Only the production-track charts under `argocd/` and pipelines under `jenkins/`
  are live.

## Chart locations

| Asset | Path (in `submodule/maveric-deployment`) |
|---|---|
| Copilot chart | `argocd/maveric_platform_copilot` |
| Postgres chart | `argocd/maveric_platform_postgres` |
| Copilot Jenkins pipeline | `jenkins/maveric_platform_copilot.groovy` |
| Retired staging charts/pipelines | `backup/argocd/`, `backup/jenkins/` |

## Secrets

- Prod app charts keep **chart-specific** Helm secrets for frontend, BDT engine,
  BDT worker, rApp, Data Sim, and SMO Sim, so expanded runtime env payloads do not overwrite
  each other through a shared `maveric-aws` secret.
- Secret names follow a per-chart scheme: `maveric-aws-frontend`,
  `maveric-aws-bdt-engine`, `maveric-aws-bdt-worker`, `maveric-aws-data-sim`, `maveric-aws-rapp`,
  `maveric-aws-smo-sim`. Charts require an explicit `secretName` (`values.yaml`) and do not fall
  back to a shared `maveric-aws` object. Copilot migration uses a separate
  `maveric-aws-copilot-migration` (owner/app creds) plus the superuser `postgres-secret`.
- Gateway deployment values must keep `DEV_BYPASS_JWT=false` in cluster environments and carry
  matching `BDT_API_KEY` / `RAPP_API_KEY` / `SMO_API_KEY` / `DATA_API_KEY` secrets for internal
  proxy hops.
- Re-architecture key parity (see `env_variable.md`): rApp/data-sim `NDT_API_KEY` =
  bdt-engine `API_KEY` = gateway `BDT_API_KEY`; BDT engine/worker `DATA_PLATFORM_API_KEY` =
  data-sim `API_KEY` = gateway `DATA_API_KEY`.

## Migration hooks

- The postgres chart packages `files/006`–`016` (no `017+`; `007` is the trial seed) as ArgoCD
  `Sync` hook migrations against the shared `maveric` database, so cluster rollout of the
  Nybsys/NanoLink, trial-signup, and re-architecture deltas needs no separate manual `psql` step.
- Hook order by `sync-wave`:
  - wave 1 — `copilot-bootstrap-job` (copilot DB/roles; see Copilot section);
  - wave 2 — `*-nybsys-migration` applies `006_nybsys_ingestion.sql` →
    `008_nybsys_rng_seed.sql` → `009_nybsys_nanolink.sql` → `010_nybsys_cwmp_id_rename.sql`;
  - wave 3 — `*-rearch-migration` applies the re-architecture migrations
    `011_data_platform_canonical.sql` → `012_drop_e2_r1.sql` → `013_commands_loop_columns.sql` →
    `014_ndt_loop.sql` → `015_ndt_loop_policy.sql` → `016_pm_ts_browse_index.sql`, running as the
    **postgres superuser** (`015` requires superuser/BYPASSRLS and hard-depends on `014`). All
    files are idempotent and the hook re-runs on every sync, which also self-heals `012` if a
    pre-re-architecture smo-sim pod recreated the dropped E2/R1 tables before its new image
    rolled out;
  - wave 4 — `*-trial-migration` applies `007_trial_org.sql` on its own.
- The NanoLink `009` migration repairs defaults such as `edge_devices.status DEFAULT 'pending'`
  when the table already exists from an earlier partial rollout.
- Copilot schema rollout is a separate two-hook chain in `maveric_platform_copilot`, ordered by
  Argo `sync-wave`: wave 1 migration job runs `01-copilot-tenant-upgrade.sql` (tenant isolation) →
  `02-copilot-schema.sql` (schema/tables/indexes/triggers/grants) → `03-copilot-rls.sql`
  (conversation RLS); wave 2 runs the knowledge-base job; both precede the backend/MCP
  Deployments. Cross-chart refresh order: postgres first, then copilot.

## NanoLink enrollment

- The SMO Sim chart sets `PUBLIC_BASE_URL=https://<platform-host>/` so production enrollment
  tokens carry the public origin.
- The frontend ingress chart routes `/v1` on `<platform-host>` to the gateway **before** the
  frontend catch-all, so edge agents can reach `/v1/agent/**` from the public CloudlyNet origin.
- Existing edge devices must have their keys regenerated after an SMO chart sync that changes
  `PUBLIC_BASE_URL`, so their next issued token carries the corrected `base_url`.

## Copilot

- Production runtime values live in `argocd/maveric_platform_copilot/values.yaml` with concrete
  asyncpg DSNs plus shared Redis/S3/gateway endpoints. Provision the dedicated copilot DB, roles,
  and grants first using [`artifacts/copilot/copilot_prod.md`](../copilot/copilot_prod.md).
- The dedicated copilot DB is `netai_copilot`, provisioned by the postgres `copilot-bootstrap-job`
  with owner role `netai_copilot_owner` (migration) and restricted app role `netai_copilot_app`
  (runtime); that job also `REVOKE`s public access on the shared `maveric` database before cutover.
- The production chart ships `files/knowledge_base.tgz` plus a `copilot-backend-knowledge-base`
  ArgoCD `Sync` hook job that expands the curated KB snapshot, then runs
  `scripts/ingest_knowledge_base.py` followed by `scripts/contextualize_chunks.py --skip-existing`.
- Its schema pack creates `conversation.guardrail_decision_log`, matching the guardrail audit
  logger used by the running backend.
- The gateway's production copilot upstream resolves through the copilot service FQDN
  `http://copilot-backend.<namespace>.svc.cluster.local:8000`, derived from the copilot chart
  service template/helper.

## Startup gating

- The gateway production chart blocks startup on `POSTGRES_DSN` readiness via `pg_isready`.
- The pgAdmin chart preloads the platform Postgres server definition through `servers.json`
  instead of requiring manual server registration after restart.
- The pgAdmin chart adds a `startupProbe` (`periodSeconds: 5`, `failureThreshold: 12` → ~60s
  budget) because the container can take tens of seconds (~38s observed) to serve its first HTTP
  response; without startup gating the liveness probe could restart the pod mid-initialisation.

## Kafka / ZooKeeper storage

- Prod-track Kafka reuses the shared `efs-pvc` claim (`persistence.existingClaim: efs-pvc`,
  `subPath: kafka`); ZooKeeper reuses the same claim with subPaths `zookeeper/data` and
  `zookeeper/log`. Override via `persistence.existingClaim` if the shared claim name differs.
  (The retired staging charts in `backup/` used `existingClaim: ""` with chart-managed PVCs.)
- Both charts run an init container that `mkdir -p` + `chmod 0777` on those subpaths so the
  Confluent runtime (`uid=1000`) passes its writable-path preflight on the shared EFS mount.
- Topic management (`topicManagement.topics` in `argocd/maveric_platform_kafka/values.yaml`)
  now declares **7 topics**, all `replicationFactor: 1`, `retention.ms: 604800000`:
  - `maveric.rapp.train.v1` — partitions 2
  - `maveric.bdt.train.v1` — partitions 2
  - `maveric.ingest.pm.v1` — partitions 2
  - `maveric.loop.proposal.v1` — partitions 1
  - `maveric.loop.action.v1` — partitions 1
  - `maveric.loop.feedback.v1` — partitions 1
  - `maveric.utils.generate.v1` — partitions 2

  The three `maveric.loop.*` topics are **deliberately single-partition** so closed-loop
  proposal/action/feedback events keep strict ordering.
- Worker timeout envs are quoted strings so Helm does not emit scientific notation, e.g.
  `KAFKA_MAX_POLL_INTERVAL_MS: "14400000"` (not `1.44e+07`).
- Baseline: Kafka is still a single-broker `Deployment` (`replicaCount: 1`); rApp worker
  `replicaCount: 2`. Multi-broker replication and KEDA/HPA lag autoscaling are not yet available.

## CI image-tag write-back (BDT worker fix)

- Both the BDT engine chart and the dedicated BDT worker chart deploy the **same image stream**
  (`cloudlyio/maveric-platform-bdt-engine-staging`; the worker chart's Deployment renders
  `image.repository:image.tag` from its own `values.yaml`).
- The engine pipeline (`jenkins/maveric_platform_bdt_engine.groovy`) `yq`-writes the new
  `image.tag` into **both** `argocd/maveric_platform_bdt_engine/values.yaml` and
  `argocd/maveric_platform_bdt_worker/values.yaml`, so one engine build rolls engine + worker
  together.
- The standalone worker pipeline (`jenkins/maveric_platform_bdt_worker.groovy`) builds and pushes
  `cloudlyio/bdt-worker-staging` — an image **no chart references** — and writes back no chart
  values. **Do not trigger it** to deploy the worker; use the engine pipeline.

## Runtime env facts

- Each Python-service secret bakes a full `MONGODB_URL` (base64 in the chart `secretData`) built
  from the repo-managed Mongo root credential (also held in `maveric_platform_mongodb` as
  `mongo-auth-secret`): URI-escaped password (`@` → `%40`), default DB `fastapi_db`, explicit
  `authSource=admin`.
- Production still resolves service DNS in the legacy `staging` namespace (FQDNs such as
  `<cluster-service>`). Charts template `.Release.Namespace`, but namespace separation
  is not yet in effect — do not assume prod runs in its own namespace.

## Related

- [`README.md`](./README.md) — deployment bundle index
- [`env_variable.md`](./env_variable.md) — per-service env/secret inventory
- [`Runbook.md`](./Runbook.md) — deploy checklist and incident triage
- [`Naming_and_Environment_Mapping.md`](./Naming_and_Environment_Mapping.md) — naming-drift canon
