# Naming and Environment Mapping

## Why This Exists
This repository contains known naming drift between chart path names, namespaces, image repositories, and environment intent. This document defines the canonical mapping to reduce operator confusion without renaming files.

## Canonical Environment Mapping
- Treat `argocd/staging-maveric_*` paths as **staging-track**.
- Treat `argocd/maveric_*` paths as **production-track**.
- Treat shared infra charts with these pairs similarly:
  - `maveric-zookeeper` <-> `staging-maveric-zookeeper`
  - `maveric-platform-pgadmin` <-> `staging-maveric-platform-pgadmin`

## Key Discrepancies Observed
1. Production-track charts often use image repositories or tags containing `staging`.
2. Production-track namespace hardcoding was removed for updated namespaced resources (`{{ .Release.Namespace }}` now used).
3. Staging chart `argocd/staging-maveric_platform_postgres ` includes a trailing space in directory name.
4. Staging chart metadata/comments in some folders contain copied text from other services.
5. Host/domain values across raw docs and values files are not fully uniform.

## Service Mapping Table
| Logical Service | Production-Track Path | Staging-Track Path | Notes |
| --- | --- | --- | --- |
| Gateway | `argocd/maveric_platform_gateway` | `argocd/staging-maveric_platform_gateway` | both are values-driven for runtime secrets; staging uses ALB while live production keeps `nginx` |
| Copilot | `argocd/maveric_platform_copilot` | not yet onboarded | unified chart deploys backend + MCP together; production-only for now |
| Frontend | `argocd/maveric_platform_frontend` | `argocd/staging-maveric_platform_frontend` | both use values-driven runtime auth keys and chart-specific secrets; frontend secret name is `maveric-aws-frontend` |
| BDT Engine | `argocd/maveric_platform_bdt_engine` | `argocd/staging-maveric_platform_bdt_engine` | includes bdt-worker template; both tracks use chart-specific env secrets (`maveric-aws-bdt-engine`) |
| BDT Worker | `argocd/maveric_platform_bdt_worker` | `argocd/staging-maveric_platform_bdt_worker` | dedicated worker chart; commonly shares bdt-engine image stream; both tracks use `maveric-aws-bdt-worker` |
| Data Sim | `argocd/maveric_platform_data_sim` | `argocd/staging-maveric_platform_data_sim` | both tracks now require explicit `secretName`; Data Sim uses `maveric-aws-data-sim` |
| rApp | `argocd/maveric_platform_rapp` | `argocd/staging-maveric_platform_rapp` | both charts now include worker/PDB templates, both use chart-specific env secrets (`maveric-aws-rapp`), and staging sets `efs.enabled: false` |
| SMO Sim | `argocd/maveric_platform_smo_sim` | `argocd/staging-maveric_platform_smo_sim` | both tracks now require explicit `secretName`; SMO Sim uses `maveric-aws-smo-sim` |
| Redis | `argocd/maveric_platform_redis` | `argocd/staging-maveric_platform_redis` | no explicit env vars |
| PostgreSQL | `argocd/maveric_platform_postgres` | `argocd/staging-maveric_platform_postgres ` | staging path has trailing space |
| MongoDB | `argocd/maveric_platform_mongodb` | `argocd/staging-maveric_platform_mongodb` | uses `mongo-auth-secret` |
| Kafka | `argocd/maveric_platform_kafka` | `argocd/staging-maveric_platform_kafka` | static env configuration |
| Zookeeper | `argocd/maveric-zookeeper` | `argocd/staging-maveric-zookeeper` | static env configuration |
| pgAdmin | `argocd/maveric-platform-pgadmin` | `argocd/staging-maveric-platform-pgadmin` | same default env pattern |

## Operator Rules
- Do not infer environment solely from image repository names.
- Use chart path as the primary environment signal.
- Validate namespace and ingress host in rendered output before deployment.
- Do not rename existing files/folders to fix naming drift in this repository.
- For staging pipelines, deployment-manifest updates must target `argocd/staging-maveric_*` paths only.
- For production pipelines, deployment-manifest updates must target `argocd/maveric_*` paths only.
- Copilot currently follows that production-only rule: `jenkins/maveric_platform_copilot.groovy` updates only `argocd/maveric_platform_copilot/values.yaml`.
- For staging runtime configuration, treat chart `values.yaml` (`secretData`, `env`, `additionalEnvFromSecrets`) as the env source of truth.
- For production runtime configuration, apply the same SoT rule (`secretData`, `env`, `additionalEnvFromSecrets` + worker equivalents).
- Do not reuse a single namespace-shared `maveric-aws` secret across frontend, bdt-engine, bdt-worker, rapp, data-sim, or smo-sim; each app chart now owns its own Helm-rendered secret object in both tracks.
- For frontend, bdt-engine, bdt-worker, rapp, data-sim, and smo-sim in both tracks, treat `secretName` as mandatory input and fail the render if it is absent.

## Dockerfile Mapping (Deployment Context)
- `Dockerfiles/bdt.Dockerfile`: BDT engine + BDT worker image behavior.
- `Dockerfiles/rapp.Dockerfile`: rApp engine + rApp worker image behavior.
- `Dockerfiles/smo.Dockerfile`: SMO Sim.
- `Dockerfiles/datasim.Dockerfile`: Data Sim.
- `Dockerfiles/frontend.Dockerfile`: frontend runtime env placeholder strategy.
- `Dockerfiles/gateway.Dockerfile`: gateway runtime env from orchestrator (no build-time env bake).
