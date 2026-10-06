# KB v2 — copilot RAG corpus

**Built:** 2026-09-15 · **Documents:** 88 · **Source:** `artifacts/` (84) + `cloudlynet_ai_copilot` (4)

## Selection rule

Everything, except business-confidential material and secrets — ours or a client's.
Architecture and design documents are deliberately INCLUDED: the model reasons over them.
Internal detail is kept out of user-facing answers by the output redaction layer
(`app/guardrails/redaction/`, SUMMARY §37), not by withholding documents from the model.

## Contents

| Source directory | Docs | Notes |
|---|---:|---|
| `rearchitecture/` | 17 | frozen HLD, HLD assessment, execution guide, test baselines + 13 epics |
| `frontend/` | 12 | all |
| `copilot/` | 11 | all, including MCP payload contract and fixtures |
| `data_platform/` | 7 | all, including 4 adapters |
| `ric/` | 6 | all |
| `ingestion/` | 6 | all |
| `actuation/` | 6 | all |
| `deployment/` | 6 | README, HLD, LLD, Naming_and_Environment_Mapping, env_variable, rollout_notes |
| `design/` | 4 | HLD, LLD, internal-contracts, loop-guardrails |
| `nanolink/` | 4 | all |
| `copilot_repo/` | 4 | SUMMARY, repo README, backend README, mcp_server README |
| `upgrade_plans/` | 2 | kafka_plan, datamigration |
| `migration/` | 1 | README |
| `marketing/` | 1 | capabilities only |
| `platform/` | 1 | artifacts README |

## Excluded (92 markdown files)

| Group | Out | Why |
|---|---:|---|
| `legacy/` | 23 | superseded — the KB must hold current state only |
| `marketing/` | 18 | pricing, ICP, GTM, positioning, sales, roadmap |
| `ocudu/` | 7 | third-party product assessment, not CloudlyNet documentation |
| `deployment/` | 7 | live hostnames, secrets inventory, security gap analyses |
| `upgrade_plans/` | 5 | completed or dated plans |
| `docs/` | 3 | session handover and start-prompt docs |
| copilot repo | 3 | HISTORY (archive), CLAUDE.md, Agent.md (agent instructions) |
| non-markdown | 1 | `nanolink/dmcli.new.conf` — real client device dump |

## Redactions applied

A corpus-wide Tier 0 sweep was run over every staged file, not a pre-listed set.

| Item | Action | Sites |
|---|---|---|
| Real NybSys serial `2205600282` | → `2205609999` (the fixture serial) | 4 files |
| `*.cloudly.io` / `*.cloudly.com` | → `<platform-host>` | 29 occurrences |
| `*.svc.cluster.local` | → `<cluster-service>` | 2 occurrences |
| Private LAN IP `192.168.97.1` | → `<host-ip>` | 2 occurrences |

Verified after: no credential shapes, no real serials, no live hostnames remain.

## Before ingesting

1. **Purge the old corpus first.** `KnowledgeIngestionService.ingest_directory()` only inserts and
   updates — there is no stale-document prune, so v1 chunks survive a v2 ingest.
2. **Repoint the script.** `backend/scripts/ingest_knowledge_base.py` has a hardcoded 7-entry
   `SOURCES` list pointing at the v1 subdirectories. It will skip every directory here until updated
   to the 15 above.
3. **Markdown only.** The script passes `extensions=[".md"]`. `design/openapi.yaml` and
   `design/schemas.sql` are not in this bundle.
4. **Data leaves the network at ingest.** `ChunkContextualizer` sends every chunk plus a
   6,000-character parent excerpt to Groq.
