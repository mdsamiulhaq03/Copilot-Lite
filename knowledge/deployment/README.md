# Deployment — Design Bundle

Operational source of truth for delivering the platform to staging and production.
Charts, pipelines, and manifests live in `submodule/maveric-deployment`; the design and
runbooks live here.

| Doc | Covers |
|---|---|
| [`HLD.md`](./HLD.md) | Deployment-level architecture: CI/CD boundaries, environment source-of-truth model, drift control. |
| [`LLD.md`](./LLD.md) | Chart structure, Jenkins implementation notes, Dockerfile → service map. |
| [`env_variable.md`](./env_variable.md) | Per-service environment and secret inventory (gateway, frontend, all engines, Postgres, Mongo). |
| [`Runbook.md`](./Runbook.md) | Deploy checklist, health verification, incident triage, known pitfalls. |
| [`Naming_and_Environment_Mapping.md`](./Naming_and_Environment_Mapping.md) | Naming-drift canon. Read before touching a chart path. |
| [`production.md`](./production.md) | Production endpoints, chart inventory, namespace/secret conventions, nginx-ingress constraints. |
| [`staging.md`](./staging.md) | Staging endpoints, ALB ingress, environment source of truth. |
| [`gaps_production.md`](./gaps_production.md) | Open production environment gaps and remediation status. |
| [`gaps_staging.md`](./gaps_staging.md) | Staging-vs-production parity gaps; Postgres secret audit. |
| [`domain-migration-plan.md`](./domain-migration-plan.md) | Registered (not scheduled) plan to move off `<platform-host>`: edge-agent token pinning, `PUBLIC_BASE_URL`, dual-host ingress. No change in the re-architecture program. |

## Hazards worth knowing before you deploy

- **The chart path is the environment signal.** Do not infer environment from an image name.
  See [`Naming_and_Environment_Mapping.md`](./Naming_and_Environment_Mapping.md).
- A staging Postgres directory name carries a **trailing space**
  (`staging-maveric_platform_postgres `). It is load-bearing; quote it.
- Production Kafka/ZooKeeper reuse the shared `efs-pvc` claim (rApp/BDT already use it); staging
  uses chart-managed PVCs.
- Nothing auto-migrates. The gateway and services never run DDL — apply migrations before the
  dependent service starts, with a **non-superuser** role, or every RLS policy is silently disabled.

## Related

- [`artifacts/design/HLD.md`](../design/HLD.md) §8 — Deployment (AWS), high level
- `submodule/maveric-deployment/argocd/` — ArgoCD Helm charts
- `submodule/maveric-deployment/jenkins/` — Jenkins pipelines
