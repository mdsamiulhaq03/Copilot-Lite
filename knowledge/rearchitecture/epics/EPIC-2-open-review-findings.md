# EPIC-2 loop subsystem: open review findings

Two adversarial review rounds ran over the S6/S7/S8 closed-loop code on 2026-07-30 (27 agents, then
56). Everything they CONFIRMED is fixed - see the epic's Execution status and bdt_engine commits
`ba3b72f`, `38f8932`, `873b3ef`. This file records what is still OPEN, because the workflow outputs
live in a session scratchpad that does not survive.

Nothing below is in the class the fixes closed - *a change stays live on the network while the audit
trail records the healthy outcome*. That class is closed for everything two independent skeptics
could reproduce. These are the residue: one skeptic disagreed, or verification was capped before
reaching them.

**How to work these:** re-verify against current code first. Several were written against code that
has since changed twice, and round 2 dismissed 6 of round 1's 20 leftovers for exactly that reason.

---

## A. Findings on the FIX code that one skeptic did not refute (round 2, PLAUSIBLE)

Each was attacked by two skeptics; one said it holds, one did not. Ranked as reported.

### [CRITICAL] 'dispatching' is a terminal wedge: a rollback claimed but not produced is unrecoverable, and the breach it was meant to revert is then recorded as healthy

> **RESOLVED — code-verified 2026-08-08 at bdt_engine `d3b7fe4` (fix landed in `38f8932`).**
> `claim_rollback_retry` (action_store.py:676-690) now claims `status='dispatching' AND
> updated_at < now() - 300s` (STALE_CLAIM_SECONDS, :57) with a `dispatched_at IS NULL`
> no-double-publish guard; `emit_rollbacks` re-invokes it on every re-triggered breach, and the
> breached action leaves `watching` only after a successful re-dispatch — the wedge can no
> longer complete healthy. The feedback-drop leg is fixed too: `_APPLY_ACCEPTS_FROM`
> (feedback_watcher.py:77) plus the SQL guards in `mark_watching`/`mark_failed` accept
> `dispatching`. Dedicated tests: test_feedback_watcher.py:1283-1330 (stale takeover,
> live-claim exclusivity, no re-dispatch of an on-the-wire rollback) — 7 passed against live
> Postgres. The softer sibling finding (no clock-driven sweep for dispatching/approved/proposed)
> remains open below.

`submodule/maveric_platform_bdt_engine/app/services/loop/action_store.py` line 524

**Claim.** `claim_rollback_retry` is the only writer of the new status `dispatching`, and the only reader that can move a row OUT of it is `mark_failed` — which is called in the same in-process `try`-free code path that just did the claim (`emit_rollbacks` -> `_dispatch_rollback` -> `dispatch_action`). Nothing else covers it: `claim_rollback_retry` excludes it by design (`status IN ('proposed','failed')`, line 527), `expire_undelivered_actions` matches only `status = 'dispatched'` (line 412), `complete_expired_windows` only `'watching'` (line 395), `claim_pending` only `'pending_approval'` (line 494), no endpoint in `ndt_loop.py` writes status, and `_handle_apply` drops apply feedback for it because of the `row["status"] not in ('dispatched','applied')` guard (feedback_watcher.py:267). So any loss of the claiming process between the claim and `dispatch_action` returning — SIGKILL/deploy/rebalance, an exception from `mark_dispatched`/`mark_failed`, or `send_message` raising out of its own except block via `log_error_to_mongodb` — parks the rollback in `dispatching` forever. Every later breach then hits `claimed is None` and `continue`s, the breached action stays `watching`, and `complete_expired_windows` promotes it to `completed`. That is verbatim the CRITICAL #1 failure shape the fix was written to remove ('a change stays live on the network while the audit trail records the healthy outcome'); the fix narrowed the window but made the resulting state permanent instead of retryable.

**Scenario.** Cell c1 is `watching` under a live tilt change. A KPI window breaches; `emit_rollbacks` claims the deterministic rollback row (status -> `dispatching`) and the bdt-worker pod is then killed (deploy, OOM, or `mark_dispatched` hitting a DB blip) before the Kafka produce. The feedback offset was never committed, so the same breach is redelivered; `insert_actions` conflicts, `claim_rollback_retry` returns None because `dispatching` is not claimable, `emit_rollbacks` reverts nothing, and 14 minutes later the sweep writes the breached action to `completed`. The unsafe tilt stays on the radio and `GET /ndt/loop/actions/{id}` shows a healthily-closed watch window. No operator API, no sweep and no executor feedback can ever revert it.

- Skeptic 1 (refuted, high confidence): MECHANISM IS REAL BUT THE FINDING'S FRAMING AND REACHABILITY ARE WRONG.

What the code actually says (verified):
- action_store.py:519-531 `claim_rollback_retry` commits `status = 'dispatching'` in its own `tenant_transaction`, and its own WHERE is `AND status IN ('proposed', 'failed')` — so 'dispatching' is not re-claimable. complete_expired_windows (`status = 'watching'`, :390), expire_undelivered_actions (`status = 'dispatched'`, :412) and claim_pending (`status = 'pending_approval'`, :494) do not touch it. So yes, a process that dies strictly between the claim COMMIT and the next write lea
- Skeptic 2 (HOLDS, high confidence): The finding reproduces. `dispatching` has exactly one writer and one exit, and the exit is only reachable in the same in-process call that created it.

Writer — `action_store.py:520-533` (`claim_rollback_retry`):
```
UPDATE loop_actions SET status = 'dispatching', error = NULL
 WHERE tenant_id = :tid AND action_id = :aid
   AND kind = 'rollback'
   AND status IN ('proposed', 'failed')
```
`dispatching` is deliberately excluded from the claimable set, so a later breach can never reclaim it.

I grepped the whole repo for `dispatching`; the only other production occurrence is `mark_failed`'s guar

### [CRITICAL] Day scope: a recommendation on a tick the dataset has no rows for is never scored, yet dispatched as gate-passed

`submodule/maveric_platform_bdt_engine/app/services/loop/decision_hub.py` line 109

**Claim.** unscored_recommendations() checks duplicate ticks and tick-scope alignment, but not the only thing that decides whether a DAY-scope config is applied: whether the tick exists in the day's dataset. ndt_evaluator.ticks_for_scope() returns to_eval = [t for t in range(24) if t in available], i.e. ONLY ticks the loaded frame has rows for. For every evaluated tick, _tick_config_items(req, t) finds no matching entry and returns [], so the twin scores the untouched baseline - exactly the failure mode fix 3 was written to close, reached through the dataset rather than through refs.scope. The twin's own result even names the gap in result['warnings'] ('Dataset day=0 missing ticks: [...]'), and the gate reads only guardrail_kpis.

**Scenario.** Dataset for day 0 carries ticks 0-7 (a partial/truncated ingest, common with real PM/UE feeds). A day-scope proposal recommends tick 12: cell c1 to 22 deg downtilt with on_off=false. The twin evaluates ticks 0-7 against the untouched baseline, returns healthy KPIs, the gate passes, and the tick-12 action is published on maveric.loop.action.v1 carrying evaluation.verdict='pass' with reasons []. Executed end-to-end against a scratch DB (repro3.py): 'twin applied config for: []', 'FINDING 1 status: dispatched | verdict: pass | reasons: []', payload {'cell_el_deg': 22.0, 'on_off': False, 'rollback_of': None} target {'cell_id': 'c1', 'tick': 12}. The suite passes 144/144 - no test covers this.

- Skeptic 1 (refuted, high confidence): The finding's mechanics are real but its harm claim is not: skipping a tick the dataset has no rows for does not change the gate's inputs at all, so no false approval evidence is manufactured — which is precisely what distinguishes it from the case fix 3 closed.

1) The gate reads only pooled guardrails. ndt_evaluator.py:184 — "# Pooled, not averaged." / `guardrail_kpis = compute_guardrail_kpis(pooled_rsrp, pooled_sinr, merged_thresholds)`, where pooled_* is `pooled_sinr.extend(float(v) for v in ev.sinr)` over the evaluated ticks (ndt_evaluator.py:163-165). A tick absent from the dataset has z
- Skeptic 2 (HOLDS, high confidence): REPRODUCED end-to-end on a throwaway scratch DB (never `maveric`); the scratch DB was created from `artifacts/migration/014_ndt_loop.sql` via tests/scratch_db.py and dropped afterwards. Only the S3 loaders and the twin attacher were stubbed; run_evaluation, evaluate_gate, handle_proposal, action_store and the Kafka envelope are the real code.

Inputs: policy mode=auto with default guardrails; proposal refs.scope={"type":"day","day":0}; per_tick_recommendations=[{tick:12, items:[{cell_id:"c1", el_degree:22.0, on_off:false}]}]; day-0 UE dataset carrying only ticks 0..7 (truncated ingest).

Outpu

### [HIGH] The retry claim treats 'proposed'/'failed' as proof nothing was produced (dispatched_at is not checked), so a rollback that already went out is dispatched a second time

> **RESOLVED — code-verified 2026-08-08:** the claim predicate now requires
> `dispatched_at IS NULL` (action_store.py:679); covered by
> test_feedback_watcher.py:1283 `test_a_rollback_already_on_the_wire_is_never_re_dispatched`.

`submodule/maveric_platform_bdt_engine/app/services/loop/action_store.py` line 527

**Claim.** `AND status IN ('proposed','failed')` is the whole guard. Neither value implies the Kafka message was not produced: (a) `mark_dispatched`'s own docstring (line 176-181) states the produced-but-not-yet-marked state is normal and recoverable, and a row in that state is `proposed`; (b) `mark_failed` is reached whenever `send_message` returns False, but its guard now includes `'dispatched'` (line 211), so a losing racer's failed produce can flip a rollback that another process successfully dispatched back to `failed` and hence back to claimable; (c) with more than one bdt-worker replica, two breaches on the same cell race between `insert_actions` (winner is mid-produce, row still `proposed`) and the loser's `claim_rollback_retry`, which happily claims `proposed`. The docstring asserts exclusivity ('two concurrent breaches would both produce a message' is what `dispatching` prevents), but the exclusivity only starts at the claim — the insert->produce window is unprotected, which is exactly the window `insert_actions`' `RETURNING` protects for change actions. Adding `AND dispatched_at IS NULL` would separate the two states the claim currently conflates.

**Scenario.** Cell c2 breaches. `emit_rollbacks` inserts the rollback row, `send_message` succeeds (the executor is now reverting the cell), and `mark_dispatched` then fails on a transient DB error. The exception propagates out of `handle_feedback`, `_handle_feedback` returns False, so the offset is not committed and the same breach is redelivered. The row is still `proposed`, `claim_rollback_retry` claims it, and a SECOND identical `maveric.loop.action.v1` rollback envelope goes to the executor for the same action_id — a duplicate write to live radio hardware, while the log line says 'Retrying a rollback whose earlier dispatch never went out'.

- Skeptic 1 (refuted, high confidence): REFUTED on three code-verified grounds.

1. THE PROPOSED REMEDY IS A NO-OP FOR THE FINDING'S OWN SCENARIO. `mark_dispatched` (action_store.py:181-189) sets status and dispatched_at in ONE statement: `"UPDATE loop_actions SET status = 'dispatched', dispatched_at = now(), expires_at = :exp, error = NULL WHERE tenant_id = :tid AND action_id = :aid"`. `insert_actions` (action_store.py:135-142) never writes dispatched_at, and no other writer sets it. So in the repro ("produce succeeded, then mark_dispatched raised on a transient DB error") the row is `proposed` with `dispatched_at IS NULL` — the fi
- Skeptic 2 (HOLDS, high confidence): CONFIRMED by executed repro on a scratch database (never `maveric`).

The guard is exactly what the finding quotes — `action_store.py:520-533`:

    UPDATE loop_actions SET status = 'dispatching', error = NULL
     WHERE tenant_id = :tid AND action_id = :aid
       AND kind = 'rollback'
       AND status IN ('proposed', 'failed')
    RETURNING ...

and its own docstring justifies including `proposed` as "a process that died between `insert_actions` and `dispatch_action` leaves the row at `proposed` with nothing having been produced." But `proposed` does not imply that. `mark_dispatched` (actio

### [HIGH] The watch-deadline clamp only fires for lag > window, so any smaller lag shortens the window to near zero

`submodule/maveric_platform_bdt_engine/app/services/loop/feedback_watcher.py` line 289

**Claim.** `deadline = max(applied_at + window, now + window) if applied_at < now - window else applied_at + window` guarantees a full window only when the lag EXCEEDS the window. For any lag L in (0, window] the else-branch is taken and the effective watch is window - L, which tends to zero. The discontinuity is absurd: 15 min 1 s of lag buys a full 15-minute watch, 14 min 59 s buys 1 second. The max() is also dead code - when the condition holds, applied_at + window < now < now + window, so max() always selects now + window; the whole expression is equivalent to `now + window if applied_at < now - window else applied_at + window`, and the intended form is simply `max(applied_at, now) + window`.

**Scenario.** Consumer lag under one window (a rebalance, a broker backlog, a bdt-worker restart, mild clock skew) is the normal case, not the extreme one. Executed with watch_window_min=1 and apply feedback 58 s late: watch_deadline = now + 2.0 s; sweep_deadlines() 3 s later -> completed; a subsequent executor guardrail_breach with sinr_avg_db=-12.0 and rrc_success_pct=3.0 emitted 0 rollbacks (_handle_window skips a non-watching action) and the row stayed 'completed'. The change stays live on the radio with an audit trail saying the window closed healthily. The same shape at the documented default: watch_window_min=15 with 14 min of lag -> deadline = now + 1.0 min (measured).

- Skeptic 1 (refuted, high confidence): The arithmetic in the finding is correct, but the behaviour it calls a defect is the contract of record, not a clamp failure.

1. The spec mandates the anchor. `artifacts/docs/cloudlynet-rearchitecture/epics/EPIC-2-ndt-consolidation.md` §E2.S7 Contract: "`applied` -> action `applied`, `applied_at=observed_at`, then `watching` with **`watch_deadline = applied_at + policy_ref.watch_window_min`**", and the acceptance criterion "moves `dispatched -> applied -> watching` with the correct deadline from the action's `policy_ref` snapshot". The window is defined as wall-clock time *on the radio after 
- Skeptic 2 (HOLDS, high confidence): The finding reproduces exactly, including the numbers it quotes.

Deciding code, /Users/laawanyakishor/Projects/NetAI/cloudlynet_ai/submodule/maveric_platform_bdt_engine/app/services/loop/feedback_watcher.py:287-289:

    now = _now()
    window = timedelta(minutes=policy.watch_window_min)
    deadline = max(applied_at + window, now + window) if applied_at < now - window else applied_at + window

The guard is `applied_at < now - window`, i.e. it fires only when lag STRICTLY EXCEEDS the window. For lag L in (0, window] the else-branch runs and the deadline is `applied_at + window = now + (windo

### [HIGH] The day-scope gate reads only day-POOLED guardrails, so one blacked-out tick is diluted below every threshold

`submodule/maveric_platform_bdt_engine/app/services/loop/decision_hub.py` line 226

**Claim.** For day scope the gate compares only the pooled sinr_p5 / outage_rate over all 24 ticks. per_tick_kpis and worst_tick_stats are computed by the same result and never consulted, so a change that is catastrophic for one hour is averaged away by 23 healthy hours. A single bad tick out of 24 is 4.17% of samples - below max_outage_rate=0.1 - and the 5th percentile of the pooled SINR sits above the 4.17% of bad samples, so even sinr_p5 stays healthy.

**Scenario.** A day-scope proposal changes cell c1 only at tick 3 and the twin predicts total outage there. Executed with 24 ticks x 20 UEs (repro7.py): day-pooled {'sinr_p5': 12.0, 'outage_rate': 0.0417, 'coverage_rate': 0.9583}; tick 3's own KPIs {'outage_rate': 1.0, 'sinr_p5': -20.0}; worst_tick_stats {'highest_outage_tick': 3, 'highest_outage_rate': 1.0, 'lowest_coverage_rate': 0.0}. Gate fails? False -> dispatched with verdict pass. A one-hour cell blackout reaches hardware while the evidence that names it is sitting unread in the same result dict.

- Skeptic 1 (refuted, high confidence): 1) NOT NEW CODE. `git log --follow -- app/services/loop/decision_hub.py` gives ba3b72f -> 9b11d9c -> 1c6eb79, and `git show ba3b72f -- app/services/loop/decision_hub.py` contains exactly two hunks: `+    SCOPE_TICK,` in the imports, and the `unscored_recommendations()` function plus its call site inside evaluate_gate. The cited block is untouched since the original S6 commit 1c6eb79:

    guardrails = result.get("guardrail_kpis") or {}
    ...
    sinr_p5 = guardrails.get("sinr_p5")
    outage_rate = guardrails.get("outage_rate")
    ...
        if float(sinr_p5) < min_sinr:   # decision_hub.p
- Skeptic 2 (HOLDS, high confidence): The finding holds against current code (bdt_engine ba3b72f) and I reproduced it end-to-end.

1. The gate reads only the pooled dict. decision_hub.py:213-229:
```
guardrails = result.get("guardrail_kpis") or {}
...
sinr_p5 = guardrails.get("sinr_p5")
outage_rate = guardrails.get("outage_rate")
...
    if float(sinr_p5) < min_sinr: ...
    if float(outage_rate) > max_outage: ...
```
`grep -rn "worst_tick\|per_tick_kpis" app/services/loop/ app/api/v1/endpoints/ndt_loop.py app/models/ndt_loop_models.py` returns nothing — neither key is read anywhere in the loop package, and `GateVerdict.guardrail_

## B. Findings on the FIX code that verification never reached (round 2, capped at the top 8)

- **[high]** Canonical-PM watch window can never contain a canonical PM row, so the one guardrail the A1 path can enforce is still never enforced — silently — `/Users/laawanyakishor/Projects/NetAI/cloudlynet_ai/submodule/maveric_platform_bdt_engine/app/services/loop/feedback_watcher.py`
- **[high]** The added vendor-spelling fallback cannot match the names an unmapped dictionary actually produces (`nybsys:` prefix), so the fixed defect still reproduces in full — `/Users/laawanyakishor/Projects/NetAI/cloudlynet_ai/submodule/maveric_platform_bdt_engine/app/services/loop/feedback_watcher.py`
- **[medium]** 'dispatching' was added to the code but to no contract surface: the DDL CHECK, API status enum and status machine all still enumerate 13 values without it — `artifacts/design/schemas.sql`
- **[medium]** The claimed-row merge gives the stale stored row authority over the freshly planned rollback, so the retried rollback's audit record names the wrong breach — `submodule/maveric_platform_bdt_engine/app/services/loop/feedback_watcher.py`
- **[medium]** The maintenance policy is FOR ALL with a matching WITH CHECK, so a maintenance session can insert rows for any tenant, reassign a row's tenant_id, and delete every tenant's audit trail — and it was applied to loop_feedback, which no clock-driven statement touches — `artifacts/migration/014_ndt_loop.sql`
- **[medium]** No upper clamp: an executor clock ahead of the NDT parks an action in `watching` for as long as the skew — `submodule/maveric_platform_bdt_engine/app/services/loop/feedback_watcher.py`
- **[medium]** An apply/applied ack for a rollback row is now recorded nowhere, the caller logs "Action applied; watching" anyway, and the sweep later files the delivered revert as `expired` — `/Users/laawanyakishor/Projects/NetAI/cloudlynet_ai/submodule/maveric_platform_bdt_engine/app/services/loop/feedback_watcher.py`
- **[medium]** The new `dispatching` status is the one state with no recovery path, so a crash between the claim and the produce makes a breach permanently un-revertible again — `/Users/laawanyakishor/Projects/NetAI/cloudlynet_ai/submodule/maveric_platform_bdt_engine/app/services/loop/action_store.py`
- **[medium]** All four status mutators discard their rowcount and no caller checks, so a dispatched revert can coexist with an action row that says `completed` and a log line that says "reverted" — `/Users/laawanyakishor/Projects/NetAI/cloudlynet_ai/submodule/maveric_platform_bdt_engine/app/services/loop/action_store.py`
- **[medium]** Overlapping att/succ metric lists make `aggregate_pm_window` report 0% success and roll back every healthy watching action on the target — `/Users/laawanyakishor/Projects/NetAI/cloudlynet_ai/submodule/maveric_platform_bdt_engine/app/services/loop/feedback_watcher.py`
- **[low]** The claim erases the previous failure reason and logs 'never went out' without verifying it, leaving no trail for the one path that touches hardware twice — `submodule/maveric_platform_bdt_engine/app/services/loop/feedback_watcher.py`
- **[low]** Now that the sweep is tenant-less, neither loop_actions index can serve it: every watch tick does full sequential scans of an append-only table, and the migration comment claiming otherwise is wrong — `artifacts/migration/014_ndt_loop.sql`
- **[low]** watch_canonical_pm fans out across every tenant with no bound and issues one unfiltered PM fetch per watching action per tick, on the Kafka consumer thread — `submodule/maveric_platform_bdt_engine/app/services/loop/feedback_watcher.py`
- **[low]** S8 approve re-dispatches without the scope check, and 014 has no backfill for rows gated before the fix — `submodule/maveric_platform_bdt_engine/app/api/v1/endpoints/ndt_loop.py`

## C. Round-1 findings verification never reached, that round 2 also did not clear

Round 2 rechecked all 20 of round 1's capped-out findings. 14 were confirmed by both skeptics and
are FIXED. The 6 below were dismissed, and are recorded so nobody re-files them:

- **never_a_defect** — `test_a_policy_is_invisible_to_another_tenant` proves the WHERE clause, not RLS — the exact bug class the epic already recorded twice
  - why: The finding's descriptive claims about the module are TRUE, but its failure scenario ("loop_policies then has no database-level isolation and the suite is green") is refuted by a test in a sibling module plus by Postgres deny-all semantics.

What is true:
- tests/test_loop_policy_api.py:22 imports only `migration_section, scratch_engine, statements` — it never imports `rls_probe_engine`, and it is
- **fixed_by_the_new_code** — A rollback whose Kafka produce fails can never be re-emitted, and the unreverted action is then marked 'completed'
  - why: The finding is exactly what fix #1 was written for, and the deciding code is no longer what the finding quotes.

The finding's mechanism was "`inserted` is empty, the `continue` skips the dispatch". That bare `continue` is gone. `feedback_watcher.py:399-416` now reads:

```
399  for row in rows:
400      if row["action_id"] not in inserted:
406          claimed = action_store.claim_rollback_retry(
- **unreachable_in_practice** — One `null` KPI value makes the whole feedback message an invalid dialect, so a breach is committed and dropped
  - why: The MECHANISM the finding describes is real; the PATH to it is not.

Mechanism confirmed. `feedback_watcher.py:135` is exactly as quoted — `kpis: dict[str, float] | None = None` — and pydantic's lax mode does not coerce `None` to `float`. Probe against the real model (PYTHONPATH=. uv run python, bdt_engine venv):
  null sinr    -> FAIL ValidationError  kpis.sinr_avg_db "Input should be a valid num
- **fixed_by_the_new_code** — A stale observed_at opens an already-closed watch window, and the sweep silently completes a change nothing ever checked
  - why: Finding [15] describes the pre-fix code verbatim, but that code no longer exists. It is fix #6 of commit ba3b72f.

CURRENT code, `feedback_watcher.py:276-302`:
```
276  policy = _policy_from(row)
277  applied_at = feedback.observed_at or _now()
...
287  now = _now()
288  window = timedelta(minutes=policy.watch_window_min)
289  deadline = max(applied_at + window, now + window) if applied_at < now -
- **never_a_defect** — The approval audit trail's actor is caller-asserted: `X-User-Id` is only shape-checked, never tied to the path tenant
  - why: The code reading in the finding is literally accurate but the behaviour is the documented, spec'd contract for this epic, and the scenario grants no capability the caller does not already have.

1) The quoted code does say what the finding says. `ndt_loop.py:202-205`: `if raw is None or raw == "": return None, None` / `return str(uuid.UUID(raw)), None` — shape check only, no lookup. `ndt_loop.py:2

## D. Structural gaps from the completeness critiques

Round 1's critique is superseded. Round 2's flagged two, both now closed:

- multi-replica watch tick with no lock — CLOSED by `advisory_tick_lock` (bdt_engine `873b3ef`)
- migration 014 reaching no existing database — CLOSED by the gateway boot-time net
  (`a3c444c`) plus the compose mount and README instructions (`7b1844f`)

The remainder of round 2's critique is reproduced verbatim below, because it names specific
functions and acceptance criteria that nothing verifies and is worth reading before EPIC-3/4/5
touch this subsystem.

```
Two rounds have covered the message-level state machine very thoroughly. What neither round opened is the **operational envelope**: the clock, the deployment topology, the DDL delivery path, and the executor-facing end of the rollback. Prioritised:

---

**1. Production runs 2–10 bdt-worker replicas, and the clock tick has no lock at all.**
`submodule/maveric-deployment/argocd/maveric_platform_bdt_worker/values.yaml:6` is `replicaCount: 2`, with `autoscaling: {enabled: true, minReplicas: 2, maxReplicas: 10, targetCPUUtilizationPercentage: 80}` (lines 139-144). `grep -rn "advisory\|leader" app/` in bdt_engine returns nothing. `LoopConsumer._run_watch_tick` (`loop_consumer.py:73-95`) is called from `run_forever` **outside** the records loop (line 114), so every replica runs it regardless of partition assignment — and the loop topics are single-partition on purpose (`scripts/kafka/init-topics.sh:54-56`), so extra replicas add no consumption, only extra ticks. Two consequences nobody has examined: (a) N replicas run `watch_canonical_pm` on the identical `watching`/`a1_policy` row set, all reach the same breach, and all call `emit_rollbacks`; `insert_actions` gives the row to one, and the losers then call `claim_rollback_retry`, which claims `status='proposed'` — precisely the state the winner's row sits in between `insert_actions`' commit and `dispatch_action`'s produce (two separate transactions, `decision_hub.py:385-397`). That is a duplicate revert command onto live hardware, produced by the fix's own recovery path, in the default production topology. (b) The tick's cost is CPU (a day-scope gate is 24 GP passes in the same thread), so the HPA scales on the tick's own load and multiplies it. Round 2's pending finding about `dispatched_at` not being checked is the single-process version of (a); the multi-replica version is untested and the topology is not documented anywhere as a constraint.

**2. The DDL half of fix #2 reaches no database that already exists.**
`docker-compose.yaml:37-54` mounts `artifacts/design/schemas.sql` and migrations 001–010 into `docker-entrypoint-initdb.d`, which Postgres runs **only on first cluster init**; `014_ndt_loop.sql` is mounted nowhere and `compose.sh` has no migrate verb. The only thing that re-applies loop-table policies on an existing database is the gateway's boot-time safety net (`submodule/maveric_platform_gateway/internal/db/migrate.go:330-345`), and that block creates `%s_rls` only — it never creates `loop_actions_maintenance_rls`. So on any dev or lab stack whose volume predates `ba3b72f` (including the one running the E2.S9 soak), `maintenance_transaction()` sets a GUC that no policy reads, and the sweep fails exactly as it did before the fix. `artifacts/migration/README.md:175-235` still documents only the S1 and S5 sections of 014 — no mention of the S6/S7/S8 additions, `updated_by`, or the maintenance policy — so an operator has no instruction to apply it either. Adding the two `_maintenance_rls` policies to migrate.go's post-statement list, or a `compose.sh migrate`, is the missing piece; the code-side fix is correct and inert without it.

**3. "Never rolls back after the deadline" is false for the whole interval between deadline and sweep. Reproduced.**
E2.S7 acceptance criterion, verbatim: *"Healthy window (`ok` feedbacks, deadline passes) -> `completed`; never rolls back after the deadline."* `_handle_window` (`feedback_watcher.py:310-318`) guards on `row["status"] != STATUS_WATCHING` and never compares `watch_deadline` to now; `watching_actions_for_target` (`action_store.py:321-350`) has no deadline predicate either. I seeded a `watching` row whose deadline passed 25 minutes ago and delivered a breaching `kpi_window`: status went to `rolled_back` and a revert was produced. The existing test `test_a_closed_window_never_rolls_back_afterwards` (`tests/test_feedback_watcher.py:621`) calls `sweep_deadlines()` *first*, so it only proves the post-sweep case. The gap is not narrow: the sweep is throttled to `LOOP_WATCH_TICK_SECONDS` and shares its thread with proposal handling, whose budget is `max_poll_interval_ms` = 30 minutes for a day-scope gate. Worse, the LIFO set is unfiltered, so one live breach reverts every stale-deadline `watching` action on the cell — changes whose windows closed healthily.

**4. A successfully applied rollback is recorded as `expired`. Reproduced.**
Fix #5 correctly stopped `mark_watching` from touching `kind='rollback'`, but nothing gives an applied rollback any terminal success state: `handle_feedback` treats `kind="rollback"` as audit-only (`feedback_watcher.py:243-244`), and an `kind="apply"/"applied"` ack now hits the `kind <> 'rollback'` guard and no-ops, so `applied_at` stays NULL forever. `expire_undelivered_actions` then matches (`status='dispatched' AND expires_at < now() AND applied_at IS NULL`) and writes `expired` — the status whose documented meaning is "an action nobody acted on" (`action_store.py:401-406`). I fed a dispatched rollback both ack shapes and swept: final state `('expired', None)`. So the single most safety-relevant record in the system — did the revert reach the network — reads as "never delivered", and that is what E5.S3's lineage API will publish. Pre-fix this row would have gone `watching -> completed`; the fix closed a real hazard and left no success terminal behind it.

**5. No sweep covers `approved`, `dispatching`, or `proposed`. Reproduced.**
Both sweeps key on `watching` and `dispatched` only. Answering the cross-story question directly: an S8 action that `claim_pending` moved to `approved` (`ndt_loop.py:296-321`) and whose process died before the produce returned is stuck at `approved` forever — no sweep ages it, and `claim_pending` requires `pending_approval` so it can never be re-approved or rejected. Same for the new `dispatching` (the round-2 wedge finding, but note the sweeps are the recovery mechanism that is missing, not just a retry). Same for `proposed` on the auto path: `claim_rollback_retry`'s docstring advertises `proposed` recovery for "a process that died between `insert_actions` and `dispatch_action`", but it is gated `AND kind = 'rollback'`, so a change action has no such path — and because the dispatch loop at `decision_hub.py:394-397` is outside `insert_actions`' transaction, a crash mid-loop leaves a multi-cell proposal *half-applied on the network* with the remaining rows at `proposed` forever, while `existing_action_ids` makes every Kafka redelivery a silent no-op. That is exactly the outcome `insert_actions`' docstring says it prevents ("a partial set would leave some cells changed and others not with no record of why") — the guarantee stops at the row insert.

**6. Every clock-driven query is a sequential scan, and the one index added for the sweep cannot serve it.** Measured with `EXPLAIN (ANALYZE, BUFFERS)` on a scratch DB built from 014 with 400k `loop_actions` rows: `complete_expired_windows` → `Seq Scan`, 400 000 rows scanned, 332 ms; `expire_undelivered_actions` → `Seq Scan`, 400 000 rows, no index on `expires_at` exists at all; `watching_actions_by_adapter` → parallel `Seq Scan` + `Sort`. Reason: `idx_loop_actions_watch` is `(tenant_id, watch_deadline)` and all three statements are cross-tenant with no `tenant_id` predicate, so its leading column is unusable — the comment at `014_ndt_loop.sql:229` ("without this it table-scans") describes an index that cannot be used by the query it was added for. This runs every 60 s per replica, on tables with no retention job (`artifacts/migration/README.md` records "none of these tables has a retention job" for the NDT tables; `loop_feedback` is append-only and never deduplicated by design). `list_actions` filtered by `proposal_id` is also unindexed and uses OFFSET pagination. Partial indexes on `(status, watch_deadline) WHERE status='watching'` / `(status, expires_at) WHERE status='dispatched'` / `(adapter, status)` are the fix.

**7. `watch_canonical_pm` sends neither a cell filter nor `to_ts`, so each watching A1 action refetches the tenant's entire PM history every tick.** `PMQuery` supports `dn_prefix` and `to_ts` (`app/feature_builder/pm_source.py:49-63`) and the spec says *"filtered by the action's `target.cell_id` (dn match) and `from_ts = applied_at`"* — the code passes `from_ts` alone (`feedback_watcher.py:506-510`) and filters the cell in Python afterwards (`aggregate_pm_window`). `fetch_pm_items` paginates on `has_more` with `PAGE_LIMIT = 10_000` and `_MAX_PAGES = 1_000`, i.e. up to 10 M rows, 120 s per page, for four metric names, once per watching A1 action, once per tick, on the thread that also consumes feedback. Two correctness effects follow from the same omission: no `to_ts` means the aggregate keeps absorbing data collected *after* `watch_deadline` (feeding item 3), and the window is cumulative from `applied_at`, so an early transient dip depresses the ratio for the rest of the window. The tests mock the transport and assert only that `from_ts` is present (`test_the_a1_watch_scopes_the_query_from_applied_at`), so nothing observes the missing scope.

**8. `_policy_from`'s fallback is never exercised, and its stated conservatism is wrong for one of the three fields it fills.** Every test in `test_feedback_watcher.py` seeds `POLICY_REF` with `watch_window_min: 15`; no test seeds a NULL or malformed `policy_ref`. The docstring (`feedback_watcher.py:186-188`) claims "Defaults are the conservative direction here: they are the tightest thresholds in the system." True for `guardrails`; false for `watch_window_min`, where the hardcoded `15` is the *shortest* window the model permits (`1..1440`). A tenant running a 24-hour watch whose row lost its snapshot gets a 15-minute one, and the sweep then completes it as healthy — the same failure shape as the clamp bug fix #6 addressed, in the path that decides the clamp's window.

**9. The policy that decides whether the loop may touch the network records no operator and no history.** `put_loop_policy` (`ndt_loop.py:61-86`) accepts no `X-User-Id` and calls `upsert_policy` without `updated_by`, so the `ON CONFLICT DO UPDATE ... updated_by = EXCLUDED.updated_by` (`policy_store.py:86-91`) writes NULL — and *erases* any previously recorded value. There is no history table, so `mode: off -> auto` is an in-place overwrite. Approving one action attributes an operator (S8 went to real trouble for it); turning the whole loop to `auto` for a tenant attributes nobody. S6's acceptance list does not require it, which is why no lens caught it, but it is the higher-privilege operation.

**10. Smaller, but genuinely unexamined:** the `[breached, *watching]` prepend branch (`feedback_watcher.py:363-366`), which exists for "a concurrent sweep just moved it", is dead code in the suite — no test delivers a breach for a row absent from the watching set, and on that path `mark_rolled_back`'s `WHERE status = 'watching'` silently no-ops, so a revert goes out while the row stays `completed`. The retry merge at line 415 overwrites the retry's fresh `evaluation` with the first breach's, so the audit attributes the revert to the older breach. And on the E3/E4 seam: the frozen action envelope has no `kind` field, so an executor can only distinguish a revert by `payload.rollback_of`, while a rollback's payload carries *no* target values at all — and it still carries the breached action's `policy_ref.watch_window_min`, which `action_message`'s own docstring says E4's adapters read, i.e. we hand an executor the window for an action we insist is never watched. Nothing in this repo can test any of that; it should be an explicit assertion in E4's contract rather than an assumption.

---

**Genuinely well covered, for the record:** the four gate branches, redelivery/idempotency, deterministic ids, the frozen envelopes, per-tenant RLS isolation on the request path, the LIFO ordering and its tie-breaks, the 404/409 approval semantics including route shadowing, `check_breach`'s
```
