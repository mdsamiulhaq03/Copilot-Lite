# Decision record — guardrail_decision_log RLS + deployment wiring

**Date:** 2026-07-22 · **Owner:** platform/devops · **Status:** decided + copilot answers folded in (2026-07-22). Env change applied; RLS/index/bootstrap edits staged next.

Reconciling the merged guardrail work (`CloudlyIO/cloudlynet_ai#285`, `cloudlynet_ai_copilot#27`)
against the deployed ArgoCD/Helm charts (`submodule/maveric-deployment/argocd`). This records the
calls made on the platform side so the copilot team sees our decisions before we port RLS into the
prod chart. `conversation.guardrail_decision_log` currently has **no RLS in prod** — waiting does not
regress anything, so these land together when the open questions below are answered.

Context fact: `maveric_platform_postgres` is one common Postgres instance; copilot has its own logical
DB (`netai_copilot`) on it, created by the bootstrap job. The app connects to that DB.

---

## Decisions

### D1 — Path 2 (scoped ops role), NOT `BYPASSRLS`
No `BYPASSRLS` role exists anywhere in the platform today; this would be the first. `BYPASSRLS` is a
**role attribute, not table-scoped** — it exempts the role from RLS on every table on every
connection, which is over-privileged for a single-table audit-review CLI. **Approved: path 2** — keep
`FORCE` RLS and gate ops access with a dedicated role named in the policy. Least-privilege, table-scoped,
reversible.

### D2 — New `copilot_ops` role, provisioned in the bootstrap job
Add a dedicated login role `copilot_ops` in `copilot-bootstrap-job.yaml` (alongside owner + app), with:
`CONNECT` on `netai_copilot`, `USAGE` on schema `conversation`, and `SELECT, UPDATE` on
`conversation.guardrail_decision_log`. The application keeps connecting as its existing runtime role. **Cross-validated 2026-07-22** against
the deployed secret (`values.yaml` `secretData.DATABASE_URL`): the backend connects as
**`netai_copilot_app`** (not `netai_copilot_owner` as `.env.example` suggested). `copilot_ops` is
distinct from `netai_copilot_app`. Under `FORCE` RLS the app role is bound by policies regardless of
being owner or not, so this correction does not change the policy design.

### D3 — Policy design (no dependency on `app.current_user_id`)
Reads/updates are **ops-only**; the app only writes (fire-and-forget insert, may carry
`tenant_id = NULL` for pre-auth PII blocks). So the SELECT/UPDATE policies key on `current_user =
'copilot_ops'` and do **not** depend on the `app.current_user_id` GUC (which `database.py` does not
set — it only sets `app.current_tenant_id`). This sidesteps the missing-GUC risk entirely.

```sql
-- conversation.guardrail_decision_log — audit table. FORCE RLS; writes fire-and-forget from the
-- middleware (tenant_id may be NULL); reads/updates ops-only via copilot_ops (HITL review CLI).
-- No BYPASSRLS (D1). App role gets INSERT only; it never reads this table.
ALTER TABLE conversation.guardrail_decision_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversation.guardrail_decision_log FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS guardrail_log_insert ON conversation.guardrail_decision_log;
CREATE POLICY guardrail_log_insert ON conversation.guardrail_decision_log
  FOR INSERT WITH CHECK (true);            -- audit writes must never fail on RLS

DROP POLICY IF EXISTS guardrail_log_ops_read ON conversation.guardrail_decision_log;
CREATE POLICY guardrail_log_ops_read ON conversation.guardrail_decision_log
  FOR SELECT USING (current_user = 'copilot_ops');

DROP POLICY IF EXISTS guardrail_log_ops_update ON conversation.guardrail_decision_log;
CREATE POLICY guardrail_log_ops_update ON conversation.guardrail_decision_log
  FOR UPDATE USING (current_user = 'copilot_ops') WITH CHECK (current_user = 'copilot_ops');
```

This block goes into `argocd/maveric_platform_copilot/files/03-copilot-rls.sql` (applied by the copilot
`migration-job` as admin), mirroring the source `artifacts/db/init_copilot_rls.sql` intent but with the
`copilot_ops` predicate instead of a `BYPASSRLS` comment.

### D4 — Review CLI contract (CLI does not exist yet)
`scripts/guardrail-review.py` is only referenced in a comment today. Decision: when built, it connects
as **`copilot_ops`** and performs **`SELECT` + `UPDATE`** (it sets `reviewer_label`, `reviewer_note`,
`reviewed_at` post-hoc). That is why D3 grants `copilot_ops` both SELECT and UPDATE. If the copilot team
later decides the CLI is read-only, we tighten to SELECT-only.

### D5 — Deployed index alignment (additive only)
The prod table shipped the "Version A" index set. #285's purpose-built indexes
(`idx_guardrail_log_unreviewed_blocks` partial, `idx_guardrail_log_user_id` partial) are missing.
Decision: add **both** as additive `CREATE INDEX IF NOT EXISTS` to the chart's `02-copilot-schema.sql`
(safe, no rewrite). We do **not** change `guardrail_name varchar` → `varchar(50)`: the table already
exists, `CREATE TABLE IF NOT EXISTS` is a no-op on it, and the length cap is immaterial. Canonical-file
de-dup remains the copilot team's (Q1).

### D6 — Guardrail env vars + prod mode
Done: the 7 `GUARDRAIL_*` vars are surfaced in `argocd/maveric_platform_copilot/values.yaml`
`backend.env` (prod-only chart) with the compose/Pydantic defaults, so operators can tune without an
image change. **`GUARDRAIL_MODE=enforce`** set per copilot sign-off (2026-07-22). `GROQ_API_KEY` is
present in the `maveric-aws-copilot` secret (`gsk_` prefix) — required for enforce to actually block,
since `safeguard.py` reads it via `os.getenv` and, with `FAIL_OPEN=true`, a missing key would silently
fail-open. No `GUARDRAIL_*` in `secretData`, so no `env`/`envFrom` collision.

**Env caveat flagged:** `secretData.APP_ENV` decodes to `production` but `DATABASE_URL` points at a
`<cluster-service>` host — verify which environment this chart actually targets before
relying on "enforce in prod".

---

## Copilot answers folded in (2026-07-22)
- **Q1 — Answered:** #285 "Version B" is authoritative → D5 adds its two partial indexes. Copilot to
  de-dup `copilot_schemas.sql` in their repo (their action, tracked below).
- **Q2 — Resolved by inspection:** only `GROQ_API_KEY` lives in `secretData`; no `GUARDRAIL_*` there,
  so the chart `env` values do not collide with `envFrom`.
- **Q3 — Answered + corrected:** intended `netai_copilot_owner`, but the deployed secret shows the app
  connects as **`netai_copilot_app`**. Design unaffected (see D2).
- **Q4 — Answered:** flip to **enforce** now (D6).

## Still on the copilot team
- De-dup the double `guardrail_decision_log` definition in `copilot_schemas.sql` (Version B wins).
- Build `scripts/guardrail-review.py` to the D4 contract (connect as `copilot_ops`; SELECT + UPDATE).

## Platform TODO (unblocked, stage next)
- Port D3 RLS block into `03-copilot-rls.sql`; add `copilot_ops` role to `copilot-bootstrap-job.yaml` (D2).
- Add the two partial indexes to `02-copilot-schema.sql` (D5).
