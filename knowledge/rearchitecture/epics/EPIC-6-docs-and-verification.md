# EPIC 6 — Docs, design artifacts, context graph, claims re-verification

**Epic ID:** E6
**Title:** Docs/design/context updates + claims re-verification (continuous; final gate)
**Goal:** Bring every documentation surface — `artifacts/design/`, `artifacts/oran/` (archived) + new `artifacts/ric/`, the `.context/` knowledge graph, submodule READMEs, and the marketing/claims bundle — into exact agreement with the re-architected code as E0–E5 land. E6 is the program's honesty mechanism: no doc claims a capability the code does not have, every capability claim carries its rung label, and the epic closes only when a full claims re-verification is stamped against the merged code.
**Dependencies:** E0 (rebrand + gateway fix), E1 (Data Platform), E2 (NDT), E3 (RIC layer), E4 (Actuation, E2/R1 deletion), E5 (closed-loop demo). Stories run continuously alongside those epics; S5/S6 are the final gate and merge last.
**Frozen HLD (constitution):** `docs/task_docs/cloudlynet-rearchitecture/01-hld-frozen.md` — §3 hard constraints and §4 shared contracts are binding; this epic documents them, never redefines them.

**Definition of done (epic):**

- [ ] `artifacts/design/HLD.md`, `LLD.md`, `openapi.yaml` all read **Version: 0.6.0** (lockstep policy stated in each); content matches the target service roles in frozen HLD §2.
- [ ] `openapi.yaml` contains `/ndt/**`, `/ingest/**`, `/data/**`, and loop endpoints exactly as frozen HLD §4.2/§4.3; **zero public paths removed**; existing public schemas byte-identical.
- [ ] `artifacts/design/schemas.sql` carries the canonical PM/FM/CM tables (§4.3) and the loop tables, and contains no `e2_*`/`r1_*` DDL; a fresh `./scripts/kafka/compose.sh infra` boot creates them.
- [ ] `artifacts/oran/` no longer exists; content lives under `artifacts/legacy/oran/` with a deprecation README; `artifacts/ric/` documents the RIC integration layer with claims-compliant wording; zero dangling in-repo links to `artifacts/oran/`.
- [ ] `.context/` has pages `data-platform`, `ndt-decision-hub`, `ric-integration`, `actuator-framework`; stale pages refreshed; `python .claude/skills/context-agent/tools/graph_check.py .context` reports 0 orphans / 0 broken links.
- [ ] data_sim / smo_sim / rapp README (and Agent.md where drifted) describe only files, ports, and capabilities that exist.
- [ ] `artifacts/marketing/claims-guardrails.md` re-verified against merged code with a fresh "last verified against code" stamp; roadmap.md / product.html / roadmap.html rungs updated; `python3 artifacts/marketing/build_site.py` regenerated the GTM pack; no em dash (U+2014) in any marketing-bound text; no forbidden claim ("O-RAN compliant", "carrier grade", "zero-touch", "5G NR TDD" for NanoLink).
- [ ] Zero CI/CD change: this epic touches only `.md`, `.html`, `.sql` (reference DDL), `.yaml` (OpenAPI doc) files — no charts, pipelines, images, ports, compose services.

---

## Ownership rule for shared files (read before any story)

Executable migrations belong to the code epics: E1 owns the canonical-table migration, E2 owns the loop-table migration, E4 owns the `e2_*`/`r1_*` DROP migration (all under `artifacts/migration/`). E6 owns the **reference mirrors**: `artifacts/design/schemas.sql`, `openapi.yaml`, HLD/LLD prose, `.context/`, and marketing. When a reference mirror and a landed migration disagree, the landed migration wins and the mirror is corrected — never the reverse. This prevents merge-conflict ping-pong on `schemas.sql`/`openapi.yaml` between E1/E2/E4 and E6.

Product naming (frozen HLD §3.4): product **CloudlyNet**, solution term **Network Digital Twin**. Note the parent `CLAUDE.md` still carries the older "NetAI by Cloudly" lockup; E0 owns the repo-wide rebrand including CLAUDE.md. E6 stories use CloudlyNet in every file they touch and must not reintroduce "NetAI by Cloudly", "CloudlyNet AI", or "Maveric Platform".

---

## E6.S1 — Rewrite the canonical design docs to the new service roles (lockstep v0.6.0)

**Why:** Recon found version skew (HLD v0.4.9 / LLD v0.4.8 / openapi v0.5.0 — `.context/index.md` known gap #6) and the docs describe the pre-rearchitecture roles. After E1–E4 land, `artifacts/design/` must describe the Data Platform / NDT / RAN Intelligence / Actuation split or every future agent starts from wrong context.

**Size:** L

**Scope:**
- In: full rewrite of service-role sections of `HLD.md` + `LLD.md`; add `/ndt/**`, `/ingest/**`, `/data/**`, loop endpoints to `openapi.yaml`; add canonical + loop tables to `schemas.sql`; version lockstep to 0.6.0 with a stated bump policy; fix HLD-internal inconsistencies flagged in recon (§8.8 "Optionally use RLS" vs §4 FORCE RLS; §4 "Ops note" inline ALTER TABLE patches vs `artifacts/migration/` as migration source of truth); retitle docs to CloudlyNet.
- Out: removing any public path or changing any existing schema in `openapi.yaml` (forbidden — HLD §3.2); writing executable migrations (E1/E2/E4 own those); marketing wording (S5); `.context` (S3).

**Files:**
- `artifacts/design/HLD.md` (modify — currently titled "NetAI by Cloudly — High-Level Design", Version 0.4.9 at line 3)
- `artifacts/design/LLD.md` (modify — Version 0.4.8 at line 3)
- `artifacts/design/openapi.yaml` (modify — `info.version: 0.5.0` at line 4; 4062 lines)
- `artifacts/design/schemas.sql` (modify — 517 lines; mounted as init SQL by root `docker-compose.yaml` infra profile, so additions are live for fresh local DBs)
- `artifacts/migration/README.md` (modify — index cross-references to E1/E2/E4 migrations)

**Contract:**

Version lockstep policy (state verbatim near the version line of all three docs):

> The three canonical design docs (HLD.md, LLD.md, openapi.yaml) version-bump together. Any PR that changes one bumps all three to the same version.

OpenAPI additions (paths only; envelope/error model reuse the file's existing `Envelope`/`Error` components; all shapes verbatim from frozen HLD §4.2/§4.3):

| Path | Method | Tag | Auth note |
|---|---|---|---|
| `/v1/tenants/{tenant_id}/ndt/evaluate` | POST | `NDT (internal)` | Gateway-routed since E5.S7 (2026-08-04): `/v1/tenants/{t}/ndt/**` under Cognito + RequireMembership, `BDT_API_KEY` injected server-side. bdt_engine still also accepts direct X-API-Key on :8000 for service-to-service callers. The tag description must NOT repeat the old "not gateway-routed yet" claim. |
| `/v1/tenants/{tenant_id}/ndt/evaluate/{run_id}` | GET | `NDT (internal)` | 200 for completed tick-scope; day-scope is 202-then-poll |
| `/v1/tenants/{tenant_id}/ndt/loop/proposals` | POST | `NDT (internal)` | mirror of topic `maveric.loop.proposal.v1` |
| `/v1/tenants/{tenant_id}/ndt/loop/actions/{action_id}` | GET | `NDT (internal)` | |
| `/v1/tenants/{tenant_id}/ndt/loop/policy` | GET, PUT | `NDT (internal)` | body `{mode: off|approval|auto, guardrails: {min_sinr_db, min_rrc_success_pct, max_outage_rate}, watch_window_min}` |
| `/v1/tenants/{tenant_id}/ndt/loop/actions` | GET | `NDT (internal)` | list + filters `status, proposal_id, kind, limit, offset` (E2.S8/E5.S3) |
| `/v1/tenants/{tenant_id}/ndt/loop/actions/{action_id}:approve` | POST | `NDT (internal)` | 200 `{action_id, status: "dispatched"}`; 404 `ACTION_NOT_FOUND` / 409 `ACTION_NOT_PENDING` (E2.S8) |
| `/v1/tenants/{tenant_id}/ndt/loop/actions/{action_id}:reject` | POST | `NDT (internal)` | mirrors approve semantics (E2.S8) |
| `/v1/tenants/{tenant_id}/ndt/feature-builds` | POST | `NDT (internal)` | 202 `{build_id, status: "queued"}` + Location; E1.S4 seam contract of record (E2.S4 implements) |
| `/v1/tenants/{tenant_id}/ndt/feature-builds/{build_id}` | GET | `NDT (internal)` | `{build_id, status, error, artifacts}` |
| `/v1/tenants/{tenant_id}/ndt/kpis` | GET | `NDT (internal)` | filters `bdt_id, baseline_id, source, from_ts, to_ts, limit, offset` (E2.S5) |
| `/v1/tenants/{tenant_id}/ingest/uploads` | POST | `Data Platform` | gateway-routed (`/ingest/**` → DATA); `source_type=nybsys_pm_csv` first |
| `/v1/tenants/{tenant_id}/ingest/jobs/{job_id}` | GET | `Data Platform` | gateway-routed |
| `/v1/tenants/{tenant_id}/data/pm` | GET | `Data Platform` | gateway-routed; filters `dn, metric, from, to, day, tick` |
| `/v1/tenants/{tenant_id}/data/fm` | GET | `Data Platform` | gateway-routed |
| `/v1/tenants/{tenant_id}/data/cm` | GET | `Data Platform` | gateway-routed |

`/custom/nybsys/uploads*` paths stay in the file **unchanged** (byte-compatible contract, now served by data_sim — update only the human-readable description text, never the schema). E2/R1 paths were never in `openapi.yaml` (verified in recon), so "remove nothing public" is satisfied by construction.

**Key snippets:**

HLD/LLD service-role table must match frozen HLD §2 exactly (same four containers, same ports 8000/8001/8002/8003, new roles):

```markdown
| Service (container/port unchanged) | Role |
|---|---|
| data_sim :8003 | Data Platform: per-vendor ingestion adapters -> canonical PM/FM/CM tables (Postgres) + raw S3; synthetic data factory; ingestion Kafka consumer runs inside the API container (no new deployable) |
| bdt_engine :8000 | Network Digital Twin: twin engines (Maveric BDT GP; commercial slot), twin feature builder, evaluate API, KPI tracking, loop decision hub |
| rapp :8001 | RAN Intelligence: rApp/xApp model registry + Kafka training, recommendation inference (twin evaluation delegated to NDT via NDT_BASE_URL/NDT_API_KEY), RIC integration layer (app/ric/) |
| smo_sim :8002 | Actuation & Integration: NanoLink TR-069 control plane, actuator adapter framework (app/actuators/), wired placeholders (o1_netconf, ocudu_ws_collector, open_mplane, sas_domain_proxy, nms_northbound). E2/R1 facades deleted (D4) |
```

Kafka topic table (HLD + LLD): `maveric.ingest.pm.v1`, `maveric.loop.proposal.v1`, `maveric.loop.action.v1`, `maveric.loop.feedback.v1` added; `maveric.bdt.train.v1`, `maveric.rapp.train.v1` unchanged.

`schemas.sql` additions — canonical tables verbatim from frozen HLD §4.3 (RLS-forced like every tenant table in this file; reuse the file's existing RLS `FOREACH`/policy loop pattern at lines ~466–497):

```sql
-- ============ Canonical data platform (owner: data_sim; frozen HLD §4.3) ============
CREATE TABLE IF NOT EXISTS pm_measurements (
  tenant_id     uuid NOT NULL,
  source        text NOT NULL,
  vendor        text NOT NULL,
  dn            text NOT NULL,
  metric        text NOT NULL,          -- TS 28.552 name where mappable, else 'vendor:<name>'
  value         double precision NOT NULL,
  unit          text,
  granularity_s int,
  ts            timestamptz NOT NULL,
  day           int,
  tick          int,
  labels        jsonb NOT NULL DEFAULT '{}'::jsonb,
  raw_ref       text
) PARTITION BY RANGE (ts);              -- monthly partitions

CREATE TABLE IF NOT EXISTS fm_alarms (
  tenant_id uuid NOT NULL, source text NOT NULL, dn text NOT NULL,
  alarm_id text NOT NULL, severity text NOT NULL, probable_cause text,
  raised_at timestamptz NOT NULL, cleared_at timestamptz, state text NOT NULL,
  raw jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS cm_records (
  tenant_id uuid NOT NULL, source text NOT NULL, dn text NOT NULL,
  params jsonb NOT NULL, captured_at timestamptz NOT NULL, origin text
);

CREATE TABLE IF NOT EXISTS ingest_jobs (
  tenant_id uuid NOT NULL, job_id uuid PRIMARY KEY, source_type text NOT NULL,
  status text NOT NULL, stats jsonb NOT NULL DEFAULT '{}'::jsonb, error text,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS vendor_dictionaries (
  vendor text NOT NULL, source_metric text NOT NULL,
  canonical_metric text NOT NULL, transform text, unit text,
  PRIMARY KEY (vendor, source_metric)
);
```

Loop tables — **reference mirror of E2's decision-hub DDL** (E2.S6's landed migration `014_ndt_loop.sql` is authoritative; the mirror below copies E2's shapes — status vocabulary, `prev_action_id`, jsonb `policy_ref`/`target` included; if E2's landed DDL differs, copy E2's verbatim and fix this mirror):

```sql
-- ============ Closed-loop decision hub (owner: bdt_engine/NDT; see E2.S6/S7) ============
CREATE TABLE IF NOT EXISTS loop_policies (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        uuid NOT NULL UNIQUE,
  mode             text NOT NULL DEFAULT 'off' CHECK (mode IN ('off','approval','auto')),
  guardrails       jsonb NOT NULL DEFAULT '{}'::jsonb,  -- {min_sinr_db, min_rrc_success_pct, max_outage_rate}
  watch_window_min int  NOT NULL DEFAULT 15,
  updated_by       uuid,
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS loop_actions (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       uuid NOT NULL,
  action_id       text NOT NULL,
  proposal_id     text,
  kind            text NOT NULL DEFAULT 'change' CHECK (kind IN ('change','rollback')),
  source          jsonb,                      -- proposal source block
  adapter         text NOT NULL,              -- HLD Appendix A.4 key (nanolink_tr069, ...)
  target          jsonb NOT NULL,             -- {"cell_id": ..., "tick": ...} or {"device_id": ...}
  payload         jsonb NOT NULL,
  policy_ref      jsonb,                      -- policy snapshot at decision time (object, never text)
  evaluation      jsonb,                      -- {"run_id":..., "verdict":"pass|fail", "reasons":[...]}
  status          text NOT NULL DEFAULT 'proposed'
                  CHECK (status IN ('proposed','suppressed','rejected_by_gate','pending_approval',
                                    'approved','rejected','dispatched','applied','failed',
                                    'watching','completed','rolled_back','expired')),
  prev_action_id  text,                       -- rollback rows: the action being reverted
  expires_at      timestamptz,
  dispatched_at   timestamptz,
  applied_at      timestamptz,
  watch_deadline  timestamptz,
  error           text,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, action_id)
);

CREATE TABLE IF NOT EXISTS loop_proposals (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL,
  proposal_id text NOT NULL,
  payload     jsonb NOT NULL,             -- raw maveric.loop.proposal.v1 message (HLD Appendix A.1)
  created_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, proposal_id)
);

CREATE TABLE IF NOT EXISTS loop_feedback (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL,
  action_id   text,                       -- null for unsolicited device events
  kind        text NOT NULL,              -- apply|kpi_window|guardrail_breach|rollback
  status      text,
  payload     jsonb NOT NULL,             -- raw maveric.loop.feedback.v1 message (HLD Appendix A.3)
  observed_at timestamptz,
  created_at  timestamptz NOT NULL DEFAULT now()
);
```

`POST /ndt/evaluate` request body schema (OpenAPI, verbatim from frozen HLD §4.2 — do not reshape):

```yaml
NdtEvaluateRequest:
  type: object
  required: [baseline_id, bdt_id, ue_dataset_id, scope, cell_configs]
  properties:
    baseline_id: {type: string}
    bdt_id: {type: string}
    ue_dataset_id: {type: string}
    scope:
      type: object
      required: [type]
      properties:
        type: {type: string, enum: [tick, day]}
        tick: {type: integer, minimum: 0, maximum: 23}
        day: {type: integer}
    cell_configs:
      type: array
      items:
        type: object
        required: [items]
        properties:
          tick: {type: integer}
          items:
            type: array
            items:
              type: object
              required: [cell_id, cell_el_deg, on_off]
              properties:
                cell_id: {type: string}
                cell_el_deg: {type: number}
                on_off: {type: boolean}
    options:
      type: object
      properties:
        thresholds: {type: object}
        energy_params: {type: object}
        include: {type: array, items: {type: string}}
```

Response schema fields (`guardrail_kpis`, `objective_kpis`, `per_tick_kpis`, `worst_tick_stats`, `raw_tick_data?`) must be copied from the shapes rapp's `kpi_calculator` produces today (E2's stories pin them; reuse E2's schema names) so the documented contract proves rapp's public `/rapps/**` responses stay byte-compatible.

**Acceptance criteria:**
- All three docs show `Version: 0.6.0` and the lockstep policy sentence.
- HLD/LLD service tables match frozen HLD §2 (roles, unchanged containers/ports); closed-loop narrative matches frozen HLD "Closed loop" paragraph; Kafka topic list matches §4.1 exactly.
- `openapi.yaml` diff adds only the 17 paths above plus components/tags; `git diff` shows no deletion of any existing path or schema property; file parses as valid OpenAPI 3.0.3.
- `schemas.sql` contains the five canonical tables + four loop tables (`loop_policies`, `loop_actions`, `loop_proposals`, `loop_feedback`, copied from E2's landed `014_ndt_loop.sql`; the `loop_actions` CHECK carries E2's FULL status set incl. `suppressed`/`rejected_by_gate`/`pending_approval`/`watching`/`completed`) with FORCE RLS wired via the existing loop pattern; contains no `e2_`/`r1_` DDL (verify: `grep -E "e2_|r1_" artifacts/design/schemas.sql` returns nothing).
- HLD §8.8 no longer says RLS is optional; HLD ops-note ALTERs replaced by a pointer to `artifacts/migration/`.
- Doc titles/prose use CloudlyNet; `grep -n "NetAI" artifacts/design/*.{md,yaml}` returns nothing.
- No public gateway-routed contract text changed except backend-pointer prose for `/custom/**` (HLD §3.2).

**Test plan:**
- OpenAPI validity: `uv run --with openapi-spec-validator python -m openapi_spec_validator artifacts/design/openapi.yaml`.
- Schema boot (integration): `./scripts/kafka/compose.sh down && ./scripts/kafka/compose.sh infra`, then `docker exec -it $(docker ps -qf name=postgres) psql -U postgres -d maveric -c "\dt"` shows `pm_measurements`, `fm_alarms`, `cm_records`, `ingest_jobs`, `vendor_dictionaries`, `loop_policies`, `loop_actions`, `loop_proposals`, `loop_feedback` and no `e2_*`/`r1_*`.
- Greps in acceptance criteria run clean. No service unit tests (doc-only story).

**Coding-agent prompt:**

```text
You are working in the CloudlyNet backend monorepo at /Users/laawanyakishor/Projects/NetAI/cloudlynet_ai.
Read docs/task_docs/cloudlynet-rearchitecture/01-hld-frozen.md first: it is the frozen constitution;
its §2 target roles, §3 hard constraints, and §4 shared contracts are binding and must be copied, not
reinterpreted. Then read docs/task_docs/cloudlynet-rearchitecture/epics/EPIC-6-docs-and-verification.md
story E6.S1 for exact snippets.

TASK: bring the four canonical design artifacts up to the re-architected platform, in lockstep version 0.6.0.
1. artifacts/design/HLD.md and artifacts/design/LLD.md: rewrite the service-role and data-flow sections to
   the frozen HLD §2 roles (data_sim = Data Platform, bdt_engine = Network Digital Twin + loop decision hub,
   rapp = RAN Intelligence + RIC integration layer, smo_sim = Actuation & Integration; E2/R1 facades deleted).
   Containers, charts, images, ports are UNCHANGED and the docs must say so. Add the closed-loop flow and the
   four new Kafka topics (maveric.ingest.pm.v1, maveric.loop.proposal.v1, maveric.loop.action.v1,
   maveric.loop.feedback.v1). Set "Version: 0.6.0" in both and add the lockstep sentence: the three canonical
   docs bump together. Fix two internal HLD inconsistencies: §8.8 must mandate FORCE RLS (not "optionally"),
   and the §4 ops-note inline ALTER TABLE patches must be replaced by a pointer to artifacts/migration/.
   Retitle both docs to CloudlyNet (product name per frozen HLD §3.4); remove every "NetAI" occurrence in
   artifacts/design/.
2. artifacts/design/openapi.yaml: bump info.version to 0.6.0. ADD (never remove or reshape anything existing):
   POST /v1/tenants/{tenant_id}/ndt/evaluate, GET .../ndt/evaluate/{run_id}, POST .../ndt/loop/proposals,
   GET .../ndt/loop/actions/{action_id}, GET+PUT .../ndt/loop/policy (tag "NDT (internal)", description
   states X-API-Key service auth, not gateway-routed yet); POST /v1/tenants/{tenant_id}/ingest/uploads,
   GET .../ingest/jobs/{job_id}, GET .../data/pm, GET .../data/fm, GET .../data/cm (tag "Data Platform",
   gateway-routed). Request/response shapes are given verbatim in E6.S1 "Key snippets" and frozen HLD §4.2/§4.3.
   Reuse the file's existing envelope/error components. /custom/nybsys/** schemas stay byte-identical; only
   update description prose to say data_sim now serves uploads.
3. artifacts/design/schemas.sql: add the five canonical data-platform tables and four loop tables
   (loop_policies, loop_actions with E2's FULL status CHECK, loop_proposals, loop_feedback) using the
   DDL in E6.S1 "Key snippets"; wire them into the file's existing FORCE-RLS policy loop; confirm no e2_*/r1_*
   DDL exists in the file. IMPORTANT: if artifacts/migration/ already contains E1/E2 migrations for these
   tables (011_data_platform_canonical.sql / 014_ndt_loop.sql), copy that DDL verbatim instead (landed
   migrations win over this epic's reference snippets).
4. artifacts/migration/README.md: index the E1/E2/E4 migrations if present (canonical tables, loop tables,
   e2_*/r1_* drop) with one-line descriptions.

CONSTRAINTS: zero CI/CD change (docs/SQL-reference only); public gateway-routed API contracts byte-compatible;
never redefine a frozen §4 contract; product name CloudlyNet, solution term Network Digital Twin; no marketing
copy in these files. Conventions per /Users/laawanyakishor/Projects/NetAI/cloudlynet_ai/CLAUDE.md.

DEFINITION OF DONE:
- uv run --with openapi-spec-validator python -m openapi_spec_validator artifacts/design/openapi.yaml passes.
- ./scripts/kafka/compose.sh down && ./scripts/kafka/compose.sh infra boots; psql \dt on DB maveric shows the
  8 new tables and no e2_*/r1_* tables.
- git diff on openapi.yaml shows additions only (no removed paths/properties).
- grep -E "e2_|r1_" artifacts/design/schemas.sql -> empty; grep -n "NetAI" artifacts/design/ -r -> empty.
- All three docs read Version: 0.6.0.
Commit style: "[docs]: design docs v0.6.0 - re-architected service roles, /ndt+/ingest+/data paths, canonical+loop DDL"
(no Claude signature, no submodule pointer changes).
```

---

## E6.S2 — Archive `artifacts/oran/` to legacy; create the `artifacts/ric/` bundle

**Why:** D4 deletes the E2/R1 REST facades, so their design bundle must move to `artifacts/legacy/` with an explicit deprecation notice (frozen HLD D4), and the new RIC integration layer (frozen HLD §4.4, built by E3) needs a design bundle of record with claims-compliant wording.

**Size:** M

**Scope:**
- In: `git mv artifacts/oran artifacts/legacy/oran`; deprecation README; archive copies of smo_sim's submodule-root E2/R1 docs (`e2_spec.md`, `E2-Data-Pipeline-Explanation.md`, `r1-plan.md`, `R1-SMO-Delivery-Doc.md`) into the same legacy folder; new `artifacts/ric/` bundle (README, ports-and-adapters, NONRTRIC lab profile + image-mirroring posture, OCUDU integration surfaces, R1 packaging facade, near-RT placeholder summary; the two E3-authored files `nonrtric-lab.md` and `nearrt-placeholder.md` are extended/owned here, never recreated under a different name); fix every in-repo reference to `artifacts/oran/` (parent CLAUDE.md bundle table, HLD.md doc-links section, `artifacts/legacy/README.md` index, `artifacts/nanolink/` cross-links if any). This story is the SOLE OWNER of the `artifacts/oran/` archival end state (`artifacts/oran/` does not exist afterward, no tombstone left behind): E4.S1 deletes only smo_sim submodule files and touches no `artifacts/oran/` file.
- Out: deleting the smo_sim submodule files themselves (rides E4's deletion PR — this story only archives copies in the parent repo); `.context` page updates (S3); any RIC source code (never copied — NONRTRIC is consumed as container images + REST; only prose describing the lab profile owned by E3).

**Files:**
- `artifacts/oran/{README.md, e2_interface.md, e2_data_pipeline.md, r1_interface.md, r1_roadmap.md}` → move to `artifacts/legacy/oran/` (5 files)
- `artifacts/legacy/oran/README.md` (rewrite as deprecation README, content below)
- `artifacts/legacy/oran/submodule-docs/{e2_spec.md, E2-Data-Pipeline-Explanation.md, r1-plan.md, R1-SMO-Delivery-Doc.md}` (create — copies from `submodule/maveric_platform_smo_sim/`)
- `artifacts/legacy/README.md` (modify — add oran row to the archive index)
- `artifacts/ric/README.md`, `artifacts/ric/ports_and_adapters.md`, `artifacts/ric/ocudu_integration.md`, `artifacts/ric/r1_packaging.md` (create)
- `artifacts/ric/nonrtric-lab.md`, `artifacts/ric/nearrt-placeholder.md` (extend/own the E3-authored files — E3.S2/S3/S4 create and extend `nonrtric-lab.md`, E3.S7 creates `nearrt-placeholder.md`; keep E3's hyphenated filenames, never create an underscore duplicate; create per the contract table only if E3 has not landed yet)
- `CLAUDE.md` (modify — bundle table: replace the `artifacts/oran/` row with `artifacts/ric/`; **flag for owner review in the PR description**, per repo governance CLAUDE.md edits need explicit human sign-off)
- Grep-fix inbound links: `artifacts/design/HLD.md` (line ~513 links `../oran/r1_roadmap.md`), any other `grep -rn "artifacts/oran\|\.\./oran/" --include="*.md" --include="*.yaml"` hit outside `.context/` (S3 owns those)

**Contract:** `artifacts/ric/` bundle structure and wording rules:

| File | Covers | Wording rung rule |
|---|---|---|
| `README.md` | Bundle map; the hard line "CloudlyNet integrates a RIC; it is not a RIC and does not implement E2 termination itself" | Negation framing is always permitted (guardrails §2) |
| `ports_and_adapters.md` | `rapp app/ric/ports.py`: `RanControlPort` (submit_policy_intent/delete_policy_intent/policy_status, capability discovery), `RanDataPort` (subscribe → normalized records to `maveric.ingest.pm.v1`); adapter registry (`a1_policy` implemented, `nearrt_xapp` reserved); NONRTRIC A1-PMS connector | "A1-policy-aligned intents", never "A1 compliant" (frozen HLD §4.4) |
| `nonrtric-lab.md` (E3.S2-authored runbook; this story extends/owns it, no rename, no duplicate) | Compose profile `ric-lab`: O-RAN SC NONRTRIC A1-PMS (`nexus3.o-ran-sc.org:10002/o-ran-sc/nonrtric-plt-a1policymanagementservice:2.11.0`) + two `a1-simulator:2.8.1` containers (one `STD_2.0.0`, one `OSC_2.1.0`), container images only (no submodule, no source copied); Apache-2.0; production posture: mirror images into our own registry, customer K8s installs use upstream charts; keep the O-RAN ALLIANCE notice if the pms-api-v3 OpenAPI file is vendored; near-RT tier: reserved `nearrt_xapp` placeholder (the past FlexRIC/CSSL v1.0 license findings that drove the deferral stay recorded, past-tense, in E3's contract doc) | Everything labeled "Today (Lab)" only after E3+E5 land; before that "Building". Lab-only, compose-profile-only, no chart, no CI/CD; never O-RAN compliance/certification language |
| `nearrt-placeholder.md` (E3.S7-authored; this story extends/owns it) | One-page near-RT deferral summary + pointer to the canonical contract doc (`submodule/maveric_platform_rapp/app/ric/adapters/nearrt/README.md`); reserved `nearrt_xapp` adapter key + `nearrt_kpm_stream` source_type | Deferral rationale (FlexRIC/CSSL v1.0 findings) stays past-tense; the deferred track is labeled roadmap, never a present-tense capability |
| `ocudu_integration.md` | Three OCUDU surfaces: (1) E2SM-KPM v3 via a near-RT RIC (DEFERRED: reserved `nearrt_xapp` adapter key + `nearrt_kpm_stream` source_type; no bridge code in committed scope), (2) JSON metrics over WebSocket → data platform (`ocudu_ws_collector` placeholder in smo_sim, E4), (3) O1/NETCONF via companion `ocudu_netconf` (placeholder adapter, E4) | Each surface individually rung-labeled; OCUDU is an integration target, never a customer |
| `r1_packaging.md` | `rapp packaging/r1/`: R1-shaped rApp manifest, metadata facade for future EIAP/MantaRay onboarding | "R1-shaped manifest (facade)", never "R1 compliant" |

Deprecation README skeleton (`artifacts/legacy/oran/README.md`):

```markdown
# ARCHIVED: E2/R1 REST facade design bundle

> Deprecated <date> by re-architecture decision D4
> (docs/task_docs/cloudlynet-rearchitecture/01-hld-frozen.md). The E2/R1 REST/JSON
> facades these documents describe were deleted from smo_sim (routers, schemas,
> tables, e2test/r1test harnesses) in epic E4. Nothing depended on them: the routes
> were never gateway-routed, the measurement tables had no writer, and R1
> subscriptions never notified.
>
> The successor design of record for RAN-intelligence integration is
> artifacts/ric/ (RIC integration layer: ports/adapters in rapp, NONRTRIC A1-PMS lab
> posture, OCUDU surfaces). These archived documents described REST resource
> models only, never protocol implementations (no SCTP, no ASN.1, no E2AP/E2SM
> wire behavior), and must not be cited as capability evidence.
```

**Key snippets:** none beyond the above (prose bundle). Every `artifacts/ric/` page opens with the rung-label banner pattern used by `artifacts/oran/README.md` today (adapted: "integration layer, not a RIC").

**Acceptance criteria:**
- `artifacts/oran/` does not exist; `git log --follow artifacts/legacy/oran/e2_interface.md` shows history preserved (moves, not delete+create).
- `grep -rn "artifacts/oran" --include="*.md" --include="*.yaml" .` (excluding `.context/`, `artifacts/legacy/`, `docs/task_docs/`) returns nothing.
- All six `artifacts/ric/` files exist (`README.md`, `ports_and_adapters.md`, `nonrtric-lab.md`, `nearrt-placeholder.md`, `ocudu_integration.md`, `r1_packaging.md` — the E3-authored two under E3's hyphenated names, no underscore duplicates: `ls artifacts/ric/nonrtric_lab.md` fails); none contains a present-tense "supports E2/A1/O1/R1" claim, "O-RAN compliant/certified", or an unlabeled future capability; NONRTRIC license posture (Apache-2.0, image mirroring for production pulls, O-RAN ALLIANCE notice rule) stated in `nonrtric-lab.md`, with the near-RT deferral and its past FlexRIC/CSSL rationale clearly past-tense.
- No em dash (U+2014) in any new/modified marketing-bound file: `grep -rn $'—' artifacts/ric/ artifacts/legacy/oran/README.md` → empty.
- CLAUDE.md bundle table updated and the PR description explicitly calls out the CLAUDE.md hunk for owner review.
- Zero non-doc files touched.

**Test plan:** doc-only story — the greps above plus link check: `python .claude/skills/context-agent/tools/graph_check.py .context` still passes (no .context edits here, but the move must not break graph-referenced paths; if it does, defer that link to S3 and note it in the PR).

**Coding-agent prompt:**

```text
You are working in the CloudlyNet backend monorepo at /Users/laawanyakishor/Projects/NetAI/cloudlynet_ai.
Read docs/task_docs/cloudlynet-rearchitecture/01-hld-frozen.md (decisions D1 and D4, contract §4.4), then
docs/task_docs/cloudlynet-rearchitecture/epics/EPIC-6-docs-and-verification.md story E6.S2, then
artifacts/marketing/claims-guardrails.md §2 (wording rules for anything O-RAN adjacent).

TASK:
1. git mv artifacts/oran artifacts/legacy/oran (preserve history). Rewrite artifacts/legacy/oran/README.md
   as a deprecation README using the skeleton in E6.S2 (deleted per D4 in epic E4; successor bundle is
   artifacts/ric/; these were REST resource models, never protocol implementations, never capability evidence).
2. Copy (do not move; deletion rides epic E4's PR) these submodule docs into
   artifacts/legacy/oran/submodule-docs/: submodule/maveric_platform_smo_sim/e2_spec.md,
   E2-Data-Pipeline-Explanation.md, r1-plan.md, R1-SMO-Delivery-Doc.md. Add a one-line archived-copy header
   to each.
3. Bring artifacts/ric/ to six files per the E6.S2 contract table. Create: README.md, ports_and_adapters.md
   (RanControlPort/RanDataPort in rapp app/ric/ports.py, adapter registry with a1_policy implemented and
   nearrt_xapp reserved, NONRTRIC A1-PMS connector), ocudu_integration.md (three surfaces:
   E2SM-KPM v3 via a near-RT RIC (deferred, reserved placeholders only), JSON WebSocket metrics -> data
   platform, O1/NETCONF via companion ocudu_netconf; OCUDU is an integration target, never a customer),
   r1_packaging.md (R1-shaped rApp manifest facade in rapp packaging/r1/, for future EIAP/MantaRay
   onboarding; OSC rApp Manager is pre-spec and stays roadmap). Extend/own the two E3-authored files under
   E3's exact hyphenated filenames (NEVER create nonrtric_lab.md or any underscore variant):
   nonrtric-lab.md (E3.S2's runbook; ensure it covers: compose profile ric-lab with NONRTRIC A1-PMS 2.11.0
   + two a1-simulator 2.8.1 containers, images from nexus3.o-ran-sc.org:10002, no submodule, no source
   copied; Apache-2.0; production posture: mirror the images into our own registry, customer K8s installs
   use upstream charts; keep the O-RAN ALLIANCE notice if the pms-api-v3 OpenAPI file is vendored; near-RT
   tier deferred behind the reserved nearrt_xapp placeholder, with the past FlexRIC/CSSL v1.0 findings
   recorded past-tense as the deferral rationale) and nearrt-placeholder.md (E3.S7's one-page deferral
   summary + pointer to the canonical submodule README). If epic E3 has landed, cite real file paths
   from submodule/maveric_platform_rapp/app/ric/ and only extend its files; if not, create them under the
   same hyphenated names, mark each section "Building", and cite the frozen HLD §4.4.
4. Fix every in-repo reference to artifacts/oran outside .context/ and docs/task_docs/: the CLAUDE.md bundle
   table row (replace artifacts/oran with artifacts/ric; flag this hunk for owner review in the PR
   description), artifacts/design/HLD.md doc links, artifacts/legacy/README.md index.

WORDING CONSTRAINTS (hard): every capability line carries a rung label (Today GA/Beta/Lab, Building, Vision);
never "O-RAN compliant/certified", never present-tense "we support E2/A1/O1/R1"; "A1-policy-aligned intents"
not "A1 compliant"; "CloudlyNet integrates a RIC, is not a RIC" negation is encouraged; no em dash character
(U+2014) anywhere in the new files; product name CloudlyNet. Never copy NONRTRIC (or any RIC) code or text
into our repos; RIC components arrive as container images only.

DEFINITION OF DONE:
- artifacts/oran/ gone; artifacts/legacy/oran/ has 5 moved files + submodule-docs/ with 4 copies + deprecation README.
- artifacts/ric/ has the 6 files (nonrtric-lab.md and nearrt-placeholder.md under E3's hyphenated names;
  no nonrtric_lab.md); grep -rn "compliant" artifacts/ric/ only in negations/roadmap framing.
- grep -rn "artifacts/oran" --include="*.md" --include="*.yaml" . (excluding .context/, artifacts/legacy/,
  docs/task_docs/) is empty; grep -rn $'—' artifacts/ric/ is empty.
- Only .md files and CLAUDE.md touched; no submodule content modified.
Commit style: "[docs]: archive artifacts/oran to legacy (D4); add artifacts/ric bundle for the RIC integration layer".
```

---

## E6.S3 — `.context/` knowledge-graph update

**Why:** The graph (16 pages, last verified 2026-07-13 @ 9b2b5f5) is the orientation layer every agent reads first; after E0–E4 it would describe four services that no longer have those roles, and its "Known gaps" list would state resolved gaps as open.

**Size:** M

**Scope:**
- In: four new pages (`data-platform`, `ndt-decision-hub`, `ric-integration`, `actuator-framework`); refresh stale pages (`data-sim`, `bdt-engine`, `rapp-engine`, `smo-sim`, `nybsys-ingestion`, `kafka-worker-pattern`, `gateway`, `deployment` if route split touched it); retire `oran-e2-r1` (tombstone or delete + fix links); update `index.md` (page tables, Known gaps, verification stamp) and the three MOC files; validate.
- Out: creating design docs (S1/S2); page content for epics not yet landed (each page's `last-verified` stamp must reference a real commit containing the code it describes).

**Files:**
- `.context/pages/data-platform.md`, `.context/pages/ndt-decision-hub.md`, `.context/pages/ric-integration.md`, `.context/pages/actuator-framework.md` (create)
- `.context/pages/{data-sim,bdt-engine,rapp-engine,smo-sim,nybsys-ingestion,kafka-worker-pattern,gateway,deployment}.md` (modify as needed)
- `.context/pages/oran-e2-r1.md` (retire: replace body with a tombstone linking `[[ric-integration]]` and `artifacts/legacy/oran/`, or delete and fix all inbound links — pick one, run the checker)
- `.context/index.md` (modify — page tables, Known gaps rewrite, header stamp)
- `.context/MOC/{Architecture MOC,Data MOC,Onboarding MOC}.md` (modify — add new pages to reading paths)
- `.context/_graph.json` (regenerate if the tooling maintains it; otherwise leave to graph_check)

**Contract:** page front-matter convention already used by the graph: every page carries `sources:` (file paths with line refs) and `last-verified: <date> @ <short-sha>`. New-page content contracts:

| Page | Must cover | Links |
|---|---|---|
| `data-platform` | data_sim's new role: adapter framework, canonical PM/FM/CM tables, `maveric.ingest.pm.v1` consumer inside the API container, `/ingest/**` + `/data/**` APIs, `/custom/nybsys/uploads` legacy contract served verbatim, feature-flag guard on `tenants.feature_flags['nybsys']`, store-only rule (no synthesis) | `[[data-sim]]`, `[[kafka-worker-pattern]]`, `[[multi-tenancy-rls]]`, `[[nybsys-ingestion]]` |
| `ndt-decision-hub` | bdt_engine's evaluate API, twin feature builder (pipeline stages 3–6 relocated; `semi_synthetic=true` labeling in `baselines.stats`), loop policy/guardrail gates, `maveric.loop.*` topics, rollback ordering, defense-in-depth split vs smo_sim's device-level watcher | `[[bdt-engine]]`, `[[actuator-framework]]`, `[[ric-integration]]`, `[[kafka-worker-pattern]]` |
| `ric-integration` | rapp `app/ric/` ports/adapters, A1-policy-aligned intents, NONRTRIC A1-PMS connector + `ric-lab` profile (A1-PMS + A1 Simulator container images, Apache-2.0), `a1_policy` loop executor, reserved `nearrt_xapp` placeholder, R1 packaging facade; explicit "integration layer, not a RIC" line | `[[rapp-engine]]`, `[[ndt-decision-hub]]`, `artifacts/ric/` |
| `actuator-framework` | smo_sim `app/actuators/` `ActuatorAdapter` protocol (capabilities/apply/read_back/rollback/health), command router keyed by loop-action `adapter` field, NanoLink TR-069 as first implementation, five wired placeholders, loop feedback hook to `maveric.loop.feedback.v1` | `[[smo-sim]]`, `[[nanolink-control-plane]]`, `[[ndt-decision-hub]]` |

`index.md` Known-gaps rewrite rules: remove gaps resolved by the program (E2/R1-absent-from-openapi → resolved by deletion D4; version skew → resolved by S1 lockstep; Kafka-unwired-in-data-sim → resolved by E1's consumer — keep "unwired in smo-sim" only if still true); keep unresolved gaps (frontend `lib/supabase/`, RLS-in-external-migrations if still true, `reset_stale_commands` startup-only if E4 did not fix it — verify each against code before deciding).

**Acceptance criteria:**
- `python .claude/skills/context-agent/tools/graph_check.py .context` exits 0 with 0 orphans / 0 broken links.
- Four new pages exist with `sources:` pointing at real files (verified by opening each cited path) and `last-verified` stamps at the current commit.
- No page still describes smo_sim as serving E2/R1, data_sim as synthetic-only, or rapp as computing twin KPIs internally.
- `index.md` header stamp updated (date @ sha, page/link counts); Known gaps list contains no resolved gap.
- Every claim on a refreshed page traces to a cited file (graph rule: pages whose claims are not traceable to code are a defect).

**Test plan:** `python .claude/skills/context-agent/tools/graph_check.py .context` (the graph's own validator — this is the story's test). Spot-check: for each new page, `ls` every path in its `sources:` block.

**Coding-agent prompt:**

```text
You are working in the CloudlyNet backend monorepo at /Users/laawanyakishor/Projects/NetAI/cloudlynet_ai.
Read docs/task_docs/cloudlynet-rearchitecture/01-hld-frozen.md (§2 roles, §4 contracts), then
docs/task_docs/cloudlynet-rearchitecture/epics/EPIC-6-docs-and-verification.md story E6.S3, then
.context/index.md to learn the graph's conventions (wikilinks, sources:, last-verified stamps, MOCs).

TASK: update the .context/ knowledge graph to the re-architected platform.
1. Create pages/data-platform.md, pages/ndt-decision-hub.md, pages/ric-integration.md,
   pages/actuator-framework.md per the content table in E6.S3. Ground every claim in real code:
   before writing a line, open the cited file in the relevant submodule (data_sim ingestion adapters,
   bdt_engine app/feature_builder + loop decision hub, rapp app/ric/, smo_sim app/actuators/) and cite
   path + line. If an epic has not landed yet, DO NOT create its page; note it in the PR and stop short.
2. Refresh stale pages: data-sim, bdt-engine, rapp-engine, smo-sim, nybsys-ingestion (pipeline split:
   parse/store in data_sim, synthesis stages 3-6 in bdt_engine feature builder), kafka-worker-pattern
   (new topics maveric.ingest.pm.v1 + maveric.loop.*, consumer-in-API-container pattern), gateway
   (custom/nybsys/uploads* -> DATA split rule, duplicate-route panic fix) and deployment if needed.
   Bump each page's last-verified stamp only after re-verifying its claims against code.
3. Retire pages/oran-e2-r1.md: replace its body with a short tombstone pointing at [[ric-integration]]
   and artifacts/legacy/oran/, or delete the page and fix every inbound link. Either way the checker
   must pass.
4. Rewrite index.md: add the new pages to the tables, update the MOCs (.context/MOC/*.md) reading
   paths, refresh the header stamp (date @ current short sha, page/link counts), and rewrite "Known
   gaps": drop gaps resolved by the re-architecture (E2/R1 openapi gap resolved by deletion; version
   skew resolved by design-docs v0.6.0 lockstep; data-sim Kafka now wired) after VERIFYING each in
   code, and keep gaps still true (check frontend lib/supabase/, RLS-in-external-migrations,
   reset_stale_commands timer against current code before deciding).

CONSTRAINTS: evidence-only (every claim cites a file); never edit submodules from repo root; this story
touches only .context/ files; product name CloudlyNet.

DEFINITION OF DONE:
- python .claude/skills/context-agent/tools/graph_check.py .context -> 0 orphans, 0 broken links.
- 4 new pages with valid sources; no page describes the old roles; index stamp current.
Commit style: "[docs]: context graph - data-platform/ndt-decision-hub/ric-integration/actuator-framework pages; refresh stale pages".
```

---

## E6.S4 — Submodule README/Agent.md drift fixes (data_sim, smo_sim, rapp)

**Why:** Recon flagged three concrete drifts that mislead every agent opening those submodules: data_sim's README describes a layout that does not exist (`design/` dir, `app/workers/generate_worker.py` — neither present), smo_sim's README overclaims E2/R1 ("implemented following the O-RAN E2AP… specifications", lines 81–158), and rapp's README pins port 8004 while the service runs on 8001 (`README.md:147`).

**Size:** S

**Scope:**
- In: truth-only rewrites of the three READMEs (layout blocks, ports, capability sections); same-drift check in each submodule's `Agent.md`; role paragraphs updated to the frozen-HLD roles once the owning epic has landed; pointer line "design docs live in the parent repo `artifacts/`" per parent CLAUDE.md rule.
- Out: deleting smo_sim's E2/R1 code/harnesses or its root `e2_spec.md`/`r1-plan.md` files (E4 owns deletion; archives created in S2); copilot submodule (own context layer); frontend (E0 rebrand story).

**Files** (each in its own submodule — `cd` into the submodule before any git op; one PR per submodule; do **not** stage submodule pointer bumps in the parent repo):
- `submodule/maveric_platform_data_sim/README.md` (modify — fake layout block at lines ~3–30; describe real tree: `app/api/v1/…`, `alembic/`, no `design/`, no `app/workers/`; after E1: ingestion adapters + consumer-in-API-container + canonical tables + `/ingest`,`/data`,`/custom/nybsys/uploads` roles)
- `submodule/maveric_platform_data_sim/Agent.md` (check/modify for the same drift)
- `submodule/maveric_platform_smo_sim/README.md` (modify — delete the "R1 interface alignment (SMO-5)" and "E2 interface implementation" sections, lines ~81–158; fix the layout block's `design/` reference; add Actuation & Integration role summary + `app/actuators/` once E4 lands; add one line: "E2/R1 REST facades were removed <date>; archived design docs: parent repo artifacts/legacy/oran/")
- `submodule/maveric_platform_smo_sim/Agent.md` (check/modify)
- `submodule/maveric_platform_rapp/README.md` (modify — line 147 `servers: [ { url: http://localhost:8004/v1 } ]` → `http://localhost:8001/v1`; fix layout block; add RAN Intelligence role summary + `app/ric/` pointer once E3 lands)
- `submodule/maveric_platform_rapp/Agent.md` (check/modify)

**Contract:** README structure per submodule (submodules keep only how-to-run/develop content per parent CLAUDE.md):

```markdown
# <submodule name>

One-paragraph role (frozen-HLD §2 wording, code-true at time of merge).

## Where the design docs live
All architecture/contract/schema docs live in the parent repo: cloudlynet_ai/artifacts/
(design/, ric/, nanolink/, migration/). This repo keeps only run/develop docs.

## Project layout   <- must list only paths that exist (verify with ls)
## Run / develop    <- ports must match parent CLAUDE.md service table (rapp 8001, smo 8002, data 8003, bdt 8000)
## Tests            <- real command for this submodule
```

**Acceptance criteria:**
- Every path in each README/Agent.md layout block exists (`ls` proof); every port matches the parent CLAUDE.md service table.
- smo_sim README contains no claim of implementing/following O-RAN E2AP/E2SM/R1AP specs; `grep -inE "o-ran|e2ap|e2sm|r1ap" README.md Agent.md` in smo_sim returns only the archival pointer line (or nothing).
- rapp README has no `8004` occurrence.
- data_sim README has no `design/` or `app/workers/generate_worker.py` reference.
- Parent repo working tree clean of submodule pointer changes for these commits.

**Test plan:** doc-only. Per-submodule sanity that docs match reality: in data_sim/smo_sim run `uv run pytest` (should be unaffected — proves no stray file edits), in rapp `PYTHONPATH=app:app/radplib/dependencies uv run pytest` if any doubt; primary verification is the `ls`/grep checks above.

**Coding-agent prompt:**

```text
You are working in the CloudlyNet backend monorepo at /Users/laawanyakishor/Projects/NetAI/cloudlynet_ai.
Read docs/task_docs/cloudlynet-rearchitecture/01-hld-frozen.md §2 (target roles) and
docs/task_docs/cloudlynet-rearchitecture/epics/EPIC-6-docs-and-verification.md story E6.S4.
GIT RULE: always cd into the submodule before any git operation; never stage submodule pointer
changes in the parent repo; one commit/PR per submodule.

TASK: make three submodule READMEs (and Agent.md where drifted) truth-only.
1. submodule/maveric_platform_data_sim/README.md: the "Project layout" block describes a repo that
   does not exist (design/ dir, app/workers/generate_worker.py). Replace it with the actual tree
   (verify every line with ls). Update the role paragraph to the Data Platform role (ingestion
   adapters -> canonical PM/FM/CM tables + raw S3; synthetic factory; Kafka ingestion consumer runs
   inside the API container) ONLY if epic E1 has landed in this submodule; otherwise describe current
   code. Check Agent.md for the same drift.
2. submodule/maveric_platform_smo_sim/README.md: DELETE the sections "R1 interface alignment (SMO-5)"
   and "E2 interface implementation" (approx lines 81-158; they claim the interfaces were
   "implemented following the O-RAN ... specifications", which is forbidden overclaim and the code is
   deleted by epic E4). Add one pointer line: E2/R1 REST facades removed per re-architecture D4;
   archived docs live in the parent repo at artifacts/legacy/oran/. Fix the layout block (no design/
   dir). If E4's app/actuators/ framework has landed, document it (ActuatorAdapter protocol, adapter
   registry, placeholders). Check Agent.md too.
3. submodule/maveric_platform_rapp/README.md: line ~147 says servers url http://localhost:8004/v1 -
   the service runs on 8001 (parent CLAUDE.md service table); fix it. Fix the layout block. If epic
   E3 has landed, add a short app/ric/ section (ports/adapters; "integration layer, not a RIC").
   Check Agent.md too.
4. In all three: add a "Where the design docs live" section pointing at the parent repo artifacts/
   (design/, ric/, nanolink/, migration/) - submodules keep only run/develop docs.

CONSTRAINTS: no code changes; no O-RAN compliance/overclaim wording anywhere (see
artifacts/marketing/claims-guardrails.md §2); product name CloudlyNet; ports must match the parent
CLAUDE.md table (bdt 8000, rapp 8001, smo 8002, data 8003).

DEFINITION OF DONE (per submodule):
- Every path in the layout block exists; grep -n "8004" rapp README empty; grep -inE
  "e2ap|e2sm|r1ap|o-ran" smo_sim README/Agent.md returns at most the archival pointer.
- Commits made inside each submodule; parent repo has NO staged submodule pointer change.
Commit style (in each submodule): "[docs]: README truth pass - fix layout/port/E2-R1 drift".
```

---

## E6.S5 — Claims-guardrails re-verification + rung updates (final gate, after E3/E5)

**Why:** `claims-guardrails.md` is stamped "verified against code 2026-07-09" and its §2 engineering blockers (the `/etwoint/e2ap` route landmine, R1 dead subscriptions) are resolved by E4's deletion, while E3+E5 move the open-RIC integration claim from Building to Today (Lab) for the NONRTRIC A1 path. Docs claiming stale rungs in either direction (over- or under-claiming) defeat the guardrail system.

**Size:** M

**Scope:**
- In: full §-by-§ re-verification of `claims-guardrails.md` against merged code with fresh stamps; §2 rewrite (facades deleted, RIC layer exists, rung moves); roadmap.md rung updates; product.html + roadmap.html rung strings; offering-ladder rung table (guardrails §8 packages: Lite Today (lab) unchanged; Advanced items progress only where E2/E3/E5 landed evidence exists; Site stays Building unless evidence exists); root marketing `.md` engineering-truth files where wording changed.
- Out: gtm-pack sync + regeneration (S6); inventing any new claim not backed by a file citation; any Field/Scale rung claim (none exists — lab demo evidence is Lab rung only).

**Files:**
- `artifacts/marketing/claims-guardrails.md` (modify — header stamp line 4, §1 "As of <date>" line 42, §2 "What exists" lines 49–71, §2 engineering-actions block lines 109–117, §8 package rung table lines ~345–347, footer stamp line 376)
- `artifacts/marketing/roadmap.md` (modify — "Last updated" line 4; §2.1 rows 61–62 where E2 landed; §2.3 rows 88–95 + the open-RIC track block lines 98–118; §3 delivery table; §4 items resolved by the program)
- `artifacts/marketing/product.html`, `artifacts/marketing/roadmap.html` (modify — internal, noindexed pages; update the same rung strings)
- Root engineering-truth docs where the rung wording appears: `artifacts/marketing/{positioning.md, product.md, toolchain-fit.md, capabilities.md}` (grep-driven; touch only rung/wording lines)

**Contract — the specific verdict changes (each requires a code citation before it may be written):**

| Claim | Old rung | New rung (condition) | Required evidence citation |
|---|---|---|---|
| Open-source RIC integration (NONRTRIC A1 path: `a1_policy` executor → A1-PMS → A1 Simulator) | Building ("on the roadmap: rApps/xApps on an open-source RIC we integrate") | **Today (Lab)** — only if E3 landed AND E5's closed-loop demo ran | `submodule/maveric_platform_rapp/app/ric/…`, compose profile `ric-lab` in root `docker-compose.yaml`, E5 demo artifact |
| `/etwoint/e2ap` route landmine (guardrails §2 engineering action #1) | Open blocker | **Resolved by deletion** (D4/E4) — rewrite as resolved with date | absence proof: `grep -rn "etwoint\|e2ap" submodule/maveric_platform_smo_sim/app/` → empty |
| R1 silent-drop subscriptions (§2 engineering action #3) | Open blocker | **Resolved by deletion** | same absence proof for `roneint`/`r1_interface` |
| §2 action #2 "update artifacts/oran docs" | Open | **Superseded** — bundle archived to `artifacts/legacy/oran/`, successor `artifacts/ric/` (S2) | path existence |
| Closed loop with policy gate + rollback (twin-evaluated) | partial (device-level only) | **Today (Lab)** if E5 demo ran; else Building | E5 demo runbook/artifact |
| "Consolidate inference + KPI tracking into the twin" (roadmap §2.1) | Building | **Today** (simulation rung) if E2 landed | `submodule/maveric_platform_bdt_engine/app/…` evaluate API |
| Offering ladder: Lite | Today (lab) | **unchanged** | n/a |
| Offering ladder: Advanced rows touching twin-evaluated loop / open-RIC lab path | Vision/Building | progress one rung only where the rows above moved; phrase as "in lab" | same as rows above |

Wording rules that survive unchanged and must be re-asserted, not weakened: never "O-RAN compliant/certified"; the RIC (not CloudlyNet) provides E2 termination; "A1-policy-aligned intents"; integration claims labeled by rung; no Field/Scale claim; NanoLink is LTE FDD Band 3 (never "5G NR TDD"); no "carrier grade"/"zero-touch"/"self-healing"; no em dash (U+2014) in marketing-bound text; humanized headings.

Re-stamp format (both stamp locations): `Every claim below was verified against code on <YYYY-MM-DD> (re-architecture epics E0-E5, commit <short-sha>).`

**Acceptance criteria:**
- Both stamps in claims-guardrails.md carry the new date + commit; §1 "As of" line updated.
- §2 "What exists" describes the post-D4 reality (facades deleted; RIC integration layer in rapp; NONRTRIC A1-PMS lab profile) with file citations; the three engineering actions are marked resolved/superseded with dates.
- Every rung change in the table above is present iff its evidence citation is real (reviewer spot-checks each).
- `grep -rn $'—' artifacts/marketing/*.md` → empty for every file touched; forbidden-term grep (`grep -rinE "o-ran compliant|o-ran certified|carrier.grade|zero.touch|self.healing|5G NR TDD" artifacts/marketing/ --include="*.md" --include="*.html"`) returns only don't-say-list mentions inside guardrails/positioning themselves.
- roadmap.md "Last updated" bumped; product.html/roadmap.html rung strings match the .md sources.
- No claim moved to Field or Scale anywhere.

**Test plan:** doc-only; verification is the grep suite above plus manual evidence-citation review. Run the absence proofs (`grep -rn "etwoint\|roneint" submodule/maveric_platform_smo_sim/app/`) and paste outputs into the PR description.

**Coding-agent prompt:**

```text
You are working in the CloudlyNet backend monorepo at /Users/laawanyakishor/Projects/NetAI/cloudlynet_ai.
PRECONDITION: epics E3 (RIC layer), E4 (E2/R1 deletion), and E5 (closed-loop demo) have merged. Verify
each before writing a single rung change; if one has not merged, do only the parts whose evidence
exists and say so in the PR.
Read, in order: docs/task_docs/cloudlynet-rearchitecture/01-hld-frozen.md;
artifacts/marketing/claims-guardrails.md end to end;
docs/task_docs/cloudlynet-rearchitecture/epics/EPIC-6-docs-and-verification.md story E6.S5 (it has the
exact verdict table with required evidence citations).

TASK: re-verify the claims system against merged code and update rungs.
1. artifacts/marketing/claims-guardrails.md: re-verify every section against code. Rewrite §2 "What
   exists": the smo_sim E2/R1 REST facades are deleted (cite the absence:
   grep -rn "etwoint|roneint" submodule/maveric_platform_smo_sim/app/ must be empty); what exists now
   is the RIC integration layer in submodule/maveric_platform_rapp/app/ric/ (ports/adapters,
   NONRTRIC A1-PMS connector + a1_policy executor, lab compose profile ric-lab with NONRTRIC A1-PMS +
   A1 Simulator container images; near-RT reserved placeholder nearrt_xapp only). Move the
   open-RIC integration claim from Building to Today (Lab) FOR THE NONRTRIC A1 PATH ONLY, with file
   citations. Mark the three "Engineering action required" items resolved/superseded with dates
   (route landmine: resolved by deletion; oran docs: archived to artifacts/legacy/oran, successor
   artifacts/ric/; R1 silent subscriptions: resolved by deletion). Re-stamp BOTH verification lines
   (header line ~4 and footer line ~376) with today's date + current short commit sha; update the §1
   "As of <date> CloudlyNet has no Field or Scale rung evidence" line (this stays true - the lab demo
   is Lab rung).
2. artifacts/marketing/roadmap.md: bump "Last updated"; §2.1 move "Consolidate inference + KPI
   tracking into the twin" to Today (simulation rung) if E2 landed; §2.3 open-RIC track rows to
   Today (Lab) where E3+E5 evidence exists; update §3 delivery table and close §4 items the program
   resolved. Keep everything without evidence at its current rung.
3. artifacts/marketing/product.html and roadmap.html: update the same rung strings so the HTML pages
   match the .md sources (they are hand-authored internal pages, edit in place).
4. Root engineering-truth docs (artifacts/marketing/positioning.md, product.md, toolchain-fit.md,
   capabilities.md): grep for the moved claims and align wording. Offering ladder (guardrails §8
   packages table): Lite stays Today (lab); Advanced rows progress ONE rung only where the underlying
   capability moved above; Site stays Building.

HARD WORDING RULES: never "O-RAN compliant/certified"; the RIC provides E2 termination, not
CloudlyNet; "A1-policy-aligned intents"; every capability line carries its rung; NO em dash character
(U+2014) in any marketing-bound text (use commas, colons, or parentheses); humanized sentence-case
headings; NanoLink is LTE FDD Band 3, never "5G NR TDD"; no "carrier grade"/"zero-touch"/
"self-healing"; no Field/Scale claim anywhere; product name CloudlyNet; never state a rung change
without a real file citation.

DEFINITION OF DONE:
- Both guardrails stamps updated; §2 rewritten with citations; three engineering actions closed.
- grep -rn $'—' on every touched file -> empty; forbidden-term grep (E6.S5 acceptance criteria)
  clean; absence-proof grep outputs pasted into the PR description.
- roadmap.md/product.html/roadmap.html rungs consistent with each other and with code.
Commit style: "[docs]: claims re-verification - open-RIC lab path to Today (Lab); E2 route landmine closed by deletion; re-stamp".
```

---

## E6.S6 — Marketing follow-ups: domain migration plan, rebrand pointer, GTM pack regeneration

**Why:** Three loose ends must be registered so they are owned, not forgotten: the `<platform-host>` domain outlives the CloudlyNet rename (and edge agents pin it), the frontend UI rebrand belongs to E0 and needs a tracked pointer, and the generated GTM pack must be rebuilt after any S5 wording change or it silently diverges from the engineering-truth docs.

**Size:** S

**Scope:**
- In: `artifacts/deployment/domain-migration-plan.md` (plan document only — infra execution is out of program scope); roadmap.md §4 register entries (domain migration; frontend rebrand pointer to E0); sync `artifacts/marketing/gtm-pack/*.md` sales editions with S5's engineering-truth changes; regenerate `gtm-pack-cloudlynet.html` via `python3 artifacts/marketing/build_site.py`; update `artifacts/marketing/README.md` if the doc map changed.
- Out: any DNS/ingress/chart change (zero CI/CD rule — the plan doc explicitly defers execution); frontend code changes (E0); new marketing claims (S5 owns wording verdicts; this story propagates them).

**Files:**
- `artifacts/deployment/domain-migration-plan.md` (create)
- `artifacts/marketing/roadmap.md` (modify — §4 register: add domain-migration item; update the frontend-rebrand item to point at the E0 story)
- `artifacts/marketing/gtm-pack/{positioning,product,toolchain-fit,sales-pitch,sales-motion,gtm-strategy,icp}.md` (modify only where S5 changed the corresponding root doc)
- `artifacts/marketing/gtm-pack-cloudlynet.html` (regenerated — never hand-edited)
- `artifacts/marketing/README.md` (modify if needed)

**Contract:** `domain-migration-plan.md` required content (plan-only, infra-scope):

```markdown
# Domain migration plan: <platform-host> -> <cloudlynet target> (infra scope, out of code scope)

Status: registered, not scheduled. No code or chart change in the re-architecture program.

## Load-bearing facts (from submodule/maveric-deployment recon)
- <platform-host> is served by the frontend chart nginx ingress; path /v1 routes to
  maveric-platform-gateway:8080 BEFORE the / catch-all (values.yaml apiProxy block).
- NanoLink edge agents call https://<platform-host>/v1/agent/** and smo_sim charts pin
  PUBLIC_BASE_URL=https://<platform-host>/ (staging: https://staging.<platform-host>/).
  Cutting the old domain over strands every deployed edge agent.

## Plan (when scheduled)
1. Dual-host phase: add the new host as an ADDITIONAL ingress host + TLS cert; old host keeps serving.
2. Re-issue enrollment material / PUBLIC_BASE_URL for NEW edge installs only; existing agents keep
   the old host until their next maintenance touch.
3. Frontend NEXT_PUBLIC_API_BASEURL + Cognito callback URLs updated in chart secretData (base64).
4. Deprecation window measured in agent-fleet check-ins observed on the old host, not calendar time.
5. Only then: old host 301/410 posture decision.

## Explicitly out of scope for the re-architecture program
Any chart, secretData, DNS, or pipeline change. This document exists so the dependency graph
(edge agents -> PUBLIC_BASE_URL -> ingress host) is written down before anyone touches DNS.
```

GTM pack sync rule (from `artifacts/marketing/README.md`): `gtm-pack/*.md` are intended-state sales rewrites of the root engineering-truth docs; the generated HTML embeds them verbatim. Regeneration command: `python3 artifacts/marketing/build_site.py` (rebuilds content blocks + PAGES array, preserves shell CSS/JS byte-for-byte). The pack is internal-only and rung-free **by design** — sync means propagating renames/wording/structure, not adding rung labels there.

**Acceptance criteria:**
- `domain-migration-plan.md` exists with the load-bearing facts + phased plan + out-of-scope section; zero chart/DNS/pipeline files touched.
- roadmap.md §4 has the domain item ("registered, infra scope") and the frontend-rebrand item pointing at the E0 story ID.
- `python3 artifacts/marketing/build_site.py` runs clean; `git diff artifacts/marketing/gtm-pack-cloudlynet.html` shows changes only inside `<script type="text/markdown" data-doc=…>` blocks, the PAGES array, and date lines (shell preserved).
- No em dash (U+2014) introduced in any touched `.md`; no legacy claim (guardrails-forbidden list) reintroduced into the pack.
- gtm-pack docs contain no wording that S5 changed in the root docs but was left stale here (grep the changed phrases).

**Test plan:** `python3 artifacts/marketing/build_site.py` (must exit 0); open the regenerated HTML locally and confirm nav + embedded docs render; grep suite from S5 re-run over `artifacts/marketing/gtm-pack/`.

**Coding-agent prompt:**

```text
You are working in the CloudlyNet backend monorepo at /Users/laawanyakishor/Projects/NetAI/cloudlynet_ai.
PRECONDITION: story E6.S5 (claims re-verification) has merged. Read
docs/task_docs/cloudlynet-rearchitecture/epics/EPIC-6-docs-and-verification.md story E6.S6,
artifacts/marketing/README.md (pack sync rules), and artifacts/marketing/claims-guardrails.md.

TASK:
1. Create artifacts/deployment/domain-migration-plan.md using the skeleton in E6.S6: <platform-host>
   is the live production host (frontend ingress /v1 -> maveric-platform-gateway:8080; edge agents pin
   https://<platform-host>/v1/agent/** via PUBLIC_BASE_URL). The plan is REGISTERED ONLY: dual-host
   phase, new-installs-first enrollment, chart secretData updates listed as future infra work, fleet
   check-in-driven deprecation. State explicitly that no chart/DNS/pipeline change happens in this
   program. Touch no file under submodule/maveric-deployment/.
2. artifacts/marketing/roadmap.md §4 (compliance & tech-debt register): add the domain-migration item
   (infra scope, plan doc linked) and update the frontend UI rebrand item to point at epic E0's
   rebrand story (repo-wide CloudlyNet rename; frontend strings included there, not here).
3. Sync artifacts/marketing/gtm-pack/*.md with any wording S5 changed in the root engineering-truth
   docs (diff each root doc against its gtm-pack sibling; propagate renames/wording, keep the pack's
   intended-state, rung-free style - it is internal sales training material and README.md documents
   that posture). Do not add rung labels inside gtm-pack files; do not reintroduce any forbidden
   claim (O-RAN compliant, carrier grade, zero-touch, 5G NR TDD, invented figures).
4. Regenerate the pack: python3 artifacts/marketing/build_site.py. Verify the diff on
   gtm-pack-cloudlynet.html only touches embedded markdown blocks / PAGES array / date lines.
5. Update artifacts/marketing/README.md if the doc map changed.

CONSTRAINTS: no em dash character (U+2014) in any text you write; humanized headings; product name
CloudlyNet; zero CI/CD change; gtm-pack-cloudlynet.html is generated, never hand-edited.

DEFINITION OF DONE:
- Plan doc exists; roadmap §4 updated; build_site.py exits 0; HTML diff confined to content blocks;
- grep -rn $'—' over touched .md files empty; forbidden-term grep over gtm-pack/ clean.
Commit style: "[docs]: register domain-migration plan; sync + regenerate GTM pack after claims re-verification".
```

---

## Rollout / migration notes

**Order.** E6 is continuous with two anchors:

1. **Early (can start immediately, truth-only):** S4 (submodule README drift — the port/layout/overclaim fixes are true today; the role-paragraph upgrades wait for the owning epic), S2 steps 1–2 (archive `artifacts/oran/` — D4 is decided; archiving does not depend on E4's code deletion having merged, but the deprecation README should cite E4's PR once it exists).
2. **Per-epic tail:** after each of E1–E4 merges, S1's corresponding doc sections, S2's `artifacts/ric/` code citations, and S3's pages for that epic get written/re-verified. Keep PRs small and epic-tagged.
3. **Final gate (strict order):** E5 merges → S5 (claims re-verification, rung moves, stamps) → S6 (pack sync + regeneration + registers). S5 must never merge before its evidence exists; S6 must never merge before S5.

**Backward-compat shims.** No runtime shims (docs-only epic). Link compatibility: `artifacts/oran/` is fully moved with all in-repo references fixed in the same PR (no stub left behind); external bookmarks are acceptable breakage for an internal bundle. `openapi.yaml` is strictly additive; `/custom/nybsys/**` documentation keeps the exact legacy request/response schemas with only backend-pointer prose changed (mirrors HLD §3.2 byte-compatibility).

**Data migration.** None owned by E6. `artifacts/design/schemas.sql` additions affect **fresh local databases only** (compose init SQL); live databases are migrated by E1/E2/E4's numbered migrations in `artifacts/migration/`, which E6 indexes but does not author. If E6's reference DDL and a landed migration diverge, the migration wins (ownership rule at top).

**Coordination handshakes.** S2 archives copies of smo_sim root docs while E4 deletes the originals — sequence the archive PR before or with E4's deletion PR so history is never only-in-reflog. S4's smo_sim README rewrite lands with/after E4's deletion. S1's loop-table mirror lands after E2's migration (or is corrected to it). CLAUDE.md edits (S2 bundle table; E0 owns naming lines) are called out for explicit owner review in PR descriptions.

## Epic-level risks

1. **Docs ahead of code (rung inflation).** The single worst failure: S5 moving open-RIC to Today (Lab) before E3+E5 actually merged, or S1/S3 describing modules that slipped. Mitigation is structural: every rung change and every `.context` page requires a file citation verified at authoring time, and each coding-agent prompt starts with a precondition check.
2. **Parallel-epic merge conflicts on shared mirrors.** `openapi.yaml`/`schemas.sql` are also touched by E1/E2 stories if those epics ship their own doc updates. The ownership rule (code epics own migrations, E6 owns mirrors; migrations win) must be stated in each E6 PR description; otherwise two agents will fight over DDL text.
3. **Naming ambiguity window.** Frozen HLD mandates CloudlyNet while parent CLAUDE.md and user memory still say "NetAI by Cloudly"; until E0's rebrand lands, E6 PRs will mix with older NetAI strings in files E6 does not own. E6 uses CloudlyNet in every touched file and leaves the rest to E0 — reviewers must not "helpfully" widen scope.
4. **GTM pack leak surface.** `gtm-pack-cloudlynet.html` presents intended state without rungs by design (internal sales training). Regenerating it after S5 keeps it consistent, but if it ever leaks externally it violates guardrails on its own; the README posture note must survive S6.
5. **Guardrails weakening under edit pressure.** S5 rewrites §2, the highest-risk section of the highest-risk document. The re-verification must re-assert the forbidden list and negation framings verbatim, not just update rungs — a reviewer should diff §2's forbidden/defensible lists for accidental deletions.
6. **`.context` gap-list regressions.** Removing a "known gap" that is in fact still true (e.g., `reset_stale_commands` timer if E4 didn't fix it) silently re-poisons agent context; S3 requires per-gap code verification before removal.
7. **CLAUDE.md edit governance.** S2 touches the parent CLAUDE.md bundle table; this is flagged for explicit human sign-off in the PR, since agent workflows must not self-authorize CLAUDE.md changes.

---

## Execution status (2026-08-10) — EPIC COMPLETE, 6/6

Executed after the full E0–E5 merge to main (all repos, 2026-08-10), as two adversarially-verified
waves. Every story's output was checked by an independent verifier agent against this spec and the
merged code; all verdicts pass, zero blocking findings open.

| Story | Status | Evidence |
|---|---|---|
| S1 design docs v0.6.0 | DONE | HLD/LLD/openapi all 0.6.0 + lockstep sentence; 16 new paths (`/ndt/**`, `/ingest/**`, `/data/**`, loop) added, zero public paths/schemas removed (diff-verified); openapi-spec-validator OK; schemas.sql canonical+loop DDL matches landed 011/014 (landed-migration-wins divergences recorded in the S1 report: no CHECK on `loop_actions.status`, `updated_by` present, `pm_measurements` PK/`granularity_s NOT NULL`, `ingest_jobs.job_id text`) |
| S2 oran→legacy + ric bundle | DONE | `artifacts/oran/` archived to `artifacts/legacy/oran/` (git renames, D4 README); `artifacts/ric/` 6 files, every code claim verified (rapp `app/ric/`, ric-lab profile: A1-PMS 2.11.0 + 2× a1-simulator 2.8.1); zero dangling `artifacts/oran` refs outside `.context` (fixed by S3) and planning docs |
| S3 .context refresh | DONE | 21 pages (4 new: data-platform, ndt-decision-hub, ric-integration, actuator-framework); graph_check: 0 broken / 0 orphans; all touched pages stamped 2026-08-10 @ eec8203; known-gaps list re-verified per gap (dropped 4 resolved, kept 3 still-true, added 3 new) |
| S4 submodule READMEs | DONE | data_sim layout fixed, smo_sim E2/R1 overclaim removed (Actuation role; `ocudu_ws_collector` documented collect-only implemented), rapp port 8001; every path/port/command ls/grep-verified |
| S5 claims re-verification | DONE | claims-guardrails.md + roadmap/product/positioning/toolchain-fit/capabilities re-stamped 2026-08-10 @ eec8203; E2/R1 blockers RESOLVED with absence proofs; NONRTRIC A1 rung → Today (Lab) exactly; forbidden-phrase and em-dash greps clean on all touched files |
| S6 GTM follow-ups | DONE | `artifacts/deployment/domain-migration-plan.md` (<platform-host> outliving the rename; token-minting mechanism code-verified), roadmap items #8/#11 registered, `build_site.py` regenerated the GTM pack (exit 0, idempotent) |

Governance note per risk 7: the parent `CLAUDE.md` bundle-table row (`artifacts/oran/` → `artifacts/ric/`)
was edited by S2 and is called out for explicit human review in the landing PR.
