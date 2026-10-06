# Closed-loop guardrails: HLD + LLD

Status: design, 2026-08-04. Supersedes the guardrail semantics assumed by frozen HLD §4.2, E2.S6
(`evaluate_gate`), E2.S7 (`check_breach`) and E5.S6 (the `015` policy seed).
Author's note: written after a live run exposed the defect below; the evidence is measured, not
reasoned.

---

## 1. The problem

CloudlyNet's closed loop asks one question in two places:

| Place | Code | Question it should ask |
| --- | --- | --- |
| Gate, before actuation | `decision_hub.evaluate_gate` | Is this **change** safe to apply? |
| Watch, after actuation | `feedback_watcher.check_breach` | Has this **change** made things worse? |

Both are implemented as **absolute threshold comparisons**:

```python
# gate  (decision_hub.py)
if float(sinr_p5) < min_sinr:        reasons.append(...)
# watch (feedback_watcher.py)
if float(observed) < float(limits["min_sinr_db"]):  reasons.append(...)
```

Neither expression contains a baseline term. That is the defect: an absolute floor answers *"is
this network good?"*, not *"did this change make it worse?"* — and those come apart in both
directions, silently.

### 1.1 Failure mode A: the loop is dead on arrival

If the undisturbed network already sits below the floor, **every** proposal is rejected regardless
of its effect, and the audit trail reads like a working safety gate.

Measured on the lab dataset (`lab-bdt-1` / `lab-baseline-1` / `lab-dataset-1`), from
`ndt_kpi_snapshots`:

```
baseline            sinr_p5 = -3.0954   outage_rate = 0.0   coverage_rate = 1.0
proposed (cell off) sinr_p5 = -3.1225   outage_rate = 0.0   coverage_rate = 1.0
seeded floor        min_sinr_db = 0.0
```

The change's measured effect is **-0.027 dB**. It was rejected because the *baseline* is 3.1 dB
below a floor the change had nothing to do with. Every proposal ever sent to this tenant would be
rejected identically, and `rejected_by_gate` with a plausible reason string is indistinguishable
from correct operation. This is why the loop has never been observed to dispatch: not a fixture
problem, a guardrail-shape problem.

### 1.2 Failure mode B: the loop approves real harm

The mirror image, and the dangerous one. If baseline `sinr_p5` is +12 dB and the floor is 0 dB, a
change that destroys **11 dB** of SINR passes the gate cleanly. Nothing in the gate can see the
regression, because nothing in the gate looks at where it started.

Failure mode A is embarrassing. Failure mode B ships a network outage with a `verdict: pass` audit
record. Both come from the same missing term.

### 1.3 Defect 2: one threshold, two incompatible statistics

`policy.guardrails.min_sinr_db` is a single number compared against two different quantities:

| Layer | Quantity | What it is |
| --- | --- | --- |
| Gate | `sinr_p5` | 5th percentile of the **predicted** per-UE SINR distribution, from the twin |
| Watch | `sinr_avg_db` | arithmetic **mean**, **observed**, from the device's PM counter (`Parameter.412`) |

A percentile and a mean of the same distribution are not interchangeable. On the lab data:

```
sinr_p5 = -3.10    sinr_p50 = -0.88    sinr_p95 = +4.72     (mean ≈ 0)
```

A floor tuned so the watch is meaningful (≈0, around the mean) rejects every proposal at the gate
(p5 ≈ -3.1). A floor tuned so the gate is usable (-4) leaves the watch ~3 dB under-protected. **No
single value is correct for both**, so the current schema cannot be configured correctly — only
mis-configured in one direction or the other.

E5.S6's seed comment states the defaults "mirror smo_sim's device-level GUARD constants so both
defense layers agree". They share a *number*, applied to different *statistics*. They do not agree;
they only look as though they do.

### 1.4 Defect 3: default drift

`DEFAULT_GUARDRAILS.max_outage_rate = 0.1` (`ndt_loop_models.py`) versus `0.05` in the `015` seed.
A tenant seeded by the migration is held to twice the strictness of one relying on defaults. Minor
next to 1.1–1.3, but it is the same class of error: a threshold whose meaning depends on which code
path constructed it.

---

## 2. Decision

**Guardrails become two-part: an absolute SAFETY FLOOR and a relative REGRESSION BUDGET, evaluated
per named KPI, against an explicitly recorded baseline.**

```
a change is SAFE  ⇔  absolute limits hold  AND  regression vs baseline is within budget
```

Rationale for keeping both rather than replacing one with the other:

- **Absolute alone** is what we have. Defects 1.1 and 1.2 follow directly.
- **Relative alone** permits unbounded drift: twenty changes each degrading 0.4 dB are individually
  within budget and collectively an 8 dB collapse. The absolute floor is what stops the ratchet.
- Together, each covers the other's blind spot, and each answers a question an operator actually
  asks: *"how bad are we ever allowed to get"* and *"how much may any one change cost us"*.

### 2.1 Per-KPI statistics, named explicitly

A guardrail names the KPI it governs. `min_sinr_db` disappears as a single cross-layer number and
becomes two entries with distinct keys, so the gate and the watch can never again be silently
compared on incompatible statistics:

| Key | Layer | Compared against |
| --- | --- | --- |
| `sinr_p5_floor_db` | gate | twin `sinr_p5` |
| `sinr_p5_max_drop_db` | gate | baseline `sinr_p5` − proposed `sinr_p5` |
| `sinr_avg_floor_db` | watch | device `sinr_avg_db` |
| `sinr_avg_max_drop_db` | watch | pre-change `sinr_avg_db` − observed |
| `outage_rate_ceiling` | both | `outage_rate` |
| `outage_rate_max_rise` | both | observed − baseline |
| `rrc_success_floor_pct` | watch | `rrc_success_pct` |

### 2.2 Backward compatibility is mandatory, not optional

`policy_ref` is a **snapshot frozen on every historical action row**. Actions decided months ago
carry the old key names, and `feedback_watcher._policy_from` rebuilds a policy from that snapshot to
judge a rollback today. A rename that cannot read old snapshots would silently change the verdict on
in-flight actions — the exact class of bug this document exists to remove.

So: old keys are **accepted forever** and mapped on read. `LoopPolicy` already tolerates unknown keys
by design (its docstring says so, for this reason). Only `LoopPolicyIn` (the PUT body) validates
strictly.

### 2.3 Rejected alternatives

| Option | Why not |
| --- | --- |
| Retune `min_sinr_db` per tenant | What I did as a hot fix, and it is wrong: it makes one dataset pass while leaving both failure modes intact for every other. Treating a shape defect as a tuning problem is how it stays hidden. |
| Compare gate against `p5` and watch against `p5` | The device PM counter reports a mean; there is no per-UE distribution at the device. Cannot be done without a new device-side counter. |
| Drop the absolute floor, keep only deltas | Permits the ratchet in 2. |
| Percentage-based deltas (`max_drop_pct`) | SINR is logarithmic and signed; "20% worse" is meaningless when the value crosses zero. dB deltas are the natural unit. |

---

## 3. LLD

### 3.1 Data model

No DDL. `loop_policies.guardrails` is already `jsonb`, and `policy_ref` snapshots are already
`jsonb`. This is a change to the *document* inside those columns, so no migration number is
consumed beyond `015`'s reseed.

```jsonc
{
  "sinr_p5_floor_db":      -6.0,   // hard floor, twin p5
  "sinr_p5_max_drop_db":    1.0,   // a change may cost at most 1 dB of p5
  "sinr_avg_floor_db":     -3.0,   // hard floor, device mean
  "sinr_avg_max_drop_db":   3.0,
  "outage_rate_ceiling":    0.05,
  "outage_rate_max_rise":   0.02,
  "rrc_success_floor_pct": 95.0
}
```

### 3.2 Legacy key mapping (read path)

| Legacy key | Maps to | Note |
| --- | --- | --- |
| `min_sinr_db` | `sinr_p5_floor_db` **and** `sinr_avg_floor_db` | Preserves today's behaviour exactly for old snapshots: both layers keep using the one number. |
| `max_outage_rate` | `outage_rate_ceiling` | |
| `min_rrc_success_pct` | `rrc_success_floor_pct` | |

Absent delta budgets mean **delta checking is off** for that KPI. That is the conservative default
for a legacy snapshot: it cannot invent a budget the operator never set, and it must not start
rejecting actions that would have passed under the policy they were actually decided against.

### 3.3 The baseline term

The gate already computes a baseline evaluation — `ndt_kpi_snapshots` holds rows keyed
`(tenant_id, run_id, source)`. The gate must evaluate the **unmodified** config as well as the
proposed one to have a comparison. Two options:

- **(a) Evaluate baseline in the gate.** Correct and self-contained; costs a second twin pass.
- **(b) Reuse the most recent `source='evaluate'` snapshot for the same refs.** Cheap, but compares
  against a run whose inputs may have moved — precisely the staleness `policy_ref` snapshotting
  exists to prevent.

**Decision: (a).** Correctness over cost. Tick-scope evaluation is a single GP pass; the demo path
is tick scope. Day scope (24 passes) doubles to 48, which is why the baseline pass is **cached** by
the existing `run_id`/`db_key` mechanism: the unmodified config is identical across every proposal
for the same refs, so the second and later proposals hit cache.

The baseline verdict is recorded in `GateVerdict.baseline_kpis`, so `evaluation` on the action row
carries both sides and the lineage API shows them without a second query.

### 3.4 Contract changes

```python
# ndt_loop_models.py
class GateVerdict(BaseModel):
    run_id: str | None
    verdict: Literal["pass", "fail"]
    reasons: list[str]
    guardrail_kpis: dict[str, Any] | None      # proposed
    baseline_kpis: dict[str, Any] | None = None   # NEW, additive
    baseline_run_id: str | None = None            # NEW, additive
```

Additive only. `extra="forbid"` on `GateVerdict` must be relaxed to allow reading historical rows
that lack the new keys — they are already absent-tolerant via defaults, so no relaxation needed.

### 3.5 Evaluation function

One shared function, used by both layers, so gate and watch can never drift again:

```python
def evaluate_guardrails(
    *, observed: Mapping[str, float], baseline: Mapping[str, float] | None,
    guardrails: Mapping[str, float], layer: Literal["gate", "watch"],
) -> list[str]:
    """Reasons a change is unsafe; empty means safe.

    `layer` selects the KPI keys, because the gate reads a predicted p5 and the watch reads an
    observed mean. Missing observed KPI => not checked (the existing 'no news is not bad news'
    rule). Missing baseline => delta checks skipped, absolute checks still run.
    """
```

### 3.6 Rollout

1. Land `evaluate_guardrails` + the legacy mapping, with both layers calling it. Behaviour for an
   unmigrated policy is **bit-identical** to today (legacy keys map to floors, no deltas set).
2. Re-seed defaults (`015` reseed, or a `016`) with the new keys for tenants still on legacy values.
3. Frontend: the approvals card already renders `evaluation.reasons`; delta reasons carry both
   numbers so no UI change is required for correctness, only for polish.

### 3.7 Test plan

| Test | Asserts |
| --- | --- |
| legacy policy, no deltas | verdict identical to pre-change for the same inputs (regression lock) |
| baseline below floor, change neutral | **passes** — the 1.1 bug, inverted |
| baseline healthy, change drops 11 dB, lands above floor | **fails** — the 1.2 bug |
| delta budget absent | delta not enforced, absolute still enforced |
| observed KPI missing | not a breach (existing rule preserved) |
| gate and watch on the same policy | use different keys, no cross-contamination |
| `policy_ref` snapshot from a legacy action | still rebuildable and judgeable today |

### 3.8 Precondition: the guardrails only mean something if the twin evaluated the proposal

Added 2026-08-04, after the baseline term of §3.3 exposed a defect it did not cause.

No comparison in this document is worth anything when the twin scored a network other than the one
proposed. `_apply_cell_config` overlays a config item with `topo[cell_id] == item.cell_id`, which
matches nothing for a cell the baseline topology lacks: the tilt write lands nowhere and the
`on_off` filter removes no row. The twin then returns the untouched baseline, and BOTH terms agree —
the absolute floor is satisfied and the regression delta is exactly zero. **A gate built entirely
from §2 passes that proposal, twice over.** The tell is `baseline_kpis == guardrail_kpis` to the
last decimal, and it is only observable at all because §3.3 added the baseline term.

So the evaluator is guarded by a precondition, checked BEFORE the twin runs and outside
`evaluate_guardrails`:

| Condition | Verdict |
| --- | --- |
| a `cell_id` not in the baseline topology | `fail` — `unscorable_proposal: cell '…' is not in the baseline topology` |
| topology has no `cell_id` column (the overlay applies nothing at all) | `fail` — one aggregate reason, not one per cell |
| topology cannot be read | `fail` — `unreadable_topology: <type>: <msg>` |

Fail-closed in all three, because none of them is evidence that a change is safe. It costs nothing
that worked before: `run_evaluation` loads the same topology as its first step, so an unreadable
baseline already ended on `evaluation_failed`, only later and with a worse message.

The rule lives in `decision_hub.unscored_recommendations(proposal, known_cells)` — beside the
unknown-TICK guard, which is the same failure by a different key — and stays pure; the I/O is
`ndt_runner.topology_cell_ids`. That reads RAW topology rather than the merged frame, which is sound
because `build_cell_config_frame` only ever LEFT-merges the config CSV: config can retune a cell,
never introduce one. A test pins that merge so the equivalence cannot rot silently.

**Not covered:** `/ndt/evaluate` called directly still no-ops on an unknown cell. Raising inside the
per-tick overlay would change a public endpoint's behaviour for every caller, which is a contract
decision this document does not own.

### 3.9 Out of scope

Retuning any tenant's actual thresholds (an RF sign-off question, smo_sim OD4); smo_sim's
device-level `GUARD` constants, which are a second, independent defence layer with its own owner;
adding new device PM counters.
